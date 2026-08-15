# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Hardware-free contract tests for the typed headless OpenClaw adapter."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from aiohttp import web

from ic_chat.openclaw_gateway import OpenClawGatewayClient, _tool_payload


def test_history_structured_content_promotes_vlm_frame_id() -> None:
    result = _tool_payload({
        "content": [{
            "type": "text",
            "text": (
                'structuredContent:\n{"result":"{\\"answer\\":\\"yes\\",'
                '\\"evidence\\":\\"green brick visible\\",'
                '\\"_meta\\":{\\"request_id\\":\\"frame-123\\"}}"}'
            ),
        }],
    })
    assert result["answer"] == "yes"
    assert result["evidence"] == "green brick visible"
    assert result["request_id"] == "frame-123"


def test_plaintext_remote_gateway_is_refused() -> None:
    with pytest.raises(ValueError, match="loopback"):
        OpenClawGatewayClient(
            ws_url="ws://10.0.0.5:18790",
            token="gateway-token",
        )


async def test_native_gateway_streams_mcp_tool_cards_and_final(aiohttp_server) -> None:
    seen: dict[str, Any] = {}

    async def gateway(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({
            "type": "event",
            "event": "connect.challenge",
            "payload": {"nonce": "challenge-1"},
        })
        connect = await ws.receive_json()
        seen["connect"] = connect
        await ws.send_json({
            "type": "res",
            "id": connect["id"],
            "ok": True,
            "payload": {
                "type": "hello-ok",
                "protocol": 4,
                "features": {
                    "methods": ["chat.send", "chat.abort", "chat.history"],
                    "events": ["chat", "agent"],
                },
            },
        })
        send = await ws.receive_json()
        seen["send"] = send
        run_id = send["params"]["idempotencyKey"]
        session_key = send["params"]["sessionKey"]
        await ws.send_json({
            "type": "res",
            "id": send["id"],
            "ok": True,
            "payload": {"status": "started", "runId": run_id},
        })
        await ws.send_json({
            "type": "event",
            "event": "agent",
            "payload": {
                "runId": run_id,
                "seq": 1,
                "stream": "tool",
                "ts": 1,
                "data": {
                    "phase": "start",
                    "toolCallId": "tool-1",
                    "name": "ic-floor__dispatch_task",
                    "args": {"action": "move", "color": "green"},
                },
            },
        })
        await ws.send_json({
            "type": "event",
            "event": "agent",
            "payload": {
                "runId": run_id,
                "seq": 2,
                "stream": "tool",
                "ts": 2,
                "data": {
                    "phase": "result",
                    "toolCallId": "tool-1",
                    "name": "ic-floor__dispatch_task",
                    "result": {
                        "content": [{
                            "type": "text",
                            "text": '{"dispatched":true,"verified":true}',
                        }],
                    },
                    "isError": False,
                },
            },
        })
        await ws.send_json({
            "type": "event",
            "event": "chat",
            "payload": {
                "runId": run_id,
                "sessionKey": session_key,
                "seq": 3,
                "state": "final",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Green move verified."}],
                },
            },
        })
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/", gateway)
    server = await aiohttp_server(app)
    client = OpenClawGatewayClient(
        ws_url=str(server.make_url("/")).replace("http://", "ws://"),
        token="gateway-token",
        timeout_s=5,
    )
    events = [event async for event in client.run_stream("sort green", "chat-native-1")]

    connect = seen["connect"]
    assert connect["method"] == "connect"
    assert connect["params"]["minProtocol"] == 4
    assert connect["params"]["maxProtocol"] == 4
    assert connect["params"]["caps"] == ["tool-events"]
    assert connect["params"]["scopes"] == ["operator.read", "operator.write"]
    assert connect["params"]["auth"] == {"token": "gateway-token"}
    assert seen["send"]["method"] == "chat.send"
    assert seen["send"]["params"]["sessionKey"] == (
        "agent:ic-console:ic-chat-chat-native-1"
    )
    assert seen["send"]["params"]["message"] == "sort green"
    assert events[0] == {
        "role": "tool_start",
        "name": "dispatch_task",
        "args": {"action": "move", "color": "green"},
    }
    assert events[1]["role"] == "tool"
    assert events[1]["name"] == "dispatch_task"
    assert events[1]["result"]["verified"] is True
    assert events[1]["result"]["harness"] == "openclaw"
    assert events[1]["result"]["harness_tool"] == "ic-floor__dispatch_task"
    assert events[2]["content"] == "Green move verified."


