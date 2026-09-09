# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests: backend adapters, tool loop safety, CSRF, session continuity.

Hardware-free: a scripted backend + a fake seam (aiohttp) stand in for the model
and the floor service.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from aiohttp import web
from fastapi.testclient import TestClient

from ic_chat.app import _require_write_token, build_app
from ic_chat.backends import (
    AnthropicBackend,
    EchoBackend,
    OpenAIBackend,
    OpenClawBackend,
    make_backend,
)
from ic_chat.toolloop import ToolLoop, ToolLoopSettings

HDR = {"x-ic-chat": "console"}


class ScriptBackend:
    """Emits a fixed sequence of turns (each: content + tool_calls)."""

    name = "script"

    def __init__(self, turns: List[Dict[str, Any]], strict: bool = False) -> None:
        self.turns = list(turns)
        self.seen: List[List[Dict[str, Any]]] = []
        self.strict = strict

    async def respond(self, messages, tools):
        if self.strict:
            _assert_openai_shape(messages)
        self.seen.append(messages)
        return self.turns.pop(0) if self.turns else {"content": "done", "tool_calls": []}


class NativeHarnessBackend:
    """OpenClaw-shaped backend: owns tools and emits normalized events."""

    name = "openclaw"
    configured = True
    native_tool_owner = True

    def __init__(self) -> None:
        self.seen: List[tuple[List[Dict[str, Any]], str]] = []

    async def respond(self, messages, tools):  # pragma: no cover - must never be called
        raise AssertionError("native harness must not enter the IC Chat tool loop")

    async def run_native_stream(self, messages, mission_id):
        self.seen.append((messages, mission_id))
        yield {"role": "tool_start", "name": "floor_state", "args": {}}
        yield {
            "role": "tool",
            "name": "floor_state",
            "args": {},
            "result": {
                "status": "ok",
                "harness": "openclaw",
                "harness_tool": "ic-floor__floor_state",
            },
        }
        yield {"role": "assistant", "content": "Native OpenClaw reply.", "tool_calls": []}

    async def request_stop(self, mission_id):
        return {"accepted": True, "status": "stopping", "mission_id": mission_id}


