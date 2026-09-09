# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests: spec safety, templating, runner gating/retry, API, publish shape."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml
from fastapi.testclient import TestClient

from ic_workflows.app import Store, _require_write_token, build_app
from ic_workflows.runner import Runner
from ic_workflows.runner import _step_ok
from ic_workflows.spec import Workflow, resolve_args


def wf_dict(**over: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "name": "sort-one-cube",
        "description": "perceive then move one cube",
        "params": {"color": "cube color"},
        "steps": [
            {"tool": "perceive", "args": {"target": "conveyor_1"}},
            {
                "tool": "dispatch_task",
                "args": {
                    "action": "move",
                    "endpoint": "franka_left",
                    "color": "${params.color}",
                    "source": "conveyor_1",
                    "destination": "tote",
                },
                "max_retries": 1,
            },
            {
                "tool": "check_predicate",
                "args": {"predicate": "the cube is in the tote", "region": "tote"},
            },
        ],
        "done_criteria": "cube physically in its tote compartment",
    }
    base.update(over)
    return base


def yes_proof() -> Dict[str, Any]:
    return {
        "answer": "yes",
        "evidence": "the requested object is visibly in the tote",
        "source_used": "inspect_cam",
        "request_id": "req-proof",
    }


class FakeRunner(Runner):
    """Runner with a scripted seam."""

    def __init__(self, script: List[Dict[str, Any]]) -> None:
        super().__init__()
        self.script = list(script)
        self.calls: List[Dict[str, Any]] = []

    async def _call(self, tool: str, args: Dict[str, Any], mission_id: str) -> Dict[str, Any]:
        self.calls.append({"tool": tool, "args": args, "mission_id": mission_id})
        return self.script.pop(0) if self.script else {"error": "script exhausted"}


def runner_dry(wf: Workflow, params: Dict[str, Any]) -> Dict[str, Any]:
    return FakeRunner([]).dry_run(wf, params)


def test_non_loopback_workflows_requires_token() -> None:
    with pytest.raises(RuntimeError, match="without its write token"):
        _require_write_token("0.0.0.0", None, "IC Workflows")
    _require_write_token("0.0.0.0", "secret", "IC Workflows")
    _require_write_token("localhost", None, "IC Workflows")


