# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the granular floor CLI subcommands the TS plugin shells out to.

Each is a thin, JSON-emitting bridge over policy_gated_factory_robot_orchestrator_reference.floor, sharing one
``--state`` file so perceive reflects what dispatch did in a prior invocation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from policy_gated_factory_robot_orchestrator_reference.cli import main


def _json_out(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(capsys.readouterr().out)
    return result


def test_floor_state_subcommand_emits_endpoints(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    state = tmp_path / "floor.json"
    code = main(["floor-state", "--state", str(state)])
    assert code == 0
    out = _json_out(capsys)
    assert {e["id"] for e in out["endpoints"]} == {"amr_franka_1", "amr_franka_2", "conveyor_1"}


def test_perceive_subcommand_emits_observation(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    state = tmp_path / "floor.json"
    code = main(["perceive", "table_1", "--state", str(state)])
    assert code == 0
    out = _json_out(capsys)
    assert out["counts"] == {"red": 2, "green": 1}
    assert out["sorted"] is False


def test_dispatch_subcommand_mutates_shared_state_file(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    state = tmp_path / "floor.json"
    # Seed the file via a first read.
    main(["perceive", "table_1", "--state", str(state)])
    capsys.readouterr()

    code = main(
        [
            "dispatch", "--endpoint", "amr_franka_1", "--action", "move",
            "--color", "red", "--from", "table_1", "--destination", "red_rack",
            "--state", str(state),
        ]
    )
    assert code == 0
    dispatched = _json_out(capsys)
    assert dispatched["dispatched"] is True
    assert dispatched["verified"] is True
    assert dispatched["moved"] == {"color": "red", "from": "table_1", "destination": "red_rack"}

    # A fresh invocation reading the same file must see the move.
    main(["perceive", "table_1", "--state", str(state)])
    after = _json_out(capsys)
    assert after["counts"]["red"] == 1
    assert after["racks"]["red_rack"] == 1


def test_dispatch_failure_returns_nonzero_exit(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    state = tmp_path / "floor.json"
    code = main(
        [
            "dispatch", "--endpoint", "nope", "--action", "move",
            "--color", "red", "--from", "table_1", "--destination", "red_rack",
            "--state", str(state),
        ]
    )
    assert code != 0
    out = _json_out(capsys)
    assert out["dispatched"] is False


def test_dispatch_against_scene_faulty_endpoint_is_unverified(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A scene whose only arm is faulty: it accepts the move but never lands the block.
    # The CLI must seed the floor FROM this scene (so the fault survives the per-session
    # reset) — then dispatch reports verified:false, the signal PGFR retries/escalates on.
    # Without scene-seeding the CLI would seed the default floor, bad_arm would be an
    # unknown endpoint, and "dispatched" would be False instead.
    scene = tmp_path / "faulty_scene.yaml"
    scene.write_text(
        "tables:\n"
        "  table_1: [red]\n"
        "racks:\n"
        "  red_rack: 0\n"
        "endpoints:\n"
        "  - id: bad_arm\n"
        "    kind: arm+base\n"
        "    faulty: true\n"
    )
    monkeypatch.setenv("PGFR_FLOOR_SCENE", str(scene))
    state = tmp_path / "floor.json"

    code = main(
        [
            "dispatch", "--endpoint", "bad_arm", "--action", "move",
            "--color", "red", "--from", "table_1", "--destination", "red_rack",
            "--state", str(state),
        ]
    )
    out = _json_out(capsys)
    assert out["dispatched"] is True
    assert out["verified"] is False
    # Accepted-but-unverified is a scripting failure (nonzero), distinct from success.
    assert code == 2
