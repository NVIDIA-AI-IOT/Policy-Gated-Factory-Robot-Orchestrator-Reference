#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Convert the recorded Franka joint trajectories to native GR00T DROID v2.1.

Forward kinematics is intentionally not implemented here.  ``export`` emits the
recorded seven-joint vectors for Isaac Sim's stock ``LulaKinematicsSolver``.
``build`` consumes the resulting ``panda_link8`` poses and applies the exact
DROID Euler/rotation-6D conversion used by Isaac-GR00T's
``scripts/download_droid_sample.py``.

This adapter only changes the dataset contract.  It does not define a custom
embodiment, modality, model head, trainer, policy server, or robot controller.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation


DROID_EEF_ROTATION_CORRECT = np.array(
    [[0, 0, -1], [-1, 0, 0], [0, 1, 0]], dtype=np.float64
)
PANDA_OPEN_WIDTH_M = 0.040
PANDA_CLOSED_WIDTH_M = 0.016


def _json_dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        json.dump(value, stream, indent=2)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _episode_paths(dataset: Path) -> list[Path]:
    paths = sorted(dataset.glob("data/*/episode_*.parquet"))
    if not paths:
        raise FileNotFoundError(f"No episode parquet files found under {dataset}")
    return paths


def export_joint_request(source: Path, request_path: Path) -> None:
    episodes = []
    total_frames = 0
    for episode_index, parquet_path in enumerate(_episode_paths(source)):
        frame = pd.read_parquet(parquet_path)
        state = np.stack(frame["observation.state"].to_numpy()).astype(np.float64)
        action = np.stack(frame["action"].to_numpy()).astype(np.float64)
        if state.shape[1] != 8 or action.shape[1] != 8:
            raise ValueError(
                f"Expected recorded 8D joint+gripper arrays, got {state.shape} and {action.shape}"
            )
        if not np.isfinite(state).all() or not np.isfinite(action).all():
            raise ValueError(f"Non-finite state/action in {parquet_path}")
        episodes.append(
            {
                "episode_index": episode_index,
                "source_file": parquet_path.name,
                "source_sha256": _sha256(parquet_path),
                "state_joint_position": state[:, :7].tolist(),
                "action_joint_position": action[:, :7].tolist(),
            }
        )
        total_frames += len(frame)

    _json_dump(
        request_path,
        {
            "schema_version": 1,
            "kinematics": "Isaac Sim LulaKinematicsSolver(Franka)",
            "frame": "panda_link8",
            "episodes": episodes,
        },
    )
    print(f"Exported {len(episodes)} episodes / {total_frames} frames to {request_path}")


