# GR00T color-specialist training utility

This utility trains a single-color red, blue, or green specialist. For the
shared three-object, two-arm checkpoint, use the
[fine-tuning recipe](../groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md).

## Files

| File | Purpose |
| --- | --- |
| [`droid_single_frame_config.py`](droid_single_frame_config.py) | Preserves the `nvidia/GR00T-N1.7-DROID` current-frame processor contract: exterior and wrist images, DROID state fields, 40-step relative EEF/joint actions, absolute gripper actions, and language instruction input. |
| [`finetune-specialist.sh`](finetune-specialist.sh) | Calls NVIDIA's `gr00t/experiment/launch_finetune.py` for one color using a left/right native-DROID dataset pair and a final-only 1,000-step output. |

## Run a specialist experiment

Run from the prepared Isaac-GR00T source root. Point
`PGFR_GROOT_BASE_MODEL_PATH` to the local pinned DROID base and optionally set
`PGFR_GROOT_PYTHON` to the prepared environment's Python executable:

```bash
export PGFR_GROOT_BASE_MODEL_PATH=/path/to/GR00T-N1.7-DROID
export PGFR_GROOT_PYTHON=/path/to/Isaac-GR00T/.venv/bin/python

/path/to/Policy-Gated-Factory-Robot-Orchestrator-Reference/reference/groot/training/finetune-specialist.sh \
  red \
  /data/left/red:/data/right/red \
  /output/red-specialist
```

The script validates the color and base-model setting, then runs 1,000 training
steps. Use a separate experiment name and output directory when changing the
base checkpoint, dataset composition, modality, or training parameters.
