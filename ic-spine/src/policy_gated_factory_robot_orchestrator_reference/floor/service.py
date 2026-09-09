# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persistent HTTP floor service (FastAPI). Holds ONE backend for the process
lifetime so a ROS 2 connection is established once (not per call).

v1 API — versioned, request-validated, self-documenting (GET /docs, /openapi.json):
  POST /v1/floor-state {}                       -> world state + _meta freshness
  POST /v1/perceive    {target}                 -> symbolic+vision (or vision_only)
  POST /v1/dispatch    {endpoint, action, ...}  -> always 200; read `dispatched`/`verified`
  POST /v1/dispatch-parallel {moves:[left,right]} -> one atomic two-server B=1 GR00T pair
  POST /v1/verify      {predicate, region?}     -> camera yes/no
  GET  /v1/health                               -> liveness incl. ROS context + freshness
                                                   (503 when degraded; never blocks)

Legacy aliases are preserved verbatim for existing adapters (gateway plugin, MCP):
POST /floor-state /perceive /dispatch /verify — including dispatch's 400-on-unverified.

All floor operations serialize through one lock (the cell is a single FIFO queue and
requests mutate one shared floor); /v1/health skips the lock so a wedged floor can
never hide from monitoring. Every response carries an x-request-id header and an
error envelope {"error": {"code", "message", "request_id"}} on failure.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import re
import time
import uuid
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from policy_gated_factory_robot_orchestrator_reference.floor import ops, ros2
from policy_gated_factory_robot_orchestrator_reference.floor.backend import load_backend
from policy_gated_factory_robot_orchestrator_reference.floor.policy import ActionPolicy

log = logging.getLogger("policy_gated_factory_robot_orchestrator_reference.serve")

_CERTIFIED_GROOT_MIXED_COLOR_PAIRS = (
    ("blue", "green"),
    ("green", "red"),
    ("red", "blue"),
)


class _Journal:
    """Append-only mission journal (phase 1 of the audit store). One JSONL line
    per floor operation + the camera frame the VLM saw (frames/<rid>.jpg).
    Never blocks or fails a floor op — journaling errors degrade to debug logs.
    Enabled by IC_JOURNAL_DIR; disabled (no-op) when unset."""

    def __init__(self, root: str | None) -> None:
        import pathlib

        self._root = pathlib.Path(root).expanduser() if root else None
        if self._root is not None:
            try:
                (self._root / "frames").mkdir(parents=True, exist_ok=True)
                self._file = self._root / "journal.jsonl"
            except Exception:
                log.exception("journal: cannot init %s — disabled", root)
                self._root = None

    def record(self, op: str, rid: str, request: dict, result: dict,
               duration_s: float, mission_id: str | None, frame: bytes | None) -> None:
        if self._root is None:
            return
        try:
            import json as _json
            from datetime import UTC, datetime

            entry = {
                "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "request_id": rid,
                "mission_id": mission_id,
                "op": op,
                "request": request,
                "result": result,
                "duration_s": round(duration_s, 3),
                "frame": f"frames/{rid}.jpg" if frame else None,
            }
            with open(self._file, "a") as f:
                f.write(_json.dumps(entry) + "\n")
            if frame:
                (self._root / "frames" / f"{rid}.jpg").write_bytes(frame)
        except Exception:
            log.debug("journal write failed", exc_info=True)


class PerceiveRequest(BaseModel):
    target: str = Field(description="Region to look at: conveyor_1 | tote | rack_1 | table_1")


