# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the ic_cell resources server.

Hardware-free by design: a fake in-process seam (aiohttp test server) stands in
for the IC Spine floor service, mirroring the repo convention used by the MCP
server tests. Run via ``gym env test --resources-server ic_cell``.
"""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from aiohttp import web

from nemo_gym.server_utils import ServerClient

from resources_servers.ic_cell.app import (
    ICCellResourcesServer,
    ICCellResourcesServerConfig,
    ICCellVerifyRequest,
)


def make_server(seam_url: str = "http://127.0.0.1:1", **overrides: Any) -> ICCellResourcesServer:
    config = ICCellResourcesServerConfig(
        host="0.0.0.0",
        port=8080,
        entrypoint="",
        name="ic_cell",
        seam_base_url=seam_url,
        **overrides,
    )
    return ICCellResourcesServer(config=config, server_client=MagicMock(spec=ServerClient))


class FakeSeam:
    """Minimal stand-in for the floor seam's v1 surface."""

    def __init__(self) -> None:
        self.operations: list[Dict[str, Any]] = []
        self.verify_answer = "yes"
        self.requests: list[Dict[str, Any]] = []

    def build(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/v1/dispatch", self.dispatch)
        app.router.add_post("/v1/verify", self.verify)
        app.router.add_post("/v1/floor-state", self.floor_state)
        app.router.add_get("/v1/missions/{mission_id}", self.mission_detail)
        return app

    async def dispatch(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.requests.append(
            {"path": "/v1/dispatch", "body": body, "headers": dict(request.headers)}
        )
        return web.json_response({"dispatched": True, "verified": True, "reason": "ok"})

    async def verify(self, request: web.Request) -> web.Response:
        return web.json_response({"answer": self.verify_answer, "evidence": {}})

    async def floor_state(self, request: web.Request) -> web.Response:
        return web.json_response({"endpoints": ["franka_left"], "_meta": {"api": "v1"}})

    async def mission_detail(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"mission_id": request.match_info["mission_id"], "operations": self.operations}
        )


class FakeRequest:
    """Carries the starlette session dict the handlers read."""

    def __init__(self, session_id: str = "s-1") -> None:
        self.session = {"session_id": session_id}


def verify_request(meta: Dict[str, Any]) -> ICCellVerifyRequest:
    return ICCellVerifyRequest(
        responses_create_params={"input": []},
        response={
            "id": "r",
            "object": "response",
            "created_at": 0,
            "model": "m",
            "output": [],
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
        },
        verifier_metadata=meta,
    )


class TestApp:
    def test_sanity(self) -> None:
        make_server()

    async def test_reward_requires_physics_verified_dispatch(self, aiohttp_server) -> None:
        seam = FakeSeam()
        seam.operations = [
            {"action": "move", "color": "red", "verified": True, "reason": "in tote_red"}
        ]
        server = await aiohttp_server(seam.build())
        rs = make_server(seam_url=str(server.make_url("")).rstrip("/"))
        out = await rs.verify(
            FakeRequest(),
            verify_request({"expected_action": "move", "expected_color": "red"}),
        )
        assert out.reward == 1.0
        assert out.verified_dispatches == 1

    async def test_unverified_dispatch_scores_zero(self, aiohttp_server) -> None:
        seam = FakeSeam()
        seam.operations = [
            {"action": "move", "color": "red", "verified": False, "reason": "missed off=0.19"}
        ]
        server = await aiohttp_server(seam.build())
        rs = make_server(seam_url=str(server.make_url("")).rstrip("/"))
        out = await rs.verify(
            FakeRequest(), verify_request({"expected_action": "move", "expected_color": "red"})
        )
        assert out.reward == 0.0

    async def test_wrong_color_scores_zero(self, aiohttp_server) -> None:
        seam = FakeSeam()
        seam.operations = [
            {"action": "move", "color": "blue", "verified": True, "reason": "in tote_blue"}
        ]
        server = await aiohttp_server(seam.build())
        rs = make_server(seam_url=str(server.make_url("")).rstrip("/"))
        out = await rs.verify(
            FakeRequest(), verify_request({"expected_action": "move", "expected_color": "red"})
        )
        assert out.reward == 0.0

    async def test_predicate_no_gates_reward(self, aiohttp_server) -> None:
        seam = FakeSeam()
        seam.verify_answer = "no"
        seam.operations = [{"action": "move", "color": "red", "verified": True, "reason": "ok"}]
        server = await aiohttp_server(seam.build())
        rs = make_server(seam_url=str(server.make_url("")).rstrip("/"))
        out = await rs.verify(
            FakeRequest(),
            verify_request(
                {"expected_action": "move", "predicate": "the red cube is in the tote"}
            ),
        )
        assert out.reward == 0.0
        assert out.predicate_answer == "no"

    async def test_seed_session_resets_with_operator_role(self, aiohttp_server) -> None:
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        rs = make_server(seam_url=str(server.make_url("")).rstrip("/"))
        from nemo_gym.base_resources_server import BaseSeedSessionRequest

        await rs.seed_session(FakeRequest(), BaseSeedSessionRequest())
        assert len(seam.requests) == 1
        req = seam.requests[0]
        assert req["body"] == {"action": "reset", "endpoint": "franka_left"}
        assert req["headers"].get("x-role") == "operator"
        assert req["headers"].get("x-mission-id", "").startswith("gym-")

    async def test_seam_unreachable_degrades_to_zero_reward(self) -> None:
        rs = make_server(seam_url="http://127.0.0.1:1")
        out = await rs.verify(FakeRequest(), verify_request({"expected_action": "move"}))
        assert out.reward == 0.0
        assert "journal_unreachable" in out.reason

    async def test_tool_routes_registered(self) -> None:
        rs = make_server()
        app = rs.setup_webserver()
        routes = {r.path for r in app.routes}
        for path in ("/floor_state", "/perceive", "/dispatch_task", "/check_predicate",
                     "/seed_session", "/verify", "/aggregate_metrics"):
            assert path in routes, path

    def test_example_data_contract(self) -> None:
        import pathlib

        data = pathlib.Path(__file__).parent.parent / "data" / "example.jsonl"
        rows = [json.loads(line) for line in data.read_text().splitlines()]
        assert len(rows) == 5
        reserved = {"verify", "seed_session", "aggregate_metrics", "mcp"}
        for row in rows:
            assert "responses_create_params" in row
            assert "verifier_metadata" in row
            tool_names = {t["name"] for t in row["responses_create_params"]["tools"]}
            assert not (tool_names & reserved)
