# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Franka pick/place handler around the existing controller implementation."""

from __future__ import annotations

from typing import Any


class MoveAction:
    action_names = ("move",)

    def start(self, runtime: Any, command: dict[str, Any]) -> None:
        runtime.start(command)

    def step(self, runtime: Any, dt: float) -> None:
        endpoint = runtime.S["task"].get("endpoint") or "franka_left"
        runtime.hold_arms(runtime.frL if endpoint == "franka_right" else runtime.frR)
        runtime.run_move(dt)


ACTION_HANDLERS = (MoveAction(),)
