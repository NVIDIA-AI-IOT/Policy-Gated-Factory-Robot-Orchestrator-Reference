# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ActionEndpoint abstract base and MockActionEndpoint."""
from __future__ import annotations

import pytest

from industrial_claw.action_endpoints.base import ActionEndpoint
from industrial_claw.action_endpoints.mock import MockActionEndpoint, ScriptedOutcome
from industrial_claw.types import Capability, Pose


def test_abstract_cannot_instantiate() -> None:
    with pytest.raises(TypeError):
        ActionEndpoint()  # type: ignore[abstract]


async def test_mock_executes_capability() -> None:
    cap = Capability(
        name="navigate_to",
        description="Move the AMR base to a named location.",
        goal_schema={"type": "object", "required": ["location_id"]},
        result_schema={"type": "object", "required": ["success"]},
    )
    ep = MockActionEndpoint(
        id="amr_franka_1",
        type="mobile_manipulator",
        capabilities=[cap],
        pose=Pose(x=0, y=0),
    )
    r = await ep.execute("navigate_to", {"location_id": "table_1_approach"})
    assert r.success
    assert r.result == {"success": True, "location_id": "table_1_approach"}


async def test_mock_unknown_capability_fails() -> None:
    ep = MockActionEndpoint(id="ep1", type="mobile_manipulator", capabilities=[])
    r = await ep.execute("nope", {})
    assert not r.success
    assert r.reason is not None
    assert "unknown capability" in r.reason


async def test_mock_scripted_outcomes_drive_failures() -> None:
    cap = Capability(
        name="pick_and_place",
        description="Pick and place.",
        goal_schema={"type": "object", "required": ["object_id", "target_id"]},
        result_schema={"type": "object", "required": ["success"]},
    )
    ep = MockActionEndpoint(
        id="ep1",
        type="mobile_manipulator",
        capabilities=[cap],
        scripted_outcomes={
            "pick_and_place": [
                ScriptedOutcome(success=False, reason="grasp slipped"),
                ScriptedOutcome(success=True),
            ]
        },
    )
    r1 = await ep.execute("pick_and_place", {"object_id": "g1", "target_id": "green_rack"})
    r2 = await ep.execute("pick_and_place", {"object_id": "g1", "target_id": "green_rack"})
    assert not r1.success
    assert r2.success


def test_metadata_lists_capabilities() -> None:
    cap = Capability(
        name="navigate_to",
        description="d",
        goal_schema={},
        result_schema={},
    )
    ep = MockActionEndpoint(id="ep1", type="mobile_manipulator", capabilities=[cap])
    meta = ep.metadata()
    assert meta["id"] == "ep1"
    assert meta["type"] == "mobile_manipulator"
    assert meta["capabilities"][0]["name"] == "navigate_to"
    # Live state is flattened into metadata so Brain's LLM can see busy/battery_pct
    assert meta["busy"] is False
    assert meta["battery_pct"] == 100.0
    assert meta["last_action_result"] == ""


def test_set_state_mutates_subsequent_metadata() -> None:
    ep = MockActionEndpoint(id="ep1", type="mobile_manipulator", capabilities=[])
    ep.set_state(busy=True, battery_pct=42.0, last_action_result="failed:grasp")
    s = ep.state()
    assert s.busy is True
    assert s.battery_pct == 42.0
    meta = ep.metadata()
    assert meta["busy"] is True
    assert meta["battery_pct"] == 42.0
    assert meta["last_action_result"] == "failed:grasp"
