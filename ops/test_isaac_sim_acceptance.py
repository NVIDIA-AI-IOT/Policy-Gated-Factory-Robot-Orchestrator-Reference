# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free tests for the live Isaac Sim acceptance command."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "ops" / "isaac_sim_acceptance.py"
SCRIPT = ROOT / "ops" / "accept-isaac-sim-workstation.sh"
SOURCE = (
    ROOT
    / "reference"
    / "policy-gated-factory-robot-orchestrator-reference"
    / "isaac-cell"
)
ROS_DIGEST = (
    "sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4"
)

spec = importlib.util.spec_from_file_location("isaac_sim_acceptance", CLIENT)
assert spec is not None and spec.loader is not None
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def reset_state() -> dict[str, object]:
    return {
        "endpoints": ["franka_left", "franka_right", "mobilebot"],
        "conveyor_1": ["red", "blue", "green"],
        "tote": {},
        "tote_on_rack": False,
        "cubes": [
            {"i": 0, "color": "red", "where": "conveyor"},
            {"i": 2, "color": "blue", "where": "conveyor"},
            {"i": 4, "color": "green", "where": "conveyor"},
        ],
    }


def test_stream_contract_has_fifteen_distinct_application_payloads() -> None:
    assert len(acceptance.REQUIRED_TOPICS) == 15
    assert len(set(acceptance.REQUIRED_TOPICS)) == 15
    assert len(acceptance.IMAGE_TOPICS) == 8
    assert len(acceptance.CAMERA_INFO_TOPICS) == 5
    assert set(acceptance.STRING_TOPICS) == {"/pgfr/floor_state", "/pgfr/joints"}


def test_reset_and_red_move_require_observed_world_state() -> None:
    state = reset_state()
    assert acceptance.is_deterministic_reset_state(state)
    assert not acceptance.is_red_move_state(state)

    moved = json.loads(json.dumps(state))
    moved["conveyor_1"] = ["blue", "green"]
    moved["tote"] = {"red": "in"}
    moved["cubes"][0]["where"] = "tote"
    assert not acceptance.is_deterministic_reset_state(moved)
    assert acceptance.is_red_move_state(moved)

    moved["cubes"].append({"i": 1, "color": "red", "where": "conveyor"})
    assert not acceptance.is_red_move_state(moved)


def test_reset_rejects_duplicate_extra_or_wrong_identity_cubes() -> None:
    duplicate = reset_state()
    duplicate["cubes"][2] = {"i": 5, "color": "red", "where": "conveyor"}
    assert not acceptance.is_deterministic_reset_state(duplicate)

    extra = reset_state()
    extra["cubes"].append({"i": 1, "color": "red", "where": "conveyor"})
    assert not acceptance.is_deterministic_reset_state(extra)

    wrong_id = reset_state()
    wrong_id["cubes"][0]["i"] = 1
    assert not acceptance.is_deterministic_reset_state(wrong_id)


def test_red_move_rejects_any_collateral_or_extra_state_change() -> None:
    moved = reset_state()
    moved["conveyor_1"] = ["blue", "green"]
    moved["tote"] = {"red": "in"}
    moved["cubes"][0]["where"] = "tote"
    assert acceptance.is_red_move_state(moved)

    collateral = json.loads(json.dumps(moved))
    collateral["cubes"][1]["where"] = "off"
    assert not acceptance.is_red_move_state(collateral)

    wrong_conveyor = json.loads(json.dumps(moved))
    wrong_conveyor["conveyor_1"] = ["green", "blue"]
    assert not acceptance.is_red_move_state(wrong_conveyor)

    extra_tote_state = json.loads(json.dumps(moved))
    extra_tote_state["tote"]["blue"] = "in"
    assert not acceptance.is_red_move_state(extra_tote_state)

    rack_moved = json.loads(json.dumps(moved))
    rack_moved["tote_on_rack"] = True
    assert not acceptance.is_red_move_state(rack_moved)

    extra_cube = json.loads(json.dumps(moved))
    extra_cube["cubes"].append({"i": 1, "color": "red", "where": "off"})
    assert not acceptance.is_red_move_state(extra_cube)


