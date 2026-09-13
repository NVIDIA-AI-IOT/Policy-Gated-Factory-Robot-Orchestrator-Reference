#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Verify your local GR00T export and fetch only the pinned upstream Cosmos backbone.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKBONE_REPO="nvidia/Cosmos-Reason2-2B"
BACKBONE_REVISION="9ce19a195e423419c349abfc86fd07178b230561"
BACKBONE_MODEL_SHA256="fa5a6e6ef4fce40216b185cc48a3b24d31637ac3e2ba69c107ed1f389c1e6ede"
MODEL_ROOT="${1:-${PGFR_GROOT_MODEL_ROOT:-}}"
HF_BIN="${PGFR_HF_BIN:-}"
HF_HOME="${PGFR_HF_HOME:-$(dirname "$MODEL_ROOT")/hf-home}"
HF_TOKEN_PATH="${PGFR_HF_TOKEN_PATH:-$HF_HOME/token}"
export HF_HOME HF_TOKEN_PATH

fail() { printf 'fetch-groot-models: ERROR: %s\n' "$*" >&2; exit 2; }
LEGACY_GUARD="$REPO/ops/pgfr-legacy-guard.sh"
[ -r "$LEGACY_GUARD" ] || fail "missing migration guard: $LEGACY_GUARD"
# shellcheck disable=SC1090
. "$LEGACY_GUARD"

[ "$#" -le 1 ] || fail "usage: ops/fetch-groot-models.sh CHECKPOINT_DIRECTORY"
[ -n "$MODEL_ROOT" ] || fail "supply your local checkpoint export path; create data, fine-tune, and run ops/export-groot-checkpoint.py first"
"$REPO/ops/verify-groot-models.sh" "$MODEL_ROOT"
if [ -z "$HF_BIN" ]; then
  runtime_hf="$HOME/groot_shadow/Isaac-GR00T/.venv/bin/hf"
  if [ -x "$runtime_hf" ]; then
    HF_BIN="$runtime_hf"
  else
    HF_BIN="$(command -v hf || true)"
  fi
fi
[ -x "$HF_BIN" ] || fail \
  "hf CLI not found; run ops/prepare-groot-runtime.sh --install or set PGFR_HF_BIN"
HF_PYTHON="$(dirname "$HF_BIN")/python"
[ -x "$HF_PYTHON" ] || fail "hf CLI must belong to a Python virtual environment: $HF_BIN"
HF_VERSION="$($HF_PYTHON -c 'import huggingface_hub; print(huggingface_hub.__version__)')"
[ "$HF_VERSION" = "0.36.2" ] \
  || fail "huggingface-hub 0.36.2 required; found $HF_VERSION"
[ -n "${HF_TOKEN:-}" ] || [ -r "$HF_TOKEN_PATH" ] || fail \
  "the runtime backbone is gated; accept its NVIDIA terms and authenticate with hf auth login"

pgfr_refuse_active_legacy_units
for profile in shared-left shared-right; do
  if systemctl --user --quiet is-active "pgfr-groot-policy@$profile.service" 2>/dev/null; then
    fail "pgfr-groot-policy@$profile.service is active; never replace a model beneath a running server"
  fi
done

mkdir -p "$HF_HOME"
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

echo "PGFR_GROOT_BACKBONE_FETCHED repo=$BACKBONE_REPO revision=$BACKBONE_REVISION model_root=$MODEL_ROOT"
