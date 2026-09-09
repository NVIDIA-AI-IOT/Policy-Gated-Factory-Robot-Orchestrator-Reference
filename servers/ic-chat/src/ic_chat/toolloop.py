# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The agentic tool loop — runs the model against the cell through the seam.

The loop lives here, not in the model: when the backend emits a tool call, we
execute it through the SAME seam routes + policy gate the MCP server and
workflow runner use, under a per-conversation mission id. So chat is just
another actor — every floor action it triggers is journaled and appears in the
console's mission replay.

Physical safety is inherited from the seam contract: dispatch is one call, never
auto-retried (an unverified dispatch may already have moved the arm — the model
must perceive and decide its next action explicitly, which the loop supports by
feeding the tool result back).
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import httpx

# The tool verbs exposed to the model — same surface as the MCP server / builder.
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "floor_state",
        "description": (
            "Privileged ROS/Isaac diagnostic snapshot of endpoints and world state. "
            "Use perceive for visual scene understanding and object selection."
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "perceive",
        "description": (
            "Use the VLM to observe one camera region: conveyor_1, conveyor_2, "
            "tote, tote_r, table_1, or rack_1."
        ),
        "parameters": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
            "additionalProperties": False,
        },
    },
    {
        "name": "dispatch_task",
        "description": (
            "Dispatch ONE floor action. move(color, source, destination) on a "
            "franka arm; pick_and_place(object_id, target_id) on mobilebot. "
            "For GR00T moves, the destination is the matching color pad: "
            "tote_red, tote_blue, or tote_green. "
            "Returns verified=true only when the cell physically confirmed the effect."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "endpoint": {"type": "string"},
                "color": {"type": "string"},
                "source": {"type": "string"},
                "destination": {"type": "string"},
                "backend": {
                    "type": "string",
                    "enum": ["groot"],
                    "description": (
                        "Optional learned-policy override. The gateway normally "
                        "selects the arm executor from IC_DEFAULT_BACKEND; the "
                        "agent must not downgrade that configured backend."
                    ),
                },
                "object_id": {"type": "string"},
                "target_id": {"type": "string"},
                "wait": {"type": "boolean",
                         "description": "Optional: false = async dispatch returning a goal_id immediately"},
            },
            "required": ["action", "endpoint"],
            "additionalProperties": False,
        },
    },
    {
        "name": "reset_scene",
        "description": (
            "OPERATOR recovery action. Reset the current hardened Isaac scene "
            "and wait for its verified result. Call only when the user explicitly "
            "asks to reset; the floor refuses it while another task is active."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "check_predicate",
        "description": (
            "Ask the VLM to verify one visible predicate from a fresh camera frame. "
            "Call after every dispatch before starting another physical action."
        ),
        "parameters": {
            "type": "object",
            "properties": {"predicate": {"type": "string"}, "region": {"type": "string"}},
            "required": ["predicate"],
            "additionalProperties": False,
        },
    },
]
_ROUTES = {
    "floor_state": "/v1/floor-state",
    "perceive": "/v1/perceive",
    "dispatch_task": "/v1/dispatch",
    "reset_scene": "/v1/dispatch",
    "check_predicate": "/v1/verify",
}
AGENT_ACTIONS = {"move", "pick_and_place"}

def _dispatch_key(args: Dict[str, Any]) -> tuple[Any, ...]:
    """Stable identity for enforcing one bounded retry per physical step."""
    return tuple(
        args.get(field)
        for field in (
            "action",
            "endpoint",
            "color",
            "source",
            "destination",
            "object_id",
            "target_id",
        )
    )


_PHYSICAL_EFFECT_PATTERNS = (
    re.compile(
        r"\b(?:red|blue|green|cube|block|brick|cylinder|object|tote)\b"
        r".{0,80}\b(?:is|are|was|were|has been|have been)\s+"
        r"(?:now\s+)?(?:in|inside|on|placed|picked|moved|hauled|shelved|seated)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:verified|confirmed|successful(?:ly)?|completed?)\b"
        r".{0,80}\b(?:move|dispatch|pick|plac|haul|shelv|tote|cube|block|brick|cylinder)\b",
        re.IGNORECASE | re.DOTALL,
    ),
)

