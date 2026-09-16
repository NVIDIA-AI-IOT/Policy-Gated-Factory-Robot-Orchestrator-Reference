# OpenClaw integration

The reference deployment uses OpenClaw as an agent runtime and connects it to
the [PGFR floor MCP server](../../servers/policy-gated-factory-robot-orchestrator-reference-mcp/).
`ops/openclaw.template.json` is the template for its generated configuration.

## Deployed MCP tool surface

The MCP server exposes nine PGFR Spine tools:

- `floor_state`
- `perceive`
- `dispatch_task`
- `dispatch_parallel`
- `certified_groot_sequence`
- `reset_scene`
- `verify`
- `mission_history`
- `mission_detail`

The conformance kit checks handshake instructions, tool availability,
descriptions, and annotations. These checks do not test model completions or
physical missions.

## Repository-local adapter

This directory also contains a direct OpenClaw plugin adapter and its unit
tests. It registers six tools: `floor_state`, `perceive`, `dispatch_task`,
`reset_scene`, `task_status`, and `verify`.

The direct adapter is not the deployed nine-tool MCP boundary. It does not
provide parallel dispatch, the certified sequence, or mission-history tools.
Use it for adapter development and tests only.

```bash
npm ci
npm test
```

These tests validate registration and the policy hook without starting
OpenClaw, PGFR Spine, a model, ROS 2, or Isaac Sim.

## Deployment

The root lockfile pins the OpenClaw runtime. Use the generated configuration
and launcher described in the
[two-host deployment guide](../../docs/REPRODUCIBLE-DEMO.md). Configure and
test its model provider with
[`docs/MODEL-PROVIDERS.md`](../../docs/MODEL-PROVIDERS.md), then apply the
[OpenClaw acceptance boundary](../../docs/VALIDATION.md#openclaw-acceptance-boundary).

Do not wire this plugin directory as a replacement MCP server. Access to the
deployed MCP process includes physical actions and operator scene reset; keep
the PGFR Spine and Gateway listeners on their documented trust boundaries.