def _cartesian_and_eef(position: np.ndarray, rotation: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Apply the native DROID convention used by NVIDIA's official converter."""
    euler_xyz = Rotation.from_matrix(rotation).as_euler("xyz")
    droid_rotation = Rotation.from_euler("XYZ", euler_xyz).as_matrix()
    droid_rotation = droid_rotation @ DROID_EEF_ROTATION_CORRECT
    cartesian = np.concatenate([position, euler_xyz], axis=-1)
    rot6d = droid_rotation[..., :2, :].reshape(*droid_rotation.shape[:-2], 6)
    eef_9d = np.concatenate([position, rot6d], axis=-1)
    return cartesian.astype(np.float32), eef_9d.astype(np.float32)


def _droid_gripper(width_m: np.ndarray) -> np.ndarray:
    """Map Panda finger width to DROID's absolute gripper convention: 0=open, 1=closed."""
    scale = PANDA_OPEN_WIDTH_M - PANDA_CLOSED_WIDTH_M
    return np.clip((PANDA_OPEN_WIDTH_M - width_m) / scale, 0.0, 1.0).astype(np.float32)


def _poses(arrays: dict, expected: int, label: str) -> tuple[np.ndarray, np.ndarray]:
    positions = np.asarray(arrays["position"], dtype=np.float64)
    rotations = np.asarray(arrays["rotation"], dtype=np.float64)
    if positions.shape != (expected, 3) or rotations.shape != (expected, 3, 3):
        raise ValueError(
            f"Bad {label} FK shapes: position={positions.shape}, rotation={rotations.shape}"
        )
    if not np.isfinite(positions).all() or not np.isfinite(rotations).all():
        raise ValueError(f"Non-finite values in {label} FK")
    orthogonality = np.max(np.abs(rotations @ rotations.transpose(0, 2, 1) - np.eye(3)))
    determinant_error = np.max(np.abs(np.linalg.det(rotations) - 1.0))
    if orthogonality > 1e-6 or determinant_error > 1e-6:
        raise ValueError(
            f"Invalid {label} rotations: orthogonality={orthogonality}, determinant={determinant_error}"
        )
    return positions, rotations


def _copy_videos(source: Path, output: Path) -> None:
    source_videos = source / "videos"
    output_videos = output / "videos"
    shutil.copytree(source_videos, output_videos)
    chunk = output_videos / "chunk-000"
    (chunk / "observation.images.front").rename(
        chunk / "observation.images.exterior_1_left"
    )
    (chunk / "observation.images.wrist").rename(chunk / "observation.images.wrist_left")


def build_dataset(source: Path, fk_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {output}")
    if source.resolve() in output.resolve().parents or output.resolve() in source.resolve().parents:
        raise ValueError("Source and output must be non-overlapping directories")
    with fk_path.open() as stream:
        fk_result = json.load(stream)
    if fk_result.get("frame") != "panda_link8":
        raise ValueError(f"Expected panda_link8 FK, got {fk_result.get('frame')!r}")

    episode_paths = _episode_paths(source)
    fk_episodes = fk_result.get("episodes", [])
    if len(fk_episodes) != len(episode_paths):
        raise ValueError(f"Episode count mismatch: {len(fk_episodes)} FK vs {len(episode_paths)} data")

    # Verify every request hash before creating output; stale FK must not be paired
    # with recaptured or edited trajectories that happen to have the same length.
    for index, (parquet_path, fk_episode) in enumerate(zip(episode_paths, fk_episodes)):
        if (fk_episode.get("episode_index") != index
                or fk_episode.get("source_file") != parquet_path.name
                or fk_episode.get("source_sha256") != _sha256(parquet_path)):
            raise ValueError(f"FK source identity mismatch: {parquet_path}")
    output.mkdir(parents=True)
    (output / "data" / "chunk-000").mkdir(parents=True)
    (output / "meta").mkdir()
    _copy_videos(source, output)

    total_frames = 0
    max_joint_target_error = 0.0
    max_eef_target_distance = 0.0
    gripper_state_min = 1.0
    gripper_state_max = 0.0

    for episode_index, (parquet_path, fk_episode) in enumerate(zip(episode_paths, fk_episodes)):
        if int(fk_episode.get("episode_index", -1)) != episode_index:
            raise ValueError(f"FK episode ordering mismatch at episode {episode_index}")
        frame = pd.read_parquet(parquet_path)
        state8 = np.stack(frame["observation.state"].to_numpy()).astype(np.float32)
        action8 = np.stack(frame["action"].to_numpy()).astype(np.float32)
        if state8.ndim != 2 or action8.shape != state8.shape or state8.shape[1] != 8:
            raise ValueError(f"Expected matching 8D state/action: {parquet_path}")
        if not np.isfinite(state8).all() or not np.isfinite(action8).all():
            raise ValueError(f"Non-finite state/action: {parquet_path}")
        nframes = len(frame)
        state_position, state_rotation = _poses(fk_episode["state"], nframes, "state")
        action_position, action_rotation = _poses(fk_episode["action"], nframes, "action")

        state_cartesian, state_eef = _cartesian_and_eef(state_position, state_rotation)
        action_cartesian, action_eef = _cartesian_and_eef(action_position, action_rotation)
        state_gripper = _droid_gripper(state8[:, 7:8])
        action_gripper = _droid_gripper(action8[:, 7:8])
        state_joint = state8[:, :7]
        action_joint = action8[:, :7]
        state17 = np.concatenate([state_eef, state_gripper, state_joint], axis=-1)
        action17 = np.concatenate([action_eef, action_gripper, action_joint], axis=-1)

        frame["observation.state.cartesian_position"] = list(state_cartesian)
        frame["observation.state.eef_9d"] = list(state_eef)
        frame["observation.state.gripper_position"] = list(state_gripper)
        frame["observation.state.joint_position"] = list(state_joint)
        frame["observation.state"] = list(state17)
        frame["action.cartesian_position"] = list(action_cartesian)
        frame["action.eef_9d"] = list(action_eef)
        frame["action.gripper_position"] = list(action_gripper)
        frame["action.joint_position"] = list(action_joint)
        frame["action"] = list(action17)
        destination = output / "data" / "chunk-000" / f"episode_{episode_index:06d}.parquet"
        frame.to_parquet(destination, index=False)

        total_frames += nframes
        max_joint_target_error = max(
            max_joint_target_error, float(np.max(np.abs(action_joint - state_joint)))
        )
        max_eef_target_distance = max(
            max_eef_target_distance,
            float(np.max(np.linalg.norm(action_position - state_position, axis=-1))),
        )
        gripper_state_min = min(gripper_state_min, float(state_gripper.min()))
        gripper_state_max = max(gripper_state_max, float(state_gripper.max()))

    shutil.copy2(source / "meta" / "episodes.jsonl", output / "meta" / "episodes.jsonl")
    shutil.copy2(source / "meta" / "tasks.jsonl", output / "meta" / "tasks.jsonl")
    encoder_provenance = source / "meta" / "ffmpeg_provenance.json"
    if encoder_provenance.is_file():
        shutil.copy2(encoder_provenance, output / "meta" / encoder_provenance.name)

    with (source / "meta" / "info.json").open() as stream:
        source_info = json.load(stream)
    info = {
        "codebase_version": "v2.1",
        "robot_type": "droid",
        "total_episodes": len(episode_paths),
        "total_frames": total_frames,
        "total_tasks": int(source_info.get("total_tasks", 1)),
        "total_videos": 2 * len(episode_paths),
        "total_chunks": 1,
        "chunks_size": 1000,
        "fps": int(source_info["fps"]),
        "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
        "splits": {"train": f"0:{len(episode_paths)}"},
        "features": {
            "observation.images.exterior_1_left": {
                "dtype": "video",
                "shape": [180, 320, 3],
            },
            "observation.images.wrist_left": {"dtype": "video", "shape": [180, 320, 3]},
            "observation.state": {"dtype": "float32", "shape": [17]},
            "action": {"dtype": "float32", "shape": [17]},
            "timestamp": {"dtype": "float32", "shape": [1]},
            "frame_index": {"dtype": "int64", "shape": [1]},
            "episode_index": {"dtype": "int64", "shape": [1]},
            "index": {"dtype": "int64", "shape": [1]},
            "task_index": {"dtype": "int64", "shape": [1]},
        },
    }
    modality = {
        "state": {
            "eef_9d": {"start": 0, "end": 9},
            "gripper_position": {"start": 9, "end": 10},
            "joint_position": {"start": 10, "end": 17},
        },
        "action": {
            "eef_9d": {"start": 0, "end": 9},
            "gripper_position": {"start": 9, "end": 10},
            "joint_position": {"start": 10, "end": 17},
        },
        "video": {
            "exterior_1_left": {"original_key": "observation.images.exterior_1_left"},
            "wrist_left": {"original_key": "observation.images.wrist_left"},
        },
        "annotation": {
            "language.language_instruction": {"original_key": "task_index"},
        },
    }
    _json_dump(output / "meta" / "info.json", info)
    _json_dump(output / "meta" / "modality.json", modality)
    # Statistics are deliberately absent until gr00t/data/stats.py computes
    # absolute and relative values from this dataset with the training modality.
    # Empty placeholders can otherwise look like completed training inputs.
    _json_dump(
        output / "meta" / "native_droid_provenance.json",
        {
            "source_dataset": str(source.resolve()),
            "source_contract": "absolute 7-DoF joint targets + Panda finger width meters",
            "kinematics": fk_result.get("kinematics"),
            "kinematics_frame": "panda_link8",
            "droid_eef_conversion": "Isaac-GR00T scripts/download_droid_sample.py convention",
            "droid_gripper": {
                "open_width_m": PANDA_OPEN_WIDTH_M,
                "closed_width_m": PANDA_CLOSED_WIDTH_M,
                "output": "0=open, 1=closed",
            },
            "validation": {
                "episodes": len(episode_paths),
                "frames": total_frames,
                "max_joint_target_state_error_rad": max_joint_target_error,
                "max_eef_target_state_distance_m": max_eef_target_distance,
                "state_gripper_min": gripper_state_min,
                "state_gripper_max": gripper_state_max,
            },
        },
    )
    print(
        f"Built native DROID dataset: {len(episode_paths)} episodes / {total_frames} frames; "
        f"max joint target gap={max_joint_target_error:.6f} rad, "
        f"max EEF target gap={max_eef_target_distance:.6f} m"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--source", type=Path, required=True)
    export_parser.add_argument("--request", type=Path, required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--source", type=Path, required=True)
    build_parser.add_argument("--fk-results", type=Path, required=True)
    build_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "export":
        export_joint_request(args.source, args.request)
    else:
        build_dataset(args.source, args.fk_results, args.output)


if __name__ == "__main__":
    main()