SYSTEM_PROMPT = (
    "You orchestrate the Policy-Gated Factory Robot Orchestrator Reference warehouse cell. Standard loop: perceive "
    "first, dispatch ONE action at a time, wait for the tool result's 'verified' "
    "field before the next action, then report. The cell is a single FIFO queue — "
    "Use perceive, not floor_state, to understand the visible scene and choose an "
    "object. floor_state is privileged diagnostics for endpoint health or recovery. "
    "Physics verification after an action remains the safety verdict, but it is not "
    "visual evidence. After EVERY dispatch, inspect the physics verdict before acting "
    "again. If verified=true, call check_predicate on the relevant tote or rack camera. "
    "If verified=false, read floor_state to reconcile the attempted action: when the "
    "identity reached the destination, run the normal destination proof; when it remains "
    "at the original conveyor, run check_predicate on that source region asking whether "
    "the exact object is still there. Retry at most once, and only after the proof gate "
    "returns cleared_failed_action. If the identity is at neither place, or the VLM "
    "answers no/unknown or errors, stop and report it; do not substitute floor_state for "
    "the required fresh visual evidence. A demo step is complete only when the dispatch "
    "is physics-verified AND the destination VLM check answers yes with evidence. "
    "The gateway selects the arm executor from IC_DEFAULT_BACKEND. Omit backend "
    "from move tool calls and never downgrade the configured executor. When the "
    "configured default is GR00T, the gateway injects backend='groot' for every "
    "arm move, including the canonical whole-cell sort below, and canonicalizes "
    "a generic tote/tote_r destination to the matching tote_<color> pad. "
    "A vague whole-cell request such as 'check the table, sort the blocks, and "
    "shelve them' is a complete instruction; do not ask the operator to spell "
    "out the steps. In that request, 'table' means the complete two-arm work "
    "surface, including conveyor_1 and conveyor_2. If floor_state reports any "
    "objects with where='conveyor' or lists colors in conveyor_1, the condition "
    "'if there are blocks on the table' is satisfied: sort them and continue to "
    "shelving without stopping for confirmation, even if the table-camera VLM "
    "mislabels their location. That vague whole-cell request is the hardened demo; "
    "do not reinterpret it as a general learned-policy request. Execute the six "
    "GR00T moves in this exact physically certified order: (1) franka_right green "
    "from conveyor_2, (2) franka_left green from conveyor_1, (3) franka_right red "
    "from conveyor_2, (4) franka_left red from conveyor_1, (5) franka_right blue "
    "from conveyor_2, (6) franka_left blue from conveyor_1. Use the matching "
    "tote_<color> destination for every move. Never group all colors on one arm "
    "or reorder this green-first interleaved sequence. If current tote contents "
    "are not a completed prefix of this sequence, stop and request the certified "
    "operator scene reset instead of improvising a different order. The gateway "
    "injects the configured GR00T backend for those six canonical arm moves. "
    "Object identities are fixed: red cube, blue cylinder, "
    "and green rectangular brick. Use those exact identities in visual predicates; "
    "never call the green brick a cube. After each left move "
    "visually verify the moved color in region tote; after each right move verify "
    "it in region tote_r. Then use mobilebot to pick_and_place tote onto rack_1, "
    "verify region rack_1, and separately pick_and_place tote_r onto rack_1 and "
    "verify rack_1 again. Finish with floor_state and declare completion only "
    "when no conveyor objects remain and both tote_on_rack flags are true. Skip "
    "a step only when floor_state proves that exact identity/destination is "
    "already complete. Once both tote_on_rack and tote_r_on_rack are true, the "
    "totes and their cargo have left the arm workcell: those rack flags take "
    "precedence over any stale cube 'where' classification. Never dispatch an "
    "arm move after both rack flags become true; perform only the pending rack "
    "visual proof and final report. "
    "This Traditional IC Chat tool surface intentionally exposes only the "
    "serial dispatch_task fallback. It does not expose dispatch_parallel or "
    "certified_groot_sequence. If an operator explicitly asks this backend to "
    "run objects together, do not simulate concurrency with serial calls and "
    "do not claim the concurrent mission ran; report that the readiness-gated "
    "MCP/OpenClaw surface is required. On that MCP-backed surface, the only "
    "certified concurrent reference is left blue/right green, then left "
    "green/right red, then left red/right blue, with both tote proofs after "
    "every pair; same-color green/red/blue pairs are not the qualified plan. "
    "never request a second action while one is running. Never use operator "
    "actions spawn or cancel. Call reset_scene only when the user explicitly "
    "requests a scene reset; wait for its verified result before continuing. "
    "NEVER claim an action happened unless a tool result in this conversation "
    "shows it (dispatched/verified) — if you did not call the tool, say exactly "
    "that. When asked to call a tool with given arguments, call it with those "
    "arguments verbatim before saying anything. Describe the scene only from "
    "the latest tool results, never from memory."
)


