#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Serve explicit or compatibility-batched native-DROID policy requests.

The NVIDIA policy already accepts observations with a batch dimension.  Its
published PolicyServer intentionally processes one ZeroMQ request at a time.
The hardened concurrent path sends both arm observations in one versioned
request, making B=2 deterministic.  Independent legacy requests retain their
bounded-window B=1/B=2 behavior for serial and terminal-arm fallback.

The Isaac-facing protocol remains the length-prefixed pickle contract used by
the certified executor.  It is trusted loopback traffic only; neither this
listener nor the policy listener may be exposed to an untrusted network.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import ipaddress
import json
import os
from pathlib import Path
import pickle
import re
import socket
import socketserver
import struct
import tempfile
import threading
import time
from typing import Any, Callable

import numpy as np


MAX_MESSAGE_BYTES = 32 * 1024 * 1024
ALLOWED_CLIENTS = frozenset(("franka_left", "franka_right"))
EXPLICIT_PAIR_REQUEST = "infer_pair_v1"
EXPLICIT_PAIR_RESPONSE = "infer_pair_result_v1"
EXPLICIT_PAIR_PROTOCOL = "explicit_pair_v1"
TIMED_BATCH_PROTOCOL = "timed_batch_v1"
RELAY_CONTRACT = "explicit_pair_v1_single_frame_[0]"


def _require_loopback(host: str, label: str) -> None:
    try:
        address = ipaddress.ip_address(socket.gethostbyname(host))
    except OSError as exc:
        raise ValueError(f"{label} host does not resolve: {host}") from exc
    if not address.is_loopback:
        raise ValueError(f"{label} must bind/connect through loopback, got {host}")


def _write_service_state(
    *,
    relay_host: str,
    relay_port: int,
    policy_host: str,
    policy_port: int,
) -> Path | None:
    """Atomically publish the exact live identity consumed by Isaac.

    Unit tests and ad-hoc development runs may omit IC_SERVICE_STATE_PATH.  A
    production run that provides it must also provide a complete, validated
    model identity; a partial or stale readiness record is never emitted.
    """

    raw_path = os.environ.get("IC_SERVICE_STATE_PATH", "").strip()
    if not raw_path:
        return None
    state_path = Path(raw_path)
    model_label = os.environ.get("IC_MODEL_LABEL", "").strip()
    checkpoint = Path(os.environ.get("IC_MODEL_PATH", "").strip())
    fingerprint = os.environ.get("IC_CHECKPOINT_FINGERPRINT", "").strip()
    if not state_path.is_absolute() or not state_path.parent.is_dir():
        raise ValueError("IC_SERVICE_STATE_PATH must have an existing absolute parent")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", model_label):
        raise ValueError("IC_MODEL_LABEL is invalid")
    if not checkpoint.is_absolute() or not checkpoint.is_dir():
        raise ValueError("IC_MODEL_PATH must identify an existing checkpoint directory")
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("IC_CHECKPOINT_FINGERPRINT must be 64 lowercase hex characters")
    state = {
        "schema_version": 1,
        "status": "ready",
        "model_label": model_label,
        "checkpoint": str(checkpoint),
        "checkpoint_fingerprint": fingerprint,
        "server_host": policy_host,
        "server_port": policy_port,
        "relay_host": relay_host,
        "relay_port": relay_port,
        "relay_contract": RELAY_CONTRACT,
        "relay_pid": os.getpid(),
        "preserve_until_explicit_stop": True,
    }
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=state_path.parent,
            prefix=f".{state_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_name = stream.name
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # This record carries no secret; Isaac may run under a container UID
        # different from the workstation user and must be able to validate it.
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, state_path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return state_path


def _array(value: object) -> np.ndarray:
    if isinstance(value, (tuple, list)):
        if len(value) != 2:
            raise ValueError("encoded image must be (bytes, shape)")
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
    count = struct.unpack(">I", header)[0]
    if count < 1 or count > MAX_MESSAGE_BYTES:
        raise ValueError(f"invalid relay payload size: {count}")
    return _receive_exact(connection, count)


def _send(connection: socket.socket, value: object) -> None:
    payload = pickle.dumps(value, protocol=4)
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError(f"relay response is too large: {len(payload)}")
    connection.sendall(struct.pack(">I", len(payload)) + payload)


@dataclass
class _Prepared:
    client_id: str
    inference_seed: int | None
    request: dict[str, Any]
    source_joints: np.ndarray


@dataclass
class _Pending:
    prepared: _Prepared
    event: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None
    error: BaseException | None = None


