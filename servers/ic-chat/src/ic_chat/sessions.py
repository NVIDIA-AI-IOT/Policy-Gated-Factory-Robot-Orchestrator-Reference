# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persistent chat sessions — history survives restart, listable, deletable.

Each session is one JSON file named by its id (id validated against traversal).
Display history is capped (max_history) to bound file size; the model context
window is sliced separately at call time. Oldest sessions are evicted past
max_sessions. Single-operator, loopback posture — no per-user ownership.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SessionStore:
    def __init__(self, root: str, max_sessions: int = 200, max_history: int = 200) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_sessions = max_sessions
        self.max_history = max_history

    def _path(self, sid: str) -> Path:
        if not _ID_RE.match(sid):
            raise ValueError(f"bad session id: {sid!r}")
        return self.root / f"{sid}.json"

    def _read(self, sid: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(self._path(sid).read_text())
        except (FileNotFoundError, ValueError):
            return None

    def get(self, sid: str) -> Optional[Dict[str, Any]]:
        return self._read(sid)

    def get_or_create(self, sid: str) -> Dict[str, Any]:
        if sid:
            existing = self._read(sid)
            if existing:
                return existing
            if not _ID_RE.match(sid):
                sid = ""  # ignore a malformed client id, mint a fresh one
        new_id = sid or uuid.uuid4().hex[:16]
        now = time.time()
        sess = {
            "id": new_id,
            "mission_id": f"chat-{new_id}",
            "title": "New chat",
            "created": now,
            "updated": now,
            "history": [],
        }
        self.save(sess)
        return sess

    def save(self, sess: Dict[str, Any]) -> None:
        sess["updated"] = time.time()
        hist = sess.get("history", [])
        if len(hist) > self.max_history:
            sess["history"] = hist[-self.max_history:]
        # title from the first user line if still default
        if sess.get("title", "New chat") == "New chat":
            first = next((m["content"] for m in sess["history"] if m.get("role") == "user"), "")
            if first:
                sess["title"] = (first[:48] + "…") if len(first) > 48 else first
        self._path(sess["id"]).write_text(json.dumps(sess))
        self._evict()

    def _evict(self) -> None:
        files = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[self.max_sessions:]:
            p.unlink(missing_ok=True)

    def list(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for p in self.root.glob("*.json"):
            try:
                s = json.loads(p.read_text())
            except (ValueError, OSError):
                continue
            out.append({
                "id": s.get("id", p.stem),
                "mission_id": s.get("mission_id", f"chat-{s.get('id', p.stem)}"),
                "backend": s.get("backend", "traditional"),
                "title": s.get("title", "chat"),
                "created": s.get("created", 0),
                "updated": s.get("updated", 0),
                "messages": len(s.get("history", [])),
            })
        out.sort(key=lambda s: s["updated"], reverse=True)
        return out

    def delete(self, sid: str) -> bool:
        try:
            path = self._path(sid)
        except ValueError:
            return False
        if path.exists():
            path.unlink()
            return True
        return False