class ToolLoopSettings:
    def __init__(self) -> None:
        self.seam_url = os.environ.get("IC_FLOOR_SERVICE", "http://127.0.0.1:8766").rstrip("/")
        self.max_tool_turns = int(os.environ.get("IC_CHAT_MAX_TURNS", "48"))
        # Seam's longest physical wait is 180 seconds.  Keep a bounded transport
        # margin, but never leave a chat turn waiting for an unbounded response.
        self.timeout_s = float(os.environ.get("IC_CHAT_SEAM_TIMEOUT_S", "200"))


class ToolLoop:
    def __init__(self, settings: Optional[ToolLoopSettings] = None) -> None:
        self.settings = settings or ToolLoopSettings()
        # A mission may not issue its next physical action until the previous
        # dispatch has a fresh, journaled VLM yes+evidence result.  Keep this
        # in the gateway (not only in the prompt) so it survives model turns
        # and cannot be bypassed by an eager planner.
        self._visual_proof_pending: Dict[str, Dict[str, Any]] = {}
        self._stop_requested: set[str] = set()
        self._mission_failure: Dict[str, Dict[str, Any]] = {}
        self._dispatch_attempts: Dict[str, Dict[tuple[Any, ...], int]] = {}

    def request_stop(self, mission_id: str) -> Dict[str, Any]:
        """Cooperatively stop one chat mission at the next safe boundary."""
        self._stop_requested.add(mission_id)
        return {
            "accepted": True,
            "status": "stopping",
            "mission_id": mission_id,
            "reason": (
                "no new physical action will start; an in-flight action and its "
                "required visual proof will finish naturally"
            ),
        }

    async def _seam(self, tool: str, args: Dict[str, Any], mission_id: str) -> Dict[str, Any]:
        route = _ROUTES[tool]
        payload = (
            {
                "endpoint": "mobilebot",
                "action": "reset_scene",
                "scene_profile": "groot_three_object",
                "arm": "both",
                "color": "red",
                "layout_left": 3,
                "layout_right": 3,
                "seed": 31302,
            }
            if tool == "reset_scene"
            else {k: v for k, v in args.items() if v is not None}
        )
        headers = {"x-mission-id": mission_id}
        if tool == "reset_scene":
            headers["x-role"] = "operator"
        async with httpx.AsyncClient(timeout=self.settings.timeout_s) as client:
            try:
                resp = await client.post(
                    f"{self.settings.seam_url}{route}",
                    json=payload,
                    headers=headers,
                )
                body = resp.json()
                out = body if isinstance(body, dict) else {"response": body}
                # Tie this op to the evidence frame the VLM saw (served by the
                # seam at /v1/frames/<request_id>); the frontend renders it.
                rid = resp.headers.get("x-request-id")
                if rid:
                    out.setdefault("request_id", rid)
                return out
            except httpx.ConnectError as exc:
                # The request never established a connection, so no physical
                # command crossed this boundary.
                return {
                    "error": f"{type(exc).__name__}: {exc}",
                    "transport_error": True,
                    "delivery_uncertain": False,
                }
            except Exception as exc:
                # A read timeout, protocol failure, or malformed response can
                # happen after Seam accepted and dispatched the action.  Mark
                # that ambiguity explicitly; callers must reconcile visually
                # before a retry instead of assuming nothing moved.
                return {
                    "error": f"{type(exc).__name__}: {exc}",
                    "transport_error": True,
                    "delivery_uncertain": True,
                }

    async def execute_tool(
        self, name: str, args: Dict[str, Any], mission_id: str
    ) -> Dict[str, Any]:
        if name not in _ROUTES:
            return {"error": f"unknown tool: {name}"}
        if not isinstance(args, dict):
            return {"error": "tool arguments must be an object"}
        # Refuse operator-class actions defensively (the policy gate also would).
        if name == "dispatch_task":
            mission_failure = self._mission_failure.get(mission_id)
            if mission_failure is not None:
                return {
                    "dispatched": False,
                    "verified": False,
                    "status": "refused",
                    "mission_must_stop": True,
                    "reason": (
                        "the preceding physical action ended in a terminal "
                        "unverified state; await a new operator turn"
                    ),
                    "terminal_failure": mission_failure,
                }
            if (
                mission_id in self._stop_requested
                and mission_id not in self._visual_proof_pending
            ):
                return {
                    "dispatched": False,
                    "verified": False,
                    "status": "stopped",
                    "reason": "operator requested stop before this dispatch started",
                }
            action = args.get("action")
            if action not in AGENT_ACTIONS:
                return {"error": f"action '{action}' is not agent-class"}
            pending = self._visual_proof_pending.get(mission_id)
            if pending is not None:
                return {
                    "error": (
                        "fresh VLM verification is required before another "
                        "physical action"
                    ),
                    "status": "refused",
                    "pending_visual_proof": pending,
                }
            # The deployment setting is authoritative: the deliberation model
            # chooses the task, not the motor executor.  In GR00T mode every arm
            # move carries an explicit backend field into the Seam journal,
            # including the canonical six-move whole-cell cycle.
            default_backend = os.environ.get("IC_DEFAULT_BACKEND")
            if action == "move" and default_backend == "groot":
                args = {**args, "backend": "groot"}
            elif action == "move" and args.get("backend") == "scripted":
                # The Seam contract represents the canonical scripted
                # controller by an absent backend field. This compatibility
                # path applies only when the deployment has no GR00T default;
                # "scripted" is intentionally absent from the agent schema.
                args = {k: v for k, v in args.items() if k != "backend"}
            elif default_backend and action == "move" and "backend" not in args:
                args = {**args, "backend": default_backend}
            if action == "move" and args.get("backend") == "groot":
                color = str(args.get("color") or "").strip().lower()
                destination = str(args.get("destination") or "").strip().lower()
                if color in {"red", "blue", "green"}:
                    expected_destination = f"tote_{color}"
                    if destination in {
                        "", "tote", "tote_r", color, expected_destination
                    }:
                        # Arm selection determines left tote versus right tote;
                        # the certified policy contract names the color pad.
                        args = {**args, "destination": expected_destination}
                    else:
                        return {
                            "dispatched": False,
                            "verified": False,
                            "status": "refused",
                            "reason": (
                                "GR00T move destination must match the selected "
                                f"color; expected {expected_destination}, got "
                                f"{destination}"
                            ),
                        }
            # Build the retry identity from the normalized command so a generic
            # first attempt and an exact retry cannot bypass the two-attempt cap.
            attempt_key = _dispatch_key(args)
            attempt_count = self._dispatch_attempts.setdefault(
                mission_id, {}
            ).get(attempt_key, 0)
            if attempt_count >= 2:
                return {
                    "dispatched": False,
                    "verified": False,
                    "status": "refused",
                    "mission_must_stop": True,
                    "reason": (
                        "the one permitted retry for this physical step is "
                        "already exhausted"
                    ),
                    "attempts": attempt_count,
                }
        elif name == "check_predicate" and mission_id in self._visual_proof_pending:
            pending = self._visual_proof_pending[mission_id]
            binding_error = _proof_binding_error(pending, args)
            if binding_error:
                gate_state = (
                    "awaiting_reconciliation"
                    if pending.get("dispatch_verified") is False
                    else "awaiting_vlm"
                )
                return {
                    "error": binding_error,
                    "status": "refused",
                    "pending_visual_proof": pending,
                    "proof_gate": {
                        "state": gate_state,
                        "dispatch": pending,
                        "reason": binding_error,
                    },
                }
        result = await self._seam(name, args, mission_id)
        if name == "reset_scene" and result.get("verified") is True:
            self._visual_proof_pending.pop(mission_id, None)
            self._mission_failure.pop(mission_id, None)
            self._dispatch_attempts.pop(mission_id, None)
            self._stop_requested.discard(mission_id)
        if name == "dispatch_task":
            if result.get("delivery_uncertain"):
                result = {
                    **result,
                    "dispatched": None,
                    "verified": False,
                    "reason": (
                        "dispatch response deadline expired after delivery may "
                        "have occurred; reconcile the object before any retry"
                    ),
                }
            # A non-refused seam call may already have moved hardware even if
            # its final physics verdict is false or a timeout is reported.
            # Therefore every attempted physical action closes the gate.
            if (
                result.get("status") != "refused"
                and (
                    not result.get("transport_error")
                    or result.get("delivery_uncertain")
                )
            ):
                attempts = self._dispatch_attempts.setdefault(mission_id, {})
                attempt_number = attempts.get(attempt_key, 0) + 1
                attempts[attempt_key] = attempt_number
                pending = {
                    "action": args.get("action"),
                    "endpoint": args.get("endpoint"),
                    "color": args.get("color"),
                    "source": args.get("source"),
                    "destination": args.get("destination"),
                    "object_id": args.get("object_id"),
                    "target_id": args.get("target_id"),
                    "dispatch_verified": result.get("verified"),
                    "dispatch_dispatched": result.get("dispatched"),
                    "attempt_number": attempt_number,
                }
                pending = {k: v for k, v in pending.items() if v is not None}
                self._visual_proof_pending[mission_id] = pending
                gate_state = (
                    "awaiting_reconciliation"
                    if result.get("verified") is False
                    else "awaiting_vlm"
                )
                result = {
                    **result,
                    "proof_gate": {
                        "state": gate_state,
                        "dispatch": pending,
                        "reason": (
                            "unverified physical attempt must be visually reconciled "
                            "at its destination or original source before any retry"
                            if result.get("verified") is False
                            else "fresh destination visual proof required"
                        ),
                    },
                }
        elif name == "check_predicate" and mission_id in self._visual_proof_pending:
            pending = self._visual_proof_pending[mission_id]
            source_reconciliation = bool(
                pending.get("action") == "move"
                and pending.get("dispatch_verified") is False
                and str(args.get("region") or "").strip().lower()
                == str(pending.get("source") or "").strip().lower()
            )
            visual_ok = bool(
                result.get("answer") == "yes"
                and str(result.get("evidence") or "").strip()
                and str(result.get("source_used") or "").strip()
                and str(result.get("request_id") or "").strip()
            )
            identity = {
                "ok": False,
                "reason": "identity check waits for a valid visual yes result",
            }
            if visual_ok:
                # A VLM can mistake the flat colored pad for the object.  Bind
                # every visual yes to an authoritative identity read before
                # clearing the physical-action gate.
                state = await self._seam("floor_state", {}, mission_id)
                identity = (
                    _source_identity_proof(pending, state)
                    if source_reconciliation
                    else _identity_proof(pending, state)
                )
            proof_ok = bool(visual_ok and identity.get("ok"))
            if proof_ok:
                cleared = self._visual_proof_pending.pop(mission_id)
                failed_attempt = pending.get("dispatch_verified") is False
                attempt_number = int(pending.get("attempt_number", 1))
                terminal_state = None
                terminal_reason = None
                if failed_attempt and not source_reconciliation:
                    terminal_state = "reconciled_unverified_destination"
                    terminal_reason = (
                        "the identity reached the destination, but the physical "
                        "executor did not verify the action"
                    )
                elif source_reconciliation and attempt_number >= 2:
                    terminal_state = "failed_retry_exhausted"
                    terminal_reason = (
                        "the retry also failed and the identity is back at the "
                        "original source"
                    )
                if terminal_state is not None:
                    failure = {
                        "state": terminal_state,
                        "dispatch": cleared,
                        "reason": terminal_reason,
                    }
                    self._mission_failure[mission_id] = failure
                    result = {
                        **result,
                        "identity_proof": identity,
                        "retry_allowed": False,
                        "step_complete": False,
                        "mission_must_stop": True,
                        "proof_gate": failure,
                    }
                    return result
                cleared_state = (
                    "cleared_failed_action"
                    if source_reconciliation
                    else "cleared"
                )
                result = {
                    **result,
                    "identity_proof": identity,
                    "retry_allowed": source_reconciliation,
                    "proof_gate": {
                        "state": cleared_state,
                        "dispatch": cleared,
                        "reason": (
                            "failed action reconciled: identity is visually and "
                            "authoritatively confirmed at the original source"
                            if source_reconciliation
                            else "destination visual and identity proof cleared"
                        ),
                    },
                }
            else:
                failed_attempt = pending.get("dispatch_verified") is False
                if failed_attempt:
                    terminal_state = None
                    terminal_reason = None
                    if not visual_ok:
                        terminal_state = "failed_visual_reconciliation"
                        terminal_reason = (
                            "fresh visual reconciliation did not return "
                            "answer=yes with evidence"
                        )
                    else:
                        destination = _identity_proof(pending, state)
                        source = _source_identity_proof(pending, state)
                        if not destination.get("ok") and not source.get("ok"):
                            terminal_state = "failed_irreconcilable"
                            terminal_reason = (
                                "authoritative identity is at neither the "
                                "intended destination nor the original source"
                            )
                    if terminal_state is not None:
                        cleared = self._visual_proof_pending.pop(mission_id)
                        failure = {
                            "state": terminal_state,
                            "dispatch": cleared,
                            "reason": terminal_reason,
                        }
                        self._mission_failure[mission_id] = failure
                        result = {
                            **result,
                            "identity_proof": identity,
                            "retry_allowed": False,
                            "step_complete": False,
                            "mission_must_stop": True,
                            "proof_gate": failure,
                        }
                        return result
                result = {
                    **result,
                    "identity_proof": identity,
                    "retry_allowed": False,
                    "proof_gate": {
                        "state": (
                            "awaiting_reconciliation"
                            if failed_attempt
                            else ("awaiting_identity" if visual_ok else "awaiting_vlm")
                        ),
                        "dispatch": pending,
                        "reason": (
                            "unverified dispatch requires fresh visual evidence "
                            "and matching floor identity at either the intended "
                            "destination or the original source"
                            if failed_attempt
                            else (
                                "requires a fresh visual answer=yes with evidence "
                                "and a matching floor-state identity in the "
                                "intended tote/rack"
                            )
                        ),
                    },
                }
        return result
    async def run(
        self,
        backend: Any,
        history: List[Dict[str, Any]],
        mission_id: str,
    ) -> Dict[str, Any]:
        """Batch form of :meth:`run_stream` — collect the same events.

        One implementation, two shapes: the streaming loop is the only place
        the model and the seam are driven, so a live turn and a replayed turn
        can never disagree.
        """
        transcript: List[Dict[str, Any]] = []
        async for event in self.run_stream(backend, history, mission_id):
            if event.get("role") in ("assistant", "tool"):
                transcript.append(event)
        return {"transcript": transcript, "mission_id": mission_id}

    async def run_stream(
        self,
        backend: Any,
        history: List[Dict[str, Any]],
        mission_id: str,
    ):
        """Yield each turn event as it happens: assistant text, then every tool
        call with its result (and the request_id its evidence frame hangs off).

        Same loop, same guarantees — the operator just sees the mission unfold
        instead of waiting for a wall of text at the end.

        Enforces the floor's single-action rule in CODE (not just the prompt):
        at most ONE dispatch_task actuates per model turn, and the loop always
        feeds the result back before the model can act again — so a model that
        emits several dispatches at once cannot fire them blindly, and an
        unverified dispatch forces re-deliberation instead of blind continuation.
        """
        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
        # Terminal reconciliation blocks the remainder of the current model
        # turn. A new operator turn is the explicit boundary for fresh
        # direction; pending visual proof, if any, remains persistent.
        self._mission_failure.pop(mission_id, None)
        if mission_id not in self._visual_proof_pending:
            self._dispatch_attempts[mission_id] = {}
        # A proof may legitimately be retried in a later user turn after the
        # physical dispatch already happened (for example, after a transient
        # camera failure). Preserve that action context so a successful bound
        # proof can be acknowledged without demanding a duplicate dispatch.
        dispatch_attempted = mission_id in self._visual_proof_pending
        stop_notice_sent = False
        for _turn in range(self.settings.max_tool_turns):
            proof_pending = mission_id in self._visual_proof_pending
            if mission_id in self._stop_requested and not proof_pending:
                self._stop_requested.discard(mission_id)
                yield {
                    "role": "assistant",
                    "content": (
                        "Stopped by the operator. No further physical action "
                        "was dispatched."
                    ),
                    "tool_calls": [],
                }
                break
            if (
                mission_id in self._stop_requested
                and proof_pending
                and not stop_notice_sent
            ):
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "The operator requested Stop while a physical action "
                            "was in flight. Do not dispatch another action. Complete "
                            "only the pending bound check_predicate visual proof; "
                            "then the gateway will end this turn."
                        ),
                    }
                )
                stop_notice_sent = True
            reply = await backend.respond(messages, TOOLS)
            content = reply.get("content", "")
            calls = list(reply.get("tool_calls", []))
            has_dispatch_call = any(
                c.get("name", "") == "dispatch_task" for c in calls
            )
            claims_effect = _claims_physical_effect(content)
            proof_pending = mission_id in self._visual_proof_pending

            # Model prose is not actuation evidence.  If it claims an effect
            # before this user turn has produced any dispatch, reject the
            # entire proposed turn (including premature verification reads)
            # and force a real dispatch call.  This caught a live incident
            # where the model said "right red is now in the tote" and jumped
            # straight to check_predicate without ever calling dispatch_task.
            if claims_effect and not dispatch_attempted and not has_dispatch_call:
                correction = (
                    "Action-claim gate: no dispatch_task has executed in this "
                    "user turn, so no physical effect may be claimed or "
                    "verified. Call dispatch_task with the requested action "
                    "before any success statement or post-action check."
                )
                yield {"role": "assistant", "content": correction, "tool_calls": []}
                messages.append({"role": "system", "content": correction})
                continue

            # Text is generated before this reply's tools execute.  Never show
            # a success claim while the dispatch or its required fresh VLM
            # proof is still outstanding.
            if claims_effect and (has_dispatch_call or proof_pending):
                content = (
                    "Physical result pending: waiting for the dispatch and "
                    "required fresh visual verification tool results."
                )

            # A model may not end a turn while a physical action is awaiting
            # its bound VLM proof.  Force it back into the tool loop instead
            # of persisting an unsupported final success report.
            if not calls and proof_pending:
                correction = (
                    "Visual-proof gate: the last physical action still needs "
                    "a bound check_predicate call with a fresh frame before "
                    "this turn can finish."
                )
                yield {"role": "assistant", "content": correction, "tool_calls": []}
                messages.append({"role": "system", "content": correction})
                continue

            yield {"role": "assistant", "content": content, "tool_calls": calls}
            if not calls:
                if content:
                    messages.append({"role": "assistant", "content": content})
                break
            # Decide which calls actually run THIS turn before declaring them:
            # all calls up to and including the first dispatch_task (one actuation
            # per turn). This keeps the OpenAI contract intact — every tool_call
            # the assistant message declares gets a matching tool reply — while
            # the trailing queued dispatches are simply not advertised or run.
            executed = []
            for i, c in enumerate(calls):
                executed.append((i, c))
                if c.get("name", "") == "dispatch_task":
                    break
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": content or None}
            assistant_msg["tool_calls"] = [
                {"id": c.get("id") or f"call_{i}", "type": "function",
                 "function": {"name": c.get("name", ""),
                              "arguments": _dumps(c.get("arguments", {}))}}
                for i, c in executed
            ]
            messages.append(assistant_msg)
            for i, call in executed:
                name = call.get("name", "")
                args = call.get("arguments", {})
                call_id = call.get("id") or f"call_{i}"
                yield {"role": "tool_start", "name": name, "args": args}
                result = await self.execute_tool(name, args, mission_id)
                yield {"role": "tool", "name": name, "args": args, "result": result}
                if (
                    name == "dispatch_task"
                    and result.get("status") != "refused"
                    and not result.get("transport_error")
                    and not result.get("error")
                ):
                    dispatch_attempted = True
                messages.append(
                    {"role": "tool", "tool_call_id": call_id, "content": _short(result)}
                )
        yield {"role": "done", "mission_id": mission_id}