def _assert_openai_shape(messages: List[Dict[str, Any]]) -> None:
    """Enforce the OpenAI contract a strict endpoint/NIM enforces: every
    role:tool message follows an assistant with a matching tool_call id, and
    every declared tool_call id gets exactly one tool reply."""
    i = 0
    while i < len(messages):
        m = messages[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            declared = [tc["id"] for tc in m["tool_calls"]]
            answered = []
            j = i + 1
            while j < len(messages) and messages[j].get("role") == "tool":
                answered.append(messages[j]["tool_call_id"])
                j += 1
            assert sorted(declared) == sorted(answered), (
                f"unanswered tool_calls: declared={declared} answered={answered}"
            )
            i = j
            continue
        if m.get("role") == "tool":
            raise AssertionError("tool message not preceded by matching assistant tool_calls")
        i += 1


class FakeSeam:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.dispatch_response = {"dispatched": True, "verified": True, "reason": "in tote"}
        self.verify_response = {
            "answer": "yes",
            "evidence": "the requested object is visibly in the tote",
            "source_used": "inspect_cam",
        }
        self.floor_state_response = {
            "cubes": [
                {"i": 0, "color": "red", "where": "tote"},
                {"i": 1, "color": "red", "where": "tote_r"},
                {"i": 2, "color": "blue", "where": "tote"},
                {"i": 3, "color": "blue", "where": "tote_r"},
            ],
            "tote": {"red": "in", "blue": "in"},
            "tote_r": {"red": "in", "blue": "in"},
            "tote_on_rack": True,
            "tote_r_on_rack": True,
        }
        self.frames: Dict[str, bytes] = {}  # request_id -> jpg bytes

    def build(self) -> web.Application:
        app = web.Application()
        for route in ("/v1/floor-state", "/v1/perceive", "/v1/dispatch", "/v1/verify"):
            app.router.add_post(route, self.handle)
        app.router.add_get("/v1/frames/{rid}", self.frame)
        return app

    async def handle(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.calls.append(
            {
                "path": request.path,
                "body": body,
                "mission": request.headers.get("x-mission-id"),
                "role": request.headers.get("x-role"),
            }
        )
        rid = f"req-{len(self.calls)}"
        self.frames[rid] = b"\xff\xd8jpgbytes"  # pretend a frame exists for this op
        headers = {"x-request-id": rid}
        if request.path == "/v1/dispatch":
            return web.json_response(self.dispatch_response, headers=headers)
        if request.path == "/v1/verify":
            return web.json_response(self.verify_response, headers=headers)
        if request.path == "/v1/floor-state":
            return web.json_response(self.floor_state_response, headers=headers)
        return web.json_response({"ok": True, "path": request.path}, headers=headers)

    async def frame(self, request: web.Request) -> web.Response:
        rid = request.match_info["rid"]
        if rid not in self.frames:
            return web.Response(status=404)
        return web.Response(body=self.frames[rid], content_type="image/jpeg")


def loop_for(server) -> ToolLoop:
    s = ToolLoopSettings()
    s.seam_url = str(server.make_url("")).rstrip("/")
    return ToolLoop(s)


class TestBackends:
    async def test_echo_plain(self) -> None:
        out = await EchoBackend().respond([{"role": "user", "content": "hi"}], [])
        assert out["content"] == "echo: hi"
        assert out["tool_calls"] == []

    async def test_echo_tool_directive(self) -> None:
        out = await EchoBackend().respond(
            [{"role": "user", "content": 'tool perceive {"target": "tote"}'}], []
        )
        assert out["tool_calls"][0]["name"] == "perceive"
        assert out["tool_calls"][0]["arguments"] == {"target": "tote"}

    async def test_echo_stops_after_tool_result(self) -> None:
        # A tool result as the last message = the action ran; do not re-fire.
        out = await EchoBackend().respond(
            [
                {"role": "user", "content": 'tool perceive {"target": "tote"}'},
                {"role": "tool", "tool_call_id": "echo-0", "content": "{}"},
            ],
            [],
        )
        assert out["tool_calls"] == []

    def test_make_backend_unknown(self) -> None:
        with pytest.raises(ValueError):
            make_backend("nope")

    def test_openai_requires_url(self) -> None:
        import asyncio

        b = OpenAIBackend(base_url="")
        with pytest.raises(RuntimeError):
            asyncio.get_event_loop().run_until_complete(b.respond([], []))

    async def test_openai_readiness_requires_the_advertised_model(
        self, aiohttp_server
    ) -> None:
        seen: Dict[str, Any] = {}

        async def models(request: web.Request) -> web.Response:
            seen.setdefault("authorization", []).append(
                request.headers.get("authorization")
            )
            return web.json_response({"data": [{"id": "reasoning-model"}]})

        app = web.Application()
        app.router.add_get("/v1/models", models)
        server = await aiohttp_server(app)
        base_url = str(server.make_url("")).rstrip("/")

        ready = await OpenAIBackend(
            base_url=base_url,
            api_key="endpoint-token",
            model="reasoning-model",
        ).readiness()
        mismatch = await OpenAIBackend(
            base_url=base_url,
            model="different-model",
        ).readiness()

        assert ready == {
            "ready": True,
            "backend": "openai",
            "model": "reasoning-model",
        }
        assert seen["authorization"] == ["Bearer endpoint-token", None]
        assert mismatch["ready"] is False
        assert mismatch["advertised_models"] == ["reasoning-model"]

    async def test_openai_uses_sk_style_ic_chat_key_for_tool_call(
        self, aiohttp_server, monkeypatch
    ) -> None:
        seen: Dict[str, Any] = {}

        async def completions(request: web.Request) -> web.Response:
            seen["authorization"] = request.headers.get("authorization")
            seen["body"] = await request.json()
            return web.json_response({
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "id": "internal-call-1",
                            "type": "function",
                            "function": {
                                "name": "dispatch_task",
                                "arguments": '{"color":"red"}',
                            },
                        }],
                    }
                }]
            })

        app = web.Application()
        app.router.add_post("/v1/chat/completions", completions)
        server = await aiohttp_server(app)
        api_key = "sk-internal-NVIDIA_42.token"
        model = "nvidia/internal-reasoning-model"
        monkeypatch.setenv(
            "IC_CHAT_MODEL_URL", str(server.make_url("")).rstrip("/")
        )
        monkeypatch.setenv("IC_CHAT_API_KEY", api_key)
        monkeypatch.setenv("IC_CHAT_MODEL", model)
        tool = {
            "name": "dispatch_task",
            "description": "Move one object through the policy gate.",
            "parameters": {
                "type": "object",
                "properties": {"color": {"type": "string"}},
                "required": ["color"],
            },
        }

        out = await OpenAIBackend().respond(
            [{"role": "user", "content": "move the red object"}], [tool]
        )

        assert seen["authorization"] == f"Bearer {api_key}"
        assert seen["body"]["model"] == model
        assert seen["body"]["tools"] == [{"type": "function", "function": tool}]
        assert seen["body"]["tool_choice"] == "auto"
        assert out == {
            "content": "",
            "tool_calls": [{
                "id": "internal-call-1",
                "name": "dispatch_task",
                "arguments": {"color": "red"},
            }],
        }

    def test_anthropic_reuses_openclaw_nim_key(self, monkeypatch) -> None:
        monkeypatch.delenv("IC_CHAT_API_KEY", raising=False)
        monkeypatch.setenv("NVIDIA_NIM_API_KEY", "shared-openclaw-key")
        backend = AnthropicBackend(
            base_url="https://inference-api.nvidia.com",
            model="aws/anthropic/bedrock-claude-opus-4-8",
        )
        assert backend.api_key == "shared-openclaw-key"

    def test_openclaw_timeout_uses_environment_default(self, monkeypatch) -> None:
        monkeypatch.setenv("IC_OPENCLAW_TIMEOUT_S", "900")
        backend = OpenClawBackend(
            base_url="http://127.0.0.1:18790",
            api_key="gateway-token",
            native_gateway=True,
        )
        assert backend.timeout_s == 900.0
        assert backend.gateway.timeout_s == 900.0

    def test_openclaw_reuses_official_gateway_token(self, monkeypatch, tmp_path) -> None:
        monkeypatch.delenv("IC_OPENCLAW_TOKEN", raising=False)
        monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "shared-gateway-token")
        backend = OpenClawBackend(
            base_url="http://127.0.0.1:18790",
            config_path=str(tmp_path / "missing-openclaw.json"),
            native_gateway=True,
        )

        assert backend.configured is True
        assert backend.api_key == "shared-gateway-token"
        assert backend.gateway.token == "shared-gateway-token"

    def test_openclaw_prefers_ic_token_override(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("IC_OPENCLAW_TOKEN", "ic-token")
        monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "official-token")
        backend = OpenClawBackend(
            base_url="http://127.0.0.1:18790",
            config_path=str(tmp_path / "missing-openclaw.json"),
            native_gateway=True,
        )

        assert backend.api_key == "ic-token"
        assert backend.gateway.token == "ic-token"

    def test_openclaw_explicit_timeout_overrides_environment(self, monkeypatch) -> None:
        monkeypatch.setenv("IC_OPENCLAW_TIMEOUT_S", "900")
        backend = OpenClawBackend(
            base_url="http://127.0.0.1:18790",
            api_key="gateway-token",
            timeout_s=12.0,
            native_gateway=True,
        )
        assert backend.timeout_s == 12.0
        assert backend.gateway.timeout_s == 12.0

    async def test_openclaw_uses_supported_gateway_chat_endpoint(
        self, aiohttp_server
    ) -> None:
        seen: Dict[str, Any] = {}

        async def completions(request: web.Request) -> web.Response:
            seen["authorization"] = request.headers.get("authorization")
            seen["body"] = await request.json()
            return web.json_response({
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "id": "oc-1",
                            "type": "function",
                            "function": {
                                "name": "floor_state",
                                "arguments": "{}",
                            },
                        }],
                    }
                }]
            })

        app = web.Application()
        app.router.add_post("/v1/chat/completions", completions)
        server = await aiohttp_server(app)
        backend = OpenClawBackend(
            base_url=str(server.make_url("")).rstrip("/"),
            api_key="gateway-token",
            model="openclaw/ic-console",
        )
        out = await backend.respond(
            [{"role": "user", "content": "inspect"}],
            [{"name": "floor_state", "parameters": {"type": "object", "properties": {}}}],
        )

        assert seen["authorization"] == "Bearer gateway-token"
        assert seen["body"]["model"] == "openclaw/ic-console"
        assert seen["body"]["tools"][0]["function"]["name"] == "floor_state"
        assert out["tool_calls"][0]["name"] == "floor_state"


