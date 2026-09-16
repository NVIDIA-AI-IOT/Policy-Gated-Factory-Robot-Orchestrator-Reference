# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests: tool → seam-route/payload mapping against a fake floor service."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from pgfr_mcp import server


class _FakeSeam(BaseHTTPRequestHandler):
    calls: list[tuple[str, dict]] = []
    roles: list[str | None] = []
    floor_state_response: dict | None = None
    dispatch_response: dict | None = None
    verify_response: dict | None = None
    status_code: int = 200

    def log_message(self, *_a: object) -> None:
        return

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length", 0))
        params = json.loads(self.rfile.read(n) or b"{}")
        _FakeSeam.calls.append((self.path, params))
        _FakeSeam.roles.append(self.headers.get("x-role"))
        code = 400 if params.get("action") == "fail_me" else _FakeSeam.status_code
        configured = None
        if self.path == "/v1/floor-state":
            configured = _FakeSeam.floor_state_response
        elif self.path == "/v1/dispatch":
            configured = _FakeSeam.dispatch_response
        elif self.path == "/v1/dispatch-parallel":
            configured = _FakeSeam.dispatch_response
        elif self.path == "/v1/verify":
            configured = _FakeSeam.verify_response
        body = json.dumps(
            configured if configured is not None
            else {"echo": self.path, "ok": code == 200}
        ).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def seam(monkeypatch):
    httpd = HTTPServer(("127.0.0.1", 0), _FakeSeam)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("PGFR_FLOOR_SERVICE", f"http://127.0.0.1:{httpd.server_port}")
    monkeypatch.delenv("PGFR_MCP_ROLE", raising=False)
    monkeypatch.delenv("PGFR_DEFAULT_BACKEND", raising=False)
    monkeypatch.delenv("PGFR_CERTIFIED_GROOT_ORDER", raising=False)
    monkeypatch.delenv("PGFR_GROOT_PARALLEL_ENABLED", raising=False)
    monkeypatch.delenv("PGFR_GROOT_FLEXIBLE_ORDER", raising=False)
    _FakeSeam.calls.clear()
    _FakeSeam.roles.clear()
    _FakeSeam.floor_state_response = None
    _FakeSeam.dispatch_response = None
    _FakeSeam.verify_response = None
    _FakeSeam.status_code = 200
    server._PENDING_PROOF = None
    server._DISPATCH_ATTEMPTS.clear()
    server._LAST_CERTIFIED_PREFIX = None
    server._SCENE_RESET_ID = None
    server._SCENE_RESET_KNOWN = False
    yield httpd
    httpd.shutdown()


def test_floor_state_route(seam):
    out = json.loads(server.floor_state())
    assert out["echo"] == "/v1/floor-state"
    assert _FakeSeam.calls == [("/v1/floor-state", {})]
    assert _FakeSeam.roles == ["agent"]


def test_playbook_defaults_vague_whole_cell_sort_to_both_arms() -> None:
    playbook = server._playbook()
    assert "use **both arms by default**" in playbook
    assert '"use only the left arm"' in playbook
    assert '"use only the right arm"' in playbook
    assert '"use one arm" without naming left or right' in playbook
    assert "Never make a single arm reach across the cell" in playbook
    assert "active_capabilities.mixed_color_parallel_enabled" in playbook
    assert "Do not ask the operator to edit environment" in playbook


def test_perceive_route(seam):
    server.perceive("conveyor_1")
    assert _FakeSeam.calls == [("/v1/perceive", {"target": "conveyor_1"})]


def test_reset_scene_uses_operator_role_and_clears_policy_state(seam):
    _FakeSeam.dispatch_response = {
        "dispatched": True,
        "verified": True,
        "reason": "scene reset",
    }
    server._PENDING_PROOF = {"action": "move", "color": "red"}
    server._DISPATCH_ATTEMPTS[("move", "red")] = 2
    server._LAST_CERTIFIED_PREFIX = 4
    out = json.loads(server.reset_scene())
    assert out["verified"] is True
    assert _FakeSeam.calls == [
        (
            "/v1/dispatch",
            {
                "endpoint": "mobilebot",
                "action": "reset_scene",
                "scene_profile": "groot_three_object",
                "arm": "both",
                "color": "red",
                "layout_left": 3,
                "layout_right": 3,
                "seed": 31302,
            },
        )
    ]
    assert _FakeSeam.roles == ["operator"]
    assert server._PENDING_PROOF is None
    assert server._DISPATCH_ATTEMPTS == {}
    assert server._LAST_CERTIFIED_PREFIX is None


