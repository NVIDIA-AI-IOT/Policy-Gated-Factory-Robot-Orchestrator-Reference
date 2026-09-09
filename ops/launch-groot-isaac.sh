#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Launch Isaac Sim with the installed Policy-Gated Factory Robot Orchestrator Reference GR00T cell.
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
FAST_DDS_PROFILE="${IC_FASTDDS_PROFILE:-$REPO/ops/fastdds-multi-host.xml}"
ROS_DOMAIN_ID_VALUE="${ROS_DOMAIN_ID:-0}"
READY_TIMEOUT="${IC_GROOT_READY_TIMEOUT:-900}"
ERROR_MARKER_RE='[A-Z][A-Z0-9_]*_(ERR|ERROR)(:|[[:space:]=]|$)'

fail() { printf 'launch-groot-isaac: ERROR: %s\n' "$*" >&2; exit 2; }
[ -n "$MOUNT" ] || fail "usage: $0 <isaac-scripts-mount>"
[[ "$ROS_DOMAIN_ID_VALUE" =~ ^[0-9]+$ ]] \
  && [ "$ROS_DOMAIN_ID_VALUE" -le 232 ] \
  || fail "ROS_DOMAIN_ID must be an integer from 0 through 232"
[[ "$READY_TIMEOUT" =~ ^[1-9][0-9]*$ ]] \
  && [ "$READY_TIMEOUT" -le 3600 ] \
  || fail "IC_GROOT_READY_TIMEOUT must be an integer from 1 through 3600"
[ -f "$FAST_DDS_PROFILE" ] && [ ! -L "$FAST_DDS_PROFILE" ] \
  || fail "Fast DDS profile must be a regular non-symlink file: $FAST_DDS_PROFILE"
