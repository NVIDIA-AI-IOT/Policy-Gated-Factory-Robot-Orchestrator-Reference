# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Scene config: the floor's tables, racks, and endpoints. Replaces the hard-coded
seed_default() so an Isaac scene or a real cell is just a different YAML file."""
from __future__ import annotations

import os
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from policy_gated_factory_robot_orchestrator_reference.types import Capability


class SceneEndpoint(BaseModel):
    id: str
    kind: str
    battery: float | None = None
    location: str = ""
    # Optional, declarative action surface. Existing scene files that omit this
    # retain the legacy kind-based arm/AMR defaults in Ros2FloorBackend.
    capabilities: list[Capability] = Field(default_factory=list)
    # Fault injection for testing/sim: the endpoint accepts a move but never lands it
    # (so dispatch's act-and-confirm reports verified:false). Not surfaced by floor_state.
    faulty: bool = False


class Scene(BaseModel):
    schema_version: Literal[1] = 1
    tables: dict[str, list[str]] = Field(default_factory=dict)
    racks: dict[str, int] = Field(default_factory=dict)
    endpoints: list[SceneEndpoint] = Field(default_factory=list)


def _default_scene_path() -> Traversable:
    bundled = files(__package__).joinpath("scene.example.yaml")
    if bundled.is_file():
        return bundled
    # Editable installs use the canonical config directly; wheels include the
    # same file as a package resource through Hatch's force-include mapping.
    return Path(__file__).resolve().parents[3] / "configs" / "scene.example.yaml"


def load_scene(path: Path | None) -> Scene:
    """Load a scene from ``path``, else $PGFR_FLOOR_SCENE, else the bundled default."""
    source: Traversable
    if path is None:
        env = os.environ.get("PGFR_FLOOR_SCENE")
        source = Path(env).expanduser() if env else _default_scene_path()
    else:
        source = Path(path)
    return Scene.model_validate(yaml.safe_load(source.read_text(encoding="utf-8")))