def test_dispatch_move_maps_source_to_from(seam):
    server.dispatch_task(
        action="move", endpoint="franka_left",
        color="blue", source="conveyor_1", destination="tote_blue",
    )
    path, payload = _FakeSeam.calls[0]
    assert path == "/v1/dispatch"
    assert payload == {
        "action": "move", "endpoint": "franka_left",
        "color": "blue", "source": "conveyor_1", "destination": "tote_blue",
    }


def test_dispatch_haul_payload(seam):
    server.dispatch_task(
        action="pick_and_place", endpoint="mobilebot",
        object_id="tote", target_id="rack_1",
    )
    _, payload = _FakeSeam.calls[0]
    assert payload == {
        "action": "pick_and_place", "endpoint": "mobilebot",
        "object_id": "tote", "target_id": "rack_1",
    }


def test_certified_groot_sequence_is_green_first_and_interleaved(monkeypatch):
    monkeypatch.delenv("PGFR_GROOT_PARALLEL_ENABLED", raising=False)
    plan = json.loads(server.certified_groot_sequence())
    assert plan["execution_mode"] == "serial_fallback"
    assert [
        (move["endpoint"], move["color"])
        for move in plan["moves"]
    ] == [
        ("franka_right", "green"),
        ("franka_left", "green"),
        ("franka_right", "red"),
        ("franka_left", "red"),
        ("franka_right", "blue"),
        ("franka_left", "blue"),
    ]
    assert all(move["backend"] == "groot" for move in plan["moves"])


def test_certified_groot_sequence_uses_atomic_pairs_when_enabled(monkeypatch):
    monkeypatch.setenv("PGFR_CERTIFIED_GROOT_ORDER", "1")
    monkeypatch.setenv("PGFR_GROOT_PARALLEL_ENABLED", "1")
    monkeypatch.setenv("PGFR_GROOT_FLEXIBLE_ORDER", "1")
    plan = json.loads(server.certified_groot_sequence())
    assert plan["execution_mode"] == "concurrent_mixed_pairs"
    assert plan["active_capabilities"] == {
        "certified_order_enabled": True,
        "parallel_enabled": True,
        "flexible_order_enabled": True,
        "mixed_color_parallel_enabled": True,
        "configuration_change_required_for_mixed_color": False,
    }
    assert "moves" not in plan
    assert [transaction["tool"] for transaction in plan["transactions"]] == [
        "dispatch_parallel",
        "dispatch_parallel",
        "dispatch_parallel",
    ]
    assert [transaction["args"] for transaction in plan["transactions"]] == [
        {"left_color": "blue", "right_color": "green"},
        {"left_color": "green", "right_color": "red"},
        {"left_color": "red", "right_color": "blue"},
    ]
    assert all(
        [proof["region"] for proof in transaction["proofs"]] == ["tote", "tote_r"]
        for transaction in plan["transactions"]
    )


def test_parallel_plan_reports_mixed_color_disabled_without_flexible_flag(
    monkeypatch,
):
    monkeypatch.setenv("PGFR_CERTIFIED_GROOT_ORDER", "1")
    monkeypatch.setenv("PGFR_GROOT_PARALLEL_ENABLED", "1")
    monkeypatch.delenv("PGFR_GROOT_FLEXIBLE_ORDER", raising=False)
    plan = json.loads(server.certified_groot_sequence())
    assert plan["execution_mode"] == "serial_fallback"
    assert "transactions" not in plan
    assert plan["active_capabilities"]["mixed_color_parallel_enabled"] is False
    assert (
        plan["active_capabilities"][
            "configuration_change_required_for_mixed_color"
        ]
        is True
    )