class TestToolLoop:
    async def test_stop_prevents_a_new_dispatch(self) -> None:
        loop = ToolLoop()
        loop.request_stop("chat-stop")
        backend = ScriptBackend(
            [{"content": "", "tool_calls": [{
                "id": "d1",
                "name": "dispatch_task",
                "arguments": {
                    "action": "move",
                    "endpoint": "franka_left",
                    "color": "red",
                },
            }]}]
        )

        out = await loop.run(
            backend, [{"role": "user", "content": "move red"}], "chat-stop"
        )

        assert backend.seen == []
        assert "Stopped by the operator" in out["transcript"][-1]["content"]

    async def test_tool_call_hits_seam_with_mission_id(self, aiohttp_server) -> None:
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {"content": "", "tool_calls": [
                    {"id": "1", "name": "perceive", "arguments": {"target": "tote"}}]},
                {"content": "the tote has cubes", "tool_calls": []},
            ]
        )
        out = await loop.run(backend, [{"role": "user", "content": "look"}], "chat-abc")
        assert seam.calls[0]["path"] == "/v1/perceive"
        assert seam.calls[0]["mission"] == "chat-abc"
        assert out["transcript"][-1]["content"] == "the tote has cubes"

    async def test_tool_result_carries_evidence_request_id(self, aiohttp_server) -> None:
        # Each tool result should carry the seam's x-request-id so the frontend
        # can fetch the exact frame the VLM saw for that op.
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {"content": "", "tool_calls": [
                    {"id": "1", "name": "perceive", "arguments": {"target": "tote"}}]},
                {"content": "ok", "tool_calls": []},
            ]
        )
        out = await loop.run(backend, [{"role": "user", "content": "look"}], "chat-abc")
        tool = [e for e in out["transcript"] if e["role"] == "tool"][0]
        assert tool["result"]["request_id"].startswith("req-")

    async def test_operator_action_refused_before_seam(self, aiohttp_server) -> None:
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [{"content": "", "tool_calls": [
                {"id": "1", "name": "dispatch_task",
                 "arguments": {"action": "reset", "endpoint": "franka_left"}}]}]
        )
        out = await loop.run(backend, [{"role": "user", "content": "reset"}], "chat-abc")
        tool_entry = [e for e in out["transcript"] if e["role"] == "tool"][0]
        assert "not agent-class" in tool_entry["result"]["error"]
        assert seam.calls == []  # never reached the seam

    async def test_explicit_reset_scene_uses_operator_route(self, aiohttp_server) -> None:
        seam = FakeSeam()
        seam.dispatch_response = {
            "dispatched": True,
            "verified": True,
            "reason": "scene reset",
        }
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        result = await loop.execute_tool("reset_scene", {}, "chat-reset")
        assert result["verified"] is True
        assert seam.calls == [
            {
                "path": "/v1/dispatch",
                "body": {
                    "endpoint": "mobilebot",
                    "action": "reset_scene",
                    "scene_profile": "groot_three_object",
                    "arm": "both",
                    "color": "red",
                    "layout_left": 3,
                    "layout_right": 3,
                    "seed": 31302,
                },
                "mission": "chat-reset",
                "role": "operator",
            }
        ]

    async def test_tool_result_follows_assistant_tool_calls(self, aiohttp_server) -> None:
        # OpenAI contract: a role:tool message must follow an assistant message
        # whose tool_calls[].id matches the tool_call_id. Verify the loop builds
        # that shape (regression for the broken-first-tool-call bug).
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {"content": "", "tool_calls": [
                    {"id": "call_x", "name": "perceive", "arguments": {"target": "tote"}}]},
                {"content": "ok", "tool_calls": []},
            ],
            strict=True,
        )
        await loop.run(backend, [{"role": "user", "content": "look"}], "chat-abc")
        second_turn = backend.seen[1]  # messages sent to the model on turn 2
        # find the tool message and the assistant message before it
        tool_idx = next(i for i, m in enumerate(second_turn) if m.get("role") == "tool")
        prior = second_turn[tool_idx - 1]
        assert prior["role"] == "assistant"
        ids = {tc["id"] for tc in prior.get("tool_calls", [])}
        assert second_turn[tool_idx]["tool_call_id"] in ids

    async def test_one_dispatch_per_turn(self, aiohttp_server) -> None:
        # A model emitting 3 dispatches in one turn must only actuate ONCE;
        # the rest are dropped, the model re-deliberates, AND the message list
        # stays OpenAI-valid on the next turn (strict=True enforces the contract).
        seam = FakeSeam()
        seam.dispatch_response = {"dispatched": True, "verified": False, "reason": "missed"}
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {"content": "", "tool_calls": [
                    {"id": "a", "name": "dispatch_task",
                     "arguments": {"action": "move", "endpoint": "franka_left", "color": "red"}},
                    {"id": "b", "name": "dispatch_task",
                     "arguments": {"action": "move", "endpoint": "franka_left", "color": "blue"}},
                    {"id": "c", "name": "dispatch_task",
                     "arguments": {"action": "move", "endpoint": "franka_left", "color": "green"}},
                ]},
                {"content": "stopping", "tool_calls": []},
            ],
            strict=True,  # would 400 on a real endpoint if b/c were left unanswered
        )
        await loop.run(backend, [{"role": "user", "content": "go"}], "chat-abc")
        dispatches = [c for c in seam.calls if c["path"] == "/v1/dispatch"]
        assert len(dispatches) == 1  # only the first fired

    async def test_reads_then_dispatch_stay_openai_valid(self, aiohttp_server) -> None:
        # perceive + dispatch + perceive in one turn: reads before the dispatch
        # run, the dispatch runs, the trailing read is dropped — and every
        # declared tool_call is answered (strict mock would 400 otherwise).
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {"content": "", "tool_calls": [
                    {"id": "p1", "name": "perceive", "arguments": {"target": "conveyor_1"}},
                    {"id": "d1", "name": "dispatch_task",
                     "arguments": {"action": "move", "endpoint": "franka_left", "color": "red"}},
                    {"id": "p2", "name": "perceive", "arguments": {"target": "tote"}},
                ]},
                {"content": "done", "tool_calls": []},
            ],
            strict=True,
        )
        await loop.run(backend, [{"role": "user", "content": "go"}], "chat-abc")
        assert len([c for c in seam.calls if c["path"] == "/v1/dispatch"]) == 1
        # the trailing perceive (p2) was dropped, not executed
        assert len([c for c in seam.calls if c["path"] == "/v1/perceive"]) == 1

    async def test_second_dispatch_requires_fresh_vlm_proof(self, aiohttp_server) -> None:
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {"content": "", "tool_calls": [
                    {"id": "d1", "name": "dispatch_task", "arguments": {
                        "action": "move", "endpoint": "franka_left", "color": "red"}}]},
                {"content": "", "tool_calls": [
                    {"id": "d2", "name": "dispatch_task", "arguments": {
                        "action": "move", "endpoint": "franka_left", "color": "blue"}}]},
                {"content": "stopped by proof gate", "tool_calls": []},
            ],
            strict=True,
        )
        out = await loop.run(backend, [{"role": "user", "content": "go"}], "chat-proof")
        dispatches = [c for c in seam.calls if c["path"] == "/v1/dispatch"]
        assert len(dispatches) == 1
        refused = [
            e for e in out["transcript"]
            if e.get("role") == "tool" and e.get("result", {}).get("status") == "refused"
        ]
        assert refused
        assert refused[0]["result"]["pending_visual_proof"]["color"] == "red"

    async def test_action_claim_without_dispatch_is_rejected_and_retried(
        self, aiohttp_server
    ) -> None:
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {
                    "content": "Verified — right red is now in the right tote.",
                    "tool_calls": [
                        {
                            "id": "v-premature",
                            "name": "check_predicate",
                            "arguments": {
                                "predicate": "the red cube is in the right tote",
                                "region": "tote_r",
                            },
                        },
                        {"id": "f-premature", "name": "floor_state", "arguments": {}},
                    ],
                },
                {
                    "content": "Dispatching right red.",
                    "tool_calls": [
                        {
                            "id": "d1",
                            "name": "dispatch_task",
                            "arguments": {
                                "action": "move",
                                "endpoint": "franka_right",
                                "color": "red",
                                "source": "conveyor_1",
                                "destination": "tote_red",
                                "backend": "groot",
                            },
                        }
                    ],
                },
                {
                    "content": "The dispatch returned; checking the camera.",
                    "tool_calls": [
                        {
                            "id": "v1",
                            "name": "check_predicate",
                            "arguments": {
                                "predicate": "the red cube is in the right tote",
                                "region": "tote_r",
                            },
                        }
                    ],
                },
                {"content": "Right red is now in the right tote.", "tool_calls": []},
            ],
            strict=True,
        )

        out = await loop.run(
            backend, [{"role": "user", "content": "move right red"}], "chat-claim"
        )

        assert [c["path"] for c in seam.calls] == [
            "/v1/dispatch", "/v1/verify", "/v1/floor-state"
        ]
        corrections = [
            e["content"]
            for e in out["transcript"]
            if e.get("role") == "assistant"
            and str(e.get("content", "")).startswith("Action-claim gate:")
        ]
        assert corrections

    async def test_pending_visual_proof_prevents_early_final_answer(
        self, aiohttp_server
    ) -> None:
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {
                    "content": "Dispatching.",
                    "tool_calls": [
                        {
                            "id": "d1",
                            "name": "dispatch_task",
                            "arguments": {
                                "action": "move",
                                "endpoint": "franka_left",
                                "color": "red",
                                "source": "conveyor_1",
                                "destination": "tote_red",
                            },
                        }
                    ],
                },
                {"content": "The move is complete.", "tool_calls": []},
                {
                    "content": "Checking.",
                    "tool_calls": [
                        {
                            "id": "v1",
                            "name": "check_predicate",
                            "arguments": {
                                "predicate": "the red cube is in the left tote",
                                "region": "tote",
                            },
                        }
                    ],
                },
                {"content": "Done.", "tool_calls": []},
            ],
            strict=True,
        )

        out = await loop.run(
            backend, [{"role": "user", "content": "move red"}], "chat-final-proof"
        )

        assert [c["path"] for c in seam.calls] == [
            "/v1/dispatch", "/v1/verify", "/v1/floor-state"
        ]
        assert any(
            str(e.get("content", "")).startswith("Visual-proof gate:")
            for e in out["transcript"]
            if e.get("role") == "assistant"
        )

    async def test_later_turn_can_clear_and_acknowledge_pending_proof(
        self, aiohttp_server
    ) -> None:
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        mission = "chat-proof-retry"
        dispatched = await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_right",
                "color": "red",
                "source": "conveyor_2",
                "destination": "tote_green",
                "backend": "scripted",
            },
            mission,
        )
        assert dispatched["proof_gate"]["state"] == "awaiting_vlm"

        backend = ScriptBackend(
            [
                {
                    "content": "Retrying the visual check.",
                    "tool_calls": [
                        {
                            "id": "v-retry",
                            "name": "check_predicate",
                            "arguments": {
                                "predicate": "the red cube is in the right tote",
                                "region": "tote_r",
                            },
                        }
                    ],
                },
                {
                    "content": "The red cube is now verified in the right tote.",
                    "tool_calls": [],
                },
            ],
            strict=True,
        )

        out = await loop.run(
            backend,
            [{"role": "user", "content": "retry only the visual check"}],
            mission,
        )

        assert out["transcript"][-1]["content"] == (
            "The red cube is now verified in the right tote."
        )
        assert not any(
            str(e.get("content", "")).startswith("Action-claim gate:")
            for e in out["transcript"]
            if e.get("role") == "assistant"
        )

    async def test_journaled_vlm_yes_clears_gate_for_next_dispatch(
        self, aiohttp_server
    ) -> None:
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {"content": "", "tool_calls": [
                    {"id": "d1", "name": "dispatch_task", "arguments": {
                        "action": "move", "endpoint": "franka_left", "color": "red"}}]},
                {"content": "", "tool_calls": [
                    {"id": "v1", "name": "check_predicate", "arguments": {
                        "predicate": "the red cube is in the left tote", "region": "tote"}}]},
                {"content": "", "tool_calls": [
                    {"id": "d2", "name": "dispatch_task", "arguments": {
                        "action": "move", "endpoint": "franka_left", "color": "blue"}}]},
                {"content": "two actions complete", "tool_calls": []},
            ],
            strict=True,
        )
        out = await loop.run(backend, [{"role": "user", "content": "go"}], "chat-proof")
        assert len([c for c in seam.calls if c["path"] == "/v1/dispatch"]) == 2
        verify = next(
            e for e in out["transcript"]
            if e.get("role") == "tool" and e.get("name") == "check_predicate"
        )
        assert verify["result"]["proof_gate"]["state"] == "cleared"
        assert verify["result"]["identity_proof"]["ok"] is True
        assert verify["result"]["request_id"].startswith("req-")

    async def test_vlm_yes_cannot_clear_gate_when_identity_stays_at_spawn(
        self, aiohttp_server
    ) -> None:
        seam = FakeSeam()
        seam.floor_state_response = {
            "cubes": [{"i": 5, "color": "green", "where": "conveyor"}],
            "tote_r": {},
            "tote_r_on_rack": False,
        }
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {"content": "", "tool_calls": [
                    {"id": "d1", "name": "dispatch_task", "arguments": {
                        "action": "move", "endpoint": "franka_right",
                        "color": "green", "source": "conveyor_1",
                        "destination": "tote_green"}}]},
                {"content": "", "tool_calls": [
                    {"id": "v1", "name": "check_predicate", "arguments": {
                        "predicate": "the green brick is in the right tote",
                        "region": "tote_r"}}]},
                {"content": "", "tool_calls": [
                    {"id": "d2", "name": "dispatch_task", "arguments": {
                        "action": "move", "endpoint": "franka_left",
                        "color": "red"}}]},
                {"content": "stopped", "tool_calls": []},
            ],
            strict=True,
        )

        out = await loop.run(
            backend, [{"role": "user", "content": "go"}], "chat-identity-proof"
        )

        assert len([c for c in seam.calls if c["path"] == "/v1/dispatch"]) == 1
        verify = next(
            e for e in out["transcript"]
            if e.get("role") == "tool" and e.get("name") == "check_predicate"
        )
        assert verify["result"]["proof_gate"]["state"] == "awaiting_identity"
        assert verify["result"]["identity_proof"]["ok"] is False
        assert verify["result"]["identity_proof"]["matched_indices"] == []

    async def test_failed_move_reconciled_at_source_allows_retry(
        self, aiohttp_server
    ) -> None:
        seam = FakeSeam()
        seam.dispatch_response = {
            "dispatched": False,
            "verified": False,
            "reason": (
                "groot physical-friction timeout grasp_seen=True "
                "released=False"
            ),
        }
        seam.floor_state_response = {
            "cubes": [{"i": 2, "color": "blue", "where": "conveyor"}],
            "tote": {},
            "tote_r": {},
        }
        seam.verify_response = {
            "answer": "yes",
            "evidence": "the blue cylinder is visibly on conveyor_1",
            "source_used": "inspect_cam",
        }
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        mission = "chat-failed-source-retry"

        failed = await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_left",
                "color": "blue",
                "source": "conveyor_1",
                "destination": "tote_blue",
                "backend": "groot",
            },
            mission,
        )

        assert failed["verified"] is False
        assert failed["proof_gate"]["state"] == "awaiting_reconciliation"
        assert failed["proof_gate"]["dispatch"]["dispatch_verified"] is False

        reconciled = await loop.execute_tool(
            "check_predicate",
            {
                "predicate": "Is the blue cylinder still on conveyor_1?",
                "region": "conveyor_1",
            },
            mission,
        )

        assert reconciled["proof_gate"]["state"] == "cleared_failed_action"
        assert reconciled["identity_proof"]["ok"] is True
        assert reconciled["identity_proof"]["matched_indices"] == [2]
        assert reconciled["retry_allowed"] is True

        seam.dispatch_response = {
            "dispatched": True,
            "verified": True,
            "reason": "in tote",
        }
        retry = await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_left",
                "color": "blue",
                "source": "conveyor_1",
                "destination": "tote_blue",
                "backend": "groot",
            },
            mission,
        )

        assert retry["verified"] is True
        assert retry["proof_gate"]["state"] == "awaiting_vlm"
        assert [c["path"] for c in seam.calls] == [
            "/v1/dispatch",
            "/v1/verify",
            "/v1/floor-state",
            "/v1/dispatch",
        ]

    async def test_failed_move_source_proof_requires_authoritative_source_identity(
        self, aiohttp_server
    ) -> None:
        seam = FakeSeam()
        seam.dispatch_response = {
            "dispatched": False,
            "verified": False,
            "reason": "timeout",
        }
        seam.floor_state_response = {
            "cubes": [{"i": 2, "color": "blue", "where": "tote"}],
            "tote": {"blue": "in"},
            "tote_r": {},
        }
        seam.verify_response = {
            "answer": "yes",
            "evidence": "a blue shape is visible near the conveyor",
            "source_used": "inspect_cam",
        }
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        mission = "chat-failed-source-mismatch"

        await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_left",
                "color": "blue",
                "source": "conveyor_1",
                "destination": "tote_blue",
                "backend": "groot",
            },
            mission,
        )
        reconciliation = await loop.execute_tool(
            "check_predicate",
            {
                "predicate": "Is the blue cylinder still on conveyor_1?",
                "region": "conveyor_1",
            },
            mission,
        )

        assert reconciliation["proof_gate"]["state"] == "awaiting_reconciliation"
        assert reconciliation["identity_proof"]["ok"] is False
        assert reconciliation["retry_allowed"] is False

        refused_retry = await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_left",
                "color": "blue",
                "source": "conveyor_1",
                "destination": "tote_blue",
                "backend": "groot",
            },
            mission,
        )
        assert refused_retry["status"] == "refused"
        assert len([c for c in seam.calls if c["path"] == "/v1/dispatch"]) == 1

    async def test_unverified_destination_is_not_a_completed_step(
        self, aiohttp_server
    ) -> None:
        seam = FakeSeam()
        seam.dispatch_response = {
            "dispatched": False,
            "verified": False,
            "reason": "timeout after physical motion",
        }
        seam.floor_state_response = {
            "cubes": [{"i": 5, "color": "green", "where": "tote_r"}],
            "tote": {},
            "tote_r": {"green": "in"},
        }
        seam.verify_response = {
            "answer": "yes",
            "evidence": "the green brick is visibly in the right tote",
            "source_used": "outside_right_cam",
        }
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        mission = "chat-unverified-at-destination"

        await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_right",
                "color": "green",
                "source": "conveyor_2",
                "destination": "tote_green",
                "backend": "groot",
            },
            mission,
        )
        reconciliation = await loop.execute_tool(
            "check_predicate",
            {
                "predicate": "Is the green brick in the right tote?",
                "region": "tote_r",
            },
            mission,
        )

        assert reconciliation["proof_gate"]["state"] == (
            "reconciled_unverified_destination"
        )
        assert reconciliation["identity_proof"]["ok"] is True
        assert reconciliation["step_complete"] is False
        assert reconciliation["mission_must_stop"] is True
        assert reconciliation["retry_allowed"] is False

        refused = await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_left",
                "color": "red",
                "source": "conveyor_1",
                "destination": "tote_red",
            },
            mission,
        )
        assert refused["status"] == "refused"
        assert refused["mission_must_stop"] is True
        assert len([c for c in seam.calls if c["path"] == "/v1/dispatch"]) == 1

    async def test_failed_move_off_target_ends_gate_without_deadlock(
        self, aiohttp_server
    ) -> None:
        seam = FakeSeam()
        seam.dispatch_response = {
            "dispatched": False,
            "verified": False,
            "reason": "timeout after physical motion",
        }
        seam.floor_state_response = {
            "cubes": [{"i": 4, "color": "green", "where": "off"}],
            "tote": {},
            "tote_r": {},
        }
        seam.verify_response = {
            "answer": "yes",
            "evidence": "a green shape is visible near the tote",
            "source_used": "inspect_cam",
        }
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        mission = "chat-failed-off-target"

        await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_left",
                "color": "green",
                "source": "conveyor_1",
                "destination": "tote_green",
                "backend": "groot",
            },
            mission,
        )
        reconciliation = await loop.execute_tool(
            "check_predicate",
            {
                "predicate": "Is the green brick in the left tote?",
                "region": "tote",
            },
            mission,
        )

        assert reconciliation["proof_gate"]["state"] == "failed_irreconcilable"
        assert reconciliation["step_complete"] is False
        assert reconciliation["mission_must_stop"] is True
        assert mission not in loop._visual_proof_pending

    async def test_only_one_failed_source_retry_is_allowed(
        self, aiohttp_server
    ) -> None:
        seam = FakeSeam()
        seam.dispatch_response = {
            "dispatched": False,
            "verified": False,
            "reason": "timeout",
        }
        seam.floor_state_response = {
            "cubes": [{"i": 2, "color": "blue", "where": "conveyor"}],
            "tote": {},
            "tote_r": {},
        }
        seam.verify_response = {
            "answer": "yes",
            "evidence": "the blue cylinder is visibly on conveyor_1",
            "source_used": "inspect_cam",
        }
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        mission = "chat-one-retry"
        dispatch_args = {
            "action": "move",
            "endpoint": "franka_left",
            "color": "blue",
            "source": "conveyor_1",
            "destination": "tote_blue",
            "backend": "groot",
        }
        proof_args = {
            "predicate": "Is the blue cylinder still on conveyor_1?",
            "region": "conveyor_1",
        }

        await loop.execute_tool("dispatch_task", dispatch_args, mission)
        first = await loop.execute_tool(
            "check_predicate", proof_args, mission
        )
        assert first["proof_gate"]["state"] == "cleared_failed_action"
        assert first["retry_allowed"] is True

        await loop.execute_tool("dispatch_task", dispatch_args, mission)
        second = await loop.execute_tool(
            "check_predicate", proof_args, mission
        )
        assert second["proof_gate"]["state"] == "failed_retry_exhausted"
        assert second["mission_must_stop"] is True
        assert second["retry_allowed"] is False
        assert len([c for c in seam.calls if c["path"] == "/v1/dispatch"]) == 2

    async def test_vlm_no_keeps_gate_closed(self, aiohttp_server) -> None:
        seam = FakeSeam()
        seam.verify_response = {
            "answer": "no",
            "evidence": "the tote compartment is visibly empty",
            "source_used": "inspect_cam",
        }
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {"content": "", "tool_calls": [
                    {"id": "d1", "name": "dispatch_task", "arguments": {
                        "action": "move", "endpoint": "franka_left", "color": "red"}}]},
                {"content": "", "tool_calls": [
                    {"id": "v1", "name": "check_predicate", "arguments": {
                        "predicate": "the red cube is in the left tote", "region": "tote"}}]},
                {"content": "", "tool_calls": [
                    {"id": "d2", "name": "dispatch_task", "arguments": {
                        "action": "move", "endpoint": "franka_left", "color": "blue"}}]},
                {"content": "stopped", "tool_calls": []},
            ],
            strict=True,
        )
        out = await loop.run(backend, [{"role": "user", "content": "go"}], "chat-proof")
        assert len([c for c in seam.calls if c["path"] == "/v1/dispatch"]) == 1
        verify = next(
            e for e in out["transcript"]
            if e.get("role") == "tool" and e.get("name") == "check_predicate"
        )
        assert verify["result"]["proof_gate"]["state"] == "awaiting_vlm"

    async def test_unrelated_yes_cannot_clear_move_gate(self, aiohttp_server) -> None:
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        loop = loop_for(server)
        backend = ScriptBackend(
            [
                {"content": "", "tool_calls": [
                    {"id": "d1", "name": "dispatch_task", "arguments": {
                        "action": "move", "endpoint": "franka_left", "color": "red",
                        "source": "conveyor_1", "destination": "tote_red"}}]},
                {"content": "", "tool_calls": [
                    {"id": "v1", "name": "check_predicate", "arguments": {
                        "predicate": "the red cube is still on conveyor_1",
                        "region": "conveyor_1"}}]},
                {"content": "", "tool_calls": [
                    {"id": "d2", "name": "dispatch_task", "arguments": {
                        "action": "move", "endpoint": "franka_left", "color": "blue"}}]},
                {"content": "stopped", "tool_calls": []},
            ],
            strict=True,
        )
        out = await loop.run(
            backend, [{"role": "user", "content": "go"}], "chat-proof-binding"
        )
        assert len([c for c in seam.calls if c["path"] == "/v1/dispatch"]) == 1
        assert not [c for c in seam.calls if c["path"] == "/v1/verify"]
        refused = next(
            e for e in out["transcript"]
            if e.get("role") == "tool"
            and e.get("name") == "check_predicate"
        )
        assert refused["result"]["status"] == "refused"
        assert "must use region 'tote'" in refused["result"]["error"]

    async def test_loop_bounded(self, aiohttp_server) -> None:
        seam = FakeSeam()
        server = await aiohttp_server(seam.build())
        s = ToolLoopSettings()
        s.seam_url = str(server.make_url("")).rstrip("/")
        s.max_tool_turns = 3
        loop = ToolLoop(s)
        # backend that never stops calling tools
        backend = ScriptBackend(
            [{"content": "", "tool_calls": [
                {"id": str(i), "name": "floor_state", "arguments": {}}]} for i in range(10)]
        )
        out = await loop.run(backend, [{"role": "user", "content": "go"}], "chat-abc")
        assert len([e for e in out["transcript"] if e["role"] == "assistant"]) == 3


