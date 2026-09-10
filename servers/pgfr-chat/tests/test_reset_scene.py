# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Operator reset API: no model, one guarded dispatch, truthful persisted results."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from aiohttp import web
from fastapi.testclient import TestClient

from pgfr_chat.app import build_app
from pgfr_chat.backends import EchoBackend
from pgfr_chat.sessions import SessionStore
from pgfr_chat.toolloop import ToolLoop

HDR = {"x-pgfr-chat": "console"}
VERIFIED = {"dispatched": True, "verified": True, "request_id": "reset-evidence"}


class UnavailableBackend(EchoBackend):
    configured = False

    async def respond(self, messages, tools):
        raise AssertionError("the reset control must not call a model")


@pytest.fixture
def reset_api(tmp_path, monkeypatch):
    monkeypatch.delenv("PGFR_CHAT_TOKEN", raising=False)
    monkeypatch.setenv("PGFR_CHAT_CORS", "http://127.0.0.1:8600")
    loop = ToolLoop()
    seam = AsyncMock(return_value=VERIFIED)
    monkeypatch.setattr(loop, "_seam", seam)
    store = SessionStore(str(tmp_path))
    app = build_app(
        backend=UnavailableBackend(), openclaw_backend=UnavailableBackend(),
        loop=loop, sessions_store=store,
    )
    return app, loop, store, seam


@pytest.mark.parametrize("headers", [
    {},
    {**HDR, "origin": "http://evil.example"},
])
def test_reset_rejects_csrf_before_dispatch(reset_api, headers):
    app, _, store, seam = reset_api
    response = TestClient(app).post("/api/reset-scene", json={}, headers=headers)
    assert response.status_code == 403
    seam.assert_not_awaited()
    assert store.list() == []


def test_reset_enforces_configured_write_token(reset_api, monkeypatch):
    _, loop, store, seam = reset_api
    monkeypatch.setenv("PGFR_CHAT_TOKEN", "operator-secret")
    app = build_app(backend=UnavailableBackend(), loop=loop, sessions_store=store)
    client = TestClient(app)
    assert client.post("/api/reset-scene", json={}, headers=HDR).status_code == 403
    seam.assert_not_awaited()
    response = client.post(
        "/api/reset-scene", json={},
        headers={"x-pgfr-chat": "operator-secret", "origin": "http://127.0.0.1:8600"},
    )
    assert response.status_code == 200
    seam.assert_awaited_once()


@pytest.mark.parametrize("body", [
    {"session_id": "../bad"},
    {"session_id": "bad\n"},
    {"session_id": "x" * 65},
    {"backend": "unknown"},
    {"action": "arbitrary-floor-action"},
    {"scene_profile": "unapproved-profile"},
])
def test_reset_rejects_invalid_request(reset_api, body):
    app, _, _, seam = reset_api
    assert TestClient(app).post("/api/reset-scene", json=body, headers=HDR).status_code == 422
    seam.assert_not_awaited()


def test_reset_uses_fixed_tool_without_model_and_persists_selected_backend(reset_api):
    app, _, store, seam = reset_api
    client = TestClient(app)
    health = client.get("/api/health").json()
    assert health["actions"]["reset_scene"] is True
    assert health["backends"]["openclaw"]["available"] is False
    response = client.post(
        "/api/reset-scene", json={"session_id": "operator", "backend": "openclaw"},
        headers=HDR,
    )
    assert response.status_code == 200
    out = response.json()
    assert out["session_id"] == "operator"
    assert out["mission_id"] == "chat-operator"
    seam.assert_awaited_once_with("reset_scene", {}, "chat-operator")
    assert out["result"] == {**VERIFIED, "status": "verified"}
    assert out["transcript"][0] == {
        "role": "tool", "name": "reset_scene", "args": {}, "result": out["result"],
    }
    saved = store.get("operator")
    assert saved["backend"] == "openclaw"
    assert saved["history"] == [
        {"role": "user", "content": "Reset the Isaac Sim scene."}, *out["transcript"],
    ]
    switched = client.post(
        "/api/reset-scene", json={"session_id": "operator", "backend": "traditional"},
        headers=HDR,
    )
    assert switched.status_code == 409
    seam.assert_awaited_once()


