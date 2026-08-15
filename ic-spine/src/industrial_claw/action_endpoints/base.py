# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ActionEndpoint — abstract base for any controllable endpoint (robot, conveyor, alert, ...)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from industrial_claw.types import Capability, EndpointState, Pose


@dataclass
class ActionResult:
    success: bool
    result: dict[str, Any]
    reason: str | None = None


class ActionEndpoint(ABC):
    id: str
    type: str
    pose: Pose | None
    capabilities: list[Capability]

    @abstractmethod
    async def execute(self, capability_name: str, goal_args: dict[str, Any]) -> ActionResult:
        """Run a named capability with the given arguments."""

    @abstractmethod
    def state(self) -> EndpointState:
        """Live operational status (busy, battery, last result)."""

    def get_capability(self, name: str) -> Capability | None:
        for c in self.capabilities:
            if c.name == name:
                return c
        return None

    def metadata(self) -> dict[str, Any]:
        s = self.state()
        return {
            "id": self.id,
            "type": self.type,
            "pose": self.pose.model_dump() if self.pose else None,
            "busy": s.busy,
            "battery_pct": s.battery_pct,
            "last_action_result": s.last_action_result,
            "capabilities": [
                {
                    "name": c.name,
                    "description": c.description,
                    "goal_schema": c.goal_schema,
                    "result_schema": c.result_schema,
                }
                for c in self.capabilities
            ],
        }
