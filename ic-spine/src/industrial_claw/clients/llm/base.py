# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLMClient — Protocol for any text-completion provider used by Brain."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(Protocol):
    async def complete(self, system: str, user: str) -> LLMResponse:
        ...