@pytest.mark.parametrize(("raw", "status"), [
    (VERIFIED, "verified"),
    ({"dispatched": False, "verified": False, "status": "refused", "reason": "policy"},
     "refused"),
    ({"dispatched": True, "verified": False, "reason": "reset verification failed"},
     "failed"),
    ({"transport_error": True, "delivery_uncertain": False, "error": "ConnectError"},
     "failed"),
    ({"transport_error": True, "delivery_uncertain": True, "error": "ReadTimeout"},
     "uncertain"),
    ({"verified": True}, "uncertain"),
    ({}, "uncertain"),
    ({**VERIFIED, "dispatched": False, "status": "refused"}, "refused"),
    ({**VERIFIED, "status": "refused"}, "refused"),
    ({**VERIFIED, "delivery_uncertain": True}, "uncertain"),
    ({**VERIFIED, "error": "malformed confirmation"}, "failed"),
    ({**VERIFIED, "status": "failed"}, "failed"),
    ({**VERIFIED, "transport_error": True}, "uncertain"),
])
def test_reset_outcomes_are_truthful_and_only_success_clears_guards(reset_api, raw, status):
    app, loop, store, seam = reset_api
    seam.return_value = raw
    mission = "chat-outcome"
    loop._visual_proof_pending[mission] = {"request_id": "previous-move"}
    loop._mission_failure[mission] = {"reason": "previous failure"}
    loop._stop_requested.add(mission)
    response = TestClient(app).post(
        "/api/reset-scene", json={"session_id": "outcome"}, headers=HDR,
    )
    assert response.status_code == 200
    out = response.json()
    assert out["result"]["status"] == status
    assert out["result"]["verified"] is (status == "verified")
    seam.assert_awaited_once()
    assert (mission in loop._visual_proof_pending) is (status != "verified")
    assert (mission in loop._mission_failure) is (status != "verified")
    assert (mission in loop._stop_requested) is (status != "verified")
    assert store.get("outcome")["history"][-2:] == out["transcript"]



@pytest.mark.parametrize("reason", [
    "scene reset verification failed after actuation",
    "policy: action 'reset_scene' is operator-only (send x-role: operator)",
])
def test_spine_unsuccessful_reset_is_not_assumed_to_be_refused(reset_api, reason):
    app, loop, store, seam = reset_api
    # live_dispatch maps ActionAgent.success to dispatched, including when
    # an endpoint executed the reset but could not verify its final state.
    seam.return_value = {
        "dispatched": False,
        "endpoint": "mobilebot",
        "action": "reset_scene",
        "verified": False,
        "moved": {
            "color": "red", "scene_profile": "groot_three_object", "arm": "both",
            "layout_left": 3, "layout_right": 3, "seed": 31302,
        },
        "reason": reason,
    }
    loop._visual_proof_pending["chat-attempted"] = {"request_id": "previous-move"}
    response = TestClient(app).post(
        "/api/reset-scene", json={"session_id": "attempted"}, headers=HDR,
    )
    assert response.status_code == 200
    out = response.json()
    assert out["result"]["status"] == "failed"
    assert out["result"]["verified"] is False
    assert out["result"]["reason"] == reason
    assert "not verified" in out["transcript"][-1]["content"]
    assert "Inspect Isaac Sim" in out["transcript"][-1]["content"]
    assert "refused" not in out["transcript"][-1]["content"]
    assert "chat-attempted" in loop._visual_proof_pending
    assert store.get("attempted")["history"][-2:] == out["transcript"]
    seam.assert_awaited_once()


def test_dispatched_false_without_verification_leaves_reset_outcome_unknown(reset_api):
    app, _, store, seam = reset_api
    seam.return_value = {"dispatched": False}
    response = TestClient(app).post("/api/reset-scene", json={}, headers=HDR)
    assert response.status_code == 200
    out = response.json()
    assert out["result"]["status"] == "uncertain"
    assert out["result"]["delivery_uncertain"] is True
    assert "did not confirm" in out["transcript"][-1]["content"]
    assert store.get(out["session_id"])["history"][-2:] == out["transcript"]
    seam.assert_awaited_once()

def test_reset_exception_is_persisted_as_uncertain_without_retry(reset_api):
    app, _, store, seam = reset_api
    seam.side_effect = RuntimeError("lost response after possible delivery")
    response = TestClient(app).post("/api/reset-scene", json={}, headers=HDR)
    out = response.json()
    assert out["result"]["status"] == "uncertain"
    assert out["result"]["delivery_uncertain"] is True
    assert "No retry was sent" in out["transcript"][-1]["content"]
    assert store.get(out["session_id"])["history"][-2:] == out["transcript"]
    seam.assert_awaited_once()


