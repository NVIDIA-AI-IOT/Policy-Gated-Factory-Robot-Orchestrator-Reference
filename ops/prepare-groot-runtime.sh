#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Prepare the pinned NVIDIA Isaac-GR00T source and Thor environment.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${IC_GROOT_SOURCE_ROOT:-$HOME/groot_shadow/Isaac-GR00T}"
MODE="${1:---source-only}"
UPSTREAM="https://github.com/NVIDIA/Isaac-GR00T"
REVISION="e5749287857afd97b78f1147166137de29746392"
PATCH="$REPO/reference/industrial-claw/groot/patches/isaac-groot-e574-industrial-claw.patch"
THOR="$REPO/reference/industrial-claw/groot/thor"
PATCH_SHA256="51ca0f19912b264a1e5091e94e45ea8bb0d719a0fefacb9fb1e7b44bef1e98f5"

fail() { printf 'prepare-groot-runtime: ERROR: %s\n' "$*" >&2; exit 2; }
case "$MODE" in --source-only|--install) ;; *) fail "usage: $0 [--source-only|--install]" ;; esac
for command in git sha256sum; do
  command -v "$command" >/dev/null 2>&1 || fail "missing command: $command"
done

for profile in shared-left shared-right; do
  for kind in policy relay; do
    if systemctl --user --quiet is-active "ic-groot-${kind}@$profile.service" 2>/dev/null; then
      fail "ic-groot-${kind}@$profile.service is active; this script never replaces an active runtime"
    fi
  done
done
[ ! -e "$DEST" ] || fail "destination already exists: $DEST"
printf '%s  %s\n' "$PATCH_SHA256" "$PATCH" | sha256sum --check --strict

parent="$(dirname "$DEST")"
mkdir -p "$parent"
tmp="$(mktemp -d "$parent/.groot-source.XXXXXX")"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT
GIT_LFS_SKIP_SMUDGE=1 git clone --no-checkout "$UPSTREAM" "$tmp"
GIT_LFS_SKIP_SMUDGE=1 git -C "$tmp" checkout --detach "$REVISION"
git -C "$tmp" apply --check "$PATCH"
git -C "$tmp" apply "$PATCH"

mkdir -p "$tmp/scripts/deployment/thor"
for name in Dockerfile install_deps.sh pyproject.toml uv.lock; do
  install -m 0644 "$THOR/$name" "$tmp/scripts/deployment/thor/$name"
done
chmod 0755 "$tmp/scripts/deployment/thor/install_deps.sh"
actual_patch="$(git -C "$tmp" diff --binary "$REVISION" -- gr00t | sha256sum | cut -d' ' -f1)"
[ "$actual_patch" = "$PATCH_SHA256" ] || fail "prepared GR00T source differs from the pinned patch"
mv "$tmp" "$DEST"
trap - EXIT

if [ "$MODE" = "--install" ]; then
  UV_BIN="${IC_UV_BIN:-$HOME/.local/bin/uv}"
  [ -x "$UV_BIN" ] \
    || fail "pinned uv is missing; run ops/install-brain-host-prereqs.sh first"
  case "$("$UV_BIN" --version)" in
    "uv 0.11.32"*) ;;
    *) fail "uv 0.11.32 is required: $("$UV_BIN" --version)" ;;
  esac
  export PATH="$(dirname "$UV_BIN"):$PATH"
  "$DEST/scripts/deployment/thor/install_deps.sh"
fi
echo "IC_GROOT_RUNTIME_PREPARED source=$DEST revision=$REVISION mode=$MODE"
