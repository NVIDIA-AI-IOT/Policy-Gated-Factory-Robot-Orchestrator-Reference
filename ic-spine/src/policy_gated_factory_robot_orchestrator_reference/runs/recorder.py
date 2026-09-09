# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""RunRecorder — append-only event sink for one mission."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, TextIO


class RunRecorder:
    """Writes per-mission artifacts to ``{base_dir}/{mission_id}/``:

    * ``plan.json`` — the validated plan list (written once via ``write_plan``)
    * ``events.jsonl`` — append-only stream of events, one JSON object per line
    * ``frames/{camera_id}-NNNN.{suffix}`` — VLM-consulted images

    Designed to survive a crash mid-mission: each event flush is independently
    valid; the only data loss possible is a single in-flight line.
    """

    def __init__(self, base_dir: Path, mission_id: str) -> None:
        self._dir = Path(base_dir).expanduser() / mission_id
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / "frames").mkdir(exist_ok=True)
        self._events_fp: TextIO | None = open(
            self._dir / "events.jsonl", "a", encoding="utf-8"
        )
        self._frame_counter = 0

    @property
    def directory(self) -> Path:
        return self._dir

    def write_plan(self, plan_items: list[dict[str, Any]]) -> None:
        (self._dir / "plan.json").write_text(json.dumps(plan_items, indent=2))

    def event(self, type_: str, payload: dict[str, Any]) -> None:
        if self._events_fp is None:
            raise RuntimeError("RunRecorder already closed")
        record = {"ts": time.time(), "type": type_, **payload}
        self._events_fp.write(json.dumps(record) + "\n")
        self._events_fp.flush()

    def write_frame(self, camera_id: str, image_bytes: bytes, suffix: str = "jpg") -> Path:
        self._frame_counter += 1
        path = self._dir / "frames" / f"{camera_id}-{self._frame_counter:04d}.{suffix}"
        path.write_bytes(image_bytes)
        return path

    def close(self) -> None:
        if self._events_fp is not None:
            self._events_fp.close()
            self._events_fp = None