async def test_stop_uses_the_same_gateway_connection_that_owns_the_run(
    aiohttp_server,
) -> None:
    seen: dict[str, Any] = {"connections": 0}

    async def gateway(request: web.Request) -> web.WebSocketResponse:
        seen["connections"] += 1
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({
            "type": "event",
            "event": "connect.challenge",
            "payload": {"nonce": "challenge-stop"},
        })
        connect = await ws.receive_json()
        await ws.send_json({
            "type": "res",
            "id": connect["id"],
            "ok": True,
            "payload": {
                "type": "hello-ok",
                "protocol": 4,
                "features": {
                    "methods": ["chat.send", "chat.abort", "chat.history"],
                    "events": ["chat", "agent"],
                },
            },
        })
        send = await ws.receive_json()
        run_id = send["params"]["idempotencyKey"]
        session_key = send["params"]["sessionKey"]
        await ws.send_json({
            "type": "res",
            "id": send["id"],
            "ok": True,
            "payload": {"status": "started", "runId": run_id},
        })
        await ws.send_json({
            "type": "event",
            "event": "agent",
            "payload": {
                "runId": run_id,
                "stream": "tool",
                "data": {
                    "phase": "start",
                    "toolCallId": "tool-stop",
                    "name": "ic-floor__perceive",
                    "args": {"target": "table_1"},
                },
            },
        })
        abort = await ws.receive_json()
        seen["abort"] = abort
        # OpenClaw emits the terminal event before acknowledging chat.abort.
        await ws.send_json({
            "type": "event",
            "event": "chat",
            "payload": {
                "runId": run_id,
                "sessionKey": session_key,
                "state": "aborted",
            },
        })
        await ws.send_json({
            "type": "res",
            "id": abort["id"],
            "ok": True,
            "payload": {"ok": True, "aborted": True, "runIds": [run_id]},
        })
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/", gateway)
    server = await aiohttp_server(app)
    client = OpenClawGatewayClient(
        ws_url=str(server.make_url("/")).replace("http://", "ws://"),
        token="gateway-token",
        timeout_s=5,
    )
    stream = client.run_stream("sort blocks", "chat-stop-owner")
    started = await anext(stream)
    assert started["role"] == "tool_start"

    async def consume_tail() -> list[dict[str, Any]]:
        return [event async for event in stream]

    stop_task = asyncio.create_task(client.request_stop("chat-stop-owner"))
    tail_task = asyncio.create_task(consume_tail())
    stopped, tail = await asyncio.gather(stop_task, tail_task)

    assert seen["connections"] == 1
    assert seen["abort"]["method"] == "chat.abort"
    assert seen["abort"]["params"]["runId"].startswith("ic-chat-")
    assert stopped["accepted"] is True
    assert stopped["status"] == "stopping"
    assert any(event.get("error") == "OpenClaw run aborted" for event in tail)


