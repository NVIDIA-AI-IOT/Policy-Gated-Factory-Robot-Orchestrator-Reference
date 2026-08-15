# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""MockVLMClient — canned VLM responses for tests."""
from __future__ import annotations

from dataclasses import dataclass, field

from industrial_claw.clients.vlm.base import VLMResponse


@dataclass
class RecordedVLMCall:
    image_bytes: bytes
    prompt: str


@dataclass
class MockVLMClient:
    responses: list[VLMResponse]
    calls: list[RecordedVLMCall] = field(default_factory=list)

    async def query(self, image_bytes: bytes, prompt: str) -> VLMResponse:
        self.calls.append(RecordedVLMCall(image_bytes=image_bytes, prompt=prompt))
        if not self.responses:
            return VLMResponse(answer="unknown")
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[idx]
