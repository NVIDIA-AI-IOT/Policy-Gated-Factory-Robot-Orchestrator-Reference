# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The Isaac action plugin contract is testable without importing Isaac Sim."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ISAAC_CELL = REPOSITORY_ROOT / "reference" / "policy-gated-factory-robot-orchestrator-reference" / "isaac-cell"
if str(ISAAC_CELL) not in sys.path:
    sys.path.insert(0, str(ISAAC_CELL))


class ActionHandler(Protocol):
    action_names: tuple[str, ...]

    def start(self, runtime: object, command: dict[str, object]) -> None: ...

    def step(self, runtime: object, dt: float) -> None: ...


class Registry(Protocol):
    @property
    def action_names(self) -> tuple[str, ...]: ...

    def register(self, handler: ActionHandler) -> None: ...

    def resolve(self, action_name: str | None) -> ActionHandler | None: ...


# The optional Isaac package lives outside the spine distribution. Describe its
# small, hardware-free interface at the dynamic import boundary.
discover_actions = cast(
    Callable[[], Registry], import_module("pgfr_cell.actions").discover_actions
)
ActionRegistry = cast(
    Callable[[], Registry], import_module("pgfr_cell.actions.base").ActionRegistry
)
ActionRegistrationError = cast(
    type[ValueError], import_module("pgfr_cell.actions.base").ActionRegistrationError
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
        action_names: tuple[str, ...] = ("move",)

        def start(self, runtime: object, command: dict[str, object]) -> None:
            pass

        def step(self, runtime: object, dt: float) -> None:
            pass

    registry = ActionRegistry()
    registry.register(Handler())

    with pytest.raises(ActionRegistrationError, match="provided by both"):
        registry.register(Handler())


@pytest.mark.parametrize("name", ["", "Move", "move-arm", "move arm"])
def test_registry_rejects_invalid_action_names(name: str) -> None:
    class Handler:
        action_names: tuple[str, ...] = (name,)

        def start(self, runtime: object, command: dict[str, object]) -> None:
            pass

        def step(self, runtime: object, dt: float) -> None:
            pass

    with pytest.raises(ActionRegistrationError, match="invalid action name"):
        ActionRegistry().register(Handler())


def test_move_handler_delegates_to_existing_runtime_motion() -> None:
    class Runtime:
        def __init__(self) -> None:
            self.S = {"task": {"endpoint": "franka_left"}}
            self.frL = object()
            self.frR = object()
            self.events: list[tuple[str, object]] = []

        def start(self, command: dict[str, object]) -> None:
            self.events.append(("start", command))

        def hold_arms(self, *arms: object) -> None:
            self.events.append(("hold", arms))

        def run_move(self, dt: float) -> None:
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