def _claims_physical_effect(content: Any) -> bool:
    """Return true for prose that asserts a completed physical cell effect."""
    text = str(content or "").strip()
    return bool(text and any(pattern.search(text) for pattern in _PHYSICAL_EFFECT_PATTERNS))


def _identity_proof(
    pending: Dict[str, Any], state: Dict[str, Any]
) -> Dict[str, Any]:
    """Bind VLM evidence to the intended object's authoritative destination."""
    base = {"request_id": state.get("request_id")}
    if state.get("error") or state.get("transport_error"):
        return {
            **base,
            "ok": False,
            "reason": state.get("error") or "floor-state transport error",
        }

    action = pending.get("action")
    if action == "move":
        endpoint = str(pending.get("endpoint") or "")
        color = str(pending.get("color") or "")
        target = "tote_r" if endpoint == "franka_right" else "tote"
        expected_where = target
        matching = [
            c
            for c in state.get("cubes", [])
            if c.get("color") == color and c.get("where") == expected_where
        ]
        tote_map = state.get(target) or {}
        ok = bool(color and tote_map.get(color) == "in" and matching)
        return {
            **base,
            "ok": ok,
            "target": target,
            "color": color,
            "expected_where": expected_where,
            "matched_indices": [c.get("i") for c in matching],
            "reason": (
                "matching object identity is in the intended tote"
                if ok
                else "floor_state does not place the moved identity in the intended tote"
            ),
        }

    if action == "pick_and_place":
        object_id = str(pending.get("object_id") or "")
        target_id = str(pending.get("target_id") or "")
        flag = "tote_r_on_rack" if object_id == "tote_r" else "tote_on_rack"
        ok = bool(target_id == "rack_1" and state.get(flag))
        return {
            **base,
            "ok": ok,
            "object_id": object_id,
            "target_id": target_id,
            "state_flag": flag,
            "reason": (
                "tote identity is on rack_1"
                if ok
                else "floor_state does not place the requested tote on rack_1"
            ),
        }

    return {**base, "ok": False, "reason": f"unsupported action {action!r}"}


