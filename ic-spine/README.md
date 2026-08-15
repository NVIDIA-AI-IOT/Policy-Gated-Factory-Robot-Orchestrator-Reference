# IC Spine

IC Spine is Industrial Claw's policy-gated control and assurance service. It
sits between agent harnesses and floor systems, exposing a stable API for
perception, action dispatch, verification, task status, mission history, and
evidence.

The same service runs with a hardware-free mock backend for development or the
ROS 2 backend used by the Industrial Claw Isaac Sim reference cell.

## Responsibilities

- discover input sources and action endpoints;
- enforce action policy before dispatch;
- serialize shared-floor operations while allowing bounded robot-internal
  concurrency;
- acquire fresh camera evidence for perception and verification;
- expose synchronous and asynchronous task APIs;
- record mission operations, outcomes, and evidence frames; and
- provide health and freshness metadata to IC Console and agent adapters.

IC Spine owns these guarantees independently of the connected agent harness.
IC Chat, OpenClaw, Codex, Claude Code, and other MCP clients use the same
floor contract.

## Install and test

From the repository root:

```bash
cd ic-spine
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

ROS 2 deployments normally create the environment with
`--system-site-packages` so the host's `rclpy` installation is available.

## Run with the mock backend

```bash
export IC_FLOOR_STATE=/tmp/ic-floor.json
.venv/bin/industrial_claw floor-state
.venv/bin/industrial_claw dispatch \
  --endpoint amr_franka_1 \
  --action move \
  --color red \
  --from table_1 \
  --destination red_rack
```

## Run with the Isaac Sim ROS 2 backend

```bash
export IC_FLOOR_BACKEND=ros2
export ROS_DOMAIN_ID=0
export IC_FLOOR_SCENE=$PWD/configs/scene.our_demo.yaml
export IC_PERCEIVE_MODE=vision_only
export IC_VLM_URL=http://127.0.0.1:8001
export IC_VLM_MODEL=nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-NVFP4-QAD
export IC_JOURNAL_DIR=~/ic-journal
.venv/bin/industrial_claw serve --host 127.0.0.1 --port 8766
```

The service publishes its OpenAPI documentation at `/docs` and health state
at `/v1/health`. Deployment templates live under
[`ops/systemd/`](../ops/systemd/).

## Configuration

- [`configs/scene.example.yaml`](configs/scene.example.yaml) defines floor
  topology and endpoint capabilities.
- [`configs/policy.example.yaml`](configs/policy.example.yaml) adds or
  overrides reviewed action-policy entries.
- [`configs/scene.our_demo.yaml`](configs/scene.our_demo.yaml) describes the
  Industrial Claw reference cell.

See the [repository architecture](../docs/ARCHITECTURE.md), the
[endpoint integration guide](../docs/ENDPOINT-INTEGRATION.md), and the
[reference implementation](../reference/industrial-claw/) for the complete
system.
