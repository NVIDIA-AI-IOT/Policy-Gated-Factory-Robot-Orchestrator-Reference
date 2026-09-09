#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Destructive live acceptance for the packaged scripted Isaac Sim baseline.
# The target must already be running. This command never starts, stops, or
# removes it, and it publishes each uniquely identified ROS command once.

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
CLIENT="$SCRIPT_DIR/isaac_sim_acceptance.py"
SOURCE_ROOT="$REPO/reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell"
ROS_IMAGE="docker.io/library/ros:jazzy-ros-base-noble@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4"
ISAAC_IMAGE="nvcr.io/nvidia/isaac-sim:6.0.1"
ISAAC_DIGEST="sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb"
ISAAC_IMAGE_REF="$ISAAC_IMAGE@$ISAAC_DIGEST"
EXPECTED_USER="1234:1234"
EXPECTED_ENTRYPOINT="/isaac-sim/runheadless.sh"
REQUIRED_PRIVACY_ARGUMENTS=(
  --/telemetry/enableAnonymousAppName=false
  --/telemetry/enableAnonymousData=false
  --/telemetry/useOpenEndpoint=false
  --/privacy/usage=false
  --/privacy/performance=false
  --/privacy/personalization=false
  --/crashreporter/enabled=false
)

CONTAINER="${PGFR_ISAAC_CONTAINER:-pgfr-isaac-sim-baseline}"
ROS_DOMAIN_OVERRIDE=""
READY_TIMEOUT=900
DISCOVERY_TIMEOUT=30
STREAM_TIMEOUT=90
RESULT_TIMEOUT=180
LOG_TIMEOUT=30

fail() {
  printf 'PGFR_ISAAC_WORKSTATION_ACCEPTANCE_FAIL: %s\n' "$*" >&2
  exit 2
}

usage() {
  cat <<'EOF'
Usage: ops/accept-isaac-sim-workstation.sh [OPTIONS]

Run a destructive ROS acceptance cycle against an already-running packaged
Isaac Sim baseline. The cycle resets the scene, validates all 15 application
streams, moves the red cube with franka_left, and performs a final reset.

Options:
  --container NAME       Target container (default: pgfr-isaac-sim-baseline).
  --ros-domain-id ID     Require this value to match the target ROS_DOMAIN_ID.
  --ready-timeout SEC    Wait for PGFR_CELL_UP (default: 900).
  --discovery-timeout S  Wait for the one command subscriber (default: 30).
  --stream-timeout SEC   Wait for streams and observed state (default: 90).
  --result-timeout SEC   Wait for each unique goal result (default: 180).
  --log-timeout SEC      Wait for three unique simulator command logs
                         (default: 30).
  -h, --help             Show this help.

The pinned ROS sidecar image must already exist locally. The target must use a
shareable IPC namespace. No state-changing ROS command is automatically retried.
EOF
}

