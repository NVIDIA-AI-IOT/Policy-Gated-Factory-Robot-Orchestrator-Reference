# MCP servers — the northbound catalog

Every server here passes `ic-conformance mcp` (instructions + tool hygiene).
Create your own: [`TEMPLATE/`](TEMPLATE/README.md).

| Server | Tools | Status |
|---|---|---|
| [`industrial-claw-mcp`](industrial-claw-mcp/) | floor_state · perceive · dispatch_task · verify | ✅ certified 6/6 · mission-proven (Claude Code) |
| [`TEMPLATE`](TEMPLATE/) | — | the paved road |
| [`ic-console`](ic-console/) | HTTP (not MCP): live topology · mission replay | read-only observability plane |
| [`ic-workflows`](ic-workflows/) | HTTP (not MCP): workflow builder/runner · publish-as-skill | write path, policy-gated |
| [`ic-chat`](ic-chat/) | HTTP (not MCP): chat gateway · swappable model drives the cell | write path, policy-gated |