class TestAPI:
    def make_client(self, backend, seam_url: str = "http://127.0.0.1:1",
                    tmp_path=None, max_sessions=200, max_history=200,
                    openclaw_backend=None):
        import tempfile

        from ic_chat.sessions import SessionStore

        s = ToolLoopSettings()
        s.seam_url = seam_url
        root = str(tmp_path) if tmp_path else tempfile.mkdtemp()
        store = SessionStore(root, max_sessions=max_sessions, max_history=max_history)
        return TestClient(build_app(
            backend=backend,
            openclaw_backend=openclaw_backend,
            loop=ToolLoop(s),
            sessions_store=store,
        ))

    def test_csrf_missing_header_refused(self) -> None:
        client = self.make_client(EchoBackend())
        r = client.post("/api/chat", json={"message": "hi"})
        assert r.status_code == 403
        assert "CSRF" in r.text

    def test_csrf_foreign_origin_refused(self) -> None:
        client = self.make_client(EchoBackend())
        r = client.post(
            "/api/chat", json={"message": "hi"},
            headers={**HDR, "origin": "http://evil.example"},
        )
        assert r.status_code == 403

    def test_chat_roundtrip_and_session_continuity(self) -> None:
        client = self.make_client(EchoBackend())
        r1 = client.post("/api/chat", json={"message": "hello"}, headers=HDR)
        assert r1.status_code == 200
        sid = r1.json()["session_id"]
        assert r1.json()["transcript"][-1]["content"] == "echo: hello"
        r2 = client.post(
            "/api/chat", json={"session_id": sid, "message": "again"}, headers=HDR
        )
        hist = client.get(f"/api/sessions/{sid}").json()["history"]
        assert [h["content"] for h in hist if h["role"] == "user"] == ["hello", "again"]

    def test_bad_session_id_rejected(self) -> None:
        client = self.make_client(EchoBackend())
        r = client.post(
            "/api/chat", json={"session_id": "../etc", "message": "hi"}, headers=HDR
        )
        assert r.status_code == 422

    def test_health_reports_backend_and_tools(self) -> None:
        client = self.make_client(EchoBackend())
        body = client.get("/api/health").json()
        assert body["backend"] == "echo"
        assert "dispatch_task" in body["tools"]
        assert body["default_backend"] == "traditional"
        assert body["backends"]["traditional"]["available"] is True

    def test_ready_accepts_configured_process_backend(self) -> None:
        client = self.make_client(EchoBackend())
        body = client.get("/api/ready").json()
        assert body["status"] == "ready"
        assert body["backend"] == "echo"

    def test_placeholder_openai_backend_is_not_ready(self) -> None:
        backend = OpenAIBackend(
            base_url="http://127.0.0.1:8000",
            model="replace-with-your-model-id",
        )
        client = self.make_client(backend)
        assert client.get("/api/health").json()["backends"]["traditional"]["available"] is False
        response = client.get("/api/ready")
        assert response.status_code == 503
        assert "non-placeholder" in response.json()["detail"]["reason"]

    def test_non_loopback_chat_requires_token(self) -> None:
        with pytest.raises(RuntimeError, match="without its write token"):
            _require_write_token("0.0.0.0", None, "IC Chat")
        _require_write_token("0.0.0.0", "secret", "IC Chat")
        _require_write_token("127.0.0.1", None, "IC Chat")

    def test_backend_is_selected_once_and_persisted_per_session(self) -> None:
        openclaw = ScriptBackend([
            {"content": "openclaw reply", "tool_calls": []},
        ])
        client = self.make_client(EchoBackend(), openclaw_backend=openclaw)

        created = client.post(
            "/api/chat",
            json={"message": "hello", "backend": "openclaw"},
            headers=HDR,
        )
        assert created.status_code == 200
        sid = created.json()["session_id"]
        assert created.json()["transcript"][-1]["content"] == "openclaw reply"
        saved = client.get(f"/api/sessions/{sid}").json()
        assert saved["backend"] == "openclaw"
        listed = client.get("/api/sessions").json()["sessions"]
        assert listed[0]["backend"] == "openclaw"

        switched = client.post(
            "/api/chat",
            json={"session_id": sid, "message": "switch", "backend": "traditional"},
            headers=HDR,
        )
        assert switched.status_code == 409
        assert "start a new chat" in switched.text

    def test_openclaw_native_harness_owns_tools_and_persists_events(self) -> None:
        native = NativeHarnessBackend()
        client = self.make_client(EchoBackend(), openclaw_backend=native)
        health = client.get("/api/health").json()["backends"]["openclaw"]
        assert health["transport"] == "typed-gateway"
        assert health["tool_owner"] == "openclaw-mcp"

        response = client.post(
            "/api/chat",
            json={"message": "inspect the floor", "backend": "openclaw"},
            headers=HDR,
        )
        assert response.status_code == 200
        transcript = response.json()["transcript"]
        assert [event["role"] for event in transcript] == ["tool", "assistant"]
        assert transcript[0]["result"]["harness_tool"] == "ic-floor__floor_state"
        assert transcript[1]["content"] == "Native OpenClaw reply."
        assert native.seen[0][0][-1]["content"] == "inspect the floor"

        saved = client.get(f"/api/sessions/{response.json()['session_id']}").json()
        tool = next(item for item in saved["history"] if item["role"] == "tool")
        assert tool["result"]["harness"] == "openclaw"
        assert tool["result"]["harness_tool"] == "ic-floor__floor_state"

    def test_stop_idle_session_is_safe(self) -> None:
        client = self.make_client(EchoBackend())
        created = client.post("/api/chat", json={"message": "hello"}, headers=HDR)
        sid = created.json()["session_id"]
        stopped = client.post(f"/api/sessions/{sid}/stop", headers=HDR)
        assert stopped.status_code == 200
        assert stopped.json()["accepted"] is False
        assert stopped.json()["status"] == "idle"

    def test_tool_contract_is_vlm_first_and_visually_verifies_every_action(self) -> None:
        from ic_chat.toolloop import SYSTEM_PROMPT, TOOLS

        tools = {t["name"]: t for t in TOOLS}
        assert tools["reset_scene"]["parameters"]["additionalProperties"] is False
        assert "explicitly asks" in tools["reset_scene"]["description"]
        assert "conveyor_2" in tools["perceive"]["description"]
        assert "fresh camera frame" in tools["check_predicate"]["description"]
        assert "After EVERY dispatch" in SYSTEM_PROMPT
        assert "do not substitute" in SYSTEM_PROMPT
        assert "A vague whole-cell request" in SYSTEM_PROMPT
        assert "'table' means the complete two-arm work surface" in SYSTEM_PROMPT
        assert "'if there are blocks on the table' is satisfied" in SYSTEM_PROMPT
        assert "franka_right green from conveyor_2" in SYSTEM_PROMPT
        assert "franka_left green from conveyor_1" in SYSTEM_PROMPT
        assert "franka_right red from conveyor_2" in SYSTEM_PROMPT
        assert "franka_left red from conveyor_1" in SYSTEM_PROMPT
        assert "franka_right blue from conveyor_2" in SYSTEM_PROMPT
        assert "franka_left blue from conveyor_1" in SYSTEM_PROMPT
        assert "Never group all colors on one arm" in SYSTEM_PROMPT
        assert "gateway injects backend='groot'" in SYSTEM_PROMPT
        assert "never call the green brick a cube" in SYSTEM_PROMPT
        assert "pick_and_place tote_r onto rack_1" in SYSTEM_PROMPT
        assert "those rack flags take precedence" in SYSTEM_PROMPT
        assert "Never dispatch an arm move after both rack flags" in SYSTEM_PROMPT

    def test_sessions_are_capped(self, tmp_path) -> None:
        client = self.make_client(EchoBackend(), tmp_path=tmp_path, max_sessions=3)
        ids = []
        for i in range(6):
            r = client.post("/api/chat", json={"message": f"m{i}"}, headers=HDR)
            ids.append(r.json()["session_id"])
        assert client.get(f"/api/sessions/{ids[0]}").status_code == 404  # evicted
        assert client.get(f"/api/sessions/{ids[-1]}").status_code == 200

    def test_history_is_trimmed(self, tmp_path) -> None:
        client = self.make_client(EchoBackend(), tmp_path=tmp_path, max_history=4)
        sid = client.post("/api/chat", json={"message": "1"}, headers=HDR).json()["session_id"]
        for i in range(2, 8):
            client.post("/api/chat", json={"session_id": sid, "message": str(i)}, headers=HDR)
        hist = client.get(f"/api/sessions/{sid}").json()["history"]
        assert len(hist) <= 4

    def test_sessions_list_and_title(self, tmp_path) -> None:
        client = self.make_client(EchoBackend(), tmp_path=tmp_path)
        client.post("/api/chat", json={"message": "move the red cube please"}, headers=HDR)
        lst = client.get("/api/sessions").json()["sessions"]
        assert len(lst) == 1
        assert lst[0]["title"].startswith("move the red cube")  # titled from 1st msg
        assert lst[0]["messages"] >= 1
        assert lst[0]["mission_id"] == f"chat-{lst[0]['id']}"
        assert lst[0]["created"] > 0
        assert lst[0]["updated"] >= lst[0]["created"]
        assert lst[0]["active"] is False

        detail = client.get(f"/api/sessions/{lst[0]['id']}").json()
        assert detail["created"] == lst[0]["created"]
        assert detail["updated"] == lst[0]["updated"]
        assert detail["active"] is False

    def test_sessions_persist_across_new_store(self, tmp_path) -> None:
        # history survives a "restart" — a fresh store over the same dir sees it
        c1 = self.make_client(EchoBackend(), tmp_path=tmp_path)
        sid = c1.post("/api/chat", json={"message": "remember me"}, headers=HDR).json()["session_id"]
        c2 = self.make_client(EchoBackend(), tmp_path=tmp_path)  # new store, same dir
        hist = c2.get(f"/api/sessions/{sid}").json()["history"]
        assert any(h["content"] == "remember me" for h in hist)

    def test_delete_session_requires_csrf_and_works(self, tmp_path) -> None:
        client = self.make_client(EchoBackend(), tmp_path=tmp_path)
        sid = client.post("/api/chat", json={"message": "x"}, headers=HDR).json()["session_id"]
        assert client.delete(f"/api/sessions/{sid}").status_code == 403  # no header
        assert client.delete(f"/api/sessions/{sid}", headers=HDR).json()["deleted"] is True
        assert client.get(f"/api/sessions/{sid}").status_code == 404

    def test_delete_bad_id_rejected(self, tmp_path) -> None:
        client = self.make_client(EchoBackend(), tmp_path=tmp_path)
        assert client.delete("/api/sessions/..%2fetc", headers=HDR).status_code in (403, 404, 422)


