#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ops/install-groot-two-host-bridge.sh \
    --thor-ssh user@thor-host \
    --remote-checkpoint /absolute/checkpoint/path \
    --remote-state-root /absolute/thor/state/path

Installs, but never enables or starts, the simulation-host GR00T bridge.
Optional port and path flags are documented by --help.
EOF
}

IC_REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
IC_USER_HOME=${HOME:?HOME is required}
UNIT_NAME=ic-groot-two-host-bridge.service
THOR_SSH=
REMOTE_CHECKPOINT=
REMOTE_STATE_ROOT=
LOCAL_STATE_ROOT="$IC_USER_HOME/.local/share/ic-spine/groot/remote-thor-v36"
REMOTE_LEFT_POLICY_PORT=5592
REMOTE_RIGHT_POLICY_PORT=5593
REMOTE_LEFT_RELAY_PORT=5641
REMOTE_RIGHT_RELAY_PORT=5642
LOCAL_LEFT_POLICY_PORT=5792
LOCAL_RIGHT_POLICY_PORT=5793
LOCAL_LEFT_RELAY_PORT=5741
LOCAL_RIGHT_RELAY_PORT=5742
POLL_SECONDS=5

while (($#)); do
  case "$1" in
    --thor-ssh) THOR_SSH=${2:?missing value}; shift 2 ;;
    --remote-checkpoint) REMOTE_CHECKPOINT=${2:?missing value}; shift 2 ;;
    --remote-state-root) REMOTE_STATE_ROOT=${2:?missing value}; shift 2 ;;
    --remote-left-policy-port) REMOTE_LEFT_POLICY_PORT=${2:?missing value}; shift 2 ;;
    --remote-right-policy-port) REMOTE_RIGHT_POLICY_PORT=${2:?missing value}; shift 2 ;;
    --remote-left-relay-port) REMOTE_LEFT_RELAY_PORT=${2:?missing value}; shift 2 ;;
    --remote-right-relay-port) REMOTE_RIGHT_RELAY_PORT=${2:?missing value}; shift 2 ;;
    --local-left-policy-port) LOCAL_LEFT_POLICY_PORT=${2:?missing value}; shift 2 ;;
    --local-right-policy-port) LOCAL_RIGHT_POLICY_PORT=${2:?missing value}; shift 2 ;;
    --local-left-relay-port) LOCAL_LEFT_RELAY_PORT=${2:?missing value}; shift 2 ;;
    --local-right-relay-port) LOCAL_RIGHT_RELAY_PORT=${2:?missing value}; shift 2 ;;
    --poll-seconds) POLL_SECONDS=${2:?missing value}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "install-groot-two-host-bridge: ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z $REMOTE_STATE_ROOT ]]; then
  echo "install-groot-two-host-bridge: ERROR: --remote-state-root is required" >&2
  exit 2
fi

if [[ ! $THOR_SSH =~ ^[A-Za-z_][A-Za-z0-9_.-]*@[A-Za-z0-9_.:-]+$ ]]; then
  echo "install-groot-two-host-bridge: ERROR: --thor-ssh must be user@host" >&2
  exit 2
fi
for named_path in REMOTE_CHECKPOINT REMOTE_STATE_ROOT LOCAL_STATE_ROOT; do
  path_value=${!named_path}
  if [[ ! $path_value =~ ^/[A-Za-z0-9_./-]+$ || $path_value == *"/../"* || $path_value == */.. ]]; then
    echo "install-groot-two-host-bridge: ERROR: $named_path must be a normalized absolute path" >&2
    exit 2
  fi
done

PORT_VALUES=(
  "$REMOTE_LEFT_POLICY_PORT" "$REMOTE_RIGHT_POLICY_PORT"
  "$REMOTE_LEFT_RELAY_PORT" "$REMOTE_RIGHT_RELAY_PORT"
  "$LOCAL_LEFT_POLICY_PORT" "$LOCAL_RIGHT_POLICY_PORT"
  "$LOCAL_LEFT_RELAY_PORT" "$LOCAL_RIGHT_RELAY_PORT"
)
for port in "${PORT_VALUES[@]}"; do
  if [[ ! $port =~ ^[0-9]+$ ]] || ((port < 1 || port > 65535)); then
    echo "install-groot-two-host-bridge: ERROR: invalid TCP port: $port" >&2
    exit 2
  fi
done
if [[ $(printf '%s\n' "${PORT_VALUES[@]:0:4}" | sort -u | wc -l) -ne 4 ]]; then
  echo "install-groot-two-host-bridge: ERROR: remote ports must be distinct" >&2
  exit 2
