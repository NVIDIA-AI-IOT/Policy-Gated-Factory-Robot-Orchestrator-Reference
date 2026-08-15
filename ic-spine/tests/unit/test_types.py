# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for cross-cutting types and JSON-schema validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from industrial_claw.types import (
    Capability,
    EndpointState,
    MissionResult,
    Pose,
    Subtask,
    SubtaskKind,
)


def test_pose_round_trips() -> None:
    p = Pose(x=1.0, y=2.0, z=0.0, yaw=0.5)
    d = p.model_dump()
    assert d == {"x": 1.0, "y": 2.0, "z": 0.0, "yaw": 0.5, "frame_id": "map"}
    assert Pose.model_validate(d) == p


def test_capability_carries_schemas() -> None:
    cap = Capability(
        name="pick_and_place",
        description="Pick an object and place it at a target location.",
        goal_schema={"type": "object", "required": ["object_id", "target_id"]},
        result_schema={"type": "object", "required": ["success"]},
    )
    assert cap.name == "pick_and_place"


def test_subtask_action_valid() -> None:
    s = Subtask(
        kind=SubtaskKind.ACTION,
        endpoint_id="amr_franka_1",
        capability="pick_and_place",
        args={"object_id": "green_block_3", "target_id": "green_rack"},
        verify="is green_block_3 in green_rack?",
        max_attempts=2,
    )
    assert s.kind == SubtaskKind.ACTION


def test_subtask_action_missing_endpoint_id_fails() -> None:
    with pytest.raises(ValidationError):
        Subtask(
            kind=SubtaskKind.ACTION,
            capability="pick_and_place",
            args={"object_id": "x", "target_id": "y"},
        )


def test_subtask_perception_valid() -> None:
    s = Subtask(
        kind=SubtaskKind.PERCEPTION,
        query="describe_scene",
        args={"region_id": "table_1"},
    )
    assert s.kind == SubtaskKind.PERCEPTION


def test_subtask_perception_missing_query_fails() -> None:
    with pytest.raises(ValidationError):
        Subtask(kind=SubtaskKind.PERCEPTION, args={"region_id": "table_1"})


def test_mission_result_defaults() -> None:
    r = MissionResult(mission_id="m1", goal_met=True, subtask_count=3, retries=0, escalated=False)
    assert r.duration_seconds is None


def test_endpoint_state_defaults_are_free_and_full() -> None:
    s = EndpointState()
    assert s.busy is False
    assert s.battery_pct == 100.0
    assert s.last_action_result == ""


def test_endpoint_state_round_trips() -> None:
    s = EndpointState(busy=True, battery_pct=42.5, last_action_result="success")
    assert EndpointState.model_validate(s.model_dump()) == s


def test_pose_has_frame_id_default_map() -> None:
    assert Pose(x=1.0, y=2.0).frame_id == "map"


def test_endpoint_state_has_optional_fault() -> None:
    assert EndpointState(fault="estop").fault == "estop"
    assert EndpointState().fault is None
