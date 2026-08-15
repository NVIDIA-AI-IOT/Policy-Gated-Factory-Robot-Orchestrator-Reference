#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Install the pinned host prerequisites used by the validated aarch64 Thor brain.
# This script never starts, stops, or restarts an Industrial Claw service.
set -euo pipefail

NODE_VERSION="22.22.3-1nodesource1"
NODESOURCE_KEY_SHA256="7a96b125f721c99e07d3f45b279adbd6884ec4f3f06750f6b54df40cfae36836"
ROS_KEY_SHA256="4a91c49af0d6f0016108b93698782b596c27ccd836937e18e0e36c3347dc602f"
UV_VERSION="0.11.32"
UV_INSTALLER_SHA256="43aff33a967fe40e8c17949d8c85c65bc43f3b5c94742393c957f56ab5ba80f4"

fail() { printf 'install-brain-host-prereqs: ERROR: %s\n' "$*" >&2; exit 2; }

[ "$(uname -m)" = "aarch64" ] || fail "this installer targets the validated aarch64 Thor setup"
[ "$(. /etc/os-release && printf '%s' "$VERSION_ID")" = "24.04" ] \
  || fail "this installer targets Ubuntu 24.04"

for unit in ic-seam ic-openclaw ic-chat ic-workflows ic-gpu-exporter ic-console; do
  if systemctl --user --quiet is-active "$unit.service" 2>/dev/null; then
    fail "$unit.service is active; host packages are never replaced beneath a running IC service"
  fi
done
if pgrep -x apt-get >/dev/null || pgrep -x dpkg >/dev/null; then
  fail "another package-manager job is active"
fi

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
  $SUDO -v
fi

$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends ca-certificates curl gnupg

tmp_dir="$(mktemp -d /tmp/ic-host-prereqs.XXXXXX)"
cleanup() { rm -rf "$tmp_dir"; }
trap cleanup EXIT

curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
  -o "$tmp_dir/nodesource.asc"
gpg --batch --yes --dearmor -o "$tmp_dir/nodesource.gpg" "$tmp_dir/nodesource.asc"
printf '%s  %s\n' "$NODESOURCE_KEY_SHA256" "$tmp_dir/nodesource.gpg" \
  | sha256sum --check --strict

curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o "$tmp_dir/ros.asc"
gpg --batch --yes --dearmor -o "$tmp_dir/ros.gpg" "$tmp_dir/ros.asc"
printf '%s  %s\n' "$ROS_KEY_SHA256" "$tmp_dir/ros.gpg" \
  | sha256sum --check --strict

# Keep uv outside the system Python and pin the exact installer bytes. The
# unmanaged install never edits shell profiles or replaces a distro package.
curl -fsSL "https://astral.sh/uv/$UV_VERSION/install.sh" \
  -o "$tmp_dir/uv-install.sh"
printf '%s  %s\n' "$UV_INSTALLER_SHA256" "$tmp_dir/uv-install.sh" \
  | sha256sum --check --strict
UV_UNMANAGED_INSTALL="$HOME/.local/bin" sh "$tmp_dir/uv-install.sh"

cat >"$tmp_dir/nodesource.sources" <<'EOF'
Types: deb
URIs: https://deb.nodesource.com/node_22.x
Suites: nodistro
Components: main
Architectures: arm64
Signed-By: /usr/share/keyrings/nodesource.gpg
EOF
cat >"$tmp_dir/ros2.list" <<'EOF'
deb [arch=arm64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu noble main
EOF

$SUDO install -m 0644 "$tmp_dir/nodesource.gpg" /usr/share/keyrings/nodesource.gpg
$SUDO install -m 0644 "$tmp_dir/ros.gpg" /usr/share/keyrings/ros-archive-keyring.gpg
$SUDO install -m 0644 "$tmp_dir/nodesource.sources" /etc/apt/sources.list.d/nodesource.sources
$SUDO install -m 0644 "$tmp_dir/ros2.list" /etc/apt/sources.list.d/ros2.list

# A stock Thor image may expose only the Jetson runtime repository. Add the
# versioned NVIDIA CUDA keyring when the CUDA 13 CUPTI package is not visible.
if ! apt-cache show cuda-cupti-13-0 >/dev/null 2>&1; then
  curl -fsSL \
    https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/sbsa/cuda-keyring_1.1-1_all.deb \
    -o "$tmp_dir/cuda-keyring.deb"
  $SUDO dpkg -i "$tmp_dir/cuda-keyring.deb"
fi

$SUDO apt-get update
apt-cache madison nodejs | awk '{print $3}' | grep -Fx "$NODE_VERSION" >/dev/null \
  || fail "pinned Node package is unavailable: $NODE_VERSION"
$SUDO apt-get install -y --no-install-recommends \
  "nodejs=$NODE_VERSION" \
  ros-jazzy-ros-base \
  ros-jazzy-rmw-fastrtps-cpp \
  cuda-cupti-13-0 \
  libcufft-13-0 \
  libcurand-13-0 \
  libcusparse-13-0 \
  libnvjitlink-13-0

[ "$(node --version)" = "v22.22.3" ] || fail "unexpected Node version: $(node --version)"
[ -x "$HOME/.local/bin/uv" ] || fail "pinned uv executable is missing"
case "$("$HOME/.local/bin/uv" --version)" in
  "uv $UV_VERSION"*) ;;
  *) fail "unexpected uv version: $("$HOME/.local/bin/uv" --version)" ;;
esac
[ -f /opt/ros/jazzy/setup.bash ] || fail "ROS Jazzy setup file is missing"
CUDA_RUNTIME_DIR=/usr/local/cuda-13.0/targets/sbsa-linux/lib
for library in \
  libcupti.so.13 \
  libcufft.so.12 \
  libcurand.so.10 \
  libcusparse.so.12 \
  libnvJitLink.so.13; do
  [ -e "$CUDA_RUNTIME_DIR/$library" ] \
    || fail "$library is missing from the packaged service runtime path"
done

echo "IC_BRAIN_HOST_PREREQS_INSTALLED node=$(node --version) uv=$UV_VERSION ros=jazzy cuda_runtime=13.0"
