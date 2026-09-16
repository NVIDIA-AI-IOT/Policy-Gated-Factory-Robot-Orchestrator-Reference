# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

import numpy as np


MODULE_PATH = (
    Path(__file__).parents[1] / "relay" / "native_droid_relay_batch2.py"
)
SPEC = importlib.util.spec_from_file_location("native_droid_relay_batch2", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
relay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = relay
SPEC.loader.exec_module(relay)

TRANSPORT_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "pgfr_groot_pair_transport.py"
)
TRANSPORT_SPEC = importlib.util.spec_from_file_location(
    "pgfr_groot_pair_transport", TRANSPORT_PATH
)
assert TRANSPORT_SPEC is not None and TRANSPORT_SPEC.loader is not None
transport = importlib.util.module_from_spec(TRANSPORT_SPEC)
sys.modules[TRANSPORT_SPEC.name] = transport
TRANSPORT_SPEC.loader.exec_module(transport)


class FakeClient:
    def __init__(self) -> None:
        self.calls = []
        self.lock = threading.Lock()

    def get_action(self, observation, options=None):
        with self.lock:
            self.calls.append((observation, options))
        batch = observation["state"]["joint_position"].shape[0]
        horizon = 40
        joints = np.repeat(
            observation["state"]["joint_position"][:, :1, :], horizon, axis=1
        ).astype(np.float32)
        gripper = np.zeros((batch, horizon, 1), dtype=np.float32)
        return (
            {
                "joint_position": joints,
                "gripper_position": gripper,
                "eef_9d": np.zeros((batch, horizon, 9), dtype=np.float32),
            },
            {},
        )


def observation(client_id: str, seed: int = 7):
    image = np.zeros((180, 320, 3), dtype=np.uint8)
    joint_value = 1.0 if client_id == "franka_left" else 2.0
    return {
        "client_id": client_id,
        "inference_seed": seed,
        "task": "pick the green brick and place it on the green pad",
        "outside": image,
        "wrist": image,
        "joint_position": np.full(7, joint_value, dtype=np.float32),
        "eef_9d": np.zeros(9, dtype=np.float32),
        "gripper_position": np.zeros(1, dtype=np.float32),
    }


def identity_resize(image, _size):
    return image


def run_pair(batcher, left_seed=7, right_seed=7):
    results = {}

    def invoke(arm, seed):
        results[arm] = batcher.infer(observation(arm, seed))

    left = threading.Thread(target=invoke, args=("franka_left", left_seed))
    right = threading.Thread(target=invoke, args=("franka_right", right_seed))
    left.start()
    right.start()
    left.join(timeout=2)
    right.join(timeout=2)
    assert not left.is_alive() and not right.is_alive()
    return results


def explicit_pair_envelope(left_seed=7, right_seed=7):
    return {
        "_pgfr_relay_request": relay.EXPLICIT_PAIR_REQUEST,
        "schema_version": 1,
        "pair_id": 4,
        "observations": {
            "franka_right": observation("franka_right", right_seed),
            "franka_left": observation("franka_left", left_seed),
        },
    }


