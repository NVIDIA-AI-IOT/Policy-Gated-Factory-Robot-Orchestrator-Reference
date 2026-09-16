#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Install the Policy-Gated Factory Robot Orchestrator Reference GR00T runtime into an idle Isaac mount.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISAAC_DEPLOYMENT="$REPO/reference/isaac-cell/deployment"
CAPTURE_CONTEXT="$REPO/reference/groot/capture_context"
RUNTIME="$REPO/reference/groot/runtime"
BATCH_RELAY="$REPO/reference/groot/relay/native_droid_relay_batch2.py"
RENDERER="$REPO/ops/render-groot-cont24-contracts.py"
MOUNT=""
CHECKPOINT_PATH=""
CHECKPOINT_METADATA=""
LEFT_SERVICE_STATE=""
RIGHT_SERVICE_STATE=""
LEFT_POLICY_PORT="5592"
RIGHT_POLICY_PORT="5593"
LEFT_RELAY_PORT="5641"
RIGHT_RELAY_PORT="5642"

fail() { printf 'install-groot-cell: ERROR: %s\n' "$*" >&2; exit 2; }
LEGACY_GUARD="$REPO/ops/pgfr-legacy-guard.sh"
[ -r "$LEGACY_GUARD" ] || fail "missing migration guard: $LEGACY_GUARD"
# shellcheck disable=SC1090
. "$LEGACY_GUARD"
usage() {
  cat >&2 <<EOF
usage: $0 --mount PATH --checkpoint-path PATH \\
  --left-service-state PATH --right-service-state PATH \\
  [--checkpoint-metadata /absolute/pgfr_checkpoint.json] \\
  [--left-policy-port PORT] [--right-policy-port PORT] \\
  [--left-relay-port PORT] [--right-relay-port PORT]
EOF
  exit 2
}
capture_home_matches() {
  python3 -c '
import json
import sys

expected = json.load(open(sys.argv[1], encoding="utf-8"))[0]["fl_joints"]
installed = json.load(open(sys.argv[2], encoding="utf-8"))[0]["fl_joints"]
raise SystemExit(0 if installed == expected else 1)
' "$1" "$2"
}
assert_mount_idle() {
  local container_id name source target_mount
  command -v docker >/dev/null 2>&1 || return
  target_mount="$(realpath -m "$MOUNT")"
  while IFS= read -r container_id; do
    [ -n "$container_id" ] || continue
    source="$(docker container inspect --format \
      '{{range .Mounts}}{{if eq .Destination "/scripts"}}{{.Source}}{{end}}{{end}}' \
      "$container_id")"
    if [ -n "$source" ] && [ "$(realpath -m "$source")" = "$target_mount" ]; then
      name="$(docker container inspect --format '{{.Name}}' "$container_id")"
      fail "${name#/} is active; this installer never replaces live files beneath its scripts mount"
    fi
  done < <(docker ps -q)
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mount) MOUNT="${2:-}"; shift 2 ;;
    --checkpoint-path) CHECKPOINT_PATH="${2:-}"; shift 2 ;;
    --checkpoint-metadata) CHECKPOINT_METADATA="${2:-}"; shift 2 ;;
    --left-service-state) LEFT_SERVICE_STATE="${2:-}"; shift 2 ;;
    --right-service-state) RIGHT_SERVICE_STATE="${2:-}"; shift 2 ;;
    --left-policy-port) LEFT_POLICY_PORT="${2:-}"; shift 2 ;;
    --right-policy-port) RIGHT_POLICY_PORT="${2:-}"; shift 2 ;;
    --left-relay-port) LEFT_RELAY_PORT="${2:-}"; shift 2 ;;
    --right-relay-port) RIGHT_RELAY_PORT="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[ -n "$MOUNT" ] || usage
[ -n "$CHECKPOINT_PATH" ] || usage
[ -n "$LEFT_SERVICE_STATE" ] || usage
[ -n "$RIGHT_SERVICE_STATE" ] || usage
[ -d "$MOUNT" ] || fail "Isaac scripts mount does not exist: $MOUNT"
pgfr_refuse_active_legacy_containers
assert_mount_idle

