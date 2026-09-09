# PGFR Spine

PGFR Spine is the policy and assurance service for the Policy-Gated Factory Robot
Orchestrator Reference. It presents one floor API for perception, action
dispatch, verification, task status, mission history, and evidence. The service
can use a hardware-free mock backend or the ROS 2 backend for the Isaac Sim
reference cell.

## Responsibilities

- Discover configured input sources and action endpoints.
- Enforce action policy before dispatch.
- Serialize shared-floor operations while allowing qualified, bounded
  robot-internal concurrency.
- Collect fresh camera evidence for perception and verification.
- Expose synchronous and asynchronous task results.
- Record mission operations, outcomes, and evidence frames when journaling is
  enabled.
- Report backend health and sensor freshness.

PGFR Chat, OpenClaw, MCP clients, and deterministic workflows use this same floor
contract.

## API

| Method and path | Purpose |
|---|---|
| `GET /v1/health` | Backend health, ROS context, and freshness. |
| `POST /v1/floor-state` | Current endpoints and world-state metadata. |
| `POST /v1/perceive` | Symbolic, visual, or fused observation of a target. |
| `POST /v1/dispatch` | Policy-gated single action. Inspect `dispatched` and `verified` in the response. |
| `POST /v1/dispatch-parallel` | Qualified two-arm GR00T pair; disabled by default. |
| `POST /v1/verify` | Camera-based yes/no check of a predicate. |
| `GET /v1/tasks/{goal_id}` | Result of an asynchronous ROS 2 goal. |
| `GET /v1/missions` | Journaled mission summaries. |
| `GET /v1/missions/{mission_id}` | Operation timeline for one journaled mission. |
| `GET /v1/frames/{request_id}` | Evidence frame associated with a journaled request. |

OpenAPI documentation is available at `/docs` while the service is running.

## Install and test

From the repository root:

```bash
uv sync --frozen --extra dev --project pgfr-spine
uv run --frozen --project pgfr-spine pytest -q pgfr-spine/tests
```

Python 3.12 is required. ROS 2 deployments use the environment created by the
deployment scripts with access to the host `rclpy` installation.

## Run with the mock backend

Start the HTTP service:

```bash
export PGFR_FLOOR_BACKEND=mock
export PGFR_FLOOR_STATE=/tmp/pgfr-floor.json
uv run --frozen --project pgfr-spine \
  policy_gated_factory_robot_orchestrator_reference serve \
  --host 127.0.0.1 --port 8766
```

In another terminal, inspect and update the mock floor:

```bash
uv run --frozen --project pgfr-spine \
  policy_gated_factory_robot_orchestrator_reference floor-state
uv run --frozen --project pgfr-spine \
  policy_gated_factory_robot_orchestrator_reference dispatch \
  --endpoint amr_franka_1 \
  --action move \
  --color red \
  --from table_1 \
  --destination red_rack
```

## Run with the Isaac Sim ROS 2 backend

The reference deployment configures PGFR Spine through systemd. For a manual
loopback start from the repository root:

```bash
export PGFR_FLOOR_BACKEND=ros2
export ROS_DOMAIN_ID=0
export PGFR_FLOOR_SCENE="$PWD/pgfr-spine/configs/scene.our_demo.yaml"
export PGFR_PERCEIVE_MODE=vision_only
export PGFR_VLM_URL=http://127.0.0.1:8001
export PGFR_VLM_MODEL=nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-NVFP4-QAD
export PGFR_JOURNAL_DIR="$HOME/pgfr-journal"
uv run --frozen --project pgfr-spine \
  policy_gated_factory_robot_orchestrator_reference serve \
  --host 127.0.0.1 --port 8766
```

Use the [`ops/bootstrap-brain.sh`](../ops/bootstrap-brain.sh) compatibility
script for the complete Jetson control-host installation. See the [two-host
deployment guide](../docs/REPRODUCIBLE-DEMO.md)
for the Isaac Sim and GR00T services.

## Parallel-dispatch controls

`/v1/dispatch-parallel` denies dispatch by default at PGFR Spine. Set
`PGFR_GROOT_PARALLEL_ENABLED=1` only after the independent two-server B=1
readiness contract passes. The route also requires
`PGFR_GROOT_FLEXIBLE_ORDER=1`. Both flags default to `0`.

When both flags are enabled, PGFR Spine rejects same-color pairs and permits only
the next pair in the qualified Order744 sequence:

1. left blue and right green;
2. left green and right red;
3. left red and right blue.

State measurement and dispatch share one route lock. Partial, skipped,
out-of-order, and repeated pairs are refused before motion. The MCP layer adds
per-session visual-proof handling, and the bundled workflow places two proof
barriers after each accepted pair.

## Configuration

- [`configs/scene.example.yaml`](configs/scene.example.yaml) defines floor
  topology and endpoint capabilities.
- [`configs/policy.example.yaml`](configs/policy.example.yaml) adds or overrides
  reviewed action-policy entries.
- [`configs/scene.our_demo.yaml`](configs/scene.our_demo.yaml) describes the
  Isaac Sim reference cell.

Keep the service on loopback unless the deployment adds an authenticated,
encrypted ingress. See [Remote access](../docs/REMOTE-ACCESS.md) for supported
access patterns.

## Related documentation

- [Architecture](../docs/ARCHITECTURE.md)
- [Endpoint integration](../docs/ENDPOINT-INTEGRATION.md)
- [Validation](../docs/VALIDATION.md)
- [Systemd deployment](../ops/systemd/README.md)
