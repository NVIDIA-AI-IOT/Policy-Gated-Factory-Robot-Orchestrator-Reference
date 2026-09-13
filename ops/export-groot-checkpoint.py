#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Export a user's trained GR00T checkpoint and record artifact integrity locally."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile

from pgfr_checkpoint import EMBODIMENT_TAG, METADATA_NAME, digest_file, inference_files, verify_checkpoint


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--model-label", required=True)
    parser.add_argument("--dataset-path", required=True, type=Path)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", args.model_label):
            raise ValueError("model-label must contain 1-160 letters, digits, dots, underscores, or hyphens")
        source = args.checkpoint.expanduser().resolve(strict=True)
        dataset = args.dataset_path.expanduser().resolve(strict=True)
        if not source.is_dir() or not dataset.is_dir():
            raise ValueError("checkpoint and dataset-path must be existing directories on the training host")
        output = args.output_dir.expanduser().absolute()
        if output.exists() or output.is_symlink():
            raise ValueError("output directory already exists; choose a fresh checkpoint export")
        if source == output or source in output.parents:
            raise ValueError("output directory must be outside the training checkpoint")
        names = inference_files(source)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".pgfr-checkpoint-", dir=output.parent) as temporary:
            stage = Path(temporary) / "export"
            stage.mkdir()
            for name in names:
                shutil.copyfile(source / name, stage / name)
            metadata = {
                "schema_version": 1,
                "model_label": args.model_label,
                "embodiment_tag": EMBODIMENT_TAG,
                "provenance": {"kind": "user_trained", "checkpoint": str(source), "dataset": str(dataset)},
                "inference_files": names,
            }
            (stage / METADATA_NAME).write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (stage / "SHA256SUMS").write_text(
                "".join(f"{digest_file(stage / name)}  {name}\n" for name in sorted([*names, METADATA_NAME])),
                encoding="ascii",
            )
            identity = verify_checkpoint(stage)
            # Reserve the destination so a concurrent export cannot be replaced.
            output.mkdir()
            try:
                for path in stage.iterdir():
                    path.rename(output / path.name)
            except BaseException:
                shutil.rmtree(output)
                raise
        print(f"PGFR_GROOT_CHECKPOINT_EXPORTED model_root={output} model_label={identity['model_label']} checkpoint_fingerprint={identity['checkpoint_fingerprint']}")
        print("Artifact integrity recorded; task performance requires independent evaluation of this checkpoint.")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"export-groot-checkpoint: ERROR: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
