#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Publish one verified Order744-cont24 inference checkpoint to Hugging Face.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKPOINT="${IC_GROOT_CHECKPOINT_PATH:-}"
MODEL_REPO="${IC_GROOT_HF_REPO:-}"
VISIBILITY="${IC_GROOT_HF_VISIBILITY:-}"
HF_BIN="${IC_HF_BIN:-$(command -v hf || true)}"
PYTHON="${IC_GROOT_PYTHON:-}"

fail() { printf 'upload-groot-models: ERROR: %s\n' "$*" >&2; exit 2; }
[ -d "$CHECKPOINT" ] || fail "set IC_GROOT_CHECKPOINT_PATH to the final checkpoint-3000 directory"
[ -n "$MODEL_REPO" ] || fail "set IC_GROOT_HF_REPO to namespace/repository"
case "$VISIBILITY" in public|private) ;; *) fail "set IC_GROOT_HF_VISIBILITY to public or private" ;; esac
[ -x "$HF_BIN" ] || fail "hf CLI not found; set IC_HF_BIN"
if [ -z "$PYTHON" ]; then
  PYTHON="$(dirname "$HF_BIN")/python"
fi
[ -x "$PYTHON" ] || fail "GR00T Python not found; set IC_GROOT_PYTHON"
"$HF_BIN" auth whoami >/dev/null 2>&1 || fail "Hugging Face login is required"

inference_files=(
  config.json embodiment_id.json
  model-00001-of-00003.safetensors
  model-00002-of-00003.safetensors
  model-00003-of-00003.safetensors
  model.safetensors.index.json processor_config.json statistics.json
)
for name in "${inference_files[@]}"; do
  [ -f "$CHECKPOINT/$name" ] || fail "required inference artifact is missing: $CHECKPOINT/$name"
done

sums="$(mktemp)"
trap 'rm -f "$sums"' EXIT
for name in "${inference_files[@]}"; do
  digest="$(sha256sum "$CHECKPOINT/$name")"
  digest="${digest%% *}"
  printf '%s  %s\n' "$digest" "$name" >>"$sums"
done

create_args=(repo create "$MODEL_REPO" --repo-type model --exist-ok)
[ "$VISIBILITY" = private ] && create_args+=(--private)
"$HF_BIN" "${create_args[@]}"

actual_visibility="$($PYTHON - "$MODEL_REPO" <<'PY'
import sys
from huggingface_hub import HfApi
print("private" if HfApi().model_info(sys.argv[1]).private else "public")
PY
)"
[ "$actual_visibility" = "$VISIBILITY" ] \
  || fail "repository is $actual_visibility, requested $VISIBILITY"

"$HF_BIN" upload "$MODEL_REPO" \
  "$REPO/reference/industrial-claw/groot/models/README.md" README.md \
  --commit-message "Add Industrial Claw Order744-cont24 model card"
"$HF_BIN" upload "$MODEL_REPO" "$sums" SHA256SUMS \
  --commit-message "Add model artifact checksums"
"$HF_BIN" upload "$MODEL_REPO" "$CHECKPOINT" . \
  --include "${inference_files[@]}" \
  --commit-message "Upload Order744-cont24 inference artifacts"

revision="$($PYTHON - "$MODEL_REPO" <<'PY'
import sys
from huggingface_hub import HfApi
print(HfApi().model_info(sys.argv[1]).sha)
PY
)"
echo "IC_GROOT_HF_UPLOADED repo=$MODEL_REPO revision=$revision visibility=$VISIBILITY"
