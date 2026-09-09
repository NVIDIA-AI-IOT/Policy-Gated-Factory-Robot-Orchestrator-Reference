#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Prepare, check, and launch the packaged Isaac Sim scripted baseline.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="$REPO/reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell"
CHECKER="$REPO/ops/check-sim-host.sh"
IMAGE="nvcr.io/nvidia/isaac-sim:6.0.0-dev2"
DIGEST="sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9"
IMAGE_REF="$IMAGE@$DIGEST"
ASSET_ROOT="https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0"

MODE=""
STATE_ROOT="${IC_ISAAC_ROOT:-$HOME/.local/share/policy-gated-factory-robot-orchestrator-reference/isaac-sim}"
MOUNT="${IC_ISAAC_MOUNT:-}"
CONTAINER_NAME="${IC_ISAAC_CONTAINER:-ic-isaac-sim-baseline}"
DISPLAY_VALUE="${DISPLAY:-:1}"
ROS_DOMAIN_ID_VALUE="${ROS_DOMAIN_ID:-0}"
READY_TIMEOUT=900
ACCEPT_EULA=false
PRIVACY_CONSENT=false
WAIT_FOR_READY=true

fail() { printf 'isaac-sim-workstation: ERROR: %s\n' "$*" >&2; exit 2; }
usage() {
  cat <<'EOF'
usage: ops/isaac-sim-workstation.sh MODE [OPTIONS]

Modes (choose exactly one):
  --prepare              Stage the scripted baseline and create private host state.
                         Does not pull an image or start a container.
  --check                Read-only validation of the prepared baseline and host.
  --run                  Start the prepared baseline from the pinned local image.

Options:
  --root PATH            Host state root (default: ~/.local/share/policy-gated-factory-robot-orchestrator-reference/isaac-sim).
  --mount PATH           Directory mounted read-only at /scripts
                         (default: ROOT/scripts).
  --container NAME       Container name (default: ic-isaac-sim-baseline).
  --display DISPLAY      Local X11 display (default: $DISPLAY, otherwise :1).
  --ros-domain-id ID     ROS 2 domain, 0..232 (default: $ROS_DOMAIN_ID, otherwise 0).
  --timeout SECONDS      Readiness timeout for --run (default: 900).
  --no-wait              Return after Docker starts instead of waiting for IC_CELL_UP.
  --accept-eula          Required with --run; passes ACCEPT_EULA=Y to Isaac Sim.
  --privacy-consent      Optional telemetry opt-in; otherwise Kit telemetry and
                         all three privacy consent settings are forced off.
  -h, --help             Show this help.

The image is immutable in this launcher:
  nvcr.io/nvidia/isaac-sim:6.0.0-dev2@sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9

Prepare is idempotent only while the installed files exactly match this checkout.
It refuses conflicting files and never replaces an existing container.
EOF
}
set_mode() {
  [ -z "$MODE" ] || fail "choose exactly one of --prepare, --check, or --run"
  MODE="$1"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prepare) set_mode prepare; shift ;;
    --check) set_mode check; shift ;;
    --run) set_mode run; shift ;;
    --root) [ "$#" -ge 2 ] || fail "--root requires PATH"; STATE_ROOT="$2"; shift 2 ;;
    --mount) [ "$#" -ge 2 ] || fail "--mount requires PATH"; MOUNT="$2"; shift 2 ;;
    --container) [ "$#" -ge 2 ] || fail "--container requires NAME"; CONTAINER_NAME="$2"; shift 2 ;;
    --display) [ "$#" -ge 2 ] || fail "--display requires DISPLAY"; DISPLAY_VALUE="$2"; shift 2 ;;
    --ros-domain-id) [ "$#" -ge 2 ] || fail "--ros-domain-id requires ID"; ROS_DOMAIN_ID_VALUE="$2"; shift 2 ;;
    --timeout) [ "$#" -ge 2 ] || fail "--timeout requires SECONDS"; READY_TIMEOUT="$2"; shift 2 ;;
    --no-wait) WAIT_FOR_READY=false; shift ;;
    --accept-eula) ACCEPT_EULA=true; shift ;;
    --privacy-consent) PRIVACY_CONSENT=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[ -n "$MODE" ] || fail "choose one of --prepare, --check, or --run"
