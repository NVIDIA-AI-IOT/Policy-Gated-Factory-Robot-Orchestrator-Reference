#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Prepare, check, and launch the packaged Isaac Sim scripted baseline.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="$REPO/reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell"
CHECKER="$REPO/ops/check-sim-host.sh"
IMAGE="nvcr.io/nvidia/isaac-sim:6.0.1"
DIGEST="sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb"
IMAGE_REF="$IMAGE@$DIGEST"
ASSET_ROOT="https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0"

MODE=""
STATE_ROOT="${PGFR_ISAAC_ROOT:-$HOME/.local/share/policy-gated-factory-robot-orchestrator-reference/isaac-sim}"
MOUNT="${PGFR_ISAAC_MOUNT:-}"
CONTAINER_NAME="${PGFR_ISAAC_CONTAINER:-pgfr-isaac-sim-baseline}"
PRESENTATION_PROFILE="headless"
DISPLAY_VALUE="${DISPLAY:-:1}"
DISPLAY_OPTION_SET=false
WEBRTC_HOST="${ISAACSIM_HOST:-127.0.0.1}"
WEBRTC_SIGNAL_PORT="${ISAACSIM_SIGNAL_PORT:-49100}"
WEBRTC_STREAM_PORT="${ISAACSIM_STREAM_PORT:-47998}"
WEBRTC_OPTION_SET=false
ROS_DOMAIN_ID_VALUE="${ROS_DOMAIN_ID:-0}"
READY_TIMEOUT=900
ACCEPT_EULA=false
PRIVACY_CONSENT=false
WAIT_FOR_READY=true

