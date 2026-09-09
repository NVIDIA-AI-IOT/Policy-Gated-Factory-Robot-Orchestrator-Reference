# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""MockInputSource — replays canned snapshots for tests and offline dev."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from policy_gated_factory_robot_orchestrator_reference.input_sources.base import InputSource


@dataclass
class MockSnapshot:
    image_bytes: bytes = b""
    payload: dict[str, Any] = field(default_factory=dict)


class MockInputSource(InputSource):
    def __init__(
        self,
        id: str,
        modality: str = "image",
        coverage_region: str | None = None,
        snapshots: list[MockSnapshot] | None = None,
    ) -> None:
        self.id = id
        self.modality = modality
        self.coverage_region = coverage_region
        self._snapshots = snapshots or [MockSnapshot()]
        self._cursor = 0

    async def snapshot(self) -> MockSnapshot:
        if self._cursor >= len(self._snapshots):
            return self._snapshots[-1]
        s = self._snapshots[self._cursor]
        self._cursor += 1
        return s

    def query_kinds(self) -> list[str]:
        return ["predicate", "describe", "locate"]
