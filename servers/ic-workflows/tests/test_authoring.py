# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NL authoring assistant: valid draft passes, invalid retries then fails,
operator actions can't slip through, and the endpoint is CSRF-guarded."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from ic_workflows.app import Store, build_app
from ic_workflows.authoring import author

HDR = {"x-ic-workflows": "console"}


class JsonBackend:
    """Returns a scripted sequence of assistant contents (model stand-in)."""

    name = "json"

    def __init__(self, contents: List[str]) -> None:
        self.contents = list(contents)
        self.seen: List[List[Dict[str, Any]]] = []

    async def respond(self, messages, tools):
        self.seen.append(messages)
        return {"content": self.contents.pop(0) if self.contents else "{}", "tool_calls": []}


GOOD_WF = json.dumps({
    "name": "sort-red",
    "description": "move the red cube to the tote and verify",
    "params": {},
    "steps": [
        {"tool": "perceive", "args": {"target": "conveyor_1"}},
        {"tool": "dispatch_task", "args": {
            "action": "move", "endpoint": "franka_left", "color": "red",
            "source": "conveyor_1", "destination": "tote"}},
        {"tool": "check_predicate", "args": {"predicate": "the red cube is in the tote"}},
    ],
    "done_criteria": "red cube physically in the tote",
})
GOOD_SKILL = json.dumps({
    "name": "sort-cubes", "version": "0.1.0", "description": "sort cubes into totes",
    "requires_tools": ["perceive", "dispatch_task", "check_predicate"],
    "allowed_actions": ["move"], "done_criteria": "each cube in its matching tote",
})


class TestAuthor:
    async def test_valid_workflow_first_try(self) -> None:
        out = await author(JsonBackend([GOOD_WF]), "workflow", "move red to tote")
        assert out["ok"] is True
        assert out["draft"]["name"] == "sort-red"
        assert out["attempts"] == 1

    async def test_fenced_json_is_tolerated(self) -> None:
        out = await author(JsonBackend([f"```json\n{GOOD_WF}\n```"]), "workflow", "x")
        assert out["ok"] is True

    async def test_invalid_then_valid_retries(self) -> None:
        bad = json.dumps({"name": "Bad Name", "steps": []})  # bad name + empty steps
        b = JsonBackend([bad, GOOD_WF])
        out = await author(b, "workflow", "x")
        assert out["ok"] is True and out["attempts"] == 2
        # the validation error was fed back to the model
        assert any("did not pass the schema" in m["content"]
                   for msgs in b.seen for m in msgs if m["role"] == "user")

    async def test_operator_action_rejected(self) -> None:
        bad = json.dumps({
            "name": "danger", "description": "d",
            "steps": [{"tool": "dispatch_task",
                       "args": {"action": "reset", "endpoint": "franka_left"}}],
            "done_criteria": "d"})
        out = await author(JsonBackend([bad, bad, bad]), "workflow", "reset the arm")
        assert out["ok"] is False
        assert "agent-class" in out["error"] or "not agent-class" in out["error"]

    async def test_non_json_output_fails_cleanly(self) -> None:
        out = await author(JsonBackend(["I cannot help", "still prose"]), "workflow", "x", max_attempts=2)
        assert out["ok"] is False
        assert "not JSON" in out["error"]

    async def test_skill_nondict_output_retries_not_crash(self) -> None:
        # bare array / non-object skill output must retry cleanly, not 502
        out = await author(JsonBackend(["[1,2,3]", "42"]), "skill", "x", max_attempts=2)
        assert out["ok"] is False
        assert "object" in out["error"] or "JSON" in out["error"]

    async def test_skill_unhashable_actions_retries_not_crash(self) -> None:
        bad = json.dumps({"name": "x", "version": "0.1.0", "description": "d",
                          "requires_tools": ["perceive"], "allowed_actions": [["move"]],
                          "done_criteria": "d"})
        out = await author(JsonBackend([bad, bad]), "skill", "x", max_attempts=2)
        assert out["ok"] is False
        assert "list of strings" in out["error"]

    async def test_skill_unknown_tool_refused(self) -> None:
        bad = json.dumps({"name": "x", "version": "0.1.0", "description": "d",
                          "requires_tools": ["teleport"], "allowed_actions": ["move"],
                          "done_criteria": "d"})
        out = await author(JsonBackend([bad, bad]), "skill", "x", max_attempts=2)
        assert out["ok"] is False
        assert "known tools" in out["error"]

    async def test_valid_skill(self) -> None:
        out = await author(JsonBackend([GOOD_SKILL]), "skill", "a cube sorter skill")
        assert out["ok"] is True
        assert out["draft"]["allowed_actions"] == ["move"]

    async def test_skill_operator_action_rejected(self) -> None:
        bad = json.dumps({"name": "x", "version": "0.1.0", "description": "d",
                          "requires_tools": ["dispatch_task"], "allowed_actions": ["reset"],
                          "done_criteria": "d"})
        out = await author(JsonBackend([bad, bad]), "skill", "x", max_attempts=2)
        assert out["ok"] is False


class TestAssistAPI:
    def make_client(self, tmp_path: Path, backend):
        return TestClient(build_app(
            store=Store(tmp_path / "wf"), skills_dir=tmp_path / "sk", backend=backend))

    def test_assist_requires_csrf_header(self, tmp_path: Path) -> None:
        client = self.make_client(tmp_path, JsonBackend([GOOD_WF]))
        r = client.post("/api/assist", json={"kind": "workflow", "instruction": "x"})
        assert r.status_code == 403

    def test_assist_returns_validated_draft(self, tmp_path: Path) -> None:
        client = self.make_client(tmp_path, JsonBackend([GOOD_WF]))
        r = client.post("/api/assist", json={"kind": "workflow", "instruction": "move red"},
                        headers=HDR)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] and body["draft"]["name"] == "sort-red"

    def test_instruction_length_bounded(self, tmp_path: Path) -> None:
        client = self.make_client(tmp_path, JsonBackend([GOOD_WF]))
        r = client.post("/api/assist",
                        json={"kind": "workflow", "instruction": "x" * 9000}, headers=HDR)
        assert r.status_code == 422  # exceeds max_length, rejected before the model

    def test_bad_kind_rejected(self, tmp_path: Path) -> None:
        client = self.make_client(tmp_path, JsonBackend([GOOD_WF]))
        r = client.post("/api/assist",
                        json={"kind": "malware", "instruction": "x"}, headers=HDR)
        assert r.status_code == 422

    def test_assist_no_backend_503(self, tmp_path: Path) -> None:
        client = self.make_client(tmp_path, None)
        r = client.post("/api/assist", json={"kind": "workflow", "instruction": "x"}, headers=HDR)
        assert r.status_code == 503

    def test_drafted_workflow_saves_through_normal_endpoint(self, tmp_path: Path) -> None:
        # end-to-end: assistant draft -> save via the (re-validating) PUT
        client = self.make_client(tmp_path, JsonBackend([GOOD_WF]))
        draft = client.post("/api/assist", json={"kind": "workflow", "instruction": "x"},
                            headers=HDR).json()["draft"]
        saved = client.put(f"/api/workflows/{draft['name']}", json=draft, headers=HDR)
        assert saved.status_code == 200
