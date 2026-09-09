# policy-gated-factory-robot-orchestrator-reference-mcp

The floor seam's tools — `floor_state`, `perceive`, `dispatch_task`,
`dispatch_parallel`, `certified_groot_sequence`, `reset_scene`, `verify`,
`mission_history`, and `mission_detail` — exposed as an MCP server (stdio). Any
MCP client (OpenClaw, Claude Code, Claude Desktop, NIM agents) connects and
receives, in one handshake, both the tools and the operating manual:
`skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/PLAYBOOK.md` ships verbatim as the server
`instructions`.

Thin by design: tools proxy the floor service (`IC_FLOOR_SERVICE`, default
`http://127.0.0.1:8766`). Execution authority and physical safety remain at the
Seam. When `IC_CERTIFIED_GROOT_ORDER=1`, this MCP boundary additionally enforces
the validated serial six-move fallback, the configured GR00T backend, one fresh
exact-object visual proof between physical actions, and at most one retry. The
optional certified concurrent plan is the separately qualified Order744
sequence: left blue/right green, left green/right red, then left red/right
blue. It is never synthesized by grouping the serial fallback by color.

## Run (on the brain host, next to the serve)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                    # unit tests (fake seam, no ROS needed)
.venv/bin/ic-mcp                    # stdio server
```

## Connect Claude Code from another machine

```bash
claude mcp add ic-floor -- ssh jetson@<thor-ip> ~/Policy-Gated-Factory-Robot-Orchestrator-Reference/servers/policy-gated-factory-robot-orchestrator-reference-mcp/.venv/bin/ic-mcp
```

Then give a session a goal like *"Tidy the conveyor, then shelve the tote"* — the
playbook arrives via instructions; no profile setup, no sync scripts.

## Env

- `IC_FLOOR_SERVICE` — floor service base URL (default `http://127.0.0.1:8766`)
- `IC_MCP_TIMEOUT_S` — per-call HTTP timeout (default 280; hauls take ~2.5 min)
- `IC_MCP_ROLE` — Seam role header (default `agent`; operator use must be explicit)
- `IC_DEFAULT_BACKEND` — deployment-selected arm executor (`groot` in the hardened demo)
- `IC_CERTIFIED_GROOT_ORDER=1` — enable certified order/proof/retry enforcement
- `IC_GROOT_PARALLEL_ENABLED=1` — assert that the independent two-server B=1
  readiness contract passed; required for any atomic two-arm transaction
- `IC_GROOT_FLEXIBLE_ORDER=1` — together with certified-order and parallel
  mode, select the exact three-pair mixed Order744 plan while retaining the
  same proof/retry gates; leave disabled for the serial fallback

All three settings default to `0` in the MCP process. With certified-order
enforcement enabled but either concurrent flag disabled,
`certified_groot_sequence` reports and enforces the unchanged serial fallback.
With all three enabled, it reports the exact mixed transactions, rejects a
wrong or partial pair before motion, rejects same-color pairs, and refuses to
expand a pair into serial `dispatch_task` calls. The Seam independently checks
the same exact next-pair order from authoritative floor state.
