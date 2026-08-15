# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the config-driven floor scene loader."""
from __future__ import annotations

from pathlib import Path


def test_load_scene_reads_tables_and_endpoints(tmp_path: Path) -> None:
    from industrial_claw.floor.scene import load_scene

    p = tmp_path / "scene.yaml"
    p.write_text(
        "tables:\n  table_1: [red, green, red]\n"
        "racks: {red_rack: 0, green_rack: 0}\n"
        "endpoints:\n  - {id: amr_franka_1, kind: arm+base, battery: 0.92, location: dock_1}\n"
    )
    scene = load_scene(p)
    assert scene.tables["table_1"] == ["red", "green", "red"]
    assert scene.endpoints[0].id == "amr_franka_1"
    assert scene.endpoints[0].battery == 0.92


def test_default_scene_matches_the_demo() -> None:
    from industrial_claw.floor.scene import load_scene

    scene = load_scene(None)  # bundled default
    assert scene.tables["table_1"].count("red") == 2
    assert scene.tables["table_1"].count("green") == 1
    assert {e.id for e in scene.endpoints} == {"amr_franka_1", "amr_franka_2", "conveyor_1"}
