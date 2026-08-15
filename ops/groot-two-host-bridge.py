#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Bridge Thor-owned GR00T serving into an Isaac host's loopback contract.

The bridge owns only four SSH local forwards and two derived readiness files.
The authoritative policy, relay, and readiness records remain on Thor.  No
local readiness is published until the tunnel and both remote identities pass
the complete contract check.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time
from typing import Mapping


MODEL_LABEL = "droid15_dual_shared3_layout3_order744_cont24_droid1f_steps3000_v1"
CHECKPOINT_FINGERPRINT = (
    "bef1f16e82d87962b6d9659c25ed5cc8e7ec75bf2a7c7bfc5afcfa1af9ca5178"
)
RELAY_CONTRACT = "explicit_pair_v1_single_frame_[0]"
REMOTE_UNITS = (
    "ic-groot-policy@shared-left.service",
    "ic-groot-policy@shared-right.service",
    "ic-groot-relay@shared-left.service",
    "ic-groot-relay@shared-right.service",
)
STATE_NAMES = ("shared-left.json", "shared-right.json")
TARGET_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*@[A-Za-z0-9_.:-]+")

REMOTE_PROBE = r"""
import json
from pathlib import Path
import socket
import subprocess
import sys

units = json.loads(sys.argv[1])
state_root = Path(sys.argv[2])
ports = [int(value) for value in json.loads(sys.argv[3])]
active = {}
for unit in units:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", unit],
        check=False,
    )
    active[unit] = result.returncode == 0
listeners = {}
for port in ports:
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(1.0)
    try:
        connection.connect(("127.0.0.1", port))
        listeners[str(port)] = True
    except OSError:
        listeners[str(port)] = False
    finally:
        connection.close()
states = {}
for name in ("shared-left.json", "shared-right.json"):
    path = state_root / name
    try:
        if not path.is_file() or path.is_symlink():
            raise ValueError("not a regular file")
        states[name] = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        states[name] = {"_probe_error": str(exc)}
print(json.dumps({"active": active, "listeners": listeners, "states": states}))
"""


class BridgeError(RuntimeError):
    """Fail-closed bridge configuration or runtime error."""


@dataclass(frozen=True)
class Arm:
    name: str
    state_name: str
    remote_policy_port: int
    remote_relay_port: int
    local_policy_port: int
    local_relay_port: int


@dataclass(frozen=True)
class Config:
    thor_ssh: str
    remote_checkpoint: str
    remote_state_root: Path
    local_state_root: Path
    poll_seconds: float
    ssh_bin: str
    arms: tuple[Arm, Arm]


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise BridgeError(f"{name} is required")
    return value


