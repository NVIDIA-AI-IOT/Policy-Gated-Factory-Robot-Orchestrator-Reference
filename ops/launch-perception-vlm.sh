#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Supported owner for the pinned OpenAI-compatible perception VLM container.
set -euo pipefail

MODE="${1:---check}"
IMAGE="${IC_VLM_IMAGE:-vllm/vllm-openai:v0.20.0-ubuntu2404}"
DIGEST="${IC_VLM_IMAGE_DIGEST:-sha256:aff65d7198dd284c37dd0a18a606544cc5e92bfb0d5eb608b77e8b8f1c6b8b0d}"
MODEL="${IC_VLM_MODEL:-nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-NVFP4-QAD}"
REVISION="${IC_VLM_REVISION:-312eb94f6d36209f7c6a82eda896e27200d152ee}"
PORT="${IC_VLM_PORT:-8001}"
CONTAINER="${IC_VLM_CONTAINER:-ic-perception-vlm}"
CACHE="${IC_VLM_CACHE:-$HOME/.cache/huggingface}"
READY_TIMEOUT="${IC_VLM_READY_TIMEOUT_S:-900}"

# Docker accepts TAG@DIGEST while pulling, but Docker 29 stores and resolves the
# immutable local reference as REPOSITORY@DIGEST. Keep the tag for readable
# release metadata while removing it from the reference used by inspect/run.
IMAGE_REPOSITORY="$IMAGE"
IMAGE_BASENAME="${IMAGE_REPOSITORY##*/}"
if [[ "$IMAGE_BASENAME" == *:* ]]; then
  IMAGE_REPOSITORY="${IMAGE_REPOSITORY%:*}"
fi
IMAGE_REF="$IMAGE_REPOSITORY@$DIGEST"

fail() { printf 'launch-perception-vlm: ERROR: %s\n' "$*" >&2; exit 2; }
verify_image() {
  docker image inspect "$IMAGE_REF" >/dev/null 2>&1 \
    || fail "pinned image is not local: $IMAGE_REF"
}
check_endpoint() {
  response="$(curl -fsS --max-time 8 "http://127.0.0.1:$PORT/v1/models")" \
    || fail "VLM endpoint is not ready on loopback port $PORT"
  python3 -c '
import json, sys
payload = json.loads(sys.argv[1])
expected = sys.argv[2]
models = {str(item.get("id")) for item in payload.get("data", []) if isinstance(item, dict)}
raise SystemExit(0 if expected in models else 1)
' "$response" "$MODEL" || fail "VLM endpoint does not advertise $MODEL"
}

command -v docker >/dev/null 2>&1 || fail "docker is not installed"
command -v curl >/dev/null 2>&1 || fail "curl is not installed"
[[ "$PORT" =~ ^[0-9]+$ ]] && [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] \
  || fail "IC_VLM_PORT must be an integer from 1 to 65535"
[[ "$READY_TIMEOUT" =~ ^[0-9]+$ ]] && [ "$READY_TIMEOUT" -ge 2 ] \
  || fail "IC_VLM_READY_TIMEOUT_S must be an integer of at least 2 seconds"
case "$MODE" in
  --check)
    verify_image
    check_endpoint
    echo "IC_PERCEPTION_VLM_READY model=$MODEL revision=$REVISION port=$PORT"
    ;;
  --wait)
    for ((attempt=1; attempt<=(READY_TIMEOUT+1)/2; attempt++)); do
      if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
        check_endpoint
        echo "IC_PERCEPTION_VLM_READY model=$MODEL revision=$REVISION port=$PORT"
        exit 0
      fi
      if [ "$attempt" -ge 2 ] \
        && ! docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
        fail "VLM container exited before readiness: $CONTAINER"
      fi
      sleep 2
    done
    fail "VLM did not become ready within ${READY_TIMEOUT}s"
    ;;
  --run)
    verify_image
    if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
      fail "container already exists: $CONTAINER"
    fi
    mkdir -p "$CACHE"
    exec docker run --rm --name "$CONTAINER" --pull never \
      --runtime=nvidia --gpus all --ipc=host --network=host \
      -e HF_HOME=/root/.cache/huggingface \
      -v "$CACHE:/root/.cache/huggingface" \
      "$IMAGE_REF" "$MODEL" \
      --revision "$REVISION" \
      --served-model-name "$MODEL" \
      --host 127.0.0.1 --port "$PORT" --dtype auto \
      --gpu-memory-utilization 0.16 --max-model-len 8192 \
      --max-num-seqs 128 --trust-remote-code
    ;;
  *) fail "usage: $0 [--check|--wait|--run]" ;;
esac
