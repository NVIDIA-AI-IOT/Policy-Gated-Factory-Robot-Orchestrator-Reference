# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Mobile manipulator tote-haul handler around the existing implementation."""

from __future__ import annotations

from typing import Any


class HaulAction:
    # pick_and_place is the public legacy name; haul is retained for direct calls.
    action_names = ("pick_and_place", "haul")

    def start(self, runtime: Any, command: dict[str, Any]) -> None:
        runtime.start(command)

    def step(self, runtime: Any, dt: float) -> None:
        runtime.hold_arms(runtime.frR)
        runtime.run_haul(dt)


ACTION_HANDLERS = (HaulAction(),)
