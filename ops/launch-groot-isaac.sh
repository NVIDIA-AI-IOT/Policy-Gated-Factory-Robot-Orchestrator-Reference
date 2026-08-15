#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Launch Isaac Sim with the installed Industrial Claw GR00T cell.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOUNT="${1:-}"
IMAGE="${IC_ISAAC_IMAGE:-nvcr.io/nvidia/isaac-sim:6.0.0-dev2}"
IMAGE_DIGEST="${IC_ISAAC_IMAGE_DIGEST:-sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9}"
IMAGE_REF="$IMAGE@$IMAGE_DIGEST"
DISPLAY_VALUE="${DISPLAY:-:1}"
CONTAINER_NAME="${IC_ISAAC_CONTAINER:-isaac-sim}"
GROOT_STATE_ROOT="${IC_GROOT_STATE_ROOT:-$HOME/.local/share/ic-spine/groot}"
ASSET_ROOT="${IC_ISAAC_ASSET_ROOT:-https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0}"

fail() { printf 'launch-groot-isaac: ERROR: %s\n' "$*" >&2; exit 2; }
[ -n "$MOUNT" ] || fail "usage: $0 <isaac-scripts-mount>"
[ -f "$MOUNT/startup.py" ] || fail "run ops/install-groot-cell.sh first"
[ -f "$MOUNT/groot_shared_policy_contract.json" ] || \
  fail "shared GR00T policy contract is missing; run ops/install-groot-cell.sh"
[ -f "$MOUNT/groot_shared_concurrent_policy_contract.json" ] || \
  fail "shared concurrent GR00T contract is missing; run ops/install-groot-cell.sh"
[ -f "$GROOT_STATE_ROOT/shared-left.json" ] || \
  fail "left GR00T service state is missing: $GROOT_STATE_ROOT/shared-left.json"
[ -f "$GROOT_STATE_ROOT/shared-right.json" ] || \
  fail "right GR00T service state is missing: $GROOT_STATE_ROOT/shared-right.json"
"$REPO/ops/check-sim-host.sh" --mount "$MOUNT"
if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  fail "$CONTAINER_NAME is already active; this launcher will not replace it"
fi
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  fail "$CONTAINER_NAME already exists but is stopped; remove it explicitly before launch"
fi
ISAAC_ROOT="${IC_ISAAC_ROOT:-$(cd "$MOUNT/.." && pwd)}"
mkdir -p "$ISAAC_ROOT"/cache/{kit,ov,glcache,computecache,pip} \
  "$ISAAC_ROOT"/{logs,data}
XAUTH_FILE="${XDG_RUNTIME_DIR:-/tmp}/ic-isaac.xauth"
rm -f "$XAUTH_FILE"
touch "$XAUTH_FILE"
xhost +local: >/dev/null 2>&1 || true
xauth nlist "$DISPLAY_VALUE" | sed -e 's/^..../ffff/' | \
  xauth -f "$XAUTH_FILE" nmerge - 2>/dev/null || true
chmod 0600 "$XAUTH_FILE"

docker run -d --rm --name "$CONTAINER_NAME" \
  --entrypoint /isaac-sim/isaac-sim.sh --gpus all --net=host \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e DISPLAY="$DISPLAY_VALUE" \
  -e IC_CAMERA_PROFILE=capture \
  -e IC_SCENE_PROFILE=groot_three_object \
  -e IC_GROOT_POLICY_ROUTE=shared \
  -e IC_GROOT_SHARED_POLICY_CONTRACT_PATH=/scripts/groot_shared_policy_contract.json \
  -e IC_GROOT_READY_ARM="${IC_GROOT_READY_ARM:-both}" \
  -e IC_GROOT_READY_COLOR="${IC_GROOT_READY_COLOR:-red}" \
  -e IC_GROOT_READY_LAYOUT="${IC_GROOT_READY_LAYOUT:-3}" \
  -e IC_GROOT_READY_SEED="${IC_GROOT_READY_SEED:-31302}" \
  -e XAUTHORITY="$XAUTH_FILE" \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v "$XAUTH_FILE:$XAUTH_FILE:ro" \
  -v "$ISAAC_ROOT/cache/kit:/isaac-sim/kit/cache" \
  -v "$ISAAC_ROOT/cache/ov:/root/.cache/ov" \
  -v "$ISAAC_ROOT/cache/glcache:/root/.cache/nvidia/GLCache" \
  -v "$ISAAC_ROOT/cache/computecache:/root/.nv/ComputeCache" \
  -v "$ISAAC_ROOT/cache/pip:/root/.cache/pip" \
  -v "$ISAAC_ROOT/logs:/root/.nvidia-omniverse/logs" \
  -v "$ISAAC_ROOT/data:/root/.local/share/ov/data" \
  -v "$GROOT_STATE_ROOT:/groot-state:ro" \
  -v "$MOUNT:/scripts" \
  "$IMAGE_REF" \
  --/persistent/isaac/asset_root/default="$ASSET_ROOT" \
  --/persistent/app/omniverse/bookmarks/Isaac_Cloud_Assets="$ASSET_ROOT" \
  --exec /scripts/startup.py

echo "IC_ISAAC_STARTING container=$CONTAINER_NAME"
echo "Wait for both IC_GROOT_RUNTIME_READY and STARTUP_DONE full_scene+runner."