class TestSpec:
    def test_full_groot_dual_tote_demo_contract(self) -> None:
        """The shipped demo must remain eight actions with visual proof after each."""
        path = Path(__file__).parents[1] / "workflows" / "full-groot-dual-tote.yaml"
        wf = Workflow.model_validate(yaml.safe_load(path.read_text()))

        assert len(wf.steps) == 20
        dispatch_indices = [
            index
            for index, step in enumerate(wf.steps)
            if step.tool == "dispatch_task"
        ]
        assert len(dispatch_indices) == 8
        assert all(
            index + 1 < len(wf.steps)
            and wf.steps[index + 1].tool == "check_predicate"
            for index in dispatch_indices
        )
        proofs = [step for step in wf.steps if step.tool == "check_predicate"]
        assert len(proofs) == 9
        assert all(proof.max_retries == 1 for proof in proofs)
        assert all(
            step.max_retries == 0
            for step in wf.steps
            if step.tool != "check_predicate"
        )

        groot_moves = [
            wf.steps[index].args
            for index in dispatch_indices
            if wf.steps[index].args["action"] == "move"
        ]
        assert [
            (move["endpoint"], move["color"], move["backend"])
            for move in groot_moves
        ] == [
            ("franka_right", "green", "groot"),
            ("franka_left", "green", "groot"),
            ("franka_right", "red", "groot"),
            ("franka_left", "red", "groot"),
            ("franka_right", "blue", "groot"),
            ("franka_left", "blue", "groot"),
        ]

        hauls = [
            wf.steps[index].args
            for index in dispatch_indices
            if wf.steps[index].args["action"] == "pick_and_place"
        ]
        assert [
            (haul["endpoint"], haul["object_id"], haul["target_id"])
            for haul in hauls
        ] == [
            ("mobilebot", "tote", "rack_1"),
            ("mobilebot", "tote_r", "rack_1"),
        ]
        assert "fresh VLM answer=yes" in wf.done_criteria

    def test_concurrent_groot_demo_matches_validated_mixed_order(self) -> None:
        path = (
            Path(__file__).parents[1]
            / "workflows"
            / "full-groot-dual-tote-concurrent.yaml"
        )
        wf = Workflow.model_validate(yaml.safe_load(path.read_text()))

        pairs = [step for step in wf.steps if step.tool == "dispatch_parallel"]
        assert len(pairs) == 3
        assert [
            tuple(move["color"] for move in pair.args["moves"])
            for pair in pairs
        ] == [
            ("blue", "green"),
            ("green", "red"),
            ("red", "blue"),
        ]
        for pair in pairs:
            moves = pair.args["moves"]
            assert {move["endpoint"] for move in moves} == {
                "franka_left",
                "franka_right",
            }
            assert {move["backend"] for move in moves} == {"groot"}
            assert len({move["color"] for move in moves}) == 2
            assert pair.max_retries == 0
        proofs = [step for step in wf.steps if step.tool == "check_predicate"]
        assert len(proofs) == 8
        assert all(proof.max_retries == 1 for proof in proofs)
        assert all(
            step.max_retries == 0
            for step in wf.steps
            if step.tool != "check_predicate"
        )
        assert wf.dispatch_actions() == ["move", "pick_and_place"]
        assert "IC_GROOT_PARALLEL_ENABLED=1" in wf.description
        assert "IC_GROOT_FLEXIBLE_ORDER=1" in wf.description
        assert (Path(__file__).parents[1] / "workflows" / "full-groot-dual-tote.yaml").is_file()

    def test_operator_actions_refused_at_save_time(self) -> None:
        bad = wf_dict()
        bad["steps"][1]["args"]["action"] = "reset"
        with pytest.raises(Exception, match="not agent-class"):
            Workflow.model_validate(bad)

    def test_non_string_action_refused(self) -> None:
        bad = wf_dict()
        bad["steps"][1]["args"]["action"] = ["reset"]  # non-string smuggling
        with pytest.raises(Exception, match="action must be a string"):
            Workflow.model_validate(bad)

    def test_dispatch_always_gates_even_if_require_verified_false(self) -> None:
        d = wf_dict()
        d["steps"][1]["require_verified"] = False  # try to disable the gate
        wf = Workflow.model_validate(d)
        assert wf.steps[1].gates() is True  # dispatch is always verified-gated

    def test_forward_references_refused(self) -> None:
        bad = wf_dict()
        bad["steps"][0]["args"]["target"] = "${steps.2.answer}"
        with pytest.raises(Exception, match="forward reference"):
            Workflow.model_validate(bad)

    def test_templating_resolves_params_and_steps(self) -> None:
        out = resolve_args(
            {"color": "${params.color}", "target": "${steps.0.observed.region}"},
            {"color": "red"},
            [{"observed": {"region": "tote"}}],
        )
        assert out == {"color": "red", "target": "tote"}

    def test_skill_manifest_shape(self) -> None:
        manifest = Workflow.model_validate(wf_dict()).to_skill_manifest()
        for field in ("name", "version", "description", "requires_tools",
                      "allowed_actions", "done_criteria"):
            assert manifest[field], field
        assert manifest["allowed_actions"] == ["move"]