def test_parallel_schema_rejection_does_not_open_a_proof_gate(seam, monkeypatch):
    monkeypatch.setenv("PGFR_CERTIFIED_GROOT_ORDER", "1")
    monkeypatch.setenv("PGFR_GROOT_PARALLEL_ENABLED", "1")
    monkeypatch.setenv("PGFR_GROOT_FLEXIBLE_ORDER", "1")
    def fake_post(route, *_args, **_kwargs):
        if route == "/v1/floor-state":
            return json.dumps({"tote": {}, "tote_r": {}})
        return json.dumps({
            "detail": [{"msg": "Value error, stale same-color validator"}],
        })

    monkeypatch.setattr(server, "_post", fake_post)
    result = json.loads(server.dispatch_parallel("blue", "green"))
    assert result["dispatched"] is False
    assert result["status"] == "refused"
    assert "before motion" in result["reason"]
    assert "stale same-color validator" in result["reason"]
    assert server._PENDING_PROOF is None
    assert server._DISPATCH_ATTEMPTS == {}


def test_async_dispatch_behavior_is_unchanged(seam):
    server.dispatch_task(
        action="move", endpoint="franka_left", color="red",
        source="conveyor_1", destination="tote_red", wait=False,
    )
    assert _FakeSeam.calls[0][1]["wait"] is False


def test_unverified_dispatch_400_body_is_returned(seam):
    out = json.loads(server.dispatch_task(action="fail_me", endpoint="franka_left"))
    assert out["ok"] is False  # body of the 400, not an exception


def test_verify_route(seam):
    server.verify("the tote is on the rack", region="rack_1")
    assert _FakeSeam.calls == [
        ("/v1/verify", {"predicate": "the tote is on the rack", "region": "rack_1"})
    ]


def _enable_certified(monkeypatch) -> None:
    monkeypatch.setenv("PGFR_DEFAULT_BACKEND", "groot")
    monkeypatch.setenv("PGFR_CERTIFIED_GROOT_ORDER", "1")
    _FakeSeam.floor_state_response = {"tote": {}, "tote_r": {}}


def test_certified_order_rejects_wrong_first_move_before_dispatch(seam, monkeypatch):
    _enable_certified(monkeypatch)
    out = json.loads(server.dispatch_task(
        action="move",
        endpoint="franka_right",
        color="red",
        source="conveyor_2",
        destination="tote_red",
    ))
    assert out["status"] == "refused"
    assert out["expected"]["endpoint"] == "franka_right"
    assert out["expected"]["color"] == "green"
    assert [path for path, _ in _FakeSeam.calls] == ["/v1/floor-state"]


def test_certified_dispatch_requires_exact_visual_proof(seam, monkeypatch):
    _enable_certified(monkeypatch)
    _FakeSeam.dispatch_response = {
        "dispatched": True,
        "verified": True,
        "reason": "green in tote",
    }
    _FakeSeam.verify_response = {
        "answer": "yes",
        "evidence": "green brick visible in the right tote",
    }
    first = json.loads(server.dispatch_task(
        action="move",
        endpoint="franka_right",
        color="green",
        source="conveyor_2",
        destination="tote_green",
        backend="scripted",
    ))
    assert first["proof_gate"]["state"] == "awaiting_vlm"
    dispatch_payload = next(
        payload for path, payload in _FakeSeam.calls if path == "/v1/dispatch"
    )
    assert dispatch_payload["backend"] == "groot"

    blocked = json.loads(server.dispatch_task(
        action="move",
        endpoint="franka_left",
        color="green",
        source="conveyor_1",
        destination="tote_green",
    ))
    assert blocked["status"] == "refused"
    assert blocked["proof_gate"]["state"] == "awaiting_vlm"

    wrong = json.loads(server.verify("the red cube is in the tote", region="tote_r"))
    assert wrong["status"] == "refused"
    assert "green brick" in wrong["error"]

    cleared = json.loads(server.verify(
        "the green brick is visibly inside the right tote",
        region="tote_r",
    ))
    assert cleared["answer"] == "yes"
    assert cleared["proof_gate"]["state"] == "cleared"

    _FakeSeam.floor_state_response = {"tote": {}, "tote_r": {"green": "in"}}
    second = json.loads(server.dispatch_task(
        action="move",
        endpoint="franka_left",
        color="green",
        source="conveyor_1",
        destination="tote_green",
    ))
    assert second["dispatched"] is True


