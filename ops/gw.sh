#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Start only the Policy-Gated Factory Robot Orchestrator Reference OpenClaw gateway.
#
# The Seam is a separately supervised service. This launcher deliberately
# refuses to create or replace it: one process owns each port, and one service
# manager owns each process.
set -euo pipefail

export NODE_USE_SYSTEM_CA=1
IC_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IC_OPENCLAW_GATEWAY_PORT="${IC_OPENCLAW_GATEWAY_PORT:-18790}"
export IC_FLOOR_SERVICE="${IC_FLOOR_SERVICE:-http://127.0.0.1:8766}"

if ! curl --fail --silent --show-error --max-time 5 \
  "$IC_FLOOR_SERVICE/v1/health" >/dev/null; then
  echo "Policy-Gated Factory Robot Orchestrator Reference Seam is unavailable at $IC_FLOOR_SERVICE." >&2
  echo "Start the canonical ic-seam.service, then retry; this launcher will not spawn a duplicate." >&2
  exit 3
fi

# A direct invocation may source credentials. systemd supplies the same file
# independently; never put secrets in a tracked env template.
if [ -f "$HOME/.openclaw/secrets.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$HOME/.openclaw/secrets.env"
  set +a
fi

# Journal + evidence frames: the audit trail the console's mission replay and
# Inspector read. It was only ever set by a hand-made /tmp env file, so any
# restart that missed that file silently disabled the audit trail (and the
# frames the chat renders). Pin it here — versioned, survives reboots — while
# still honoring an explicit override.
export IC_JOURNAL_DIR="${IC_JOURNAL_DIR:-$HOME/ic-journal}"
mkdir -p "$IC_JOURNAL_DIR/frames"


# --- Standalone runtime: the installed openclaw dependency, isolated state ---
# OPENCLAW_STATE_DIR + OPENCLAW_CONFIG_PATH keep this gateway's config and
# sessions fully separate from any classic deployment's ~/.openclaw. First
# start seeds a minimal config that connects OpenClaw to the governed floor MCP
# server. The MCP process is owned by OpenClaw and proxies only to the Seam.
export OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-$HOME/.policy-gated-factory-robot-orchestrator-reference/openclaw}"
export OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$OPENCLAW_STATE_DIR/openclaw.json}"
IC_MCP_BIN="${IC_MCP_BIN:-$IC_REPO/servers/policy-gated-factory-robot-orchestrator-reference-mcp/.venv/bin/ic-mcp}"
mkdir -p "$OPENCLAW_STATE_DIR"
if [ ! -x "$IC_MCP_BIN" ]; then
  echo "IC MCP server not installed — run: (cd $IC_REPO/servers/policy-gated-factory-robot-orchestrator-reference-mcp && python3 -m venv .venv && .venv/bin/pip install -e .)" >&2
  exit 2
fi
if [ ! -f "$OPENCLAW_CONFIG_PATH" ]; then
  sed "s#__MCP_COMMAND__#$IC_MCP_BIN#" \
    "$IC_REPO/ops/openclaw.template.json" > "$OPENCLAW_CONFIG_PATH"
fi
OPENCLAW_BIN="$IC_REPO/node_modules/.bin/openclaw"
if [ ! -x "$OPENCLAW_BIN" ]; then
  echo "openclaw runtime not installed — run: (cd $IC_REPO && npm ci)" >&2
  exit 2
fi
exec "$OPENCLAW_BIN" gateway --port "$IC_OPENCLAW_GATEWAY_PORT" "$@"