while (($#)); do
  case "$1" in
    --container)
      (($# >= 2)) || fail "--container requires NAME"
      CONTAINER="$2"
      shift 2
      ;;
    --ros-domain-id)
      (($# >= 2)) || fail "--ros-domain-id requires ID"
      ROS_DOMAIN_OVERRIDE="$2"
      shift 2
      ;;
    --ready-timeout)
      (($# >= 2)) || fail "--ready-timeout requires SEC"
      READY_TIMEOUT="$2"
      shift 2
      ;;
    --discovery-timeout)
      (($# >= 2)) || fail "--discovery-timeout requires SEC"
      DISCOVERY_TIMEOUT="$2"
      shift 2
      ;;
    --stream-timeout)
      (($# >= 2)) || fail "--stream-timeout requires SEC"
      STREAM_TIMEOUT="$2"
      shift 2
      ;;
    --result-timeout)
      (($# >= 2)) || fail "--result-timeout requires SEC"
      RESULT_TIMEOUT="$2"
      shift 2
      ;;
    --log-timeout)
      (($# >= 2)) || fail "--log-timeout requires SEC"
      LOG_TIMEOUT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

[[ "$CONTAINER" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] \
  || fail "container name contains unsupported characters: $CONTAINER"
[[ "$READY_TIMEOUT" =~ ^[1-9][0-9]*$ ]] \
  || fail "--ready-timeout must be a positive integer"
[[ "$LOG_TIMEOUT" =~ ^[1-9][0-9]*$ ]] \
  || fail "--log-timeout must be a positive integer"
for timeout_name in DISCOVERY_TIMEOUT STREAM_TIMEOUT RESULT_TIMEOUT; do
  timeout_value="${!timeout_name}"
  [[ "$timeout_value" =~ ^[0-9]+([.][0-9]+)?$ ]] \
    || fail "${timeout_name,,} must be a positive number"
  [[ "$timeout_value" =~ [1-9] ]] \
    || fail "${timeout_name,,} must be greater than zero"
done
[[ -r "$CLIENT" ]] || fail "acceptance client is missing: $CLIENT"
for command in cmp diff docker; do
  command -v "$command" >/dev/null 2>&1 || fail "$command is not installed"
done
[[ "$(uname -m)" == "x86_64" ]] \
  || fail "the pinned acceptance sidecar is linux/amd64; x86_64 is required"
docker version >/dev/null 2>&1 || fail "Docker Engine is unavailable"

running="$(docker inspect --format '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" \
  || fail "container does not exist: $CONTAINER"
[[ "$running" == "true" ]] || fail "container is not running: $CONTAINER"

expected_image_id="$(
  docker image inspect --format '{{.Id}}' "$ISAAC_IMAGE_REF" 2>/dev/null
)" || fail "pinned Isaac Sim image is absent; pull exactly: docker pull --platform linux/amd64 $ISAAC_IMAGE_REF"
[[ "$expected_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] \
  || fail "cannot resolve a valid image ID for $ISAAC_IMAGE_REF"
container_image_id="$(docker inspect --format '{{.Image}}' "$CONTAINER")" \
  || fail "cannot inspect image identity for $CONTAINER"
[[ "$container_image_id" == "$expected_image_id" ]] \
  || fail "$CONTAINER does not use the pinned Isaac Sim 6.0.1 image (expected: $expected_image_id; found: $container_image_id)"

effective_user="$(docker inspect --format '{{.Config.User}}' "$CONTAINER")" \
  || fail "cannot inspect effective user for $CONTAINER"
[[ "$effective_user" == "$EXPECTED_USER" ]] \
  || fail "$CONTAINER must use --user $EXPECTED_USER (found: ${effective_user:-unset})"
effective_entrypoint="$(docker inspect --format '{{.Path}}' "$CONTAINER")" \
  || fail "cannot inspect effective entrypoint for $CONTAINER"
[[ "$effective_entrypoint" == "$EXPECTED_ENTRYPOINT" ]] \
  || fail "$CONTAINER must use --entrypoint $EXPECTED_ENTRYPOINT (found: ${effective_entrypoint:-unset})"

ipc_mode="$(docker inspect --format '{{.HostConfig.IpcMode}}' "$CONTAINER")" \
  || fail "cannot inspect IPC mode for $CONTAINER"
[[ "$ipc_mode" == "shareable" ]] \
  || fail "$CONTAINER must use --ipc=shareable (found: $ipc_mode)"

network_mode="$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$CONTAINER")" \
  || fail "cannot inspect network mode for $CONTAINER"
[[ "$network_mode" == "host" ]] \
  || fail "$CONTAINER must use --network host (found: $network_mode)"

scripts_mount_marker="$(
  docker inspect --format \
    '{{range .Mounts}}{{if eq .Destination "/scripts"}}x{{end}}{{end}}' \
    "$CONTAINER"
)" || fail "cannot inspect /scripts mounts for $CONTAINER"
[[ "$scripts_mount_marker" == "x" ]] \
  || fail "$CONTAINER must have exactly one /scripts mount"
scripts_mount_type="$(
  docker inspect --format \
    '{{range .Mounts}}{{if eq .Destination "/scripts"}}{{.Type}}{{end}}{{end}}' \
    "$CONTAINER"
)" || fail "cannot inspect /scripts mount type for $CONTAINER"
scripts_mount_source="$(
  docker inspect --format \
    '{{range .Mounts}}{{if eq .Destination "/scripts"}}{{.Source}}{{end}}{{end}}' \
    "$CONTAINER"
)" || fail "cannot inspect /scripts mount source for $CONTAINER"
scripts_mount_rw="$(
  docker inspect --format \
    '{{range .Mounts}}{{if eq .Destination "/scripts"}}{{.RW}}{{end}}{{end}}' \
    "$CONTAINER"
)" || fail "cannot inspect /scripts mount access for $CONTAINER"
[[ "$scripts_mount_type" == "bind" && "$scripts_mount_rw" == "false" ]] \
  || fail "$CONTAINER /scripts must be one read-only bind mount"
[[ "$scripts_mount_source" == /* && -d "$scripts_mount_source" \
  && ! -L "$scripts_mount_source" ]] \
  || fail "$CONTAINER /scripts bind source is not a local regular directory"
for payload in pgfr_boot.py our_factory.usda; do
  [[ -f "$SOURCE_ROOT/$payload" && ! -L "$SOURCE_ROOT/$payload" ]] \
    || fail "checkout payload is missing or invalid: $SOURCE_ROOT/$payload"
  [[ -f "$scripts_mount_source/$payload" \
    && ! -L "$scripts_mount_source/$payload" ]] \
    || fail "mounted payload is missing or invalid: $scripts_mount_source/$payload"
  cmp -s "$SOURCE_ROOT/$payload" "$scripts_mount_source/$payload" \
    || fail "mounted payload differs from this checkout: $payload"
done
[[ -d "$SOURCE_ROOT/pgfr_cell" && ! -L "$SOURCE_ROOT/pgfr_cell" \
  && -d "$scripts_mount_source/pgfr_cell" \
  && ! -L "$scripts_mount_source/pgfr_cell" ]] \
  || fail "mounted pgfr_cell tree is missing or invalid"
diff -qr --no-dereference --exclude=__pycache__ --exclude='*.pyc' \
  "$SOURCE_ROOT/pgfr_cell" "$scripts_mount_source/pgfr_cell" \
  || fail "mounted pgfr_cell tree differs from this checkout"

container_arguments="$(
  docker inspect --format '{{range .Args}}{{println .}}{{end}}' "$CONTAINER"
)" || fail "cannot inspect command arguments for $CONTAINER"
exec_flag_count="$(
  awk '$0 == "--exec" {count++} END {print count + 0}' \
    <<<"$container_arguments"
)"
exec_pair_count="$(
  awk 'previous == "--exec" && $0 == "/scripts/pgfr_boot.py" {count++} {previous=$0} END {print count + 0}' \
    <<<"$container_arguments"
)"
[[ "$exec_flag_count" == "1" && "$exec_pair_count" == "1" ]] \
  || fail "$CONTAINER must execute exactly --exec /scripts/pgfr_boot.py"
for required_argument in "${REQUIRED_PRIVACY_ARGUMENTS[@]}"; do
  argument_key="${required_argument%%=*}"
  argument_key_count="$(
    awk -v key="$argument_key" \
      '$0 == key || index($0, key "=") == 1 {count++} END {print count + 0}' \
      <<<"$container_arguments"
  )"
  argument_exact_count="$(
    awk -v expected="$required_argument" \
      '$0 == expected {count++} END {print count + 0}' \
      <<<"$container_arguments"
  )"
  [[ "$argument_key_count" == "1" && "$argument_exact_count" == "1" ]] \
    || fail "$CONTAINER must define exactly one default opt-out argument: $required_argument"
done

container_environment="$(
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$CONTAINER"
)" || fail "cannot inspect environment for $CONTAINER"
for required_environment in \
  ACCEPT_EULA=Y \
  OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1; do
  environment_key="${required_environment%%=*}"
  environment_key_count="$(
    awk -F= -v key="$environment_key" \
      '$1 == key {count++} END {print count + 0}' \
      <<<"$container_environment"
  )"
  environment_exact_count="$(
    awk -v expected="$required_environment" \
      '$0 == expected {count++} END {print count + 0}' \
      <<<"$container_environment"
  )"
  [[ "$environment_key_count" == "1" && "$environment_exact_count" == "1" ]] \
    || fail "$CONTAINER must define exactly $required_environment"
done
container_stage="$(
  awk -F= '$1 == "PGFR_STAGE" {print substr($0, index($0, "=") + 1); exit}' \
    <<<"$container_environment"
)"
container_stage_count="$(
  awk -F= '$1 == "PGFR_STAGE" {count++} END {print count + 0}' \
    <<<"$container_environment"
)"
[[ "$container_stage_count" == "1" \
  && "$container_stage" == "/scripts/our_factory.usda" ]] \
  || fail "$CONTAINER must define exactly PGFR_STAGE=/scripts/our_factory.usda"
container_domain="$(
  awk -F= '$1 == "ROS_DOMAIN_ID" {print substr($0, index($0, "=") + 1); exit}' \
    <<<"$container_environment"
)"
container_domain_count="$(
  awk -F= '$1 == "ROS_DOMAIN_ID" {count++} END {print count + 0}' \
    <<<"$container_environment"
)"
[[ "$container_domain_count" == "1" ]] \
  || fail "$CONTAINER must define exactly one ROS_DOMAIN_ID (found: $container_domain_count)"
[[ "$container_domain" =~ ^[0-9]+$ ]] \
  && ((container_domain <= 232)) \
  || fail "ROS domain ID must be an integer from 0 through 232"
if [[ -n "$ROS_DOMAIN_OVERRIDE" ]]; then
  [[ "$ROS_DOMAIN_OVERRIDE" =~ ^[0-9]+$ ]] \
    && ((ROS_DOMAIN_OVERRIDE <= 232)) \
    || fail "--ros-domain-id must be an integer from 0 through 232"
  [[ "$ROS_DOMAIN_OVERRIDE" == "$container_domain" ]] \
    || fail "--ros-domain-id $ROS_DOMAIN_OVERRIDE does not match $CONTAINER ROS_DOMAIN_ID $container_domain"
fi
ROS_DOMAIN_ID_VALUE="$container_domain"

docker image inspect "$ROS_IMAGE" >/dev/null 2>&1 \
  || fail "pinned ROS sidecar is absent; pull exactly: docker pull --platform linux/amd64 $ROS_IMAGE"

critical_pattern='PGFR_CELL_BOOT_ERR|PGFR_STEP_ERR|Traceback \(most recent call last\)|CUDA[^[:cntrl:]]*(error|fail)|out of memory|(^|[^[:alnum:]_])OOM([^[:alnum:]_]|$)|segmentation fault|fatal python error'

wait_for_ready() {
  local deadline logs now
  deadline=$((SECONDS + READY_TIMEOUT))
  while :; do
    logs="$(docker logs "$CONTAINER" 2>&1)" \
      || fail "cannot read logs from $CONTAINER"
    if grep -Eiq "$critical_pattern" <<<"$logs"; then
      grep -Ei "$critical_pattern" <<<"$logs" >&2 || true
      fail "$CONTAINER has a critical log marker"
    fi
    # Avoid an early-exit grep pipeline here. Under pipefail, a large log can
    # make the producer receive SIGPIPE after grep -q finds the marker, turning
    # a successful readiness match into a false negative.
    if grep -Fq 'PGFR_CELL_UP markers=all' <<<"$logs"; then
      printf 'PGFR_ISAAC_ACCEPTANCE_READY container=%s marker=PGFR_CELL_UP domain=%s\n' \
        "$CONTAINER" "$ROS_DOMAIN_ID_VALUE"
      return
    fi
    running="$(docker inspect --format '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" \
      || fail "container disappeared while waiting: $CONTAINER"
    [[ "$running" == "true" ]] || fail "container stopped before PGFR_CELL_UP: $CONTAINER"
    now=$SECONDS
    ((now < deadline)) || fail "timed out waiting for PGFR_CELL_UP from $CONTAINER"
    sleep 2
  done
}

wait_for_ready

run_id="$(tr -d '-' </proc/sys/kernel/random/uuid)"
run_id="${run_id:0:12}"
log_since="$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)"
temporary="$(mktemp -d)"
trap 'rm -rf -- "$temporary"' EXIT
current_log="$temporary/isaac-current-run.log"
expected_goals=(
  "accept-$run_id-reset-before"
  "accept-$run_id-move-red"
  "accept-$run_id-reset-after"
)

refresh_current_run_logs() {
  docker logs --since "$log_since" "$CONTAINER" >"$current_log" 2>&1 \
    || fail "cannot read current-run logs from $CONTAINER"
  if grep -Eiq "$critical_pattern" "$current_log"; then
    grep -Ei "$critical_pattern" "$current_log" >&2 || true
    fail "critical simulator log marker appeared during acceptance run $run_id"
  fi
}

wait_for_unique_command_logs() {
  local deadline goal command_count all_present
  deadline=$((SECONDS + LOG_TIMEOUT))
  while :; do
    refresh_current_run_logs
    all_present=true
    for goal in "${expected_goals[@]}"; do
      command_count="$(
        awk -v goal="$goal" \
          'index($0, "PGFR_CMD ") && index($0, goal) {count++} END {print count + 0}' \
          "$current_log"
      )"
      ((command_count <= 1)) \
        || fail "goal $goal was observed $command_count times in current-run logs"
      if awk -v goal="$goal" \
        'index($0, "PGFR_DUP ") && index($0, goal) {found=1} END {exit !found}' \
        "$current_log"; then
        fail "simulator rejected duplicate goal: $goal"
      fi
      [[ "$command_count" == "1" ]] || all_present=false
    done
    $all_present && return
    ((SECONDS < deadline)) \
      || fail "timed out waiting for exactly one PGFR_CMD record for all three goals in run $run_id"
    sleep 1
  done
}

sidecar_status=0
docker run --rm --pull never --platform linux/amd64 \
  --network host \
  --ipc="container:$CONTAINER" \
  --user 1234:1234 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --security-opt no-new-privileges:true \
  --cap-drop ALL \
  -e HOME=/tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID_VALUE" \
  -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
  -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  --mount "type=bind,source=$CLIENT,target=/isaac_sim_acceptance.py,readonly" \
  "$ROS_IMAGE" \
  python3 /isaac_sim_acceptance.py \
    --run-id "$run_id" \
    --discovery-timeout "$DISCOVERY_TIMEOUT" \
    --stream-timeout "$STREAM_TIMEOUT" \
    --result-timeout "$RESULT_TIMEOUT" \
  || sidecar_status=$?

if ((sidecar_status != 0)); then
  refresh_current_run_logs
  fail "ROS acceptance sidecar exited with status $sidecar_status (run $run_id)"
fi

# ROS results can precede Docker log-driver visibility. Poll only for evidence
# from the three already-published unique goals; never republish a command.
wait_for_unique_command_logs

printf 'PGFR_ISAAC_ACCEPTANCE_LOGS_OK run_id=%s commands=3 critical=0\n' "$run_id"
printf 'PGFR_ISAAC_WORKSTATION_ACCEPTANCE_PASS container=%s domain=%s run_id=%s\n' \
  "$CONTAINER" "$ROS_DOMAIN_ID_VALUE" "$run_id"