[ -n "$STATE_ROOT" ] || fail "--root must not be empty"
case "$STATE_ROOT" in /*) ;; *) fail "--root must be an absolute path" ;; esac
STATE_ROOT="$(realpath -m "$STATE_ROOT")"
if [ -z "$MOUNT" ]; then MOUNT="$STATE_ROOT/scripts"; fi
case "$MOUNT" in /*) ;; *) fail "--mount must be an absolute path" ;; esac
MOUNT="$(realpath -m "$MOUNT")"
case "$STATE_ROOT" in /|"$HOME"|"$REPO"|"$REPO"/*) fail "unsafe state root: $STATE_ROOT" ;; esac
case "$MOUNT" in /|"$HOME"|"$REPO"|"$REPO"/*|"$STATE_ROOT") fail "unsafe scripts mount: $MOUNT" ;; esac
case "$STATE_ROOT$MOUNT" in *$'\n'*|*,*) fail "paths must not contain a newline or comma" ;; esac
[[ "$CONTAINER_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] \
  || fail "invalid Docker container name: $CONTAINER_NAME"
[[ "$ROS_DOMAIN_ID_VALUE" =~ ^[0-9]+$ ]] \
  && [ "$ROS_DOMAIN_ID_VALUE" -le 232 ] \
  || fail "ROS domain ID must be an integer from 0 through 232"
[[ "$READY_TIMEOUT" =~ ^[1-9][0-9]*$ ]] \
  && [ "$READY_TIMEOUT" -le 3600 ] \
  || fail "timeout must be an integer from 1 through 3600 seconds"
if [ "$MODE" != prepare ]; then
  [[ "$DISPLAY_VALUE" =~ ^:[0-9]+(\.[0-9]+)?$ ]] \
    || fail "only a local X11 display such as :1 is supported"
fi
if [ "$MODE" != run ]; then
  ! $ACCEPT_EULA || fail "--accept-eula is valid only with --run"
  ! $PRIVACY_CONSENT || fail "--privacy-consent is valid only with --run"
  $WAIT_FOR_READY || fail "--no-wait is valid only with --run"
fi

for source in "$SOURCE_ROOT/ic_boot.py" "$SOURCE_ROOT/our_factory.usda"; do
  [ -f "$source" ] || fail "required source is missing: $source"
done
[ -d "$SOURCE_ROOT/ic_cell" ] || fail "required source is missing: $SOURCE_ROOT/ic_cell"
[ -x "$CHECKER" ] || fail "simulation-host checker is not executable: $CHECKER"

require_docker() {
  command -v docker >/dev/null 2>&1 || fail "missing command: docker"
  docker info >/dev/null 2>&1 \
    || fail "Docker daemon is unavailable to this user"
}

container_state() {
  docker container inspect --format '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null
}

assert_container_absent() {
  local state
  if state="$(container_state)"; then
    fail "container $CONTAINER_NAME already exists (state=$state); this tool never replaces or removes containers"
  fi
}

assert_mount_idle() {
  local container_id source name
  while IFS= read -r container_id; do
    [ -n "$container_id" ] || continue
    source="$(docker container inspect --format \
      '{{range .Mounts}}{{if eq .Destination "/scripts"}}{{.Source}}{{end}}{{end}}' \
      "$container_id")"
    if [ -n "$source" ] && [ "$(realpath -m "$source")" = "$MOUNT" ]; then
      name="$(docker container inspect --format '{{.Name}}' "$container_id")"
      fail "scripts mount is used by active container ${name#/}; preparation will not replace live files"
    fi
  done < <(docker ps -q)
}

source_file_list() {
  (
    cd "$SOURCE_ROOT/ic_cell"
    find . -type f ! -path '*/__pycache__/*' ! -name '*.py[co]' -print | LC_ALL=C sort
  )
}

installed_file_list() {
  (
    cd "$MOUNT/ic_cell"
    find . -type f -print | LC_ALL=C sort
  )
}

verify_baseline() {
  [ -d "$MOUNT/ic_cell" ] || fail "baseline package is missing: $MOUNT/ic_cell"
  [ -f "$MOUNT/ic_boot.py" ] || fail "baseline entrypoint is missing: $MOUNT/ic_boot.py"
  [ -f "$MOUNT/our_factory.usda" ] || fail "baseline stage is missing: $MOUNT/our_factory.usda"
  [ ! -L "$MOUNT/ic_cell" ] && [ ! -L "$MOUNT/ic_boot.py" ] \
    && [ ! -L "$MOUNT/our_factory.usda" ] \
    || fail "installed baseline entrypoints must not be symbolic links"
  [ -z "$(find "$MOUNT/ic_cell" -type l -print -quit)" ] \
    || fail "installed baseline must not contain symbolic links"
  [ "$(source_file_list)" = "$(installed_file_list)" ] \
    || fail "installed ic_cell file set differs from this checkout; choose a fresh --mount"
  while IFS= read -r relative; do
    cmp -s "$SOURCE_ROOT/ic_cell/$relative" "$MOUNT/ic_cell/$relative" \
      || fail "installed baseline differs from this checkout: ic_cell/$relative"
  done < <(source_file_list)
  cmp -s "$SOURCE_ROOT/ic_boot.py" "$MOUNT/ic_boot.py" \
    || fail "installed ic_boot.py differs from this checkout; choose a fresh --mount"
  cmp -s "$SOURCE_ROOT/our_factory.usda" "$MOUNT/our_factory.usda" \
    || fail "installed our_factory.usda differs from this checkout; choose a fresh --mount"
}

ensure_state_dirs() {
  local directory
  install -d -m 0700 "$STATE_ROOT"
  for directory in \
    cache/main cache/computecache config data logs pkg hub-cache; do
    install -d -m 0777 "$STATE_ROOT/$directory"
    # These leaves are bind-mounted into the image's unprivileged uid.  The
    # state root remains 0700, so other host users cannot traverse to them.
    chmod 0777 "$STATE_ROOT/$directory"
  done
  install -d -m 0700 "$STATE_ROOT/runtime"
}

prepare() {
  local stage relative
  [ "$(uname -s)" = Linux ] || fail "validated simulation host requires Linux"
  [ "$(uname -m)" = x86_64 ] || fail "validated simulation host requires x86_64"
  require_docker
  command -v python3 >/dev/null 2>&1 || fail "missing command: python3"
  assert_container_absent
  assert_mount_idle
  ensure_state_dirs

  if [ -e "$MOUNT" ]; then
    [ -d "$MOUNT" ] || fail "scripts mount exists but is not a directory: $MOUNT"
    if [ -n "$(find "$MOUNT" -mindepth 1 -print -quit)" ]; then
      verify_baseline
      printf 'IC_ISAAC_BASELINE_PREPARED mount=%s state=%s unchanged=true\n' "$MOUNT" "$STATE_ROOT"
      return
    fi
  else
    install -d -m 0755 "$MOUNT"
  fi

  stage="$(mktemp -d "${MOUNT}.prepare.XXXXXX")"
  trap 'rm -rf "$stage"' RETURN
  while IFS= read -r relative; do
    install -D -m 0644 \
      "$SOURCE_ROOT/ic_cell/$relative" "$stage/ic_cell/$relative"
  done < <(source_file_list)
  install -m 0644 "$SOURCE_ROOT/ic_boot.py" "$stage/ic_boot.py"
  install -m 0644 "$SOURCE_ROOT/our_factory.usda" "$stage/our_factory.usda"
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$stage" python3 -c \
    'from ic_cell.actions import discover_actions; r=discover_actions(); assert r.action_names == ("haul", "inspect", "move", "pick_and_place", "reset", "spawn")'
  mv "$stage/ic_cell" "$stage/ic_boot.py" "$stage/our_factory.usda" "$MOUNT/"
  rmdir "$stage"
  trap - RETURN
  verify_baseline
  printf 'IC_ISAAC_BASELINE_PREPARED mount=%s state=%s unchanged=false\n' "$MOUNT" "$STATE_ROOT"
  printf 'No image was pulled and no container was started.\n'
}

check() {
  verify_baseline
  local directory
  command -v python3 >/dev/null 2>&1 || fail "missing command: python3"
  for directory in \
    cache/main cache/computecache config data logs pkg hub-cache runtime; do
    [ -d "$STATE_ROOT/$directory" ] \
      || fail "state directory is missing; run --prepare first: $STATE_ROOT/$directory"
  done
  IC_ISAAC_IMAGE="$IMAGE" IC_ISAAC_IMAGE_DIGEST="$DIGEST" \
    DISPLAY="$DISPLAY_VALUE" "$CHECKER" --mount "$MOUNT"
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$MOUNT" python3 -c \
    'from ic_cell.actions import discover_actions; r=discover_actions(); assert r.action_names == ("haul", "inspect", "move", "pick_and_place", "reset", "spawn")'
  printf 'IC_ISAAC_BASELINE_CHECK_OK mount=%s image=%s\n' "$MOUNT" "$IMAGE_REF"
}

find_xauthority() {
  local candidate
  if [ -n "${XAUTHORITY:-}" ]; then
    printf '%s\n' "$XAUTHORITY"
    return
  fi
  for candidate in \
    "${XDG_RUNTIME_DIR:-}/gdm/Xauthority" \
    "/run/user/$(id -u)/gdm/Xauthority" \
    "$HOME/.Xauthority"; do
    if [ -n "$candidate" ] && [ -r "$candidate" ]; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  return 1
}

prepare_xauthority() {
  local source target temp
  source="$(find_xauthority)" \
    || fail "no readable Xauthority file; set XAUTHORITY explicitly"
  [ -r "$source" ] || fail "Xauthority file is not readable: $source"
  target="$STATE_ROOT/runtime/xauthority"
  temp="$STATE_ROOT/runtime/xauthority.$$"
  : > "$temp"
  chmod 0600 "$temp"
  xauth -f "$source" nlist "$DISPLAY_VALUE" \
    | sed -e 's/^..../ffff/' \
    | xauth -f "$temp" nmerge - >/dev/null 2>&1 \
    || fail "could not copy X11 authorization for DISPLAY=$DISPLAY_VALUE"
  [ -s "$temp" ] \
    || fail "Xauthority has no cookie for DISPLAY=$DISPLAY_VALUE: $source"
  chmod 0444 "$temp"
  mv -f "$temp" "$target"
  printf '%s\n' "$target"
}

wait_for_cell() {
  local deadline logs state
  deadline=$((SECONDS + READY_TIMEOUT))
  while [ "$SECONDS" -lt "$deadline" ]; do
    logs="$(docker logs "$CONTAINER_NAME" 2>&1 | tail -n 2000 || true)"
    if printf '%s\n' "$logs" | grep -Eq 'IC_CELL_BOOT_ERR|IC_STEP_ERR'; then
      docker logs --tail 80 "$CONTAINER_NAME" >&2 || true
      fail "Isaac cell reported a physics/bootstrap error; container was left intact"
    fi
    if printf '%s\n' "$logs" | grep -Fq 'IC_CELL_UP markers=all'; then
      # Keep observing briefly so an immediately-following asynchronous physics
      # failure cannot be hidden behind a success marker in the same launch.
      sleep 5
      logs="$(docker logs "$CONTAINER_NAME" 2>&1 | tail -n 2000 || true)"
      if printf '%s\n' "$logs" | grep -Eq 'IC_CELL_BOOT_ERR|IC_STEP_ERR'; then
        docker logs --tail 80 "$CONTAINER_NAME" >&2 || true
        fail "Isaac cell failed during the post-ready stability window; container was left intact"
      fi
      state="$(docker container inspect --format '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || true)"
      [ "$state" = running ] \
        || fail "container stopped during the post-ready stability window (state=${state:-missing}); it was left intact"
      printf 'IC_ISAAC_BASELINE_READY container=%s marker=IC_CELL_UP\n' "$CONTAINER_NAME"
      return
    fi
    state="$(docker container inspect --format '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || true)"
    if [ "$state" != running ]; then
      docker logs --tail 80 "$CONTAINER_NAME" >&2 || true
      fail "container stopped before IC_CELL_UP (state=${state:-missing}); it was left intact"
    fi
    sleep 2
  done
  docker logs --tail 80 "$CONTAINER_NAME" >&2 || true
  fail "timed out waiting for IC_CELL_UP; the running container was left intact"
}

run() {
  local xauth_file container_id
  local -a docker_args
  $ACCEPT_EULA \
    || fail "--run requires --accept-eula (review NVIDIA's Omniverse license first)"
  require_docker
  assert_container_absent
  assert_mount_idle
  check
  command -v xauth >/dev/null 2>&1 || fail "missing command: xauth"
  xauth_file="$(prepare_xauthority)"
  assert_container_absent
  assert_mount_idle

  docker_args=(
    run -d --pull never --name "$CONTAINER_NAME"
    --entrypoint /isaac-sim/isaac-sim.sh
    --gpus all --network host --ipc=shareable --shm-size 2g
    -e ACCEPT_EULA=Y
    -e DISPLAY="$DISPLAY_VALUE"
    -e XAUTHORITY=/tmp/ic-isaac.xauth
    -e IC_STAGE=/scripts/our_factory.usda
    -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID_VALUE"
    -e ROS_LOCALHOST_ONLY=1
    -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
    -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp
    --mount "type=bind,source=/tmp/.X11-unix,target=/tmp/.X11-unix,readonly"
    --mount "type=bind,source=$xauth_file,target=/tmp/ic-isaac.xauth,readonly"
    --mount "type=bind,source=$MOUNT,target=/scripts,readonly"
    --mount "type=bind,source=$STATE_ROOT/cache/main,target=/isaac-sim/.cache"
    --mount "type=bind,source=$STATE_ROOT/cache/computecache,target=/isaac-sim/.nv/ComputeCache"
    --mount "type=bind,source=$STATE_ROOT/config,target=/isaac-sim/.nvidia-omniverse/config"
    --mount "type=bind,source=$STATE_ROOT/data,target=/isaac-sim/.local/share/ov/data"
    --mount "type=bind,source=$STATE_ROOT/logs,target=/isaac-sim/.nvidia-omniverse/logs"
    --mount "type=bind,source=$STATE_ROOT/pkg,target=/isaac-sim/.local/share/ov/pkg"
    --mount "type=bind,source=$STATE_ROOT/hub-cache,target=/var/cache/hub"
  )
  if $PRIVACY_CONSENT; then docker_args+=(-e PRIVACY_CONSENT=Y); fi
  docker_args+=(
    "$IMAGE_REF"
    --/persistent/isaac/asset_root/default="$ASSET_ROOT"
    --/persistent/app/omniverse/bookmarks/Isaac_Cloud_Assets="$ASSET_ROOT"
  )
  if ! $PRIVACY_CONSENT; then
    # Isaac Sim 6.0.0-dev2's application config enables anonymous telemetry
    # even when PRIVACY_CONSENT is absent. Override both telemetry transport
    # and consent settings explicitly; omission alone is not an opt-out.
    docker_args+=(
      --/telemetry/enableAnonymousAppName=false
      --/telemetry/enableAnonymousData=false
      --/telemetry/useOpenEndpoint=false
      --/privacy/usage=false
      --/privacy/performance=false
      --/privacy/personalization=false
      --/crashreporter/enabled=false
    )
  fi
  docker_args+=(--exec /scripts/ic_boot.py)
  container_id="$(docker "${docker_args[@]}")" \
    || fail "Docker did not start the container; any failed container was left intact"
  printf 'IC_ISAAC_BASELINE_STARTING container=%s id=%s display=%s\n' \
    "$CONTAINER_NAME" "$container_id" "$DISPLAY_VALUE"
  printf 'Logs: docker logs -f %q\n' "$CONTAINER_NAME"
  if $WAIT_FOR_READY; then
    wait_for_cell
  else
    printf 'Expected marker: IC_CELL_UP markers=all\n'
  fi
}

case "$MODE" in
  prepare) prepare ;;
  check) check ;;
  run) run ;;
esac
