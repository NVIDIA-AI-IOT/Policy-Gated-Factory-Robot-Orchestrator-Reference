#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Migration protection for the IC-to-PGFR cutover.
#
# This is the only deployment source that intentionally retains the legacy
# project prefix. Installers and launchers source it before mutating files or
# starting a replacement runtime, preventing old and new owners from sharing
# the same ports, mounts, or device resources.

readonly PGFR_LEGACY_UNIT_PATTERNS=(
  'ic-*.service'
  'ic-*.target'
)
readonly PGFR_LEGACY_CONTAINER_PATTERNS=(
  'ic-*'
)
readonly PGFR_LEGACY_PLAYBOOK_MARKER='IC-PLAYBOOK'

pgfr_legacy_guard_error() {
  printf 'pgfr-legacy-guard: ERROR: %s\n' "$*" >&2
}

pgfr_matches_legacy_pattern() {
  local candidate=$1 pattern
  shift
  for pattern in "$@"; do
    case "$candidate" in
      $pattern) return 0 ;;
    esac
  done
  return 1
}

pgfr_refuse_active_legacy_units() {
  local active_state load_state output rest sub_state unit
  command -v systemctl >/dev/null 2>&1 || {
    pgfr_legacy_guard_error "systemctl is unavailable; cannot verify legacy user units are stopped"
    return 2
  }
  output="$(
    systemctl --user list-units --all --type=service,target \
      --no-legend --plain --no-pager
  )" || {
    pgfr_legacy_guard_error "cannot inspect user units; refusing a mixed-name deployment"
    return 2
  }

  while read -r unit load_state active_state sub_state rest; do
    [ -n "$unit" ] || continue
    case "$active_state" in
      active|activating|reloading|deactivating)
        if pgfr_matches_legacy_pattern \
          "$unit" "${PGFR_LEGACY_UNIT_PATTERNS[@]}"; then
          pgfr_legacy_guard_error \
            "legacy unit $unit is $active_state; stop and disable it before installing or starting PGFR"
          return 2
        fi
        ;;
    esac
  done <<<"$output"
}

pgfr_refuse_active_legacy_containers() {
  local container output
  # Some source-only operations are valid before Docker is installed. If the
  # CLI exists, however, an uncertain inspection result must block work.
  command -v docker >/dev/null 2>&1 || return 0
  output="$(docker ps --format '{{.Names}}')" || {
    pgfr_legacy_guard_error \
      "cannot inspect running Docker containers; refusing a mixed-name deployment"
    return 2
  }

  while IFS= read -r container; do
    [ -n "$container" ] || continue
    if pgfr_matches_legacy_pattern \
      "$container" "${PGFR_LEGACY_CONTAINER_PATTERNS[@]}"; then
      pgfr_legacy_guard_error \
        "legacy container $container is active; stop it before installing or starting PGFR"
      return 2
    fi
  done <<<"$output"
}
