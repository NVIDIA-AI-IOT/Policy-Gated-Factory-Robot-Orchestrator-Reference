# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Scene-declared endpoint capabilities and legacy compatibility."""

from industrial_claw.action_endpoints.base import ActionEndpoint
from industrial_claw.floor.ros2 import Ros2FloorBackend
from industrial_claw.floor.scene import Scene, SceneEndpoint
from industrial_claw.types import Capability


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
    backend._b = object()  # type: ignore[assignment]
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
