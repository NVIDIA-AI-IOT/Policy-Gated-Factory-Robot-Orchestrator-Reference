# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the config-selected floor backend seam."""
from __future__ import annotations

import importlib.util

import pytest


def test_load_backend_mock_builds_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IC_FLOOR_BACKEND", "mock")
    from industrial_claw.floor.backend import load_backend

    backend = load_backend()
    assert {e.id for e in backend.endpoints()} == {"amr_franka_1", "amr_franka_2", "conveyor_1"}
    assert isinstance(backend.sources(), list)


def test_load_backend_ros2_constructs_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    # The ros2 backend imports rclpy lazily, so it constructs on a host without ROS;
    # touching the cell (endpoints/sources/observe) is what needs rclpy.
    monkeypatch.setenv("IC_FLOOR_BACKEND", "ros2")
    from industrial_claw.floor.backend import load_backend

    backend = load_backend()
    assert backend is not None
    if importlib.util.find_spec("rclpy") is None:
        with pytest.raises(ModuleNotFoundError):
            backend.endpoints()


def test_load_backend_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IC_FLOOR_BACKEND", "bogus")
    from industrial_claw.floor.backend import load_backend

    with pytest.raises(ValueError, match="IC_FLOOR_BACKEND"):
        load_backend()
