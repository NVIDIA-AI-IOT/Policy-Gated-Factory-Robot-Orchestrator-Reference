# Repository structure

Start with [Architecture](docs/ARCHITECTURE.md) for runtime behavior or
[Contributing](CONTRIBUTING.md) for development and test commands. Components
are installed independently; there is no combined Python distribution.
OpenClaw is pinned in [package.json](package.json), not vendored.
The reference simulation and GR00T integration live in `reference/isaac-cell/`
and `reference/groot/`.

| Source | Purpose |
|---|---|
| [pgfr-spine](pgfr-spine/README.md) | Floor service: policy, dispatch, perception, verification, and journals |
| [pgfr-console](pgfr-console/README.md) | Operator UI and read-only aggregation API |
| [servers/pgfr-chat](servers/pgfr-chat/README.md) | Chat gateway and model-provider integration |
| [servers/pgfr-workflows](servers/pgfr-workflows/README.md) | Deterministic workflow execution and scheduling |
| [MCP server](servers/policy-gated-factory-robot-orchestrator-reference-mcp/README.md) | Agent-facing floor tools and operating instructions |
| [Server template](servers/TEMPLATE/README.md) | Scaffold for another MCP tool server |
| [plugins/openclaw](plugins/openclaw/README.md) | OpenClaw tool adapter |
| [skills](skills/README.md) | Orchestration skill, canonical playbook, and skill template |
| [Isaac Sim cell](reference/isaac-cell/README.md) | Scene assets, scripted controllers, ROS 2 endpoints, and learned-motion startup |
| [GR00T integration](reference/groot/README.md) | Training pipeline, Thor serving, relays, and simulator executor |
| [ops](ops/) | Installers, preflights, and acceptance scripts; [service guide](ops/systemd/README.md) |
| [deploy/reproducible-demo.yaml](deploy/reproducible-demo.yaml) | Two-host deployment versions, artifact identities, ports, and service ownership |
| [HTTP schema](schemas/floor-service.openapi.json) | Generated PGFR Spine API contract; tests detect drift |
| [Cell protocol schemas](schemas/cell-protocol/) | ROS 2 JSON payloads; action-registry tests check supported actions |
| [Conformance kit](packages/conformance-kit/README.md) | Black-box floor API, MCP, and skill checks |
| [Connector SDK](packages/connector-sdk/README.md) | Typed interfaces for external integrations |
| [connectors](connectors/README.md) | Template for external-system connectors |
| [docs](docs/README.md) | Setup, operations, training, and release guidance |
