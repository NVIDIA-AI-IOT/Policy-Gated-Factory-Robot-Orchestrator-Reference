# Server catalog

This directory contains the agent-facing MCP server and the HTTP services used
by PGFR Console. The MCP implementation is validated with
`pgfr-conformance mcp`. Use [`TEMPLATE/`](TEMPLATE/README.md) when adding another
MCP server.

| Service | Interface | Purpose |
|---|---|---|
| [`policy-gated-factory-robot-orchestrator-reference-mcp`](policy-gated-factory-robot-orchestrator-reference-mcp/) | MCP over stdio | Nine PGFR Spine tools plus the operating playbook; conformance 11/11 |
| [`pgfr-chat`](pgfr-chat/) | HTTP | Chat sessions and model-driven PGFR Spine tool calls |
| [`pgfr-workflows`](pgfr-workflows/) | HTTP | Workflow authoring, validation, execution, and skill publication |
| [`pgfr-console`](../pgfr-console/) | HTTP | Read-only topology, health, telemetry, and mission aggregation |
| [`TEMPLATE`](TEMPLATE/) | MCP template | Starting point for another conformant MCP server |

Hardware acceptance scope is recorded in
[`docs/SUPPORT.md`](../docs/SUPPORT.md); conformance status alone is not a
physical mission result.
