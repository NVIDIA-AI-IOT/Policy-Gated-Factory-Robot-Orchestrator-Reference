# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the IC console aggregator + API.

Hardware-free: a fake seam (FastAPI TestClient-style httpx MockTransport is
not used because the aggregator owns its client; instead we run a real
in-process HTTP server via uvicorn-free asyncio) — simplest robust approach:
monkeypatch the aggregator's HTTP layer with canned responses.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
import pytest
from fastapi.testclient import TestClient

from ic_console.aggregator import Aggregator, Settings
from ic_console.app import build_app


class CannedHTTP:
    """Stands in for Aggregator._get_json with canned per-URL payloads."""

    def __init__(self, payloads: Dict[str, Optional[Dict[str, Any]]]) -> None:
        self.payloads = payloads
        self.calls: list[str] = []

    async def __call__(
        self, client: httpx.AsyncClient, url: str
    ) -> Optional[Dict[str, Any]]:
        self.calls.append(url)
        for suffix, payload in self.payloads.items():
            if url.endswith(suffix) or suffix in url:
                return payload
        return None


def make_agg(payloads: Dict[str, Optional[Dict[str, Any]]], **env: str) -> Aggregator:
    settings = Settings()
    settings.vlm_url = env.get("vlm_url", "")
    settings.gym_url = env.get("gym_url", "")
    agg = Aggregator(settings)
    canned = CannedHTTP(payloads)
    agg._get_json = canned  # type: ignore[method-assign]
    agg._post_json = canned  # type: ignore[method-assign]
    return agg


HEALTHY = {
    "_http_status": 200,
    "status": "ok",
    "backend": "ros2",
    "ros_ok": True,
    "floor_state_age_s": 0.4,
    "camera_age_s": 0.2,
}