def test_image_validator_accepts_exact_rgb_and_depth_payloads() -> None:
    rgb = SimpleNamespace(width=4, height=3, step=12, encoding="rgb8", data=b"x" * 36)
    assert acceptance.validate_image(rgb, "/wrist_cam/image_raw") == {
        "width": 4,
        "height": 3,
        "encoding": "rgb8",
        "bytes": 36,
    }

    depth_float = SimpleNamespace(
        width=4, height=3, step=16, encoding="32FC1", data=b"x" * 48
    )
    assert acceptance.validate_image(depth_float, "/rack_cam/depth")["bytes"] == 48

    depth_uint = SimpleNamespace(
        width=4, height=3, step=8, encoding="16UC1", data=b"x" * 24
    )
    assert acceptance.validate_image(depth_uint, "/table_cam/depth")["bytes"] == 24


@pytest.mark.parametrize(
    ("topic", "message", "error"),
    (
        (
            "/wrist_cam/image_raw",
            SimpleNamespace(width=4, height=3, step=16, encoding="rgba8", data=b"x" * 48),
            "RGB encoding",
        ),
        (
            "/rack_cam/depth",
            SimpleNamespace(width=4, height=3, step=12, encoding="rgb8", data=b"x" * 36),
            "depth encoding",
        ),
        (
            "/wrist_cam/image_raw",
            SimpleNamespace(width=4, height=3, step=13, encoding="rgb8", data=b"x" * 39),
            "row step",
        ),
        (
            "/rack_cam/depth",
            SimpleNamespace(width=4, height=3, step=12, encoding="32FC1", data=b"x" * 36),
            "row step",
        ),
        (
            "/wrist_cam/image_raw",
            SimpleNamespace(width=4, height=3, step=12, encoding="rgb8", data=b"x" * 35),
            "payload size",
        ),
        (
            "/wrist_cam/image_raw",
            SimpleNamespace(width=4, height=3, step=12, encoding="rgb8", data=b"x" * 37),
            "payload size",
        ),
    ),
)
def test_image_validator_rejects_wrong_encoding_stride_or_payload_size(
    topic: str,
    message: SimpleNamespace,
    error: str,
) -> None:
    with pytest.raises(acceptance.AcceptanceError, match=error):
        acceptance.validate_image(message, topic)


def test_camera_info_validator_rejects_nonfinite_data() -> None:

    camera = SimpleNamespace(width=640, height=480, k=[1.0] * 9)
    assert acceptance.validate_camera_info(camera, "/rack_cam/camera_info")["width"] == 640
    camera.k[0] = float("nan")
    with pytest.raises(acceptance.AcceptanceError, match="intrinsic matrix"):
        acceptance.validate_camera_info(camera, "/rack_cam/camera_info")


def test_result_must_echo_the_unique_command_and_verified_success() -> None:
    command = {
        "action": "move",
        "color": "red",
        "destination": "tote_red",
        "endpoint": "franka_left",
        "goal_id": "accept-unit-move-red",
    }
    result = {
        "action": "move",
        "args": command,
        "goal_id": command["goal_id"],
        "success": True,
        "verified": True,
        "reason": "in tote_red off=0.001",
    }
    assert acceptance.validate_result(json.dumps(result), command) == result

    result["args"] = {**command, "endpoint": "franka_right"}
    with pytest.raises(acceptance.AcceptanceError, match="changed endpoint"):
        acceptance.validate_result(json.dumps(result), command)

    result["args"] = command
    result["verified"] = False
    with pytest.raises(acceptance.AcceptanceError, match="failed"):
        acceptance.validate_result(json.dumps(result), command)


def test_run_id_and_timeout_arguments_are_fail_closed() -> None:
    parsed = acceptance.parse_args(["--run-id", "unit_42"])
    assert parsed.run_id == "unit_42"
    with pytest.raises(SystemExit):
        acceptance.parse_args(["--run-id", "../bad"])
    with pytest.raises(SystemExit):
        acceptance.parse_args(["--stream-timeout", "0"])