class DispatchRequest(BaseModel):
    endpoint: str = Field(description="Executing endpoint, e.g. franka_left | mobilebot")
    action: str = Field(description="move | pick_and_place | navigate_to | inspect")
    color: str | None = None
    source: str | None = Field(
        default=None,
        validation_alias=AliasChoices("source", "from"),
        description="Source region for move (legacy key: 'from')",
    )
    destination: str | None = None
    object_id: str | None = Field(default=None, validation_alias=AliasChoices("object_id", "object-id"))
    target_id: str | None = Field(default=None, validation_alias=AliasChoices("target_id", "target-id"))
    location_id: str | None = None
    queue: bool = Field(
        default=False,
        description="Async only: allow stacking behind an in-flight goal. Default "
        "False = a second async dispatch while one runs is refused (surprise "
        "sequential motions were a real incident).",
    )
    wait: bool = Field(
        default=True,
        description="False = async dispatch: return a goal_id immediately and poll "
        "GET /v1/tasks/{goal_id} for the verified result (ros2 backend only; the "
        "mock floor completes synchronously regardless).",
    )
    backend: Literal["groot"] | None = Field(
        default=None,
        description="Execution backend: 'groot' routes the move to the learned GR00T "
        "policy stack (cell follow-mode + per-color router); None = scripted controller. "
        "Restricted to known values so a typo can never silently fall back to the "
        "scripted controller while claiming a policy ran.",
    )
    args: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Device-specific action arguments for scene-declared capabilities. "
            "Control-plane fields remain top-level and cannot be overridden here."
        ),
    )
    # Operator-only reset_scene contract.  These extend the existing dispatch
    # verb; they are never exposed in the agent/Chat tool schema and are only
    # forwarded when action == reset_scene after the policy role check.
    scene_profile: Literal["ic_two_arm", "groot_three_object"] | None = None
    arm: Literal["franka_left", "franka_right", "both"] | None = None
    layout: int | None = Field(default=None, ge=0, le=5)
    layout_left: int | None = Field(default=None, ge=0, le=5)
    layout_right: int | None = Field(default=None, ge=0, le=5)
    seed: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _protect_control_fields(self) -> DispatchRequest:
        reserved = {
            "action", "endpoint", "wait", "queue", "backend", "scene_profile",
            "arm", "layout", "layout_left", "layout_right", "seed",
        }
        overlap = sorted(reserved.intersection(self.args))
        if overlap:
            raise ValueError(
                "args cannot override control fields: " + ", ".join(overlap)
            )
        return self


class ParallelMove(BaseModel):
    """One child of the fixed two-arm GR00T transaction."""

    model_config = ConfigDict(extra="forbid")

    endpoint: Literal["franka_left", "franka_right"]
    color: Literal["red", "blue", "green"]
    source: Literal["conveyor_1", "conveyor_2"]
    destination: Literal["tote_red", "tote_blue", "tote_green"]
    backend: Literal["groot"] = "groot"


class ParallelDispatchRequest(BaseModel):
    """Exactly one independently validated move for each Franka arm."""

    model_config = ConfigDict(extra="forbid")

    moves: list[ParallelMove] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def _validate_pair(self) -> ParallelDispatchRequest:
        by_endpoint = {move.endpoint: move for move in self.moves}
        if set(by_endpoint) != {"franka_left", "franka_right"}:
            raise ValueError(
                "moves must contain one franka_left and one franka_right child"
            )
        expected_source = {
            "franka_left": "conveyor_1",
            "franka_right": "conveyor_2",
        }
        for endpoint, move in by_endpoint.items():
            expected = (expected_source[endpoint], f"tote_{move.color}")
            if (move.source, move.destination) != expected:
                raise ValueError(
                    f"{endpoint} must move {move.color} from "
                    f"{expected[0]} to {expected[1]}"
                )
        return self


def _completed_certified_mixed_pair_prefix(
    state: dict[str, Any],
) -> tuple[int, str | None]:
    """Measure the indivisible Order744 pair prefix from authoritative state."""
    if not all(isinstance(state.get(name), dict) for name in ("tote", "tote_r")):
        return 0, "authoritative tote state is unavailable"

    completion = [
        (
            state["tote"].get(left_color) == "in",
            state["tote_r"].get(right_color) == "in",
        )
        for left_color, right_color in _CERTIFIED_GROOT_MIXED_COLOR_PAIRS
    ]
    prefix = 0
    while prefix < len(completion) and all(completion[prefix]):
        prefix += 1
    if prefix == len(completion):
        return prefix, None
    if any(completion[prefix]):
        return prefix, (
            "tote contents show a partial certified concurrent pair; "
            "reconcile both arm outcomes"
        )
    if any(any(pair) for pair in completion[prefix + 1:]):
        return prefix, (
            "tote contents are not a completed prefix of the certified "
            "mixed-pair order"
        )
    return prefix, None


