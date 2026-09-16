# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Chat → Spine → retained MCP reset regression, with no hardware or network.

Run with the three packages installed; package validation also runs this file
against their wheels. Only transports and the ROS backend are replaced.
"""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import logging
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
from fastapi.testclient import TestClient
from pgfr_chat.app import build_app as build_chat_app
from pgfr_chat.backends import EchoBackend
from pgfr_chat.sessions import SessionStore
from pgfr_chat.toolloop import ToolLoop
from pgfr_mcp import server as mcp_source
from policy_gated_factory_robot_orchestrator_reference.floor import service


class NoModel(EchoBackend):
    native_tool_owner = True
    configured = True

    async def respond(self, *args, **kwargs):
        raise AssertionError("Reset Scene must not call a model")

    async def run_native_stream(self, *args, **kwargs):
        raise AssertionError("Reset Scene must not call the OpenClaw Gateway")
        yield


class ResetSceneSyncTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for logger in ("httpx", service.log.name):
            self.stack.enter_context(patch.object(logging.getLogger(logger), "disabled", True))
        temporary = self.stack.enter_context(tempfile.TemporaryDirectory(prefix="pgfr-reset-sync-"))
        self.stack.enter_context(patch.dict(os.environ, {
            "PGFR_FLOOR_SERVICE": "http://pgfr-floor.test",
            "PGFR_FLOOR_POLICY": "",
            "PGFR_JOURNAL_DIR": str(Path(temporary) / "journal"),
            "PGFR_CERTIFIED_GROOT_ORDER": "1",
            "PGFR_GROOT_PARALLEL_ENABLED": "0",
            "PGFR_GROOT_FLEXIBLE_ORDER": "0",
            "PGFR_DEFAULT_BACKEND": "groot",
            "PGFR_MCP_ROLE": "agent",
            "PGFR_CHAT_TOKEN": "reset-sync-test",
            "PGFR_CHAT_CORS": "http://127.0.0.1:8600",
        }))
        self.floor = {"tote": {}, "tote_r": {}}
        self.dispatches = []
        self.reset_result = {"dispatched": True, "verified": True}
        self.stack.enter_context(patch.object(service, "load_backend", return_value=SimpleNamespace()))
        self.stack.enter_context(patch.object(service.ros2, "is_live_backend", return_value=True))
        self.stack.enter_context(patch.object(
            service.ros2, "live_floor_state", side_effect=lambda _: copy.deepcopy(self.floor),
        ))
        self.stack.enter_context(patch.object(
            service.ros2, "live_dispatch", side_effect=self._dispatch,
        ))
        self.spine = self.stack.enter_context(TestClient(service.build_app()))
        store = SessionStore(str(Path(temporary) / "sessions"))
        self.chat = self.stack.enter_context(TestClient(build_chat_app(
            backend=NoModel(), openclaw_backend=NoModel(),
            loop=ToolLoop(), sessions_store=store,
        )))
        self.store = store

        # Exercise each component's real URL, JSON and role-header construction.
        # Any unexpected destination fails here instead of opening a socket.
        async_client = httpx.AsyncClient
        self.stack.enter_context(patch.object(
            httpx, "AsyncClient",
            side_effect=lambda **kwargs: async_client(
                transport=httpx.MockTransport(self._httpx_transport), **kwargs,
            ),
        ))
        self.stack.enter_context(patch.object(urllib.request, "urlopen", self._urllib_transport))
        self.mcps = [self._load_mcp(index) for index in range(2)]

    def _load_mcp(self, index):
        # Separate module globals model two MCP processes retained by OpenClaw.
        name = f"pgfr_mcp._reset_sync_test_{index}"
        spec = importlib.util.spec_from_file_location(name, mcp_source.__file__)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        self.stack.enter_context(patch.dict(sys.modules, {name: module}))
        spec.loader.exec_module(module)
        return module

    async def _dispatch(self, backend, endpoint, action, args):
        self.dispatches.append((endpoint, action, copy.deepcopy(args)))
        if action == "reset_scene":
            if self.reset_result == {"dispatched": True, "verified": True}:
                self.floor = {"tote": {}, "tote_r": {}}
            return copy.deepcopy(self.reset_result)
        self.assertEqual(action, "move")
        self.assertEqual(args["backend"], "groot")
        tote = "tote_r" if endpoint == "franka_right" else "tote"
        self.floor[tote][args["color"]] = "in"
        return {"dispatched": True, "verified": True}

    def _request(self, method, url, content, headers):
        parsed = urlsplit(str(url))
        self.assertEqual((parsed.scheme, parsed.netloc), ("http", "pgfr-floor.test"))
        self.assertEqual(method, "POST")
        self.assertIn(parsed.path, ("/v1/floor-state", "/v1/dispatch"))
        payload = json.loads(content)
        headers = {key.lower(): value for key, value in headers.items()}
        if payload.get("action") == "reset_scene":
            self.assertEqual(headers["x-role"], "operator")
            self.assertEqual(headers["x-mission-id"], "chat-reset-sync")
        return self.spine.post(parsed.path, json=payload, headers=headers)

    def _httpx_transport(self, request):
        response = self._request(request.method, request.url, request.content, request.headers)
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    def _urllib_transport(self, request, timeout):
        response = self._request(
            request.get_method(), request.full_url, request.data, dict(request.header_items()),
        )
        if response.status_code >= 400:
            raise urllib.error.HTTPError(
                request.full_url, response.status_code, response.reason_phrase,
                response.headers, io.BytesIO(response.content),
            )
        return io.BytesIO(response.content)

    def _move(self, module, side="right"):
        return json.loads(module.dispatch_task(
            action="move", endpoint=f"franka_{side}", color="green",
            source="conveyor_2" if side == "right" else "conveyor_1",
            destination="tote_green",
        ))

    def _reset(self):
        response = self.chat.post(
            "/api/reset-scene", json={"session_id": "reset-sync", "backend": "openclaw"},
            headers={"x-pgfr-chat": "reset-sync-test"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.get("reset-sync")["backend"], "openclaw")
        return response.json()["result"]

    def _reset_id(self):
        return self.spine.post("/v1/floor-state", json={}).json()["_meta"]["scene_reset_id"]

    def test_verified_chat_reset_releases_both_retained_mcp_processes(self):
        self.assertIsNone(self._reset_id())
        for module, side in zip(self.mcps, ("right", "left"), strict=True):
            self.assertIs(self._move(module, side)["verified"], True)
            self.assertIsNotNone(module._PENDING_PROOF)

        previous_id = None
        for _ in range(2):
            result = self._reset()
            self.assertEqual(result["status"], "verified")
            reset_id = self._reset_id()
            self.assertTrue(reset_id)
            self.assertNotEqual(reset_id, previous_id)
            self.assertEqual(result["_meta"]["scene_reset_id"], reset_id)
            self.assertEqual(self.floor, {"tote": {}, "tote_r": {}})
            for module, side in zip(self.mcps, ("right", "left"), strict=True):
                # No MCP restart, native reset, or second physical reset.
                outcome = self._move(module, side)
                self.assertIs(outcome["verified"], True)
                self.assertEqual(outcome["pending_visual_proof"]["attempt"], 1)
                self.assertEqual(list(module._DISPATCH_ATTEMPTS.values()), [1])
            previous_id = reset_id
        self.assertEqual(
            [action for _, action, _ in self.dispatches],
            ["move", "move", "reset_scene", "move", "move", "reset_scene", "move", "move"],
        )

    def _assert_unverified_reset_preserves_pending(self, reset_result, expected_status):
        # Also cover a failed reset after an earlier verified reset generation.
        self.assertEqual(self._reset()["status"], "verified")
        reset_id = self._reset_id()
        module = self.mcps[0]
        self.assertIs(self._move(module)["verified"], True)
        pending = copy.deepcopy(module._PENDING_PROOF)
        attempts = copy.deepcopy(module._DISPATCH_ATTEMPTS)
        prefix = module._LAST_CERTIFIED_PREFIX
        self.reset_result = reset_result
        result = self._reset()
        self.assertEqual(result["status"], expected_status)
        self.assertIs(result["verified"], False)
        self.assertEqual(self._reset_id(), reset_id)
        dispatch_count = len(self.dispatches)
        outcome = self._move(module)
        self.assertEqual(outcome["status"], "refused")
        self.assertIn("fresh visual proof", outcome["reason"])
        self.assertEqual(module._PENDING_PROOF, pending)
        self.assertEqual(module._DISPATCH_ATTEMPTS, attempts)
        self.assertEqual(module._LAST_CERTIFIED_PREFIX, prefix)
        self.assertEqual(len(self.dispatches), dispatch_count)

    def test_failed_reset_preserves_pending(self):
        self._assert_unverified_reset_preserves_pending(
            {"dispatched": True, "verified": False, "reason": "reset verification failed"},
            "failed",
        )

    def test_refused_reset_preserves_pending(self):
        self._assert_unverified_reset_preserves_pending(
            {"dispatched": False, "verified": False, "status": "refused", "reason": "policy"},
            "refused",
        )

    def test_uncertain_reset_preserves_pending(self):
        self._assert_unverified_reset_preserves_pending(
            {"dispatched": True, "verified": True, "delivery_uncertain": True},
            "uncertain",
        )


if __name__ == "__main__":
    unittest.main()
