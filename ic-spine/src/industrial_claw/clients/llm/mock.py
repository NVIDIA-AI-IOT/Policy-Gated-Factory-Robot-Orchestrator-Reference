# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""MockLLMClient — canned LLM responses for tests."""
from __future__ import annotations

from dataclasses import dataclass, field

from industrial_claw.clients.llm.base import LLMResponse


@dataclass
class RecordedCall:
    system: str
    user: str


@dataclass
class MockLLMClient:
    responses: list[LLMResponse]
    calls: list[RecordedCall] = field(default_factory=list)

    async def complete(self, system: str, user: str) -> LLMResponse:
        self.calls.append(RecordedCall(system=system, user=user))
        if not self.responses:
            return LLMResponse(text="")
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[idx]
