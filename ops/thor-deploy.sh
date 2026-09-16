#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Inspect or explicitly operate the canonical Thor user services.
#
# Read-only by default. No PID discovery, kill -9, nohup, or implicit restart.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEAM_URL="${PGFR_FLOOR_SERVICE:-http://127.0.0.1:8766}"
GW_URL="${PGFR_OPENCLAW_URL:-http://127.0.0.1:18790}"
CHAT_URL="${PGFR_CHAT_URL:-http://127.0.0.1:8620}"
WORKFLOWS_URL="${PGFR_WORKFLOWS_URL:-http://127.0.0.1:8610}"
CONSOLE_URL="${PGFR_CONSOLE_URL:-http://127.0.0.1:8600}"
GPU_URL="${PGFR_GPU_URL_THOR:-http://127.0.0.1:8601}"
VLM_URL="${PGFR_VLM_URL:-http://127.0.0.1:8001}"
MODE="${1:---check}"
TARGET="${2:-}"

say() { printf '%s thor-deploy: %s\n' "$(date +%H:%M:%S)" "$*"; }

LEGACY_GUARD="$REPO/ops/pgfr-legacy-guard.sh"
if [ ! -r "$LEGACY_GUARD" ]; then
  say "ERROR: missing migration guard: $LEGACY_GUARD"
  exit 2
fi
# shellcheck disable=SC1090
. "$LEGACY_GUARD"

port_listener_count() {
  ss -H -ltnp "sport = :$1" 2>/dev/null \
    | grep -oE 'pid=[0-9]+' | sort -u | wc -l
}

verify() {
  local rc=0 health code count name url
  if health="$(curl --fail --silent --show-error --max-time 8 "$SEAM_URL/v1/health")"; then
    say "seam reachable — ${health:0:160}"
  else
    say "seam NOT reachable at $SEAM_URL"
    rc=1
  fi

  while IFS='|' read -r name url; do
    if curl --fail --silent --max-time 8 "$url" >/dev/null; then
      say "$name reachable"
    else
      say "$name NOT reachable at $url"
      rc=1
    fi
  done <<EOF
chat|$CHAT_URL/api/ready
workflows|$WORKFLOWS_URL/api/health
console|$CONSOLE_URL/api/health
gpu exporter|$GPU_URL/healthz
perception VLM|$VLM_URL/v1/models
EOF

  code="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 8 "$GW_URL/health" || true)"
  if [[ "$code" =~ ^(200|401|403)$ ]]; then
    say "OpenClaw gateway reachable — HTTP $code"
  else
    say "OpenClaw gateway NOT reachable at $GW_URL — HTTP ${code:-none}"
    rc=1
  fi

  for port in 8766 18790 8620 8610 8600 8601 8001; do
    count="$(port_listener_count "$port")"
    if [ "$count" -gt 1 ]; then
      say "port $port has $count listeners — duplicate ownership"
      rc=1
    fi
  done
  return "$rc"
}

units_for() {
  case "$1" in
    vlm) printf '%s\n' pgfr-perception-vlm.service ;;
    seam) printf '%s\n' pgfr-seam.service ;;
    gateway) printf '%s\n' pgfr-openclaw.service ;;
    chat) printf '%s\n' pgfr-chat.service ;;
    workflows) printf '%s\n' pgfr-workflows.service ;;
    console) printf '%s\n' pgfr-console.service ;;
    gpu) printf '%s\n' pgfr-gpu-exporter.service ;;
    all) printf '%s\n' pgfr-perception-vlm.service pgfr-seam.service pgfr-openclaw.service pgfr-chat.service pgfr-workflows.service pgfr-gpu-exporter.service pgfr-console.service ;;
    *) return 2 ;;
  esac
}

operate() {
  local verb="$1" unit
  if [ -z "$TARGET" ] || ! units_for "$TARGET" >/dev/null; then
    echo "Usage: $0 --$verb {vlm|seam|gateway|chat|workflows|gpu|console|all}" >&2
    exit 2
  fi
  while IFS= read -r unit; do
    say "$verb $unit (explicit target: $TARGET)"
    systemctl --user "$verb" "$unit"
  done < <(units_for "$TARGET")
}

target_is_active() {
  local unit rc=0
  while IFS= read -r unit; do
    systemctl --user is-active "$unit" || rc=1
  done < <(units_for "$TARGET")
  return "$rc"
}

wait_for_stack() {
  local attempt code
  for attempt in $(seq 1 30); do
    code="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 3 "$GW_URL/health" || true)"
    if curl --fail --silent --max-time 3 "$SEAM_URL/v1/health" >/dev/null \
      && [[ "$code" =~ ^(200|401|403)$ ]] \
      && curl --fail --silent --max-time 8 "$CHAT_URL/api/ready" >/dev/null \
      && curl --fail --silent --max-time 3 "$WORKFLOWS_URL/api/health" >/dev/null \
      && curl --fail --silent --max-time 3 "$CONSOLE_URL/api/health" >/dev/null \
      && curl --fail --silent --max-time 3 "$GPU_URL/healthz" >/dev/null \
      && curl --fail --silent --max-time 3 "$VLM_URL/v1/models" >/dev/null; then
      verify
      return
    fi
    sleep 2
  done
  say "stack did not become ready within 60 seconds"
  verify
}

pgfr_refuse_active_legacy_units

case "$MODE" in
  --check) verify ;;
  --status)
    systemctl --user --no-pager status \
      pgfr-perception-vlm.service pgfr-seam.service pgfr-openclaw.service pgfr-chat.service \
      pgfr-workflows.service pgfr-gpu-exporter.service pgfr-console.service || true
    verify
    ;;
  --start)
    operate start
    [ "$TARGET" = "all" ] && wait_for_stack || target_is_active
    ;;
  --restart)
    operate restart
    [ "$TARGET" = "all" ] && wait_for_stack || target_is_active
    ;;
  *)
    echo "Usage: $0 [--check|--status|--start TARGET|--restart TARGET]" >&2
    exit 2
    ;;
esac