case "$FAST_DDS_PROFILE" in /*) ;; *) fail "IC_FASTDDS_PROFILE must be an absolute path" ;; esac
[ -f "$MOUNT/startup.py" ] || fail "run ops/install-groot-cell.sh first"
[ -f "$MOUNT/groot_shared_policy_contract.json" ] || \
  fail "shared GR00T policy contract is missing; run ops/install-groot-cell.sh"
[ -f "$MOUNT/groot_shared_concurrent_policy_contract.json" ] || \
  fail "shared concurrent GR00T contract is missing; run ops/install-groot-cell.sh"
[ -f "$GROOT_STATE_ROOT/shared-left.json" ] || \
  fail "left GR00T service state is missing: $GROOT_STATE_ROOT/shared-left.json"
[ -f "$GROOT_STATE_ROOT/shared-right.json" ] || \
  fail "right GR00T service state is missing: $GROOT_STATE_ROOT/shared-right.json"
ISAAC_ROOT="${IC_ISAAC_ROOT:-$(cd "$MOUNT/.." && pwd)}"
mkdir -p "$ISAAC_ROOT"/cache/{kit,ov,glcache,computecache,pip} \
  "$ISAAC_ROOT"/{logs,data}
IC_ISAAC_IMAGE="$IMAGE" \
  IC_ISAAC_IMAGE_DIGEST="$IMAGE_DIGEST" \
  DISPLAY="$DISPLAY_VALUE" \
  "$REPO/ops/check-sim-host.sh" --profile x11 \
    --state-root "$ISAAC_ROOT" --mount "$MOUNT"

assert_no_active_simulator() {
  local container_id container_image image_id name source target_mount
  target_mount="$(realpath -m "$MOUNT")"
  image_id="$(docker image inspect --format '{{.Id}}' "$IMAGE_REF")"
  while IFS= read -r container_id; do
    [ -n "$container_id" ] || continue
    name="$(docker container inspect --format '{{.Name}}' "$container_id")"
    source="$(docker container inspect --format \
      '{{range .Mounts}}{{if eq .Destination "/scripts"}}{{.Source}}{{end}}{{end}}' \
      "$container_id")"
    if [ -n "$source" ] && [ "$(realpath -m "$source")" = "$target_mount" ]; then
      fail "scripts mount is used by active container ${name#/}; launch will not create a second owner"
    fi
    container_image="$(docker container inspect --format '{{.Image}}' "$container_id")"
    if [ "$container_image" = "$image_id" ]; then
      fail "pinned Isaac image is already active as ${name#/}; stop it explicitly before launching GR00T"
    fi
  done < <(docker ps -q)
}

wait_for_groot_runtime() {
  local deadline logs state
  deadline=$((SECONDS + READY_TIMEOUT))
  while [ "$SECONDS" -lt "$deadline" ]; do
    # This command creates a fresh container, so the complete log belongs to
    # this launch. Do not let noisy Kit output roll an early error out of the
    # pass/fail window; tail is reserved for diagnostics below.
    logs="$(docker logs "$CONTAINER_NAME" 2>&1 || true)"
    if grep -Eq "$ERROR_MARKER_RE" <<<"$logs"; then
      docker logs --tail 100 "$CONTAINER_NAME" >&2 || true
      fail "Isaac GR00T runtime reported a startup or physics error; container was left intact"
    fi
    if grep -Fq 'IC_GROOT_RUNTIME_READY' <<<"$logs" \
      && grep -Fq 'STARTUP_DONE full_scene+runner' <<<"$logs"; then
      sleep 5
      logs="$(docker logs "$CONTAINER_NAME" 2>&1 || true)"
      if grep -Eq "$ERROR_MARKER_RE" <<<"$logs"; then
        docker logs --tail 100 "$CONTAINER_NAME" >&2 || true
        fail "Isaac GR00T runtime failed during the post-ready stability window; container was left intact"
      fi
      state="$(docker container inspect --format '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || true)"
      [ "$state" = running ] \
        || fail "Isaac GR00T container stopped after readiness (state=${state:-missing}); it was left intact"
      printf 'IC_GROOT_ISAAC_READY container=%s markers=runtime,full_scene\n' "$CONTAINER_NAME"
      return
    fi
    state="$(docker container inspect --format '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || true)"
    [ "$state" = running ] || {
      docker logs --tail 100 "$CONTAINER_NAME" >&2 || true
      fail "Isaac GR00T container stopped before readiness (state=${state:-missing}); it was left intact"
    }
    sleep 2
  done
  docker logs --tail 100 "$CONTAINER_NAME" >&2 || true
  fail "timed out waiting for both GR00T readiness markers; container was left intact"
}

assert_no_active_simulator
active_container_names="$(docker ps --format '{{.Names}}')" \
  || fail "could not enumerate running Docker containers"
if grep -qx "$CONTAINER_NAME" <<<"$active_container_names"; then
  fail "$CONTAINER_NAME is already active; this launcher will not replace it"
fi
all_container_names="$(docker ps -a --format '{{.Names}}')" \
  || fail "could not enumerate Docker containers"
if grep -qx "$CONTAINER_NAME" <<<"$all_container_names"; then
  fail "$CONTAINER_NAME already exists but is stopped; remove it explicitly before launch"
fi
XAUTH_FILE="${XDG_RUNTIME_DIR:-/tmp}/ic-isaac.xauth"
rm -f "$XAUTH_FILE"
touch "$XAUTH_FILE"
if ! XAUTH_ENTRY="$(xauth nlist "$DISPLAY_VALUE" 2>/dev/null | sed -e 's/^..../ffff/')"; then
  fail "could not read the X11 authorization cookie for DISPLAY=$DISPLAY_VALUE"
fi
[ -n "$XAUTH_ENTRY" ] \
  || fail "no X11 authorization cookie exists for DISPLAY=$DISPLAY_VALUE"
printf '%s\n' "$XAUTH_ENTRY" | xauth -f "$XAUTH_FILE" nmerge - 2>/dev/null \
  || fail "could not create the container X11 authorization cookie"
chmod 0600 "$XAUTH_FILE"

CONTAINER_ID="$(
  docker run -d --name "$CONTAINER_NAME" \
    --entrypoint /isaac-sim/isaac-sim.sh --gpus all --net=host \
    -e ACCEPT_EULA=Y \
    -e OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1 \
    -e DISPLAY="$DISPLAY_VALUE" \
    -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID_VALUE" \
    -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    -e FASTRTPS_DEFAULT_PROFILES_FILE=/etc/policy-gated-factory-robot-orchestrator-reference/fastdds.xml \
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
    -v "$FAST_DDS_PROFILE:/etc/policy-gated-factory-robot-orchestrator-reference/fastdds.xml:ro" \
    -v "$MOUNT:/scripts:ro" \
    "$IMAGE_REF" \
    --/persistent/isaac/asset_root/default="$ASSET_ROOT" \
    --/persistent/app/omniverse/bookmarks/Isaac_Cloud_Assets="$ASSET_ROOT" \
    --exec /scripts/startup.py
)" || fail "Docker did not start the Isaac GR00T container; any failed container was left intact"

echo "IC_ISAAC_STARTING container=$CONTAINER_NAME id=$CONTAINER_ID"
wait_for_groot_runtime
