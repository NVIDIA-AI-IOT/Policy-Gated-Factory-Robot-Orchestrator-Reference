# PGFR floor MCP server

This package exposes PGFR Spine through a standard input/output MCP server. It is
a thin client of `PGFR_FLOOR_SERVICE`, which defaults to
`http://127.0.0.1:8766`. Action policy and physical verification remain in PGFR
Spine.

When run from this checkout, the server sends the reference
[`PLAYBOOK.md`](../../skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/PLAYBOOK.md)
as MCP handshake instructions. A standalone installation without that file
uses a short fallback instruction. Each server process generates one mission
ID to group requests in the PGFR Spine journal.

## Tools

| Tool | Purpose | Effect |
|---|---|---|
| `floor_state` | Read symbolic floor state. | Read-only |
| `perceive` | Observe a configured camera region. | Read-only |
| `dispatch_task` | Submit one policy-gated floor action. | Physical action |
| `dispatch_parallel` | Submit one qualified two-arm GR00T pair. | Physical action |
| `certified_groot_sequence` | Report the active serial or mixed-pair plan. | Read-only |
| `reset_scene` | Reset the supported Isaac Sim scene after an explicit operator request. | Operator control |
| `verify` | Evaluate a yes/no visual predicate and advance a pending proof gate. | Read-only |
| `mission_history` | List journaled missions. | Read-only |
| `mission_detail` | Read a mission operation timeline. | Read-only |

## Install and test

From the repository root:

```bash
uv sync --frozen --extra dev \
  --project servers/policy-gated-factory-robot-orchestrator-reference-mcp
uv run --frozen \
  --project servers/policy-gated-factory-robot-orchestrator-reference-mcp \
  pytest -q servers/policy-gated-factory-robot-orchestrator-reference-mcp/tests
```

The unit tests use a local fake PGFR Spine service and do not require ROS 2 or
Isaac Sim.

## Run on the Jetson control host

PGFR Spine must be reachable at `PGFR_FLOOR_SERVICE`. Start the MCP server with:

```bash
servers/policy-gated-factory-robot-orchestrator-reference-mcp/.venv/bin/pgfr-mcp
```

The process waits for an MCP client on standard input/output.

## Connect from Claude Code

The following example launches the MCP server through SSH:

```bash
claude mcp add pgfr-floor -- ssh jetson@<thor-ip> ~/Policy-Gated-Factory-Robot-Orchestrator-Reference/servers/policy-gated-factory-robot-orchestrator-reference-mcp/.venv/bin/pgfr-mcp
```

After connecting, start a new client session so it receives the current tools
and playbook instructions.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PGFR_FLOOR_SERVICE` | `http://127.0.0.1:8766` | PGFR Spine base URL. |
| `PGFR_MCP_TIMEOUT_S` | `280` | Per-call HTTP timeout in seconds. |
| `PGFR_MCP_ROLE` | `agent` | Role sent for ordinary PGFR Spine requests. Operator use must be explicit. |
| `PGFR_DEFAULT_BACKEND` | unset | Deployment-selected arm executor. The qualified deployment sets `groot`. |
| `PGFR_CERTIFIED_GROOT_ORDER` | `0` | Enables the fixed serial order and proof/retry gates. |
| `PGFR_GROOT_PARALLEL_ENABLED` | `0` | Records that the independent two-server B=1 readiness contract passed. |
| `PGFR_GROOT_FLEXIBLE_ORDER` | `0` | Selects the qualified mixed-pair plan when the other two flags are also enabled. |

## Certified GR00T modes

With `PGFR_CERTIFIED_GROOT_ORDER=1` and either concurrency flag disabled,
`certified_groot_sequence` reports the six-move serial fallback:

1. right green;
2. left green;
3. right red;
4. left red;
5. right blue;
6. left blue.

Each accepted physical action must be followed by fresh visual proof before the
next action. A client may submit the same action at most twice; the MCP server
does not retry physical actions automatically.

The mixed-pair plan is active only when all three flags are `1`. It permits
these atomic pairs in order:

1. left blue and right green;
2. left green and right red;
3. left red and right blue.

Each pair requires separate proof for the left and right tote. The server
rejects wrong, partial, repeated, and same-color pairs before dispatch, and it
does not expand a pair into serial `dispatch_task` calls. PGFR Spine independently
checks the same order against current floor state.

## Security boundary

The MCP process has no network listener or user-authentication layer. Access to
its standard input/output stream grants use of its exposed tools, including the
operator scene-reset tool. Restrict SSH and process access to trusted users,
keep PGFR Spine on loopback, and use the repository's documented remote-access
patterns.

See [Remote access](../../docs/REMOTE-ACCESS.md) and
[Validation](../../docs/VALIDATION.md) for deployment and acceptance guidance.
