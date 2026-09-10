# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the config-driven floor scene loader."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_load_scene_reads_tables_and_endpoints(tmp_path: Path) -> None:
    from policy_gated_factory_robot_orchestrator_reference.floor.scene import load_scene

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


def test_default_scene_matches_the_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    from policy_gated_factory_robot_orchestrator_reference.floor.scene import load_scene

    monkeypatch.delenv("PGFR_FLOOR_SCENE", raising=False)
    scene = load_scene(None)  # bundled default
    assert scene.tables["table_1"].count("red") == 2
    assert scene.tables["table_1"].count("green") == 1
    assert {e.id for e in scene.endpoints} == {"amr_franka_1", "amr_franka_2", "conveyor_1"}


@pytest.mark.parametrize("explicit", [False, True])
def test_configured_scene_takes_precedence_over_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit: bool,
) -> None:
    from policy_gated_factory_robot_orchestrator_reference.floor.scene import load_scene

    configured = tmp_path / "configured.yaml"
    configured.write_text("tables: {configured_table: [blue]}\n")
    monkeypatch.setenv("PGFR_FLOOR_SCENE", str(configured))
    chosen = None
    if explicit:
        chosen = tmp_path / "explicit.yaml"
        chosen.write_text("tables: {explicit_table: [yellow]}\n")
    scene = load_scene(chosen)
    assert scene.tables == ({"explicit_table": ["yellow"]} if explicit else {"configured_table": ["blue"]})
