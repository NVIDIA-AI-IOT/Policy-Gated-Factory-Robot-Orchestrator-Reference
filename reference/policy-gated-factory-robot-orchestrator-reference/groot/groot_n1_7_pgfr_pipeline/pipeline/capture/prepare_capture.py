#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Stage an expert-capture scripts mount; never launch Isaac or alter a live mount."""
import argparse
from pathlib import Path
import shutil


def prepare(destination, reference):
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Choose a new, dedicated capture scripts directory: {destination}")
    deployment = reference / "isaac-cell/deployment"
    runtime = reference / "groot/runtime"
    files = [(path, Path(path.name)) for path in sorted(deployment.iterdir())
             if path.suffix in (".py", ".json", ".usda")]
    files.extend([
        (runtime / "cell/reset_two_arm.py", Path("reset_two_arm.py")),
        (runtime / "native_droid_work/pgfr_sync_capture_cell.py", Path("native_droid_work/pgfr_sync_capture_cell.py")),
    ])
    if not all(source.is_file() for source, _ in files):
        raise FileNotFoundError("Incomplete reference scene checkout")
    destination.mkdir(parents=True)
    for source, relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o644)
    print(f"CAPTURE_MOUNT_STAGED {destination}; no simulator started")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mount", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.mount, Path(__file__).resolve().parents[4])
