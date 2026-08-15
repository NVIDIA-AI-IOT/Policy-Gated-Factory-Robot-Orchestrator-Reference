#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Render portable Order744-cont24 contracts for the Isaac runtime mount."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile


MODEL_LABEL = "droid15_dual_shared3_layout3_order744_cont24_droid1f_steps3000_v1"
CHECKPOINT_FINGERPRINT = (
    "bef1f16e82d87962b6d9659c25ed5cc8e7ec75bf2a7c7bfc5afcfa1af9ca5178"
)
ROUTING = "shared-fixed-layout3-evaluation"
MODE = "independent-b1-per-arm-v1"
RELAY_CONTRACT = "explicit_pair_v1_single_frame_[0]"
DEFAULT_SERVER_PORTS = {"franka_left": 5592, "franka_right": 5593}
DEFAULT_RELAY_PORTS = {"franka_left": 5641, "franka_right": 5642}


def absolute_path(value: str, *, label: str) -> str:
    path = Path(value)
    if not path.is_absolute() or path == Path("/"):
        raise argparse.ArgumentTypeError(f"{label} must be a non-root absolute path")
    if "\x00" in value:
        raise argparse.ArgumentTypeError(f"{label} contains a null byte")
    return str(path)


def state_path(value: str, *, label: str) -> str:
    result = absolute_path(value, label=label)
    if Path(result).suffix != ".json":
        raise argparse.ArgumentTypeError(f"{label} must name a JSON file")
    return result


def tcp_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def write_json(path: Path, payload: dict) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.chmod(0o644)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def build_contracts(
    checkpoint: str,
    left_state: str,
    right_state: str,
    *,
    left_policy_port: int,
    right_policy_port: int,
    left_relay_port: int,
    right_relay_port: int,
) -> tuple[dict, dict]:
    if left_state == right_state:
        raise ValueError("left and right service-state paths must be distinct")

    selected_ports = (
        left_policy_port,
        right_policy_port,
        left_relay_port,
        right_relay_port,
    )
    if len(set(selected_ports)) != len(selected_ports):
        raise ValueError("policy and relay ports must be distinct")

    server_ports = {
        "franka_left": left_policy_port,
        "franka_right": right_policy_port,
    }
    relay_ports = {
        "franka_left": left_relay_port,
        "franka_right": right_relay_port,
    }

    relays = {}
    for arm, state in (
        ("franka_left", left_state),
        ("franka_right", right_state),
    ):
        relays[arm] = {
            "relay_contract": RELAY_CONTRACT,
            "relay_host": "127.0.0.1",
            "relay_port": relay_ports[arm],
            "server_host": "127.0.0.1",
            "server_port": server_ports[arm],
            "service_state_path": state,
        }

    serial = {
        "checkpoint": checkpoint,
        "checkpoint_fingerprint": CHECKPOINT_FINGERPRINT,
        "model_label": MODEL_LABEL,
        "relay_contract": RELAY_CONTRACT,
        "relay_host": "127.0.0.1",
        "relay_port": relay_ports["franka_left"],
        "routing": ROUTING,
        "schema_version": 1,
        "server_port": server_ports["franka_left"],
        "service_state_path": left_state,
    }
    concurrent = {
        "checkpoint": checkpoint,
        "checkpoint_fingerprint": CHECKPOINT_FINGERPRINT,
        "mode": MODE,
        "model_label": MODEL_LABEL,
        "relays": relays,
        "schema_version": 1,
    }
    return serial, concurrent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-path", required=True)
    parser.add_argument("--left-service-state", required=True)
    parser.add_argument("--right-service-state", required=True)
    parser.add_argument(
        "--left-policy-port",
        type=tcp_port,
        default=DEFAULT_SERVER_PORTS["franka_left"],
    )
    parser.add_argument(
        "--right-policy-port",
        type=tcp_port,
        default=DEFAULT_SERVER_PORTS["franka_right"],
    )
    parser.add_argument(
        "--left-relay-port",
        type=tcp_port,
        default=DEFAULT_RELAY_PORTS["franka_left"],
    )
    parser.add_argument(
        "--right-relay-port",
        type=tcp_port,
        default=DEFAULT_RELAY_PORTS["franka_right"],
    )
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checkpoint = absolute_path(args.checkpoint_path, label="checkpoint path")
    left_state = state_path(args.left_service_state, label="left service state")
    right_state = state_path(args.right_service_state, label="right service state")
    output_dir = Path(
        absolute_path(args.output_dir, label="output directory")
    )
    if output_dir.is_symlink():
        raise RuntimeError("output directory must not be a symbolic link")
    output_dir.mkdir(parents=True, exist_ok=True)
    if not output_dir.is_dir():
        raise RuntimeError("output directory is not a directory")

    try:
        serial, concurrent = build_contracts(
            checkpoint,
            left_state,
            right_state,
            left_policy_port=args.left_policy_port,
            right_policy_port=args.right_policy_port,
            left_relay_port=args.left_relay_port,
            right_relay_port=args.right_relay_port,
        )
    except ValueError as exc:
        raise SystemExit(f"render-groot-cont24-contracts: ERROR: {exc}") from exc
    write_json(output_dir / "groot_shared_policy_contract.json", serial)
    write_json(
        output_dir / "groot_shared_concurrent_policy_contract.json",
        concurrent,
    )
    print(
        "Rendered GR00T contracts in "
        f"{output_dir} for {MODEL_LABEL} using two serving instances."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
