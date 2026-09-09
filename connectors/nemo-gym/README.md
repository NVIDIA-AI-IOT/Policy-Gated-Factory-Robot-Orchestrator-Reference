# nemo-gym — NeMo Gym integration for IC Spine

Makes the Policy-Gated Factory Robot Orchestrator Reference cell a [NeMo Gym](https://github.com/NVIDIA-NeMo/Gym)
environment: benchmark any model/agent against the cell with physics-verified
scoring, and export scored rollouts for RL/SFT training (NeMo RL, VeRL).

- `resources_servers/ic_cell/` — the environment server (tools → seam,
  reset → operator dispatch, reward → mission-journal ground truth).
  See its README for the full run recipe.

Point NeMo Gym at this directory with `--search-dir` (Gym discovers servers by
the `resources_servers/<name>/configs/<name>.yaml` path convention).
