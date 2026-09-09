# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the OpenAI-compatible Cosmos VLM client + env selector (no real model)."""
from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


class _Handler(BaseHTTPRequestHandler):
    last_request: dict = {}

    def log_message(self, *_a: object) -> None:
        return

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length", 0))
        _Handler.last_request = {
            "body": json.loads(self.rfile.read(n) or b"{}"),
            "auth": self.headers.get("Authorization"),
            "path": self.path,
        }
        body = json.dumps(
            {
                "choices": [{"message": {"content": "yes - the blue block is in the tote."}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_cosmos_vlm_client_builds_request_and_parses_response() -> None:
    from policy_gated_factory_robot_orchestrator_reference.clients.vlm.cosmos_client import (
        CosmosVLMClient,
    )

    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        client = CosmosVLMClient(url=f"http://127.0.0.1:{port}", model="cosmos-reason", api_key="secret")
        resp = asyncio.run(client.query(b"\xff\xd8\xff jpeg-bytes", "Is the blue block in the tote?"))
    finally:
        httpd.shutdown()

    # Response parsed into the VLMResponse contract.
    assert resp.answer.startswith("yes")
    assert resp.input_tokens == 11 and resp.output_tokens == 7

    # Request shape: OpenAI-compatible vision call — image as a base64 data URL, model + auth set.
    req = _Handler.last_request
    assert req["path"].endswith("/v1/chat/completions")
    assert req["auth"] == "Bearer secret"
    assert req["body"]["model"] == "cosmos-reason"
    assert req["body"]["temperature"] == 0.0
    content = req["body"]["messages"][0]["content"]
    assert any(
        p.get("type") == "image_url" and p["image_url"]["url"].startswith("data:image/jpeg;base64,")
        for p in content
    )
    assert any(p.get("type") == "text" and "blue block" in p["text"] for p in content)


def test_vlm_from_env_selects_cosmos_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from policy_gated_factory_robot_orchestrator_reference.clients.vlm import vlm_from_env
    from policy_gated_factory_robot_orchestrator_reference.clients.vlm.cosmos_client import (
        CosmosVLMClient,
    )

    monkeypatch.delenv("PGFR_VLM_URL", raising=False)
    assert vlm_from_env() is None  # unconfigured -> caller falls back to ground truth

    monkeypatch.setenv("PGFR_VLM_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("PGFR_VLM_MODEL", "nvidia/cosmos-reason")
    assert isinstance(vlm_from_env(), CosmosVLMClient)


def test_live_verify_checks_predicate_over_cameras() -> None:
    # The verify loop: PerceptionAgent picks the camera covering the region, snapshots it,
    # and the VLM answers yes/no — all without ROS (mock source + mock VLM).
    import asyncio

    from policy_gated_factory_robot_orchestrator_reference.clients.vlm.base import VLMResponse
    from policy_gated_factory_robot_orchestrator_reference.clients.vlm.mock import MockVLMClient
    from policy_gated_factory_robot_orchestrator_reference.floor import ros2
    from policy_gated_factory_robot_orchestrator_reference.input_sources.mock import (
        MockInputSource,
        MockSnapshot,
    )

    cam = MockInputSource(
        "rack_cam", modality="image", coverage_region="rack_1",
        snapshots=[MockSnapshot(image_bytes=b"frame")],
    )

    class _Backend:
        def sources(self):
            return [cam]

    vlm = MockVLMClient(responses=[VLMResponse(answer="yes - the tote is on the rack")])
    out = asyncio.run(ros2.live_verify(_Backend(), "is the tote on the rack?", region="rack_1", vlm=vlm))
    assert out["answer"] == "yes"
    assert out["source_used"] == "rack_cam"
    assert vlm.calls[0].image_bytes == b"frame"


def test_live_verify_no_vlm_returns_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from policy_gated_factory_robot_orchestrator_reference.floor import ros2

    monkeypatch.delenv("PGFR_VLM_URL", raising=False)

    class _Backend:
        def sources(self):
            return []

    out = asyncio.run(ros2.live_verify(_Backend(), "anything?", vlm=None))
    assert out["answer"] == "unknown"
    assert "PGFR_VLM_URL" in out["evidence"]


def _conveyor_cam():
    from policy_gated_factory_robot_orchestrator_reference.input_sources.mock import (
        MockInputSource,
        MockSnapshot,
    )

    return MockInputSource(
        "table_cam", modality="image", coverage_region="conveyor_1",
        snapshots=[MockSnapshot(image_bytes=b"frame")],
    )


def test_live_perceive_fuses_agreeing_vision() -> None:
    import asyncio

    from policy_gated_factory_robot_orchestrator_reference.clients.vlm.base import VLMResponse
    from policy_gated_factory_robot_orchestrator_reference.clients.vlm.mock import MockVLMClient
    from policy_gated_factory_robot_orchestrator_reference.floor import ros2

    cam = _conveyor_cam()

    class _Backend:
        def observe(self, target):
            return {
                "target": target,
                "blocks_on_table": [{"item": "block", "color": "red"}, {"item": "block", "color": "blue"}],
                "counts": {"red": 1, "blue": 1},
                "sorted": False,
            }

        def sources(self):
            return [cam]

    vlm = MockVLMClient(responses=[VLMResponse(
        answer='{"cubes_visible": [{"color": "red", "where": "conveyor"}, '
               '{"color": "blue", "where": "conveyor"}], "tote_on_rack": null, "summary": "two cubes"}'
    )])
    out = asyncio.run(ros2.live_perceive(_Backend(), "conveyor_1", vlm=vlm))
    assert out["sorted"] is False  # symbolic ground truth preserved at top level
    assert out["vision_discrepancies"] == []
    assert out["vision_agrees"] is True


def test_live_perceive_flags_discrepancy_but_keeps_ground_truth() -> None:
    import asyncio

    from policy_gated_factory_robot_orchestrator_reference.clients.vlm.base import VLMResponse
    from policy_gated_factory_robot_orchestrator_reference.clients.vlm.mock import MockVLMClient
    from policy_gated_factory_robot_orchestrator_reference.floor import ros2
    from policy_gated_factory_robot_orchestrator_reference.input_sources.mock import (
        MockInputSource,
        MockSnapshot,
    )

    cam = MockInputSource(
        "rack_cam", modality="image", coverage_region="rack_1",
        snapshots=[MockSnapshot(image_bytes=b"frame")],
    )

    class _Backend:
        def observe(self, target):
            return {"target": target, "tote": {}, "tote_on_rack": False,
                    "racks": {"tote_red": 0, "tote_blue": 0, "tote_green": 0, "rack_1": 0}}

        def sources(self):
            return [cam]

    # VLM (wrongly) says the tote is on the rack; ground truth says it is not.
    vlm = MockVLMClient(responses=[VLMResponse(
        answer='{"cubes_visible": [], "tote_on_rack": true, "summary": "tote on rack"}'
    )])
    out = asyncio.run(ros2.live_perceive(_Backend(), "rack_1", vlm=vlm))
    assert out["tote_on_rack"] is False  # symbolic wins the conflict
    assert out["vision_discrepancies"] == [
        {"field": "tote_on_rack", "ground_truth": False, "vision": True}
    ]
    assert out["vision_agrees"] is False
    assert out["vision"]["tote_on_rack"] is True  # what the camera reported is still visible


def test_live_perceive_ignores_tote_on_rack_from_non_rack_camera() -> None:
    import asyncio

    from policy_gated_factory_robot_orchestrator_reference.clients.vlm.base import VLMResponse
    from policy_gated_factory_robot_orchestrator_reference.clients.vlm.mock import MockVLMClient
    from policy_gated_factory_robot_orchestrator_reference.floor import ros2

    cam = _conveyor_cam()

    class _Backend:
        def observe(self, target):
            return {"target": target, "blocks_on_table": [], "counts": {}, "sorted": True,
                    "racks": {"tote_red": 0, "tote_blue": 0, "tote_green": 0, "rack_1": 1}}

        def sources(self):
            return [cam]

    # table_cam (conveyor_1) cannot see the rack; even if Cosmos asserts tote_on_rack it must
    # not produce a discrepancy — only the rack_1 camera judges that field.
    vlm = MockVLMClient(responses=[VLMResponse(
        answer='{"cubes_visible": [], "tote_on_rack": false, "summary": "no cubes"}'
    )])
    out = asyncio.run(ros2.live_perceive(_Backend(), "conveyor_1", vlm=vlm))
    assert out["vision_discrepancies"] == []
    assert out["racks"]["rack_1"] == 1  # ground truth untouched


def test_live_perceive_no_vlm_is_symbolic_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from policy_gated_factory_robot_orchestrator_reference.floor import ros2

    monkeypatch.delenv("PGFR_VLM_URL", raising=False)

    class _Backend:
        def observe(self, target):
            return {"target": target, "blocks_on_table": [], "sorted": True}

        def sources(self):
            return []

    out = asyncio.run(ros2.live_perceive(_Backend(), "conveyor_1", vlm=None))
    assert out["sorted"] is True
    assert out["vision"] is None
    assert out["vision_discrepancies"] == []
    assert out["vision_agrees"] is False
