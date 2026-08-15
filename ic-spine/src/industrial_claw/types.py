# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cross-cutting types for plans, agents, and the recorder."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Pose(BaseModel):
    """6-DoF reduced to xyz + yaw for top-down navigation; enough for the MVP."""
    x: float
    y: float
    z: float = 0.0
    yaw: float = 0.0
    # tf frame the pose is expressed in (sim/hardware report a real frame).
    frame_id: str = "map"


class Capability(BaseModel):
    """A named action exposed by an ActionEndpoint, carrying schemas for goal and result."""
    name: str
    description: str
    goal_schema: dict[str, Any]
    result_schema: dict[str, Any]


class SubtaskKind(StrEnum):
    ACTION = "action"
    PERCEPTION = "perception"


class Subtask(BaseModel):
    """One step in Brain's plan. Either an action call or a perception query."""
    kind: SubtaskKind
    # Action fields
    endpoint_id: str | None = None
    capability: str | None = None
    # Perception fields
    query: str | None = None
    # Shared
    args: dict[str, Any] = Field(default_factory=dict)
    verify: str | None = None
    max_attempts: int = 2

    @model_validator(mode="after")
    def _check_kind_fields(self) -> Subtask:
        if self.kind is SubtaskKind.ACTION:
            if not self.endpoint_id or not self.capability:
                raise ValueError("action subtask requires endpoint_id and capability")
        elif self.kind is SubtaskKind.PERCEPTION:
            if not self.query:
                raise ValueError("perception subtask requires query")
        return self


class EndpointState(BaseModel):
    """Live operational status of an ActionEndpoint (refreshed from the state topic in prod)."""
    busy: bool = False
    battery_pct: float = 100.0
    last_action_result: str = ""
    # Fault/e-stop code reported by the endpoint, if any (None = healthy).
    fault: str | None = None


class MissionResult(BaseModel):
    """Returned by BrainAgent.run_mission. Also serialized by the recorder."""
    mission_id: str
    goal_met: bool
    subtask_count: int
    retries: int
    escalated: bool
    duration_seconds: float | None = None
    reason: str | None = None
