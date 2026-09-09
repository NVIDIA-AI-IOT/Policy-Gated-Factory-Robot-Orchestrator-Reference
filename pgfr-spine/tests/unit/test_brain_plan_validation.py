# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for BrainAgent.plan() — the LLM-driven planning step."""
from __future__ import annotations

import json

import pytest

from policy_gated_factory_robot_orchestrator_reference.action_endpoints.mock import (
    MockActionEndpoint,
)
from policy_gated_factory_robot_orchestrator_reference.agents.action import ActionAgent
from policy_gated_factory_robot_orchestrator_reference.agents.brain import (
    BrainAgent,
    InvalidPlanError,
)
from policy_gated_factory_robot_orchestrator_reference.agents.perception import PerceptionAgent
from policy_gated_factory_robot_orchestrator_reference.clients.llm.base import LLMResponse
from policy_gated_factory_robot_orchestrator_reference.clients.llm.mock import MockLLMClient
from policy_gated_factory_robot_orchestrator_reference.clients.vlm.mock import MockVLMClient
from policy_gated_factory_robot_orchestrator_reference.input_sources.mock import MockInputSource
from policy_gated_factory_robot_orchestrator_reference.types import Capability, Pose, SubtaskKind


def _build_brain(llm_text: str) -> BrainAgent:
    perception = PerceptionAgent(
        sources=[MockInputSource(id="cam_1", modality="image", coverage_region="table_1")],
        vlm=MockVLMClient(responses=[]),
    )
    cap = Capability(
        name="navigate_to",
        description="Move base to a named location.",
        goal_schema={"type": "object", "required": ["location_id"]},
        result_schema={"type": "object"},
    )
    action = ActionAgent(
        endpoints=[
            MockActionEndpoint(
                id="ep1", type="mobile_manipulator", capabilities=[cap], pose=Pose(x=0, y=0)
            )
        ]
    )
    llm = MockLLMClient(responses=[LLMResponse(text=llm_text)])
    return BrainAgent(llm=llm, perception=perception, action=action)


async def test_plan_parses_valid_subtasks() -> None:
    raw = json.dumps(
        {
            "plan": [
                {
                    "kind": "action",
                    "endpoint_id": "ep1",
                    "capability": "navigate_to",
                    "args": {"location_id": "table_1"},
                    "verify": "robot at table_1?",
                    "max_attempts": 2,
                }
            ]
        }
    )
    brain = _build_brain(raw)
    plan = await brain.plan("go to table 1")
    assert len(plan) == 1
    assert plan[0].kind is SubtaskKind.ACTION
    assert plan[0].endpoint_id == "ep1"


async def test_plan_rejects_unknown_endpoint() -> None:
    raw = json.dumps(
        {
            "plan": [
                {
                    "kind": "action",
                    "endpoint_id": "ghost",
                    "capability": "navigate_to",
                    "args": {"location_id": "table_1"},
                }
            ]
        }
    )
    brain = _build_brain(raw)
    with pytest.raises(InvalidPlanError):
        await brain.plan("go")


async def test_plan_rejects_unknown_capability() -> None:
    raw = json.dumps(
        {
            "plan": [
                {
                    "kind": "action",
                    "endpoint_id": "ep1",
                    "capability": "fly",
                    "args": {},
                }
            ]
        }
    )
    brain = _build_brain(raw)
    with pytest.raises(InvalidPlanError):
        await brain.plan("go")


async def test_plan_rejects_non_json() -> None:
    brain = _build_brain("here is the plan: do stuff")
    with pytest.raises(InvalidPlanError):
        await brain.plan("go")


async def test_plan_extracts_fenced_json() -> None:
    raw = (
        "Sure! Here is the plan:\n"
        "```json\n"
        '{"plan": [{"kind": "perception", "query": "describe_scene", "args": {"region_id": "table_1"}}]}\n'
        "```\n"
        "Hope that helps."
    )
    brain = _build_brain(raw)
    plan = await brain.plan("look at table 1")
    assert plan[0].kind is SubtaskKind.PERCEPTION


async def test_plan_retries_on_invalid_then_succeeds() -> None:
    """First LLM response is malformed; the second is valid.

    plan() must call the LLM twice — the second time with the validation error
    in the user prompt — and return the valid plan.
    """
    bad = "not json at all"
    good = json.dumps(
        {
            "plan": [
                {
                    "kind": "action",
                    "endpoint_id": "ep1",
                    "capability": "navigate_to",
                    "args": {"location_id": "table_1"},
                }
            ]
        }
    )
    perception = PerceptionAgent(
        sources=[MockInputSource(id="cam_1", modality="image", coverage_region="table_1")],
        vlm=MockVLMClient(responses=[]),
    )
    cap = Capability(
        name="navigate_to",
        description="Move base to a named location.",
        goal_schema={"type": "object", "required": ["location_id"]},
        result_schema={"type": "object"},
    )
    action = ActionAgent(
        endpoints=[
            MockActionEndpoint(
                id="ep1", type="mobile_manipulator", capabilities=[cap], pose=Pose(x=0, y=0)
            )
        ]
    )
    llm = MockLLMClient(responses=[LLMResponse(text=bad), LLMResponse(text=good)])
    brain = BrainAgent(llm=llm, perception=perception, action=action)
    plan = await brain.plan("go to table 1")
    assert len(plan) == 1
    assert len(llm.calls) == 2  # two LLM calls: first bad, second good
    assert "failed" in llm.calls[1].user.lower()