@pytest.mark.parametrize("chat_route", ["/api/chat", "/api/chat/stream"])
@pytest.mark.parametrize("reset_session", ["busy", "other"])
async def test_reset_refuses_any_active_chat(reset_api, chat_route, reset_session):
    _, loop, store, seam = reset_api
    started, release = asyncio.Event(), asyncio.Event()

    class BusyBackend(EchoBackend):
        async def respond(self, messages, tools):
            started.set()
            await release.wait()
            return {"content": "done", "tool_calls": []}

    app = build_app(backend=BusyBackend(), loop=loop, sessions_store=store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        running = asyncio.create_task(client.post(
            chat_route, json={"session_id": "busy", "message": "inspect"}, headers=HDR,
        ))
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            detail = (await client.get("/api/sessions/busy")).json()
            assert detail["active"] is True
            response = await client.post(
                "/api/reset-scene", json={"session_id": reset_session}, headers=HDR,
            )
            assert response.status_code == 409
            seam.assert_not_awaited()
            # A second turn on the same session cannot replace its active flag.
            duplicate = await client.post(
                chat_route, json={"session_id": "busy", "message": "again"}, headers=HDR,
            )
            assert duplicate.status_code == 409
        finally:
            release.set()
            assert (await running).status_code == 200
        assert (await client.post("/api/reset-scene", json={}, headers=HDR)).status_code == 200
        seam.assert_awaited_once()


async def test_reset_reserves_scene_against_other_resets_chat_and_deletion(reset_api):
    app, _, store, seam = reset_api
    started, release = asyncio.Event(), asyncio.Event()

    async def pending_reset(*args):
        started.set()
        await release.wait()
        return VERIFIED

    seam.side_effect = pending_reset
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        running = asyncio.create_task(client.post(
            "/api/reset-scene", json={"session_id": "resetting"}, headers=HDR,
        ))
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            for sid in ("resetting", "other"):
                assert (await client.post(
                    "/api/reset-scene", json={"session_id": sid}, headers=HDR,
                )).status_code == 409
                for route in ("/api/chat", "/api/chat/stream"):
                    assert (await client.post(
                        route, json={"session_id": sid, "message": "go"}, headers=HDR,
                    )).status_code == 409
            assert (await client.delete("/api/sessions/resetting", headers=HDR)).status_code == 409
            assert store.get("resetting")["history"] == [
                {"role": "user", "content": "Reset the Isaac Sim scene."},
            ]
            assert store.get("other") is None
        finally:
            release.set()
            assert (await running).status_code == 200
        seam.assert_awaited_once()
        assert (await client.delete("/api/sessions/resetting", headers=HDR)).status_code == 200


async def test_cancelled_reset_records_uncertainty_and_releases_reservation(reset_api):
    app, _, store, seam = reset_api
    started = asyncio.Event()

    async def pending_reset(*args):
        started.set()
        await asyncio.Event().wait()

    seam.side_effect = pending_reset
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        running = asyncio.create_task(client.post(
            "/api/reset-scene", json={"session_id": "interrupted"}, headers=HDR,
        ))
        await asyncio.wait_for(started.wait(), timeout=2)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert store.get("interrupted")["history"][-2]["result"]["status"] == "uncertain"
        seam.assert_awaited_once()
        assert (await client.delete("/api/sessions/interrupted", headers=HDR)).status_code == 200


@pytest.mark.parametrize(("http_status", "raw", "expected_status"), [
    (500, VERIFIED, "uncertain"),
    (302, VERIFIED, "uncertain"),
    (403, {"dispatched": False, "verified": True, "status": "refused"}, "refused"),
])
async def test_non_success_http_response_cannot_verify_reset(
    tmp_path, aiohttp_server, http_status, raw, expected_status,
):
    calls = []

    async def dispatch(request):
        calls.append({
            "body": await request.json(),
            "role": request.headers.get("x-role"),
            "mission": request.headers.get("x-mission-id"),
        })
        return web.json_response(raw, status=http_status)

    seam = web.Application()
    seam.router.add_post("/v1/dispatch", dispatch)
    server = await aiohttp_server(seam)
    loop = ToolLoop()
    loop.settings.seam_url = str(server.make_url("")).rstrip("/")
    loop._mission_failure["chat-http-error"] = {"reason": "unverified motion"}
    app = build_app(
        backend=UnavailableBackend(), loop=loop, sessions_store=SessionStore(str(tmp_path)),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/reset-scene", json={"session_id": "http-error"}, headers=HDR,
        )
    assert response.json()["result"]["status"] == expected_status
    assert response.json()["result"]["verified"] is False
    assert "chat-http-error" in loop._mission_failure
    assert len(calls) == 1
    assert calls[0] == {
        "body": {
            "endpoint": "mobilebot", "action": "reset_scene",
            "scene_profile": "groot_three_object", "arm": "both", "color": "red",
            "layout_left": 3, "layout_right": 3, "seed": 31302,
        },
        "role": "operator", "mission": "chat-http-error",
    }