class TestDefaultBackend:
    async def test_move_gets_default_backend_when_env_set(self, monkeypatch):
        from ic_chat.toolloop import ToolLoop

        monkeypatch.setenv("IC_DEFAULT_BACKEND", "groot")
        seen = {}
        loop = ToolLoop()

        async def fake_seam(name, args, mission_id):
            seen.update(args)
            return {"ok": True}

        loop._seam = fake_seam
        await loop.execute_tool("dispatch_task", {"action": "move", "color": "red"}, "m1")
        assert seen.get("backend") == "groot"

    async def test_groot_default_is_authoritative_and_non_move_untouched(self, monkeypatch):
        from ic_chat.toolloop import ToolLoop

        monkeypatch.setenv("IC_DEFAULT_BACKEND", "groot")
        loop = ToolLoop()
        calls = []

        async def fake_seam(name, args, mission_id):
            calls.append(dict(args))
            return {"ok": True}

        loop._seam = fake_seam
        await loop.execute_tool("dispatch_task", {"action": "move", "backend": None}, "m1")
        await loop.execute_tool(
            "dispatch_task",
            {"action": "pick_and_place", "object_id": "tote"},
            "m2",
        )
        assert calls[0]["backend"] == "groot"
        assert "backend" not in calls[1]  # non-move untouched

    async def test_groot_default_overrides_explicit_scripted(self, monkeypatch):
        from ic_chat.toolloop import ToolLoop

        monkeypatch.setenv("IC_DEFAULT_BACKEND", "groot")
        loop = ToolLoop()
        seen = {}

        async def fake_seam(name, args, mission_id):
            seen.update(args)
            return {"dispatched": True, "verified": True}

        loop._seam = fake_seam
        await loop.execute_tool(
            "dispatch_task",
            {"action": "move", "color": "green", "backend": "scripted"},
            "m-scripted",
        )
        assert seen["backend"] == "groot"

    async def test_canonical_demo_moves_get_groot_default(self, monkeypatch):
        from ic_chat.toolloop import ToolLoop

        monkeypatch.setenv("IC_DEFAULT_BACKEND", "groot")
        loop = ToolLoop()
        calls = []

        async def fake_seam(name, args, mission_id):
            calls.append(dict(args))
            return {"dispatched": True, "verified": True}

        loop._seam = fake_seam
        await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_left",
                "color": "red",
                "source": "conveyor_1",
                "destination": "tote",
            },
            "canonical-left",
        )
        await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_right",
                "color": "blue",
                "source": "conveyor_2",
                "destination": "tote_r",
            },
            "canonical-right",
        )
        assert all(call.get("backend") == "groot" for call in calls)
        assert calls[0]["destination"] == "tote_red"
        assert calls[1]["destination"] == "tote_blue"

    async def test_explicit_groot_still_wins_for_canonical_demo_move(self, monkeypatch):
        from ic_chat.toolloop import ToolLoop

        monkeypatch.setenv("IC_DEFAULT_BACKEND", "groot")
        loop = ToolLoop()
        seen = {}

        async def fake_seam(name, args, mission_id):
            seen.update(args)
            return {"dispatched": True, "verified": True}

        loop._seam = fake_seam
        await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_left",
                "color": "red",
                "source": "conveyor_1",
                "destination": "tote",
                "backend": "groot",
            },
            "explicit-groot",
        )
        assert seen["backend"] == "groot"
        assert seen["destination"] == "tote_red"

    async def test_groot_refuses_mismatched_color_pad_before_seam(self, monkeypatch):
        from ic_chat.toolloop import ToolLoop

        monkeypatch.setenv("IC_DEFAULT_BACKEND", "groot")
        loop = ToolLoop()
        called = False

        async def fake_seam(name, args, mission_id):
            nonlocal called
            called = True
            return {"dispatched": True, "verified": True}

        loop._seam = fake_seam
        out = await loop.execute_tool(
            "dispatch_task",
            {
                "action": "move",
                "endpoint": "franka_left",
                "color": "red",
                "source": "conveyor_1",
                "destination": "tote_blue",
            },
            "mismatched-pad",
        )
        assert called is False
        assert out["status"] == "refused"
        assert "expected tote_red" in out["reason"]

    async def test_uncertain_dispatch_timeout_closes_retry_gate(self, monkeypatch):
        from ic_chat.toolloop import ToolLoop

        monkeypatch.setenv("IC_DEFAULT_BACKEND", "groot")
        loop = ToolLoop()

        async def fake_seam(name, args, mission_id):
            return {
                "error": "ReadTimeout",
                "transport_error": True,
                "delivery_uncertain": True,
            }

        loop._seam = fake_seam
        args = {
            "action": "move",
            "endpoint": "franka_left",
            "color": "red",
            "source": "conveyor_1",
            "destination": "tote",
        }
        out = await loop.execute_tool("dispatch_task", args, "timeout-gate")
        assert out["verified"] is False
        assert out["proof_gate"]["state"] == "awaiting_reconciliation"
        blocked = await loop.execute_tool(
            "dispatch_task", args, "timeout-gate"
        )
        assert blocked["status"] == "refused"
        assert "fresh VLM verification" in blocked["error"]
