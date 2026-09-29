#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Re-run the exact 1,000-step specialist recipe around NVIDIA's launcher.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <red|blue|green> <left-dataset:right-dataset> <output-dir>" >&2
  exit 2
fi

COLOR="$1"
DATASET_PATH="$2"
OUTPUT_DIR="$3"
BASE_MODEL_PATH="${PGFR_GROOT_BASE_MODEL_PATH:-}"
PYTHON="${PGFR_GROOT_PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$COLOR" in
  red|blue|green) ;;
  *) echo "unknown specialist color: $COLOR" >&2; exit 2 ;;
esac
[ -n "$BASE_MODEL_PATH" ] || {
  echo "set PGFR_GROOT_BASE_MODEL_PATH to a local copy of the pinned DROID base" >&2
  exit 2
}
[ -e gr00t/experiment/launch_finetune.py ] || {
  echo "run this command from the prepared Isaac-GR00T source root" >&2
  exit 2
}

EXPERIMENT_NAME="droid15_dual_${COLOR}_expert168_droid1f_steps1000"
# Keep checkpoint loading restricted even if a library requests unsafe pickle.
export TORCH_FORCE_WEIGHTS_ONLY_LOAD=1
unset TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD
exec "$PYTHON" gr00t/experiment/launch_finetune.py \
  --base_model_path "$BASE_MODEL_PATH" \
  --dataset_path "$DATASET_PATH" \
  --embodiment_tag OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT \
  --num_gpus 1 \
  --output_dir "$OUTPUT_DIR" \
  --save_steps 1000 \
  --save_total_limit 1 \
  --max_steps 1000 \
  --warmup_ratio 0.05 \
  --weight_decay 1e-5 \
  --learning_rate 1e-4 \
  --global_batch_size 16 \
  --color_jitter_params brightness 0.3 contrast 0.4 saturation 0.5 hue 0.08 \
  --dataloader_num_workers 4 \
  --shard_size 1024 \
  --num_shards_per_epoch 100000 \
  --episode_sampling_rate 0.1 \
  --modality_config_path "$SCRIPT_DIR/droid_single_frame_config.py" \
  --experiment_name "$EXPERIMENT_NAME" \
  --state_dropout_prob 0.2 \
  --save_only_model
