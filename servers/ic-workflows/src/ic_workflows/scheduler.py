# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Periodic workflow scheduler — run scheduled workflows on their interval.

Safety/robustness properties (hardened against the scheduler audit):
- **Single-flight per workflow**: a run in progress is never overlapped.
- **Global concurrency cap** (`max_concurrent`, default 2): bounds the TOTAL
  number of scheduled runs actuating at once, so a restart or a burst of
  simultaneously-due schedules cannot pile unsequenced arm actions into the
  seam — the aggregate is capped regardless of how many are due.
- **Cold-start stagger**: a first-seen schedule gets a random phase within its
  interval, so a restart does not synchronize every schedule onto the first tick.
- **Tracked tasks**: run tasks are strongly referenced (not GC-cancellable) and
  drained/cancelled on stop().
- **mtime cache**: each tick re-parses only changed workflow files.

Every scheduled run goes through the same runner -> seam -> policy gate as a
manual run (operator-action refusal, dispatch-always-verified, no auto-retry).
`due()`/`schedules()` take an explicit `now` for deterministic testing.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .spec import Workflow


class Scheduler:
    def __init__(
        self, store: Any, runner: Any, tick_s: float = 5.0,
        max_concurrent: Optional[int] = None, jitter: bool = True,
    ) -> None:
        self.store = store
        self.runner = runner
        self.tick_s = tick_s
        self.jitter = jitter
        cap = (
            max_concurrent if max_concurrent is not None
            else int(os.environ.get("IC_WORKFLOWS_MAX_CONCURRENT", "2"))
        )
        self.max_concurrent = max(1, cap)  # never 0 (would soft-hang all runs)
        self.last_run: Dict[str, float] = {}
        self.last_ok: Dict[str, bool] = {}
        self.running: Set[str] = set()
        self._seeded: Set[str] = set()
        self._cache: Dict[str, Tuple[float, Workflow]] = {}  # path -> (mtime, wf)
        self._tasks: Set[asyncio.Task] = set()
        self._sem: Optional[asyncio.Semaphore] = None
        self._loop_task: Optional[asyncio.Task] = None

    # ---- cheap, cached workflow reads (one parse per changed file per tick) --
    def _scheduled_workflows(self) -> List[Workflow]:
        out: List[Workflow] = []
        root = getattr(self.store, "root", None)
        if root is None:
            return out
        for p in sorted(Path(root).glob("*.yaml")):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            cached = self._cache.get(str(p))
            if cached and cached[0] == mtime:
                wf = cached[1]
            else:
                try:
                    import yaml

                    wf = Workflow.model_validate(yaml.safe_load(p.read_text()))
                except Exception:
                    self._cache.pop(str(p), None)
                    continue
                self._cache[str(p)] = (mtime, wf)
            if wf.schedule:
                out.append(wf)
        return out

    def schedules(self, now: float) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for wf in self._scheduled_workflows():
            sch = wf.schedule
            lr = self.last_run.get(wf.name)
            out.append({
                "name": wf.name,
                "interval_s": sch.interval_s,
                "enabled": sch.enabled,
                "params": sch.params,
                "last_run": lr,
                "next_run": (lr + sch.interval_s) if lr is not None else now,
                "last_ok": self.last_ok.get(wf.name),
                "running": wf.name in self.running,
            })
        return out

    def _seed(self, wfs: List[Workflow], now: float) -> None:
        # First time we see an enabled schedule, give it a random phase so a
        # restart doesn't align every schedule onto the same first tick.
        for wf in wfs:
            if wf.name in self._seeded:
                continue
            self._seeded.add(wf.name)
            if wf.schedule and wf.schedule.enabled and self.jitter:
                phase = random.uniform(0, wf.schedule.interval_s)
                self.last_run[wf.name] = now - phase

    def due(self, now: float) -> List[str]:
        due: List[str] = []
        for s in self.schedules(now):
            if not s["enabled"] or s["name"] in self.running:
                continue
            lr = self.last_run.get(s["name"])
            if lr is None or (now - lr) >= s["interval_s"]:
                due.append(s["name"])
        return due

    async def _run_one(self, name: str) -> None:
        self.running.add(name)
        try:
            assert self._sem is not None
            async with self._sem:  # global cap on concurrent scheduled runs
                wf = self.store.load(name)
                params = wf.schedule.params if getattr(wf, "schedule", None) else {}
                out = await self.runner.run(wf, params)
                self.last_ok[name] = bool(out.get("ok"))
        except Exception:
            self.last_ok[name] = False
        finally:
            self.running.discard(name)

    async def tick(self, now: Optional[float] = None) -> List[str]:
        now = time.time() if now is None else now
        if self._sem is None:
            self._sem = asyncio.Semaphore(self.max_concurrent)
        self._seed(self._scheduled_workflows(), now)
        fired = self.due(now)
        for name in fired:
            self.last_run[name] = now
            task = asyncio.create_task(self._run_one(name))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return fired

    async def loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                pass
            await asyncio.sleep(self.tick_s)

    def start(self) -> None:
        if self._sem is None:
            self._sem = asyncio.Semaphore(self.max_concurrent)
        if self._loop_task is None:
            self._loop_task = asyncio.create_task(self.loop())

    def stop(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            self._loop_task = None
        for t in list(self._tasks):  # abandon in-flight scheduled runs cleanly
            t.cancel()
        self._tasks.clear()