class NativeDroidBatcher:
    """Own one PolicyClient and serialize B=1/B=2 inference through it."""

    def __init__(
        self,
        client: Any,
        language_key: str,
        *,
        batch_window_s: float = 0.025,
        result_timeout_s: float = 300.0,
        resize: Callable[[np.ndarray, tuple[int, int]], np.ndarray] | None = None,
    ) -> None:
        if batch_window_s < 0 or batch_window_s > 0.5:
            raise ValueError("batch_window_s must be in [0, 0.5]")
        self.client = client
        self.language_key = language_key
        self.batch_window_s = batch_window_s
        self.result_timeout_s = result_timeout_s
        self._resize = resize or self._cv2_resize
        self._queue: deque[_Pending] = deque()
        self._cv = threading.Condition()
        self._inference_lock = threading.Lock()
        self._closed = False
        self._batch_index = 0
        self._worker = threading.Thread(
            target=self._run, name="ic-groot-batch2", daemon=True
        )
        self._worker.start()

    @staticmethod
    def _cv2_resize(image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
        import cv2

        return cv2.resize(image, size)

    def close(self) -> None:
        with self._cv:
            if self._closed:
                return
            self._closed = True
            self._cv.notify_all()
        self._worker.join(timeout=2.0)

    def _prepare(self, observation: dict[str, Any]) -> _Prepared:
        client_id = str(observation.get("client_id") or "")
        if client_id not in ALLOWED_CLIENTS:
            raise ValueError(
                f"client_id must be one of {sorted(ALLOWED_CLIENTS)}, got {client_id!r}"
            )
        joints = np.asarray(observation["joint_position"], dtype=np.float32)
        eef_9d = np.asarray(observation["eef_9d"], dtype=np.float32)
        gripper = np.asarray(observation["gripper_position"], dtype=np.float32)
        if joints.shape != (7,) or eef_9d.shape != (9,) or gripper.shape != (1,):
            raise ValueError(
                "bad native state shapes: "
                f"joints={joints.shape} eef={eef_9d.shape} gripper={gripper.shape}"
            )
        if not all(np.isfinite(value).all() for value in (joints, eef_9d, gripper)):
            raise ValueError("non-finite native DROID state")

        exterior = self._resize(_array(observation["outside"])[..., :3], (320, 180))
        wrist = self._resize(_array(observation["wrist"])[..., :3], (320, 180))
        if exterior.shape != (180, 320, 3) or wrist.shape != (180, 320, 3):
            raise ValueError(
                f"bad resized video shapes: outside={exterior.shape} wrist={wrist.shape}"
            )
        seed_value = observation.get("inference_seed")
        seed = int(seed_value) if seed_value is not None else None
        if seed is not None and seed < 0:
            raise ValueError("inference_seed must be non-negative")
        task = observation.get("task")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")
        return _Prepared(
            client_id=client_id,
            inference_seed=seed,
            source_joints=joints,
            request={
                "video": {
                    "exterior_image_1_left": exterior[None, None, ...],
                    "wrist_image_left": wrist[None, None, ...],
                },
                "state": {
                    "eef_9d": eef_9d[None, None],
                    "gripper_position": gripper[None, None],
                    "joint_position": joints[None, None],
                },
                "language": {self.language_key: [[task]]},
            },
        )

    def infer(self, observation: dict[str, Any]) -> dict[str, Any]:
        pending = _Pending(self._prepare(observation))
        with self._cv:
            if self._closed:
                raise RuntimeError("batcher is closed")
            self._queue.append(pending)
            self._cv.notify()
        if not pending.event.wait(self.result_timeout_s):
            raise TimeoutError(
                f"GR00T batch result timed out for {pending.prepared.client_id}"
            )
        if pending.error is not None:
            raise RuntimeError(
                f"GR00T inference failed for {pending.prepared.client_id}"
            ) from pending.error
        if pending.result is None:
            raise RuntimeError("GR00T batcher completed without a result")
        return pending.result

    def infer_pair(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Run one explicit left/right request as exactly one B=2 inference."""

        expected_keys = {
            "_ic_relay_request",
            "schema_version",
            "pair_id",
            "observations",
        }
        if set(envelope) != expected_keys:
            raise ValueError(
                "explicit pair envelope keys mismatch: "
                f"{sorted(set(envelope) ^ expected_keys)}"
            )
        if (
            envelope["_ic_relay_request"] != EXPLICIT_PAIR_REQUEST
            or envelope["schema_version"] != 1
        ):
            raise ValueError("unsupported explicit pair protocol")
        pair_id = envelope["pair_id"]
        if not isinstance(pair_id, int) or isinstance(pair_id, bool) or pair_id < 0:
            raise ValueError("explicit pair_id must be a non-negative integer")
        observations = envelope["observations"]
        if not isinstance(observations, dict) or set(observations) != ALLOWED_CLIENTS:
            raise ValueError(
                "explicit pair observations must contain exactly "
                f"{sorted(ALLOWED_CLIENTS)}"
            )
        prepared = []
        for client_id in ("franka_left", "franka_right"):
            observation = observations[client_id]
            if not isinstance(observation, dict):
                raise ValueError(f"explicit pair observation for {client_id} is invalid")
            item = dict(observation)
            supplied_client = item.get("client_id")
            if supplied_client != client_id:
                raise ValueError(
                    f"explicit pair client identity mismatch for {client_id}"
                )
            prepared.append(_Pending(self._prepare(item)))
        seeds = {item.prepared.inference_seed for item in prepared}
        if len(seeds) != 1:
            raise ValueError("explicit pair observations must share one inference seed")
        tasks = {
            item.prepared.request["language"][self.language_key][0][0]
            for item in prepared
        }
        if len(tasks) != 1:
            raise ValueError("explicit pair observations must share one task instruction")
        with self._cv:
            if self._closed:
                raise RuntimeError("batcher is closed")
        self._infer_batch(prepared, protocol=EXPLICIT_PAIR_PROTOCOL)
        results = {
            item.prepared.client_id: item.result
            for item in prepared
        }
        if any(result is None for result in results.values()):
            raise RuntimeError("explicit pair inference completed without both results")
        batch_indices = {
            result["_batch"]["batch_index"]  # type: ignore[index]
            for result in results.values()
        }
        if len(batch_indices) != 1:
            raise RuntimeError("explicit pair results have mismatched batch identity")
        return {
            "_ic_relay_response": EXPLICIT_PAIR_RESPONSE,
            "schema_version": 1,
            "pair_id": pair_id,
            "inference_seed": next(iter(seeds)),
            "batch_index": next(iter(batch_indices)),
            "batch_size": 2,
            "results": results,
        }

    @staticmethod
    def _compatible(left: _Pending, right: _Pending) -> bool:
        return (
            left.prepared.client_id != right.prepared.client_id
            and left.prepared.inference_seed == right.prepared.inference_seed
        )

    def _take_batch(self) -> list[_Pending] | None:
        with self._cv:
            while not self._queue and not self._closed:
                self._cv.wait()
            if self._closed and not self._queue:
                return None
            first = self._queue.popleft()
            deadline = time.monotonic() + self.batch_window_s
            while True:
                for candidate in tuple(self._queue):
                    if self._compatible(first, candidate):
                        self._queue.remove(candidate)
                        return [first, candidate]
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self._closed:
                    return [first]
                self._cv.wait(remaining)

    @staticmethod
    def _combine(items: list[_Pending], language_key: str) -> dict[str, Any]:
        prepared = [item.prepared.request for item in items]
        return {
            "video": {
                key: np.concatenate(
                    [request["video"][key] for request in prepared], axis=0
                )
                for key in ("exterior_image_1_left", "wrist_image_left")
            },
            "state": {
                key: np.concatenate(
                    [request["state"][key] for request in prepared], axis=0
                )
                for key in ("eef_9d", "gripper_position", "joint_position")
            },
            "language": {
                language_key: [
                    request["language"][language_key][0] for request in prepared
                ]
            },
        }

    @staticmethod
    def _row_result(
        action: dict[str, Any],
        row: int,
        source_joints: np.ndarray,
        *,
        batch_size: int,
        batch_index: int,
        client_id: str,
        inference_seconds: float,
        inference_seed: int | None,
        protocol: str,
    ) -> dict[str, Any]:
        predicted_joints = np.asarray(action["joint_position"][row], dtype=np.float32)
        predicted_gripper = np.asarray(
            action["gripper_position"][row], dtype=np.float32
        )
        if predicted_joints.ndim != 2 or predicted_joints.shape[1] != 7:
            raise ValueError(f"bad joint action shape: {predicted_joints.shape}")
        if predicted_gripper.shape != (len(predicted_joints), 1):
            raise ValueError(f"bad gripper action shape: {predicted_gripper.shape}")
        if len(predicted_joints) < 15:
            raise ValueError(f"native action chunk is too short: {len(predicted_joints)}")
        if not np.isfinite(predicted_joints).all() or not np.isfinite(
            predicted_gripper
        ).all():
            raise ValueError("non-finite native DROID action")
        gripper_closed = predicted_gripper > 0.5
        return {
            "single_arm": predicted_joints,
            "gripper": np.where(gripper_closed, 0.016, 0.040).astype(np.float32),
            "_batch": {
                "schema_version": 1,
                "client_id": client_id,
                "batch_index": batch_index,
                "batch_size": batch_size,
                "protocol": protocol,
                "inference_seed": inference_seed,
                "inference_seconds": round(inference_seconds, 6),
                "first_joint_error": float(
                    np.max(np.abs(predicted_joints[0] - source_joints))
                ),
                "grip_closed_actions": int(gripper_closed.sum()),
            },
        }

    def _infer_batch(
        self,
        items: list[_Pending],
        *,
        protocol: str = TIMED_BATCH_PROTOCOL,
    ) -> None:
        with self._inference_lock:
            batch_index = self._batch_index
            self._batch_index += 1
            request = self._combine(items, self.language_key)
            seed = items[0].prepared.inference_seed
            options = {"inference_seed": seed} if seed is not None else None
            started = time.perf_counter()
            response = self.client.get_action(request, options=options)[0]
            inference_seconds = time.perf_counter() - started
            batch_size = len(items)
            for row, item in enumerate(items):
                item.result = self._row_result(
                    response,
                    row,
                    item.prepared.source_joints,
                    batch_size=batch_size,
                    batch_index=batch_index,
                    client_id=item.prepared.client_id,
                    inference_seconds=inference_seconds,
                    inference_seed=seed,
                    protocol=protocol,
                )
        print(
            "NATIVE_DROID_BATCH2_QUERY "
            f"index={batch_index} batch={batch_size} protocol={protocol} seed={seed} "
            f"clients={','.join(item.prepared.client_id for item in items)} "
            f"inference={inference_seconds:.3f}s",
            flush=True,
        )

    def _run(self) -> None:
        while True:
            items = self._take_batch()
            if items is None:
                return
            try:
                self._infer_batch(items)
            except BaseException as exc:
                for item in items:
                    item.error = exc
            finally:
                for item in items:
                    item.event.set()


def _validate_modality_config(config: dict[str, Any]) -> str:
    if config["video"].delta_indices != [0]:
        raise ValueError(
            f"expected native-DROID video delta [0], got {config['video'].delta_indices}"
        )
    if config["state"].delta_indices != [0]:
        raise ValueError(
            f"expected native-DROID state delta [0], got {config['state'].delta_indices}"
        )
    if config["action"].delta_indices != list(range(40)):
        raise ValueError(
            "expected native-DROID action delta [0..39], got "
            f"{config['action'].delta_indices}"
        )
    if config["video"].modality_keys != [
        "exterior_image_1_left",
        "wrist_image_left",
    ]:
        raise ValueError(
            f"unexpected native-DROID video keys: {config['video'].modality_keys}"
        )
    keys = ["eef_9d", "gripper_position", "joint_position"]
    if config["state"].modality_keys != keys:
        raise ValueError(f"unexpected native-DROID state keys: {config['state'].modality_keys}")
    if config["action"].modality_keys != keys:
        raise ValueError(
            f"unexpected native-DROID action keys: {config['action'].modality_keys}"
        )
    language_keys = config["language"].modality_keys
    if len(language_keys) != 1:
        raise ValueError(f"expected one language key, got {language_keys}")
    return language_keys[0]


class _RelayServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 8


class _RelayHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        batcher: NativeDroidBatcher = self.server.batcher  # type: ignore[attr-defined]
        while True:
            message = _receive(self.request)
            if message is None:
                return
            observation = pickle.loads(message)
            if not isinstance(observation, dict):
                raise ValueError("relay request must be a dictionary")
            if observation.get("_ic_relay_request") == EXPLICIT_PAIR_REQUEST:
                result = batcher.infer_pair(observation)
            else:
                result = batcher.infer(observation)
            _send(self.request, result)


def main() -> None:
    from gr00t.policy.server_client import PolicyClient

    host = os.environ.get("IC_RELAY_HOST", "127.0.0.1")
    port = int(os.environ.get("IC_RELAY_PORT", "5611"))
    policy_host = os.environ.get("IC_POLICY_HOST", "127.0.0.1")
    policy_port = int(os.environ.get("IC_POLICY_PORT", "5571"))
    batch_window_s = float(os.environ.get("IC_BATCH_WINDOW_MS", "25")) / 1000.0
    _require_loopback(host, "relay")
    _require_loopback(policy_host, "policy")

    client = PolicyClient(host=policy_host, port=policy_port, timeout_ms=300_000)
    language_key = _validate_modality_config(client.get_modality_config())
    batcher = NativeDroidBatcher(
        client, language_key, batch_window_s=batch_window_s
    )
    with _RelayServer((host, port), _RelayHandler) as server:
        server.batcher = batcher  # type: ignore[attr-defined]
        state_path = _write_service_state(
            relay_host=host,
            relay_port=port,
            policy_host=policy_host,
            policy_port=policy_port,
        )
        print(
            "NATIVE_DROID_BATCH2_RELAY_READY "
            f"{host}:{port} -> {policy_host}:{policy_port} "
            f"batch_window_ms={batch_window_s * 1000:.1f} max_batch=2 "
            "video_delta=[0] state=17D action=17D "
            f"service_state={state_path or 'disabled'}",
            flush=True,
        )
        try:
            server.serve_forever()
        finally:
            batcher.close()
            client.close()


if __name__ == "__main__":
    main()