def _source_identity_proof(
    pending: Dict[str, Any], state: Dict[str, Any]
) -> Dict[str, Any]:
    """Reconcile an unverified move without assuming that it had no effect.

    A retry is safe only when a fresh source-camera VLM check agrees with the
    authoritative floor state that the requested identity remains on a
    conveyor, while the intended destination does not contain that identity.
    """
    base = {"request_id": state.get("request_id")}
    if state.get("error") or state.get("transport_error"):
        return {
            **base,
            "ok": False,
            "reason": state.get("error") or "floor-state transport error",
        }
    if pending.get("action") != "move":
        return {
            **base,
            "ok": False,
            "reason": "source reconciliation is supported only for arm moves",
        }

    color = str(pending.get("color") or "")
    source = str(pending.get("source") or "")
    matching = [
        c
        for c in state.get("cubes", [])
        if c.get("color") == color and c.get("where") == "conveyor"
    ]
    destination = _identity_proof(pending, state)
    ok = bool(
        color
        and source in {"conveyor_1", "conveyor_2"}
        and matching
        and not destination.get("ok")
    )
    return {
        **base,
        "ok": ok,
        "color": color,
        "source": source,
        "expected_where": "conveyor",
        "matched_indices": [c.get("i") for c in matching],
        "destination_identity_ok": bool(destination.get("ok")),
        "reason": (
            "matching identity remains at the original conveyor and is absent "
            "from the intended tote"
            if ok
            else (
                "floor_state cannot safely reconcile the identity at the "
                "original source"
            )
        ),
    }