def test_wrapper_pins_and_bounds_the_ros_sidecar_contract() -> None:
    wrapper = SCRIPT.read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")

    assert f"ros:jazzy-ros-base-noble@{ROS_DIGEST}" in wrapper
    for contract in (
        "--pull never --platform linux/amd64",
        '--ipc="container:$CONTAINER"',
        "--user 1234:1234",
        "--network host",
        ".HostConfig.NetworkMode",
        "ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST",
        "--read-only",
        "--cap-drop ALL",
        "PGFR_CELL_UP markers=all",
        "ISAAC_IMAGE_REF",
        "'{{.Image}}'",
        "'{{.Config.User}}'",
        "'{{.Path}}'",
        "exactly one /scripts mount",
        "mounted pgfr_cell tree differs",
        "--exec /scripts/pgfr_boot.py",
        "PGFR_STAGE=/scripts/our_factory.usda",
        "must define exactly one ROS_DOMAIN_ID",
        "does not match",
        'docker logs --since "$log_since"',
        "wait_for_unique_command_logs",
        "PGFR_CELL_BOOT_ERR|PGFR_STEP_ERR",
        "commands=3 critical=0",
    ):
        assert contract in wrapper
    assert "docker stop " not in wrapper
    assert "docker rm " not in wrapper
    assert "ROS_LOCALHOST_ONLY" not in wrapper
    assert "\nsleep 1\n" not in wrapper
    assert client.count("self.command.publish(") == 1
    assert 'self.count_subscribers("/pgfr/command") == 1' in client
    assert 'self.count_publishers("/pgfr/result") == 1' in client
    assert 'self.count_publishers("/pgfr/command") == 1' in client
    spin_body = client[
        client.index("def spin_until(") : client.index("def wait_for_control_graph(")
    ]
    assert "if self.control_graph_attested:" in spin_body
    assert "self.assert_exclusive_control_graph()" in spin_body
    discovery_body = client[
        client.index("def wait_for_control_graph(") : client.index(
            "def assert_exclusive_control_graph("
        )
    ]
    assert discovery_body.index("self.spin_until(") < discovery_body.index(
        "self.control_graph_attested = True"
    )
    publish_body = client[
        client.index("def publish_once_and_wait(") : client.index(
            "def wait_for_reset_state("
        )
    ]
    assert publish_body.index("self.assert_exclusive_control_graph()") < publish_body.index(
        "self.command.publish("
    )
    assert "self._subscriptions" not in client
    assert "self._application_subscriptions" in client
    assert "red cube to leave the conveyor and enter tote_red" in client
    assert "all 15 required fresh camera/state payloads" in client


