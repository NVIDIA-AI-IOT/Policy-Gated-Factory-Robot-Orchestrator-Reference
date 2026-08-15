# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Frozen floor contracts: the capability vocabulary and the perceive observation.

Sim (Isaac) and hardware (Thor) implement against these — keep them stable.
Each capability maps to a ROS 2 action/service in docs/floor-ros2-contract.md.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from industrial_claw.types import Capability

_OBJ: dict[str, Any] = {"type": "object"}


def _cap(name: str, desc: str, required: list[str]) -> Capability:
    return Capability(
        name=name,
        description=desc,
        goal_schema={"type": "object", "required": required},
        result_schema=_OBJ,
    )


CAPABILITIES: dict[str, Capability] = {
    c.name: c
    for c in [
        _cap(
            "move",
            "Move a colored object from a source to a destination.",
            ["color", "source", "destination"],
        ),
        _cap("navigate_to", "Move the base to a named location.", ["location_id"]),
        _cap(
            "pick_and_place",
            "Pick an object and place it at a target.",
            ["object_id", "target_id"],
        ),
        _cap("inspect", "Inspect a target and report its state.", ["target_id"]),
    ]
}


class Observation(BaseModel):
    """What ``perceive`` returns — a stable shape across mock / sim / real backends."""

    target: str
    blocks_on_table: list[dict[str, Any]] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    racks: dict[str, int] = Field(default_factory=dict)
    sorted: bool = False
    note: str | None = None
    source_used: str | None = None
