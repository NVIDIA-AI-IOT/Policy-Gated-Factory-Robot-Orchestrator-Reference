# OpenClaw integration

The deployed OpenClaw profile connects to the canonical
[`policy-gated-factory-robot-orchestrator-reference-mcp`](../../servers/policy-gated-factory-robot-orchestrator-reference-mcp/)
server through [`ops/openclaw.template.json`](../../ops/openclaw.template.json).
That MCP server exposes all nine governed floor tools:

- `floor_state`
- `perceive`
- `dispatch_task`
- `dispatch_parallel`
- `certified_groot_sequence`
- `reset_scene`
- `verify`
- `mission_history`
- `mission_detail`

The conformance kit checks the MCP handshake, server instructions, and tool
hygiene. The current nine-tool surface reports `CERTIFIED: 11/11`; see the
[two-host reproduction guide](../../docs/REPRODUCIBLE-DEMO.md#5-start-and-validate).

This directory retains a repository-local direct plugin adapter and its unit
tests. The adapter itself registers six tools: `floor_state`, `perceive`,
`dispatch_task`, `reset_scene`, `task_status`, and `verify`. It is not the
deployed nine-tool MCP boundary and does not supply the parallel, certified
sequence, or mission-history tools. `npm ci && npm test` verifies this direct
adapter's policy hook and registration behavior; it is not a live OpenClaw,
MCP, model-inference, or physical-mission acceptance test.

The root lockfile pins the OpenClaw runtime. Use the repository launcher and
generated configuration described in the
[deployment guide](../../docs/REPRODUCIBLE-DEMO.md), rather than wiring this
directory as a substitute MCP server.