fail() { printf 'isaac-sim-workstation: ERROR: %s\n' "$*" >&2; exit 2; }
LEGACY_GUARD="$REPO/ops/pgfr-legacy-guard.sh"
[ -r "$LEGACY_GUARD" ] || fail "missing migration guard: $LEGACY_GUARD"
# shellcheck disable=SC1090
. "$LEGACY_GUARD"
usage() {
  cat <<'EOF'
usage: ops/isaac-sim-workstation.sh MODE [OPTIONS]

Modes (choose exactly one):
  --prepare              Stage the scripted baseline and create private host state.
                         Does not pull an image or start a container.
  --check                Validate the prepared baseline and host, including
                         NVIDIA's transient compatibility-check container.
  --run                  Start the prepared baseline from the pinned local image.

Options:
  --root PATH            Host state root (default: ~/.local/share/policy-gated-factory-robot-orchestrator-reference/isaac-sim).
  --mount PATH           Directory mounted read-only at /scripts
                         (default: ROOT/scripts).
  --container NAME       Container name (default: pgfr-isaac-sim-baseline).
  --profile PROFILE      Presentation profile: headless (default) or x11.
  --webrtc-host IP       Host interface address advertised by headless WebRTC
                         (default: $ISAACSIM_HOST, otherwise 127.0.0.1).
  --webrtc-signal-port PORT
                         WebRTC signaling TCP port (default: 49100).
  --webrtc-stream-port PORT
                         WebRTC media UDP port (default: 47998).
  --display DISPLAY      Local display for the explicit x11 profile
                         (default: $DISPLAY, otherwise :1).
  --ros-domain-id ID     ROS 2 domain, 0..232 (default: $ROS_DOMAIN_ID, otherwise 0).
  --timeout SECONDS      Readiness timeout for --run (default: 900).
  --no-wait              Return after Docker starts instead of waiting for PGFR_CELL_UP.
  --accept-eula          Required with --check and --run; passes ACCEPT_EULA=Y
                         only to NVIDIA containers started by those modes.
  --privacy-consent      Optional telemetry opt-in; otherwise Kit telemetry and
                         all three privacy consent settings are forced off.
  -h, --help             Show this help.

The image is immutable in this launcher:
  nvcr.io/nvidia/isaac-sim:6.0.1@sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb

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
    --profile) [ "$#" -ge 2 ] || fail "--profile requires PROFILE"; PRESENTATION_PROFILE="$2"; shift 2 ;;
    --webrtc-host) [ "$#" -ge 2 ] || fail "--webrtc-host requires IP"; WEBRTC_HOST="$2"; WEBRTC_OPTION_SET=true; shift 2 ;;
    --webrtc-signal-port) [ "$#" -ge 2 ] || fail "--webrtc-signal-port requires PORT"; WEBRTC_SIGNAL_PORT="$2"; WEBRTC_OPTION_SET=true; shift 2 ;;
    --webrtc-stream-port) [ "$#" -ge 2 ] || fail "--webrtc-stream-port requires PORT"; WEBRTC_STREAM_PORT="$2"; WEBRTC_OPTION_SET=true; shift 2 ;;
    --display) [ "$#" -ge 2 ] || fail "--display requires DISPLAY"; DISPLAY_VALUE="$2"; DISPLAY_OPTION_SET=true; shift 2 ;;
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
case "$STATE_ROOT" in /|"$HOME"|"$REPO"|"$REPO"/*) fail "prohibited state root: $STATE_ROOT" ;; esac
case "$MOUNT" in /|"$HOME"|"$REPO"|"$REPO"/*|"$STATE_ROOT") fail "prohibited scripts mount: $MOUNT" ;; esac
case "$STATE_ROOT$MOUNT" in *$'\n'*|*,*) fail "paths must not contain a newline or comma" ;; esac
[[ "$CONTAINER_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] \
  || fail "invalid Docker container name: $CONTAINER_NAME"
[[ "$ROS_DOMAIN_ID_VALUE" =~ ^[0-9]+$ ]] \
  && [ "$ROS_DOMAIN_ID_VALUE" -le 232 ] \
  || fail "ROS domain ID must be an integer from 0 through 232"
[[ "$READY_TIMEOUT" =~ ^[1-9][0-9]*$ ]] \
  && [ "$READY_TIMEOUT" -le 3600 ] \
  || fail "timeout must be an integer from 1 through 3600 seconds"
command -v python3 >/dev/null 2>&1 || fail "missing command: python3"
case "$PRESENTATION_PROFILE" in
  headless)
    $DISPLAY_OPTION_SET && fail "--display is valid only with --profile x11"
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
    ;;
  x11)
    $WEBRTC_OPTION_SET && fail "--webrtc-* options are valid only with --profile headless"
    if [ "$MODE" != prepare ]; then
      [[ "$DISPLAY_VALUE" =~ ^:[0-9]+(\.[0-9]+)?$ ]] \
        || fail "only a local X11 display such as :1 is supported"
    fi
    ;;
  *) fail "--profile must be headless or x11" ;;
esac
if [ "$MODE" = prepare ]; then
  ! $ACCEPT_EULA || fail "--accept-eula is valid only with --check or --run"
else
  $ACCEPT_EULA || fail "--$MODE requires --accept-eula (review NVIDIA's Omniverse license first)"
fi
if [ "$MODE" != run ]; then
  ! $PRIVACY_CONSENT || fail "--privacy-consent is valid only with --run"
  $WAIT_FOR_READY || fail "--no-wait is valid only with --run"
fi

for source in "$SOURCE_ROOT/pgfr_boot.py" "$SOURCE_ROOT/our_factory.usda"; do
  [ -f "$source" ] || fail "required source is missing: $source"
done
[ -d "$SOURCE_ROOT/pgfr_cell" ] || fail "required source is missing: $SOURCE_ROOT/pgfr_cell"
[ -x "$CHECKER" ] || fail "simulation-host checker is not executable: $CHECKER"

require_docker() {
  command -v docker >/dev/null 2>&1 || fail "missing command: docker"
  docker info >/dev/null 2>&1 \
    || fail "Docker daemon is unavailable to this user"
  pgfr_refuse_active_legacy_containers
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
    cd "$SOURCE_ROOT/pgfr_cell"
    find . -type f ! -path '*/__pycache__/*' ! -name '*.py[co]' -print | LC_ALL=C sort
  )
}

installed_file_list() {
  (
    cd "$MOUNT/pgfr_cell"
    find . -type f -print | LC_ALL=C sort
  )
}

verify_baseline() {
  [ -d "$MOUNT/pgfr_cell" ] || fail "baseline package is missing: $MOUNT/pgfr_cell"
  [ -f "$MOUNT/pgfr_boot.py" ] || fail "baseline entrypoint is missing: $MOUNT/pgfr_boot.py"
  [ -f "$MOUNT/our_factory.usda" ] || fail "baseline stage is missing: $MOUNT/our_factory.usda"
  [ ! -L "$MOUNT/pgfr_cell" ] && [ ! -L "$MOUNT/pgfr_boot.py" ] \
    && [ ! -L "$MOUNT/our_factory.usda" ] \
    || fail "installed baseline entrypoints must not be symbolic links"
  [ -z "$(find "$MOUNT/pgfr_cell" -type l -print -quit)" ] \
    || fail "installed baseline must not contain symbolic links"
  [ "$(source_file_list)" = "$(installed_file_list)" ] \
    || fail "installed pgfr_cell file set differs from this checkout; choose a fresh --mount"
  while IFS= read -r relative; do
    cmp -s "$SOURCE_ROOT/pgfr_cell/$relative" "$MOUNT/pgfr_cell/$relative" \
      || fail "installed baseline differs from this checkout: pgfr_cell/$relative"
  done < <(source_file_list)
  cmp -s "$SOURCE_ROOT/pgfr_boot.py" "$MOUNT/pgfr_boot.py" \
    || fail "installed pgfr_boot.py differs from this checkout; choose a fresh --mount"
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
  local stage relative mount_parent
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
      printf 'PGFR_ISAAC_BASELINE_PREPARED mount=%s state=%s unchanged=true\n' "$MOUNT" "$STATE_ROOT"
      return
    fi
  fi

  mount_parent="$(dirname "$MOUNT")"
  if [ ! -d "$mount_parent" ]; then
    install -d -m 0700 "$mount_parent"
  fi
  stage="$(mktemp -d "${MOUNT}.prepare.XXXXXX")"
  trap 'rm -rf "$stage"' RETURN
  while IFS= read -r relative; do
    install -D -m 0644 \
      "$SOURCE_ROOT/pgfr_cell/$relative" "$stage/pgfr_cell/$relative"
  done < <(source_file_list)
  install -m 0644 "$SOURCE_ROOT/pgfr_boot.py" "$stage/pgfr_boot.py"
  install -m 0644 "$SOURCE_ROOT/our_factory.usda" "$stage/our_factory.usda"
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$stage" python3 -c \
    'from pgfr_cell.actions import discover_actions; r=discover_actions(); assert r.action_names == ("haul", "inspect", "move", "pick_and_place", "reset", "spawn")'
  # Validate the complete sibling tree before publishing it. GNU mv -T uses
  # one directory rename here (and can replace only the known-empty target),
  # so readers can observe either no bundle/the old empty directory or the
  # complete bundle, never a partially copied set of entrypoints.
  chmod 0755 "$stage"
  mv -T "$stage" "$MOUNT"
  trap - RETURN
  verify_baseline
  printf 'PGFR_ISAAC_BASELINE_PREPARED mount=%s state=%s unchanged=false\n' "$MOUNT" "$STATE_ROOT"
  printf 'No image was pulled and no container was started.\n'
}

run_nvidia_compatibility_check() {
  local output
  if ! output="$(docker run --pull never --rm --network host --gpus all \
    --user 1234:1234 \
    -e ACCEPT_EULA=Y \
    -e OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1 \
    --entrypoint bash \
    "$IMAGE_REF" \
    /isaac-sim/isaac-sim.compatibility_check.sh \
    --/app/quitAfter=10 --no-window 2>&1)"; then
    printf '%s\n' "$output" >&2
    fail "NVIDIA's bundled Isaac Sim compatibility checker failed"
  fi
  printf '%s\n' "$output"
  case "$output" in
    *'System checking result: PASSED'*) ;;
    *) fail "NVIDIA compatibility checker did not report PASSED" ;;
  esac
  printf 'PGFR_ISAAC_NVIDIA_CHECK_OK image=%s result=PASSED\n' "$IMAGE_REF"
}

check() {
  verify_baseline
  local directory
  local -a checker_args
  require_docker
  command -v python3 >/dev/null 2>&1 || fail "missing command: python3"
  for directory in \
    cache/main cache/computecache config data logs pkg hub-cache runtime; do
    [ -d "$STATE_ROOT/$directory" ] \
      || fail "state directory is missing; run --prepare first: $STATE_ROOT/$directory"
  done
  checker_args=(
    --profile "$PRESENTATION_PROFILE"
    --state-root "$STATE_ROOT"
    --mount "$MOUNT"
  )
  if [ "$PRESENTATION_PROFILE" = headless ]; then
    checker_args+=(
      --webrtc-host "$WEBRTC_HOST"
      --webrtc-signal-port "$WEBRTC_SIGNAL_PORT"
      --webrtc-stream-port "$WEBRTC_STREAM_PORT"
    )
  fi
  PGFR_ISAAC_IMAGE="$IMAGE" PGFR_ISAAC_IMAGE_DIGEST="$DIGEST" \
    DISPLAY="$DISPLAY_VALUE" "$CHECKER" "${checker_args[@]}"
  run_nvidia_compatibility_check
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$MOUNT" python3 -c \
    'from pgfr_cell.actions import discover_actions; r=discover_actions(); assert r.action_names == ("haul", "inspect", "move", "pick_and_place", "reset", "spawn")'
  printf 'PGFR_ISAAC_BASELINE_CHECK_OK mount=%s image=%s profile=%s\n' \
    "$MOUNT" "$IMAGE_REF" "$PRESENTATION_PROFILE"
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

verify_streaming_listener() {
  local listeners
  [ "$PRESENTATION_PROFILE" = headless ] || return
  listeners="$(ss -H -ltn "sport = :$WEBRTC_SIGNAL_PORT" 2>/dev/null || true)"
  [ -n "$listeners" ] \
    || fail "WebRTC signaling TCP port $WEBRTC_SIGNAL_PORT is not listening after application readiness"
}

assert_streaming_ports_available() {
  local listeners
  [ "$PRESENTATION_PROFILE" = headless ] || return
  listeners="$(ss -H -ltn "sport = :$WEBRTC_SIGNAL_PORT" 2>/dev/null || true)"
  [ -z "$listeners" ] \
    || fail "WebRTC signaling TCP port $WEBRTC_SIGNAL_PORT is already in use"
  listeners="$(ss -H -lun "sport = :$WEBRTC_STREAM_PORT" 2>/dev/null || true)"
  [ -z "$listeners" ] \
    || fail "WebRTC media UDP port $WEBRTC_STREAM_PORT is already in use"
}

wait_for_cell() {
  local deadline logs state cell_ready=false stream_ready=false
  if [ "$PRESENTATION_PROFILE" = x11 ]; then
    stream_ready=true
  fi
  deadline=$((SECONDS + READY_TIMEOUT))
  while [ "$SECONDS" -lt "$deadline" ]; do
    # This launcher creates a fresh, uniquely named container, so its complete
    # log belongs to this boot. Never truncate the pass/fail scan: noisy Kit
    # startup can push an early physics/bootstrap error beyond a tail window.
    logs="$(docker logs "$CONTAINER_NAME" 2>&1 || true)"
    if grep -Eq 'PGFR_CELL_BOOT_ERR|PGFR_STEP_ERR' <<<"$logs"; then
      docker logs --tail 80 "$CONTAINER_NAME" >&2 || true
      fail "Isaac cell reported a physics/bootstrap error; container was left intact"
    fi
    if grep -Fq 'PGFR_CELL_UP markers=all' <<<"$logs"; then
      cell_ready=true
    fi
    if grep -Fq 'Isaac Sim Full Streaming App is loaded.' <<<"$logs"; then
      stream_ready=true
    fi
    if $cell_ready && $stream_ready; then
      # Keep observing briefly so an immediately-following asynchronous physics
      # failure cannot be hidden behind a success marker in the same launch.
      sleep 5
      logs="$(docker logs "$CONTAINER_NAME" 2>&1 || true)"
      if grep -Eq 'PGFR_CELL_BOOT_ERR|PGFR_STEP_ERR' <<<"$logs"; then
        docker logs --tail 80 "$CONTAINER_NAME" >&2 || true
        fail "Isaac cell failed during the post-ready stability window; container was left intact"
      fi
      state="$(docker container inspect --format '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || true)"
      [ "$state" = running ] \
        || fail "container stopped during the post-ready stability window (state=${state:-missing}); it was left intact"
      verify_streaming_listener
      if [ "$PRESENTATION_PROFILE" = headless ]; then
        printf 'PGFR_ISAAC_BASELINE_READY container=%s profile=headless marker=PGFR_CELL_UP streaming=true webrtc_host=%s signal_tcp=%s stream_udp=%s\n' \
          "$CONTAINER_NAME" "$WEBRTC_HOST" "$WEBRTC_SIGNAL_PORT" \
          "$WEBRTC_STREAM_PORT"
      else
        printf 'PGFR_ISAAC_BASELINE_READY container=%s profile=x11 marker=PGFR_CELL_UP\n' \
          "$CONTAINER_NAME"
      fi
      return
    fi
    state="$(docker container inspect --format '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || true)"
    if [ "$state" != running ]; then
      docker logs --tail 80 "$CONTAINER_NAME" >&2 || true
      fail "container stopped before required readiness markers (state=${state:-missing}); it was left intact"
    fi
    sleep 2
  done
  docker logs --tail 80 "$CONTAINER_NAME" >&2 || true
  fail "timed out waiting for required readiness markers; the running container was left intact"
}

run() {
  local xauth_file="" container_id
  local -a docker_args
  $ACCEPT_EULA \
    || fail "--run requires --accept-eula (review NVIDIA's Omniverse license first)"
  require_docker
  assert_container_absent
  assert_mount_idle
  check
  if [ "$PRESENTATION_PROFILE" = x11 ]; then
    command -v xauth >/dev/null 2>&1 || fail "missing command: xauth"
    xauth_file="$(prepare_xauthority)"
  fi
  assert_container_absent
  assert_mount_idle
  # Host networking gives Isaac direct ownership of these ports. Verify both
  # immediately before launch so the readiness listener cannot be unrelated.
  assert_streaming_ports_available

  docker_args=(
    run -d --pull never --name "$CONTAINER_NAME"
    --user 1234:1234
    --gpus all --network host --ipc=shareable --shm-size 2g
    -e ACCEPT_EULA=Y
    -e PGFR_STAGE=/scripts/our_factory.usda
    -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID_VALUE"
    -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
    -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp
    --mount "type=bind,source=$MOUNT,target=/scripts,readonly"
    --mount "type=bind,source=$STATE_ROOT/cache/main,target=/isaac-sim/.cache"
    --mount "type=bind,source=$STATE_ROOT/cache/computecache,target=/isaac-sim/.nv/ComputeCache"
    --mount "type=bind,source=$STATE_ROOT/config,target=/isaac-sim/.nvidia-omniverse/config"
    --mount "type=bind,source=$STATE_ROOT/data,target=/isaac-sim/.local/share/ov/data"
    --mount "type=bind,source=$STATE_ROOT/logs,target=/isaac-sim/.nvidia-omniverse/logs"
    --mount "type=bind,source=$STATE_ROOT/pkg,target=/isaac-sim/.local/share/ov/pkg"
    --mount "type=bind,source=$STATE_ROOT/hub-cache,target=/var/cache/hub"
  )
  if [ "$PRESENTATION_PROFILE" = headless ]; then
    docker_args+=(
      --entrypoint /isaac-sim/runheadless.sh
      -e ISAACSIM_HOST="$WEBRTC_HOST"
      -e ISAACSIM_SIGNAL_PORT="$WEBRTC_SIGNAL_PORT"
      -e ISAACSIM_STREAM_PORT="$WEBRTC_STREAM_PORT"
    )
  else
    docker_args+=(
      --entrypoint /isaac-sim/isaac-sim.sh
      -e DISPLAY="$DISPLAY_VALUE"
      -e XAUTHORITY=/tmp/pgfr-isaac.xauth
      --mount "type=bind,source=/tmp/.X11-unix,target=/tmp/.X11-unix,readonly"
      --mount "type=bind,source=$xauth_file,target=/tmp/pgfr-isaac.xauth,readonly"
    )
  fi
  if $PRIVACY_CONSENT; then
    docker_args+=(-e PRIVACY_CONSENT=Y)
  else
    docker_args+=(-e OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1)
  fi
  docker_args+=("$IMAGE_REF")
  if [ "$PRESENTATION_PROFILE" = headless ]; then
    docker_args+=(-v)
  fi
  docker_args+=(
    --/persistent/isaac/asset_root/default="$ASSET_ROOT"
    --/persistent/app/omniverse/bookmarks/Isaac_Cloud_Assets="$ASSET_ROOT"
  )
  if ! $PRIVACY_CONSENT; then
    # Retain the validated Kit-level controls as defense in depth alongside
    # NVIDIA's documented container opt-out environment variable.
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
  docker_args+=(--exec /scripts/pgfr_boot.py)
  container_id="$(docker "${docker_args[@]}")" \
    || fail "Docker did not start the container; any failed container was left intact"
  if [ "$PRESENTATION_PROFILE" = headless ]; then
    printf 'PGFR_ISAAC_BASELINE_STARTING container=%s id=%s profile=headless webrtc_host=%s signal_tcp=%s stream_udp=%s\n' \
      "$CONTAINER_NAME" "$container_id" "$WEBRTC_HOST" \
      "$WEBRTC_SIGNAL_PORT" "$WEBRTC_STREAM_PORT"
  else
    printf 'PGFR_ISAAC_BASELINE_STARTING container=%s id=%s profile=x11 display=%s\n' \
      "$CONTAINER_NAME" "$container_id" "$DISPLAY_VALUE"
  fi
  printf 'Logs: docker logs -f %q\n' "$CONTAINER_NAME"
  if $WAIT_FOR_READY; then
    wait_for_cell
  else
    printf 'Expected marker: PGFR_CELL_UP markers=all\n'
    if [ "$PRESENTATION_PROFILE" = headless ]; then
      printf 'Expected marker: Isaac Sim Full Streaming App is loaded.\n'
    fi
  fi
}

case "$MODE" in
  prepare) prepare ;;
  check) check ;;
  run) run ;;
esac
