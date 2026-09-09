#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Read-only compatibility check for the validated Linux RTX simulation host.
set -euo pipefail

IMAGE="${IC_ISAAC_IMAGE:-nvcr.io/nvidia/isaac-sim:6.0.1}"
DIGEST="${IC_ISAAC_IMAGE_DIGEST:-sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb}"
IMAGE_REF="$IMAGE@$DIGEST"
PROFILE=headless
DISPLAY_VALUE="${DISPLAY:-:1}"
WEBRTC_HOST="${ISAACSIM_HOST:-127.0.0.1}"
WEBRTC_SIGNAL_PORT="${ISAACSIM_SIGNAL_PORT:-49100}"
WEBRTC_STREAM_PORT="${ISAACSIM_STREAM_PORT:-47998}"
MOUNT=""
STATE_ROOT=""
MIN_CPU_CORES=4
MIN_RAM_BYTES=32000000000
MIN_STORAGE_CAPACITY_BYTES=50000000000
MIN_VRAM_MIB=16384
TESTED_DRIVER_BASELINE=595.58.03

fail() { printf 'check-sim-host: ERROR: %s\n' "$*" >&2; exit 2; }
version_at_least() {
  [ "$(printf '%s\n%s\n' "$TESTED_DRIVER_BASELINE" "$1" \
    | sort -V \
    | awk 'NR == 1 {oldest=$0} END {print oldest}')" \
    = "$TESTED_DRIVER_BASELINE" ]
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mount) [ "$#" -ge 2 ] || fail "--mount requires PATH"; MOUNT="$2"; shift 2 ;;
    --state-root) [ "$#" -ge 2 ] || fail "--state-root requires PATH"; STATE_ROOT="$2"; shift 2 ;;
    --profile) [ "$#" -ge 2 ] || fail "--profile requires PROFILE"; PROFILE="$2"; shift 2 ;;
    --webrtc-host) [ "$#" -ge 2 ] || fail "--webrtc-host requires IP"; WEBRTC_HOST="$2"; shift 2 ;;
    --webrtc-signal-port) [ "$#" -ge 2 ] || fail "--webrtc-signal-port requires PORT"; WEBRTC_SIGNAL_PORT="$2"; shift 2 ;;
    --webrtc-stream-port) [ "$#" -ge 2 ] || fail "--webrtc-stream-port requires PORT"; WEBRTC_STREAM_PORT="$2"; shift 2 ;;
    -h|--help)
      echo "usage: $0 [--profile headless|x11] --state-root ISAAC_STATE_ROOT [--mount ISAAC_SCRIPTS_MOUNT] [--webrtc-host IP] [--webrtc-signal-port PORT] [--webrtc-stream-port PORT]"
      exit 0
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done
case "$PROFILE" in headless|x11) ;; *) fail "--profile must be headless or x11" ;; esac
case "$STATE_ROOT" in
  /*) ;;
  "") fail "--state-root is required" ;;
  *) fail "--state-root must be an absolute path" ;;
esac
STATE_ROOT="$(realpath -m "$STATE_ROOT")"

[ "$(uname -s)" = "Linux" ] || fail "validated simulation host requires Linux"
[ "$(uname -m)" = "x86_64" ] || fail "validated simulation host requires x86_64"
[ -r /etc/os-release ] || fail "cannot identify the host operating system"
os_id="$(. /etc/os-release; printf '%s' "${ID:-}")"
os_version="$(. /etc/os-release; printf '%s' "${VERSION_ID:-}")"
[ "$os_id" = ubuntu ] || fail "Isaac Sim 6.0 requires Ubuntu on this Linux container path"
case "$os_version" in
  22.04|24.04) ;;
  *) fail "Isaac Sim 6.0 supports Ubuntu 22.04 or 24.04; detected ${os_version:-unknown}" ;;
esac
for command in docker nvidia-smi nproc; do
  command -v "$command" >/dev/null 2>&1 || fail "missing command: $command"
done
if [ "$PROFILE" = x11 ]; then
  command -v xauth >/dev/null 2>&1 || fail "missing command: xauth"
else
  for command in ip python3 ss; do
    command -v "$command" >/dev/null 2>&1 || fail "missing command: $command"
  done
  python3 -c \
    'import ipaddress, sys; ipaddress.ip_address(sys.argv[1])' \
    "$WEBRTC_HOST" \
    || fail "--webrtc-host must be a literal IP address"
  for port in "$WEBRTC_SIGNAL_PORT" "$WEBRTC_STREAM_PORT"; do
    [[ "$port" =~ ^[1-9][0-9]*$ ]] && [ "$port" -le 65535 ] \
      || fail "WebRTC ports must be integers from 1 through 65535"
  done
  [ "$WEBRTC_SIGNAL_PORT" != "$WEBRTC_STREAM_PORT" ] \
    || fail "WebRTC signal and stream ports must differ"
  host_addresses="$(ip -o address show | awk '{print $4}')" \
    || fail "cannot enumerate host interface addresses"
  host_address_found=false
  while IFS= read -r host_address; do
    if [ "${host_address%/*}" = "$WEBRTC_HOST" ]; then
      host_address_found=true
      break
    fi
  done <<<"$host_addresses"
  $host_address_found \
    || fail "ISAACSIM_HOST is not assigned to a host interface: $WEBRTC_HOST"
fi

cpu_cores="$(nproc)"
[[ "$cpu_cores" =~ ^[0-9]+$ ]] && [ "$cpu_cores" -ge "$MIN_CPU_CORES" ] \
  || fail "Isaac Sim 6.0 requires at least $MIN_CPU_CORES available CPU cores; detected ${cpu_cores:-unknown}"
ram_bytes="$(awk '/^MemTotal:/ {printf "%.0f", $2 * 1024; exit}' /proc/meminfo)"
[[ "$ram_bytes" =~ ^[0-9]+$ ]] && [ "$ram_bytes" -ge "$MIN_RAM_BYTES" ] \
  || fail "Isaac Sim 6.0 requires at least 32 GB RAM"

docker info >/dev/null 2>&1 || fail "Docker daemon is unavailable to this user"
docker_runtimes="$(docker info --format '{{json .Runtimes}}')" \
  || fail "cannot inspect Docker runtimes"
grep -q '"nvidia"' <<<"$docker_runtimes" \
  || fail "NVIDIA Container Runtime is not registered with Docker"

driver_versions="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader)" \
  || fail "could not query NVIDIA driver versions"
driver_version="${driver_versions%%$'\n'*}"
driver_version="${driver_version//[[:space:]]/}"
[[ "$driver_version" =~ ^[0-9]+([.][0-9]+)+$ ]] \
  || fail "could not read an NVIDIA driver version"
version_at_least "$driver_version" \
  || fail "project requires the tested Isaac Sim 6.0.1 Linux driver baseline $TESTED_DRIVER_BASELINE or newer; detected $driver_version"

qualified_gpu=""
gpu_inventory="$(
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits
)" || fail "could not query NVIDIA GPU inventory"
while IFS=, read -r gpu_name gpu_memory_mib; do
  gpu_memory_mib="${gpu_memory_mib//[[:space:]]/}"
  if [[ "$gpu_name" == *RTX* ]] \
    && [[ "$gpu_memory_mib" =~ ^[0-9]+$ ]] \
    && [ "$gpu_memory_mib" -ge "$MIN_VRAM_MIB" ]; then
    qualified_gpu="${gpu_name# }"
    break
  fi
done <<<"$gpu_inventory"
[ -n "$qualified_gpu" ] \
  || fail "validated Isaac Sim 6.0 host requires an RTX GPU with at least 16 GB VRAM"

if [ "$PROFILE" = x11 ]; then
  [ -n "$DISPLAY_VALUE" ] || fail "DISPLAY is unset"
  [[ "$DISPLAY_VALUE" =~ ^:[0-9]+(\.[0-9]+)?$ ]] \
    || fail "only a local X11 display such as :1 is supported"
  display_number="${DISPLAY_VALUE#*:}"
  display_number="${display_number%%.*}"
  [ -S "/tmp/.X11-unix/X$display_number" ] \
    || fail "X11 socket is missing for DISPLAY=$DISPLAY_VALUE"
fi

docker image inspect "$IMAGE_REF" >/dev/null 2>&1 \
  || fail "pinned Isaac Sim image is not local: $IMAGE_REF"

if [ -n "$MOUNT" ]; then
  [ -d "$MOUNT" ] || fail "Isaac scripts mount does not exist: $MOUNT"
fi
[ -d "$STATE_ROOT/cache" ] \
  || fail "Isaac state cache does not exist: $STATE_ROOT/cache"
read -r storage_capacity_bytes storage_available_bytes < <(
  df -PB1 "$STATE_ROOT/cache" | awk 'NR==2 {print $2, $4}'
)
[[ "$storage_capacity_bytes" =~ ^[0-9]+$ ]] \
  && [ "$storage_capacity_bytes" -ge "$MIN_STORAGE_CAPACITY_BYTES" ] \
  || fail "Isaac state cache filesystem requires at least 50000000000 total bytes"
[[ "$storage_available_bytes" =~ ^[0-9]+$ ]] \
  || fail "could not read available bytes on the Isaac state cache filesystem"

if [ "$PROFILE" = headless ]; then
  echo "IC_SIM_HOST_READY image=$IMAGE_REF profile=headless webrtc_host=$WEBRTC_HOST signal_tcp=$WEBRTC_SIGNAL_PORT stream_udp=$WEBRTC_STREAM_PORT gpu=$qualified_gpu storage_capacity_bytes=$storage_capacity_bytes storage_available_bytes=$storage_available_bytes"
else
  echo "IC_SIM_HOST_READY image=$IMAGE_REF profile=x11 display=$DISPLAY_VALUE gpu=$qualified_gpu storage_capacity_bytes=$storage_capacity_bytes storage_available_bytes=$storage_available_bytes"
fi