def make_fake_docker(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_DOCKER_CALLS"
case "$1" in
  version)
    exit 0
    ;;
  inspect)
    case "$3" in
      *.Mounts*.Source*) printf '%s\\n' "$FAKE_SCRIPTS_SOURCE" ;;
      *.Mounts*.Type*) printf '%s\\n' "${FAKE_SCRIPTS_TYPE:-bind}" ;;
      *.Mounts*.RW*) printf '%s\\n' "${FAKE_SCRIPTS_RW:-false}" ;;
      *.Mounts*)
        mount_count="${FAKE_SCRIPTS_COUNT:-1}"
        while [ "$mount_count" -gt 0 ]; do
          printf x
          mount_count=$((mount_count - 1))
        done
        printf '\\n'
        ;;
      *.Args*)
        if [ "${FAKE_PRIVACY_ARGS_MODE:-valid}" != missing ]; then
          printf '%s\n' \
            --/telemetry/enableAnonymousAppName=false \
            --/telemetry/enableAnonymousData=false \
            --/telemetry/useOpenEndpoint=false \
            --/privacy/usage=false \
            --/privacy/performance=false \
            --/privacy/personalization=false \
            --/crashreporter/enabled=false
        fi
        case "${FAKE_PRIVACY_ARGS_MODE:-valid}" in
          duplicate) printf '%s\n' --/telemetry/enableAnonymousAppName=false ;;
          conflicting) printf '%s\n' --/telemetry/enableAnonymousAppName=true ;;
        esac
        if [ "${FAKE_CONTAINER_ARGS_VALID:-1}" = 1 ]; then
          printf '%s\\n' -v --exec /scripts/pgfr_boot.py
        else
          printf '%s\\n' -v --exec /scripts/wrong.py
        fi
        ;;
      *.Image*) printf '%s\\n' "${FAKE_CONTAINER_IMAGE_ID:-sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}" ;;
      *.Config.User*) printf '%s\\n' "${FAKE_CONTAINER_USER:-1234:1234}" ;;
      *.Path*) printf '%s\\n' "${FAKE_CONTAINER_ENTRYPOINT:-/isaac-sim/runheadless.sh}" ;;
      *State.Running*) printf 'true\\n' ;;
      *HostConfig.IpcMode*) printf '%s\\n' "${FAKE_IPC_MODE:-shareable}" ;;
      *HostConfig.NetworkMode*) printf '%s\\n' "${FAKE_NETWORK_MODE:-host}" ;;
      *Config.Env*)
        accept_eula_count="${FAKE_ACCEPT_EULA_COUNT:-1}"
        while [ "$accept_eula_count" -gt 0 ]; do
          printf 'ACCEPT_EULA=%s\n' "${FAKE_ACCEPT_EULA:-Y}"
          accept_eula_count=$((accept_eula_count - 1))
        done
        telemetry_count="${FAKE_TELEMETRY_COUNT:-1}"
        while [ "$telemetry_count" -gt 0 ]; do
          printf 'OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=%s\n' "${FAKE_TELEMETRY:-1}"
          telemetry_count=$((telemetry_count - 1))
        done
        if [ "${FAKE_ROS_DOMAIN_PRESENT:-1}" = 1 ]; then
          printf 'ROS_DOMAIN_ID=%s\\n' "${FAKE_ROS_DOMAIN_ID:-42}"
        fi
        printf 'PGFR_STAGE=%s\\n' "${FAKE_PGFR_STAGE:-/scripts/our_factory.usda}"
        ;;
      *) exit 90 ;;
    esac
    ;;
  image)
    [ "$2" = inspect ] || exit 90
    if [ "${3:-}" = --format ]; then
      printf '%s\\n' "${FAKE_EXPECTED_IMAGE_ID:-sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}"
    fi
    exit 0
    ;;
  run)
    previous=
    run_id=
    for argument in "$@"; do
      if [ "$previous" = --run-id ]; then
        run_id="$argument"
      fi
      previous="$argument"
    done
    [ -n "$run_id" ] || exit 91
    printf '%s\\n' "$run_id" > "$FAKE_RUN_ID"
    printf 'PGFR_ISAAC_ROS_ACCEPTANCE_PASS {"run_id":"%s"}\\n' "$run_id"
    [ "${FAKE_SIDECAR_FAIL:-0}" != 1 ] || exit 7
    ;;
  logs)
    if [ "${2:-}" = --since ]; then
      log_poll=0
      if [ -f "$FAKE_LOG_POLLS" ]; then
        log_poll="$(sed -n '1p' "$FAKE_LOG_POLLS")"
      fi
      log_poll=$((log_poll + 1))
      printf '%s\\n' "$log_poll" > "$FAKE_LOG_POLLS"
      if [ "$log_poll" -le "${FAKE_LOG_DELAY_POLLS:-0}" ]; then
        exit 0
      fi
      run_id="$(sed -n '1p' "$FAKE_RUN_ID")"
      printf "PGFR_CMD {'action': 'reset', 'goal_id': 'accept-%s-reset-before'}\\n" "$run_id"
      printf "PGFR_CMD {'action': 'move', 'goal_id': 'accept-%s-move-red'}\\n" "$run_id"
      printf "PGFR_CMD {'action': 'reset', 'goal_id': 'accept-%s-reset-after'}\\n" "$run_id"
      if [ "${FAKE_CRITICAL:-0}" = 1 ]; then
        printf 'PGFR_STEP_ERR: simulated current-run failure\\n'
      fi
    else
      printf 'PGFR_CELL_UP markers=all\\n'
      ready_lines="${FAKE_READY_LOG_LINES:-0}"
      while [ "$ready_lines" -gt 0 ]; do
        printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\\n'
        ready_lines=$((ready_lines - 1))
      done
    fi
    ;;
  *)
    exit 90
    ;;
esac
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return fake_bin


