# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the frozen floor contracts (capabilities + observation shape)."""
from __future__ import annotations


def test_capabilities_include_the_core_set_with_schema() -> None:
    from industrial_claw.floor.contracts import CAPABILITIES

    assert set(CAPABILITIES) >= {"move", "navigate_to", "pick_and_place", "inspect"}
    move = CAPABILITIES["move"]
    assert move.goal_schema["required"] == ["color", "source", "destination"]


def test_observation_round_trips_the_perceive_shape() -> None:
    from industrial_claw.floor.contracts import Observation

    obs = Observation(
        target="table_1",
        blocks_on_table=[{"item": "block", "color": "red"}],
        counts={"red": 1},
        racks={"red_rack": 0},
        sorted=False,
    )
    dumped = obs.model_dump()
    assert dumped["target"] == "table_1"
    assert dumped["blocks_on_table"][0]["color"] == "red"


def test_tote_verification_uses_a_separate_high_resolution_camera() -> None:
    from industrial_claw.floor.ros2 import _CAMERA_FOR_REGION

    assert _CAMERA_FOR_REGION["conveyor_1"] == "inspect_cam"
    assert _CAMERA_FOR_REGION["tote"] == "inspect_vlm_cam"
