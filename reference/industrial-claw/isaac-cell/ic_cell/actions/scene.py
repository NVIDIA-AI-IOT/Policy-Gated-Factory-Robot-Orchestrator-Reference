# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Immediate scene-management actions supplied by the canonical cell."""

from __future__ import annotations

import traceback
from typing import Any


class InspectAction:
    action_names = ("inspect",)

    def start(self, runtime: Any, command: dict[str, Any]) -> None:
        runtime.S["task"] = command
        try:
            runtime.do_inspect(command)
        except Exception:
            runtime.finish(False, False, "inspect err\n" + traceback.format_exc())

    def step(self, runtime: Any, dt: float) -> None:
        raise RuntimeError("inspect must finish during start()")


class SpawnAction:
    action_names = ("spawn",)

    def start(self, runtime: Any, command: dict[str, Any]) -> None:
        try:
            runtime.spawn_scene(command.get("n"))
            runtime.S["task"] = command
            runtime.finish(True, True, "spawned %d" % len(runtime.ACTIVE))
        except Exception:
            runtime.S["task"] = command
            runtime.finish(False, False, "spawn err\n" + traceback.format_exc())

    def step(self, runtime: Any, dt: float) -> None:
        raise RuntimeError("spawn must finish during start()")


class ResetAction:
    action_names = ("reset",)

    def start(self, runtime: Any, command: dict[str, Any]) -> None:
        try:
            runtime.reset_scene()
            runtime.S["task"] = command
            runtime.finish(True, True, "scene reset")
        except Exception:
            runtime.S["task"] = command
            runtime.finish(False, False, "reset err\n" + traceback.format_exc())

    def step(self, runtime: Any, dt: float) -> None:
        raise RuntimeError("reset must finish during start()")


ACTION_HANDLERS = (InspectAction(), SpawnAction(), ResetAction())
