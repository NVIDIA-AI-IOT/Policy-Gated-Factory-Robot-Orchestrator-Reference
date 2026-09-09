# NVIDIA NeMo Gym integration

This integration exposes the reference cell as an
[NVIDIA NeMo Gym](https://github.com/NVIDIA-NeMo/Gym) environment. It supports
model and agent evaluation against PGFR Spine, physics-verified scoring, and
rollout collection for downstream training workflows.

| Path | Description |
|---|---|
| [`resources_servers/pgfr_cell/`](resources_servers/pgfr_cell/README.md) | NeMo Gym resource server, configuration, tests, and sample rollout data |

NeMo Gym discovers the integration through
`resources_servers/pgfr_cell/configs/pgfr_cell.yaml`. Pass this directory through
Gym's `--search-dir` option. See the
[resource-server guide](resources_servers/pgfr_cell/README.md) for the exact run
commands and scoring boundary.
