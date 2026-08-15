# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""InputSource — abstract base for any perception input (camera, audio, lidar, telemetry)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class InputSource(ABC):
    """A registered source of perceptual data."""

    id: str
    modality: str  # "image" | "audio" | "point_cloud" | "telemetry" | ...
    coverage_region: str | None  # logical region this source covers (e.g. "table_1")

    @abstractmethod
    async def snapshot(self) -> Any:
        """Return the latest reading. Subclass decides the payload shape."""

    @abstractmethod
    def query_kinds(self) -> list[str]:
        """Which Perception query kinds this source can serve."""

    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "modality": self.modality,
            "coverage_region": self.coverage_region,
            "query_kinds": self.query_kinds(),
        }
