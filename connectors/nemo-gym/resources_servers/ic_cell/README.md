# ic_cell — NeMo Gym resources server for the Policy-Gated Factory Robot Orchestrator Reference cell

Wraps the IC Spine floor seam as a [NeMo Gym](https://github.com/NVIDIA-NeMo/Gym)
environment: any Gym agent harness/model can drive the warehouse cell through
the same seam + policy gate as the production brain, and every episode is
scored by the cell's physics ground truth (a dispatch counts only when the
cell re-measured the world and set `verified=true`).

## How it maps

| NeMo Gym | IC Spine |
|---|---|
| tools (`floor_state`, `perceive`, `dispatch_task`, `check_predicate`) | seam `/v1/*` routes, stamped with a per-rollout `x-mission-id` |
| `seed_session` (episode reset) | operator `reset` dispatch through the policy gate |
| `verify` (reward) | mission journal: physics-`verified` dispatch matching the task, optionally AND a `/v1/verify` ground-truth predicate |

`verify` is a reserved Gym tool name, so the seam's verify tool is exposed to
models as `check_predicate`.

## Run

```bash
# 1. seam (mock backend needs no sim/ROS; use the live cell by just having it up)
IC_FLOOR_BACKEND=mock policy_gated_factory_robot_orchestrator_reference serve --port 8766

# 2. from a NeMo Gym checkout/install, with this connector on the search path:
gym env start "+config_paths=[resources_servers/ic_cell/configs/ic_cell.yaml,responses_api_models/openai_model/configs/openai_model.yaml]" \
  --search-dir /path/to/Policy-Gated-Factory-Robot-Orchestrator-Reference/connectors/nemo-gym

# 3. collect scored rollouts
gym eval run --no-serve +agent_name=ic_cell_simple_agent \
  +input_jsonl_fpath=resources_servers/ic_cell/data/example.jsonl \
  +output_jsonl_fpath=resources_servers/ic_cell/data/example_rollouts.jsonl +limit=null
```

Config via env: `IC_FLOOR_SERVICE` (seam base URL, default `http://127.0.0.1:8766`),
`IC_RESET_ENDPOINT` (default `franka_left`).

## Tests

`gym env test --resources-server ic_cell` — hardware-free; a fake in-process
seam stands in for the floor service (same convention as the MCP server tests).

## Rules of the house

- No privileged path: every call goes through the seam's policy gate; the
  only elevated act is the episode `reset` (operator role), identical to how
  a human operator resets the cell.
- Fail loud, score honest: seam unreachable or unverified physics → reward 0
  with the reason recorded, never a silent pass.
- `data/example_rollouts.jsonl` ships as schema-correct placeholders;
  regenerate with the `gym eval run` above against a real model + seam.

## License

Follows the repository license (see repo root `LICENSE`). Example data is
synthetic and self-contained.