class TestNativeDroidBatcher(unittest.TestCase):
    def test_scheduler_never_uses_independent_query_with_two_active_arms(self):
        self.assertEqual(
            transport.select_query_mode(
                ["franka_left", "franka_right"],
                ["franka_left"],
            ),
            ("advance_peer", "franka_right"),
        )
        self.assertEqual(
            transport.select_query_mode(
                ["franka_left", "franka_right"],
                ["franka_left", "franka_right"],
            ),
            ("explicit_pair", None),
        )
        self.assertEqual(
            transport.select_query_mode(
                ["franka_left"],
                ["franka_left"],
            ),
            ("terminal_pair", None),
        )

    def test_explicit_pair_round_trips_over_relay_socket(self):
        client = FakeClient()
        batcher = relay.NativeDroidBatcher(
            client, "task", batch_window_s=0, resize=identity_resize
        )
        server = relay._RelayServer(("127.0.0.1", 0), relay._RelayHandler)
        server.batcher = batcher
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.start()
        connection = socket.create_connection(server.server_address, timeout=2)
        connection.settimeout(2)
        observations = explicit_pair_envelope()["observations"]
        try:
            results = transport.exchange_pair(
                connection,
                pair_id=4,
                observations=observations,
            )
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)
            batcher.close()

        self.assertFalse(server_thread.is_alive())
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(set(results), set(transport.ENDPOINTS))
        self.assertEqual(
            {
                result["_batch"]["protocol"]
                for result in results.values()
            },
            {transport.PROTOCOL},
        )

    def test_explicit_pair_is_one_deterministic_b2_request(self):
        client = FakeClient()
        batcher = relay.NativeDroidBatcher(
            client, "task", batch_window_s=0, resize=identity_resize
        )
        try:
            response = batcher.infer_pair(explicit_pair_envelope())
        finally:
            batcher.close()

        self.assertEqual(len(client.calls), 1)
        request, options = client.calls[0]
        self.assertEqual(request["state"]["joint_position"].shape, (2, 1, 7))
        self.assertEqual(request["state"]["joint_position"][0, 0, 0], 1.0)
        self.assertEqual(request["state"]["joint_position"][1, 0, 0], 2.0)
        self.assertEqual(options, {"inference_seed": 7})
        self.assertEqual(response["_pgfr_relay_response"], relay.EXPLICIT_PAIR_RESPONSE)
        self.assertEqual(response["pair_id"], 4)
        self.assertEqual(response["batch_size"], 2)
        self.assertEqual(set(response["results"]), relay.ALLOWED_CLIENTS)
        validated = transport.validate_pair_response(
            response,
            expected_pair_id=4,
            expected_seed=7,
        )
        self.assertEqual(set(validated), set(transport.ENDPOINTS))
        self.assertEqual(transport.REQUEST_TYPE, relay.EXPLICIT_PAIR_REQUEST)
        self.assertEqual(transport.RESPONSE_TYPE, relay.EXPLICIT_PAIR_RESPONSE)
        self.assertEqual(transport.PROTOCOL, relay.EXPLICIT_PAIR_PROTOCOL)
        for client_id, result in response["results"].items():
            self.assertEqual(result["_batch"]["client_id"], client_id)
            self.assertEqual(result["_batch"]["batch_size"], 2)
            self.assertEqual(
                result["_batch"]["protocol"], relay.EXPLICIT_PAIR_PROTOCOL
            )
            self.assertEqual(result["_batch"]["inference_seed"], 7)

    def test_isaac_validator_rejects_cross_arm_result_mapping(self):
        client = FakeClient()
        batcher = relay.NativeDroidBatcher(
            client, "task", batch_window_s=0, resize=identity_resize
        )
        try:
            response = batcher.infer_pair(explicit_pair_envelope())
        finally:
            batcher.close()
        response["results"]["franka_left"]["_batch"]["client_id"] = (
            "franka_right"
        )
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            transport.validate_pair_response(
                response,
                expected_pair_id=4,
                expected_seed=7,
            )

    def test_explicit_pair_rejects_mismatched_seeds_without_inference(self):
        client = FakeClient()
        batcher = relay.NativeDroidBatcher(
            client, "task", batch_window_s=0, resize=identity_resize
        )
        try:
            with self.assertRaisesRegex(ValueError, "share one inference seed"):
                batcher.infer_pair(explicit_pair_envelope(3, 4))
        finally:
            batcher.close()
        self.assertEqual(client.calls, [])

    def test_explicit_pair_rejects_mismatched_tasks_without_inference(self):
        client = FakeClient()
        envelope = explicit_pair_envelope()
        envelope["observations"]["franka_right"]["task"] = "pick the red cube"
        batcher = relay.NativeDroidBatcher(
            client, "task", batch_window_s=0, resize=identity_resize
        )
        try:
            with self.assertRaisesRegex(ValueError, "share one task instruction"):
                batcher.infer_pair(envelope)
        finally:
            batcher.close()
        self.assertEqual(client.calls, [])

    def test_explicit_pair_rejects_partial_envelope_without_inference(self):
        client = FakeClient()
        envelope = explicit_pair_envelope()
        del envelope["observations"]["franka_right"]
        batcher = relay.NativeDroidBatcher(
            client, "task", batch_window_s=0, resize=identity_resize
        )
        try:
            with self.assertRaisesRegex(ValueError, "exactly"):
                batcher.infer_pair(envelope)
        finally:
            batcher.close()
        self.assertEqual(client.calls, [])

    def test_explicit_pair_rejects_missing_client_identity(self):
        client = FakeClient()
        envelope = explicit_pair_envelope()
        del envelope["observations"]["franka_left"]["client_id"]
        batcher = relay.NativeDroidBatcher(
            client, "task", batch_window_s=0, resize=identity_resize
        )
        try:
            with self.assertRaisesRegex(ValueError, "client identity mismatch"):
                batcher.infer_pair(envelope)
        finally:
            batcher.close()
        self.assertEqual(client.calls, [])

    def test_two_arms_share_one_batched_policy_request(self):
        client = FakeClient()
        batcher = relay.NativeDroidBatcher(
            client, "task", batch_window_s=0.1, resize=identity_resize
        )
        try:
            results = run_pair(batcher)
        finally:
            batcher.close()

        self.assertEqual(len(client.calls), 1)
        request, options = client.calls[0]
        self.assertEqual(
            request["video"]["exterior_image_1_left"].shape,
            (2, 1, 180, 320, 3),
        )
        self.assertEqual(request["state"]["joint_position"].shape, (2, 1, 7))
        self.assertEqual(options, {"inference_seed": 7})
        self.assertEqual(
            {result["_batch"]["batch_size"] for result in results.values()},
            {2},
        )
        self.assertEqual(
            {result["_batch"]["protocol"] for result in results.values()},
            {relay.TIMED_BATCH_PROTOCOL},
        )
        self.assertEqual(results["franka_left"]["single_arm"][0, 0], 1.0)
        self.assertEqual(results["franka_right"]["single_arm"][0, 0], 2.0)

    def test_different_seeds_are_not_batched(self):
        client = FakeClient()
        batcher = relay.NativeDroidBatcher(
            client, "task", batch_window_s=0.02, resize=identity_resize
        )
        try:
            results = run_pair(batcher, left_seed=3, right_seed=4)
        finally:
            batcher.close()

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            {result["_batch"]["batch_size"] for result in results.values()},
            {1},
        )

    def test_unmatched_arm_falls_back_to_batch_one(self):
        client = FakeClient()
        batcher = relay.NativeDroidBatcher(
            client, "task", batch_window_s=0.001, resize=identity_resize
        )
        try:
            result = batcher.infer(observation("franka_left"))
        finally:
            batcher.close()

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result["_batch"]["batch_size"], 1)

    def test_rejects_unknown_client_before_inference(self):
        client = FakeClient()
        batcher = relay.NativeDroidBatcher(
            client, "task", batch_window_s=0, resize=identity_resize
        )
        try:
            with self.assertRaisesRegex(ValueError, "client_id"):
                batcher.infer(observation("mobilebot"))
        finally:
            batcher.close()
        self.assertEqual(client.calls, [])

    def test_service_state_is_atomic_and_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / "checkpoint-1000"
            checkpoint.mkdir()
            state_path = root / "service_state.json"
            environment = {
                "PGFR_SERVICE_STATE_PATH": str(state_path),
                "PGFR_MODEL_LABEL": "shared-layout3",
                "PGFR_MODEL_PATH": str(checkpoint),
                "PGFR_CHECKPOINT_FINGERPRINT": "a" * 64,
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                result = relay._write_service_state(
                    relay_host="127.0.0.1",
                    relay_port=5611,
                    policy_host="127.0.0.1",
                    policy_port=5571,
                )

            self.assertEqual(result, state_path)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "ready")
            self.assertEqual(state["relay_contract"], relay.RELAY_CONTRACT)
            self.assertEqual(state["checkpoint"], str(checkpoint))
            self.assertEqual(state["relay_pid"], os.getpid())
            self.assertEqual(state_path.stat().st_mode & 0o777, 0o644)
            self.assertEqual(list(root.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
