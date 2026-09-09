#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Install only the shared Order744-cont24 GR00T profiles on an idle Thor stack.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ops/install-groot-thor-shared-profiles.sh

Verifies the existing generic GR00T policy/relay templates and the pinned
Order744-cont24 checkpoint, then installs only the two shared profiles and
their target. The command never enables or starts a service.
EOF
}

if (($#)); then
  case "$1" in
    -h|--help) usage; exit 0 ;;
    *) echo "install-groot-thor-shared-profiles: ERROR: no arguments are accepted" >&2; exit 2 ;;
  esac
fi

PGFR_REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
PGFR_USER_HOME=${HOME:?HOME is required}
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$PGFR_USER_HOME/.config}/systemd/user"
GROOT_ENV_DIR="${XDG_CONFIG_HOME:-$PGFR_USER_HOME/.config}/pgfr-spine/groot"
STATE_ROOT="$PGFR_USER_HOME/.local/share/pgfr-spine/groot"
MODEL_ROOT="$PGFR_USER_HOME/policy-gated-factory-robot-orchestrator-reference-models/order744-cont24"
POLICY_UNIT="$SYSTEMD_DIR/pgfr-groot-policy@.service"
RELAY_UNIT="$SYSTEMD_DIR/pgfr-groot-relay@.service"
TARGET_NAME=pgfr-groot-shared-stack.target
TARGET_SOURCE="$PGFR_REPO/ops/systemd/groot/$TARGET_NAME"
LEFT_SOURCE="$PGFR_REPO/ops/systemd/groot/shared-left.env"
RIGHT_SOURCE="$PGFR_REPO/ops/systemd/groot/shared-right.env"
VERIFY_MODEL="$PGFR_REPO/ops/verify-groot-models.sh"
SHARED_UNITS=(
  "$TARGET_NAME"
  pgfr-groot-policy@shared-left.service
  pgfr-groot-policy@shared-right.service
  pgfr-groot-relay@shared-left.service
  pgfr-groot-relay@shared-right.service
)
SHARED_PORTS=(5592 5593 5641 5642)

fail() {
  printf 'install-groot-thor-shared-profiles: ERROR: %s\n' "$*" >&2
  exit 2
}

LEGACY_GUARD="$PGFR_REPO/ops/pgfr-legacy-guard.sh"
[[ -r $LEGACY_GUARD ]] || fail "missing migration guard: $LEGACY_GUARD"
# shellcheck disable=SC1090
. "$LEGACY_GUARD"

for command in systemctl python3 grep cmp install mktemp sed mv dirname basename rm; do
  command -v "$command" >/dev/null 2>&1 || fail "missing command: $command"
done
for source in "$TARGET_SOURCE" "$LEFT_SOURCE" "$RIGHT_SOURCE" "$VERIFY_MODEL"; do
  [[ -f $source && ! -L $source ]] || fail "missing regular source file: $source"
done
pgfr_refuse_active_legacy_units
for unit in "${SHARED_UNITS[@]}"; do
  if systemctl --user --quiet is-active "$unit" 2>/dev/null; then
    fail "$unit is active; this installer never changes an active shared stack"
  fi
done

for installed in "$POLICY_UNIT" "$RELAY_UNIT"; do
  [[ -f $installed && ! -L $installed ]] || fail "compatible generic unit must already be installed: $installed"
done

require_line() {
  local file=$1 expected=$2
  grep -Fqx -- "$expected" "$file" || fail "installed unit contract mismatch in $file: $expected"
}
require_text() {
  local file=$1 expected=$2
  grep -Fq -- "$expected" "$file" || fail "installed unit contract mismatch in $file: $expected"
}

require_line "$POLICY_UNIT" "WorkingDirectory=$PGFR_USER_HOME/groot_shadow/Isaac-GR00T"
require_line "$POLICY_UNIT" "EnvironmentFile=$PGFR_USER_HOME/.config/pgfr-spine/groot/%i.env"
require_text "$POLICY_UNIT" "ExecStart=$PGFR_USER_HOME/groot_shadow/Isaac-GR00T/.venv/bin/python gr00t/eval/run_gr00t_server.py"
require_text "$POLICY_UNIT" "--host 127.0.0.1"
require_text "$POLICY_UNIT" '--port ${POLICY_PORT} --model-path ${MODEL_PATH}'
require_line "$POLICY_UNIT" "Restart=on-failure"

