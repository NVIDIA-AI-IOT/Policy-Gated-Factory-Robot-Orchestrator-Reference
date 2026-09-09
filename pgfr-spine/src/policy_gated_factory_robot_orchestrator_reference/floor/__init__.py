# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Floor package: the mock world, backend-agnostic ops, and frozen contracts.

Re-exports the public API so existing imports (`from policy_gated_factory_robot_orchestrator_reference.floor import
FloorState, perceive, dispatch, floor_state, ...`) keep working after the split.
"""
from policy_gated_factory_robot_orchestrator_reference.floor.backend import (
    FloorBackend,
    load_backend,
)
from policy_gated_factory_robot_orchestrator_reference.floor.contracts import (
    CAPABILITIES,
    Observation,
)
from policy_gated_factory_robot_orchestrator_reference.floor.mock import (
    Block,
    Endpoint,
    FloorActionEndpoint,
    FloorState,
    MockFloorBackend,
)
from policy_gated_factory_robot_orchestrator_reference.floor.ops import (
    dispatch,
    floor_state,
    perceive,
)
from policy_gated_factory_robot_orchestrator_reference.floor.scene import (
    Scene,
    SceneEndpoint,
    load_scene,
)

__all__ = [
    "CAPABILITIES",
    "Observation",
    "Block",
    "Endpoint",
    "FloorActionEndpoint",
    "FloorBackend",
    "FloorState",
    "MockFloorBackend",
    "Scene",
    "SceneEndpoint",
    "dispatch",
    "floor_state",
    "load_backend",
    "load_scene",
    "perceive",
]
