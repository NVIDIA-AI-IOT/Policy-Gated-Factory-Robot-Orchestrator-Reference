# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TEMPLATE MCP server — copy this directory, rename `my_mcp`, fill in the tools.

The three non-negotiables (the `ic-conformance mcp` check enforces them):
1. `instructions` is non-empty — ship your operating doctrine in the handshake.
2. Every tool has a docstring (the model reads it) AND ToolAnnotations
   (title + readOnlyHint — clients render and gate on these).
3. Tools return DATA (JSON strings), not prose — the model does the talking.

Backing your tools with HTTP? Point at a certified seam (`ic-conformance run`)
and pass through its results untouched — never invent success the seam didn't
report. See servers/policy-gated-factory-robot-orchestrator-reference-mcp for the reference implementation.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


def _instructions() -> str:
    """Load your doctrine from a versioned file — never hardcode prose here."""
    doc = Path(__file__).resolve().parent / "INSTRUCTIONS.md"
    if doc.exists():
        return doc.read_text()
    return "REPLACE ME: ship the operating playbook for your domain in the handshake."


_MISSION_ID = "tmpl-" + uuid.uuid4().hex[:12]   # journal grouping, one per session

mcp = FastMCP(os.environ.get("MY_MCP_NAME", "my-domain"), instructions=_instructions())


@mcp.tool(annotations=ToolAnnotations(title="Domain: read something", readOnlyHint=True))
def read_something(query: str) -> str:
    """One-line summary the model will read. State inputs, outputs, and limits."""
    return json.dumps({"query": query, "answer": "REPLACE ME"})


@mcp.tool(annotations=ToolAnnotations(
    title="Domain: do something (has real effects)",
    readOnlyHint=False, destructiveHint=False, idempotentHint=False))
def do_something(target: str) -> str:
    """Effects must be verified before you report them — return the evidence."""
    return json.dumps({"target": target, "done": False, "verified": False,
                       "reason": "REPLACE ME: never claim unverified success"})


def main() -> None:
    mcp.run()   # stdio


if __name__ == "__main__":
    main()
