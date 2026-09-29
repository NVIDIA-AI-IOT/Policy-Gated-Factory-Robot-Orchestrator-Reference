#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate user-created native DROID inputs and launch pinned GR00T directly.

Use the Python interpreter of the prepared Isaac-GR00T environment. This wrapper
never downloads data/models and never uses examples/finetune.sh env overrides.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys

UPSTREAM_REVISION = "e5749287857afd97b78f1147166137de29746392"
EMBODIMENT = "OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT"
MODALITY = Path(__file__).with_name("droid_checkpoint_single_frame_config.py")


def _read(path):
    return json.loads(path.read_text())


def _finite_shape(value, shape):
    if not shape:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    return (isinstance(value, list) and len(value) == shape[0]
            and all(_finite_shape(item, shape[1:]) for item in value))


def validate_dataset(root: Path):
    """Reject missing/placeholder statistics, incomplete episodes, and wrong contracts.

    This metadata check complements converter numeric checks. It does not certify
    video content, physical success, split independence, or checkpoint behavior.
    """
    info = _read(root / "meta/info.json")
    if info.get("robot_type") != "droid" or info.get("fps") != 15:
        raise ValueError(f"Expected native DROID at 15 fps: {root}")
    for key in ("observation.state", "action"):
        if info.get("features", {}).get(key, {}).get("shape") != [17]:
            raise ValueError(f"Expected 17D {key}: {root}")
    count = info.get("total_episodes", 0)
    if not isinstance(count, int) or count <= 0:
        raise ValueError(f"Dataset must contain episodes: {root}")
    episodes = [json.loads(line) for line in (root / "meta/episodes.jsonl").read_text().splitlines() if line.strip()]
    if len(episodes) != count or sum(ep["length"] for ep in episodes) != info.get("total_frames"):
        raise ValueError(f"Episode/frame totals disagree: {root}")
    if [ep["episode_index"] for ep in episodes] != list(range(count)) or any(ep["length"] < 40 for ep in episodes):
        raise ValueError(f"Episodes must be contiguous and cover the 40-step action horizon: {root}")
    if not (root / "meta/tasks.jsonl").read_text().strip():
        raise ValueError(f"Task descriptions are missing: {root}")
    modality = _read(root / "meta/modality.json")
    expected_slices = {"eef_9d": (0, 9), "gripper_position": (9, 10), "joint_position": (10, 17)}
    for group in ("state", "action"):
        for name, (start, end) in expected_slices.items():
            actual = modality.get(group, {}).get(name, {})
            if (actual.get("start"), actual.get("end")) != (start, end):
                raise ValueError(f"Wrong {group}.{name} layout: {root}")
    expected_videos = ["observation.images.exterior_1_left", "observation.images.wrist_left"]
    if [item.get("original_key") for item in modality.get("video", {}).values()] != expected_videos:
        raise ValueError(f"Expected exterior then wrist video ordering: {root}")
    data_files = sorted(root.glob("data/*/episode_*.parquet"))
    if len(data_files) != count:
        raise ValueError(f"Parquet count differs from metadata: {root}")
    for index in range(count):
        expected = root / info["data_path"].format(episode_chunk=index // info["chunks_size"], episode_index=index)
        if not expected.is_file() or expected.stat().st_size == 0:
            raise ValueError(f"Episode file missing or empty: {expected}")
        for key in expected_videos:
            video = root / info["video_path"].format(episode_chunk=index // info["chunks_size"], episode_index=index, video_key=key)
            if not video.is_file() or video.stat().st_size == 0:
                raise ValueError(f"Camera video missing or empty: {video}")
    for filename, shapes in (
        ("stats.json", {"observation.state": (17,), "action": (17,)}),
        ("relative_stats.json", {"eef_9d": (40, 9), "joint_position": (40, 7)}),
    ):
        stats = _read(root / "meta" / filename)
        for key, shape in shapes.items():
            for statistic in ("mean", "std", "min", "max", "q01", "q99"):
                if not _finite_shape(stats.get(key, {}).get(statistic), shape):
                    raise ValueError(f"Missing/non-finite {filename}:{key}.{statistic}; run gr00t/data/stats.py: {root}")
    return {"path": str(root), "episodes": count, "frames": info["total_frames"]}


def build_command(args, python=None):
    if not math.isfinite(args.learning_rate) or args.learning_rate <= 0:
        raise ValueError("--learning-rate must be finite and positive")
    if args.max_steps <= 0 or args.batch_size <= 0 or args.workers < 0:
        raise ValueError("steps/batch must be positive and workers non-negative")
    datasets = [Path(path).expanduser().resolve() for path in args.dataset]
    if any(os.pathsep in str(path) for path in datasets):
        raise ValueError("Dataset paths cannot contain the platform path separator")
    command = [python or sys.executable, "gr00t/experiment/launch_finetune.py",
               "--base-model-path", str(args.base_model.expanduser().resolve()),
               "--dataset-path", os.pathsep.join(map(str, datasets)),
               "--embodiment-tag", EMBODIMENT,
               "--modality-config-path", str(MODALITY.resolve()),
               "--output-dir", str(args.output_dir.expanduser().resolve()),
               "--num-gpus", "1", "--global-batch-size", str(args.batch_size),
               "--dataloader-num-workers", str(args.workers),
               "--max-steps", str(args.max_steps),
               "--learning-rate", str(args.learning_rate),
               "--save-steps", str(args.max_steps), "--save-total-limit", "1",
               "--save-only-model", "--no-use-wandb",
               "--no-tune-llm", "--no-tune-visual",
               "--tune-projector", "--tune-diffusion-model",
               "--color-jitter-params", "brightness", "0.3", "contrast", "0.4", "saturation", "0.5", "hue", "0.08"]
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groot-root", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--learning-rate", type=float, required=True)
    parser.add_argument("--max-steps", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    groot_root = args.groot_root.expanduser().resolve()
    revision = subprocess.check_output(["git", "-C", str(groot_root), "rev-parse", "HEAD"], text=True).strip()
    if revision != UPSTREAM_REVISION:
        parser.error(f"Expected Isaac-GR00T revision {UPSTREAM_REVISION}, got {revision}")
    if not args.base_model.expanduser().is_dir():
        parser.error("--base-model must be a local NVIDIA base or your own training checkpoint")
    output = args.output_dir.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Refusing non-empty output; continuation needs a fresh output directory")
    summaries = [validate_dataset(path.expanduser().resolve()) for path in args.dataset]
    command = build_command(args)
    print(shlex.join(command), flush=True)
    if args.dry_run:
        return
    output.mkdir(parents=True, exist_ok=True)
    (output / "pgfr_training_run.json").write_text(json.dumps({
        "upstream_revision": revision, "argv": command,
        "datasets": summaries, "learning_rate": args.learning_rate,
        "checkpoint": str(output / f"checkpoint-{args.max_steps}"),
        "validation": "Input metadata only; no behavioral qualification implied",
    }, indent=2) + "\n")
    environment = os.environ.copy()
    # Keep checkpoint loading restricted even if a library requests unsafe pickle.
    environment["TORCH_FORCE_WEIGHTS_ONLY_LOAD"] = "1"
    environment.pop("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", None)
    subprocess.run(command, cwd=groot_root, env=environment, check=True)


if __name__ == "__main__":
    main()