async def test_redacted_live_result_is_recovered_from_official_history(
    aiohttp_server,
) -> None:
    seen_methods: list[str] = []

    async def gateway(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({
            "type": "event",
            "event": "connect.challenge",
            "payload": {"nonce": "challenge-history"},
        })
        connect = await ws.receive_json()
        await ws.send_json({
            "type": "res",
            "id": connect["id"],
            "ok": True,
            "payload": {
                "type": "hello-ok",
                "protocol": 4,
                "features": {
                    "methods": ["chat.send", "chat.abort", "chat.history"],
                    "events": ["chat", "agent"],
                },
            },
        })
        request_frame = await ws.receive_json()
        method = request_frame["method"]
        seen_methods.append(method)
        if method == "chat.history":
            await ws.send_json({
                "type": "res",
                "id": request_frame["id"],
                "ok": True,
                "payload": {
                    "messages": [{
                        "role": "toolResult",
                        "toolCallId": "tool-redacted",
                        "toolName": "ic-floor__verify",
                        "content": [{
                            "type": "text",
                            "text": (
                                'structuredContent:\n{"result":"{'
                                '\\"answer\\":\\"yes\\",'
                                '\\"evidence\\":\\"red cube visible\\",'
                                '\\"source_used\\":\\"inspect_cam\\",'
                                '\\"_meta\\":{\\"request_id\\":\\"req-vlm-1\\"}'
                                '}"}'
                            ),
                        }],
                        "isError": False,
                    }],
                },
            })
            await ws.close()
            return ws

        run_id = request_frame["params"]["idempotencyKey"]
        session_key = request_frame["params"]["sessionKey"]
        await ws.send_json({
            "type": "res",
            "id": request_frame["id"],
            "ok": True,
            "payload": {"status": "started", "runId": run_id},
        })
        await ws.send_json({
            "type": "event",
            "event": "agent",
            "payload": {
                "runId": run_id,
                "stream": "tool",
                "data": {
                    "phase": "start",
                    "toolCallId": "tool-redacted",
                    "name": "ic-floor__verify",
                    "args": {"predicate": "red cube in tote", "region": "tote"},
                },
            },
        })
        await ws.send_json({
            "type": "event",
            "event": "agent",
            "payload": {
                "runId": run_id,
                "stream": "tool",
                "data": {
                    "phase": "result",
                    "toolCallId": "tool-redacted",
                    "name": "ic-floor__verify",
                    "isError": False,
                },
            },
        })
        await ws.send_json({
            "type": "event",
            "event": "chat",
            "payload": {
                "runId": run_id,
                "sessionKey": session_key,
                "state": "final",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Verified."}],
                },
            },
        })
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/", gateway)
    server = await aiohttp_server(app)
    client = OpenClawGatewayClient(
        ws_url=str(server.make_url("/")).replace("http://", "ws://"),
        token="gateway-token",
        timeout_s=5,
    )
    events = [event async for event in client.run_stream("verify", "chat-history-1")]

    tool = next(event for event in events if event.get("role") == "tool")
    assert tool["name"] == "verify"
    assert tool["result"]["answer"] == "yes"
    assert tool["result"]["evidence"] == "red cube visible"
    assert tool["result"]["source_used"] == "inspect_cam"
    assert tool["result"]["request_id"] == "req-vlm-1"
    assert tool["result"]["harness"] == "openclaw"
    assert seen_methods.count("chat.send") == 1
    assert seen_methods.count("chat.history") == 1


async def test_protocol_mismatch_fails_closed(aiohttp_server) -> None:
    async def gateway(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({
            "type": "event",
            "event": "connect.challenge",
            "payload": {"nonce": "challenge-2"},
        })
        connect = await ws.receive_json()
        await ws.send_json({
            "type": "res",
            "id": connect["id"],
            "ok": True,
            "payload": {
                "type": "hello-ok",
                "protocol": 5,
                "features": {"methods": ["chat.send", "chat.abort"], "events": []},
            },
        })
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/", gateway)
    server = await aiohttp_server(app)
    client = OpenClawGatewayClient(
        ws_url=str(server.make_url("/")).replace("http://", "ws://"),
        token="gateway-token",
        timeout_s=5,
    )
    with pytest.raises(RuntimeError, match="protocol mismatch"):
        _ = [event async for event in client.run_stream("hello", "chat-mismatch")]
