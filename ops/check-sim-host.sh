#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Read-only compatibility check for the validated Linux RTX simulation host.
set -euo pipefail

IMAGE="${IC_ISAAC_IMAGE:-nvcr.io/nvidia/isaac-sim:6.0.0-dev2}"
DIGEST="${IC_ISAAC_IMAGE_DIGEST:-sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9}"
IMAGE_REF="$IMAGE@$DIGEST"
DISPLAY_VALUE="${DISPLAY:-:1}"
MOUNT=""

fail() { printf 'check-sim-host: ERROR: %s\n' "$*" >&2; exit 2; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mount) MOUNT="${2:-}"; shift 2 ;;
    -h|--help) echo "usage: $0 [--mount ISAAC_SCRIPTS_MOUNT]"; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[ "$(uname -s)" = "Linux" ] || fail "validated simulation host requires Linux"
[ "$(uname -m)" = "x86_64" ] || fail "validated simulation host requires x86_64"
for command in docker nvidia-smi xauth xhost; do
  command -v "$command" >/dev/null 2>&1 || fail "missing command: $command"
done
docker info >/dev/null 2>&1 || fail "Docker daemon is unavailable to this user"
docker info --format '{{json .Runtimes}}' | grep -q '"nvidia"' \
  || fail "NVIDIA Container Runtime is not registered with Docker"
nvidia-smi -L | grep -q '^GPU ' || fail "no NVIDIA GPU is visible"

[ -n "$DISPLAY_VALUE" ] || fail "DISPLAY is unset"
display_number="${DISPLAY_VALUE#*:}"
display_number="${display_number%%.*}"
[ -S "/tmp/.X11-unix/X$display_number" ] \
  || fail "X11 socket is missing for DISPLAY=$DISPLAY_VALUE"

docker image inspect "$IMAGE_REF" >/dev/null 2>&1 \
  || fail "pinned Isaac Sim image is not local: $IMAGE_REF"

if [ -n "$MOUNT" ]; then
  [ -d "$MOUNT" ] || fail "Isaac scripts mount does not exist: $MOUNT"
  available="$(df -PB1 "$MOUNT" | awk 'NR==2 {print $4}')"
  [ "$available" -ge 21474836480 ] \
    || fail "less than 20 GiB is available beside the Isaac scripts mount"
fi

echo "IC_SIM_HOST_READY image=$IMAGE_REF display=$DISPLAY_VALUE"
