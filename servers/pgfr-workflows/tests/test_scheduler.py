# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Scheduler: due-logic, single-flight, enable gating, API set/list/clear."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml
from fastapi.testclient import TestClient

from pgfr_workflows.app import Store, build_app
from pgfr_workflows.scheduler import Scheduler
from pgfr_workflows.spec import Workflow

HDR = {"x-pgfr-workflows": "console"}


def wf_dict(name: str = "watch-table", **over: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "name": name,
        "description": "perceive the table cam",
        "steps": [{"tool": "perceive", "args": {"target": "table_1"}}],
        "done_criteria": "frame captured",
    }
    base.update(over)
    return base


class RecordingRunner:
    def __init__(self) -> None:
        self.runs: List[str] = []

    async def run(self, wf: Workflow, params: Dict[str, Any]) -> Dict[str, Any]:
        self.runs.append(wf.name)
        return {"ok": True, "mission_id": f"wf-{wf.name}"}


def store_with(tmp_path: Path, *wfs: Dict[str, Any]) -> Store:
    st = Store(tmp_path / "wf")
    for w in wfs:
        st.save(Workflow.model_validate(w))
    return st


class TestDue:
    def test_only_enabled_scheduled_workflows_are_due(self, tmp_path: Path) -> None:
        st = store_with(
            tmp_path,
            wf_dict("on", schedule={"interval_s": 120, "enabled": True}),
            wf_dict("off", schedule={"interval_s": 120, "enabled": False}),
            wf_dict("none"),  # no schedule
        )
        sch = Scheduler(st, RecordingRunner())
        assert sch.due(now=1000.0) == ["on"]

    def test_interval_respected(self, tmp_path: Path) -> None:
        st = store_with(tmp_path, wf_dict("on", schedule={"interval_s": 120, "enabled": True}))
        sch = Scheduler(st, RecordingRunner())
        assert sch.due(now=1000.0) == ["on"]  # never run -> due
        sch.last_run["on"] = 1000.0
        assert sch.due(now=1050.0) == []       # 50s < 120s
        assert sch.due(now=1120.0) == ["on"]   # 120s elapsed

    def test_single_flight(self, tmp_path: Path) -> None:
        st = store_with(tmp_path, wf_dict("on", schedule={"interval_s": 30, "enabled": True}))
        sch = Scheduler(st, RecordingRunner())
        sch.running.add("on")
        assert sch.due(now=9999.0) == []  # a run in progress is not re-fired


class TestTick:
    async def test_tick_runs_due_and_stamps(self, tmp_path: Path) -> None:
        st = store_with(tmp_path, wf_dict("on", schedule={"interval_s": 120, "enabled": True,
                                                          "params": {"x": 1}}))
        runner = RecordingRunner()
        sch = Scheduler(st, runner, jitter=False)
        fired = await sch.tick(now=1000.0)
        assert fired == ["on"]
        assert sch.last_run["on"] == 1000.0
        import asyncio

        await asyncio.sleep(0)  # let the run task execute
        assert runner.runs == ["on"]

    async def test_tick_uses_schedule_params(self, tmp_path: Path) -> None:
        captured = {}

        class ParamRunner:
            async def run(self, wf, params):
                captured.update(params)
                return {"ok": True}

        st = store_with(tmp_path, wf_dict("on", schedule={"interval_s": 30, "enabled": True,
                                                          "params": {"color": "red"}}))
        sch = Scheduler(st, ParamRunner(), jitter=False)
        await sch.tick(now=1.0)
        import asyncio

        await asyncio.sleep(0)
        assert captured == {"color": "red"}


