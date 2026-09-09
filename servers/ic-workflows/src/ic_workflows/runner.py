# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Workflow runner — executes a spec through the seam, no privileged path.

Every step is one HTTP call to the floor seam (the same routes the MCP tools
proxy), stamped with a per-run mission id so the journal records the whole run
like any other actor's mission. Gated steps stop the run on failure after
their bounded retries. ``dry_run`` resolves every template and touches
nothing — it is a pure validation pass.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from .spec import AGENT_ACTIONS, TOOLS, Workflow, resolve_args


PHYSICAL_TOOLS = {"dispatch_task", "dispatch_parallel"}


class RunnerSettings:
    def __init__(self) -> None:
        self.seam_url = os.environ.get("IC_FLOOR_SERVICE", "http://127.0.0.1:8766").rstrip("/")
        self.timeout_s = float(os.environ.get("IC_WORKFLOWS_TIMEOUT_S", "300"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _step_ok(tool: str, response: Dict[str, Any]) -> bool:
    if tool == "dispatch_parallel":
        return (
            response.get("verified") is True
            and response.get("independent_b1_verified") is True
        )
    if tool == "dispatch_task":
        return response.get("verified") is True
    if tool == "check_predicate":
        return bool(
            response.get("answer") == "yes"
            and str(response.get("evidence") or "").strip()
            and str(response.get("source_used") or "").strip()
            and str(response.get("request_id") or "").strip()
        )
    return "error" not in response


def _parallel_feature_refusal(args: Dict[str, Any]) -> str | None:
    """Fail closed before a workflow can reach the parallel Seam route.

    ``IC_GROOT_PARALLEL_ENABLED`` is set only after the two independent B=1
    servers and cell contract pass readiness. The certified concurrent route
    also requires the explicit flexible-order opt-in and rejects same-color
    pairs. The Seam enforces the authoritative next-pair state and reports
    per-arm execution evidence.
    """
    if os.environ.get("IC_GROOT_PARALLEL_ENABLED", "0") != "1":
        return (
            "concurrent GR00T is disabled; set IC_GROOT_PARALLEL_ENABLED=1 "
            "only after the two-server B=1 readiness contract passes"
        )
    moves = args.get("moves")
    colors = {
        str(move.get("color") or "").strip().lower()
        for move in moves
        if isinstance(move, dict)
    } if isinstance(moves, list) else set()
    if os.environ.get("IC_GROOT_FLEXIBLE_ORDER", "0") != "1":
        return (
            "certified mixed-color parallel GR00T requires "
            "IC_GROOT_FLEXIBLE_ORDER=1 after readiness qualification"
        )
    if len(colors) != 2:
        return (
            "the certified concurrent route requires one mixed-color "
            "Order744 pair; same-color pairs are not qualified"
        )
    return None


class Runner:
    def __init__(self, settings: Optional[RunnerSettings] = None) -> None:
        self.settings = settings or RunnerSettings()

    async def _call(
        self, tool: str, args: Dict[str, Any], mission_id: str
    ) -> Dict[str, Any]:
        route = TOOLS[tool]["route"]
        async with httpx.AsyncClient(timeout=self.settings.timeout_s) as client:
            try:
                resp = await client.post(
                    f"{self.settings.seam_url}{route}",
                    json=args,
                    headers={"x-mission-id": mission_id},
                )
                body = resp.json()
                result = body if isinstance(body, dict) else {"response": body}
                request_id = resp.headers.get("x-request-id")
                if request_id:
                    result.setdefault("request_id", request_id)
                return result
            except Exception as exc:
                # transport_error means the outcome is UNKNOWN, not "nothing
                # happened" — the runner must never retry a dispatch on this.
                return {"error": f"{type(exc).__name__}: {exc}", "transport_error": True}

    def dry_run(self, wf: Workflow, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate template shape against sample params; call nothing.

        ``${steps.N.field}`` refs cannot be dereferenced without live results,
        so they are substituted with a visible placeholder (the spec validator
        already proved they are backward refs) — only ``${params.*}`` refs are
        genuinely resolved, so a missing param is a real, reported error.
        """
        timeline: List[Dict[str, Any]] = []
        errors: List[str] = []
        for i, step in enumerate(wf.steps):
            resolved: Dict[str, Any] = {}
            for key, value in step.args.items():
                if isinstance(value, str) and value.startswith("${params."):
                    name = value[len("${params.") : -1]
                    if name in params:
                        resolved[key] = params[name]
                    else:
                        errors.append(f"step {i} arg '{key}': missing param '{name}'")
                        resolved[key] = f"<MISSING param.{name}>"
                elif isinstance(value, str) and value.startswith("${steps."):
                    resolved[key] = f"<{value[2:-1]}>"  # resolved at run time
                else:
                    resolved[key] = value
            timeline.append(
                {"step": i, "tool": step.tool, "args": resolved, "gates": step.gates()}
            )
        return {"ok": not errors, "errors": errors, "timeline": timeline, "dry_run": True}

    async def run(self, wf: Workflow, params: Dict[str, Any]) -> Dict[str, Any]:
        mission_id = f"wf-{wf.name}-{uuid.uuid4().hex[:8]}"
        timeline: List[Dict[str, Any]] = []
        results: List[Dict[str, Any]] = []
        ok = True
        for i, step in enumerate(wf.steps):
            try:
                args = resolve_args(step.args, params, results)
            except Exception as exc:
                timeline.append({"step": i, "tool": step.tool, "error": str(exc)})
                results.append({})
                ok = False
                break

            # Re-check the RESOLVED action against the agent-class allowlist —
            # a templated action (${params.*}) could resolve to an operator
            # action; refuse it here, before it can reach the seam. isinstance
            # first so an unhashable resolved value (list/dict from a run param)
            # degrades to a clean refusal, not a TypeError/500.
            if step.tool == "dispatch_task" and (
                not isinstance(args.get("action"), str)
                or args.get("action") not in AGENT_ACTIONS
            ):
                timeline.append({"step": i, "tool": step.tool, "args": args, "ok": False,
                                 "gated": True,
                                 "response": {"error": f"resolved action "
                                              f"{args.get('action')!r} is not agent-class"}})
                results.append({})
                ok = False
                break

            if step.tool == "dispatch_parallel":
                refusal_reason = _parallel_feature_refusal(args)
                if refusal_reason is not None:
                    refusal = {
                        "dispatched": False,
                        "verified": False,
                        "independent_b1_verified": False,
                        "status": "refused",
                        "reason": refusal_reason,
                    }
                    timeline.append({
                        "step": i,
                        "tool": step.tool,
                        "args": args,
                        "attempts": 0,
                        "ok": False,
                        "gated": True,
                        "response": refusal,
                    })
                    results.append(refusal)
                    ok = False
                    break

            # Physical dispatch actuates the world and is NOT idempotent. The seam
            # returns verified=false even on its own confirm-timeout (ros2.py),
            # AFTER a command reached the arm — so an unverified/errored dispatch
            # cannot be safely re-sent (it would double-actuate). Physical
            # dispatch therefore never auto-retries; to recover, a workflow must
            # perceive and conditionally re-dispatch as explicit steps.
            max_attempts = 1 if step.tool in PHYSICAL_TOOLS else step.max_retries + 1
            attempts = 0
            response: Dict[str, Any] = {}
            step_ok = False
            while attempts < max_attempts:
                attempts += 1
                response = await self._call(step.tool, args, mission_id)
                step_ok = _step_ok(step.tool, response)
                if step_ok or not step.gates():
                    break
            results.append(response)
            timeline.append(
                {
                    "step": i,
                    "tool": step.tool,
                    "args": args,
                    "attempts": attempts,
                    "ok": step_ok,
                    "gated": step.gates(),
                    "response": response,
                }
            )
            if step.gates() and not step_ok:
                ok = False
                break

        # A non-gated step that errored (e.g. perceive against an unreachable
        # seam) does not fail the run, but the run is not cleanly ok either.
        degraded = any(
            t.get("ok") is False and not t.get("gated") for t in timeline
        )
        return {
            "ok": ok,
            "degraded": ok and degraded,
            "mission_id": mission_id,
            "workflow": wf.name,
            "started_steps": len(timeline),
            "timeline": timeline,
            "finished_at": _now(),
        }
