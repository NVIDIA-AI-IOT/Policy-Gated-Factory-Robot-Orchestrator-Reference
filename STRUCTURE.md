# Repository structure

This repository contains PGFR Spine, PGFR Console, agent interfaces, and the Isaac
Sim/GR00T reference implementation. OpenClaw is installed as the pinned
dependency in `package.json`; its runtime source is not vendored.

## Runtime relationship

The working example under
`reference/policy-gated-factory-robot-orchestrator-reference/` composes the
top-level software components with the Isaac Sim cell and GR00T:

```text
Agent interfaces / PGFR Chat                 PGFR Console
              |                                |
              +---------------+----------------+
                              |
                    PGFR Spine floor service      pgfr-spine/
                              |
                    Isaac Sim reference cell    reference/.../isaac-cell/
                              |
                    GR00T action execution      reference/.../groot/
                              |
                    Two Franka arms + AMR
```

## Directory guide

```text
.
├── pgfr-spine/                 PGFR Spine orchestration and floor service
├── pgfr-console/               PGFR Console operator interface
├── reference/policy-gated-factory-robot-orchestrator-reference/
│   ├── README.md             working-example overview
│   ├── isaac-cell/           Isaac Sim baseline and deployment assets
│   │   └── deployment/      current two-arm, three-block cell deployment
│   └── groot/
│       ├── groot_n1_7_pgfr_pipeline/    GR00T N1.7 PGFR pipeline
│       ├── capture_context/            distilled per-arm capture states
│       ├── runtime/                    action execution and telemetry
│       ├── relay/                      GR00T request/response bridge
│       ├── training/                   fine-tuning entry points
│       └── models/                     artifact metadata
├── servers/
│   ├── policy-gated-factory-robot-orchestrator-reference-mcp/  MCP adapter over PGFR Spine
│   ├── pgfr-chat/              swappable chat/harness gateway
│   └── pgfr-workflows/         workflow authoring and execution
├── plugins/openclaw/         OpenClaw integration
├── skills/                   canonical agent playbook and templates
├── ops/                      installers, systemd units, and health checks
├── deploy/                   measured deployment contract
├── schemas/                  API and cell-protocol contracts
├── packages/                 conformance and connector tooling
├── connectors/               optional system and evaluation integrations
├── docs/                     installation, operations, and integration guides
└── package.json              pinned OpenClaw dependency
```

## Supported entry points

For hardware-free PGFR Spine development:

```bash
uv sync --frozen --extra dev --project pgfr-spine
uv run --frozen --project pgfr-spine pytest -q pgfr-spine/tests

export PGFR_FLOOR_STATE=/tmp/pgfr-floor.json
uv run --frozen --project pgfr-spine \
  policy_gated_factory_robot_orchestrator_reference floor-state
uv run --frozen --project pgfr-spine \
  policy_gated_factory_robot_orchestrator_reference dispatch \
    --endpoint amr_franka_1 --action move \
    --color red --from table_1 --destination red_rack
```

For the two-host live system, follow
[`docs/REPRODUCIBLE-DEMO.md`](docs/REPRODUCIBLE-DEMO.md). The model training
and serving lineage is documented under
[`reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/`](reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/).

Validated platforms and dated hardware evidence are recorded in
[`docs/SUPPORT.md`](docs/SUPPORT.md).
