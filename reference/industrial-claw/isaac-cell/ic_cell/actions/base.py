# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Small contract between the Isaac frame loop and one action implementation."""

from __future__ import annotations

import re
from typing import Any, Protocol


_ACTION_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class ActionRegistrationError(ValueError):
    """Raised at cell startup when an action plugin has an invalid contract."""


class ActionHandler(Protocol):
    """An action owns start/step behavior; the runtime owns transport/lifecycle."""

    action_names: tuple[str, ...]

    def start(self, runtime: Any, command: dict[str, Any]) -> None: ...

    def step(self, runtime: Any, dt: float) -> None: ...


class ActionRegistry:
    """Validated map from command action names to isolated handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}

    def register(self, handler: ActionHandler) -> None:
        names = getattr(handler, "action_names", None)
        if isinstance(names, str) or not isinstance(names, (tuple, list)) or not names:
            raise ActionRegistrationError(
                f"{type(handler).__name__}.action_names must be a non-empty tuple"
            )
        if not callable(getattr(handler, "start", None)):
            raise ActionRegistrationError(f"{type(handler).__name__} has no callable start()")
        if not callable(getattr(handler, "step", None)):
            raise ActionRegistrationError(f"{type(handler).__name__} has no callable step()")

        normalized = tuple(names)
        if len(set(normalized)) != len(normalized):
            raise ActionRegistrationError(
                f"{type(handler).__name__} declares a duplicate action name"
            )
        for name in normalized:
            if not isinstance(name, str) or not _ACTION_NAME.fullmatch(name):
                raise ActionRegistrationError(f"invalid action name: {name!r}")
            previous = self._handlers.get(name)
            if previous is not None:
                raise ActionRegistrationError(
                    f"action {name!r} is provided by both "
                    f"{type(previous).__name__} and {type(handler).__name__}"
                )
        for name in normalized:
            self._handlers[name] = handler

    def resolve(self, action_name: str | None) -> ActionHandler | None:
        return self._handlers.get(action_name or "")

    @property
    def action_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
