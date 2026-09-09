# GR00T environment for Jetson AGX Thor

This directory defines the pinned Python and system environment used to train
or serve the prepared NVIDIA Isaac-GR00T source on Jetson AGX Thor. It covers
the aarch64, Python 3.12, and CUDA 13 environment; dataset selection and model
fine-tuning are documented separately.

## Files

| File | Purpose | Requirement |
| --- | --- | --- |
| [`install_deps.sh`](install_deps.sh) | Installs the required CUDA libraries, creates the uv environment, installs GR00T editable, and installs or builds torchcodec. | Required for bare-metal and container setup. |
| [`pyproject.toml`](pyproject.toml) | Declares the Thor-specific Python dependencies and package indexes. | Required. |
| [`uv.lock`](uv.lock) | Pins the complete dependency resolution consumed by `uv sync`. | Required. |
| [`Dockerfile`](Dockerfile) | Builds the dependency-qualification environment in the pinned CUDA container. | Optional; not the accepted model-serving path. |

## Preparation flow

From the Policy-Gated Factory Robot Orchestrator Reference repository root, prepare the pinned upstream source,
apply the Policy-Gated Factory Robot Orchestrator Reference patch, and copy this Thor environment into the
prepared checkout:

```bash
ops/prepare-groot-runtime.sh --source-only
```

To prepare the source and install its Thor environment in one operation:

```bash
ops/prepare-groot-runtime.sh --install
```

The preparation script refuses to replace an existing destination and checks
that the known GR00T policy and relay profiles are inactive before modifying
the prepared source tree. The dependency installer consumes this directory's
`pyproject.toml` and `uv.lock` in place.

For the shared Order744-cont24 training commands and dataset composition, see
[`../groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md`](../groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md).
The Jetson control-host prerequisite installer is separate. It prepares the
system packages and application dependencies required by PGFR Spine and PGFR
Console; it does not replace this GR00T environment.

The accepted reference deployment serves GR00T bare metal from the frozen uv
environment. The Dockerfile qualifies the dependency set only and is not
evidence for containerized policy serving or a complete mission.
