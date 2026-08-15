# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""AnthropicLLMClient — real Claude completion for Brain."""
from __future__ import annotations

import os

from anthropic import AsyncAnthropic

from industrial_claw.clients.llm.base import LLMResponse


class AnthropicLLMClient:
    def __init__(self, model: str, max_tokens: int = 4096, client: AsyncAnthropic | None = None) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = client or AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    async def complete(self, system: str, user: str) -> LLMResponse:
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        return LLMResponse(
            text=text,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