def test_parallel_dispatch_batches_both_arms_and_requires_two_proofs(
    seam, monkeypatch
):
    _enable_certified(monkeypatch)
    monkeypatch.setenv("PGFR_GROOT_PARALLEL_ENABLED", "1")
    monkeypatch.setenv("PGFR_GROOT_FLEXIBLE_ORDER", "1")
    _FakeSeam.dispatch_response = {
        "dispatched": True,
        "verified": True,
        "independent_b1_verified": True,
        "per_arm_relay_ports": {"franka_left": 5612, "franka_right": 5613},
        "parallel_results": {
            "franka_left": {"verified": True},
            "franka_right": {"verified": True},
        },
    }
    _FakeSeam.verify_response = {
        "answer": "yes",
        "evidence": "requested object visible in the requested tote",
    }

    dispatched = json.loads(server.dispatch_parallel("blue", "green"))
    assert dispatched["verified"] is True
    assert dispatched["independent_b1_verified"] is True
    assert dispatched["per_arm_relay_ports"] == {
        "franka_left": 5612,
        "franka_right": 5613,
    }
    assert dispatched["proof_gate"]["remaining_regions"] == ["tote", "tote_r"]
    path, payload = next(
        call for call in _FakeSeam.calls if call[0] == "/v1/dispatch-parallel"
    )
    assert path == "/v1/dispatch-parallel"
    assert [(move["endpoint"], move["source"]) for move in payload["moves"]] == [
        ("franka_left", "conveyor_1"),
        ("franka_right", "conveyor_2"),
    ]
    assert all(move["backend"] == "groot" for move in payload["moves"])

    first_proof = json.loads(
        server.verify("the blue cylinder is inside the left tote", region="tote")
    )
    assert first_proof["proof_gate"]["remaining_regions"] == ["tote_r"]
    blocked_duplicate = json.loads(
        server.verify("the blue cylinder is inside the left tote", region="tote")
    )
    assert blocked_duplicate["status"] == "refused"

    final_proof = json.loads(
        server.verify("the green brick is inside the right tote", region="tote_r")
    )
    assert final_proof["proof_gate"]["state"] == "cleared"
    assert server._PENDING_PROOF is None

    _FakeSeam.floor_state_response = {
        "tote": {"blue": "in"},
        "tote_r": {"green": "in"},
    }
    second = json.loads(server.dispatch_parallel("green", "red"))
    assert second["verified"] is True
    assert second["pending_visual_proof"]["pair_sequence"] == 2
    assert second["pending_visual_proof"]["sequence_start"] == 3
    assert second["pending_visual_proof"]["sequence_end"] == 4


def test_certified_mixed_order_rejects_wrong_partial_and_serialized_pairs(
    seam, monkeypatch
):
    _enable_certified(monkeypatch)
    monkeypatch.setenv("PGFR_GROOT_PARALLEL_ENABLED", "1")
    monkeypatch.setenv("PGFR_GROOT_FLEXIBLE_ORDER", "1")

    wrong = json.loads(server.dispatch_parallel("green", "red"))
    assert wrong["status"] == "refused"
    assert wrong["expected_colors"] == {
        "franka_left": "blue",
        "franka_right": "green",
    }
    assert [path for path, _payload in _FakeSeam.calls] == ["/v1/floor-state"]

    _FakeSeam.calls.clear()
    serialized = json.loads(server.dispatch_task(
        action="move",
        endpoint="franka_left",
        color="blue",
        source="conveyor_1",
        destination="tote_blue",
    ))
    assert serialized["status"] == "refused"
    assert "dispatch_parallel" in serialized["reason"]
    assert [path for path, _payload in _FakeSeam.calls] == ["/v1/floor-state"]

    _FakeSeam.calls.clear()
    _FakeSeam.floor_state_response = {
        "tote": {"blue": "in"},
        "tote_r": {},
    }
    partial = json.loads(server.dispatch_parallel("blue", "green"))
    assert partial["status"] == "refused"
    assert "partial certified concurrent pair" in partial["reason"]
    assert [path for path, _payload in _FakeSeam.calls] == ["/v1/floor-state"]

    _FakeSeam.calls.clear()
    _FakeSeam.floor_state_response = {"error": "ROS floor state unavailable"}
    unavailable = json.loads(server.dispatch_parallel("blue", "green"))
    assert unavailable["status"] == "refused"
    assert "fails closed" in unavailable["reason"]
    assert [path for path, _payload in _FakeSeam.calls] == ["/v1/floor-state"]


