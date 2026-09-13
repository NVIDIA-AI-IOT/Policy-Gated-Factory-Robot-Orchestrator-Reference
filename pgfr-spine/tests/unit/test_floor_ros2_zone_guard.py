# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for duplicate-color routing in the two-arm zone guard."""

from __future__ import annotations

from typing import Any

from policy_gated_factory_robot_orchestrator_reference.action_endpoints.base import ActionResult
from policy_gated_factory_robot_orchestrator_reference.floor import ros2


class _Bridge:
    def __init__(self, cubes: list[dict[str, Any]], **state: object) -> None:
        self._cubes = cubes
        self._state = state
        self.commands: list[tuple[dict[str, Any], float]] = []

    def floor_state(self) -> dict[str, Any]:
        return {"cubes": self._cubes, **self._state}

    def send(self, command: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.commands.append((command, timeout))
        return {
            "success": True,
            "verified": True,
            "reason": "both arms verified",
            "args": {
                "independent_b1_verified": True,
                "per_arm_relay_ports": {
                    "franka_left": 5612,
                    "franka_right": 5613,
                },
                "parallel_results": {
                    "franka_left": {"verified": True},
                    "franka_right": {"verified": True},
                },
            },
        }


class _Endpoint:
    id = "franka_right"
    type = "arm"

    async def execute(self, capability: str, goal_args: dict[str, Any]) -> ActionResult:
        return ActionResult(
            success=True,
            result={"verified": True, "moved": goal_args},
            reason="ok",
        )


class _Backend:
    def __init__(self, cubes: list[dict[str, Any]], **state: object) -> None:
        self._live_bridge = _Bridge(cubes, **state)

    def _bridge(self) -> _Bridge:
        return self._live_bridge

    def endpoints(self) -> list[_Endpoint]:
        return [_Endpoint()]


async def test_right_arm_selects_nearest_duplicate_color() -> None:
    backend = _Backend(
        [
            {"i": 0, "color": "red", "x": 3.612, "where": "conveyor"},
            {"i": 1, "color": "red", "x": 4.931, "where": "conveyor"},
        ]
    )

    result = await ros2.live_dispatch(
        backend,
        "franka_right",
        "move",
        {
            "color": "red",
            "source": "conveyor_1",
            "destination": "tote_red",
            "backend": "groot",
        },
    )

    assert result["dispatched"] is True
    assert result["verified"] is True


async def test_right_arm_still_refuses_only_left_color_match() -> None:
    backend = _Backend(
        [{"i": 0, "color": "red", "x": 3.612, "where": "conveyor"}]
    )

    result = await ros2.live_dispatch(
        backend,
        "franka_right",
        "move",
        {
            "color": "red",
            "source": "conveyor_1",
            "destination": "tote_red",
            "backend": "groot",
        },
    )

    assert result["dispatched"] is False
    assert result["status"] == "refused"
    assert "franka_left's zone" in result["reason"]


async def test_move_refuses_when_no_matching_conveyor_object_remains() -> None:
    backend = _Backend(
        [{"i": 1, "color": "red", "x": 5.256, "where": "tote_r"}]
    )

    result = await ros2.live_dispatch(
        backend,
        "franka_right",
        "move",
        {"color": "red", "source": "conveyor_2", "destination": "tote_red"},
    )

    assert result["dispatched"] is False
    assert result["status"] == "refused"
    assert "no matching red object remains on the conveyor" in result["reason"]


async def test_move_refuses_when_destination_tote_is_already_shelved() -> None:
    backend = _Backend(
        [{"i": 1, "color": "red", "x": 4.931, "where": "conveyor"}],
        tote_r_on_rack=True,
    )

    result = await ros2.live_dispatch(
        backend,
        "franka_right",
        "move",
        {"color": "red", "source": "conveyor_2", "destination": "tote_red"},
    )

    assert result["dispatched"] is False
    assert result["status"] == "refused"
    assert "destination tote is already on rack_1" in result["reason"]


async def test_duplicate_tote_haul_is_refused() -> None:
    backend = _Backend([], tote_r_on_rack=True)

    result = await ros2.live_dispatch(
        backend,
        "mobilebot",
        "pick_and_place",
        {"object_id": "tote_r", "target_id": "rack_1"},
    )

    assert result["dispatched"] is False
    assert result["status"] == "refused"
    assert "tote_r is already on rack_1" in result["reason"]


async def test_parallel_dispatch_sends_one_atomic_batch2_command() -> None:
    backend = _Backend(
        [
            {"i": 4, "color": "green", "x": 3.61, "where": "conveyor"},
            {"i": 5, "color": "green", "x": 4.94, "where": "conveyor"},
        ]
    )
    moves = [
        {
            "endpoint": "franka_left",
            "color": "green",
            "source": "conveyor_1",
            "destination": "tote_green",
            "backend": "groot",
        },
        {
            "endpoint": "franka_right",
            "color": "green",
            "source": "conveyor_2",
            "destination": "tote_green",
            "backend": "groot",
        },
    ]

    result = await ros2.live_dispatch_parallel(backend, moves)

    assert result["dispatched"] is True
    assert result["verified"] is True
    assert result["independent_b1_verified"] is True
    assert result["per_arm_relay_ports"] == {
        "franka_left": 5612,
        "franka_right": 5613,
    }
    assert len(backend._live_bridge.commands) == 1
    command, timeout = backend._live_bridge.commands[0]
    assert timeout == 240.0
    assert command["action"] == "move_pair"
    assert command["endpoint"] == "franka_pair"
    assert [move["endpoint"] for move in command["moves"]] == [
        "franka_left",
        "franka_right",
    ]
    assert all(move["action"] == "move" for move in command["moves"])


async def test_parallel_dispatch_keeps_mixed_child_colors_and_zones() -> None:
    backend = _Backend(
        [
            {"i": 4, "color": "green", "x": 3.61, "where": "conveyor"},
            {"i": 3, "color": "red", "x": 4.94, "where": "conveyor"},
        ]
    )
    moves = [
        {
            "endpoint": "franka_left",
            "color": "green",
            "source": "conveyor_1",
            "destination": "tote_green",
            "backend": "groot",
        },
        {
            "endpoint": "franka_right",
            "color": "red",
            "source": "conveyor_2",
            "destination": "tote_red",
            "backend": "groot",
        },
    ]

    result = await ros2.live_dispatch_parallel(backend, moves)

    assert result["verified"] is True
    command, _timeout = backend._live_bridge.commands[0]
    assert [(move["endpoint"], move["color"]) for move in command["moves"]] == [
        ("franka_left", "green"),
        ("franka_right", "red"),
    ]