def _port(environment: Mapping[str, str], name: str) -> int:
    raw = _required(environment, name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise BridgeError(f"{name} must be an integer") from exc
    if not 1 <= value <= 65535:
        raise BridgeError(f"{name} must be between 1 and 65535")
    return value


def _absolute_path(raw: str, name: str) -> Path:
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise BridgeError(f"{name} must be a normalized absolute path")
    return path


def _require_loopback(host: str, name: str) -> None:
    try:
        address = ipaddress.ip_address(socket.gethostbyname(host))
    except OSError as exc:
        raise BridgeError(f"{name} does not resolve: {host}") from exc
    if not address.is_loopback:
        raise BridgeError(f"{name} must be loopback, got {host}")


def load_config(environment: Mapping[str, str] | None = None) -> Config:
    env = os.environ if environment is None else environment
    target = _required(env, "IC_GROOT_THOR_SSH")
    if not TARGET_PATTERN.fullmatch(target):
        raise BridgeError("IC_GROOT_THOR_SSH must have the form user@host")
    checkpoint = str(
        _absolute_path(
            _required(env, "IC_GROOT_REMOTE_CHECKPOINT"),
            "IC_GROOT_REMOTE_CHECKPOINT",
        )
    )
    remote_root = _absolute_path(
        _required(env, "IC_GROOT_REMOTE_STATE_ROOT"),
        "IC_GROOT_REMOTE_STATE_ROOT",
    )
    local_root = _absolute_path(
        _required(env, "IC_GROOT_LOCAL_STATE_ROOT"),
        "IC_GROOT_LOCAL_STATE_ROOT",
    )
    try:
        poll_seconds = float(env.get("IC_GROOT_BRIDGE_POLL_SECONDS", "5"))
    except ValueError as exc:
        raise BridgeError("IC_GROOT_BRIDGE_POLL_SECONDS must be numeric") from exc
    if not 1 <= poll_seconds <= 300:
        raise BridgeError("IC_GROOT_BRIDGE_POLL_SECONDS must be between 1 and 300")

    left = Arm(
        "franka_left",
        STATE_NAMES[0],
        _port(env, "IC_GROOT_REMOTE_LEFT_POLICY_PORT"),
        _port(env, "IC_GROOT_REMOTE_LEFT_RELAY_PORT"),
        _port(env, "IC_GROOT_LOCAL_LEFT_POLICY_PORT"),
        _port(env, "IC_GROOT_LOCAL_LEFT_RELAY_PORT"),
    )
    right = Arm(
        "franka_right",
        STATE_NAMES[1],
        _port(env, "IC_GROOT_REMOTE_RIGHT_POLICY_PORT"),
        _port(env, "IC_GROOT_REMOTE_RIGHT_RELAY_PORT"),
        _port(env, "IC_GROOT_LOCAL_RIGHT_POLICY_PORT"),
        _port(env, "IC_GROOT_LOCAL_RIGHT_RELAY_PORT"),
    )
    all_ports = (
        left.remote_policy_port,
        right.remote_policy_port,
        left.remote_relay_port,
        right.remote_relay_port,
        left.local_policy_port,
        right.local_policy_port,
        left.local_relay_port,
        right.local_relay_port,
    )
    if len(set(all_ports[:4])) != 4:
        raise BridgeError("remote policy and relay ports must be distinct")
    if len(set(all_ports[4:])) != 4:
        raise BridgeError("local policy and relay ports must be distinct")

    if not local_root.is_dir() or local_root.is_symlink():
        raise BridgeError("IC_GROOT_LOCAL_STATE_ROOT must be an existing real directory")
    if local_root.stat().st_uid != os.getuid():
        raise BridgeError("IC_GROOT_LOCAL_STATE_ROOT must be owned by the bridge user")
    ssh_bin = env.get("IC_GROOT_SSH_BIN", "/usr/bin/ssh").strip()
    if not Path(ssh_bin).is_absolute():
        raise BridgeError("IC_GROOT_SSH_BIN must be an absolute path")
    return Config(
        thor_ssh=target,
        remote_checkpoint=checkpoint,
        remote_state_root=remote_root,
        local_state_root=local_root,
        poll_seconds=poll_seconds,
        ssh_bin=ssh_bin,
        arms=(left, right),
    )


def ssh_options(config: Config) -> list[str]:
    return [
        config.ssh_bin,
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "ControlMaster=no",
        "-o",
        "ExitOnForwardFailure=yes",
    ]


def tunnel_command(config: Config) -> list[str]:
    command = ssh_options(config)
    command[1:1] = ["-N"]
    for arm in config.arms:
        command.extend(
            (
                "-L",
                f"127.0.0.1:{arm.local_policy_port}:127.0.0.1:{arm.remote_policy_port}",
                "-L",
                f"127.0.0.1:{arm.local_relay_port}:127.0.0.1:{arm.remote_relay_port}",
            )
        )
    command.append(config.thor_ssh)
    return command


def remote_probe_command(config: Config) -> list[str]:
    command = ssh_options(config)
    argv = (
        "/usr/bin/python3",
        "-c",
        REMOTE_PROBE,
        json.dumps(REMOTE_UNITS),
        str(config.remote_state_root),
        json.dumps(
            [
                arm.remote_policy_port
                for arm in config.arms
            ]
            + [
                arm.remote_relay_port
                for arm in config.arms
            ]
        ),
    )
    command.extend((config.thor_ssh, " ".join(shlex.quote(value) for value in argv)))
    return command


def _validate_remote_state(state: object, arm: Arm, config: Config) -> dict[str, object]:
    if not isinstance(state, dict):
        raise BridgeError(f"{arm.state_name}: state must be an object")
    expected = {
        "schema_version": 1,
        "status": "ready",
        "model_label": MODEL_LABEL,
        "checkpoint": config.remote_checkpoint,
        "checkpoint_fingerprint": CHECKPOINT_FINGERPRINT,
        "server_host": "127.0.0.1",
        "server_port": arm.remote_policy_port,
        "relay_host": "127.0.0.1",
        "relay_port": arm.remote_relay_port,
        "relay_contract": RELAY_CONTRACT,
        "preserve_until_explicit_stop": True,
    }
    for key, value in expected.items():
        if state.get(key) != value:
            raise BridgeError(
                f"{arm.state_name}: {key} mismatch "
                f"(expected {value!r}, got {state.get(key)!r})"
            )
    relay_pid = state.get("relay_pid")
    if isinstance(relay_pid, bool) or not isinstance(relay_pid, int) or relay_pid <= 0:
        raise BridgeError(f"{arm.state_name}: relay_pid must be a positive integer")
    return dict(state)


def validate_probe(probe: object, config: Config) -> dict[str, dict[str, object]]:
    if not isinstance(probe, dict):
        raise BridgeError("remote probe did not return an object")
    active = probe.get("active")
    listeners = probe.get("listeners")
    states = probe.get("states")
    if not isinstance(active, dict) or not all(active.get(unit) is True for unit in REMOTE_UNITS):
        raise BridgeError("one or more Thor shared GR00T units are inactive")
    if not isinstance(listeners, dict):
        raise BridgeError("Thor listener probe is missing")
    for arm in config.arms:
        for port in (arm.remote_policy_port, arm.remote_relay_port):
            if listeners.get(str(port)) is not True:
                raise BridgeError(f"Thor loopback listener {port} is unavailable")
    if not isinstance(states, dict):
        raise BridgeError("Thor readiness states are missing")
    return {
        arm.state_name: _validate_remote_state(states.get(arm.state_name), arm, config)
        for arm in config.arms
    }


def rewrite_states(
    remote_states: Mapping[str, Mapping[str, object]],
    config: Config,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for arm in config.arms:
        state = dict(remote_states[arm.state_name])
        state["server_host"] = "127.0.0.1"
        state["server_port"] = arm.local_policy_port
        state["relay_host"] = "127.0.0.1"
        state["relay_port"] = arm.local_relay_port
        state["bridge_thor_ssh"] = config.thor_ssh
        state["bridge_remote_server_port"] = arm.remote_policy_port
        state["bridge_remote_relay_port"] = arm.remote_relay_port
        result[arm.state_name] = state
    return result


def invalidate_states(config: Config) -> None:
    for name in STATE_NAMES:
        path = config.local_state_root / name
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.exists():
                raise BridgeError(f"refusing to remove non-file state path: {path}")
        except FileNotFoundError:
            pass


def publish_states(
    states: Mapping[str, Mapping[str, object]],
    config: Config,
) -> None:
    if set(states) != set(STATE_NAMES):
        raise BridgeError("the bridge must publish exactly the left and right states")
    temporary: dict[str, Path] = {}
    try:
        for name in STATE_NAMES:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=config.local_state_root,
                prefix=f".{name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                json.dump(states[name], stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
                temporary[name] = Path(stream.name)
            temporary[name].chmod(0o644)
        try:
            invalidate_states(config)
            for name in STATE_NAMES:
                os.replace(temporary[name], config.local_state_root / name)
                del temporary[name]
        except Exception:
            invalidate_states(config)
            raise
    finally:
        for path in temporary.values():
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def probe_remote(config: Config) -> dict[str, dict[str, object]]:
    result = subprocess.run(
        remote_probe_command(config),
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise BridgeError(f"Thor readiness probe failed: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BridgeError("Thor readiness probe returned invalid JSON") from exc
    return validate_probe(payload, config)


def verify_local_tunnel(config: Config) -> None:
    for arm in config.arms:
        for port in (arm.local_policy_port, arm.local_relay_port):
            connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            connection.settimeout(1.0)
            try:
                connection.connect(("127.0.0.1", port))
            except OSError as exc:
                raise BridgeError(f"local forwarded listener {port} is unavailable") from exc
            finally:
                connection.close()


def run(config: Config) -> None:
    invalidate_states(config)
    stopping = False
    tunnel: subprocess.Popen[str] | None = None

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        if tunnel is not None and tunnel.poll() is None:
            tunnel.terminate()

    previous_term = signal.signal(signal.SIGTERM, request_stop)
    previous_int = signal.signal(signal.SIGINT, request_stop)
    try:
        tunnel = subprocess.Popen(
            tunnel_command(config),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=sys.stderr,
            text=True,
        )
        while not stopping:
            if tunnel.poll() is not None:
                raise BridgeError(f"SSH tunnel exited with status {tunnel.returncode}")
            remote_states = probe_remote(config)
            verify_local_tunnel(config)
            publish_states(rewrite_states(remote_states, config), config)
            deadline = time.monotonic() + config.poll_seconds
            while not stopping and time.monotonic() < deadline:
                if tunnel.poll() is not None:
                    raise BridgeError(
                        f"SSH tunnel exited with status {tunnel.returncode}"
                    )
                time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
    finally:
        invalidate_states(config)
        if tunnel is not None and tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait(timeout=5)
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check-config",
        action="store_true",
        help="validate configuration and print the SSH tunnel command without connecting",
    )
    mode.add_argument(
        "--invalidate-states",
        action="store_true",
        help="remove both bridge-owned derived readiness files and exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = load_config()
        if args.check_config:
            print(shlex.join(tunnel_command(config)))
            return 0
        if args.invalidate_states:
            invalidate_states(config)
            return 0
        run(config)
    except (BridgeError, OSError, subprocess.SubprocessError) as exc:
        print(f"groot-two-host-bridge: ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
