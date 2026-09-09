# GR00T color-specialist training utility

This directory contains the compact training utility for a single-color
red, blue, or green specialist. It is retained for specialist experiments and
rollback models; the shared three-object, two-arm demo follows the Order744-
cont24 recipe in
[`../groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md`](../groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md).

## Files

| File | Purpose |
| --- | --- |
| [`droid_single_frame_config.py`](droid_single_frame_config.py) | Preserves the `nvidia/GR00T-N1.7-DROID` current-frame processor contract: exterior and wrist images, DROID state fields, a 40-step relative-action horizon, and language instruction input. |
| [`finetune-specialist.sh`](finetune-specialist.sh) | Calls NVIDIA's `gr00t/experiment/launch_finetune.py` for one color using a left/right native-DROID dataset pair and a final-only 1,000-step output. |

## Run a specialist experiment

Run from the prepared Isaac-GR00T source root. Point
`PGFR_GROOT_BASE_MODEL_PATH` to the local pinned DROID base and optionally set
`PGFR_GROOT_PYTHON` to the prepared environment's Python executable:

```bash
export PGFR_GROOT_BASE_MODEL_PATH=/path/to/GR00T-N1.7-DROID
export PGFR_GROOT_PYTHON=/path/to/Isaac-GR00T/.venv/bin/python

/path/to/Policy-Gated-Factory-Robot-Orchestrator-Reference/reference/policy-gated-factory-robot-orchestrator-reference/groot/training/finetune-specialist.sh \
  red \
  /data/left/red:/data/right/red \
  /output/red-specialist
```

The script validates the color and required base-model setting before invoking
the NVIDIA launcher. Its 1,000-step specialist contract must not be presented
as the shared Order744-cont24 recipe. Changes to the base checkpoint, dataset
composition, modality, or training parameters should use a separately named
experiment and output directory.
