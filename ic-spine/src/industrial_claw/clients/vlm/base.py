# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""VLMClient — Protocol for any vision-question provider used by Perception."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class VLMResponse:
    answer: str  # free-form; for predicate prompts the agent enforces "yes"/"no"/"unknown"
    evidence: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class VLMClient(Protocol):
    async def query(self, image_bytes: bytes, prompt: str) -> VLMResponse:
        ...
