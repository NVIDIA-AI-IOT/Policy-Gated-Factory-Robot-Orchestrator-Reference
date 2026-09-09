# PGFR cell resource server for NVIDIA NeMo Gym

The `pgfr_cell` resource server maps NVIDIA NeMo Gym episodes to the PGFR Spine
HTTP API. Every request uses the normal policy and verification path and is
recorded under a per-episode mission ID.

## Interface mapping

| NeMo Gym operation | PGFR Spine operation |
|---|---|
| `floor_state` | `POST /v1/floor-state` |
| `perceive` | `POST /v1/perceive` |
| `dispatch_task` | `POST /v1/dispatch` |
| `check_predicate` | `POST /v1/verify` |
| `seed_session` | Operator-role reset through `POST /v1/dispatch` |
| `verify` | Mission-journal scoring, with an optional visual predicate |

`verify` is reserved by NeMo Gym, so the PGFR Spine visual-verification
operation is exposed to an agent as `check_predicate`.

## Run

Start PGFR Spine first. The mock backend does not require Isaac Sim or ROS 2:

```bash
PGFR_FLOOR_BACKEND=mock policy_gated_factory_robot_orchestrator_reference serve --port 8766
```

From an installed NeMo Gym checkout, start the resource server with this
integration on the search path:

```bash
gym env start "+config_paths=[resources_servers/pgfr_cell/configs/pgfr_cell.yaml,responses_api_models/openai_model/configs/openai_model.yaml]" \
  --search-dir /path/to/Policy-Gated-Factory-Robot-Orchestrator-Reference/connectors/nemo-gym
```

Collect the sample rollouts:

```bash
gym eval run --no-serve +agent_name=pgfr_cell_simple_agent \
  +input_jsonl_fpath=resources_servers/pgfr_cell/data/example.jsonl \
  +output_jsonl_fpath=resources_servers/pgfr_cell/data/example_rollouts.jsonl \
  +limit=null
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PGFR_FLOOR_SERVICE` | `http://127.0.0.1:8766` | PGFR Spine base URL |
| `PGFR_RESET_ENDPOINT` | `franka_left` | Endpoint used for the episode reset |

The resource-server configuration also controls request timeout, whether to
reset between episodes, and whether a failed reset aborts `seed_session`.

## Scoring and assurance

A reward of `1.0` requires at least one matching mission-journal dispatch with
`verified=true`. When verifier metadata includes a predicate, PGFR Spine must
also return `answer=yes` for that predicate. An unreachable service, an
unverified action, a mismatched action or color, or a failed predicate produces
a reward of `0.0`.

The episode reset uses the operator role. Restrict access to this resource
server accordingly. It does not bypass PGFR Spine policy, provide independent
authentication, or convert request acceptance into physical success.

The tracked example rollout files are schema fixtures. Regenerate them with a
real model and the intended PGFR Spine deployment before using them as evaluation
evidence.

## Test

From an installed NeMo Gym environment:

```bash
gym env test --resources-server pgfr_cell
```

The tests use an in-process PGFR Spine substitute and do not require robot
hardware, ROS 2, or Isaac Sim.
