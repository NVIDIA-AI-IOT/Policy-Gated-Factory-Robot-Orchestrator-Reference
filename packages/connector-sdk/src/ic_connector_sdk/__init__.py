# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ic-connector-sdk — the contract for systems the brain reaches OUT to (T5 era).

A connector wraps an external system (VSS video analytics, MES/ERP, quality DBs)
and exposes it to the backbone as typed, read-mostly capabilities. The backbone
re-exposes those northbound as MCP tools — a connector never talks to a brain
directly and never dispatches floor actions.

Implement `Connector`, then prove it with `assert_connector_compliant` in your
tests (the certification bar the templates ship with).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__version__ = "0.1.0"


@dataclass
class CapabilitySpec:
    """One callable capability: its name, docs, and JSON-schema params contract."""

    name: str
    description: str
    params_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    read_only: bool = True


class Connector:
    """Base class. Subclass and implement: name, version, health, capabilities, call."""

    name: str = "REPLACE_ME"
    version: str = "0.0.0"

    def health(self) -> dict[str, Any]:
        """Liveness + signal freshness of the wrapped system.
        Must include: {"ok": bool}. Add ages/latency — never lie, never hang."""
        raise NotImplementedError

    def capabilities(self) -> list[CapabilitySpec]:
        raise NotImplementedError

    def call(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute one capability. Must raise KeyError for unknown capabilities.
        Results are DATA with provenance: include a 'source' and a timestamp."""
        raise NotImplementedError


def assert_connector_compliant(conn: Connector) -> None:
    """The compliance bar: run this in your connector's test suite."""
    assert conn.name and conn.name != "REPLACE_ME", "set a real connector name"
    assert conn.version and conn.version != "0.0.0", "set a real version"
    h = conn.health()
    assert isinstance(h, dict) and isinstance(h.get("ok"), bool), "health() must return {'ok': bool, ...}"
    caps = conn.capabilities()
    assert caps, "a connector with no capabilities is a mistake"
    for c in caps:
        assert c.name and c.description, f"capability {c.name!r} needs a description"
        assert isinstance(c.params_schema, dict) and c.params_schema.get("type") == "object", \
            f"capability {c.name!r} needs an object params_schema"
    try:
        conn.call("__no_such_capability__", {})
        raise AssertionError("call() must raise KeyError for unknown capabilities")
    except KeyError:
        pass
