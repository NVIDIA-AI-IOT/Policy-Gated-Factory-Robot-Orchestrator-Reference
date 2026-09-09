# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Strict loopback wire contract for one deterministic two-arm GR00T query."""

from __future__ import annotations

import pickle
import struct
from typing import Any


MAX_MESSAGE_BYTES = 32 * 1024 * 1024
ENDPOINTS = ("franka_left", "franka_right")
REQUEST_TYPE = "infer_pair_v1"
RESPONSE_TYPE = "infer_pair_result_v1"
PROTOCOL = "explicit_pair_v1"


def select_query_mode(
    active_endpoints: list[str] | tuple[str, ...],
    query_ready_endpoints: list[str] | tuple[str, ...],
) -> tuple[str, str | None]:
    """Choose the only qualified query mode for the current two-arm boundary."""

    active = set(active_endpoints)
    ready = set(query_ready_endpoints)
    known = set(ENDPOINTS)
    if not active <= known or not ready <= active:
        raise ValueError("query scheduler received invalid endpoint sets")
    if active == known and len(ready) == 1:
        waiting = next(iter(ready))
        peer = next(endpoint for endpoint in ENDPOINTS if endpoint != waiting)
        return "advance_peer", peer
    if active == known and ready == known:
        return "explicit_pair", None
    if len(active) == 1 and ready == active:
        return "terminal_pair", None
    return "advance", None


