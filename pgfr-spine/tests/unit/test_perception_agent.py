# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for PerceptionAgent."""
from __future__ import annotations

from policy_gated_factory_robot_orchestrator_reference.agents.perception import PerceptionAgent
from policy_gated_factory_robot_orchestrator_reference.clients.vlm.base import VLMResponse
from policy_gated_factory_robot_orchestrator_reference.clients.vlm.mock import MockVLMClient
from policy_gated_factory_robot_orchestrator_reference.input_sources.mock import (
    MockInputSource,
    MockSnapshot,
)


async def test_list_input_sources_returns_metadata() -> None:
    sources = [
        MockInputSource(id="cam_1", modality="image", coverage_region="table_1"),
        MockInputSource(id="cam_2", modality="image", coverage_region="table_1"),
    ]
    p = PerceptionAgent(sources=sources, vlm=MockVLMClient(responses=[]))
    listed = p.list_input_sources()
    assert len(listed) == 2
    assert listed[0]["id"] == "cam_1"


async def test_check_predicate_yes() -> None:
    sources = [
        MockInputSource(
            id="cam_1",
            modality="image",
            coverage_region="table_1",
            snapshots=[MockSnapshot(image_bytes=b"frame-1")],
        )
    ]
    vlm = MockVLMClient(responses=[VLMResponse(answer="yes", evidence="green block in green rack")])
    p = PerceptionAgent(sources=sources, vlm=vlm)
    r = await p.check_predicate("is green block in green rack?", target_region_id="table_1")
    assert r["answer"] == "yes"
    assert r["source_used"] == "cam_1"


async def test_check_predicate_prompt_names_shapes_and_both_totes() -> None:
    sources = [
        MockInputSource(
            id="cam_1",
            modality="image",
            coverage_region="table_1",
            snapshots=[MockSnapshot(image_bytes=b"frame-1")],
        )
    ]
    vlm = MockVLMClient(responses=[VLMResponse(answer="unknown")])
    p = PerceptionAgent(sources=sources, vlm=vlm)
    await p.check_predicate(
        "is the blue cylinder in the right tote?",
        target_region_id="table_1",
    )
    prompt = vlm.calls[0].prompt
    assert "RED CUBE" in prompt
    assert "BLUE CYLINDER" in prompt
    assert "GREEN RECTANGULAR BRICK" in prompt
    assert "left tote" in prompt
    assert "right tote" in prompt
    assert "Both totes can be on different levels" in prompt


async def test_check_predicate_picks_matching_region() -> None:
    sources = [
        MockInputSource(id="cam_other", modality="image", coverage_region="loading_bay"),
        MockInputSource(id="cam_target", modality="image", coverage_region="table_1"),
    ]
    vlm = MockVLMClient(responses=[VLMResponse(answer="no", evidence="empty")])
    p = PerceptionAgent(sources=sources, vlm=vlm)
    r = await p.check_predicate("anything?", target_region_id="table_1")
    assert r["source_used"] == "cam_target"


async def test_check_predicate_no_source_returns_unknown() -> None:
    p = PerceptionAgent(sources=[], vlm=MockVLMClient(responses=[]))
    r = await p.check_predicate("predicate", target_region_id="table_1")
    assert r["answer"] == "unknown"
    assert r["source_used"] == ""


def test_check_predicate_normalizes_cosmos_tagged_verdict_only() -> None:
    assert (
        PerceptionAgent._normalize_yes_no(
            "<think>I inspected the tote.</think><answer>yes</answer>"
        )
        == "yes"
    )
    assert (
        PerceptionAgent._normalize_yes_no(
            "<think>The object is not clear.</think><answer>unknown</answer>"
        )
        == "unknown"
    )
    assert (
        PerceptionAgent._normalize_yes_no(
            "<think>I considered yes and no but did not give a final tag.</think>"
        )
        == "unknown"
    )


async def test_describe_returns_text() -> None:
    sources = [
        MockInputSource(
            id="cam_1",
            modality="image",
            coverage_region="table_1",
            snapshots=[MockSnapshot(image_bytes=b"f")],
        )
    ]
    vlm = MockVLMClient(responses=[VLMResponse(answer="A green block and two red blocks on the table.")])
    p = PerceptionAgent(sources=sources, vlm=vlm)
    r = await p.describe(region_id="table_1")
    assert "green block" in r["description"]


def _table_cam(answer: str) -> PerceptionAgent:
    sources = [
        MockInputSource(
            id="table_cam",
            modality="image",
            coverage_region="table_1",
            snapshots=[MockSnapshot(image_bytes=b"frame")],
        )
    ]
    return PerceptionAgent(sources=sources, vlm=MockVLMClient(responses=[VLMResponse(answer=answer)]))


async def test_observe_visual_parses_clean_json() -> None:
    answer = (
        '{"cubes_visible": [{"color": "red", "where": "conveyor"}, '
        '{"color": "blue", "where": "tote"}], "tote_on_rack": false, '
        '"summary": "A red cube on the conveyor and a blue cube in the tote."}'
    )
    p = _table_cam(answer)
    r = await p.observe_visual(region_id="table_1")
    assert r["parse_ok"] is True
    assert r["source_used"] == "table_cam"
    assert r["cubes_visible"] == [
        {"color": "red", "where": "conveyor"},
        {"color": "blue", "where": "tote"},
    ]
    assert r["tote_on_rack"] is False