def test_certified_mixed_order_blocks_haul_until_all_pairs_complete(
    seam, monkeypatch
):
    _enable_certified(monkeypatch)
    monkeypatch.setenv("PGFR_GROOT_PARALLEL_ENABLED", "1")
    monkeypatch.setenv("PGFR_GROOT_FLEXIBLE_ORDER", "1")

    outcome = json.loads(server.dispatch_task(
        action="pick_and_place",
        endpoint="mobilebot",
        object_id="tote",
        target_id="rack_1",
    ))
    assert outcome["status"] == "refused"
    assert "only after all three certified mixed pairs" in outcome["reason"]
    assert [path for path, _payload in _FakeSeam.calls] == ["/v1/floor-state"]


def test_parallel_requires_certified_order_even_with_both_capability_flags(
    seam, monkeypatch
):
    monkeypatch.delenv("PGFR_CERTIFIED_GROOT_ORDER", raising=False)
    monkeypatch.setenv("PGFR_GROOT_PARALLEL_ENABLED", "1")
    monkeypatch.setenv("PGFR_GROOT_FLEXIBLE_ORDER", "1")

    outcome = json.loads(server.dispatch_parallel("blue", "green"))

    assert outcome["status"] == "refused"
    assert "PGFR_CERTIFIED_GROOT_ORDER=1" in outcome["reason"]
    assert _FakeSeam.calls == []


def test_certified_failed_action_retry_is_bounded(seam, monkeypatch):
    _enable_certified(monkeypatch)
    _FakeSeam.dispatch_response = {
        "dispatched": True,
        "verified": False,
        "reason": "object remains at source",
    }
    _FakeSeam.verify_response = {
        "answer": "yes",
        "evidence": "green brick remains on conveyor_2",
    }
    kwargs = {
        "action": "move",
        "endpoint": "franka_right",
        "color": "green",
        "source": "conveyor_2",
        "destination": "tote_green",
    }
    for attempt in (1, 2):
        outcome = json.loads(server.dispatch_task(**kwargs))
        assert outcome["pending_visual_proof"]["attempt"] == attempt
        proof = json.loads(server.verify(
            "the green brick is visibly still on conveyor_2",
            region="conveyor_2",
        ))
        assert proof["proof_gate"]["state"] == "cleared"
    refused = json.loads(server.dispatch_task(**kwargs))
    assert refused["status"] == "refused"
    assert refused["attempts"] == 2


def test_unreachable_seam_returns_error_json(monkeypatch):
    monkeypatch.setenv("PGFR_FLOOR_SERVICE", "http://127.0.0.1:1")
    out = json.loads(server.floor_state())
    assert "unreachable" in out["error"]


def test_dispatch_forwards_device_specific_args(seam, monkeypatch):
    monkeypatch.delenv("PGFR_CERTIFIED_GROOT_ORDER", raising=False)
    _FakeSeam.dispatch_response = {"dispatched": True, "verified": True}
    outcome = json.loads(server.dispatch_task(
        action="weld_seam",
        endpoint="welder_1",
        args={"seam_id": "s-12", "recipe_id": "r-4"},
    ))
    assert outcome["dispatched"] is True
    assert _FakeSeam.calls[-1] == (
        "/v1/dispatch",
        {
            "action": "weld_seam",
            "endpoint": "welder_1",
            "args": {"seam_id": "s-12", "recipe_id": "r-4"},
        },
    )


def test_instructions_carry_the_playbook():
    text = server._playbook()
    assert "ONE action at a time" in text or "one at a time" in text.lower()


def _first_move():
    return json.loads(server.dispatch_task(
        action="move", endpoint="franka_right", color="green",
        source="conveyor_2", destination="tote_green",
    ))


def _seed_pending_reset_scene(monkeypatch, reset_id="before"):
    _enable_certified(monkeypatch)
    _FakeSeam.floor_state_response["_meta"] = {"scene_reset_id": reset_id}
    _FakeSeam.dispatch_response = {
        "dispatched": True, "verified": True,
        "_meta": {"scene_reset_id": reset_id},
    }
    assert _first_move()["pending_visual_proof"]["attempt"] == 1


