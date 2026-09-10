# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the PGFR console aggregator + API.

Hardware-free: a fake seam (FastAPI TestClient-style httpx MockTransport is
not used because the aggregator owns its client; instead we run a real
in-process HTTP server via uvicorn-free asyncio) — simplest robust approach:
monkeypatch the aggregator's HTTP layer with canned responses.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx
import pytest
from fastapi.testclient import TestClient

from pgfr_console.aggregator import Aggregator, Settings
from pgfr_console.app import build_app
from pgfr_console.topology import Edge, NodeStatus, resolve


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
    settings.chat_url = env.get("chat_url", settings.chat_url)
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
        assert "mock" in str(nodes["cell"].detail).lower()

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

    async def test_unconfigured_integrations_are_absent(self) -> None:
        snapshot = await make_agg({"/v1/health": HEALTHY}).poll_once()
        ids = {node.id for node in snapshot["nodes"]}
        assert not ({"gym", "vlm", "groot"} & ids)
        assert all(edge.source in ids and edge.target in ids for edge in snapshot["edges"])

    @pytest.mark.parametrize("status_code", [404, 500, 503])
    async def test_configured_gym_http_failure_remains_visible(self, status_code: int) -> None:
        agg = make_agg({
            "http://gym/": {"_http_status": status_code, "detail": "Unavailable"},
            "/v1/health": HEALTHY,
        }, gym_url="http://gym")
        snapshot = await agg.poll_once()
        nodes = {node.id: node for node in snapshot["nodes"]}
        assert nodes["gym"].status == "down"
        assert nodes["gym"].detail["url"] == "http://gym"
        assert any(edge.source == "gym" for edge in snapshot["edges"])

    async def test_configured_unreachable_models_remain_visible(self) -> None:
        agg = make_agg({"/v1/health": HEALTHY}, vlm_url="http://vision")
        snapshot = await agg.poll_once()
        nodes = {node.id: node for node in snapshot["nodes"]}
        assert nodes["vlm"].status == "down"
        assert nodes["vlm"].label == "Vision model"
        assert all(edge.source in nodes and edge.target in nodes for edge in snapshot["edges"])

    async def test_model_labels_are_generic_and_metadata_is_measured(self) -> None:
        model = "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-NVFP4-QAD"
        agg = make_agg({
            "/v1/health": HEALTHY,
            "http://chat/api/health": {
                "_http_status": 200, "status": "ok", "backend": "openai",
                "backends": {"traditional": {"available": True}},
                "tools": ["floor_state", "perceive"],
            },
            "http://vision/v1/models": {"_http_status": 200, "data": [{"id": model}]},
        }, chat_url="http://chat", vlm_url="http://vision")
        nodes = {node.id: node for node in (await agg.poll_once())["nodes"]}
        assert nodes["brain"].label == "Chat"
        assert nodes["brain"].status == "ok"
        assert nodes["brain"].detail["backend"] == "openai"
        assert nodes["brain"].detail["status_basis"]
        assert nodes["vlm"].label == "Vision model"
        assert nodes["vlm"].status == "ok"
        assert nodes["vlm"].detail["model_ids"] == [model]
        assert not any("Cosmos" in node.label or "OpenClaw" in node.label for node in nodes.values())

    async def test_reported_cameras_have_individual_freshness(self) -> None:
        ages = {"inspect_vlm_cam": 0.2, "outside_right_cam": 12.0, "inspect_cam": 45.0}
        agg = make_agg({"/v1/health": dict(HEALTHY, camera_age_s=ages)})
        snapshot = await agg.poll_once()
        nodes = {node.id: node for node in snapshot["nodes"]}
        cameras = {node.id: node for node in nodes.values() if node.kind == "camera"}
        assert set(cameras) == set(ages)
        assert nodes["cell"].status == "ok"
        assert cameras["inspect_vlm_cam"].status == "ok"
        assert cameras["outside_right_cam"].status == "degraded"
        assert cameras["inspect_cam"].status == "down"
        assert cameras["outside_right_cam"].detail["camera_id"] == "outside_right_cam"
        assert cameras["outside_right_cam"].detail["camera_age_s"] == 12.0
        assert all(edge.source in nodes and edge.target in nodes for edge in snapshot["edges"])

    @pytest.mark.parametrize("age", [None, float("nan"), float("inf"), -1.0, True, "0.2"])
    async def test_invalid_camera_age_is_unknown(self, age: Any) -> None:
        agg = make_agg({"/v1/health": dict(HEALTHY, camera_age_s={"rack_cam": age})})
        nodes = {node.id: node for node in (await agg.poll_once())["nodes"]}
        assert nodes["cell"].status == "ok"
        assert nodes["rack_cam"].status == "unknown"
        assert nodes["rack_cam"].detail.get("camera_age_s") is None

    async def test_discovered_cameras_survive_missing_readings_and_outage(self) -> None:
        payloads = {"/v1/health": dict(HEALTHY, camera_age_s={"inspect_cam": 0.2, "rack_cam": 0.1})}
        agg = make_agg(payloads)
        await agg.poll_once()
        payloads["/v1/health"] = dict(HEALTHY, camera_age_s={"inspect_cam": 0.2})
        nodes = {node.id: node for node in (await agg.poll_once())["nodes"]}
        assert nodes["inspect_cam"].status == "ok"
        assert nodes["rack_cam"].status == "unknown"
        payloads.clear()
        nodes = {node.id: node for node in (await agg.poll_once())["nodes"]}
        cameras = {node.id: node for node in nodes.values() if node.kind == "camera"}
        assert set(cameras) == {"inspect_cam", "rack_cam"}
        assert all(camera.status == "unknown" for camera in cameras.values())

    async def test_legacy_missing_camera_age_does_not_inherit_healthy_cell(self) -> None:
        health = {key: value for key, value in HEALTHY.items() if key != "camera_age_s"}
        nodes = {node.id: node for node in (await make_agg({"/v1/health": health}).poll_once())["nodes"]}
        assert nodes["cell"].status == "ok"
        cameras = [node for node in nodes.values() if node.kind == "camera"]
        assert cameras and all(camera.status == "unknown" for camera in cameras)

    @pytest.mark.parametrize("age, status", [(0, "ok"), (90, "degraded"), (240, "unknown"), (None, "unknown")])
    async def test_groot_status_uses_fresh_passive_transport_evidence(
        self, age: Optional[int], status: str
    ) -> None:
        report = {
            "ports_open": 2, "ports_total": 2, "degraded": False,
            "services": {
                "franka_left": {"port": 5741, "listening": True},
                "franka_right": {"port": 5742, "listening": True},
            },
            "observed_at_epoch_s": time.time() - age if age is not None else None,
        }
        agg = make_agg({
            "/v1/health": HEALTHY,
            "/v1/floor-state": {"_http_status": 200, "groot_serving": report},
        })
        nodes = {node.id: node for node in (await agg.poll_once())["nodes"]}
        assert nodes["groot"].status == status
        assert "transport" in nodes["groot"].detail["status_basis"].lower()
        assert "inference" in nodes["groot"].detail["status_basis"].lower()
        assert nodes["groot"].detail["services"] == report["services"]
        canned = agg._get_json
        assert isinstance(canned, CannedHTTP)
        assert not any(":5741" in url or ":5742" in url for url in canned.calls)

    async def test_groot_failed_transport_is_visible_and_outage_is_unknown(self) -> None:
        payloads = {
            "/v1/health": HEALTHY,
            "/v1/floor-state": {
                "_http_status": 200,
                "groot_serving": {
                    "ports_open": 1, "ports_total": 2, "degraded": True,
                    "services": {
                        "franka_left": {"port": 5741, "listening": True},
                        "franka_right": {"port": 5742, "listening": False},
                    },
                    "observed_at_epoch_s": time.time(),
                },
            },
        }
        agg = make_agg(payloads)
        nodes = {node.id: node for node in (await agg.poll_once())["nodes"]}
        assert nodes["groot"].status == "degraded"
        payloads.clear()
        snapshot = await agg.poll_once()
        nodes = {node.id: node for node in snapshot["nodes"]}
        assert nodes["groot"].status == "unknown"
        assert all(edge.source in nodes and edge.target in nodes for edge in snapshot["edges"])

    async def test_endpoint_details_never_cross_between_arms(self) -> None:
        agg = make_agg({
            "/v1/health": HEALTHY,
            "/v1/floor-state": {"_http_status": 200, "endpoints": [
                {"id": "franka_left", "status": "idle", "location": "left station"},
            ]},
        })
        nodes = {node.id: node for node in (await agg.poll_once())["nodes"]}
        assert nodes["franka_left"].detail["location"] == "left station"
        assert nodes["franka_right"].detail.get("location") != "left station"
        assert nodes["franka_right"].detail.get("status") != "idle"

    def test_resolve_omits_edges_to_absent_components(self) -> None:
        cell = NodeStatus(id="cell", label="Isaac Sim", kind="sim", status="ok")
        journal = NodeStatus(id="journal", label="History", kind="store", status="down")
        output = resolve({"cell": cell, "journal": journal}, {
            "record": Edge(id="record", source="cell", target="journal"),
            "optional": Edge(id="optional", source="cell", target="absent"),
        })
        assert [edge.id for edge in output["edges"]] == ["record"]
        assert output["edges"][0].status == "down"

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

    async def test_assurance_derives_gate_and_coverage_from_audit(self) -> None:
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
        out = await agg.assurance()
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
        assert out["assurance_claims"]  # assurance case is non-empty

    async def test_assurance_stops_on_uncertainty_when_no_data(self) -> None:
        agg = make_agg({})
        out = await agg.assurance()
        assert out["gate"]["dispatches"] == 0
        assert out["gate"]["verified_rate"] is None  # no false PASS invented
        assert out["placement"] == []
        assert out["assurance_claims"]

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

    def test_assurance_endpoint(self) -> None:
        app = build_app(make_agg({"/v1/missions?": {"missions": []}}))
        with TestClient(app) as client:
            body = client.get("/api/assurance").json()
            assert {"gate", "coverage", "placement", "assurance_claims"} <= set(body)
            assert body["assurance_claims"]

    def test_index_serves_spa(self) -> None:
        app = build_app(make_agg({"/v1/health": HEALTHY}))
        with TestClient(app) as client:
            resp = client.get("/")
            assert resp.status_code == 200
            assert "<title>Orchestration Console</title>" in resp.text
            header = resp.text.split("<header>", 1)[1].split("</header>", 1)[0]
            assert "<h1>Orchestration Console</h1>" in header
            assert 'id="stamp"' not in header
            assert 'id="active-session"' not in header
            assert header.index('id="reset-scene"') > header.index("</nav>")
            chat = resp.text.split('<main id="chat">', 1)[1].split("</main>", 1)[0]
            sidebar = chat.split("<aside>", 1)[1].split("</aside>", 1)[0]
            details = sidebar.split('<details id="session-details">', 1)[1]
            details = details.split("</details>", 1)[0]
            assert "<summary>Session details</summary>" in details
            assert 'id="chatsession"' in details
            assert 'id="copy-session-id"' in details
            assert "What would you like the cell to do?" in chat
            assert chat.count('data-prompt="') == 2
            dialog = resp.text.split('<dialog id="reset-dialog"', 1)[1]
            dialog = dialog.split("</dialog>", 1)[0]
            assert "Current scene progress will be cleared." in dialog
            assert 'id="cancel-reset-scene"' in dialog
            assert 'id="confirm-reset-scene"' in dialog
            assert 'id="tab-assurance"' not in resp.text
            assert 'id="assurance"' not in resp.text
            assert "/static/assurance.js" not in resp.text
            assert 'id="tab-wf"' not in resp.text
            assert 'id="builder"' not in resp.text
            assert "/static/builder.js" not in resp.text
            assert client.get("/static/builder.js").status_code == 404
            assert '<button id="tab-chat" class="active">' in resp.text
            assert '<button id="tab-topo" class="active">' not in resp.text
            assert '#topo { display: none;' in resp.text
            assert '#chat { display: grid;' in resp.text

    def test_public_chat_url_only_changes_the_browser_csp(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        internal_url = "http://127.0.0.1:8620"
        public_url = "http://192.0.2.42:8620"
        monkeypatch.setenv("PGFR_CHAT_URL", internal_url)
        monkeypatch.setenv("PGFR_CHAT_PUBLIC_URL", public_url)

        app = build_app(make_agg({"/v1/health": HEALTHY}))
        with TestClient(app) as client:
            csp = client.get("/").headers["content-security-policy"]

        assert public_url in csp
        assert f"img-src 'self' data: {public_url}" in csp
        assert internal_url not in csp
        assert app.state.aggregator.settings.chat_url == internal_url

    def test_static_js_escapes_untrusted_fields(self) -> None:
        # Guard against regressing the stored-XSS fix: every innerHTML sink for
        # journal-sourced values must route through esc().
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "pgfr_console" / "static"
        for name in ("app.js", "chat.js", "inspect.js", "assurance.js"):
            src = (static / name).read_text()
            assert any(f"function {p}esc(" in src for p in ("", "c", "i", "s", "a")), name
            # the raw mission fields must never be interpolated without esc()
            for raw in ("${id}", "${op.reason", "${w.name}", "${t.description}",
                        "${body.error", "${n.label}", "${e.label}"):
                assert raw not in src, f"{name} interpolates {raw} unescaped"

    def test_chat_shows_journaled_frame_even_when_vlm_errors(self) -> None:
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "pgfr_console" / "static"
        src = (static / "chat.js").read_text()
        assert "const frame = rid" in src
        assert "visionFailed" not in src
        assert "tool response" in src
        assert '["check_predicate", "verify"].includes(entry.name)' in src

    def test_console_has_one_cross_pane_session_key(self) -> None:
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "pgfr_console" / "static"
        app = (static / "app.js").read_text()
        assert '"pgfr_active_mission"' in app
        for name in ("chat.js", "inspect.js"):
            assert "window.PGFRSession" in (static / name).read_text()

    def test_gpu_pane_promotes_thor_and_shows_live_memory_contract(self) -> None:
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "pgfr_console" / "static"
        html = (static / "index.html").read_text()
        src = (static / "gpu.js").read_text()
        assert 'id="gpulive"' in html
        assert '"groot-shared-left"' in src
        assert '"groot-shared-right"' in src
        assert '"groot-specialists"' in src
        assert "ram_used_mib ?? sample.mem_used_mib" in src
        assert "telemetry_basis: body.telemetry_basis" in src
        assert 'read("/api/chat-sessions")' in src
        assert 'smAvailable ? "<th>Compute use</th>" : ""' in src
        assert "}, 5000);" in src

    def test_active_chat_survives_pane_switch(self) -> None:
        """Returning to Chat must not replace a live SSE transcript."""
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "pgfr_console" / "static"
        src = (static / "chat.js").read_text()
        assert "renderedSessionId" in src
        assert "if (!chatRunning && !resetRunning && sessionId" in src
        assert "renderedSessionId !== sessionId)" in src
        assert "if (chatRunning || resetRunning) return;" in src
        assert "sessionLoadGeneration += 1;" in src

    def test_chat_backend_selector_is_session_bound(self) -> None:
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "pgfr_console" / "static"
        html = (static / "index.html").read_text()
        src = (static / "chat.js").read_text()
        assert 'id="chatbackend"' in html
        assert 'value="traditional"' in html
        assert 'value="openclaw"' in html
        assert "backend: selectedBackend" in src
        assert 'setBackend(s.backend || "traditional")' in src
        assert "backendEl.disabled = running || resetRunning || sessionLoading || Boolean(sessionId)" in src

    def test_inspector_frame_fallback_is_csp_compatible(self) -> None:
        import pathlib

        static = pathlib.Path(__file__).parent.parent / "src" / "pgfr_console" / "static"
        src = (static / "inspect.js").read_text()
        assert 'addEventListener("error"' in src
        assert "onerror=" not in src
