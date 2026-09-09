# Fine-tune the Policy-Gated Factory Robot Orchestrator Reference GR00T model

This recipe reproduces the shared Order744-cont24 checkpoint from the
published Hugging Face dataset. It uses NVIDIA's GR00T N1.7 DROID base and
official `examples/finetune.sh` entry point.

## 1. Download the dataset

Use the repository and immutable revision from
[`../../models/manifest.yaml`](../../models/manifest.yaml):

```bash
export IC_GROOT_DATASET_REPO='mmallick/industrial-claw-groot-order744-cont24-dataset'
export IC_GROOT_DATASET_REVISION='da9b6e9a2faf5bd91bc559e7f12babd7102a5863'
export IC_GROOT_DATASET_ROOT="$PWD/data/policy-gated-factory-robot-orchestrator-reference-groot"

hf download "$IC_GROOT_DATASET_REPO" \
  --repo-type dataset \
  --revision "$IC_GROOT_DATASET_REVISION" \
  --local-dir "$IC_GROOT_DATASET_ROOT"
```

The repository is public and does not require repository-specific access.

The published dataset contract is:

```text
Order744/base
  left/red       120 episodes
  right/red      120 episodes
  left/blue      120 episodes
  right/blue     120 episodes
  left/green      96 episodes
  right/green     96 episodes
  total          672 episodes

Order744/corrective
  left/red        12 episodes
  right/red       12 episodes
  left/blue       12 episodes
  right/blue      12 episodes
  left/green      12 episodes
  right/green     12 episodes
  total           72 episodes

Order744 total   744 episodes

cont24
  left/blue       12 accumulated-scene episodes
  right/red       12 accumulated-scene episodes
  total           24 episodes
```

Every training dataset directory must contain `meta/info.json` and official
GR00T statistics. Validate the episode totals before launching training.

## 2. Prepare NVIDIA GR00T

Create the supported GR00T environment and obtain the vanilla DROID
checkpoint according to NVIDIA's Isaac-GR00T instructions. The training
contract uses:

```text
base model:   nvidia/GR00T-N1.7-DROID
embodiment:   OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT
modality:     pipeline/training/droid_checkpoint_single_frame_config.py
video delta:  [0]
```

Set portable paths for your checkout and outputs:

```bash
export ISAAC_GROOT_ROOT=/path/to/Isaac-GR00T
export GROOT_DROID_BASE=/path/to/GR00T-N1.7-DROID
export IC_GROOT_OUTPUT_ROOT="$PWD/training-output"
export IC_MODALITY_CONFIG="$PWD/reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_ic_pipeline/pipeline/training/droid_checkpoint_single_frame_config.py"
```

## 3. Train Order744

Build a colon-separated `ORDER744_DATASETS` value from the 12 published
native-DROID dataset directories: six base roots followed by the six
corrective roots.

```bash
export ORDER744_DATASETS="\
$IC_GROOT_DATASET_ROOT/order744/base/left/red:\
$IC_GROOT_DATASET_ROOT/order744/base/right/red:\
$IC_GROOT_DATASET_ROOT/order744/base/left/blue:\
$IC_GROOT_DATASET_ROOT/order744/base/right/blue:\
$IC_GROOT_DATASET_ROOT/order744/base/left/green:\
$IC_GROOT_DATASET_ROOT/order744/base/right/green:\
$IC_GROOT_DATASET_ROOT/order744/corrective/left/red:\
$IC_GROOT_DATASET_ROOT/order744/corrective/right/red:\
$IC_GROOT_DATASET_ROOT/order744/corrective/left/blue:\
$IC_GROOT_DATASET_ROOT/order744/corrective/right/blue:\
$IC_GROOT_DATASET_ROOT/order744/corrective/left/green:\
$IC_GROOT_DATASET_ROOT/order744/corrective/right/green"

cd "$ISAAC_GROOT_ROOT"

NUM_GPUS=1 \
SAVE_STEPS=999999 \
SAVE_TOTAL_LIMIT=1 \
MAX_STEPS=3000 \
USE_WANDB=0 \
DATALOADER_NUM_WORKERS=4 \
GLOBAL_BATCH_SIZE=16 \
LEARNING_RATE=1e-4 \
SHARD_SIZE=1024 \
NUM_SHARDS_PER_EPOCH=100000 \
EPISODE_SAMPLING_RATE=0.1 \
COLOR_JITTER_BRIGHTNESS=0.3 \
COLOR_JITTER_CONTRAST=0.4 \
COLOR_JITTER_SATURATION=0.5 \
COLOR_JITTER_HUE=0.08 \
/bin/bash examples/finetune.sh \
  --base-model-path "$GROOT_DROID_BASE" \
  --dataset-path "$ORDER744_DATASETS" \
  --embodiment-tag OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT \
  --output-dir "$IC_GROOT_OUTPUT_ROOT/order744" \
  --experiment-name policy_gated_factory_robot_orchestrator_reference_order744 \
  --modality-config-path "$IC_MODALITY_CONFIG" \
  --state-dropout-prob 0.2 \
  --save-only-model
```

Only the final `checkpoint-3000` is retained.

## 4. Continue with cont24

The continuation starts from the retained Order744 checkpoint. It trains on
the same 12 Order744 dataset directories plus the two accumulated-scene
directories, for 768 episodes in total.

```bash
export CONT24_DATASETS="\
$ORDER744_DATASETS:\
$IC_GROOT_DATASET_ROOT/cont24/left/blue:\
$IC_GROOT_DATASET_ROOT/cont24/right/red"

NUM_GPUS=1 \
SAVE_STEPS=999999 \
SAVE_TOTAL_LIMIT=1 \
MAX_STEPS=3000 \
USE_WANDB=0 \
DATALOADER_NUM_WORKERS=4 \
GLOBAL_BATCH_SIZE=16 \
LEARNING_RATE=1e-5 \
SHARD_SIZE=1024 \
NUM_SHARDS_PER_EPOCH=100000 \
EPISODE_SAMPLING_RATE=0.1 \
COLOR_JITTER_BRIGHTNESS=0.3 \
COLOR_JITTER_CONTRAST=0.4 \
COLOR_JITTER_SATURATION=0.5 \
COLOR_JITTER_HUE=0.08 \
/bin/bash examples/finetune.sh \
  --base-model-path "$IC_GROOT_OUTPUT_ROOT/order744/policy_gated_factory_robot_orchestrator_reference_order744/checkpoint-3000" \
  --dataset-path "$CONT24_DATASETS" \
  --embodiment-tag OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT \
  --output-dir "$IC_GROOT_OUTPUT_ROOT/order744-cont24" \
  --experiment-name policy_gated_factory_robot_orchestrator_reference_order744_cont24 \
  --modality-config-path "$IC_MODALITY_CONFIG" \
  --state-dropout-prob 0.2 \
  --save-only-model
```

The final serving artifact is
`order744-cont24/policy_gated_factory_robot_orchestrator_reference_order744_cont24/checkpoint-3000`.
`checkpoint-3000` is the local NVIDIA trainer output directory. When the model
is published, its eight inference files and `SHA256SUMS` live at the Hugging
Face model-repository root and are downloaded into one local model directory.

## 5. Validate before serving

Require all of the following:

1. training exits successfully at step 3000;
2. the final checkpoint contains every indexed safetensor shard;
3. model, processor, statistics, and index files are present;
4. the dataset and model revisions are recorded; and
5. rollout validation uses the integrated runtime in [`../../runtime/`](../../runtime/).

Changing the dataset composition, base checkpoint, modality, learning rate,
or step count defines a new experiment and should use a new output directory.
