#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Prepare and sync the pinned x86 GR00T training dependencies."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile

from build_security_wheels import (
    BuildError,
    apply_exact_patch,
    materialize,
    read_asset,
    sha256,
)


def project_files(checkout: Path, root: Path, descriptor: dict) -> dict[str, bytes]:
    """Accept only the exact original or exact prepared pair of project files."""
    patch = read_asset(root, descriptor)
    files = {}
    states = set()
    if set(descriptor["files"]) != {"pyproject.toml", "uv.lock"}:
        raise BuildError("Training patch must target pyproject.toml and uv.lock only")
    for name, hashes in descriptor["files"].items():
        path = checkout / name
        if path.is_symlink() or not path.is_file():
            raise BuildError(f"Expected a regular training project file: {path}")
        files[name] = path.read_bytes()
        digest = sha256(files[name])
        if digest == hashes["before"]:
            states.add("original")
        elif digest == hashes["after"]:
            states.add("prepared")
        else:
            raise BuildError(f"Unexpected training configuration: {path}")
    if len(states) != 1:
        raise BuildError("Training project has mixed original/prepared files; restore the pair before retrying")
    if states == {"original"}:
        apply_exact_patch(files, patch, descriptor["files"])
    return files


def write_project(checkout: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        target = checkout / name
        if target.read_bytes() == data:
            continue
        descriptor, temporary = tempfile.mkstemp(prefix=f".{name}-", dir=checkout)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
            os.chmod(temporary, target.stat().st_mode & 0o777)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def prepare(checkout: Path, root: Path, manifest: dict, upstream_dir: Path | None, offline: bool) -> None:
    environment = checkout / ".venv"
    if environment.is_symlink() or not environment.resolve().is_relative_to(checkout.resolve()):
        raise BuildError("Training .venv must remain inside the checkout and cannot be a symlink")
    files = project_files(checkout, root, manifest["training_project"]["patch"])
    output = checkout / ".pgfr-security" / "wheels"
    if not output.resolve().is_relative_to(checkout.resolve()):
        raise BuildError("Training security wheel directory must remain inside the checkout")
    for entry in manifest["packages"]:
        # Existing verified wheels make subsequent preparation fully offline.
        # With --offline, absent wheels require explicitly supplied originals.
        materialize(entry, root, output, upstream_dir, check=offline and upstream_dir is None)
    write_project(checkout, files)


def verify_installed(checkout: Path, manifest: dict) -> None:
    """Check installed versions and patched Python bytes without importing Torch."""
    script = r'''
import hashlib, importlib.metadata, json, pathlib, sys
manifest = json.loads(sys.stdin.read())
for name, version in manifest["training_project"]["installed_versions"].items():
    actual = importlib.metadata.version(name)
    if actual != version:
        raise SystemExit(f"Unexpected installed {name}: {actual}, expected {version}")
for name in manifest["training_project"].get("absent_packages", []):
    try:
        importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        continue
    raise SystemExit(f"Removed dependency remains installed: {name}")
for entry in manifest["packages"]:
    dist = importlib.metadata.distribution(entry["name"])
    for name, hashes in entry["patch"]["files"].items():
        source = pathlib.Path(dist.locate_file(name))
        if hashlib.sha256(source.read_bytes()).hexdigest() != hashes["after"]:
            raise SystemExit(f"Installed security source differs: {name}")
print("Verified training dependency versions and security patches")
'''
    subprocess.run(
        [str(checkout / ".venv" / "bin" / "python"), "-I", "-c", script],
        input=json.dumps(manifest), text=True, check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groot-root", type=Path, required=True, help="Pinned Isaac-GR00T training checkout")
    parser.add_argument("--prepare-only", action="store_true", help="Build security wheels and prepare configuration without installing dependencies")
    parser.add_argument("--offline", action="store_true", help="Use existing wheels or --upstream-dir; disable uv network access")
    parser.add_argument("--upstream-dir", type=Path, help="Directory containing the two original hash-pinned PyPI wheels")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    checkout = args.groot_root.resolve()
    try:
        manifest = json.loads((root / "manifest-training.json").read_text())
        if manifest["schema_version"] != 1:
            raise BuildError("Unsupported training security manifest version")
        revision = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        if revision != manifest["training_project"]["revision"]:
            raise BuildError("Training checkout does not match the pinned Isaac-GR00T revision")
        if not args.prepare_only and (platform.system() != "Linux" or platform.machine() != "x86_64"):
            raise BuildError("This training installation supports Linux x86_64 only")
        uv = os.environ.get("PGFR_UV_BIN", "uv")
        if not args.prepare_only:
            version = subprocess.check_output([uv, "--version"], text=True).strip()
            if version.split()[:2] != ["uv", "0.11.32"]:
                raise BuildError("Training preparation requires uv 0.11.32")
        prepare(checkout, root, manifest, args.upstream_dir, args.offline)
        if not args.prepare_only:
            command = [uv, "sync", "--frozen", "--python", "3.10", "--project", str(checkout)]
            if args.offline:
                command.append("--offline")
            environment = dict(os.environ, UV_PROJECT_ENVIRONMENT=str(checkout / ".venv"))
            subprocess.run(command, env=environment, cwd=checkout, check=True)
            verify_installed(checkout, manifest)
        print(f"Prepared training security dependencies: {checkout}")
    except (BuildError, OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"groot-training: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
