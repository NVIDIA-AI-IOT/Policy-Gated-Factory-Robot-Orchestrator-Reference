#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Download the immutable shared GR00T model and verify its artifacts.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_REPO="${IC_GROOT_HF_REPO:-}"
MODEL_REVISION="${IC_GROOT_HF_REVISION:-}"
BACKBONE_REPO="${IC_GROOT_BACKBONE_HF_REPO:-nvidia/Cosmos-Reason2-2B}"
BACKBONE_REVISION="${IC_GROOT_BACKBONE_HF_REVISION:-9ce19a195e423419c349abfc86fd07178b230561}"
BACKBONE_MODEL_SHA256="fa5a6e6ef4fce40216b185cc48a3b24d31637ac3e2ba69c107ed1f389c1e6ede"
MODEL_ROOT="${IC_GROOT_MODEL_ROOT:-$HOME/policy-gated-factory-robot-orchestrator-reference-models/order744-cont24}"
HF_BIN="${IC_HF_BIN:-}"
HF_HOME="${IC_HF_HOME:-$(dirname "$MODEL_ROOT")/hf-home}"
HF_TOKEN_PATH="${IC_HF_TOKEN_PATH:-$HF_HOME/token}"
export HF_HOME HF_TOKEN_PATH

fail() { printf 'fetch-groot-models: ERROR: %s\n' "$*" >&2; exit 2; }

[ -n "$MODEL_REPO" ] || fail "set IC_GROOT_HF_REPO to the published shared-model repository"
[ -n "$MODEL_REVISION" ] || fail "set IC_GROOT_HF_REVISION to an immutable model revision"
if [ -z "$HF_BIN" ]; then
  runtime_hf="$HOME/groot_shadow/Isaac-GR00T/.venv/bin/hf"
  if [ -x "$runtime_hf" ]; then
    HF_BIN="$runtime_hf"
  else
    HF_BIN="$(command -v hf || true)"
  fi
fi
[ -x "$HF_BIN" ] || fail \
  "hf CLI not found; run ops/prepare-groot-runtime.sh --install or set IC_HF_BIN"
HF_PYTHON="$(dirname "$HF_BIN")/python"
[ -x "$HF_PYTHON" ] || fail "hf CLI must belong to a Python virtual environment: $HF_BIN"
HF_VERSION="$($HF_PYTHON -c 'import huggingface_hub; print(huggingface_hub.__version__)')"
[ "$HF_VERSION" = "0.36.2" ] \
  || fail "huggingface-hub 0.36.2 required; found $HF_VERSION"
[ -n "${HF_TOKEN:-}" ] || [ -r "$HF_TOKEN_PATH" ] || fail \
  "the runtime backbone is gated; accept its NVIDIA terms and authenticate with hf auth login"

for profile in shared-left shared-right; do
  if systemctl --user --quiet is-active "ic-groot-policy@$profile.service" 2>/dev/null; then
    fail "ic-groot-policy@$profile.service is active; never replace a model beneath a running server"
  fi
done

mkdir -p "$MODEL_ROOT" "$HF_HOME"
"$HF_BIN" download "$MODEL_REPO" \
  --revision "$MODEL_REVISION" \
  --local-dir "$MODEL_ROOT" \
  --include \
    config.json embodiment_id.json \
    model-00001-of-00003.safetensors \
    model-00002-of-00003.safetensors \
    model-00003-of-00003.safetensors \
    model.safetensors.index.json processor_config.json statistics.json \
    SHA256SUMS

"$HF_BIN" download "$BACKBONE_REPO" \
  --revision "$BACKBONE_REVISION" \
  --include \
    chat_template.json config.json generation_config.json merges.txt \
    model.safetensors preprocessor_config.json tokenizer.json \
    tokenizer_config.json video_preprocessor_config.json vocab.json

backbone_snapshot="$HF_HOME/hub/models--nvidia--Cosmos-Reason2-2B/snapshots/$BACKBONE_REVISION"
[ -f "$backbone_snapshot/config.json" ] \
  || fail "pinned Cosmos backbone snapshot is incomplete: $backbone_snapshot"
printf '%s  %s\n' "$BACKBONE_MODEL_SHA256" "$backbone_snapshot/model.safetensors" \
  | sha256sum --check --strict

backbone_cache="$HF_HOME/hub/models--nvidia--Cosmos-Reason2-2B"
mkdir -p "$backbone_cache/refs"
printf '%s' "$BACKBONE_REVISION" >"$backbone_cache/refs/main"
[ "$(cat "$backbone_cache/refs/main")" = "$BACKBONE_REVISION" ] \
  || fail "failed to bind the offline Cosmos main ref to the pinned revision"

"$REPO/ops/verify-groot-models.sh" "$MODEL_ROOT"
echo "IC_GROOT_MODEL_FETCHED repo=$MODEL_REPO revision=$MODEL_REVISION model_root=$MODEL_ROOT"
