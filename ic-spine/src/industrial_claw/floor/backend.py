# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The floor backend seam: select mock | ros2 by config; the agents run over it.

`FloorBackend` provides the world's endpoints + input sources (implementing the
existing ABCs). Everything above — the agents, the ops, the tools, IC's safety —
is backend-agnostic, so Isaac/Thor drop in as one new backend.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from industrial_claw.action_endpoints.base import ActionEndpoint
from industrial_claw.floor.scene import load_scene
from industrial_claw.input_sources.base import InputSource


@runtime_checkable
class FloorBackend(Protocol):
    def endpoints(self) -> list[ActionEndpoint]: ...
    def sources(self) -> list[InputSource]: ...


def load_backend(scene_path: Path | None = None) -> FloorBackend:
    """Return the floor backend named by $IC_FLOOR_BACKEND (default mock)."""
    kind = (os.environ.get("IC_FLOOR_BACKEND") or "mock").strip().lower()
    scene = load_scene(scene_path)
    if kind == "mock":
        from industrial_claw.floor.mock import MockFloorBackend

        return MockFloorBackend(scene)
    if kind == "ros2":
        from industrial_claw.floor.ros2 import Ros2FloorBackend

        return Ros2FloorBackend(scene)
    raise ValueError(f"unknown IC_FLOOR_BACKEND: {kind!r} (expected mock|ros2)")
