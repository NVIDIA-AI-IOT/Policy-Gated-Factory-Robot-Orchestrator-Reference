# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the persistent HTTP floor service (mock backend)."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

# No-proxy opener: avoids slow per-request system proxy detection (macOS).
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _post(port: int, path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), method="POST"
    )
    try:
        with _opener.open(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:  # dispatch failures return JSON with a 4xx
        return json.loads(e.read())


def test_service_perceive_dispatch_floor_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGFR_FLOOR_BACKEND", "mock")
    from policy_gated_factory_robot_orchestrator_reference.floor.service import build_service

    httpd = build_service(("127.0.0.1", 0))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        obs = _post(port, "/perceive", {"target": "table_1"})
        assert obs["counts"] == {"red": 2, "green": 1}

        res = _post(port, "/dispatch", {"endpoint": "amr_franka_1", "action": "move",
                                        "color": "red", "from": "table_1", "destination": "red_rack"})
        assert res["dispatched"] is True and res["verified"] is True

        # State persists in the service: the red is now gone from the table.
        after = _post(port, "/perceive", {"target": "table_1"})
        assert after["counts"]["red"] == 1

        fs = _post(port, "/floor-state", {})
        assert {e["id"] for e in fs["endpoints"]} == {"amr_franka_1", "amr_franka_2", "conveyor_1"}
    finally:
        httpd.shutdown()


class _FakeLiveEndpoint:
    def __init__(self, id: str, kind: str) -> None:
        self.id = id
        self.type = kind

    async def execute(self, capability: str, goal_args: dict):
        from policy_gated_factory_robot_orchestrator_reference.action_endpoints.base import (
            ActionResult,
        )

        return ActionResult(success=True, result={"verified": True, "moved": goal_args}, reason="ok")


class _FakeLiveBackend:
    """Stands in for Ros2FloorBackend (observe() + executable endpoints) without ROS."""

    def observe(self, target: str) -> dict:
        return {"target": target, "blocks_on_table": [], "counts": {}, "sorted": True}

    def endpoints(self) -> list:
        return [_FakeLiveEndpoint("mobilebot", "arm+base")]

    def sources(self) -> list:
        return []


def test_service_live_backend_routes_through_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    # The live (ROS 2) path must go through endpoints()/observe()/execute, NOT the mock
    # ops on a FloorState — so serve drives the real cell once a backend is wired.
    from policy_gated_factory_robot_orchestrator_reference.floor import service as svc

    monkeypatch.setattr(svc, "load_backend", lambda *a, **k: _FakeLiveBackend())
    httpd = svc.build_service(("127.0.0.1", 0))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        fs = _post(port, "/floor-state", {})
        assert {e["id"] for e in fs["endpoints"]} == {"mobilebot"}

        obs = _post(port, "/perceive", {"target": "conveyor_1"})
        assert obs["sorted"] is True

        res = _post(port, "/dispatch", {"endpoint": "mobilebot", "action": "pick_and_place",
                                        "object_id": "tote", "target_id": "rack_1"})
        assert res["dispatched"] is True and res["verified"] is True
        assert res["moved"] == {"object_id": "tote", "target_id": "rack_1"}

        monkeypatch.delenv("PGFR_VLM_URL", raising=False)
        v = _post(port, "/verify", {"predicate": "is the tote on the rack?", "region": "rack_1"})
        assert v["answer"] == "unknown"  # /verify route wired; no VLM configured -> graceful fallback
    finally:
        httpd.shutdown()


def test_parallel_route_is_capability_gated_atomic_and_schema_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor import service as svc

    captured: list[list[dict]] = []
    state_reads = 0
    world: dict = {"tote": {}, "tote_r": {}}

    def pair(left_color: str, right_color: str) -> dict:
        return {
            "moves": [
                {
                    "endpoint": "franka_left",
                    "color": left_color,
                    "source": "conveyor_1",
                    "destination": f"tote_{left_color}",
                    "backend": "groot",
                },
                {
                    "endpoint": "franka_right",
                    "color": right_color,
                    "source": "conveyor_2",
                    "destination": f"tote_{right_color}",
                    "backend": "groot",
                },
            ]
        }

    async def _parallel(_backend, moves):
        captured.append(moves)
        return {
            "dispatched": True,
            "action": "move_pair",
            "verified": True,
            "independent_b1_verified": True,
            "per_arm_relay_ports": {"franka_left": 5612, "franka_right": 5613},
            "parallel_results": {
                "franka_left": {"verified": True},
                "franka_right": {"verified": True},
            },
        }

    def _state(_backend):
        nonlocal state_reads
        state_reads += 1
        return world

    monkeypatch.setattr(svc, "load_backend", lambda *a, **k: _FakeLiveBackend())
    monkeypatch.setattr(svc.ros2, "live_dispatch_parallel", _parallel)
    monkeypatch.setattr(svc.ros2, "live_floor_state", _state)
    monkeypatch.delenv("PGFR_GROOT_PARALLEL_ENABLED", raising=False)
    monkeypatch.delenv("PGFR_GROOT_FLEXIBLE_ORDER", raising=False)
    same_color = pair("green", "green")
    first = pair("blue", "green")
    second = pair("green", "red")
    third = pair("red", "blue")
    with TestClient(svc.build_app()) as client:
        for payload in (same_color, first):
            disabled = client.post("/v1/dispatch-parallel", json=payload)
            assert disabled.status_code == 200
            assert disabled.json()["status"] == "refused"
            assert "PGFR_GROOT_PARALLEL_ENABLED=1" in disabled.json()["reason"]
            assert captured == []
            assert state_reads == 0

        monkeypatch.setenv("PGFR_GROOT_PARALLEL_ENABLED", "1")
        for payload in (same_color, first):
            parallel_only = client.post("/v1/dispatch-parallel", json=payload)
            assert parallel_only.json()["status"] == "refused"
            assert "PGFR_GROOT_FLEXIBLE_ORDER=1" in parallel_only.json()["reason"]
            assert captured == []
            assert state_reads == 0

        monkeypatch.setenv("PGFR_GROOT_FLEXIBLE_ORDER", "1")
        rejected_same = client.post("/v1/dispatch-parallel", json=same_color)
        assert rejected_same.json()["status"] == "refused"
        assert "same-color pairs are not qualified" in rejected_same.json()["reason"]
        assert captured == []
        assert state_reads == 0

        wrong_first = client.post("/v1/dispatch-parallel", json=second)
        assert wrong_first.json()["status"] == "refused"
        assert wrong_first.json()["expected_colors"] == {
            "franka_left": "blue",
            "franka_right": "green",
        }
        assert captured == []

        accepted = client.post("/v1/dispatch-parallel", json=first)
        assert accepted.status_code == 200
        assert accepted.json()["independent_b1_verified"] is True
        assert accepted.json()["per_arm_relay_ports"] == {
            "franka_left": 5612,
            "franka_right": 5613,
        }
        assert captured == [first["moves"]]

        world = {"tote": {"blue": "in"}, "tote_r": {"green": "in"}}
        repeated = client.post("/v1/dispatch-parallel", json=first)
        assert repeated.json()["status"] == "refused"
        assert repeated.json()["expected_colors"] == {
            "franka_left": "green",
            "franka_right": "red",
        }
        assert len(captured) == 1

        world = {
            "tote": {"blue": "in", "green": "in"},
            "tote_r": {"green": "in"},
        }
        partial = client.post("/v1/dispatch-parallel", json=second)
        assert partial.json()["status"] == "refused"
        assert "partial certified concurrent pair" in partial.json()["reason"]
        assert len(captured) == 1

        world = {"tote": {"green": "in"}, "tote_r": {"red": "in"}}
        out_of_order = client.post("/v1/dispatch-parallel", json=first)
        assert out_of_order.json()["status"] == "refused"
        assert "not a completed prefix" in out_of_order.json()["reason"]
        assert len(captured) == 1

        world = {"tote": {"blue": "in"}, "tote_r": {"green": "in"}}
        accepted_second = client.post("/v1/dispatch-parallel", json=second)
        assert accepted_second.json()["verified"] is True
        assert len(captured) == 2

        world = {
            "tote": {"blue": "in", "green": "in"},
            "tote_r": {"green": "in", "red": "in"},
        }
        accepted_third = client.post("/v1/dispatch-parallel", json=third)
        assert accepted_third.json()["verified"] is True
        assert len(captured) == 3

        world = {
            "tote": {"blue": "in", "green": "in", "red": "in"},
            "tote_r": {"green": "in", "red": "in", "blue": "in"},
        }
        completed = client.post("/v1/dispatch-parallel", json=third)
        assert completed.json()["status"] == "refused"
        assert "already complete" in completed.json()["reason"]
        assert len(captured) == 3

        mismatched = pair("green", "red")
        mismatched["moves"][1]["destination"] = "tote_green"
        refused = client.post("/v1/dispatch-parallel", json=mismatched)
        assert refused.status_code == 422
        assert len(captured) == 3


def test_scene_declared_action_args_reach_live_endpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """New device parameters cross HTTP generically but remain policy-gated."""
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor import service as svc

    policy = tmp_path / "policy.yaml"
    policy.write_text(
        "schema_version: 1\nactions:\n"
        "  weld_seam:\n"
        "    required: [seam_id, recipe_id]\n"
        "    role: agent\n"
    )
    monkeypatch.setenv("PGFR_FLOOR_POLICY", str(policy))
    monkeypatch.setattr(svc, "load_backend", lambda *a, **k: _FakeLiveBackend())

    with TestClient(svc.build_app()) as client:
        missing = client.post(
            "/v1/dispatch",
            json={"endpoint": "mobilebot", "action": "weld_seam", "args": {"seam_id": "s-12"}},
        )
        assert missing.json()["dispatched"] is False
        assert "recipe_id" in missing.json()["reason"]

        result = client.post(
            "/v1/dispatch",
            json={
                "endpoint": "mobilebot",
                "action": "weld_seam",
                "args": {"seam_id": "s-12", "recipe_id": "r-4"},
            },
        )
        assert result.json()["dispatched"] is True
        assert result.json()["moved"] == {"seam_id": "s-12", "recipe_id": "r-4"}

        reserved = client.post(
            "/v1/dispatch",
            json={
                "endpoint": "mobilebot",
                "action": "weld_seam",
                "args": {"backend": "scripted", "seam_id": "s-12", "recipe_id": "r-4"},
            },
        )
        assert reserved.status_code == 422


# ---- v1 API (FastAPI): versioned routes, health, error envelope -------------------


def test_v1_routes_and_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGFR_FLOOR_BACKEND", "mock")
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor.service import build_app

    with TestClient(build_app()) as client:
        fs = client.post("/v1/floor-state", json={})
        assert fs.status_code == 200
        assert fs.headers.get("x-request-id")
        assert fs.json()["_meta"]["api"] == "v1"

        obs = client.post("/v1/perceive", json={"target": "table_1"})
        assert obs.json()["counts"] == {"red": 2, "green": 1}

        # v1 dispatch: always 200, result fields carry the outcome; snake_case keys
        res = client.post("/v1/dispatch", json={
            "endpoint": "amr_franka_1", "action": "move",
            "color": "red", "source": "table_1", "destination": "red_rack"})
        assert res.status_code == 200
        assert res.json()["dispatched"] is True and res.json()["verified"] is True

        # legacy 'from' alias still accepted on v1
        res2 = client.post("/v1/dispatch", json={
            "endpoint": "amr_franka_1", "action": "move",
            "color": "green", "from": "table_1", "destination": "green_rack"})
        assert res2.json()["dispatched"] is True

        health = client.get("/v1/health")
        assert health.status_code == 200
        assert health.json()["backend"] == "mock"

        # validation errors are explicit, not silent
        bad = client.post("/v1/perceive", json={})
        assert bad.status_code == 422

        # the OpenAPI contract exists for future teams
        spec = client.get("/openapi.json").json()
        assert "/v1/dispatch" in spec["paths"]


def test_live_health_fails_closed_until_floor_state_is_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor import service as svc

    class _HealthBackend(_FakeLiveBackend):
        floor_state_age_s: float | None = None

        def health(self) -> dict:
            return {
                "ros_ok": True,
                "floor_state_age_s": self.floor_state_age_s,
                "camera_age_s": {},
            }

    backend = _HealthBackend()
    monkeypatch.setattr(svc, "load_backend", lambda *a, **k: backend)

    with TestClient(svc.build_app()) as client:
        missing = client.get("/v1/health")
        assert missing.status_code == 503
        assert missing.json()["status"] == "degraded"

        backend.floor_state_age_s = 0.1
        fresh = client.get("/v1/health")
        assert fresh.status_code == 200
        assert fresh.json()["status"] == "ok"


def test_committed_openapi_spec_matches_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """schemas/floor-service.openapi.json is the published contract — keep it in
    lockstep with the live app (regenerate it when this fails)."""
    import json as _json
    from pathlib import Path

    monkeypatch.setenv("PGFR_FLOOR_BACKEND", "mock")
    from policy_gated_factory_robot_orchestrator_reference.floor.service import build_app

    committed = Path(__file__).resolve().parents[3] / "schemas" / "floor-service.openapi.json"
    if not committed.exists():
        pytest.skip("spec file not present in this checkout")
    assert _json.loads(committed.read_text()) == build_app().openapi()


def test_mission_journal_records_ops(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("PGFR_FLOOR_BACKEND", "mock")
    monkeypatch.setenv("PGFR_JOURNAL_DIR", str(tmp_path))
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor.service import build_app

    with TestClient(build_app()) as client:
        client.post("/v1/perceive", json={"target": "table_1"},
                    headers={"x-mission-id": "m-test-1"})
        client.post("/v1/dispatch", json={
            "endpoint": "amr_franka_1", "action": "move",
            "color": "red", "source": "table_1", "destination": "red_rack"})
    lines = [json.loads(x) for x in (tmp_path / "journal.jsonl").read_text().splitlines()]
    assert [e["op"] for e in lines] == ["perceive", "dispatch"]
    assert lines[0]["mission_id"] == "m-test-1"
    assert lines[1]["mission_id"] is None
    assert lines[1]["result"]["dispatched"] is True
    assert all(e["request_id"] for e in lines)
    assert lines[0]["duration_s"] >= 0


def test_journal_disabled_when_unset(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("PGFR_FLOOR_BACKEND", "mock")
    monkeypatch.delenv("PGFR_JOURNAL_DIR", raising=False)
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor.service import build_app

    with TestClient(build_app()) as client:
        client.post("/v1/perceive", json={"target": "table_1"})
    assert not (tmp_path / "journal.jsonl").exists()


def test_policy_gate_at_the_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGFR_FLOOR_BACKEND", "mock")
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor.service import build_app

    with TestClient(build_app()) as client:
        # unknown action -> refused with the allow-list in the reason
        r = client.post("/v1/dispatch", json={"action": "self_destruct", "endpoint": "amr_franka_1"})
        assert r.status_code == 200 and r.json()["dispatched"] is False
        assert "policy: unknown action" in r.json()["reason"]

        # missing required params -> refused, names them
        r = client.post("/v1/dispatch", json={"action": "move", "endpoint": "amr_franka_1"})
        assert r.json()["dispatched"] is False
        assert "missing required params" in r.json()["reason"]

        # operator-only without the role header -> refused
        r = client.post("/v1/dispatch", json={"action": "reset", "endpoint": "amr_franka_1"})
        assert r.json()["dispatched"] is False and "operator-only" in r.json()["reason"]

        # allowed action with full params still flows to the backend
        r = client.post("/v1/dispatch", json={
            "action": "move", "endpoint": "amr_franka_1",
            "color": "red", "source": "table_1", "destination": "red_rack"})
        assert r.json()["dispatched"] is True

        # legacy route enforces the same gate (400 + in-band reason)
        r = client.post("/dispatch", json={"action": "reset", "endpoint": "amr_franka_1"})
        assert r.status_code == 400 and "operator-only" in r.json()["reason"]


def test_operator_reset_forwards_explicit_scene_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The existing dispatch verb can stage the six-object demo without a restart."""
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor import service as svc

    monkeypatch.setattr(svc, "load_backend", lambda *a, **k: _FakeLiveBackend())
    payload = {
        "endpoint": "mobilebot",
        "action": "reset_scene",
        "scene_profile": "groot_three_object",
        "arm": "both",
        "color": "red",
        "layout_left": 3,
        "layout_right": 3,
        "seed": 50100,
    }
    with TestClient(svc.build_app()) as client:
        refused = client.post("/v1/dispatch", json=payload)
        assert refused.json()["dispatched"] is False
        assert "operator-only" in refused.json()["reason"]

        accepted = client.post(
            "/v1/dispatch",
            json=payload,
            headers={"x-role": "operator"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["verified"] is True
        assert accepted.json()["moved"] == {
            "color": "red",
            "scene_profile": "groot_three_object",
            "arm": "both",
            "layout_left": 3,
            "layout_right": 3,
            "seed": 50100,
        }

        invalid = client.post(
            "/v1/dispatch",
            json={**payload, "layout_left": 6},
            headers={"x-role": "operator"},
        )
        assert invalid.status_code == 422


def test_conformance_kit_certifies_this_implementation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reference implementation must pass its own certification bar."""
    import sys
    from pathlib import Path

    kit_src = Path(__file__).resolve().parents[3] / "packages" / "conformance-kit" / "src"
    if not kit_src.exists():
        pytest.skip("conformance kit not in this checkout")
    sys.path.insert(0, str(kit_src))
    monkeypatch.setenv("PGFR_FLOOR_BACKEND", "mock")
    from fastapi.testclient import TestClient
    from pgfr_conformance.kit import run_checks

    from policy_gated_factory_robot_orchestrator_reference.floor.service import build_app

    with TestClient(build_app()) as client:
        results = run_checks(client, region="table_1")
    failures = [f"{r.name}: {r.detail}" for r in results if not r.passed]
    assert not failures, failures


def test_audit_store_missions_and_detail(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("PGFR_FLOOR_BACKEND", "mock")
    monkeypatch.setenv("PGFR_JOURNAL_DIR", str(tmp_path))
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor.service import build_app

    with TestClient(build_app()) as client:
        for color, dest in (("red", "red_rack"), ("green", "green_rack")):
            client.post("/v1/dispatch", json={
                "endpoint": "amr_franka_1", "action": "move",
                "color": color, "source": "table_1", "destination": dest},
                headers={"x-mission-id": "m-story"})
        client.post("/v1/perceive", json={"target": "table_1"}, headers={"x-mission-id": "m-story"})

        ms = client.get("/v1/missions").json()["missions"]
        assert ms and ms[0]["mission_id"] == "m-story"
        assert ms[0]["ops"] == 3 and ms[0]["dispatches"] == 2 and ms[0]["verified_dispatches"] == 2

        ops = client.get("/v1/missions/m-story").json()["operations"]
        assert [o["op"] for o in ops] == ["dispatch", "dispatch", "perceive"]
        assert ops[0]["verified"] is True


def test_audit_store_retention_prunes(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import json as _json
    from datetime import UTC, datetime, timedelta

    monkeypatch.setenv("PGFR_JOURNAL_RETENTION_DAYS", "30")
    old_ts = (datetime.now(UTC) - timedelta(days=45)).isoformat(timespec="milliseconds")
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "old.jpg").write_bytes(b"x")
    (tmp_path / "journal.jsonl").write_text(_json.dumps({
        "ts": old_ts, "request_id": "old1", "mission_id": "m-old", "op": "dispatch",
        "request": {"action": "move"}, "result": {"verified": True, "reason": "ok"},
        "duration_s": 1.0, "frame": "frames/old.jpg"}) + "\n")
    from policy_gated_factory_robot_orchestrator_reference.floor.store import Store

    st = Store(str(tmp_path))
    st.ingest()
    st.prune()
    assert st.missions() == []
    assert not (tmp_path / "frames" / "old.jpg").exists()


def test_dispatch_backend_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """backend='groot' is accepted and validated; unknown backends are rejected
    (deny by default: a typo must never silently run the scripted controller while
    the caller believes a learned policy executed)."""
    monkeypatch.setenv("PGFR_FLOOR_BACKEND", "mock")
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor.service import (
        DispatchRequest,
        build_app,
    )

    # model accepts groot + carries it; live path forwards non-None goal args
    req = DispatchRequest(endpoint="franka_left", action="move", color="blue", backend="groot")
    assert req.backend == "groot"
    assert DispatchRequest(endpoint="franka_left", action="move").backend is None

    with TestClient(build_app()) as client:
        ok = client.post("/v1/dispatch", json={
            "endpoint": "amr_franka_1", "action": "move",
            "color": "red", "source": "table_1", "destination": "red_rack",
            "backend": "groot"})
        assert ok.status_code == 200
        bad = client.post("/v1/dispatch", json={
            "endpoint": "amr_franka_1", "action": "move", "backend": "gr00t_typo"})
        assert bad.status_code == 422  # unknown backend rejected, not silently dropped


def test_async_dispatch_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """wait=False returns immediately with a goal_id on the live path; the task
    route answers unknown on the mock floor; unknown goal ids never read as
    running (stop on uncertainty)."""
    monkeypatch.setenv("PGFR_FLOOR_BACKEND", "mock")
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor.service import (
        DispatchRequest,
        build_app,
    )

    assert DispatchRequest(endpoint="amr_franka_1", action="move").wait is True
    req = DispatchRequest(endpoint="amr_franka_1", action="move", wait=False)
    assert req.wait is False

    with TestClient(build_app()) as client:
        r = client.get("/v1/tasks/deadbeef1234")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "unknown"  # mock floor: no async goals, never 'running'


def test_async_hardening_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Busy-guard refuses silent stacking; cancel is refused honestly on live;
    malformed goal ids are rejected without touching the bridge."""
    monkeypatch.setenv("PGFR_FLOOR_BACKEND", "mock")
    from fastapi.testclient import TestClient

    from policy_gated_factory_robot_orchestrator_reference.floor.service import (
        DispatchRequest,
        build_app,
    )

    assert DispatchRequest(endpoint="amr_franka_1", action="move").queue is False

    with TestClient(build_app()) as client:
        # path traversal is stopped by the router itself (404, never a file read)
        r = client.get("/v1/tasks/../../etc/passwd")
        assert r.status_code == 404
        r2 = client.get("/v1/tasks/%0aFORGED")
        assert r2.json()["reason"] == "malformed goal_id"


def test_bridge_async_semantics() -> None:
    """send_async busy-guard + poll lifecycle + TTL sweep, with a stubbed pub."""
    import time as _time

    from policy_gated_factory_robot_orchestrator_reference.floor import ros2 as r2

    class _Pub:
        def get_subscription_count(self):
            return 1

        def publish(self, m):
            self.last = m

    class _Str:
        def __init__(self, data=""):
            self.data = data

    b = object.__new__(r2._Bridge)
    b._lock = __import__("threading").Lock()
    b._results = {}
    b._pending = {}
    b._last_result = None
    b._cmd_pub = _Pub()
    b._String = _Str

    r = b.send_async({"action": "move"})
    gid = r["goal_id"]
    assert b.poll_result(gid) is None                      # running
    r_busy = b.send_async({"action": "move"})
    assert "refused" in r_busy and r_busy["busy_goal"] == gid   # busy-guard
    assert "goal_id" in b.send_async({"action": "move"}, queue=True)  # explicit stacking
    b._results[gid] = {"success": True, "goal_id": gid}
    assert b.poll_result(gid)["success"] is True           # done, non-destructive
    b._pending[gid]["ts"] = _time.time() - 7200
    b._sweep_async_locked_test = None
    with b._lock:
        b._sweep_async()
    assert gid not in b._pending and gid not in b._results  # TTL swept
    try:
        b.poll_result("nonexistent000")
        raise AssertionError("unknown goal must raise")
    except KeyError:
        pass
