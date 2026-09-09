# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Policy-Gated Factory Robot Orchestrator Reference MCP server — the floor seam's tools over MCP.

Thin adapter: each tool proxies one route of the floor service
(IC_FLOOR_SERVICE, default http://127.0.0.1:8766). The canonical playbook
(skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/PLAYBOOK.md) ships as the server
`instructions`, so every MCP client receives the operating manual at connect
time. Safety policy stays at the seam — this layer adds no authority.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from threading import RLock

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


def _seam() -> str:
    return os.environ.get("IC_FLOOR_SERVICE", "http://127.0.0.1:8766").rstrip("/")


def _timeout_s() -> float:
    # hauls take ~2.5 min; the seam enforces its own per-action timeout
    return float(os.environ.get("IC_MCP_TIMEOUT_S", "280"))


_MISSION_ID = "mcp-" + uuid.uuid4().hex[:12]   # one mission per server session (journal grouping)

CERTIFIED_GROOT_SERIAL_ORDER = (
    ("franka_right", "green", "conveyor_2", "tote_green"),
    ("franka_left", "green", "conveyor_1", "tote_green"),
    ("franka_right", "red", "conveyor_2", "tote_red"),
    ("franka_left", "red", "conveyor_1", "tote_red"),
    ("franka_right", "blue", "conveyor_2", "tote_blue"),
    ("franka_left", "blue", "conveyor_1", "tote_blue"),
)

# The optional concurrent reference is a different, live-qualified schedule;
# it is not the serial order grouped into same-color pairs. Each tuple is one
# atomic B=2 cell transaction backed by two independent B=1 policy servers.
CERTIFIED_GROOT_MIXED_PAIRS = (
    (
        ("franka_left", "blue", "conveyor_1", "tote_blue"),
        ("franka_right", "green", "conveyor_2", "tote_green"),
    ),
    (
        ("franka_left", "green", "conveyor_1", "tote_green"),
        ("franka_right", "red", "conveyor_2", "tote_red"),
    ),
    (
        ("franka_left", "red", "conveyor_1", "tote_red"),
        ("franka_right", "blue", "conveyor_2", "tote_blue"),
    ),
)

_SHAPES = {"red": "cube", "blue": "cylinder", "green": "brick"}
_STATE_LOCK = RLock()
_PENDING_PROOF: dict | None = None
_DISPATCH_ATTEMPTS: dict[tuple, int] = {}
_LAST_CERTIFIED_PREFIX: int | None = None


def _certified_order_enabled() -> bool:
    return os.environ.get("IC_CERTIFIED_GROOT_ORDER", "0") == "1"


def _parallel_groot_enabled() -> bool:
    return os.environ.get("IC_GROOT_PARALLEL_ENABLED", "0") == "1"


def _flexible_groot_order_enabled() -> bool:
    """Select the qualified mixed plan without weakening proof gates."""
    return os.environ.get("IC_GROOT_FLEXIBLE_ORDER", "0") == "1"


def _proof_gate_enabled() -> bool:
    return _certified_order_enabled() or _flexible_groot_order_enabled()


def _certified_mixed_mode() -> bool:
    """True only for the explicitly enabled, policy-enforced mixed mission."""
    return (
        _certified_order_enabled()
        and _parallel_groot_enabled()
        and _flexible_groot_order_enabled()
    )


def _json_object(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {"output": raw}
    return value if isinstance(value, dict) else {"output": value}


def _result(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"))


def _refused(reason: str, **extra: object) -> str:
    return _result({
        "dispatched": False,
        "verified": False,
        "status": "refused",
        "reason": reason,
        **extra,
    })


def _pre_dispatch_error(outcome: dict) -> str | None:
    """Return a stable reason for an HTTP/schema error that moved nothing."""
    if "dispatched" in outcome or "verified" in outcome:
        return None
    detail = outcome.get("detail")
    if isinstance(detail, list):
        messages = [
            str(item.get("msg") or "").strip()
            for item in detail
            if isinstance(item, dict)
        ]
        messages = [message for message in messages if message]
        if messages:
            return "; ".join(messages)
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    error = outcome.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    return None


def _completed_certified_prefix(state: dict) -> tuple[int, str | None]:
    complete: list[bool] = []
    for endpoint, color, _source, _destination in CERTIFIED_GROOT_SERIAL_ORDER:
        tote_name = "tote_r" if endpoint == "franka_right" else "tote"
        tote = state.get(tote_name)
        complete.append(isinstance(tote, dict) and tote.get(color) == "in")
    prefix = 0
    while prefix < len(complete) and complete[prefix]:
        prefix += 1
    if any(complete[prefix:]):
        return prefix, "tote contents are not a completed prefix of the certified order"
    return prefix, None


def _completed_certified_pair_prefix(state: dict) -> tuple[int, str | None]:
    """Return completed mixed pairs; reject partial or out-of-order state.

    A concurrent pair is indivisible at the orchestration boundary. Seeing
    only one child at its destination, or seeing a later pair before the next
    pair is complete, requires operator reconciliation rather than another
    physical dispatch.
    """
    if not all(isinstance(state.get(name), dict) for name in ("tote", "tote_r")):
        return 0, (
            "authoritative tote state is unavailable; certified mixed "
            "dispatch fails closed"
        )

    completion: list[tuple[bool, bool]] = []
    for pair in CERTIFIED_GROOT_MIXED_PAIRS:
        children: list[bool] = []
        for endpoint, color, _source, _destination in pair:
            tote_name = "tote_r" if endpoint == "franka_right" else "tote"
            tote = state.get(tote_name)
            children.append(
                isinstance(tote, dict) and tote.get(color) == "in"
            )
        completion.append((children[0], children[1]))

    prefix = 0
    while prefix < len(completion) and all(completion[prefix]):
        prefix += 1
    if prefix == len(completion):
        return prefix, None
    if any(completion[prefix]):
        return prefix, (
            "tote contents show a partial certified concurrent pair; "
            "reconcile both arm outcomes before another dispatch"
        )
    if any(any(pair) for pair in completion[prefix + 1:]):
        return prefix, (
            "tote contents are not a completed prefix of the certified "
            "mixed-pair order"
        )
    return prefix, None


def _pending_identity_matches(
    predicate: str, pending: dict, region: str | None = None
) -> bool:
    text = predicate.lower()
    if pending.get("action") == "move_pair":
        child = (pending.get("children_by_region") or {}).get(region or "") or {}
        color = str(child.get("color") or "").lower()
        shape = _SHAPES.get(color, "object")
        return bool(color and color in text and shape in text)
    if pending.get("action") == "move":
        color = str(pending.get("color") or "").lower()
        shape = _SHAPES.get(color, "object")
        return color in text and shape in text
    object_id = str(pending.get("object_id") or "tote").lower()
    return object_id in text


def _post(route: str, payload: dict, *, role: str | None = None) -> str:
    req = urllib.request.Request(
        f"{_seam()}{route}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-mission-id": _MISSION_ID,
                 "x-role": role or os.environ.get("IC_MCP_ROLE", "agent")},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_timeout_s()) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        # the seam answers 400 with a JSON body for unverified dispatches —
        # that body IS the result the model needs to see
        body = e.read().decode()
        return body or json.dumps({"error": f"HTTP {e.code} from the floor service"})
    except OSError as e:
        return json.dumps({"error": f"floor service unreachable at {_seam()}: {e}"})


def _playbook() -> str:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "skills" / "policy-gated-factory-robot-orchestrator-reference-orchestrator" / "PLAYBOOK.md"
        if candidate.exists():
            return candidate.read_text()
    return (
        "Policy-Gated Factory Robot Orchestrator Reference floor tools. Dispatch exactly ONE action at a time and "
        "wait for each verified result before the next."
    )


mcp = FastMCP("policy-gated-factory-robot-orchestrator-reference-floor", instructions=_playbook())


@mcp.tool(annotations=ToolAnnotations(title="Floor: ground-truth state", readOnlyHint=True))
def floor_state() -> str:
    """Exact symbolic world state: endpoints, conveyor contents, tote contents,
    whether the tote is on the rack. Fast, authoritative ground truth — no camera."""
    return _post("/v1/floor-state", {})


@mcp.tool(annotations=ToolAnnotations(title="Floor: perceive region (camera + VLM)", readOnlyHint=True))
def perceive(target: str) -> str:
    """Look at a region through its camera (Cosmos VLM), fused with symbolic state.
    Targets map to FOUR DISTINCT cameras — survey one of each, never the same twice: conveyor_1 (left band), conveyor_2 (RIGHT band), table_1 (wide overhead incl. both totes), rack_1 (shelf); tote/tote_r are crops of the left/right band cameras. Counts come from the symbolic state, never from counting a frame (up to TWO identical blocks per color). Shapes: red=cube, blue=cylinder, green=brick. Returns vision + arm/block positions (red cube, blue cylinder, green brick);
    symbolic ground truth wins conflicts — discrepancies are flagged, never applied."""
    return _post("/v1/perceive", {"target": target})


@mcp.tool(annotations=ToolAnnotations(
    title="Floor: operator scene reset",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
))
def reset_scene() -> str:
    """Reset the current hardened Isaac scene and wait for its verified result.
    Call only after an explicit operator request. The floor refuses the reset
    while another task is active; no scene implementation is duplicated here."""
    global _LAST_CERTIFIED_PREFIX, _PENDING_PROOF
    with _STATE_LOCK:
        raw = _post(
            "/v1/dispatch",
            {
                "endpoint": "mobilebot",
                "action": "reset_scene",
                "scene_profile": "groot_three_object",
                "arm": "both",
                "color": "red",
                "layout_left": 3,
                "layout_right": 3,
                "seed": 31302,
            },
            role="operator",
        )
        outcome = _json_object(raw)
        if outcome.get("verified") is True:
            _PENDING_PROOF = None
            _DISPATCH_ATTEMPTS.clear()
            _LAST_CERTIFIED_PREFIX = None
        return raw


@mcp.tool(annotations=ToolAnnotations(title="Floor: dispatch ONE action (moves real robots)", readOnlyHint=False, destructiveHint=False, idempotentHint=False))
def dispatch_task(
    action: str,
    endpoint: str,
    color: str | None = None,
    source: str | None = None,
    destination: str | None = None,
    object_id: str | None = None,
    target_id: str | None = None,
    backend: str | None = None,
    wait: bool = True,
    args: dict | None = None,
) -> str:
    """Execute ONE floor action and wait for its physics-verified result.
    Actions: move(color, source, destination) on a franka arm — e.g.
    move color=blue source=conveyor_1 destination=tote_blue; and
    pick_and_place(object_id, target_id) on mobilebot — e.g.
    pick_and_place object_id=tote target_id=rack_1 (the ~2.5 min haul).
    The cell is a single FIFO queue: dispatch one action at a time and read
    `verified` before the next. For the certified dual-arm six-object mission
    use this exact pick-and-place order: right green, left green, right red,
    left red, right blue, left blue; visually verify every result before
    continuing."""
    global _LAST_CERTIFIED_PREFIX, _PENDING_PROOF
    with _STATE_LOCK:
        payload: dict = {"action": action, "endpoint": endpoint}
        if args:
            payload["args"] = args
        if color is not None:
            payload["color"] = color
        if source is not None:
            payload["source"] = source
        if action == "move" and color and destination in {"tote", "tote_r"}:
            destination = f"tote_{color}"
        if destination is not None:
            payload["destination"] = destination
        if object_id is not None:
            payload["object_id"] = object_id
        if target_id is not None:
            payload["target_id"] = target_id

        default_backend = os.environ.get("IC_DEFAULT_BACKEND") or None
        if action == "move" and default_backend:
            # The deployment-selected executor is authoritative.  A model may
            # not silently downgrade a GR00T cell to the scripted controller.
            backend = default_backend
        if backend is not None:
            payload["backend"] = backend
        if wait is False:
            payload["wait"] = False

        proof_gated = _proof_gate_enabled()
        certified_mixed = _certified_mixed_mode()
        certified = _certified_order_enabled() and not certified_mixed
        prefix = 0
        if proof_gated:
            if wait is False:
                return _refused("proof-gated GR00T actions must use wait=true")
            if _PENDING_PROOF is not None:
                return _refused(
                    "fresh visual proof must clear before another physical dispatch",
                    pending_visual_proof=_PENDING_PROOF,
                    proof_gate={
                        "state": _PENDING_PROOF.get("state", "awaiting_vlm")
                    },
                )
        if certified_mixed and action in {"move", "pick_and_place"}:
            state = _json_object(_post("/v1/floor-state", {}))
            pair_prefix, conflict = _completed_certified_pair_prefix(state)
            if conflict:
                return _refused(conflict, certified_pair_prefix=pair_prefix)
            move_prefix = pair_prefix * 2
            if (
                move_prefix == 0
                and _LAST_CERTIFIED_PREFIX is not None
                and _LAST_CERTIFIED_PREFIX > 0
            ):
                _DISPATCH_ATTEMPTS.clear()
            _LAST_CERTIFIED_PREFIX = move_prefix
            if action == "move":
                return _refused(
                    "the active certified mixed mission requires one atomic "
                    "dispatch_parallel transaction; do not expand it into "
                    "serial dispatch_task calls",
                    certified_pair_prefix=pair_prefix,
                )
            if pair_prefix < len(CERTIFIED_GROOT_MIXED_PAIRS):
                return _refused(
                    "both totes may be hauled only after all three certified "
                    "mixed pairs",
                    certified_pair_prefix=pair_prefix,
                )
        elif certified:
            state = _json_object(_post("/v1/floor-state", {}))
            prefix, conflict = _completed_certified_prefix(state)
            if conflict:
                return _refused(conflict, certified_prefix=prefix)
            if (
                prefix == 0
                and _LAST_CERTIFIED_PREFIX is not None
                and _LAST_CERTIFIED_PREFIX > 0
            ):
                _DISPATCH_ATTEMPTS.clear()
            _LAST_CERTIFIED_PREFIX = prefix
            if action == "move":
                if prefix >= len(CERTIFIED_GROOT_SERIAL_ORDER):
                    return _refused("all six certified arm moves are already complete")
                expected = CERTIFIED_GROOT_SERIAL_ORDER[prefix]
                requested = (endpoint, color, source, destination)
                if requested != expected:
                    return _refused(
                        "requested move is not the next certified GR00T step",
                        expected={
                            "sequence": prefix + 1,
                            "endpoint": expected[0],
                            "color": expected[1],
                            "source": expected[2],
                            "destination": expected[3],
                        },
                        requested={
                            "endpoint": endpoint,
                            "color": color,
                            "source": source,
                            "destination": destination,
                        },
                    )
            elif action == "pick_and_place" and prefix < len(CERTIFIED_GROOT_SERIAL_ORDER):
                return _refused(
                    "both totes may be hauled only after all six certified arm moves",
                    certified_prefix=prefix,
                )

        attempt_key = (
            action, endpoint, color, source, destination, object_id, target_id
        )
        if proof_gated and _DISPATCH_ATTEMPTS.get(attempt_key, 0) >= 2:
            return _refused("certified action retry limit exhausted", attempts=2)
        raw = _post("/v1/dispatch", payload)
        if not proof_gated or action not in {"move", "pick_and_place"}:
            return raw

        _DISPATCH_ATTEMPTS[attempt_key] = _DISPATCH_ATTEMPTS.get(attempt_key, 0) + 1
        outcome = _json_object(raw)
        verified = outcome.get("verified") is True
        if action == "move":
            destination_region = "tote_r" if endpoint == "franka_right" else "tote"
            allowed_regions = [destination_region]
            if not verified and source:
                allowed_regions.append(source)
            pending = {
                "state": "awaiting_vlm" if verified else "awaiting_reconciliation",
                "action": action,
                "endpoint": endpoint,
                "color": color,
                "shape": _SHAPES.get(str(color), "object"),
                "source": source,
                "destination": destination,
                "destination_region": destination_region,
                "allowed_regions": allowed_regions,
                "dispatch_verified": verified,
                "attempt": _DISPATCH_ATTEMPTS[attempt_key],
            }
            if certified:
                pending["sequence"] = prefix + 1
        else:
            pending = {
                "state": "awaiting_vlm" if verified else "awaiting_reconciliation",
                "action": action,
                "endpoint": endpoint,
                "object_id": object_id,
                "target_id": target_id,
                "destination_region": "rack_1",
                "allowed_regions": ["rack_1"],
                "dispatch_verified": verified,
                "attempt": _DISPATCH_ATTEMPTS[attempt_key],
            }
        _PENDING_PROOF = pending
        if verified and action == "move" and certified:
            _LAST_CERTIFIED_PREFIX = max(
                _LAST_CERTIFIED_PREFIX or 0, int(pending["sequence"])
            )
        outcome["pending_visual_proof"] = pending
        outcome["proof_gate"] = {"state": pending["state"]}
        return _result(outcome)


@mcp.tool(annotations=ToolAnnotations(
    title="Floor: dispatch both Franka arms concurrently",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
))
def dispatch_parallel(left_color: str, right_color: str | None = None) -> str:
    """Move one object per arm as one atomic GR00T transaction.

    The certified reference uses three exact mixed-color pairs reported by
    ``certified_groot_sequence``. Mixed motion is available only when the
    deployment has explicitly enabled both parallel and flexible-order modes
    after readiness qualification. Two independent B=1 policy servers load the
    same shared checkpoint, one per arm. Call verify once on ``tote`` for the
    left identity and once on ``tote_r`` for the right identity before another
    physical transaction.
    """
    global _LAST_CERTIFIED_PREFIX, _PENDING_PROOF
    with _STATE_LOCK:
        if not _parallel_groot_enabled():
            return _refused(
                "concurrent GR00T is disabled; set IC_GROOT_PARALLEL_ENABLED=1 "
                "only after the two-server B=1 cell contract passes readiness checks"
            )
        if not _certified_order_enabled():
            return _refused(
                "concurrent GR00T requires IC_CERTIFIED_GROOT_ORDER=1 so the "
                "qualified mixed sequence is state-enforced"
            )
        left_color = str(left_color or "").strip().lower()
        right_color = str(right_color or left_color).strip().lower()
        if left_color not in _SHAPES or right_color not in _SHAPES:
            return _refused("left_color and right_color must be red, blue, or green")
        if not _flexible_groot_order_enabled():
            return _refused(
                "certified mixed-color parallel GR00T requires "
                "IC_GROOT_FLEXIBLE_ORDER=1 after readiness qualification"
            )
        if left_color == right_color:
            return _refused(
                "the certified concurrent route requires one mixed-color "
                "Order744 pair; same-color pairs are not qualified"
            )
        if _PENDING_PROOF is not None:
            return _refused(
                "fresh visual proof must clear before another physical dispatch",
                pending_visual_proof=_PENDING_PROOF,
                proof_gate={"state": _PENDING_PROOF.get("state", "awaiting_vlm")},
            )

        certified_mixed = _certified_mixed_mode()

        move_prefix = 0
        pair_prefix = 0
        if certified_mixed:
            state = _json_object(_post("/v1/floor-state", {}))
            pair_prefix, conflict = _completed_certified_pair_prefix(state)
            if conflict:
                return _refused(conflict, certified_pair_prefix=pair_prefix)
            move_prefix = pair_prefix * 2
            if (
                move_prefix == 0
                and _LAST_CERTIFIED_PREFIX is not None
                and _LAST_CERTIFIED_PREFIX > 0
            ):
                _DISPATCH_ATTEMPTS.clear()
            _LAST_CERTIFIED_PREFIX = move_prefix
            if pair_prefix >= len(CERTIFIED_GROOT_MIXED_PAIRS):
                return _refused("all six certified arm moves are already complete")
            expected_pair = CERTIFIED_GROOT_MIXED_PAIRS[pair_prefix]
            expected_colors = {
                endpoint: color
                for endpoint, color, _source, _destination in expected_pair
            }
            if (
                left_color != expected_colors["franka_left"]
                or right_color != expected_colors["franka_right"]
            ):
                return _refused(
                    "requested colors are not the next certified mixed pair",
                    expected_colors=expected_colors,
                    requested_colors={
                        "franka_left": left_color,
                        "franka_right": right_color,
                    },
                    certified_pair_prefix=pair_prefix,
                )

        attempt_key = ("move_pair", left_color, right_color)
        if _DISPATCH_ATTEMPTS.get(attempt_key, 0) >= 2:
            return _refused(
                "certified concurrent action retry limit exhausted",
                attempts=2,
            )
        moves = [
            {
                "endpoint": "franka_left",
                "color": left_color,
                "source": "conveyor_1",
                "destination": f"tote_{left_color}",
                "backend": "groot",
            },
            {
                "endpoint": "franka_right",
                "color": right_color,
                "source": "conveyor_2",
                "destination": f"tote_{right_color}",
                "backend": "groot",
            },
        ]
        raw = _post("/v1/dispatch-parallel", {"moves": moves})
        outcome = _json_object(raw)
        pre_dispatch_error = _pre_dispatch_error(outcome)
        if pre_dispatch_error is not None:
            return _refused(
                "floor service rejected dispatch_parallel before motion: "
                + pre_dispatch_error
            )
        _DISPATCH_ATTEMPTS[attempt_key] = _DISPATCH_ATTEMPTS.get(attempt_key, 0) + 1
        verified = (
            outcome.get("verified") is True
            and outcome.get("independent_b1_verified") is True
        )
        pending = {
            "state": "awaiting_vlm" if verified else "awaiting_reconciliation",
            "action": "move_pair",
            "endpoints": ["franka_left", "franka_right"],
            "colors": {
                "franka_left": left_color,
                "franka_right": right_color,
            },
            "children_by_region": {
                "tote": {
                    "endpoint": "franka_left",
                    "color": left_color,
                    "shape": _SHAPES[left_color],
                    "destination": f"tote_{left_color}",
                },
                "tote_r": {
                    "endpoint": "franka_right",
                    "color": right_color,
                    "shape": _SHAPES[right_color],
                    "destination": f"tote_{right_color}",
                },
            },
            "destination_regions": ["tote", "tote_r"],
            "remaining_regions": ["tote", "tote_r"],
            "allowed_regions": ["tote", "tote_r"],
            "dispatch_verified": verified,
            "independent_b1_verified": (
                outcome.get("independent_b1_verified") is True
            ),
            "per_arm_relay_ports": outcome.get("per_arm_relay_ports") or {},
            "attempt": _DISPATCH_ATTEMPTS[attempt_key],
        }
        if certified_mixed:
            pending["pair_sequence"] = pair_prefix + 1
            pending["sequence_start"] = move_prefix + 1
            pending["sequence_end"] = move_prefix + 2
        _PENDING_PROOF = pending
        if verified and certified_mixed:
            _LAST_CERTIFIED_PREFIX = max(
                _LAST_CERTIFIED_PREFIX or 0,
                int(pending["sequence_end"]),
            )
        outcome["pending_visual_proof"] = pending
        outcome["proof_gate"] = {
            "state": pending["state"],
            "remaining_regions": pending["remaining_regions"],
        }
        return _result(outcome)


@mcp.tool(annotations=ToolAnnotations(
    title="Floor: active certified GR00T execution plan", readOnlyHint=True
))
def certified_groot_sequence() -> str:
    """Return the active certified plan for the six-object GR00T mission.

    When concurrent GR00T is enabled, follow ``transactions`` exactly: each is
    one bounded ``dispatch_parallel`` call followed by separate left/right
    visual proofs. Otherwise follow the serial ``moves`` fallback exactly.
    """
    certified_mixed = _certified_mixed_mode()
    active_capabilities = {
        "certified_order_enabled": _certified_order_enabled(),
        "parallel_enabled": _parallel_groot_enabled(),
        "flexible_order_enabled": _flexible_groot_order_enabled(),
        "mixed_color_parallel_enabled": certified_mixed,
        "configuration_change_required_for_mixed_color": not certified_mixed,
    }
    if certified_mixed:
        return json.dumps({
            "contract": "fixed-layout3-dual-concurrent-mixed-physical-friction-v10",
            "execution_mode": "concurrent_mixed_pairs",
            "active_capabilities": active_capabilities,
            "scene": {"layout_left": 3, "layout_right": 3, "seed": 31302},
            "transactions": [
                {
                    "sequence": index,
                    "tool": "dispatch_parallel",
                    "args": {
                        "left_color": pair[0][1],
                        "right_color": pair[1][1],
                    },
                    "proofs": [
                        {
                            "region": "tote",
                            "predicate": (
                                f"the {pair[0][1]} {_SHAPES[pair[0][1]]} "
                                "is in the left tote"
                            ),
                        },
                        {
                            "region": "tote_r",
                            "predicate": (
                                f"the {pair[1][1]} {_SHAPES[pair[1][1]]} "
                                "is in the right tote"
                            ),
                        },
                    ],
                }
                for index, pair in enumerate(CERTIFIED_GROOT_MIXED_PAIRS, start=1)
            ],
            "rule": (
                "call dispatch_parallel once per transaction; require verified=true "
                "and clear both listed visual proofs before the next transaction; "
                "do not expand a transaction into serial dispatch_task calls"
            ),
        })
    return json.dumps({
        "contract": "fixed-layout3-dual-sequential-physical-friction-v8",
        "execution_mode": "serial_fallback",
        "active_capabilities": active_capabilities,
        "scene": {"layout_left": 3, "layout_right": 3, "seed": 31302},
        "moves": [
            {
                "sequence": index,
                "endpoint": endpoint,
                "color": color,
                "source": source,
                "destination": destination,
                "backend": "groot",
                "wait": True,
            }
            for index, (endpoint, color, source, destination)
            in enumerate(CERTIFIED_GROOT_SERIAL_ORDER, start=1)
        ],
        "rule": "dispatch one move, require verified=true and fresh visual proof, then continue",
    })


@mcp.tool(annotations=ToolAnnotations(title="Floor: visual verify (yes/no on camera)", readOnlyHint=True))
def verify(predicate: str, region: str | None = None) -> str:
    """Yes/no visual check of a predicate on a region camera, e.g.
    verify(predicate='the tote is on the rack', region='rack_1')."""
    global _LAST_CERTIFIED_PREFIX, _PENDING_PROOF
    with _STATE_LOCK:
        payload: dict = {"predicate": predicate}
        if region is not None:
            payload["region"] = region
        pending = _PENDING_PROOF if _proof_gate_enabled() else None
        if pending is not None:
            allowed = pending.get("allowed_regions") or []
            if region not in allowed:
                return _result({
                    "answer": "unknown",
                    "status": "refused",
                    "error": f"proof for this action must use one of regions {allowed!r}",
                    "pending_visual_proof": pending,
                    "proof_gate": {"state": pending.get("state")},
                })
            if not _pending_identity_matches(predicate, pending, region):
                if pending.get("action") == "move_pair":
                    child = (pending.get("children_by_region") or {}).get(region or "") or {}
                    identity = f"{child.get('color')} {child.get('shape')}"
                elif pending.get("action") == "move":
                    identity = f"{pending.get('color')} {pending.get('shape')}"
                else:
                    identity = pending.get("object_id")
                return _result({
                    "answer": "unknown",
                    "status": "refused",
                    "error": f"predicate must identify the exact pending object: {identity}",
                    "pending_visual_proof": pending,
                    "proof_gate": {"state": pending.get("state")},
                })

        outcome = _json_object(_post("/v1/verify", payload))
        if pending is None:
            return _result(outcome)
        if str(outcome.get("answer") or "").strip().lower() == "yes":
            if pending.get("action") == "move_pair":
                remaining = [
                    item
                    for item in pending.get("remaining_regions", [])
                    if item != region
                ]
                if remaining:
                    pending["remaining_regions"] = remaining
                    pending["allowed_regions"] = remaining
                    outcome["pending_visual_proof"] = pending
                    outcome["proof_gate"] = {
                        "state": pending.get("state"),
                        "remaining_regions": remaining,
                    }
                    return _result(outcome)
            cleared = pending
            _PENDING_PROOF = None
            if (
                cleared.get("action") == "move"
                and region == cleared.get("destination_region")
                and cleared.get("sequence") is not None
            ):
                _LAST_CERTIFIED_PREFIX = max(
                    _LAST_CERTIFIED_PREFIX or 0, int(cleared["sequence"])
                )
            elif (
                cleared.get("action") == "move_pair"
                and cleared.get("sequence_end") is not None
            ):
                _LAST_CERTIFIED_PREFIX = max(
                    _LAST_CERTIFIED_PREFIX or 0,
                    int(cleared["sequence_end"]),
                )
            outcome["proof_gate"] = {"state": "cleared", "cleared": cleared}
        else:
            outcome["pending_visual_proof"] = pending
            outcome["proof_gate"] = {"state": pending.get("state")}
        return _result(outcome)


@mcp.tool(annotations=ToolAnnotations(title="Floor: mission history (audit)", readOnlyHint=True))
def mission_history(limit: int = 10) -> str:
    """Recent missions from the audit store: id, time span, ops, dispatches,
    verified count, last result. Use mission_detail for a full timeline."""
    req = urllib.request.Request(f"{_seam()}/v1/missions?limit={int(limit)}",
                                 headers={"x-mission-id": _MISSION_ID})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode()
    except OSError as e:
        return json.dumps({"error": f"floor service unreachable: {e}"})


@mcp.tool(annotations=ToolAnnotations(title="Floor: mission detail (audit)", readOnlyHint=True))
def mission_detail(mission_id: str, limit: int = 100) -> str:
    """Full operation timeline of one mission: every perceive/dispatch/verify
    with outcome, duration, and evidence-frame reference."""
    req = urllib.request.Request(f"{_seam()}/v1/missions/{mission_id}?limit={int(limit)}",
                                 headers={"x-mission-id": _MISSION_ID})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode()
    except OSError as e:
        return json.dumps({"error": f"floor service unreachable: {e}"})


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