async def test_observe_visual_prompt_names_shapes_and_duplicate_sets() -> None:
    sources = [
        MockInputSource(
            id="table_cam",
            modality="image",
            coverage_region="table_1",
            snapshots=[MockSnapshot(image_bytes=b"frame")],
        )
    ]
    vlm = MockVLMClient(
        responses=[
            VLMResponse(
                answer='{"cubes_visible": [], "tote_on_rack": null, '
                '"summary": "empty"}'
            )
        ]
    )
    p = PerceptionAgent(sources=sources, vlm=vlm)
    await p.observe_visual(region_id="table_1")
    prompt = vlm.calls[0].prompt
    assert "RED CUBE" in prompt
    assert "BLUE CYLINDER" in prompt
    assert "GREEN RECTANGULAR BRICK" in prompt
    assert "one set at each arm" in prompt
    assert "two separate totes" in prompt


async def test_tote_predicate_prompt_is_scoped_to_visible_region() -> None:
    sources = [
        MockInputSource(
            id="inspect_vlm_cam",
            modality="image",
            coverage_region="tote",
            snapshots=[MockSnapshot(image_bytes=b"frame")],
        )
    ]
    vlm = MockVLMClient(responses=[VLMResponse(answer="no")])
    p = PerceptionAgent(sources=sources, vlm=vlm)
    await p.check_predicate("is the red cube in the tote?", target_region_id="tote")
    prompt = vlm.calls[0].prompt
    assert "only the LEFT tote's workcell location" in prompt
    assert "Do not infer where an absent tote went" in prompt
    assert "flat red, blue, and green compartment pads" in prompt
    assert "Both totes can be on different levels" not in prompt


async def test_tote_observation_prompt_forces_empty_visible_crop_semantics() -> None:
    sources = [
        MockInputSource(
            id="inspect_vlm_cam",
            modality="image",
            coverage_region="tote",
            snapshots=[MockSnapshot(image_bytes=b"frame")],
        )
    ]
    vlm = MockVLMClient(
        responses=[
            VLMResponse(
                answer='{"cubes_visible": [], "tote_on_rack": null, '
                '"summary": "no tote or object visible"}'
            )
        ]
    )
    p = PerceptionAgent(sources=sources, vlm=vlm)
    await p.observe_visual(region_id="tote")
    prompt = vlm.calls[0].prompt
    assert "only the LEFT tote's workcell location" in prompt
    assert "empty or irrelevant crop must produce an empty" in prompt
    assert "Every reported object must use where=tote" in prompt
    assert "Set tote_on_rack=null" in prompt


async def test_tote_observation_discards_out_of_view_model_claims() -> None:
    sources = [
        MockInputSource(
            id="inspect_vlm_cam",
            modality="image",
            coverage_region="tote",
            snapshots=[MockSnapshot(image_bytes=b"frame")],
        )
    ]
    vlm = MockVLMClient(
        responses=[
            VLMResponse(
                answer='{"cubes_visible": [{"color": "blue", '
                '"where": "conveyor"}], "tote_on_rack": true, '
                '"summary": "unsupported claims"}'
            )
        ]
    )
    result = await PerceptionAgent(sources=sources, vlm=vlm).observe_visual(
        region_id="tote"
    )
    assert result["parse_ok"] is True
    assert result["cubes_visible"] == []
    assert result["tote_on_rack"] is None


async def test_observe_visual_extracts_json_from_prose_and_fences() -> None:
    answer = "Sure, here is what I see:\n```json\n" '{"cubes_visible": [{"color": "GREEN", "where": "Conveyor"}], "tote_on_rack": "yes", "summary": "one green cube"}' "\n```"
    p = _table_cam(answer)
    r = await p.observe_visual(region_id="table_1")
    assert r["parse_ok"] is True
    # color/where are normalized to lowercase; tote_on_rack coerced from "yes"
    assert r["cubes_visible"] == [{"color": "green", "where": "conveyor"}]
    assert r["tote_on_rack"] is True


async def test_observe_visual_drops_unknown_colors_and_where() -> None:
    answer = '{"cubes_visible": [{"color": "purple", "where": "conveyor"}, {"color": "red", "where": "somewhere"}], "tote_on_rack": null, "summary": "x"}'
    p = _table_cam(answer)
    r = await p.observe_visual(region_id="table_1")
    # purple is dropped (not a cube color); red's bogus location collapses to "other"
    assert r["cubes_visible"] == [{"color": "red", "where": "other"}]
    assert r["tote_on_rack"] is None


async def test_observe_visual_falls_back_when_not_json() -> None:
    p = _table_cam("I see a control panel with colored buttons.")
    r = await p.observe_visual(region_id="table_1")
    assert r["parse_ok"] is False
    assert r["cubes_visible"] == []
    assert r["tote_on_rack"] is None
    assert "control panel" in r["summary"]


async def test_observe_visual_no_source_is_unknown() -> None:
    p = PerceptionAgent(sources=[], vlm=MockVLMClient(responses=[]))
    r = await p.observe_visual(region_id="table_1")
    assert r["parse_ok"] is False
    assert r["source_used"] == ""
    assert r["cubes_visible"] == []