class TestAggregator:
    async def test_floor_state_poller_uses_post(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.method)
            return httpx.Response(200, json={"endpoints": []})

        agg = Aggregator(Settings())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await agg._post_json(client, "http://seam/v1/floor-state")

        assert seen == ["POST"]
        assert result == {"endpoints": [], "_http_status": 200}

    async def test_healthy_seam_lights_up_the_chain(self) -> None:
        agg = make_agg({"/v1/health": HEALTHY})
        snap = await agg.poll_once()
        nodes = {n.id: n for n in snap["nodes"]}
        assert nodes["seam"].status == "ok"
        assert nodes["floor"].status == "ok"
        assert nodes["cell"].status == "ok"
        assert nodes["journal"].status == "ok"

    async def test_degraded_health_maps_to_degraded(self) -> None:
        degraded = dict(HEALTHY, _http_status=503, status="degraded", ros_ok=False)
        agg = make_agg({"/v1/health": degraded})
        snap = await agg.poll_once()
        nodes = {n.id: n for n in snap["nodes"]}
        assert nodes["seam"].status == "degraded"
        assert nodes["cell"].status == "down"

    async def test_unreachable_seam_is_down_never_ok(self) -> None:
        agg = make_agg({})
        snap = await agg.poll_once()
        nodes = {n.id: n for n in snap["nodes"]}
        assert nodes["seam"].status == "down"
        assert nodes["cell"].status == "unknown"

    async def test_mock_backend_marks_cell_unknown(self) -> None:
        mock_health = dict(HEALTHY, backend="mock")
        agg = make_agg({"/v1/health": mock_health})
        snap = await agg.poll_once()
        nodes = {n.id: n for n in snap["nodes"]}
        assert nodes["cell"].status == "unknown"
        assert "mock" in str(nodes["cell"].detail)

    async def test_stale_floor_state_degrades_cell(self) -> None:
        stale = dict(HEALTHY, floor_state_age_s=42.0)
        agg = make_agg({"/v1/health": stale})
        snap = await agg.poll_once()
        nodes = {n.id: n for n in snap["nodes"]}
        assert nodes["cell"].status == "degraded"

    async def test_stale_camera_degrades_independently_of_cell(self) -> None:
        # A camera must degrade LOUDLY on its own freshness, not show green just
        # because the cell is ok — its frames are the VLM's evidence.
        stale = dict(HEALTHY, camera_age_s=12.0)
        agg = make_agg({"/v1/health": stale})
        nodes = {n.id: n for n in (await agg.poll_once())["nodes"]}
        assert nodes["cell"].status == "ok"           # cell itself is fresh
        assert nodes["cam_outside"].status == "degraded"

        very_stale = dict(HEALTHY, camera_age_s=45.0)
        agg2 = make_agg({"/v1/health": very_stale})
        nodes2 = {n.id: n for n in (await agg2.poll_once())["nodes"]}
        assert nodes2["cam_wrist_l"].status == "down"

        fresh = dict(HEALTHY, camera_age_s=0.2)
        agg3 = make_agg({"/v1/health": fresh})
        nodes3 = {n.id: n for n in (await agg3.poll_once())["nodes"]}
        assert nodes3["cam_rack"].status == "ok"       # fresh -> inherits healthy cell

    async def test_edges_inherit_worst_endpoint(self) -> None:
        agg = make_agg({})
        snap = await agg.poll_once()
        edges = {e.id: e for e in snap["edges"]}
        assert edges["seam-floor"].status == "down"

    async def test_topology_has_tools_endpoints_cameras(self) -> None:
        agg = make_agg({})
        snap = await agg.poll_once()
        kinds = {n.id: n.kind for n in snap["nodes"]}
        assert kinds.get("franka_left") == "endpoint"
        assert kinds.get("mobilebot") == "endpoint"
        assert kinds.get("cam_outside") == "camera"
        assert kinds.get("t_dispatch") == "tool"

    async def test_missions_proxy_degrades_loudly(self) -> None:
        agg = make_agg({})
        body = await agg.missions()
        assert body["missions"] == []
        assert "error" in body

    async def test_inspect_flattens_ops_with_summary(self) -> None:
        agg = make_agg({
            # specific key first — CannedHTTP substring-matches in insertion order
            "/v1/missions/m1": {"operations": [
                {"ts": "2026-07-01T00:00:02", "action": "move", "endpoint": "franka_left",
                 "verified": True, "request": {"action": "move"}, "result": {"verified": True},
                 "frame": "frames/r1.jpg", "request_id": "r1"},
                {"ts": "2026-07-01T00:00:01", "op": "perceive", "verified": None,
                 "request": {"target": "tote"}, "result": {"blocks": []}, "request_id": "r2"},
            ]},
            "/v1/missions?": {"missions": [{"mission_id": "m1"}]},
        })
        out = await agg.inspect(limit=10)
        assert out["summary"]["shown"] == 2
        assert out["summary"]["verified_dispatches"] == 1
        assert out["summary"]["with_frame"] == 1  # only the op with a frame path
        assert out["operations"][0]["ts"] == "2026-07-01T00:00:02"  # newest first
        assert out["operations"][0]["request"] == {"action": "move"}  # full request kept

    async def test_inspect_degrades_when_seam_down(self) -> None:
        agg = make_agg({})
        out = await agg.inspect()
        assert out["operations"] == []

    async def test_safety_derives_gate_and_coverage_from_audit(self) -> None:
        agg = make_agg({
            "/v1/missions/m1": {"operations": [
                {"ts": "2026-07-01T00:00:03", "duration_s": 4.2, "op": "dispatch",
                 "action": "move", "verified": True,
                 "request": {"action": "move", "color": "red"},
                 "result": {"measured": {"placement_offset_m": 0.03},
                            "gate": {"placement_tolerance_m": 0.08}},
                 "frame": "frames/r1.jpg", "request_id": "r1"},
                {"ts": "2026-07-01T00:00:02", "duration_s": 5.1, "op": "dispatch",
                 "action": "move", "verified": False,
                 "request": {"action": "move", "color": "blue"},
                 "result": {"measured": {"placement_offset_m": 0.12},
                            "gate": {"placement_tolerance_m": 0.08}},
                 "frame": "frames/r3.jpg", "request_id": "r3"},
                # perceive + verify ops ALSO carry an `action` field (target /
                # predicate text). They must NOT be counted as dispatches, or the
                # verified-rate denominator is poisoned.
                {"ts": "2026-07-01T00:00:01", "op": "perceive", "action": "conveyor_1",
                 "verified": None, "request": {"target": "tote"}, "result": {"blocks": []},
                 "frame": "frames/r2.jpg", "request_id": "r2"},
                {"ts": "2026-07-01T00:00:00", "op": "verify", "action": "cube in tote",
                 "verified": True, "request": {"predicate": "cube in tote"},
                 "result": {"ok": True}, "request_id": "r4"},
            ]},
            "/v1/missions?": {"missions": [{"mission_id": "m1"}]},
        })
        out = await agg.safety()
        g = out["gate"]
        assert g["dispatches"] == 2 and g["agent_class_ok"] == 2  # perceive/verify excluded
        assert g["operator_refused"] == 0
        assert g["physics_verified"] == 1 and g["unverified"] == 1
        assert g["verified_rate"] == 0.5  # 1 of 2 real dispatches, not 1 of 4 ops
        cov = out["coverage"]
        assert cov["ops"] == 4 and cov["with_frame"] == 3  # move,move,perceive framed
        assert cov["dispatches"] == 2
        assert cov["with_verdict"] == 2  # only the two dispatches carry a bool verdict
        assert cov["with_request"] == 4  # all four ops carry request_id + request
        assert cov["with_timing"] == 2   # only the two moves carry ts + duration_s
        # coverage must be measured, never a hardcoded 100%
        assert cov["with_timing"] != cov["ops"]
        assert len(out["placement"]) == 2
        passed = [p for p in out["placement"] if p["pass"]]
        assert len(passed) == 1 and passed[0]["color"] == "red"
        assert out["guarantees"]  # assurance case is non-empty

    async def test_safety_fail_closed_on_no_data(self) -> None:
        agg = make_agg({})
        out = await agg.safety()
        assert out["gate"]["dispatches"] == 0
        assert out["gate"]["verified_rate"] is None  # no false PASS invented
        assert out["placement"] == []
        assert out["guarantees"]

    async def test_mission_id_is_url_encoded(self) -> None:
        canned = CannedHTTP({"/v1/missions/": {"operations": []}})
        agg = make_agg({})
        agg._get_json = canned  # type: ignore[method-assign]
        await agg.mission_detail("abc?admin=1")
        url = canned.calls[0]
        # the injected query separator must be encoded, not forwarded raw
        assert "abc%3Fadmin%3D1" in url
        assert "?admin=1" not in url

    async def test_limit_is_clamped(self) -> None:
        canned = CannedHTTP({"/v1/missions": {"missions": []}})
        agg = make_agg({})
        agg._get_json = canned  # type: ignore[method-assign]
        await agg.missions(limit=999999)
        assert "limit=200" in canned.calls[0]

    async def test_gpu_chat_session_uses_persisted_chat_window(self) -> None:
        agg = make_agg({})
        agg.settings.chat_url = "http://chat"
        agg.settings.gpu_url = "http://gpu"
        canned = CannedHTTP({
            "/v1/missions/chat-demo": {"operations": []},
            "/api/sessions/demo": {
                "id": "demo", "mission_id": "chat-demo", "created": 1000.0,
                "updated": 1060.0, "active": False,
            },
            "/v1/gpu/series?": {"samples": [{"ts": "1970-01-01T00:17:00+00:00"}]},
        })
        agg._get_json = canned  # type: ignore[method-assign]

        body = await agg.gpu_for_mission("chat-demo")

        assert body["mission_id"] == "chat-demo"
        assert body["telemetry_basis"] == "chat-session"
        assert body["window"] == {
            "from": "1970-01-01T00:16:10+00:00",
            "to": "1970-01-01T00:18:10+00:00",
        }
        assert any("/api/sessions/demo" in url for url in canned.calls)
        assert any("/v1/gpu/series?from=" in url for url in canned.calls)

    async def test_gpu_mission_prefers_exact_seam_operation_window(self) -> None:
        agg = make_agg({})
        agg.settings.chat_url = "http://chat"
        agg.settings.gpu_url = "http://gpu"
        canned = CannedHTTP({
            "/v1/missions/chat-demo": {"operations": [
                {"ts": "2026-08-08T01:00:00Z", "duration_s": 12},
            ]},
            "/v1/gpu/series?": {"samples": []},
        })
        agg._get_json = canned  # type: ignore[method-assign]

        body = await agg.gpu_for_mission("chat-demo")

        assert body["telemetry_basis"] == "seam-mission"
        assert not any("/api/sessions/" in url for url in canned.calls)