class TestConcurrencyAndRestart:
    async def test_global_concurrency_cap(self, tmp_path: Path) -> None:
        # Many workflows due at once must not all actuate simultaneously —
        # at most max_concurrent run at a time.
        import asyncio

        wfs = [wf_dict(f"w{i}", schedule={"interval_s": 30, "enabled": True}) for i in range(6)]
        st = store_with(tmp_path, *wfs)

        peak = 0
        active = 0
        gate = asyncio.Event()

        class SlowRunner:
            async def run(self, wf, params):
                nonlocal peak, active
                active += 1
                peak = max(peak, active)
                await gate.wait()  # hold all runs open to measure concurrency
                active -= 1
                return {"ok": True}

        sch = Scheduler(st, SlowRunner(), max_concurrent=2, jitter=False)
        await sch.tick(now=1000.0)          # all 6 seeded (no jitter) + due
        await asyncio.sleep(0.02)           # let tasks reach the semaphore
        gate.set()
        await asyncio.sleep(0.02)
        assert peak <= 2, f"peak concurrency {peak} exceeded cap 2"

    async def test_cold_start_stagger_spreads_first_fire(self, tmp_path: Path) -> None:
        # With jitter on, a fresh scheduler does NOT fire everything on tick 1.
        wfs = [wf_dict(f"w{i}", schedule={"interval_s": 120, "enabled": True}) for i in range(8)]
        st = store_with(tmp_path, *wfs)
        sch = Scheduler(st, RecordingRunner(), jitter=True)
        fired = await sch.tick(now=1000.0)
        assert len(fired) < 8  # staggered, not a thundering herd

    async def test_run_tasks_are_tracked_and_stop_drains(self, tmp_path: Path) -> None:
        import asyncio

        st = store_with(tmp_path, wf_dict("hang-wf", schedule={"interval_s": 30, "enabled": True}))

        class Hang:
            async def run(self, wf, params):
                await asyncio.sleep(100)
                return {"ok": True}

        sch = Scheduler(st, Hang(), jitter=False)
        await sch.tick(now=1.0)
        tasks = list(sch._tasks)
        assert len(tasks) == 1  # tracked, not fire-and-forget
        sch.stop()
        await asyncio.sleep(0.01)
        assert tasks[0].cancelled()  # in-flight run cancelled on stop


class TestAPI:
    def make_client(self, tmp_path: Path):
        st = Store(tmp_path / "wf")
        # scheduler present but loop NOT started (run_scheduler=False) for determinism
        return TestClient(build_app(store=st, skills_dir=tmp_path / "sk",
                                    backend=None, run_scheduler=False)), st

    def test_set_schedule_requires_csrf(self, tmp_path: Path) -> None:
        client, st = self.make_client(tmp_path)
        st.save(Workflow.model_validate(wf_dict()))
        r = client.post("/api/workflows/watch-table/schedule",
                        json={"interval_s": 120, "enabled": True})
        assert r.status_code == 403

    def test_set_and_list_schedule(self, tmp_path: Path) -> None:
        client, st = self.make_client(tmp_path)
        st.save(Workflow.model_validate(wf_dict()))
        r = client.post("/api/workflows/watch-table/schedule",
                        json={"interval_s": 120, "enabled": True, "params": {}}, headers=HDR)
        assert r.status_code == 200
        # persisted on the workflow
        assert client.get("/api/workflows/watch-table").json()["schedule"]["interval_s"] == 120
        sched = client.get("/api/schedules").json()["schedules"]
        assert sched[0]["name"] == "watch-table" and sched[0]["enabled"] is True

    def test_min_interval_enforced(self, tmp_path: Path) -> None:
        client, st = self.make_client(tmp_path)
        st.save(Workflow.model_validate(wf_dict()))
        r = client.post("/api/workflows/watch-table/schedule",
                        json={"interval_s": 5, "enabled": True}, headers=HDR)  # < 30s
        assert r.status_code == 422

    def test_clear_schedule(self, tmp_path: Path) -> None:
        client, st = self.make_client(tmp_path)
        st.save(Workflow.model_validate(wf_dict(schedule={"interval_s": 60, "enabled": True})))
        assert client.delete("/api/workflows/watch-table/schedule", headers=HDR).status_code == 200
        assert client.get("/api/workflows/watch-table").json().get("schedule") is None

    def test_editor_save_cannot_resurrect_cleared_schedule(self, tmp_path: Path) -> None:
        # R1: a workflow PUT must not re-arm a schedule the API cleared, even if
        # the client body carries a (stale) schedule.
        client, st = self.make_client(tmp_path)
        st.save(Workflow.model_validate(wf_dict(schedule={"interval_s": 60, "enabled": True})))
        client.delete("/api/workflows/watch-table/schedule", headers=HDR)  # cleared
        stale = wf_dict(schedule={"interval_s": 60, "enabled": True})       # stale client body
        assert client.put("/api/workflows/watch-table", json=stale, headers=HDR).status_code == 200
        # stays cleared — the PUT ignored the client's schedule field
        assert client.get("/api/workflows/watch-table").json().get("schedule") is None

    def test_editor_save_preserves_existing_schedule(self, tmp_path: Path) -> None:
        client, st = self.make_client(tmp_path)
        st.save(Workflow.model_validate(wf_dict()))
        client.post("/api/workflows/watch-table/schedule",
                    json={"interval_s": 90, "enabled": True}, headers=HDR)
        edited = wf_dict(description="edited")  # steps edited, NO schedule in body
        client.put("/api/workflows/watch-table", json=edited, headers=HDR)
        got = client.get("/api/workflows/watch-table").json()
        assert got["description"] == "edited" and got["schedule"]["interval_s"] == 90
