# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ActionAgent."""
from __future__ import annotations

from policy_gated_factory_robot_orchestrator_reference.action_endpoints.mock import (
    MockActionEndpoint,
)
from policy_gated_factory_robot_orchestrator_reference.agents.action import ActionAgent
from policy_gated_factory_robot_orchestrator_reference.types import Capability, Pose


def _cap(name: str = "navigate_to") -> Capability:
    return Capability(
        name=name,
        description="d",
        goal_schema={"type": "object"},
        result_schema={"type": "object"},
    )


def test_list_endpoints_returns_metadata() -> None:
    endpoints = [
        MockActionEndpoint(
            id="ep1", type="mobile_manipulator", capabilities=[_cap()], pose=Pose(x=0, y=0)
        ),
        MockActionEndpoint(
            id="ep2", type="conveyor", capabilities=[_cap("start")], pose=None
        ),
    ]
    a = ActionAgent(endpoints=endpoints)
    listed = a.list_action_endpoints()
    assert {e["id"] for e in listed} == {"ep1", "ep2"}


def test_list_endpoints_filters_by_type() -> None:
    endpoints = [
        MockActionEndpoint(id="ep1", type="mobile_manipulator", capabilities=[_cap()]),
        MockActionEndpoint(id="ep2", type="conveyor", capabilities=[_cap("start")]),
    ]
    a = ActionAgent(endpoints=endpoints)
    listed = a.list_action_endpoints(type_filter="conveyor")
    assert [e["id"] for e in listed] == ["ep2"]


def test_pick_nearest_uses_pose() -> None:
    endpoints = [
        MockActionEndpoint(
            id="far", type="mobile_manipulator", capabilities=[_cap()], pose=Pose(x=10, y=0)
        ),
        MockActionEndpoint(
            id="near", type="mobile_manipulator", capabilities=[_cap()], pose=Pose(x=1, y=0)
        ),
    ]
    a = ActionAgent(endpoints=endpoints)
    nearest = a.pick_nearest(type_filter="mobile_manipulator", target_pose=Pose(x=0, y=0))
    assert nearest == "near"


async def test_execute_calls_endpoint() -> None:
    endpoints = [
        MockActionEndpoint(id="ep1", type="mobile_manipulator", capabilities=[_cap()]),
    ]
    a = ActionAgent(endpoints=endpoints)
    r = await a.execute("ep1", "navigate_to", {"location_id": "table_1"})
    assert r["success"]


async def test_execute_unknown_endpoint() -> None:
    a = ActionAgent(endpoints=[])
    r = await a.execute("nope", "navigate_to", {})
    assert not r["success"]
    assert "unknown endpoint" in (r["reason"] or "")


def test_pick_best_picks_closer_free_endpoint() -> None:
    endpoints = [
        MockActionEndpoint(
            id="far", type="mobile_manipulator", capabilities=[_cap("pick_and_place")], pose=Pose(x=10, y=0)
        ),
        MockActionEndpoint(
            id="near", type="mobile_manipulator", capabilities=[_cap("pick_and_place")], pose=Pose(x=1, y=0)
        ),
    ]
    a = ActionAgent(endpoints=endpoints)
    best = a.pick_best(
        type_filter="mobile_manipulator",
        capability_needed="pick_and_place",
        target_pose=Pose(x=0, y=0),
    )
    assert best == "near"


def test_pick_best_skips_busy_endpoint() -> None:
    near = MockActionEndpoint(
        id="near", type="mobile_manipulator", capabilities=[_cap("pick_and_place")], pose=Pose(x=1, y=0)
    )
    far = MockActionEndpoint(
        id="far", type="mobile_manipulator", capabilities=[_cap("pick_and_place")], pose=Pose(x=10, y=0)
    )
    near.set_state(busy=True)
    a = ActionAgent(endpoints=[near, far])
    best = a.pick_best(
        type_filter="mobile_manipulator",
        capability_needed="pick_and_place",
        target_pose=Pose(x=0, y=0),
    )
    assert best == "far"


def test_pick_best_skips_low_battery_endpoint() -> None:
    near = MockActionEndpoint(
        id="near", type="mobile_manipulator", capabilities=[_cap("pick_and_place")], pose=Pose(x=1, y=0)
    )
    far = MockActionEndpoint(
        id="far", type="mobile_manipulator", capabilities=[_cap("pick_and_place")], pose=Pose(x=10, y=0)
    )
    near.set_state(battery_pct=15.0)  # below the 20% default threshold
    a = ActionAgent(endpoints=[near, far])
    best = a.pick_best(
        type_filter="mobile_manipulator",
        capability_needed="pick_and_place",
        target_pose=Pose(x=0, y=0),
    )
    assert best == "far"


def test_pick_best_returns_none_when_no_capability_match() -> None:
    endpoints = [
        MockActionEndpoint(
            id="conv", type="conveyor", capabilities=[_cap("start")], pose=Pose(x=0, y=0)
        ),
    ]
    a = ActionAgent(endpoints=endpoints)
    best = a.pick_best(
        type_filter="mobile_manipulator",
        capability_needed="pick_and_place",
        target_pose=Pose(x=0, y=0),
    )
    assert best is None