require_line "$RELAY_UNIT" "WorkingDirectory=$PGFR_USER_HOME/groot_shadow/Isaac-GR00T"
require_line "$RELAY_UNIT" "EnvironmentFile=$PGFR_USER_HOME/.config/pgfr-spine/groot/%i.env"
require_line "$RELAY_UNIT" "Environment=PGFR_RELAY_HOST=127.0.0.1"
require_line "$RELAY_UNIT" "Environment=PGFR_POLICY_HOST=127.0.0.1"
require_text "$RELAY_UNIT" "ExecStart=$PGFR_USER_HOME/groot_shadow/Isaac-GR00T/.venv/bin/python"
require_text "$RELAY_UNIT" '${RELAY_SCRIPT}'
require_line "$RELAY_UNIT" "Restart=on-failure"

"$VERIFY_MODEL" "$MODEL_ROOT"

python3 - "${SHARED_PORTS[@]}" <<'PY'
import socket
import sys

listeners = []
try:
    for raw in sys.argv[1:]:
        port = int(raw)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            listener.bind(("127.0.0.1", port))
        except OSError as exc:
            raise SystemExit(f"shared GR00T port {port} is unavailable: {exc}")
        listeners.append(listener)
finally:
    for listener in listeners:
        listener.close()
PY

for state_name in shared-left.json shared-right.json; do
  if [[ -e $STATE_ROOT/$state_name || -L $STATE_ROOT/$state_name ]]; then
    fail "authoritative shared state already exists: $STATE_ROOT/$state_name"
  fi
done

STAGE=$(mktemp -d)
trap 'rm -rf -- "$STAGE"' EXIT
render() {
  sed -e "s#__PGFR_REPO__#$PGFR_REPO#g" -e "s#__PGFR_HOME__#$PGFR_USER_HOME#g" "$1"
}
render "$TARGET_SOURCE" >"$STAGE/$TARGET_NAME"
render "$LEFT_SOURCE" >"$STAGE/shared-left.env"
render "$RIGHT_SOURCE" >"$STAGE/shared-right.env"

check_destination() {
  local source=$1 destination=$2
  if [[ -L $destination ]]; then
    fail "refusing symlink destination: $destination"
  fi
  if [[ -e $destination ]] && ! cmp -s -- "$source" "$destination"; then
    fail "existing shared-profile file differs: $destination"
  fi
}
check_destination "$STAGE/$TARGET_NAME" "$SYSTEMD_DIR/$TARGET_NAME"
check_destination "$STAGE/shared-left.env" "$GROOT_ENV_DIR/shared-left.env"
check_destination "$STAGE/shared-right.env" "$GROOT_ENV_DIR/shared-right.env"

install_missing() {
  local source=$1 destination=$2 mode=$3 temporary
  if [[ -e $destination ]]; then
    return
  fi
  temporary=$(mktemp "$(dirname "$destination")/.$(basename "$destination").XXXXXX")
  install -m "$mode" "$source" "$temporary"
  mv -T -- "$temporary" "$destination"
}

install -d -m 0755 "$SYSTEMD_DIR" "$GROOT_ENV_DIR" "$STATE_ROOT"
install_missing "$STAGE/$TARGET_NAME" "$SYSTEMD_DIR/$TARGET_NAME" 0644
install_missing "$STAGE/shared-left.env" "$GROOT_ENV_DIR/shared-left.env" 0600
install_missing "$STAGE/shared-right.env" "$GROOT_ENV_DIR/shared-right.env" 0600
systemctl --user daemon-reload

echo "Installed shared GR00T profiles without enabling or starting them."
echo "Installed files: $SYSTEMD_DIR/$TARGET_NAME and $GROOT_ENV_DIR/shared-{left,right}.env"