def build_terminal_pair_observations(
    active_endpoint: str,
    active_observation: dict[str, Any],
    last_observations: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Keep inference B=2 after one arm has completed.

    The active arm contributes its current observation.  The completed arm
    contributes its last validated paired observation with only the inference
    seed advanced to the active request's seed.  Its returned trajectory is
    discarded by the executor; the frozen row exists solely to preserve the
    policy's validated batch shape until the pair transaction is terminal.
    """

    if active_endpoint not in ENDPOINTS:
        raise ValueError("terminal pair active endpoint is invalid")
    if not isinstance(active_observation, dict):
        raise ValueError("terminal pair active observation must be an object")
    if (
        not isinstance(last_observations, dict)
        or set(last_observations) != set(ENDPOINTS)
    ):
        raise ValueError("terminal pair requires both frozen observations")

    seed = active_observation.get("inference_seed")
    observations: dict[str, dict[str, Any]] = {}
    for endpoint in ENDPOINTS:
        source = (
            active_observation
            if endpoint == active_endpoint
            else last_observations[endpoint]
        )
        if not isinstance(source, dict):
            raise ValueError(f"terminal pair observation for {endpoint} is invalid")
        item = dict(source)
        item["client_id"] = endpoint
        item["inference_seed"] = seed
        observations[endpoint] = item

    # Reuse the canonical validator so terminal-pair requests cannot silently
    # diverge from the normal explicit-pair wire contract.
    build_pair_request(0, observations)
    return observations


def _receive_exact(connection: Any, count: int) -> bytes:
    data = b""
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            raise IOError("paired GR00T relay closed")
        data += chunk
    return data


def _validate_pair_id(pair_id: object) -> int:
    if not isinstance(pair_id, int) or isinstance(pair_id, bool) or pair_id < 0:
        raise ValueError("pair_id must be a non-negative integer")
    return pair_id


def build_pair_request(
    pair_id: int,
    observations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build a canonical left-then-right request and reject ambiguous input."""

    pair_id = _validate_pair_id(pair_id)
    if not isinstance(observations, dict) or set(observations) != set(ENDPOINTS):
        raise ValueError("pair observations must contain exactly both Franka arms")
    canonical: dict[str, dict[str, Any]] = {}
    seeds: set[int | None] = set()
    tasks: set[str] = set()
    for endpoint in ENDPOINTS:
        observation = observations[endpoint]
        if not isinstance(observation, dict):
            raise ValueError(f"pair observation for {endpoint} must be an object")
        item = dict(observation)
        if item.get("client_id") != endpoint:
            raise ValueError(f"pair client identity mismatch for {endpoint}")
        seed = item.get("inference_seed")
        if seed is not None and (
            not isinstance(seed, int) or isinstance(seed, bool) or seed < 0
        ):
            raise ValueError(f"invalid inference seed for {endpoint}")
        task = item.get("task")
        if not isinstance(task, str) or not task.strip():
            raise ValueError(f"invalid task instruction for {endpoint}")
        seeds.add(seed)
        tasks.add(task)
        canonical[endpoint] = item
    if len(seeds) != 1:
        raise ValueError("pair observations must share one inference seed")
    if len(tasks) != 1:
        raise ValueError("pair observations must share one task instruction")
    return {
        "_pgfr_relay_request": REQUEST_TYPE,
        "schema_version": 1,
        "pair_id": pair_id,
        "observations": canonical,
    }


def validate_pair_response(
    response: object,
    *,
    expected_pair_id: int,
    expected_seed: int | None,
) -> dict[str, dict[str, Any]]:
    """Validate envelope and per-row identity before either arm uses output."""

    expected_pair_id = _validate_pair_id(expected_pair_id)
    if not isinstance(response, dict):
        raise ValueError("pair relay response must be an object")
    expected_keys = {
        "_pgfr_relay_response",
        "schema_version",
        "pair_id",
        "inference_seed",
        "batch_index",
        "batch_size",
        "results",
    }
    if set(response) != expected_keys:
        raise ValueError("pair relay response keys mismatch")
    if (
        response["_pgfr_relay_response"] != RESPONSE_TYPE
        or response["schema_version"] != 1
        or response["pair_id"] != expected_pair_id
        or response["inference_seed"] != expected_seed
        or response["batch_size"] != 2
    ):
        raise ValueError("pair relay response identity mismatch")
    batch_index = response["batch_index"]
    if not isinstance(batch_index, int) or isinstance(batch_index, bool):
        raise ValueError("pair relay batch_index is invalid")
    results = response["results"]
    if not isinstance(results, dict) or set(results) != set(ENDPOINTS):
        raise ValueError("pair relay results must contain exactly both Franka arms")
    validated: dict[str, dict[str, Any]] = {}
    for endpoint in ENDPOINTS:
        trajectory = results[endpoint]
        if not isinstance(trajectory, dict):
            raise ValueError(f"pair trajectory for {endpoint} must be an object")
        metadata = trajectory.get("_batch")
        if not isinstance(metadata, dict):
            raise ValueError(f"pair metadata missing for {endpoint}")
        if (
            metadata.get("schema_version") != 1
            or metadata.get("client_id") != endpoint
            or metadata.get("batch_index") != batch_index
            or metadata.get("batch_size") != 2
            or metadata.get("protocol") != PROTOCOL
            or metadata.get("inference_seed") != expected_seed
        ):
            raise ValueError(f"pair trajectory identity mismatch for {endpoint}")
        validated[endpoint] = trajectory
    return validated


def exchange_pair(
    connection: Any,
    *,
    pair_id: int,
    observations: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Send one request and return two fully validated action trajectories."""

    request = build_pair_request(pair_id, observations)
    payload = pickle.dumps(request, protocol=4)
    if not 1 <= len(payload) <= MAX_MESSAGE_BYTES:
        raise ValueError("paired GR00T request is too large")
    connection.sendall(struct.pack(">I", len(payload)) + payload)
    count = struct.unpack(">I", _receive_exact(connection, 4))[0]
    if not 1 <= count <= MAX_MESSAGE_BYTES:
        raise ValueError("paired GR00T response size is invalid")
    response = pickle.loads(_receive_exact(connection, count))
    seed = next(
        iter({observation.get("inference_seed") for observation in observations.values()})
    )
    return validate_pair_response(
        response,
        expected_pair_id=pair_id,
        expected_seed=seed,
    )