class TestAPI:
    def test_api_surface_is_read_only(self) -> None:
        app = build_app(make_agg({"/v1/health": HEALTHY}))
        methods = {
            (route.path, m)
            for route in app.routes
            if hasattr(route, "methods")
            for m in route.methods  # type: ignore[attr-defined]
        }
        mutating = {m for _, m in methods if m in {"POST", "PUT", "DELETE", "PATCH"}}
        assert not mutating, methods

    def test_topology_endpoint(self) -> None:
        app = build_app(make_agg({"/v1/health": HEALTHY}))
        with TestClient(app) as client:
            body = client.get("/api/topology").json()
            assert {n["id"] for n in body["nodes"]} >= {"brain", "seam", "cell", "journal"}
            assert body["generated_at"]

    def test_safety_endpoint(self) -> None:
        app = build_app(make_agg({"/v1/missions?": {"missions": []}}))
        with TestClient(app) as client:
            body = client.get("/api/safety").json()
            assert {"gate", "coverage", "placement", "guarantees"} <= set(body)
            assert body["guarantees"]

    def test_index_serves_spa(self) -> None:
        app = build_app(make_agg({"/v1/health": HEALTHY}))
        with TestClient(app) as client:
            resp = client.get("/")
            assert resp.status_code == 200
            assert "CONSOLE" in resp.text
            assert 'id="tab-safety"' not in resp.text
            assert 'id="safety"' not in resp.text
            assert "/static/safety.js" not in resp.text

    def test_static_js_escapes_untrusted_fields(self) -> None:
        # Guard against regressing the stored-XSS fix: every innerHTML sink for
        # journal-sourced values must route through esc().
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "ic_console" / "static"
        for name in ("app.js", "builder.js", "chat.js", "inspect.js", "safety.js"):
            src = (static / name).read_text()
            assert any(f"function {p}esc(" in src for p in ("", "c", "i", "s")), name
            # the raw mission fields must never be interpolated without esc()
            for raw in ("${id}", "${op.reason", "${w.name}", "${t.description}",
                        "${body.error", "${n.label}", "${e.label}"):
                assert raw not in src, f"{name} interpolates {raw} unescaped"

    def test_chat_shows_journaled_frame_even_when_vlm_errors(self) -> None:
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "ic_console" / "static"
        src = (static / "chat.js").read_text()
        assert "const frame = rid" in src
        assert "visionFailed" not in src
        assert "tool response" in src
        assert '["check_predicate", "verify"].includes(entry.name)' in src

    def test_console_has_one_cross_pane_session_key(self) -> None:
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "ic_console" / "static"
        app = (static / "app.js").read_text()
        assert '"ic_active_mission"' in app
        for name in ("chat.js", "inspect.js", "gpu.js"):
            assert "window.ICSession" in (static / name).read_text()

    def test_gpu_pane_promotes_thor_and_shows_live_memory_contract(self) -> None:
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "ic_console" / "static"
        html = (static / "index.html").read_text()
        src = (static / "gpu.js").read_text()
        assert 'id="gpulive"' in html
        assert '"groot-shared-left"' in src
        assert '"groot-shared-right"' in src
        assert '"groot-specialists"' in src
        assert "ram_used_mib ?? sample.mem_used_mib" in src
        assert "telemetry_basis: body.telemetry_basis" in src
        assert 'fetch("/api/chat-sessions")' in src
        assert "per-process SM unavailable on Thor" in src
        assert "}, 5000);" in src

    def test_active_chat_survives_pane_switch(self) -> None:
        """Returning to Chat must not replace a live SSE transcript."""
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "ic_console" / "static"
        src = (static / "chat.js").read_text()
        assert "renderedSessionId" in src
        assert "if (!chatRunning && sessionId && renderedSessionId !== sessionId)" in src
        assert "if (chatRunning) return;" in src
        assert "sessionLoadGeneration += 1;" in src

    def test_chat_backend_selector_is_session_bound(self) -> None:
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "ic_console" / "static"
        html = (static / "index.html").read_text()
        src = (static / "chat.js").read_text()
        assert 'id="chatbackend"' in html
        assert 'value="traditional"' in html
        assert 'value="openclaw"' in html
        assert "backend: selectedBackend" in src
        assert 'setBackend(s.backend || "traditional")' in src
        assert "backendEl.disabled = running || Boolean(sessionId)" in src

    def test_inspector_frame_fallback_is_csp_compatible(self) -> None:
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "ic_console" / "static"
        src = (static / "inspect.js").read_text()
        assert 'addEventListener("error"' in src
        assert "onerror=" not in src
