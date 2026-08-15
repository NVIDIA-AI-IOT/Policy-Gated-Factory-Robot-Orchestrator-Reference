# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the VLMClient Protocol and MockVLMClient."""
from __future__ import annotations

from industrial_claw.clients.vlm.base import VLMResponse
from industrial_claw.clients.vlm.mock import MockVLMClient


async def test_mock_returns_canned_predicate() -> None:
    client = MockVLMClient(responses=[VLMResponse(answer="yes", evidence="green block visible in green rack")])
    r = await client.query(image_bytes=b"x", prompt="is green in green rack?")
    assert r.answer == "yes"
    assert "green" in r.evidence


async def test_mock_records_calls() -> None:
    client = MockVLMClient(responses=[VLMResponse(answer="no", evidence="not visible")])
    await client.query(image_bytes=b"frame", prompt="is x in y?")
    assert len(client.calls) == 1
    assert client.calls[0].prompt == "is x in y?"
