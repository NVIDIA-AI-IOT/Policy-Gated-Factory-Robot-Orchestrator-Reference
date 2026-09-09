#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# install_deps.sh — One-time install of GR00T deps on Jetson AGX Thor (aarch64, Python 3.12)
# Used by both bare metal and scripts/deployment/thor/Dockerfile.
# After install, use `source scripts/activate_thor.sh` in each new shell.
set -euo pipefail

# Clean verified-installer scratch space even when `set -e` aborts.
TMP_DIRS=()
trap 'for _d in "${TMP_DIRS[@]:-}"; do rm -rf "$_d"; done' EXIT

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
UV_VERSION="0.11.32"
UV_INSTALLER_SHA256="43aff33a967fe40e8c17949d8c85c65bc43f3b5c94742393c957f56ab5ba80f4"
TORCHCODEC_WHEEL_SHA256="1421de7e6248cc33398c16b2d7ba5ada4bf5c2a38af7cc44a003f3b0c36eb314"
TORCHCODEC_WHEEL_NAME="torchcodec-0.10.0a0-cp312-cp312-linux_aarch64.whl"

# Use sudo only when not already root
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
fi

# Validate platform
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ]; then
    echo "ERROR: This script is intended for aarch64 (Jetson Thor). Detected: $ARCH"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$PYTHON_VERSION" != "3.12" ]; then
    echo "ERROR: Python 3.12 is required for the validated Thor cp312 artifacts; detected Python $PYTHON_VERSION" >&2
    exit 1
fi

# Fail before changing host packages or creating a venv unless the exact
# TorchCodec artifact qualified on Thor is materialized and verifiable.
mapfile -t TORCHCODEC_WHEELS < <(
    find "$SCRIPT_DIR/wheels" -maxdepth 1 -type f -name 'torchcodec-*.whl' -print 2>/dev/null \
        | LC_ALL=C sort
)
[[ "${#TORCHCODEC_WHEELS[@]}" -eq 1 \
  && "${TORCHCODEC_WHEELS[0]##*/}" == "$TORCHCODEC_WHEEL_NAME" ]] \
    || { echo "ERROR: exactly one validated Thor torchcodec wheel is required: $TORCHCODEC_WHEEL_NAME" >&2; exit 1; }
TORCHCODEC_WHL="${TORCHCODEC_WHEELS[0]}"
if grep -Fqx 'version https://git-lfs.github.com/spec/v1' "$TORCHCODEC_WHL"; then
    echo "ERROR: torchcodec wheel is still a Git LFS pointer: $TORCHCODEC_WHL" >&2
    echo "Run ops/prepare-groot-runtime.sh so the wheel is materialized before Docker build." >&2
    exit 1
fi
if ! python3 -c 'import sys, zipfile; raise SystemExit(not zipfile.is_zipfile(sys.argv[1]))' "$TORCHCODEC_WHL"; then
    echo "ERROR: torchcodec wheel is present but is not a valid wheel archive: $TORCHCODEC_WHL" >&2
    exit 1
fi
printf '%s  %s\n' "$TORCHCODEC_WHEEL_SHA256" "$TORCHCODEC_WHL" \
    | sha256sum --check --strict \
    || { echo "ERROR: torchcodec wheel checksum does not match the validated Thor artifact" >&2; exit 1; }

# The Thor-specific pyproject.toml and uv.lock are consumed in place from
# $SCRIPT_DIR via `uv sync --project` below — we no longer copy them over
# the repo root, which used to leave the working tree dirty after install.

# ──────────────────────────────────────────────────────────────────────────────
# NVPL LAPACK/BLAS — required by the jetson torch wheel
# ──────────────────────────────────────────────────────────────────────────────
if ! ldconfig -p | grep -q libnvpl_lapack_lp64_gomp; then
    echo "Installing NVPL libs (required by torch on aarch64)..."
    # Add NVIDIA CUDA apt repo if not already configured
    if ! apt-cache show libnvpl-lapack0 &>/dev/null; then
        echo "Adding NVIDIA CUDA apt repository..."
        curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/sbsa/cuda-keyring_1.1-1_all.deb \
            -o /tmp/cuda-keyring.deb
        $SUDO dpkg -i /tmp/cuda-keyring.deb
        rm /tmp/cuda-keyring.deb
        $SUDO apt-get update
    fi
    $SUDO apt-get install -y --no-remove libnvpl-lapack0 libnvpl-blas0
else
    echo "NVPL libs already installed."
fi

# ──────────────────────────────────────────────────────────────────────────────
# CUDA dev packages — Thor BSP only ships runtime libs; GR00T's native CUDA
# dependencies need the compiler and headers.
# ──────────────────────────────────────────────────────────────────────────────
if ! dpkg -s cuda-nvcc-13-0 &>/dev/null; then
    echo "Installing CUDA dev packages (nvcc, cudart-dev, nvrtc-dev)..."
    $SUDO apt-get install -y --no-remove --no-install-recommends \
        cuda-nvcc-13-0 cuda-cudart-dev-13-0 cuda-nvrtc-dev-13-0
else
    echo "CUDA dev packages already installed."
fi

