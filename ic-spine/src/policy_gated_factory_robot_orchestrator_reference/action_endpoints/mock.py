# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""MockActionEndpoint — scripted outcomes for tests and offline dev."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from policy_gated_factory_robot_orchestrator_reference.action_endpoints.base import (
    ActionEndpoint,
    ActionResult,
)
from policy_gated_factory_robot_orchestrator_reference.types import Capability, EndpointState, Pose


@dataclass
class ScriptedOutcome:
    success: bool = True
    reason: str | None = None
    result_overrides: dict[str, Any] = field(default_factory=dict)


class MockActionEndpoint(ActionEndpoint):
    def __init__(
        self,
        id: str,
        type: str,
        capabilities: list[Capability],
        pose: Pose | None = None,
        scripted_outcomes: dict[str, list[ScriptedOutcome]] | None = None,
        initial_state: EndpointState | None = None,
    ) -> None:
        self.id = id
        self.type = type
        self.capabilities = capabilities
        self.pose = pose
        self._scripted = scripted_outcomes or {}
        self._cursors: dict[str, int] = {k: 0 for k in self._scripted}
        self._state = initial_state or EndpointState()

    async def execute(self, capability_name: str, goal_args: dict[str, Any]) -> ActionResult:
        if self.get_capability(capability_name) is None:
            return ActionResult(
                success=False,
                result={},
                reason=f"unknown capability: {capability_name}",
            )
        outcome = self._next_scripted(capability_name)
        result_payload: dict[str, Any] = {"success": outcome.success, **goal_args, **outcome.result_overrides}
        return ActionResult(success=outcome.success, result=result_payload, reason=outcome.reason)

    def state(self) -> EndpointState:
        return self._state

    def set_state(self, **changes: Any) -> None:
        """Test helper: mutate any field of the current state without rebuilding the mock."""
        self._state = self._state.model_copy(update=changes)

    def _next_scripted(self, capability_name: str) -> ScriptedOutcome:
        outcomes = self._scripted.get(capability_name)
        if not outcomes:
            return ScriptedOutcome(success=True)
        cursor = self._cursors.get(capability_name, 0)
        if cursor >= len(outcomes):
            return outcomes[-1]
        self._cursors[capability_name] = cursor + 1
        return outcomes[cursor]
