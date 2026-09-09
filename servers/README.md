# Server catalog — northbound interfaces

The MCP reference server passes `ic-conformance mcp` (instructions + tool
hygiene). The HTTP services are listed separately below. Create an MCP server
from [`TEMPLATE/`](TEMPLATE/README.md).

| Server | Tools | Status |
|---|---|---|
| [`policy-gated-factory-robot-orchestrator-reference-mcp`](policy-gated-factory-robot-orchestrator-reference-mcp/) | floor_state · perceive · dispatch_task · dispatch_parallel · certified_groot_sequence · reset_scene · verify · mission_history · mission_detail | ✅ certified 11/11 · mission-proven (Claude Code) |
| [`TEMPLATE`](TEMPLATE/) | — | the paved road |
| [`ic-console`](../ic-console/) | HTTP (not MCP): live topology · mission replay | read-only observability plane |
| [`ic-workflows`](ic-workflows/) | HTTP (not MCP): workflow builder/runner · publish-as-skill | write path, policy-gated |
| [`ic-chat`](ic-chat/) | HTTP (not MCP): chat gateway · swappable model drives the cell | write path, policy-gated |