# The Jetson PyTorch wheel links against cuFile at import time.  CUDA runtime
# and nvcc packages do not pull this library in on a minimal Thor install.
if ! dpkg -s libcufile-13-0 &>/dev/null; then
    echo "Installing cuFile runtime (required by torch on a fresh Thor)..."
    $SUDO apt-get install -y --no-remove --no-install-recommends libcufile-13-0
else
    echo "cuFile runtime already installed."
fi

# PyTorch also links CUPTI at import time on the pinned CUDA 13 stack.
if ! dpkg -s cuda-cupti-13-0 &>/dev/null; then
    echo "Installing CUPTI runtime (required by torch on a fresh Thor)..."
    $SUDO apt-get install -y --no-remove --no-install-recommends cuda-cupti-13-0
else
    echo "CUPTI runtime already installed."
fi

# Minimal CUDA math/runtime set measured on the validated bare-metal Thor.
CUDA_MATH_RUNTIME=(
    libcufft-13-0
    libcurand-13-0
    libcusparse-13-0
    libnvjitlink-13-0
)
MISSING_CUDA_MATH=()
for package in "${CUDA_MATH_RUNTIME[@]}"; do
    dpkg -s "$package" &>/dev/null || MISSING_CUDA_MATH+=("$package")
done
if [ "${#MISSING_CUDA_MATH[@]}" -gt 0 ]; then
    echo "Installing CUDA math runtimes required by torch..."
    $SUDO apt-get install -y --no-remove --no-install-recommends "${MISSING_CUDA_MATH[@]}"
else
    echo "CUDA math runtimes already installed."
fi

# ──────────────────────────────────────────────────────────────────────────────
# Python environment
# ──────────────────────────────────────────────────────────────────────────────

# Install the deployment-manifest uv release if it is absent.  Pinning the URL
# alone is insufficient: verify the installer bytes before executing them and
# reject any different uv already selected by PATH.
if ! command -v uv &> /dev/null; then
    echo "Installing uv $UV_VERSION..."
    UV_INSTALL_DIR="$(mktemp -d /tmp/uv-install.XXXXXX)"
    TMP_DIRS+=("$UV_INSTALL_DIR")
    curl -fsSL "https://astral.sh/uv/$UV_VERSION/install.sh" \
        -o "$UV_INSTALL_DIR/install.sh"
    printf '%s  %s\n' "$UV_INSTALLER_SHA256" "$UV_INSTALL_DIR/install.sh" \
        | sha256sum --check --strict
    UV_UNMANAGED_INSTALL="$HOME/.local/bin" sh "$UV_INSTALL_DIR/install.sh"
    export PATH="$HOME/.local/bin:$PATH"
fi
case "$(uv --version)" in
    "uv $UV_VERSION"*) ;;
    *) echo "ERROR: uv $UV_VERSION is required; found $(uv --version)" >&2; exit 1 ;;
esac

# Install platform-specific deps from the Thor pyproject without mutating
# the repo-root pyproject.toml / uv.lock. See the Orin installer for
# details on UV_PROJECT_ENVIRONMENT + --no-install-project.
# Respect a pre-set UV_PROJECT_ENVIRONMENT from the Dockerfile
# (/opt/gr00t-venv, matched by the VIRTUAL_ENV + PATH ENV lines there);
# fall back to $REPO_ROOT/.venv on bare metal.
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$REPO_ROOT/.venv}"
echo "Running uv sync with the Thor pyproject at $SCRIPT_DIR (venv: $UV_PROJECT_ENVIRONMENT)..."
uv sync --project "$SCRIPT_DIR" --no-install-project --extra dev --frozen

VENV_DIR="$UV_PROJECT_ENVIRONMENT"
VENV_PYTHON="$VENV_DIR/bin/python"
SITE_PKGS="$VENV_DIR/lib/python${PYTHON_VERSION}/site-packages"

echo "Installing gr00t in editable mode from the repo root (--no-deps)..."
uv pip install --python "$VENV_PYTHON" --no-deps -e "$REPO_ROOT"

# ──────────────────────────────────────────────────────────────────────────────
# torchcodec — checksum-verified prebuilt wheel only
# Thor and Spark both use cp312 aarch64 wheels, but keep separate wheel
# directories because the built bytes can differ across device stacks.
# ──────────────────────────────────────────────────────────────────────────────
# The pinned Thor wheel contains FFmpeg 6 extensions. JetPack 7.2 can select
# NVIDIA's FFmpeg 8 binary, so install the versioned Ubuntu 24.04 compatibility
# libraries alongside it rather than relying on the unversioned package alone.
TORCHCODEC_FFMPEG6_RUNTIME=(
    libavfilter9
    libavformat60
    libavcodec60
    libavutil58
    libswresample4
    libswscale7
)
echo "Installing FFmpeg runtime..."
$SUDO apt-get update -qq
$SUDO apt-get install -y --no-remove --no-install-recommends \
    ffmpeg "${TORCHCODEC_FFMPEG6_RUNTIME[@]}"

echo "Installing torchcodec from validated wheel: $TORCHCODEC_WHL"
uv pip install --python "$VENV_PYTHON" --force-reinstall --no-deps "$TORCHCODEC_WHL"

echo ""
echo "Install complete! In each new shell, activate with:"
echo "  source .venv/bin/activate"
echo "  source scripts/activate_thor.sh"
