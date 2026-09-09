# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CosmosVLMClient — vision-question client over the OpenAI-compatible chat API.

Speaks `POST /v1/chat/completions` with an image part, which is what Cosmos Reason
exposes when served via NVIDIA NIM or vLLM — and what any OpenAI-compatible vision
endpoint exposes. That decoupling is deliberate: the perception integration is built
and tested against this contract (any stand-in endpoint works), then pointed at the
local Cosmos endpoint once it is served, with no code change — only `IC_VLM_*` env.

Stdlib-only HTTP (urllib) run off the event loop via ``asyncio.to_thread`` so it
satisfies the async ``VLMClient`` protocol without adding a dependency.
"""
from __future__ import annotations

import asyncio
import base64
import json
import urllib.request

from policy_gated_factory_robot_orchestrator_reference.clients.vlm.base import VLMResponse


class CosmosVLMClient:
    def __init__(
        self,
        url: str,
        model: str,
        api_key: str | None = None,
        max_tokens: int = 512,
        timeout: float = 60.0,
        temperature: float = 0.0,
    ) -> None:
        base = url.rstrip("/")
        self._url = base if base.endswith("/chat/completions") else base + "/v1/chat/completions"
        self._model = model
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._temperature = temperature

    async def query(self, image_bytes: bytes, prompt: str) -> VLMResponse:
        return await asyncio.to_thread(self._query_sync, image_bytes, prompt)

    def _query_sync(self, image_bytes: bytes, prompt: str) -> VLMResponse:
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        body = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            # Verification must be reproducible.  Provider defaults are often
            # sampling-enabled and made identical frames flip verdicts.
            "temperature": self._temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(
            self._url, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as r:
            data = json.loads(r.read())
        choice = (data.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content")) or ""
        usage = data.get("usage") or {}
        return VLMResponse(
            answer=text.strip(),
            evidence=text.strip(),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )
