#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Prepare the pinned NVIDIA Isaac-GR00T source and Thor environment.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${PGFR_GROOT_SOURCE_ROOT:-$HOME/groot_shadow/Isaac-GR00T}"
MODE="${1:---source-only}"
UPSTREAM="https://github.com/NVIDIA/Isaac-GR00T"
REVISION="e5749287857afd97b78f1147166137de29746392"
PATCH="$REPO/reference/policy-gated-factory-robot-orchestrator-reference/groot/patches/isaac-groot-e574-policy-gated-factory-robot-orchestrator-reference.patch"
THOR="$REPO/reference/policy-gated-factory-robot-orchestrator-reference/groot/thor"
PATCH_SHA256="51ca0f19912b264a1e5091e94e45ea8bb0d719a0fefacb9fb1e7b44bef1e98f5"
TORCHCODEC_WHEEL_SHA256="1421de7e6248cc33398c16b2d7ba5ada4bf5c2a38af7cc44a003f3b0c36eb314"
TORCHCODEC_WHEEL_RELATIVE="scripts/deployment/thor/wheels/torchcodec-0.10.0a0-cp312-cp312-linux_aarch64.whl"

fail() { printf 'prepare-groot-runtime: ERROR: %s\n' "$*" >&2; exit 2; }
LEGACY_GUARD="$REPO/ops/pgfr-legacy-guard.sh"
[ -r "$LEGACY_GUARD" ] || fail "missing migration guard: $LEGACY_GUARD"
# shellcheck disable=SC1090
. "$LEGACY_GUARD"
case "$MODE" in --source-only|--install) ;; *) fail "usage: $0 [--source-only|--install]" ;; esac
for command in flock git python3 sha256sum; do
  command -v "$command" >/dev/null 2>&1 || fail "missing command: $command"
done
git lfs version >/dev/null 2>&1 \
  || fail "Git LFS is required; run ops/install-brain-host-prereqs.sh first"

pgfr_refuse_active_legacy_units
for profile in shared-left shared-right; do
  for kind in policy relay; do
    if systemctl --user --quiet is-active "pgfr-groot-${kind}@$profile.service" 2>/dev/null; then
      fail "pgfr-groot-${kind}@$profile.service is active; this script never replaces an active runtime"
    fi
  done
done
printf '%s  %s\n' "$PATCH_SHA256" "$PATCH" | sha256sum --check --strict

parent="$(dirname "$DEST")"
mkdir -p "$parent"
lock_file="$parent/.isaac-groot-prepare.lock"
exec 9>"$lock_file"
flock -n 9 \
  || fail "another preparation owns the destination lock: $lock_file"
[ ! -e "$DEST" ] || fail "destination already exists: $DEST"
tmp="$(mktemp -d "$parent/.groot-source.XXXXXX")"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT
GIT_LFS_SKIP_SMUDGE=1 git clone --no-checkout "$UPSTREAM" "$tmp"
GIT_LFS_SKIP_SMUDGE=1 git -C "$tmp" checkout --detach "$REVISION"
git -C "$tmp" lfs install --local
git -C "$tmp" lfs pull --include="$TORCHCODEC_WHEEL_RELATIVE" --exclude=''
torchcodec_wheel="$tmp/$TORCHCODEC_WHEEL_RELATIVE"
[ -f "$torchcodec_wheel" ] \
  || fail "pinned GR00T source is missing its Thor torchcodec wheel"
! grep -Fqx 'version https://git-lfs.github.com/spec/v1' "$torchcodec_wheel" \
  || fail "Thor torchcodec wheel remains a Git LFS pointer after materialization"
python3 -c \
  'import sys, zipfile; raise SystemExit(not zipfile.is_zipfile(sys.argv[1]))' \
  "$torchcodec_wheel" \
  || fail "materialized Thor torchcodec artifact is not a valid wheel archive"
printf '%s  %s\n' "$TORCHCODEC_WHEEL_SHA256" "$torchcodec_wheel" \
  | sha256sum --check --strict \
  || fail "materialized Thor torchcodec wheel differs from the validated artifact"
git -C "$tmp" apply --check "$PATCH"
git -C "$tmp" apply "$PATCH"

mkdir -p "$tmp/scripts/deployment/thor"
# The project supports Thor serving on the host. Remove the upstream container
# recipe from this new staging checkout so it cannot advertise another path.
rm -f -- "$tmp/scripts/deployment/thor/Dockerfile"
for name in install_deps.sh pyproject.toml uv.lock; do
  install -m 0644 "$THOR/$name" "$tmp/scripts/deployment/thor/$name"
done
chmod 0755 "$tmp/scripts/deployment/thor/install_deps.sh"
actual_patch="$(git -C "$tmp" diff --binary "$REVISION" -- gr00t | sha256sum | cut -d' ' -f1)"
[ "$actual_patch" = "$PATCH_SHA256" ] || fail "prepared GR00T source differs from the pinned patch"
mv -T "$tmp" "$DEST"
trap - EXIT

if [ "$MODE" = "--install" ]; then
  UV_BIN="${PGFR_UV_BIN:-$HOME/.local/bin/uv}"
  [ -x "$UV_BIN" ] \
    || fail "pinned uv is missing; run ops/install-brain-host-prereqs.sh first"
  case "$("$UV_BIN" --version)" in
    "uv 0.11.32"*) ;;
    *) fail "uv 0.11.32 is required: $("$UV_BIN" --version)" ;;
  esac
  export PATH="$(dirname "$UV_BIN"):$PATH"
  "$DEST/scripts/deployment/thor/install_deps.sh"
fi
echo "PGFR_GROOT_RUNTIME_PREPARED source=$DEST revision=$REVISION mode=$MODE"
