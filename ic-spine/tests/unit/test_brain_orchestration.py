# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for BrainAgent.run_mission — the full orchestration loop."""
from __future__ import annotations

import json
from typing import Any

from industrial_claw.action_endpoints.mock import MockActionEndpoint, ScriptedOutcome
from industrial_claw.agents.action import ActionAgent
from industrial_claw.agents.brain import BrainAgent, BrainConfig
from industrial_claw.agents.perception import PerceptionAgent
from industrial_claw.clients.llm.base import LLMResponse
from industrial_claw.clients.llm.mock import MockLLMClient
from industrial_claw.clients.vlm.base import VLMResponse
from industrial_claw.clients.vlm.mock import MockVLMClient
from industrial_claw.input_sources.mock import MockInputSource, MockSnapshot
from industrial_claw.types import Capability, Pose


def _nav_cap() -> Capability:
    return Capability(
        name="navigate_to",
        description="Move base to a named location.",
        goal_schema={"type": "object", "required": ["location_id"]},
        result_schema={"type": "object"},
    )


def _pick_cap() -> Capability:
    return Capability(
        name="pick_and_place",
        description="Pick an object and place it.",
        goal_schema={"type": "object", "required": ["object_id", "target_id"]},
        result_schema={"type": "object"},
    )


def _plan_json(items: list[dict[str, Any]]) -> str:
    return json.dumps({"plan": items})


async def test_run_mission_happy_path() -> None:
    plan = _plan_json(
        [
            {
                "kind": "action",
                "endpoint_id": "ep1",
                "capability": "navigate_to",
                "args": {"location_id": "table_1_approach"},
                "verify": "robot at table_1?",
            },
            {
                "kind": "action",
                "endpoint_id": "ep1",
                "capability": "pick_and_place",
                "args": {"object_id": "g1", "target_id": "green_rack"},
                "verify": "is g1 in green_rack?",
            },
        ]
    )
    llm = MockLLMClient(responses=[LLMResponse(text=plan)])
    vlm = MockVLMClient(
        responses=[
            VLMResponse(answer="A green block on table_1."),  # initial describe
            VLMResponse(answer="yes", evidence="robot at table_1"),  # verify 1
            VLMResponse(answer="yes", evidence="g1 in green_rack"),  # verify 2
        ]
    )
    perception = PerceptionAgent(
        sources=[
            MockInputSource(
                id="cam_1", modality="image", coverage_region="table_1",
                snapshots=[MockSnapshot(image_bytes=b"f")] * 4,
            )
        ],
        vlm=vlm,
    )
    action = ActionAgent(
        endpoints=[
            MockActionEndpoint(
                id="ep1", type="mobile_manipulator",
                capabilities=[_nav_cap(), _pick_cap()], pose=Pose(x=0, y=0),
            )
        ]
    )
    brain = BrainAgent(llm=llm, perception=perception, action=action)
    result = await brain.run_mission("sort table 1")
    assert result.goal_met
    assert result.subtask_count == 2
    assert result.retries == 0
    assert not result.escalated


async def test_run_mission_retries_on_capability_failure() -> None:
    plan = _plan_json(
        [
            {
                "kind": "action",
                "endpoint_id": "ep1",
                "capability": "pick_and_place",
                "args": {"object_id": "g1", "target_id": "green_rack"},
                "verify": "is g1 in green_rack?",
                "max_attempts": 2,
            }
        ]
    )
    llm = MockLLMClient(responses=[LLMResponse(text=plan)])
    vlm = MockVLMClient(
        responses=[
            VLMResponse(answer="initial state"),
            VLMResponse(answer="yes", evidence="g1 in green_rack"),
        ]
    )
    perception = PerceptionAgent(
        sources=[
            MockInputSource(
                id="cam_1", modality="image", coverage_region="table_1",
                snapshots=[MockSnapshot(image_bytes=b"f")] * 3,
            )
        ],
        vlm=vlm,
    )
    action = ActionAgent(
        endpoints=[
            MockActionEndpoint(
                id="ep1", type="mobile_manipulator", capabilities=[_pick_cap()],
                pose=Pose(x=0, y=0),
                scripted_outcomes={
                    "pick_and_place": [
                        ScriptedOutcome(success=False, reason="grasp slipped"),
                        ScriptedOutcome(success=True),
                    ]
                },
            )
        ]
    )
    brain = BrainAgent(llm=llm, perception=perception, action=action)
    result = await brain.run_mission("place g1 in green_rack")
    assert result.goal_met
    assert result.retries == 1


async def test_run_mission_escalates_after_capability_exhaustion() -> None:
    plan = _plan_json(
        [
            {
                "kind": "action",
                "endpoint_id": "ep1",
                "capability": "pick_and_place",
                "args": {"object_id": "g1", "target_id": "green_rack"},
                "max_attempts": 2,
            }
        ]
    )
    # Brain will plan, fail, replan up to max_replans times, all fail → escalate.
    llm = MockLLMClient(responses=[LLMResponse(text=plan), LLMResponse(text=plan)])
    vlm = MockVLMClient(responses=[VLMResponse(answer="state")])
    perception = PerceptionAgent(
        sources=[
            MockInputSource(
                id="cam_1", modality="image", coverage_region="table_1",
                snapshots=[MockSnapshot(image_bytes=b"f")] * 5,
            )
        ],
        vlm=vlm,
    )
    action = ActionAgent(
        endpoints=[
            MockActionEndpoint(
                id="ep1", type="mobile_manipulator", capabilities=[_pick_cap()],
                pose=Pose(x=0, y=0),
                scripted_outcomes={
                    "pick_and_place": [
                        ScriptedOutcome(success=False, reason="grasp slipped"),
                    ]
                },
            )
        ]
    )
    brain = BrainAgent(llm=llm, perception=perception, action=action)
    result = await brain.run_mission("place g1 in green_rack")
    assert not result.goal_met
    assert result.escalated


async def test_run_mission_replans_on_verification_failure() -> None:
    plan = _plan_json(
        [
            {
                "kind": "action",
                "endpoint_id": "ep1",
                "capability": "pick_and_place",
                "args": {"object_id": "g1", "target_id": "green_rack"},
                "verify": "is g1 in green_rack?",
                "max_attempts": 1,
            }
        ]
    )
    replan = _plan_json(
        [
            {
                "kind": "action",
                "endpoint_id": "ep1",
                "capability": "pick_and_place",
                "args": {"object_id": "g1", "target_id": "green_rack"},
                "verify": "is g1 in green_rack?",
                "max_attempts": 1,
            }
        ]
    )
    llm = MockLLMClient(responses=[LLMResponse(text=plan), LLMResponse(text=replan)])
    vlm = MockVLMClient(
        responses=[
            VLMResponse(answer="initial"),     # describe
            VLMResponse(answer="no"),          # verify after first attempt (fails)
            VLMResponse(answer="yes"),         # verify after replan (succeeds)
        ]
    )
    perception = PerceptionAgent(
        sources=[
            MockInputSource(
                id="cam_1", modality="image", coverage_region="table_1",
                snapshots=[MockSnapshot(image_bytes=b"f")] * 5,
            )
        ],
        vlm=vlm,
    )
    action = ActionAgent(
        endpoints=[
            MockActionEndpoint(
                id="ep1", type="mobile_manipulator", capabilities=[_pick_cap()],
                pose=Pose(x=0, y=0),
            )
        ]
    )
    brain = BrainAgent(
        llm=llm, perception=perception, action=action,
        config=BrainConfig(max_replans=1),
    )
    result = await brain.run_mission("place g1 in green_rack")
    assert result.goal_met
    assert result.retries >= 1
