#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Verify the downloaded shared GR00T checkpoint before serving it.
set -euo pipefail

MODEL_ROOT="${1:-${IC_GROOT_MODEL_ROOT:-$HOME/industrial-claw-models/order744-cont24}}"
SUMS="$MODEL_ROOT/SHA256SUMS"

fail() { printf 'verify-groot-models: ERROR: %s\n' "$*" >&2; exit 2; }

[ -d "$MODEL_ROOT" ] || fail "model directory not found: $MODEL_ROOT"
[ -f "$SUMS" ] || fail "artifact checksum manifest not found: $SUMS"

for name in \
  config.json embodiment_id.json \
  model-00001-of-00003.safetensors \
  model-00002-of-00003.safetensors \
  model-00003-of-00003.safetensors \
  model.safetensors.index.json processor_config.json statistics.json; do
  [ -f "$MODEL_ROOT/$name" ] || fail "required inference artifact is missing: $MODEL_ROOT/$name"
done

(cd "$MODEL_ROOT" && sha256sum --check --strict SHA256SUMS)
echo "IC_GROOT_MODEL_VERIFIED model_root=$MODEL_ROOT"