def _certified_mixed_sequence_refusal(
    req: ParallelDispatchRequest, state: dict[str, Any]
) -> dict[str, Any] | None:
    prefix, conflict = _completed_certified_mixed_pair_prefix(state)
    if conflict is not None:
        return {
            "dispatched": False,
            "action": "move_pair",
            "verified": False,
            "independent_b1_verified": False,
            "parallel_results": {},
            "status": "refused",
            "reason": conflict,
            "certified_pair_prefix": prefix,
        }
    if prefix >= len(_CERTIFIED_GROOT_MIXED_COLOR_PAIRS):
        return {
            "dispatched": False,
            "action": "move_pair",
            "verified": False,
            "independent_b1_verified": False,
            "parallel_results": {},
            "status": "refused",
            "reason": "all three certified mixed pairs are already complete",
            "certified_pair_prefix": prefix,
        }

    by_endpoint = {move.endpoint: move for move in req.moves}
    requested = (
        by_endpoint["franka_left"].color,
        by_endpoint["franka_right"].color,
    )
    expected = _CERTIFIED_GROOT_MIXED_COLOR_PAIRS[prefix]
    if requested != expected:
        return {
            "dispatched": False,
            "action": "move_pair",
            "verified": False,
            "independent_b1_verified": False,
            "parallel_results": {},
            "status": "refused",
            "reason": "requested colors are not the next certified mixed pair",
            "certified_pair_prefix": prefix,
            "expected_colors": {
                "franka_left": expected[0],
                "franka_right": expected[1],
            },
            "requested_colors": {
                "franka_left": requested[0],
                "franka_right": requested[1],
            },
        }
    return None


class VerifyRequest(BaseModel):
    predicate: str = Field(description="Yes/no question about the floor, e.g. 'the tote is on the rack'")
    region: str | None = Field(default=None, description="Region whose camera answers it")


