# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""AnthropicVLMClient — real Claude vision query for Perception."""
from __future__ import annotations

import base64
import os

from anthropic import AsyncAnthropic

from industrial_claw.clients.vlm.base import VLMResponse


class AnthropicVLMClient:
    def __init__(self, model: str, max_tokens: int = 1024, client: AsyncAnthropic | None = None) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = client or AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    async def query(self, image_bytes: bytes, prompt: str) -> VLMResponse:
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        return VLMResponse(
            answer=text.strip(),
            evidence=text.strip(),
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