def _proof_binding_error(
    pending: Dict[str, Any], proof_args: Dict[str, Any]
) -> str | None:
    """Require visual proof to describe the pending action's intended effect."""
    action = str(pending.get("action") or "")
    predicate = str(proof_args.get("predicate") or "").strip().lower()
    region = str(proof_args.get("region") or "").strip().lower()

    if action == "move":
        endpoint = str(pending.get("endpoint") or "")
        source = str(pending.get("source") or "")
        expected_region = (
            "tote_r"
            if endpoint == "franka_right" or source == "conveyor_2"
            else "tote"
        )
        color = str(pending.get("color") or "").strip().lower()
        failed_attempt = pending.get("dispatch_verified") is False
        if failed_attempt and region == source:
            if source not in {"conveyor_1", "conveyor_2"}:
                return "failed move has no supported conveyor source to reconcile"
            if color and color not in predicate:
                return f"source reconciliation must mention the moved color {color!r}"
            if "conveyor" not in predicate:
                return (
                    "source reconciliation must assert that the moved object "
                    "remains on the conveyor"
                )
            return None
        if failed_attempt and region not in {expected_region, source}:
            return (
                "unverified move proof must use destination region "
                f"{expected_region!r} or source region {source!r}, "
                f"not {region or '<missing>'!r}"
            )
        if region != expected_region:
            return (
                "visual proof for this move must use region "
                f"{expected_region!r}, not {region or '<missing>'!r}"
            )
        if color and color not in predicate:
            return f"visual proof must mention the moved color {color!r}"
        if "tote" not in predicate:
            return "visual proof must assert that the moved object is in the tote"
        return None

    if action == "pick_and_place":
        if region != "rack_1":
            return (
                "visual proof for tote shelving must use region 'rack_1', "
                f"not {region or '<missing>'!r}"
            )
        if "tote" not in predicate or not any(
            word in predicate for word in ("rack", "shelf", "shelved")
        ):
            return "visual proof must assert that the tote is on the rack or shelf"
    return None


def _dumps(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj)
    except Exception:
        return "{}"


def _short(result: Dict[str, Any]) -> str:
    # Keep the tool result valid JSON for the model: cap object size by dropping
    # verbose fields rather than truncating mid-string.
    import json

    text = _dumps(result)
    if len(text) <= 2000:
        return text
    slim = {k: result[k] for k in ("verified", "error", "reason", "answer", "dispatched")
            if isinstance(result, dict) and k in result}
    slim["_truncated"] = True
    return _dumps(slim)