for source in \
  "$RUNTIME/cell/reset_two_arm.py" \
  "$RUNTIME/native_droid_work/executors/follow_groot_home_convergence_v36.py" \
  "$RUNTIME/native_droid_work/follow_groot_dual_physical_v36.py" \
  "$RUNTIME/native_droid_work/pgfr_groot_certified_deployment_v36.py" \
  "$RUNTIME/native_droid_work/pgfr_groot_dual_concurrent_mixed.py" \
  "$RENDERER" \
  "$BATCH_RELAY"; do
  [ -f "$source" ] || fail "required source is missing: $source"
done

CONTRACT_STAGE="$(mktemp -d)"
trap 'rm -rf "$CONTRACT_STAGE"' EXIT
CHECKPOINT_ARGS=(--checkpoint-path "$CHECKPOINT_PATH")
if [ -n "$CHECKPOINT_METADATA" ]; then
  CHECKPOINT_ARGS+=(--checkpoint-metadata "$CHECKPOINT_METADATA")
fi
python3 "$RENDERER" \
  "${CHECKPOINT_ARGS[@]}" \
  --left-service-state "$LEFT_SERVICE_STATE" \
  --right-service-state "$RIGHT_SERVICE_STATE" \
  --left-policy-port "$LEFT_POLICY_PORT" \
  --right-policy-port "$RIGHT_POLICY_PORT" \
  --left-relay-port "$LEFT_RELAY_PORT" \
  --right-relay-port "$RIGHT_RELAY_PORT" \
  --output-dir "$CONTRACT_STAGE"

for name in \
  startup.py cmd.py our_factory.usda full_scene_bootstrap.py \
  setup_right_cell.py pgfr_node_v2.py pgfr_cams_rp.py add_tote_colors.py \
  matte_scene.py fix_amr_haul_joint.py pgfr_serving_health.py \
  pgfr_shape_mode.py production_contract_expected.json; do
  install -m 0644 "$ISAAC_DEPLOYMENT/$name" "$MOUNT/$name"
done
install -m 0644 "$RUNTIME/cell/reset_two_arm.py" "$MOUNT/reset_two_arm.py"
install -m 0644 "$CONTRACT_STAGE/groot_shared_policy_contract.json" \
  "$MOUNT/groot_shared_policy_contract.json"
install -m 0644 "$CONTRACT_STAGE/groot_shared_concurrent_policy_contract.json" \
  "$MOUNT/groot_shared_concurrent_policy_contract.json"

install -d "$MOUNT/native_droid_work/executors"
install -m 0644 \
  "$RUNTIME/native_droid_work/executors/follow_groot_home_convergence_v36.py" \
  "$MOUNT/native_droid_work/executors/follow_groot_home_convergence_v36.py"
for name in follow_groot_dual_physical_v36.py \
  pgfr_groot_certified_deployment_v36.py \
  pgfr_groot_dual_concurrent_mixed.py; do
  install -m 0644 "$RUNTIME/native_droid_work/$name" \
    "$MOUNT/native_droid_work/$name"
done
install -m 0644 "$RUNTIME/native_droid_work/pgfr_sync_capture_cell.py" \
  "$MOUNT/native_droid_work/pgfr_sync_capture_cell.py"
install -m 0644 "$BATCH_RELAY" \
  "$MOUNT/native_droid_work/native_droid_relay_batch2.py"

while IFS= read -r -d '' source; do
  relative="${source#"$CAPTURE_CONTEXT/"}"
  destination="$MOUNT/groot_capture_context/$relative"
  # The repository carries the first state needed by deployment; an existing
  # installation may retain the complete root-owned recording.  Preserve it
  # only when its first joint state matches the pinned distilled evidence.
  if [ -f "$destination" ]; then
    if cmp -s "$source" "$destination" \
      || capture_home_matches "$source" "$destination"; then
      continue
    fi
    fail "installed capture evidence conflicts with bundle: $relative"
  fi
  install -D -m 0644 "$source" "$destination"
done < <(find "$CAPTURE_CONTEXT" -type f -print0)

echo "PGFR_GROOT_CELL_INSTALLED mount=$MOUNT runtime=order744-cont24-v36"
echo "No simulation was started or restarted."