def build_app() -> FastAPI:
    """FastAPI app over one long-lived backend (mock or ros2, from IC_FLOOR_BACKEND)."""
    backend = load_backend()
    live = ros2.is_live_backend(backend)
    state = getattr(backend, "state", None)
    lock = asyncio.Lock()  # serialize floor ops: one FIFO cell, one shared floor
    started = time.time()
    journal = _Journal(os.environ.get("IC_JOURNAL_DIR"))
    policy = ActionPolicy.load()

    def _policy_refusal(req: DispatchRequest, request_obj: Request) -> dict | None:
        params = {
            **req.args,
            **req.model_dump(exclude_none=True, exclude={"args"}),
        }
        reason = policy.check(req.action, params, request_obj.headers.get("x-role"))
        if reason is None:
            return None
        log.warning("policy refusal rid=%s action=%s: %s",
                    getattr(request_obj.state, "rid", "-"), req.action, reason)
        return {"dispatched": False, "endpoint": req.endpoint, "action": req.action,
                "verified": False, "moved": {}, "reason": reason}

    def _parallel_policy_refusal(
        req: ParallelDispatchRequest, request_obj: Request
    ) -> dict | None:
        if os.environ.get("IC_GROOT_PARALLEL_ENABLED", "0") != "1":
            return {
                "dispatched": False,
                "action": "move_pair",
                "verified": False,
                "independent_b1_verified": False,
                "parallel_results": {},
                "status": "refused",
                "reason": (
                    "concurrent GR00T is disabled; set "
                    "IC_GROOT_PARALLEL_ENABLED=1 only after the two-server "
                    "B=1 readiness contract passes"
                ),
            }
        if os.environ.get("IC_GROOT_FLEXIBLE_ORDER", "0") != "1":
            return {
                "dispatched": False,
                "action": "move_pair",
                "verified": False,
                "independent_b1_verified": False,
                "parallel_results": {},
                "status": "refused",
                "reason": (
                    "certified mixed-color parallel GR00T requires "
                    "IC_GROOT_FLEXIBLE_ORDER=1 after readiness qualification"
                ),
            }
        colors = {move.color for move in req.moves}
        if len(colors) != 2:
            return {
                "dispatched": False,
                "action": "move_pair",
                "verified": False,
                "independent_b1_verified": False,
                "parallel_results": {},
                "status": "refused",
                "reason": (
                    "the certified concurrent route requires one mixed-color "
                    "Order744 pair; same-color pairs are not qualified"
                ),
            }
        for move in req.moves:
            params = move.model_dump()
            reason = policy.check("move", params, request_obj.headers.get("x-role"))
            if reason is not None:
                log.warning(
                    "parallel policy refusal rid=%s endpoint=%s: %s",
                    getattr(request_obj.state, "rid", "-"),
                    move.endpoint,
                    reason,
                )
                return {
                    "dispatched": False,
                    "action": "move_pair",
                    "verified": False,
                    "parallel_results": {},
                    "reason": reason,
                }
        return None

    def _record(op: str, request_obj: Request, req_payload: dict, result: dict, t0: float) -> None:
        frame = None
        if op in ("perceive", "verify"):
            take = getattr(ros2, "take_last_frame", None)
            if callable(take):
                frame = take()
        journal.record(op, getattr(request_obj.state, "rid", "-"), req_payload, result,
                       time.time() - t0, request_obj.headers.get("x-mission-id"), frame)

    app = FastAPI(
        title="Policy-Gated Factory Robot Orchestrator Reference floor service",
        version="1.0.0",
        description=__doc__ or "",
    )

    @app.middleware("http")
    async def _meta(request: Request, call_next: Any) -> Any:
        rid = uuid.uuid4().hex[:12]
        request.state.rid = rid
        t0 = time.time()
        try:
            resp = await call_next(request)
        except Exception as exc:  # uniform internal-error envelope
            log.exception("request failed rid=%s path=%s", rid, request.url.path)
            return JSONResponse(
                status_code=500,
                content={"error": {"code": "internal", "message": str(exc), "request_id": rid}},
                headers={"x-request-id": rid},
            )
        resp.headers["x-request-id"] = rid
        log.info("%s %s -> %s in %.2fs rid=%s",
                 request.method, request.url.path, resp.status_code, time.time() - t0, rid)
        return resp

    async def _floor_state() -> dict:
        if live:
            payload = ros2.live_floor_state(backend)
        else:
            payload = ops.floor_state(state)
        return payload

    async def _perceive(req: PerceiveRequest) -> dict:
        if live:
            return await ros2.live_perceive(backend, req.target)
        return ops.perceive(state, req.target)

    async def _watch_async_goal(goal_id: str, req_payload: dict) -> None:
        """Guarantee the journal gets a terminal record for every async goal,
        whether or not the agent ever polls (audit-trail closure)."""
        try:
            await _watch_async_goal_inner(goal_id, req_payload)
        except Exception:
            log.exception("async goal watcher died for %s — journaling the failure", goal_id)
            try:
                journal.record("task_result", "-", {"goal_id": goal_id, **req_payload},
                               {"goal_id": goal_id, "status": "watcher_error"}, 0.0, None, None)
            except Exception:
                log.exception("watcher fallback journaling also failed for %s", goal_id)

    async def _watch_async_goal_inner(goal_id: str, req_payload: dict) -> None:
        deadline = time.time() + 420.0
        while time.time() < deadline:
            await asyncio.sleep(2.0)
            try:
                r = await ros2.live_task_status(backend, goal_id)
            except Exception:
                continue
            if r.get("status") in ("done", "stale"):
                journal.record("task_result", "-", {"goal_id": goal_id, **req_payload},
                               r, 0.0, None, None)
                return
        journal.record("task_result", "-", {"goal_id": goal_id, **req_payload},
                       {"goal_id": goal_id, "status": "watch_timeout"}, 0.0, None, None)

    async def _dispatch(req: DispatchRequest) -> dict:
        if live:
            if req.action == "cancel":
                # Honest refusal: the cell consumes its queue one task at a time, so
                # a cancel command would QUEUE BEHIND the very task it targets and
                # then bounce as unknown. Do not pretend there is a software stop.
                return {"dispatched": False, "status": "refused",
                        "reason": "cancel is not implemented by the cell (it would queue "
                                  "behind the running task) — use the operator abort "
                                  "one-shot or e-stop"}
            goal_args = dict(req.args)
            goal_args.update({k: v for k, v in {
                "color": req.color, "source": req.source, "destination": req.destination,
                "object_id": req.object_id, "target_id": req.target_id,
                "location_id": req.location_id, "backend": req.backend,
            }.items() if v is not None})
            if req.action == "reset_scene":
                goal_args.update({
                    k: v for k, v in {
                        "scene_profile": req.scene_profile,
                        "arm": req.arm,
                        "layout": req.layout,
                        "layout_left": req.layout_left,
                        "layout_right": req.layout_right,
                        "seed": req.seed,
                    }.items() if v is not None
                })
            if not req.wait:
                if req.queue:
                    goal_args["queue"] = True
                r = await ros2.live_dispatch_async(backend, req.endpoint, req.action, goal_args)
                if r.get("goal_id"):
                    asyncio.create_task(_watch_async_goal(r["goal_id"], {"action": req.action, "endpoint": req.endpoint}))
                return r
            return await ros2.live_dispatch(backend, req.endpoint, req.action, goal_args)
        return await ops.dispatch(
            state, endpoint=req.endpoint, action=req.action,
            color=req.color, source=req.source, destination=req.destination,
        )

    async def _dispatch_parallel(req: ParallelDispatchRequest) -> dict:
        if not live:
            return {
                "dispatched": False,
                "action": "move_pair",
                "verified": False,
                "parallel_results": {},
                "reason": "parallel GR00T dispatch requires the ROS 2 backend",
            }
        return await ros2.live_dispatch_parallel(
            backend,
            [move.model_dump() for move in req.moves],
        )

    async def _verify(req: VerifyRequest) -> dict:
        if live:
            return await ros2.live_verify(backend, req.predicate, req.region)
        return {"answer": "unknown", "evidence": "verify needs the ros2 backend + a VLM", "source_used": ""}

    # ---- v1: versioned, validated, always-200 results with _meta -------------
    @app.post("/v1/floor-state")
    async def v1_floor_state() -> dict:
        async with lock:
            payload = await _floor_state()
        payload["_meta"] = _freshness()
        return payload

    @app.post("/v1/perceive")
    async def v1_perceive(req: PerceiveRequest, request: Request) -> dict:
        t0 = time.time()
        async with lock:
            payload = await _perceive(req)
        payload["_meta"] = _freshness()
        # expose the journal id so clients can fetch the exact frame the VLM
        # saw for this op via GET /v1/frames/{request_id}
        payload["_meta"]["request_id"] = request.state.rid
        _record("perceive", request, req.model_dump(exclude_none=True), payload, t0)
        return payload

    @app.post("/v1/dispatch")
    async def v1_dispatch(req: DispatchRequest, request: Request) -> dict:
        t0 = time.time()
        refusal = _policy_refusal(req, request)
        if refusal is not None:
            refusal["_meta"] = _freshness()
            _record("dispatch", request, req.model_dump(exclude_none=True), refusal, t0)
            return refusal
        if req.action == "cancel":
            # control-plane: must NOT queue behind the very task it cancels
            payload = await _dispatch(req)
        else:
            async with lock:
                payload = await _dispatch(req)
        payload["_meta"] = _freshness()
        _record("dispatch", request, req.model_dump(exclude_none=True), payload, t0)
        return payload

    @app.post("/v1/dispatch-parallel")
    async def v1_dispatch_parallel(
        req: ParallelDispatchRequest, request: Request
    ) -> dict:
        t0 = time.time()
        refusal = _parallel_policy_refusal(req, request)
        if refusal is not None:
            refusal["_meta"] = _freshness()
            _record(
                "dispatch_parallel",
                request,
                req.model_dump(),
                refusal,
                t0,
            )
            return refusal
        async with lock:
            state_before = await _floor_state()
            refusal = _certified_mixed_sequence_refusal(req, state_before)
            if refusal is None:
                payload = await _dispatch_parallel(req)
            else:
                payload = refusal
        payload["_meta"] = _freshness()
        _record(
            "dispatch_parallel",
            request,
            req.model_dump(),
            payload,
            t0,
        )
        return payload

    @app.post("/v1/verify")
    async def v1_verify(req: VerifyRequest, request: Request) -> dict:
        t0 = time.time()
        async with lock:
            payload = await _verify(req)
        payload["_meta"] = _freshness()
        payload["_meta"]["request_id"] = request.state.rid
        _record("verify", request, req.model_dump(exclude_none=True), payload, t0)
        return payload

    def _freshness() -> dict:
        meta: dict[str, Any] = {"api": "v1", "uptime_s": round(time.time() - started, 1)}
        health_fn = getattr(backend, "health", None)
        if callable(health_fn):
            try:
                meta.update(health_fn())
            except Exception:
                meta["health_error"] = True
        return meta

    def _lost_goals() -> set[str]:
        """goal_ids journaled as dispatched (status running) with no terminal
        task_result record — i.e. async goals orphaned by a seam restart."""
        root = os.environ.get("IC_JOURNAL_DIR")
        if not root:
            return set()
        try:
            lines = (pathlib.Path(root) / "journal.jsonl").read_text().splitlines()[-2000:]
        except OSError:
            return set()
        started: set[str] = set()
        ended: set[str] = set()
        for line in lines:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            gid = (rec.get("result") or {}).get("goal_id") or (rec.get("request") or {}).get("goal_id")
            if not gid:
                continue
            if rec.get("op") == "dispatch" and (rec.get("result") or {}).get("status") == "running":
                started.add(gid)
            elif rec.get("op") in ("task_result", "task_status") and                     (rec.get("result") or {}).get("status") in ("done", "stale"):
                ended.add(gid)
        return started - ended

    @app.get("/v1/tasks/{goal_id}")
    async def v1_task_status(goal_id: str, request: Request) -> dict:
        t0 = time.time()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", goal_id):
            return {"goal_id": "", "status": "unknown", "reason": "malformed goal_id",
                    "_meta": _freshness()}
        if live:
            payload = await ros2.live_task_status(backend, goal_id)
            if payload.get("status") == "unknown" and goal_id in _lost_goals():
                payload = {"goal_id": goal_id, "status": "lost",
                           "reason": "the seam restarted after this goal was dispatched; "
                                     "the cell may still be executing or already finished "
                                     "— check floor-state/verify, do NOT re-dispatch"}
        else:
            payload = {"goal_id": goal_id, "status": "unknown",
                       "reason": "mock floor dispatches synchronously"}
        payload["_meta"] = _freshness()
        if payload.get("status") != "running":  # F12: don't journal poll spam
            _record("task_status", request, {"goal_id": goal_id}, payload, t0)
        return payload

    @app.get("/v1/health")
    async def v1_health() -> JSONResponse:
        # Deliberately lock-free: a wedged floor op must not hide a dead backend.
        body: dict[str, Any] = {
            "status": "ok",
            "backend": "ros2" if live else "mock",
            "uptime_s": round(time.time() - started, 1),
        }
        health_fn = getattr(backend, "health", None)
        if live and callable(health_fn):
            try:
                h = health_fn()
                body.update(h)
                age = h.get("floor_state_age_s")
                if h.get("ros_ok") is not True or age is None or age > 10.0:
                    body["status"] = "degraded"
            except Exception as exc:
                body["status"] = "degraded"
                body["health_error"] = str(exc)
        return JSONResponse(status_code=200 if body["status"] == "ok" else 503, content=body)

    # ---- audit store queries (read-only; store derives from the journal) -----
    _store = None

    def _get_store():
        nonlocal _store
        root = os.environ.get("IC_JOURNAL_DIR")
        if root and _store is None:
            from policy_gated_factory_robot_orchestrator_reference.floor.store import Store

            _store = Store(root)
        return _store

    @app.get("/v1/missions")
    async def v1_missions(limit: int = 20) -> dict:
        st = _get_store()
        if st is None:
            return {"missions": [], "note": "journal disabled (IC_JOURNAL_DIR unset)"}
        return {"missions": st.missions(limit=max(1, min(limit, 200)))}

    @app.get("/v1/missions/{mission_id}")
    async def v1_mission_detail(mission_id: str, limit: int = 100) -> dict:
        st = _get_store()
        if st is None:
            return {"operations": [], "note": "journal disabled (IC_JOURNAL_DIR unset)"}
        return {"mission_id": mission_id,
                "operations": st.operations(mission_id=mission_id, limit=max(1, min(limit, 500)))}

    @app.get("/v1/frames/{request_id}")
    async def v1_frame(request_id: str):
        # Serve the exact camera frame the VLM saw for one operation, by its
        # request id. Read-only evidence; validated to stay inside frames/.
        import re as _re

        from fastapi.responses import FileResponse, Response

        root = os.environ.get("IC_JOURNAL_DIR")
        if not root or not _re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
            return Response(status_code=404)
        path = pathlib.Path(root).expanduser() / "frames" / f"{request_id}.jpg"  # noqa: ASYNC240
        if not path.is_file():
            return Response(status_code=404)
        return FileResponse(path, media_type="image/jpeg")

    # ---- legacy aliases: exact pre-v1 semantics (plugin + MCP compatibility).
    # Parsed from the raw body: pre-v1 clients post JSON without a Content-Type
    # header, which strict body models would 422.
    async def _legacy_params(request: Request) -> dict:
        import json as _json

        body = await request.body()
        return _json.loads(body or b"{}")

    @app.post("/floor-state")
    async def legacy_floor_state(request: Request) -> dict:
        async with lock:
            return await _floor_state()

    @app.post("/perceive")
    async def legacy_perceive(request: Request) -> dict:
        req = PerceiveRequest.model_validate(await _legacy_params(request))
        t0 = time.time()
        async with lock:
            payload = await _perceive(req)
        _record("perceive", request, req.model_dump(exclude_none=True), payload, t0)
        return payload

    @app.post("/dispatch")
    async def legacy_dispatch(request: Request) -> JSONResponse:
        req = DispatchRequest.model_validate(await _legacy_params(request))
        t0 = time.time()
        refusal = _policy_refusal(req, request)
        if refusal is not None:
            _record("dispatch", request, req.model_dump(exclude_none=True), refusal, t0)
            return JSONResponse(status_code=400, content=refusal)
        if req.action == "cancel":
            result = await _dispatch(req)
        else:
            async with lock:
                result = await _dispatch(req)
        ok = result["dispatched"] and result.get("verified", True)
        _record("dispatch", request, req.model_dump(exclude_none=True), result, t0)
        return JSONResponse(status_code=200 if ok else 400, content=result)

    @app.post("/verify")
    async def legacy_verify(request: Request) -> JSONResponse:
        req = VerifyRequest.model_validate(await _legacy_params(request))
        t0 = time.time()
        async with lock:
            payload = await _verify(req)
        _record("verify", request, req.model_dump(exclude_none=True), payload, t0)
        return JSONResponse(content=payload)

    return app


def build_service(addr: tuple[str, int]):
    """Compatibility constructor: a uvicorn server presenting the stdlib-ish surface
    (.server_address, .serve_forever(), .shutdown()) the CLI and older callers use."""
    import socket

    import uvicorn

    sock = socket.create_server(addr)
    config = uvicorn.Config(build_app(), log_config=None, access_log=False)
    server = uvicorn.Server(config)

    class _Compat:
        server_address = sock.getsockname()

        def serve_forever(self) -> None:
            server.run(sockets=[sock])

        def shutdown(self) -> None:
            server.should_exit = True

    return _Compat()
