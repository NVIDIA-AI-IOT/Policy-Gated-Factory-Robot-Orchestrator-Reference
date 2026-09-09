# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ActionAgent — dispatches capability calls to ActionEndpoint instances."""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from policy_gated_factory_robot_orchestrator_reference.action_endpoints.base import ActionEndpoint
from policy_gated_factory_robot_orchestrator_reference.types import Pose


class ActionAgent:
    def __init__(self, endpoints: Sequence[ActionEndpoint]) -> None:
        self._endpoints = {e.id: e for e in endpoints}

    def list_action_endpoints(
        self,
        type_filter: str | None = None,
        capability_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        out = []
        for ep in self._endpoints.values():
            if type_filter and ep.type != type_filter:
                continue
            if capability_filter and ep.get_capability(capability_filter) is None:
                continue
            out.append(ep.metadata())
        return out

    def pick_nearest(self, type_filter: str | None, target_pose: Pose) -> str | None:
        candidates = [
            ep for ep in self._endpoints.values()
            if (type_filter is None or ep.type == type_filter) and ep.pose is not None
        ]
        if not candidates:
            return None

        def dist(ep: ActionEndpoint) -> float:
            assert ep.pose is not None
            return math.hypot(ep.pose.x - target_pose.x, ep.pose.y - target_pose.y)

        return min(candidates, key=dist).id

    def pick_best(
        self,
        type_filter: str,
        capability_needed: str,
        target_pose: Pose,
        min_battery_pct: float = 20.0,
        require_free: bool = True,
    ) -> str | None:
        """Return the id of the best endpoint, or None if none qualify.

        Policy: filter to endpoints of the right type that expose the named
        capability and have a pose; drop busy ones if ``require_free``; drop
        endpoints below ``min_battery_pct``; then return the candidate
        nearest to ``target_pose`` by Euclidean distance.
        """
        candidates: list[ActionEndpoint] = []
        for ep in self._endpoints.values():
            if ep.type != type_filter:
                continue
            if ep.get_capability(capability_needed) is None:
                continue
            if ep.pose is None:
                continue
            state = ep.state()
            if require_free and state.busy:
                continue
            if state.battery_pct < min_battery_pct:
                continue
            candidates.append(ep)

        if not candidates:
            return None

        def dist(ep: ActionEndpoint) -> float:
            assert ep.pose is not None
            return math.hypot(ep.pose.x - target_pose.x, ep.pose.y - target_pose.y)

        return min(candidates, key=dist).id

    async def execute(
        self, endpoint_id: str, capability: str, goal_args: dict[str, Any]
    ) -> dict[str, Any]:
        ep = self._endpoints.get(endpoint_id)
        if ep is None:
            return {"success": False, "result": {}, "reason": f"unknown endpoint: {endpoint_id}"}
        r = await ep.execute(capability, goal_args)
        return {"success": r.success, "result": r.result, "reason": r.reason}
