# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Scene-declared endpoint capabilities and legacy compatibility."""

from typing import Any

import pytest

from policy_gated_factory_robot_orchestrator_reference.action_endpoints.base import ActionEndpoint
from policy_gated_factory_robot_orchestrator_reference.floor import ros2
from policy_gated_factory_robot_orchestrator_reference.floor.ros2 import Ros2FloorBackend
from policy_gated_factory_robot_orchestrator_reference.floor.scene import Scene, SceneEndpoint
from policy_gated_factory_robot_orchestrator_reference.types import Capability


def _cap(name: str) -> Capability:
    return Capability(
        name=name,
        description=f"Run {name}.",
        goal_schema={"type": "object"},
        result_schema={"type": "object"},
    )


def _endpoints(scene: Scene) -> list[ActionEndpoint]:
    backend = Ros2FloorBackend(scene)
    # Endpoint construction only stores the bridge; no ROS operation occurs.
    backend._b = object.__new__(ros2._Bridge)
    return backend.endpoints()


def test_scene_declared_capability_reaches_action_endpoint() -> None:
    scene = Scene(
        endpoints=[
            SceneEndpoint(
                id="welder_1",
                kind="welder",
                capabilities=[_cap("weld_seam")],
            )
        ]
    )

    endpoint = _endpoints(scene)[0]
    assert [cap.name for cap in endpoint.capabilities] == ["weld_seam"]


def test_legacy_scene_without_capabilities_keeps_kind_defaults() -> None:
    scene = Scene(
        endpoints=[
            SceneEndpoint(id="arm_1", kind="arm"),
            SceneEndpoint(id="amr_1", kind="arm+base"),
        ]
    )

    arm, amr = _endpoints(scene)
    assert [cap.name for cap in arm.capabilities] == ["move", "pick_and_place"]
    assert [cap.name for cap in amr.capabilities] == ["pick_and_place", "navigate_to"]


def test_health_probe_initializes_the_ros_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    class _HealthyBridge(ros2._Bridge):
        def __init__(self) -> None:
            pass

        def health(self) -> dict[str, Any]:
            return {"ros_ok": True, "floor_state_age_s": 0.1}

    bridge = _HealthyBridge()
    monkeypatch.setattr(ros2, "_Bridge", lambda: bridge)
    backend = Ros2FloorBackend(Scene(endpoints=[]))

    assert backend.health() == {"ros_ok": True, "floor_state_age_s": 0.1}
    assert backend._b is bridge
