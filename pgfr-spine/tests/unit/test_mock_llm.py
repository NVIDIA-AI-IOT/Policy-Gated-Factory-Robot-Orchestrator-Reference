# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the LLMClient Protocol and MockLLMClient."""
from __future__ import annotations

from policy_gated_factory_robot_orchestrator_reference.clients.llm.base import LLMResponse
from policy_gated_factory_robot_orchestrator_reference.clients.llm.mock import MockLLMClient


async def test_mock_returns_canned_response() -> None:
    client = MockLLMClient(responses=[LLMResponse(text="hello")])
    r = await client.complete(system="sys", user="hi")
    assert r.text == "hello"


async def test_mock_cycles_through_responses() -> None:
    client = MockLLMClient(
        responses=[LLMResponse(text="first"), LLMResponse(text="second")]
    )
    a = await client.complete(system="s", user="u")
    b = await client.complete(system="s", user="u")
    c = await client.complete(system="s", user="u")
    assert a.text == "first"
    assert b.text == "second"
    assert c.text == "second"  # exhausted → repeat last


async def test_mock_records_calls() -> None:
    client = MockLLMClient(responses=[LLMResponse(text="x")])
    await client.complete(system="sys", user="user-message")
    assert len(client.calls) == 1
    assert client.calls[0].user == "user-message"