def invoke_wrapper(
    tmp_path: Path,
    *,
    ipc_mode: str = "shareable",
    network_mode: str = "host",
    critical: bool = False,
    sidecar_fail: bool = False,
    image_id: str = (
        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ),
    expected_image_id: str = (
        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ),
    container_user: str = "1234:1234",
    container_entrypoint: str = "/isaac-sim/runheadless.sh",
    scripts_source: Path = SOURCE,
    scripts_type: str = "bind",
    scripts_rw: str = "false",
    scripts_count: int = 1,
    container_args_valid: bool = True,
    pgfr_stage: str = "/scripts/our_factory.usda",
    ros_domain: str | None = "42",
    ros_domain_override: str | None = None,
    log_delay_polls: int = 0,
    ready_log_lines: int = 0,
    accept_eula: str = "Y",
    accept_eula_count: int = 1,
    telemetry_opt_out: str = "1",
    telemetry_count: int = 1,
    privacy_args_mode: str = "valid",
) -> subprocess.CompletedProcess[str]:
    fake_bin = make_fake_docker(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "FAKE_DOCKER_CALLS": str(tmp_path / "docker.calls"),
            "FAKE_RUN_ID": str(tmp_path / "run.id"),
            "FAKE_LOG_POLLS": str(tmp_path / "log.polls"),
            "FAKE_IPC_MODE": ipc_mode,
            "FAKE_NETWORK_MODE": network_mode,
            "FAKE_CONTAINER_IMAGE_ID": image_id,
            "FAKE_EXPECTED_IMAGE_ID": expected_image_id,
            "FAKE_CONTAINER_USER": container_user,
            "FAKE_CONTAINER_ENTRYPOINT": container_entrypoint,
            "FAKE_SCRIPTS_SOURCE": str(scripts_source),
            "FAKE_SCRIPTS_TYPE": scripts_type,
            "FAKE_SCRIPTS_RW": scripts_rw,
            "FAKE_SCRIPTS_COUNT": str(scripts_count),
            "FAKE_CONTAINER_ARGS_VALID": "1" if container_args_valid else "0",
            "FAKE_PRIVACY_ARGS_MODE": privacy_args_mode,
            "FAKE_PGFR_STAGE": pgfr_stage,
            "FAKE_ACCEPT_EULA": accept_eula,
            "FAKE_ACCEPT_EULA_COUNT": str(accept_eula_count),
            "FAKE_TELEMETRY": telemetry_opt_out,
            "FAKE_TELEMETRY_COUNT": str(telemetry_count),
            "FAKE_ROS_DOMAIN_PRESENT": "1" if ros_domain is not None else "0",
            "FAKE_ROS_DOMAIN_ID": ros_domain or "",
            "FAKE_LOG_DELAY_POLLS": str(log_delay_polls),
            "FAKE_READY_LOG_LINES": str(ready_log_lines),
            "FAKE_CRITICAL": "1" if critical else "0",
            "FAKE_SIDECAR_FAIL": "1" if sidecar_fail else "0",
        }
    )
    command = [
        "bash",
        str(SCRIPT),
        "--container",
        "accept-test",
        "--ready-timeout",
        "1",
        "--log-timeout",
        "4",
    ]
    if ros_domain_override is not None:
        command.extend(["--ros-domain-id", ros_domain_override])
    return subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_wrapper_accepts_one_sidecar_run_and_infers_target_domain(
    tmp_path: Path,
) -> None:
    result = invoke_wrapper(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "PGFR_ISAAC_ACCEPTANCE_READY container=accept-test" in result.stdout
    assert "PGFR_ISAAC_ACCEPTANCE_LOGS_OK" in result.stdout
    assert "PGFR_ISAAC_WORKSTATION_ACCEPTANCE_PASS" in result.stdout
    assert "domain=42" in result.stdout

    calls = (tmp_path / "docker.calls").read_text(encoding="utf-8")
    assert calls.count("run --rm --pull never") == 1
    assert "--ipc=container:accept-test" in calls
    assert "--user 1234:1234" in calls


def test_wrapper_rejects_nonshareable_target_before_sidecar(
    tmp_path: Path,
) -> None:
    result = invoke_wrapper(tmp_path, ipc_mode="private")
    assert result.returncode == 2
    assert "must use --ipc=shareable" in result.stderr
    calls = (tmp_path / "docker.calls").read_text(encoding="utf-8")
    assert "\nrun " not in f"\n{calls}"


def test_wrapper_rejects_non_host_network_before_sidecar(tmp_path: Path) -> None:
    result = invoke_wrapper(tmp_path, network_mode="bridge")
    assert result.returncode == 2
    assert "must use --network host" in result.stderr
    calls = (tmp_path / "docker.calls").read_text(encoding="utf-8")
    assert "\nrun " not in f"\n{calls}"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        (
            "image_id",
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "does not use the pinned",
        ),
        ("container_user", "0:0", "must use --user 1234:1234"),
        ("container_entrypoint", "/bin/bash", "must use --entrypoint"),
    ),
)
def test_wrapper_rejects_wrong_target_identity_before_sidecar(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    result = invoke_wrapper(tmp_path, **{field: value})
    assert result.returncode == 2
    assert message in result.stderr
    calls = (tmp_path / "docker.calls").read_text(encoding="utf-8")
    assert "\nrun " not in f"\n{calls}"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("scripts_type", "volume", "read-only bind mount"),
        ("scripts_rw", "true", "read-only bind mount"),
        ("scripts_count", 2, "exactly one /scripts mount"),
        ("container_args_valid", False, "--exec /scripts/pgfr_boot.py"),
        ("pgfr_stage", "/scripts/wrong.usda", "PGFR_STAGE=/scripts/our_factory.usda"),
    ),
)
def test_wrapper_rejects_wrong_payload_contract_before_sidecar(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    result = invoke_wrapper(tmp_path, **{field: value})
    assert result.returncode == 2
    assert message in result.stderr
    calls = (tmp_path / "docker.calls").read_text(encoding="utf-8")
    assert "\nrun " not in f"\n{calls}"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("accept_eula", "N", "exactly ACCEPT_EULA=Y"),
        ("accept_eula_count", 0, "exactly ACCEPT_EULA=Y"),
        ("accept_eula_count", 2, "exactly ACCEPT_EULA=Y"),
        (
            "telemetry_opt_out",
            "0",
            "exactly OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1",
        ),
        (
            "telemetry_count",
            0,
            "exactly OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1",
        ),
        (
            "telemetry_count",
            2,
            "exactly OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1",
        ),
        ("privacy_args_mode", "missing", "default opt-out argument"),
        ("privacy_args_mode", "duplicate", "default opt-out argument"),
        ("privacy_args_mode", "conflicting", "default opt-out argument"),
    ),
)
def test_wrapper_rejects_nondefault_license_or_privacy_profile_before_sidecar(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    result = invoke_wrapper(tmp_path, **{field: value})
    assert result.returncode == 2
    assert message in result.stderr
    calls = (tmp_path / "docker.calls").read_text(encoding="utf-8")
    assert "\nrun " not in f"\n{calls}"


def test_wrapper_rejects_tampered_project_payload_before_sidecar(
    tmp_path: Path,
) -> None:
    payload = tmp_path / "payload"
    shutil.copytree(SOURCE, payload)
    (payload / "pgfr_cell" / "__init__.py").write_text(
        "# acceptance tamper\n",
        encoding="utf-8",
    )

    result = invoke_wrapper(tmp_path, scripts_source=payload)

    assert result.returncode == 2
    assert "mounted pgfr_cell tree differs" in result.stderr
    calls = (tmp_path / "docker.calls").read_text(encoding="utf-8")
    assert "\nrun " not in f"\n{calls}"


def test_wrapper_requires_target_domain_and_rejects_override_mismatch(
    tmp_path: Path,
) -> None:
    missing = invoke_wrapper(tmp_path, ros_domain=None)
    assert missing.returncode == 2
    assert "must define exactly one ROS_DOMAIN_ID" in missing.stderr

    mismatch_dir = tmp_path / "mismatch"
    mismatch_dir.mkdir()
    mismatch = invoke_wrapper(
        mismatch_dir,
        ros_domain="42",
        ros_domain_override="43",
    )
    assert mismatch.returncode == 2
    assert "does not match" in mismatch.stderr
    calls = (mismatch_dir / "docker.calls").read_text(encoding="utf-8")
    assert "\nrun " not in f"\n{calls}"


def test_wrapper_polls_bounded_logs_without_republishing(tmp_path: Path) -> None:
    result = invoke_wrapper(tmp_path, log_delay_polls=2)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "log.polls").read_text(encoding="utf-8").strip() == "3"
    calls = (tmp_path / "docker.calls").read_text(encoding="utf-8")
    assert calls.count("run --rm --pull never") == 1


def test_wrapper_detects_ready_marker_before_large_log_tail_under_pipefail(
    tmp_path: Path,
) -> None:
    result = invoke_wrapper(tmp_path, ready_log_lines=4096)
    assert result.returncode == 0, result.stderr
    assert "PGFR_ISAAC_ACCEPTANCE_READY container=accept-test" in result.stdout
    assert "PGFR_ISAAC_WORKSTATION_ACCEPTANCE_PASS" in result.stdout


def test_wrapper_fails_on_current_run_critical_log_marker(tmp_path: Path) -> None:
    result = invoke_wrapper(tmp_path, critical=True, sidecar_fail=True)
    assert result.returncode == 2
    assert "critical simulator log marker appeared" in result.stderr


def test_wrapper_reports_sidecar_failure_after_scanning_logs(tmp_path: Path) -> None:
    result = invoke_wrapper(tmp_path, sidecar_fail=True)
    assert result.returncode == 2
    assert "ROS acceptance sidecar exited with status 7" in result.stderr
