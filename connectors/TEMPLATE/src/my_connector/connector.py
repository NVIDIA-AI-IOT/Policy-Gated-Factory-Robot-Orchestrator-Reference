# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TEMPLATE connector — copy this directory, rename `my_connector`, wrap your system.

A connector is the brain's reach INTO an enterprise system (video analytics,
MES/ERP, quality DBs). It provides context and evidence; it never dispatches
floor actions — that authority stays at the seam.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pgfr_connector_sdk import CapabilitySpec, Connector


class MyConnector(Connector):
    name = "my-system"          # RENAME: e.g. "vss-video", "sap-mes"
    version = "0.1.0"

    def __init__(self, endpoint: str | None = None) -> None:
        self._endpoint = endpoint   # your system's URL/credentials via env, not code

    def health(self) -> dict[str, Any]:
        # Ask the wrapped system, honestly: reachable? how stale is its data?
        return {"ok": True, "endpoint": self._endpoint or "unset", "data_age_s": None}

    def capabilities(self) -> list[CapabilitySpec]:
        return [
            CapabilitySpec(
                name="query_events",
                description="REPLACE ME: what question does this answer, over what time range?",
                params_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {"query": {"type": "string"},
                                   "since_minutes": {"type": "integer", "default": 60}},
                },
            ),
        ]

    def call(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        if capability == "query_events":
            return {
                "events": [],   # REPLACE ME: real results from your system
                "source": self.name,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        raise KeyError(capability)
