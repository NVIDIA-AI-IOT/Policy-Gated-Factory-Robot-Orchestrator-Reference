# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The Isaac action plugin contract is testable without importing Isaac Sim."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ISAAC_CELL = REPOSITORY_ROOT / "reference" / "policy-gated-factory-robot-orchestrator-reference" / "isaac-cell"
if str(ISAAC_CELL) not in sys.path:
    sys.path.insert(0, str(ISAAC_CELL))

from pgfr_cell.actions import discover_actions  # noqa: E402
from pgfr_cell.actions.base import (  # noqa: E402
    ActionRegistrationError,
    ActionRegistry,
)


def test_builtin_actions_are_discovered_without_importing_isaac() -> None:
    registry = discover_actions()

    assert registry.action_names == (
        "haul",
        "inspect",
        "move",
        "pick_and_place",
        "reset",
        "spawn",
    )
    assert type(registry.resolve("move")).__module__ == "pgfr_cell.actions.move"
    assert type(registry.resolve("haul")).__module__ == "pgfr_cell.actions.haul"


def test_cell_command_schema_covers_packaged_and_deployment_actions() -> None:
    schema_path = REPOSITORY_ROOT / "schemas" / "cell-protocol" / "command.v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    actions = set(schema["properties"]["action"]["enum"])

    assert actions == {
        *discover_actions().action_names,
        "cancel",
        "move_pair",
        "reset_scene",
    }


def test_registry_rejects_duplicate_action_names() -> None:
    class Handler:
        action_names = ("move",)

        def start(self, runtime, command):
            pass

        def step(self, runtime, dt):
            pass

    registry = ActionRegistry()
    registry.register(Handler())

    with pytest.raises(ActionRegistrationError, match="provided by both"):
        registry.register(Handler())


@pytest.mark.parametrize("name", ["", "Move", "move-arm", "move arm"])
def test_registry_rejects_invalid_action_names(name: str) -> None:
    class Handler:
        action_names = (name,)

        def start(self, runtime, command):
            pass

        def step(self, runtime, dt):
            pass

    with pytest.raises(ActionRegistrationError, match="invalid action name"):
        ActionRegistry().register(Handler())


def test_move_handler_delegates_to_existing_runtime_motion() -> None:
    class Runtime:
        def __init__(self):
            self.S = {"task": {"endpoint": "franka_left"}}
            self.frL = object()
            self.frR = object()
            self.events = []

        def start(self, command):
            self.events.append(("start", command))

        def hold_arms(self, *arms):
            self.events.append(("hold", arms))

        def run_move(self, dt):
            self.events.append(("move", dt))

    runtime = Runtime()
    handler = discover_actions().resolve("move")
    assert handler is not None

    handler.start(runtime, {"action": "move"})
    handler.step(runtime, 1 / 60)

    assert runtime.events == [
        ("start", {"action": "move"}),
        ("hold", (runtime.frR,)),
        ("move", 1 / 60),
    ]
