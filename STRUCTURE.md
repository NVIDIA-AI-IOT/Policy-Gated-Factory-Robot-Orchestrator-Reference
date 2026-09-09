# Repository structure

This repository contains the two primary Policy-Gated Factory Robot Orchestrator Reference software components,
IC Spine and IC Console, plus harness integrations and a complete Isaac Sim /
GR00T reference implementation. OpenClaw is consumed as the pinned dependency
in `package.json`; its runtime source is not vendored here.

## Runtime relationship

The working example under `reference/policy-gated-factory-robot-orchestrator-reference/` composes the
top-level software components with the Isaac Sim cell and GR00T:

```
  Agent harness / IC Chat                  IC Console
             │                                │
             └──────────────┬─────────────────┘
                            ▼
                  IC Spine floor service      ic-spine/
                            │
                            ▼
                  Isaac Sim reference cell    reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/
                            │
                            ▼
                  GR00T action execution      reference/policy-gated-factory-robot-orchestrator-reference/groot/
                            │
                            ▼
                  Two Franka arms + AMR
```

## Directory guide

```
.
├── ic-spine/                 IC Spine orchestration and floor service
├── ic-console/               IC Console operator interface
├── reference/policy-gated-factory-robot-orchestrator-reference/
│   ├── README.md             working-example overview
│   ├── isaac-cell/           Isaac Sim baseline and deployment assets
│   │   └── deployment/      current two-arm, three-block cell deployment
│   └── groot/
│       ├── groot_n1_7_ic_pipeline/    GR00T N1.7 IC pipeline
│       ├── capture_context/            distilled per-arm capture states
│       ├── runtime/                    action execution and telemetry
│       ├── relay/                      GR00T request/response bridge
│       ├── training/                   fine-tuning entry points
│       └── models/                     artifact metadata
├── servers/
│   ├── policy-gated-factory-robot-orchestrator-reference-mcp/  MCP adapter over IC Spine
│   ├── ic-chat/              swappable chat/harness gateway
│   └── ic-workflows/         workflow authoring and execution
├── plugins/openclaw/         OpenClaw integration
├── skills/                   canonical agent playbook and templates
├── ops/                      installers, systemd units, and health checks
├── deploy/                   measured deployment contract
├── schemas/                  API and cell-protocol contracts
├── packages/                 conformance and connector tooling
├── connectors/               optional system and evaluation integrations
├── docs/                     public guides plus clearly dated history
└── package.json              pinned OpenClaw dependency
```

## Supported entry points

For the hardware-free IC Spine path:

```bash
cd ic-spine
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest

export IC_FLOOR_STATE=/tmp/ic-floor.json
.venv/bin/policy_gated_factory_robot_orchestrator_reference floor-state
.venv/bin/policy_gated_factory_robot_orchestrator_reference dispatch --endpoint amr_franka_1 --action move \
    --color red --from table_1 --destination red_rack
```

For the two-host live system, follow
[`docs/REPRODUCIBLE-DEMO.md`](docs/REPRODUCIBLE-DEMO.md). The exact proven
one-model lineage is documented under
[`reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_ic_pipeline/`](reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_ic_pipeline/).

Historical diagnostics under `docs/baseline-*` and `docs/hardening-*` are
retained as evidence. They are not alternate launch paths.
