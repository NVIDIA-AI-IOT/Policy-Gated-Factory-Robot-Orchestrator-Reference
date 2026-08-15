#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Reproducible brain/viewer installation for one Linux user.
#
# Default is read-only validation. --install installs frozen dependencies and
# renders user-systemd templates, but deliberately does not start or restart
# any service.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:---check}"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
ENV_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/ic-spine"
UV_BIN="${IC_UV_BIN:-$HOME/.local/bin/uv}"
if [ ! -x "$UV_BIN" ]; then
  UV_BIN="$(command -v uv || true)"
fi

say() { printf 'bootstrap-brain: %s\n' "$*"; }
fail() { printf 'bootstrap-brain: ERROR: %s\n' "$*" >&2; exit 2; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

check_prerequisites() {
  require_command python3.12
  [ -x "$UV_BIN" ] || fail "missing pinned uv; run ops/install-brain-host-prereqs.sh"
  require_command node
  require_command npm
  require_command systemctl
  require_command curl
  require_command docker
  require_command ss

  local uv_version
  [ "$(node --version)" = "v22.22.3" ] \
    || fail "Node v22.22.3 required; found $(node --version)"
  uv_version="$($UV_BIN --version)"
  [[ "$uv_version" = "uv 0.11.32"* ]] \
    || fail "uv 0.11.32 required; found $uv_version"
  python3.12 -c 'import sys; assert sys.version_info[:2] == (3, 12)' \
    || fail "Python 3.12 is required"
  docker info >/dev/null 2>&1 \
    || fail "Docker daemon is unavailable to this user"
  docker info --format '{{json .Runtimes}}' | grep -q '"nvidia"' \
    || fail "NVIDIA Container Runtime is not registered with Docker"

  local lock
  for lock in \
    package-lock.json \
    ic-spine/uv.lock \
    servers/industrial-claw-mcp/uv.lock \
    ic-console/uv.lock \
    servers/ic-chat/uv.lock \
    servers/ic-workflows/uv.lock; do
    [ -f "$REPO/$lock" ] || fail "missing lockfile: $lock"
  done
  bash -n "$REPO/ops/gw.sh" "$REPO/ops/thor-deploy.sh"
  say "prerequisites and frozen dependency manifests: OK"
}

refuse_active_install() {
  local unit
  for unit in ic-seam ic-openclaw ic-chat ic-workflows ic-gpu-exporter ic-console; do
    if systemctl --user --quiet is-active "$unit.service" 2>/dev/null; then
      fail "$unit.service is active; installation will not replace files beneath a running service"
    fi
  done
  for unit in \
    ic-groot-shared-stack.target \
    ic-groot-policy@shared-left.service \
    ic-groot-policy@shared-right.service \
    ic-groot-relay@shared-left.service \
    ic-groot-relay@shared-right.service; do
    if systemctl --user --quiet is-active "$unit" 2>/dev/null; then
      fail "$unit is active; installation will not replace files beneath a running service"
    fi
  done
}

sync_python_project() {
  local project="$1"
  "$UV_BIN" sync --frozen --python python3.12 --project "$REPO/$project"
}

sync_floor_project() {
  local project="$REPO/ic-spine"
  if [ ! -d "$project/.venv" ]; then
    "$UV_BIN" venv --python python3.12 --system-site-packages "$project/.venv"
  elif ! grep -q '^include-system-site-packages = true$' "$project/.venv/pyvenv.cfg"; then
    fail "$project/.venv does not expose system ROS packages; move it aside and rerun --install"
  fi
  VIRTUAL_ENV="$project/.venv" "$UV_BIN" sync --active --frozen --project "$project"
}

render() {
  sed -e "s#__IC_REPO__#$REPO#g" -e "s#__IC_HOME__#$HOME#g" "$1"
}

install_templates() {
  local src name tmp
  mkdir -p "$SYSTEMD_DIR" "$ENV_DIR" "$ENV_DIR/groot" \
    "$HOME/.openclaw" "$HOME/.industrial-claw/openclaw" "$HOME/ic-journal/frames" \
    "$HOME/.local/share/ic-spine/chat-sessions" \
    "$HOME/.local/share/ic-spine/groot" \
    "$HOME/.local/share/ic-spine/gpu" \
    "$HOME/.cache/huggingface"

  for src in "$REPO"/ops/systemd/*.service; do
    name="$(basename "$src")"
    tmp="$(mktemp)"
    render "$src" >"$tmp"
    install -m 0644 "$tmp" "$SYSTEMD_DIR/$name"
    rm -f "$tmp"
  done
  for src in \
    "$REPO"/ops/systemd/groot/*.service \
    "$REPO"/ops/systemd/groot/*.target; do
    name="$(basename "$src")"
    tmp="$(mktemp)"
    render "$src" >"$tmp"
    install -m 0644 "$tmp" "$SYSTEMD_DIR/$name"
    rm -f "$tmp"
  done

  # Environment files are operator configuration: seed once, never overwrite.
  for src in "$REPO"/ops/systemd/*.env; do
    name="$(basename "$src")"
    if [ -e "$ENV_DIR/$name" ]; then
      say "preserved existing $ENV_DIR/$name"
      continue
    fi
    tmp="$(mktemp)"
    render "$src" >"$tmp"
    install -m 0600 "$tmp" "$ENV_DIR/$name"
    rm -f "$tmp"
  done
  for src in "$REPO"/ops/systemd/groot/*.env; do
    name="$(basename "$src")"
    if [ -e "$ENV_DIR/groot/$name" ]; then
      say "preserved existing $ENV_DIR/groot/$name"
      continue
    fi
    tmp="$(mktemp)"
    render "$src" >"$tmp"
    install -m 0600 "$tmp" "$ENV_DIR/groot/$name"
    rm -f "$tmp"
  done

  [ -e "$HOME/.openclaw/secrets.env" ] || install -m 0600 /dev/null "$HOME/.openclaw/secrets.env"
  systemctl --user daemon-reload
}

case "$MODE" in
  --check)
    check_prerequisites
    "$REPO/ops/thor-deploy.sh" --check || true
    ;;
  --install)
    check_prerequisites
    refuse_active_install
    (cd "$REPO" && npm ci)
    sync_floor_project
    sync_python_project servers/industrial-claw-mcp
    sync_python_project ic-console
    sync_python_project servers/ic-chat
    sync_python_project servers/ic-workflows
    install_templates
    say "installation complete; no service was started"
    say "review $ENV_DIR/*.env, then run: $REPO/ops/thor-deploy.sh --start all"
    ;;
  *)
    echo "Usage: $0 [--check|--install]" >&2
    exit 2
    ;;
esac