class TestRunner:
    async def test_dry_run_calls_nothing(self) -> None:
        runner = FakeRunner([])
        wf = Workflow.model_validate(wf_dict())
        out = runner.dry_run(wf, {"color": "red"})
        assert out["ok"] is True
        assert runner.calls == []
        assert out["timeline"][1]["args"]["color"] == "red"

    async def test_dry_run_tolerates_step_refs(self) -> None:
        # A workflow chaining step outputs must dry-run clean (no live results).
        spec = wf_dict()
        spec["steps"].append(
            {"tool": "check_predicate", "args": {"predicate": "${steps.0.target}"}}
        )
        wf = Workflow.model_validate(spec)
        out = runner_dry(wf, {"color": "red"})
        assert out["ok"] is True
        assert out["timeline"][-1]["args"]["predicate"] == "<steps.0.target>"

    async def test_dry_run_reports_missing_param(self) -> None:
        out = runner_dry(Workflow.model_validate(wf_dict()), {})
        assert out["ok"] is False
        assert any("missing param" in e for e in out["errors"])

    async def test_gated_step_stops_run(self) -> None:
        runner = FakeRunner(
            [{"observed": True}, {"dispatched": True, "verified": False, "reason": "missed"}]
        )
        wf = Workflow.model_validate(wf_dict())
        wf.steps[1].max_retries = 0
        out = await runner.run(wf, {"color": "red"})
        assert out["ok"] is False
        assert len(out["timeline"]) == 2  # never reached check_predicate

    async def test_templated_operator_action_refused_at_runtime(self) -> None:
        # A dispatch whose action is ${params.mode} passes save-time validation,
        # but the runner must refuse the resolved operator action before the seam.
        spec = wf_dict()
        spec["params"] = {"mode": "the action"}
        spec["steps"][1]["args"]["action"] = "${params.mode}"
        wf = Workflow.model_validate(spec)  # valid at save time
        runner = FakeRunner([{"observed": True}])  # seam should NEVER be called
        out = await runner.run(wf, {"mode": "reset", "color": "red"})
        assert out["ok"] is False
        # only the perceive ran; the dispatch was refused before any seam call
        assert not any(c["tool"] == "dispatch_task" for c in runner.calls)
        assert "not agent-class" in str(out["timeline"][-1])

    async def test_templated_action_unhashable_param_refused_cleanly(self) -> None:
        # ${params.mode} resolving to a list/dict must refuse cleanly, not crash.
        spec = wf_dict()
        spec["params"] = {"mode": "the action"}
        spec["steps"][1]["args"]["action"] = "${params.mode}"
        wf = Workflow.model_validate(spec)
        runner = FakeRunner([{"observed": True}])
        out = await runner.run(wf, {"mode": ["reset"], "color": "red"})  # unhashable
        assert out["ok"] is False
        assert not any(c["tool"] == "dispatch_task" for c in runner.calls)

    async def test_dispatch_not_retried_on_transport_error(self) -> None:
        # A timed-out move may have physically executed; retrying double-moves.
        runner = FakeRunner(
            [{"observed": True}, {"error": "ReadTimeout", "transport_error": True}]
        )
        wf = Workflow.model_validate(wf_dict())
        wf.steps[1].max_retries = 3
        out = await runner.run(wf, {"color": "red"})
        assert out["ok"] is False
        assert out["timeline"][1]["attempts"] == 1  # NOT retried

    async def test_dispatch_never_auto_retries(self) -> None:
        # The seam returns verified=false even on its own confirm-timeout, AFTER
        # the arm moved — so an unverified dispatch must NEVER be re-sent.
        runner = FakeRunner(
            [
                {"observed": True},
                {"dispatched": True, "verified": False, "reason": "timeout waiting for /ic/result"},
                {"dispatched": True, "verified": True},  # must not be consumed
            ]
        )
        wf = Workflow.model_validate(wf_dict())
        wf.steps[1].max_retries = 3  # ignored for dispatch
        out = await runner.run(wf, {"color": "red"})
        assert out["ok"] is False
        assert out["timeline"][1]["attempts"] == 1
        assert len(runner.calls) == 2  # perceive + one dispatch; no re-dispatch

    async def test_parallel_dispatch_requires_independent_b1_and_is_not_retried(
        self, monkeypatch,
    ) -> None:
        monkeypatch.setenv("IC_GROOT_PARALLEL_ENABLED", "1")
        monkeypatch.setenv("IC_GROOT_FLEXIBLE_ORDER", "1")
        spec = wf_dict()
        spec["steps"] = [
            {
                "tool": "dispatch_parallel",
                "args": {
                    "moves": [
                        {
                            "endpoint": "franka_left",
                            "color": "blue",
                            "source": "conveyor_1",
                            "destination": "tote_blue",
                            "backend": "groot",
                        },
                        {
                            "endpoint": "franka_right",
                            "color": "green",
                            "source": "conveyor_2",
                            "destination": "tote_green",
                            "backend": "groot",
                        },
                    ]
                },
                "max_retries": 3,
            },
            {
                "tool": "check_predicate",
                "args": {"predicate": "both green bricks are in their totes"},
            },
        ]
        runner = FakeRunner(
            [
                {"dispatched": True, "verified": True},
                yes_proof(),  # must not be consumed
            ]
        )
        out = await runner.run(Workflow.model_validate(spec), {"color": "green"})

        assert out["ok"] is False
        assert out["started_steps"] == 1
        assert out["timeline"][0]["attempts"] == 1
        assert len(runner.calls) == 1

    async def test_mixed_parallel_dispatch_requires_both_opt_in_flags(
        self, monkeypatch,
    ) -> None:
        spec = wf_dict()
        spec["steps"] = [{
            "tool": "dispatch_parallel",
            "args": {
                "moves": [
                    {
                        "endpoint": "franka_left",
                        "color": "blue",
                        "source": "conveyor_1",
                        "destination": "tote_blue",
                        "backend": "groot",
                    },
                    {
                        "endpoint": "franka_right",
                        "color": "green",
                        "source": "conveyor_2",
                        "destination": "tote_green",
                        "backend": "groot",
                    },
                ]
            },
        }]
        workflow = Workflow.model_validate(spec)

        monkeypatch.delenv("IC_GROOT_PARALLEL_ENABLED", raising=False)
        monkeypatch.delenv("IC_GROOT_FLEXIBLE_ORDER", raising=False)
        disabled = FakeRunner([])
        outcome = await disabled.run(workflow, {})
        assert outcome["ok"] is False
        assert outcome["timeline"][0]["attempts"] == 0
        assert "IC_GROOT_PARALLEL_ENABLED=1" in outcome["timeline"][0]["response"]["reason"]
        assert disabled.calls == []

        monkeypatch.setenv("IC_GROOT_PARALLEL_ENABLED", "1")
        parallel_only = FakeRunner([])
        outcome = await parallel_only.run(workflow, {})
        assert outcome["ok"] is False
        assert "IC_GROOT_FLEXIBLE_ORDER=1" in outcome["timeline"][0]["response"]["reason"]
        assert parallel_only.calls == []

        monkeypatch.setenv("IC_GROOT_FLEXIBLE_ORDER", "1")
        same_color_spec = yaml.safe_load(yaml.safe_dump(spec))
        right_move = same_color_spec["steps"][0]["args"]["moves"][1]
        right_move["color"] = "blue"
        right_move["destination"] = "tote_blue"
        same_color = FakeRunner([])
        outcome = await same_color.run(
            Workflow.model_validate(same_color_spec), {}
        )
        assert outcome["ok"] is False
        assert "same-color pairs" in outcome["timeline"][0]["response"]["reason"]
        assert same_color.calls == []

        qualified = FakeRunner([{
            "dispatched": True,
            "verified": True,
            "independent_b1_verified": True,
        }])
        outcome = await qualified.run(workflow, {})
        assert outcome["ok"] is True
        assert len(qualified.calls) == 1

    async def test_nongated_error_marks_run_degraded_not_failed(self) -> None:
        runner = FakeRunner(
            [
                {"error": "conn refused", "transport_error": True},  # perceive (non-gated)
                {"dispatched": True, "verified": True},
                yes_proof(),
            ]
        )
        out = await runner.run(Workflow.model_validate(wf_dict()), {"color": "red"})
        assert out["ok"] is True
        assert out["degraded"] is True

    async def test_vlm_read_step_allows_one_bounded_retry(self) -> None:
        # check_predicate is read-only/idempotent, so one explicit retry is safe.
        spec = wf_dict()
        spec["steps"] = [{"tool": "check_predicate",
                          "args": {"predicate": "the cube is in the tote"},
                          "max_retries": 1}]
        runner = FakeRunner([{"answer": "no"}, yes_proof()])
        out = await runner.run(Workflow.model_validate(spec), {"color": "red"})
        assert out["ok"] is True
        assert out["timeline"][0]["attempts"] == 2

    async def test_mission_id_stamped_per_run(self) -> None:
        runner = FakeRunner(
            [{"observed": True}, {"dispatched": True, "verified": True}, yes_proof()]
        )
        out = await runner.run(Workflow.model_validate(wf_dict()), {"color": "red"})
        ids = {c["mission_id"] for c in runner.calls}
        assert ids == {out["mission_id"]}
        assert out["mission_id"].startswith("wf-sort-one-cube-")

    def test_vlm_gate_requires_yes_evidence_source_and_exact_frame(self) -> None:
        assert _step_ok("check_predicate", yes_proof()) is True
        for missing in ("evidence", "source_used", "request_id"):
            incomplete = yes_proof()
            incomplete.pop(missing)
            assert _step_ok("check_predicate", incomplete) is False
        no = yes_proof()
        no["answer"] = "no"
        assert _step_ok("check_predicate", no) is False

    def test_parallel_gate_requires_physics_and_independent_b1(self) -> None:
        assert _step_ok("dispatch_task", {"verified": True}) is True
        assert _step_ok(
            "dispatch_parallel",
            {"verified": True, "independent_b1_verified": True},
        ) is True
        assert _step_ok("dispatch_parallel", {"verified": True}) is False
        assert _step_ok(
            "dispatch_parallel",
            {"verified": True, "independent_b1_verified": False},
        ) is False
        assert _step_ok(
            "dispatch_parallel",
            {"verified": False, "independent_b1_verified": True},
        ) is False


