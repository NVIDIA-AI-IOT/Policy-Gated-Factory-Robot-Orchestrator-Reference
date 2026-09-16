# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit store phase 2 — SQLite over the mission journal (stdlib only).

The JSONL journal remains the crash-safe write-ahead source of truth; this store
is DERIVED from it (rebuildable at any time) and answers queries: mission
summaries, per-mission operation timelines, success rates. Retention: rows,
evidence frames, and journal segments older than PGFR_JOURNAL_RETENTION_DAYS
(default 30) are pruned.

Read paths: the seam's GET /v1/missions[..] routes -> the MCP mission_history
tool. Nothing here blocks a floor op: ingest is incremental (byte offset) and
runs on query.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS operations (
    request_id TEXT PRIMARY KEY,
    mission_id TEXT,
    ts TEXT NOT NULL,
    op TEXT NOT NULL,
    action TEXT,
    endpoint TEXT,
    request TEXT NOT NULL,
    result TEXT NOT NULL,
    verified INTEGER,
    duration_s REAL,
    frame TEXT
);
CREATE INDEX IF NOT EXISTS idx_ops_mission ON operations (mission_id, ts);
CREATE INDEX IF NOT EXISTS idx_ops_ts ON operations (ts);
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    ops INTEGER NOT NULL,
    dispatches INTEGER NOT NULL,
    verified_dispatches INTEGER NOT NULL,
    last_reason TEXT
);
"""


class Store:
    def __init__(self, root: str) -> None:
        self.root = Path(root).expanduser()
        self.journal = self.root / "journal.jsonl"
        self.db_path = self.root / "pgfr.db"
        self.retention_days = float(os.environ.get("PGFR_JOURNAL_RETENTION_DAYS", "30"))
        self.root.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ---- ingest (incremental, offset-tracked) ---------------------------------
    def ingest(self) -> int:
        if not self.journal.exists():
            return 0
        cur = self._db.execute("SELECT value FROM meta WHERE key='journal_offset'").fetchone()
        offset = int(cur[0]) if cur else 0
        size = self.journal.stat().st_size
        if size < offset:      # journal rotated/rebuilt -> re-ingest
            offset = 0
        if size == offset:
            return 0
        n = 0
        with open(self.journal) as f:
            f.seek(offset)
            for line in f:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                self._insert(e)
                n += 1
            offset = f.tell()
        self._db.execute("INSERT OR REPLACE INTO meta VALUES ('journal_offset', ?)", (str(offset),))
        self._db.commit()
        self._maybe_prune()
        return n

    def _insert(self, e: dict[str, Any]) -> None:
        req = e.get("request") or {}
        res = e.get("result") or {}
        verified = res.get("verified")
        self._db.execute(
            "INSERT OR REPLACE INTO operations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (e.get("request_id"), e.get("mission_id"), e.get("ts"), e.get("op"),
             req.get("action") or req.get("target") or req.get("predicate"),
             req.get("endpoint"),
             json.dumps(req), json.dumps(res),
             None if verified is None else int(bool(verified)),
             e.get("duration_s"), e.get("frame")))
        mid = e.get("mission_id")
        if mid:
            is_dispatch = 1 if e.get("op") == "dispatch" else 0
            self._db.execute(
                """INSERT INTO missions VALUES (?,?,?,1,?,?,?)
                   ON CONFLICT(mission_id) DO UPDATE SET
                     ended_at=excluded.ended_at,
                     ops=ops+1,
                     dispatches=dispatches+excluded.dispatches,
                     verified_dispatches=verified_dispatches+excluded.verified_dispatches,
                     last_reason=excluded.last_reason""",
                (mid, e.get("ts"), e.get("ts"), is_dispatch,
                 1 if (is_dispatch and verified) else 0,
                 str(res.get("reason") or "")[:200]))

    # ---- retention -------------------------------------------------------------
    def _maybe_prune(self) -> None:
        cur = self._db.execute("SELECT value FROM meta WHERE key='last_prune'").fetchone()
        if cur and time.time() - float(cur[0]) < 86400:
            return
        self.prune()
        self._db.execute("INSERT OR REPLACE INTO meta VALUES ('last_prune', ?)", (str(time.time()),))
        self._db.commit()

    def prune(self) -> int:
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=self.retention_days)).isoformat()
        old = self._db.execute("SELECT frame FROM operations WHERE ts < ?", (cutoff,)).fetchall()
        for (frame,) in old:
            if frame:
                try:
                    (self.root / frame).unlink(missing_ok=True)
                except Exception:
                    pass
        n = self._db.execute("DELETE FROM operations WHERE ts < ?", (cutoff,)).rowcount
        self._db.execute("DELETE FROM missions WHERE ended_at < ?", (cutoff,))
        self._db.commit()
        return n

    # ---- queries ----------------------------------------------------------------
    def missions(self, limit: int = 20) -> list[dict[str, Any]]:
        self.ingest()
        rows = self._db.execute(
            """SELECT mission_id, started_at, ended_at, ops, dispatches,
                      verified_dispatches, last_reason
               FROM missions ORDER BY ended_at DESC LIMIT ?""", (limit,)).fetchall()
        return [{"mission_id": r[0], "started_at": r[1], "ended_at": r[2],
                 "ops": r[3], "dispatches": r[4], "verified_dispatches": r[5],
                 "last_reason": r[6]} for r in rows]

    def operations(self, mission_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self.ingest()
        cols = ("SELECT ts,op,action,endpoint,result,verified,duration_s,frame,"
                "request_id,mission_id,request FROM operations ")
        if mission_id:
            rows = self._db.execute(
                cols + "WHERE mission_id=? ORDER BY ts LIMIT ?", (mission_id, limit)).fetchall()
        else:
            rows = self._db.execute(
                cols + "ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            res = json.loads(r[4])
            try:
                req = json.loads(r[10]) if r[10] else {}
            except Exception:
                req = {}
            out.append({"ts": r[0], "op": r[1], "action": r[2], "endpoint": r[3],
                        "verified": None if r[5] is None else bool(r[5]),
                        "reason": res.get("reason") or (res.get("vision") or {}).get("summary"),
                        "duration_s": r[6], "frame": r[7], "request_id": r[8],
                        "mission_id": r[9], "request": req, "result": res})
        return out