@pytest.mark.parametrize("initial_reset_id", [None, "before"])
def test_external_verified_reset_restarts_serial_proof_and_retry_state(
    seam, monkeypatch, initial_reset_id,
):
    _seed_pending_reset_scene(monkeypatch, initial_reset_id)
    previous_attempt = next(iter(server._DISPATCH_ATTEMPTS))
    server._DISPATCH_ATTEMPTS[previous_attempt] = 2
    _FakeSeam.floor_state_response["_meta"] = {"scene_reset_id": "after"}
    _FakeSeam.dispatch_response["_meta"] = {"scene_reset_id": "after"}

    result = _first_move()

    assert result["verified"] is True
    assert result["pending_visual_proof"]["attempt"] == 1
    assert result["pending_visual_proof"]["sequence"] == 1
    assert server._DISPATCH_ATTEMPTS == {previous_attempt: 1}
    assert server._LAST_CERTIFIED_PREFIX == 1
    assert all(payload.get("action") != "reset_scene" for _, payload in _FakeSeam.calls)
    # The next action in this new scene still requires its own visual proof.
    assert _first_move()["status"] == "refused"


@pytest.mark.parametrize("state", [
    {"tote": {}, "tote_r": {}, "_meta": {"scene_reset_id": "before"}},
    {"tote": {}, "tote_r": {}},
    {"tote": {}, "tote_r": {}, "_meta": {"scene_reset_id": None}},
    {"tote": {}, "tote_r": {}, "_meta": {"scene_reset_id": ""}},
    {"tote": {}, "tote_r": {}, "_meta": {"scene_reset_id": 1}},
    {"error": "floor service unavailable"},
    {"error": "failed read", "_meta": {"scene_reset_id": "untrusted"}},
])
def test_missing_unchanged_or_invalid_reset_marker_retains_guards(seam, monkeypatch, state):
    _seed_pending_reset_scene(monkeypatch)
    pending = server._PENDING_PROOF.copy()
    attempts = server._DISPATCH_ATTEMPTS.copy()
    prefix = server._LAST_CERTIFIED_PREFIX
    _FakeSeam.floor_state_response = state
    _FakeSeam.calls.clear()

    result = _first_move()

    assert result["status"] == "refused"
    assert server._PENDING_PROOF == pending
    assert server._DISPATCH_ATTEMPTS == attempts
    assert server._LAST_CERTIFIED_PREFIX == prefix
    assert _FakeSeam.calls == [("/v1/floor-state", {})]


def test_first_marker_after_legacy_response_is_not_reset_evidence(seam, monkeypatch):
    _enable_certified(monkeypatch)
    _FakeSeam.dispatch_response = {"dispatched": True, "verified": True}
    _first_move()
    _FakeSeam.floor_state_response["_meta"] = {"scene_reset_id": "already-existed"}
    assert _first_move()["status"] == "refused"
    assert _first_move()["status"] == "refused"


def test_external_reset_clears_exhausted_retries_without_pending_proof(seam, monkeypatch):
    _seed_pending_reset_scene(monkeypatch)
    server._PENDING_PROOF = None
    key = next(iter(server._DISPATCH_ATTEMPTS))
    server._DISPATCH_ATTEMPTS[key] = 2
    # Empty totes alone are not evidence that an operator reset succeeded.
    assert _first_move()["attempts"] == 2
    _FakeSeam.floor_state_response["_meta"]["scene_reset_id"] = "after"
    _FakeSeam.dispatch_response["_meta"]["scene_reset_id"] = "after"
    assert _first_move()["pending_visual_proof"]["attempt"] == 1


def test_dispatch_result_binds_proof_to_reset_between_preflight_and_motion(seam, monkeypatch):
    _enable_certified(monkeypatch)
    _FakeSeam.floor_state_response["_meta"] = {"scene_reset_id": "before"}
    _FakeSeam.dispatch_response = {
        "dispatched": True, "verified": False,
        "error": "motion did not complete",
        "_meta": {"scene_reset_id": "after"},
    }
    first = _first_move()
    assert first["pending_visual_proof"]["state"] == "awaiting_reconciliation"
    _FakeSeam.floor_state_response["_meta"]["scene_reset_id"] = "after"
    assert _first_move()["status"] == "refused"
    assert server._PENDING_PROOF == first["pending_visual_proof"]