HDR = {"x-ic-workflows": "console"}  # CSRF guard header the console sends


class TestAPI:
    def make_client(self, tmp_path: Path, script: List[Dict[str, Any]] | None = None):
        runner = FakeRunner(script or [])
        app = build_app(
            store=Store(tmp_path / "workflows"),
            runner=runner,
            skills_dir=tmp_path / "skills",
        )
        return TestClient(app), runner

    def test_crud_roundtrip(self, tmp_path: Path) -> None:
        client, _ = self.make_client(tmp_path)
        assert client.put("/api/workflows/sort-one-cube", json=wf_dict(), headers=HDR).status_code == 200
        assert client.get("/api/workflows/sort-one-cube").json()["name"] == "sort-one-cube"
        listing = client.get("/api/workflows").json()["workflows"]
        assert listing[0]["steps"] == 3
        assert client.delete("/api/workflows/sort-one-cube", headers=HDR).status_code == 200
        assert client.get("/api/workflows/sort-one-cube").status_code == 404

    def test_invalid_spec_rejected(self, tmp_path: Path) -> None:
        client, _ = self.make_client(tmp_path)
        bad = wf_dict()
        bad["steps"][1]["args"]["action"] = "spawn"
        assert client.put("/api/workflows/sort-one-cube", json=bad, headers=HDR).status_code == 422

    def test_publish_writes_conformant_manifest(self, tmp_path: Path) -> None:
        client, _ = self.make_client(tmp_path)
        client.put("/api/workflows/sort-one-cube", json=wf_dict(), headers=HDR)
        body = client.post("/api/workflows/sort-one-cube/publish", headers=HDR).json()
        manifest = yaml.safe_load(Path(body["manifest"]).read_text())
        assert manifest["allowed_actions"] == ["move"]
        try:  # if the conformance kit is importable, hold publish to its bar
            from ic_conformance.kit import check_skill_manifest
        except ImportError:
            return
        results = check_skill_manifest(body["manifest"])
        assert all(r.passed for r in results), [r.name for r in results if not r.passed]

    def test_publish_refuses_foreign_skill_dir(self, tmp_path: Path) -> None:
        client, _ = self.make_client(tmp_path)
        client.put("/api/workflows/sort-one-cube", json=wf_dict(), headers=HDR)
        # a hand-authored skill that happens to collide with the wf- prefix
        foreign = tmp_path / "skills" / "wf-sort-one-cube"
        foreign.mkdir(parents=True)
        (foreign / "manifest.yaml").write_text("name: precious\n")
        resp = client.post("/api/workflows/sort-one-cube/publish", headers=HDR)
        assert resp.status_code == 409
        assert (foreign / "manifest.yaml").read_text() == "name: precious\n"  # untouched

    def test_csrf_missing_header_refused(self, tmp_path: Path) -> None:
        # No X-IC-Workflows header = a cross-origin simple POST → must be refused.
        client, _ = self.make_client(
            tmp_path, [{"dispatched": True, "verified": True}]
        )
        client.put("/api/workflows/sort-one-cube", json=wf_dict(), headers=HDR)
        r = client.post(
            "/api/workflows/sort-one-cube/run", json={"params": {"color": "red"}}
        )  # no HDR
        assert r.status_code == 403
        assert "CSRF" in r.text

    def test_csrf_foreign_origin_refused(self, tmp_path: Path) -> None:
        client, _ = self.make_client(tmp_path)
        r = client.put(
            "/api/workflows/sort-one-cube",
            json=wf_dict(),
            headers={**HDR, "origin": "http://evil.example"},
        )
        assert r.status_code == 403

    def test_csrf_origin_prefix_not_accepted(self, tmp_path: Path) -> None:
        # exact-match, not startswith: a look-alike origin must be refused
        client, _ = self.make_client(tmp_path)
        r = client.put(
            "/api/workflows/sort-one-cube",
            json=wf_dict(),
            headers={**HDR, "origin": "http://127.0.0.1:8600.evil.com"},
        )
        assert r.status_code == 403

    def test_publish_reports_conformance_state_honestly(self, tmp_path: Path) -> None:
        client, _ = self.make_client(tmp_path)
        client.put("/api/workflows/sort-one-cube", json=wf_dict(), headers=HDR)
        body = client.post("/api/workflows/sort-one-cube/publish", headers=HDR).json()
        # kit is installed in CI here → passed; if absent it must say 'skipped',
        # never a false 'passed'.
        assert body["conformance"] in ("passed", "skipped")

    def test_run_endpoint_uses_runner(self, tmp_path: Path) -> None:
        client, runner = self.make_client(
            tmp_path,
            [{"observed": True}, {"dispatched": True, "verified": True}, yes_proof()],
        )
        client.put("/api/workflows/sort-one-cube", json=wf_dict(), headers=HDR)
        out = client.post(
            "/api/workflows/sort-one-cube/run", json={"params": {"color": "red"}}, headers=HDR
        ).json()
        assert out["ok"] is True
        assert runner.calls[1]["args"]["color"] == "red"
