# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for RunRecorder — writes events.jsonl, plan.json, and frames to a run directory."""
from __future__ import annotations

import json
from pathlib import Path

from industrial_claw.runs.recorder import RunRecorder


def test_recorder_creates_run_directory(tmp_path: Path) -> None:
    rec = RunRecorder(base_dir=tmp_path, mission_id="abc123")
    rec.write_plan([{"kind": "action", "endpoint_id": "ep1", "capability": "navigate_to", "args": {}}])
    rec.event("subtask_start", {"index": 0})
    rec.close()

    run_dir = tmp_path / "abc123"
    assert (run_dir / "plan.json").exists()
    assert (run_dir / "events.jsonl").exists()

    plan = json.loads((run_dir / "plan.json").read_text())
    assert plan[0]["endpoint_id"] == "ep1"

    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
    assert events[0]["type"] == "subtask_start"


def test_recorder_writes_frame(tmp_path: Path) -> None:
    rec = RunRecorder(base_dir=tmp_path, mission_id="abc")
    rec.write_frame(camera_id="cam_1", image_bytes=b"\xff\xd8\xff\xe0sample-jpeg")
    rec.close()
    frames = list((tmp_path / "abc" / "frames").iterdir())
    assert len(frames) == 1
    assert frames[0].name.startswith("cam_1-")


def test_recorder_event_ordering(tmp_path: Path) -> None:
    rec = RunRecorder(base_dir=tmp_path, mission_id="ord")
    rec.event("a", {"i": 0})
    rec.event("b", {"i": 1})
    rec.event("c", {"i": 2})
    rec.close()
    events = [json.loads(line) for line in (tmp_path / "ord" / "events.jsonl").read_text().splitlines()]
    assert [e["type"] for e in events] == ["a", "b", "c"]