def test_external_reset_clears_parallel_proofs_and_retries(seam, monkeypatch):
    _enable_certified(monkeypatch)
    monkeypatch.setenv("PGFR_GROOT_PARALLEL_ENABLED", "1")
    monkeypatch.setenv("PGFR_GROOT_FLEXIBLE_ORDER", "1")
    _FakeSeam.floor_state_response["_meta"] = {"scene_reset_id": "before"}
    _FakeSeam.dispatch_response = {
        "dispatched": True, "verified": True, "independent_b1_verified": True,
        "_meta": {"scene_reset_id": "before"},
    }
    first = json.loads(server.dispatch_parallel("blue", "green"))
    assert first["pending_visual_proof"]["remaining_regions"] == ["tote", "tote_r"]
    server._DISPATCH_ATTEMPTS[("move_pair", "blue", "green")] = 2
    _FakeSeam.floor_state_response["_meta"]["scene_reset_id"] = "after"
    _FakeSeam.dispatch_response["_meta"]["scene_reset_id"] = "after"
    result = json.loads(server.dispatch_parallel("blue", "green"))
    assert result["verified"] is True
    assert result["pending_visual_proof"]["attempt"] == 1
    assert result["pending_visual_proof"]["remaining_regions"] == ["tote", "tote_r"]
    assert json.loads(server.dispatch_parallel("blue", "green"))["status"] == "refused"


@pytest.mark.parametrize("reset_during_verify", [False, True])
def test_verification_after_reset_does_not_claim_to_prove_old_action(
    seam, monkeypatch, reset_during_verify,
):
    _seed_pending_reset_scene(monkeypatch)
    if not reset_during_verify:
        _FakeSeam.floor_state_response["_meta"]["scene_reset_id"] = "after"
    _FakeSeam.verify_response = {
        "answer": "yes", "evidence": "current scene",
        "_meta": {"scene_reset_id": "after"},
    }
    out = json.loads(server.verify("the green brick is in the right tote", region="tote_r"))
    assert out["answer"] == "yes"
    assert "proof_gate" not in out
    assert server._PENDING_PROOF is None
    assert server._DISPATCH_ATTEMPTS == {}
    assert server._LAST_CERTIFIED_PREFIX is None


@pytest.mark.parametrize("outcome", [
    {"verified": True},
    {"dispatched": False, "verified": True},
    {"dispatched": True, "verified": False},
    {"dispatched": True, "verified": True, "status": "refused"},
    {"dispatched": True, "verified": True, "status": "uncertain"},
    {"dispatched": True, "verified": True, "status": "running"},
    {"dispatched": True, "verified": True, "status": "queued"},
    {"dispatched": True, "verified": True, "delivery_uncertain": True},
    {"dispatched": True, "verified": True, "transport_error": True},
    {"dispatched": True, "verified": True, "error": "contradictory result"},
])
def test_native_reset_requires_unambiguous_success_before_clearing(seam, monkeypatch, outcome):
    _seed_pending_reset_scene(monkeypatch)
    pending = server._PENDING_PROOF.copy()
    attempts = server._DISPATCH_ATTEMPTS.copy()
    _FakeSeam.dispatch_response = {**outcome, "_meta": {"scene_reset_id": "untrusted"}}
    server.reset_scene()
    assert server._PENDING_PROOF == pending
    assert server._DISPATCH_ATTEMPTS == attempts
    assert server._SCENE_RESET_ID == "before"


@pytest.mark.parametrize("status_code", [400, 500])
def test_http_failure_cannot_clear_policy_state_even_with_success_json(
    seam, monkeypatch, status_code,
):
    _seed_pending_reset_scene(monkeypatch)
    pending = server._PENDING_PROOF.copy()
    _FakeSeam.status_code = status_code
    _FakeSeam.dispatch_response = {
        "dispatched": True, "verified": True,
        "_meta": {"api": "v1", "scene_reset_id": "untrusted"},
    }
    result = json.loads(server.reset_scene())
    assert result["verified"] is False
    assert result["_meta"] == {"api": "v1"}
    assert server._PENDING_PROOF == pending
    assert server._SCENE_RESET_ID == "before"
    # An error reading state must not clear proof either.
    _FakeSeam.floor_state_response = {
        "tote": {}, "tote_r": {}, "_meta": {"scene_reset_id": "untrusted"},
    }
    assert _first_move()["status"] == "refused"
    assert server._PENDING_PROOF == pending
