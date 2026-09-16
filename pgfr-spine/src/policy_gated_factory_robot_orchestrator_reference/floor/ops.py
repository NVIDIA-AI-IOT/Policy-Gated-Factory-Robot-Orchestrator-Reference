# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend-agnostic floor operations the CLI and HTTP service call.

These take a :class:`FloorState` (the mock seam today); ``dispatch`` runs through
the real :class:`ActionAgent` over a :class:`FloorActionEndpoint`, so the same
contract swaps onto a ROS 2 / Isaac backend by replacing the endpoint.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from policy_gated_factory_robot_orchestrator_reference.agents.action import ActionAgent
from policy_gated_factory_robot_orchestrator_reference.floor.mock import (
    FloorActionEndpoint,
    FloorState,
)


def floor_state(state: FloorState) -> dict[str, Any]:
    """List the floor's endpoints in the shape the Control UI / PGFR expects.

    `faulty` is an internal fault-injection — a real fault is discovered by acting
    (dispatch → verified:false), not advertised — so it is excluded here.
    """
    return {"endpoints": [e.model_dump(exclude={"faulty"}) for e in state.endpoints]}


def perceive(state: FloorState, target: str) -> dict[str, Any]:
    """Return a structured observation of ``target`` from the floor's ground truth.

    This is the sensor contract: a real camera + VLM backend produces the same
    structured observation later. For now it reads the mock floor directly.
    """
    blocks = state.tables.get(target)
    if blocks is None:
        return {
            "target": target,
            "note": "no floor data for this target",
            "blocks_on_table": [],
        }
    return {
        "target": target,
        "blocks_on_table": [b.model_dump() for b in blocks],
        "counts": dict(Counter(b.color for b in blocks)),
        "racks": dict(state.racks),
        "sorted": len(blocks) == 0,
    }


async def dispatch(
    state: FloorState,
    *,
    endpoint: str,
    action: str,
    color: str | None = None,
    source: str | None = None,
    destination: str | None = None,
) -> dict[str, Any]:
    """Send ONE action to ONE endpoint, then confirm the effect actually happened.

    Act-and-confirm: rather than trust the endpoint's self-report, re-observe the
    floor afterwards and only report ``verified`` when the destination rack
    actually changed. An endpoint can accept a command yet drop the block; the
    caller (PGFR) uses ``verified`` to decide whether to retry or escalate.
    """
    rack_before = state.racks.get(destination or "", 0)
    agent = ActionAgent(endpoints=[FloorActionEndpoint(state, e) for e in state.endpoints])
    r = await agent.execute(
        endpoint, action, {"color": color, "source": source, "destination": destination}
    )
    if not r["success"]:
        return {"dispatched": False, "endpoint": endpoint, "action": action, "reason": r["reason"]}

    observed = perceive(state, source or "")
    rack_after = observed.get("racks", {}).get(destination or "", rack_before)
    verified = rack_after > rack_before
    verification = (
        f"{destination} now holds {rack_after} (was {rack_before})"
        if verified
        else f"unconfirmed: {destination} still at {rack_after} after the move"
    )
    return {
        "dispatched": True,
        "endpoint": endpoint,
        "action": action,
        "moved": r["result"]["moved"],
        "verified": verified,
        "verification": verification,
        "result": "ok" if verified else "unverified",
    }