fi
if [[ $(printf '%s\n' "${PORT_VALUES[@]:4:4}" | sort -u | wc -l) -ne 4 ]]; then
  echo "install-groot-two-host-bridge: ERROR: local ports must be distinct" >&2
  exit 2
fi

if systemctl --user is-active --quiet "$UNIT_NAME"; then
  echo "install-groot-two-host-bridge: ERROR: $UNIT_NAME is active; leave it running or explicitly stop it before installation" >&2
  exit 1
fi

for required in \
  "$IC_REPO/ops/groot-two-host-bridge.py" \
  "$IC_REPO/ops/systemd/simulation-host/$UNIT_NAME"; do
  if [[ ! -f $required || -L $required ]]; then
    echo "install-groot-two-host-bridge: ERROR: missing regular source file: $required" >&2
    exit 1
  fi
done

install -d -m 0755 \
  "$IC_USER_HOME/.config/ic-spine" \
  "$IC_USER_HOME/.config/systemd/user" \
  "$IC_USER_HOME/.local/lib/industrial-claw" \
  "$LOCAL_STATE_ROOT"
if [[ -L $LOCAL_STATE_ROOT || ! -O $LOCAL_STATE_ROOT ]]; then
  echo "install-groot-two-host-bridge: ERROR: local state root must be a user-owned real directory" >&2
  exit 1
fi
for state_name in shared-left.json shared-right.json; do
  if [[ -e $LOCAL_STATE_ROOT/$state_name || -L $LOCAL_STATE_ROOT/$state_name ]]; then
    echo "install-groot-two-host-bridge: ERROR: generated state already exists: $LOCAL_STATE_ROOT/$state_name" >&2
    exit 1
  fi
done

python3 - "${PORT_VALUES[@]:4:4}" <<'PY'
import socket
import sys

sockets = []
try:
    for raw in sys.argv[1:]:
        port = int(raw)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            listener.bind(("127.0.0.1", port))
        except OSError as exc:
            raise SystemExit(f"local bridge port {port} is unavailable: {exc}")
        sockets.append(listener)
finally:
    for listener in sockets:
        listener.close()
PY

CONFIG_PATH="$IC_USER_HOME/.config/ic-spine/groot-two-host-bridge.env"
TEMP_CONFIG=$(mktemp)
trap 'rm -f -- "$TEMP_CONFIG"' EXIT
cat >"$TEMP_CONFIG" <<EOF
IC_GROOT_THOR_SSH=$THOR_SSH
IC_GROOT_REMOTE_CHECKPOINT=$REMOTE_CHECKPOINT
IC_GROOT_REMOTE_STATE_ROOT=$REMOTE_STATE_ROOT
IC_GROOT_LOCAL_STATE_ROOT=$LOCAL_STATE_ROOT
IC_GROOT_REMOTE_LEFT_POLICY_PORT=$REMOTE_LEFT_POLICY_PORT
IC_GROOT_REMOTE_RIGHT_POLICY_PORT=$REMOTE_RIGHT_POLICY_PORT
IC_GROOT_REMOTE_LEFT_RELAY_PORT=$REMOTE_LEFT_RELAY_PORT
IC_GROOT_REMOTE_RIGHT_RELAY_PORT=$REMOTE_RIGHT_RELAY_PORT
IC_GROOT_LOCAL_LEFT_POLICY_PORT=$LOCAL_LEFT_POLICY_PORT
IC_GROOT_LOCAL_RIGHT_POLICY_PORT=$LOCAL_RIGHT_POLICY_PORT
IC_GROOT_LOCAL_LEFT_RELAY_PORT=$LOCAL_LEFT_RELAY_PORT
IC_GROOT_LOCAL_RIGHT_RELAY_PORT=$LOCAL_RIGHT_RELAY_PORT
IC_GROOT_BRIDGE_POLL_SECONDS=$POLL_SECONDS
EOF
if [[ -e $CONFIG_PATH ]] && ! cmp -s -- "$TEMP_CONFIG" "$CONFIG_PATH"; then
  echo "install-groot-two-host-bridge: ERROR: existing bridge config differs: $CONFIG_PATH" >&2
  exit 1
fi

install -m 0755 "$IC_REPO/ops/groot-two-host-bridge.py" \
  "$IC_USER_HOME/.local/lib/industrial-claw/groot-two-host-bridge.py"
install -m 0644 "$IC_REPO/ops/systemd/simulation-host/$UNIT_NAME" \
  "$IC_USER_HOME/.config/systemd/user/$UNIT_NAME"
install -m 0600 "$TEMP_CONFIG" "$CONFIG_PATH"
systemctl --user daemon-reload

echo "Installed $UNIT_NAME without enabling or starting it."
echo "Review $CONFIG_PATH and run the documented config preflight before an explicit start."
