#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Bridge Isaac to a native-DROID policy with the checkpoint's [0] video contract.

This is the single-frame counterpart of ``native_droid_relay.py``.  It keeps
the same socket protocol, state/action mapping, gripper conversion, and
validation, while packing video exactly as NVIDIA's DROID rollout example does
for ``delta_indices=[0]``: ``(B=1, T=1, H, W, C)``.
"""

from __future__ import annotations

import os
import pickle
import socket
import struct
import time

import cv2
import numpy as np

from gr00t.policy.server_client import PolicyClient


HOST = os.environ.get("IC_RELAY_HOST", "127.0.0.1")
PORT = int(os.environ.get("IC_RELAY_PORT", "5603"))
POLICY_HOST = os.environ.get("IC_POLICY_HOST", "127.0.0.1")
POLICY_PORT = int(os.environ.get("IC_POLICY_PORT", "5561"))


def _array(value: object) -> np.ndarray:
    if isinstance(value, (tuple, list)):
        return np.frombuffer(value[0], np.uint8).reshape(value[1]).copy()
    return np.asarray(value, dtype=np.uint8)


def _receive_exact(connection: socket.socket, count: int) -> bytes | None:
    data = b""
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def _receive(connection: socket.socket) -> bytes | None:
    header = _receive_exact(connection, 4)
    if header is None:
        return None
    return _receive_exact(connection, struct.unpack(">I", header)[0])


def _send(connection: socket.socket, value: object) -> None:
    payload = pickle.dumps(value, protocol=4)
    connection.sendall(struct.pack(">I", len(payload)) + payload)


client = PolicyClient(host=POLICY_HOST, port=POLICY_PORT, timeout_ms=300_000)
config = client.get_modality_config()
if config["video"].delta_indices != [0]:
    raise ValueError(
        "Expected checkpoint-matched native DROID video delta [0], got "
        f"{config['video'].delta_indices}"
    )
if config["state"].delta_indices != [0]:
    raise ValueError(
        f"Expected native DROID state delta [0], got {config['state'].delta_indices}"
    )
if config["action"].delta_indices != list(range(40)):
    raise ValueError(
        "Expected native DROID action delta [0..39], got "
        f"{config['action'].delta_indices}"
    )
if config["video"].modality_keys != [
    "exterior_image_1_left",
    "wrist_image_left",
]:
    raise ValueError(
        f"Unexpected native DROID video keys: {config['video'].modality_keys}"
    )
expected_state_action_keys = [
    "eef_9d",
    "gripper_position",
    "joint_position",
]
if config["state"].modality_keys != expected_state_action_keys:
    raise ValueError(
        f"Unexpected native DROID state keys: {config['state'].modality_keys}"
    )
if config["action"].modality_keys != expected_state_action_keys:
    raise ValueError(
        f"Unexpected native DROID action keys: {config['action'].modality_keys}"
    )
language_key = config["language"].modality_keys[0]

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(1)
print(
    f"NATIVE_DROID_SINGLE_FRAME_RELAY_READY {HOST}:{PORT} -> "
    f"{POLICY_HOST}:{POLICY_PORT} video_delta=[0] state=17D action=17D",
    flush=True,
)

query_index = 0
while True:
    connection, _ = server.accept()
    try:
        while True:
            message = _receive(connection)
            if message is None:
                break
            observation = pickle.loads(message)
            joints = np.asarray(
                observation["joint_position"], dtype=np.float32
            )
            eef_9d = np.asarray(observation["eef_9d"], dtype=np.float32)
            gripper = np.asarray(
                observation["gripper_position"], dtype=np.float32
            )
            if (
                joints.shape != (7,)
                or eef_9d.shape != (9,)
                or gripper.shape != (1,)
            ):
                raise ValueError(
                    "Bad native state shapes: "
                    f"joints={joints.shape} eef={eef_9d.shape} "
                    f"gripper={gripper.shape}"
                )
            if not all(
                np.isfinite(value).all()
                for value in (joints, eef_9d, gripper)
            ):
                raise ValueError("Non-finite native DROID state")

            exterior = cv2.resize(
                _array(observation["outside"])[..., :3], (320, 180)
            )
            wrist = cv2.resize(
                _array(observation["wrist"])[..., :3], (320, 180)
            )
            request = {
                "video": {
                    "exterior_image_1_left": exterior[None, None, ...],
                    "wrist_image_left": wrist[None, None, ...],
                },
                "state": {
                    "eef_9d": eef_9d[None, None],
                    "gripper_position": gripper[None, None],
                    "joint_position": joints[None, None],
                },
                "language": {language_key: [[observation["task"]]]},
            }
            options = (
                {"inference_seed": int(observation["inference_seed"])}
                if observation.get("inference_seed") is not None
                else None
            )
            started = time.perf_counter()
            response = client.get_action(request, options=options)[0]
            inference_seconds = time.perf_counter() - started
            predicted_joints = np.asarray(
                response["joint_position"][0], dtype=np.float32
            )
            predicted_gripper = np.asarray(
                response["gripper_position"][0], dtype=np.float32
            )
            if (
                predicted_joints.ndim != 2
                or predicted_joints.shape[1] != 7
            ):
                raise ValueError(
                    f"Bad joint action shape: {predicted_joints.shape}"
                )
            if predicted_gripper.shape != (len(predicted_joints), 1):
                raise ValueError(
                    f"Bad gripper action shape: {predicted_gripper.shape}"
                )
            if len(predicted_joints) < 15:
                raise ValueError(
                    f"Native action chunk is too short: {len(predicted_joints)}"
                )
            if (
                not np.isfinite(predicted_joints).all()
                or not np.isfinite(predicted_gripper).all()
            ):
                raise ValueError("Non-finite native DROID action")

            gripper_closed = predicted_gripper > 0.5
            finger_targets_m = np.where(
                gripper_closed, 0.016, 0.040
            ).astype(np.float32)
            result = {
                "single_arm": predicted_joints,
                "gripper": finger_targets_m,
            }
            first_joint_error = float(
                np.max(np.abs(predicted_joints[0] - joints))
            )
            print(
                "NATIVE_DROID_SINGLE_FRAME_QUERY "
                f"index={query_index} inference={inference_seconds:.3f}s "
                f"first_joint_error={first_joint_error:.5f} "
                f"grip_closed={int(gripper_closed.sum())}/"
                f"{len(gripper_closed)}",
                flush=True,
            )
            query_index += 1
            _send(connection, result)
    except Exception:
        import traceback

        print(
            "NATIVE_DROID_SINGLE_FRAME_RELAY_ERR:\n"
            + traceback.format_exc(),
            flush=True,
        )
    finally:
        connection.close()
