# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free tests for the scripted Isaac Sim workstation helper."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "isaac-sim-workstation.sh"
SOURCE = ROOT / "reference" / "policy-gated-factory-robot-orchestrator-reference" / "isaac-cell"


def make_fake_docker(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        """#!/bin/sh
case "$1 $2" in
  "info ") exit 0 ;;
  "container inspect")
    if [ "${FAKE_CONTAINER_EXISTS:-0}" = 1 ]; then
      printf 'running\\n'
      exit 0
    fi
    exit 1
    ;;
  "ps -q") exit 0 ;;
esac
printf 'unexpected fake docker invocation: %s\\n' "$*" >&2
exit 90
""",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    return fake_bin


def invoke(
    tmp_path: Path,
    *arguments: str,
    container_exists: bool = False,
    display: str = "remote.example:10",
) -> subprocess.CompletedProcess[str]:
    fake_bin = make_fake_docker(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(tmp_path / "home"),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "DISPLAY": display,
            "FAKE_CONTAINER_EXISTS": "1" if container_exists else "0",
        }
    )
    return subprocess.run(
        [str(SCRIPT), *arguments],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_prepare_stages_exact_baseline_and_is_idempotent(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    first = invoke(tmp_path, "--prepare", "--root", str(state_root))
    assert first.returncode == 0, first.stderr
    assert "unchanged=false" in first.stdout
    mount = state_root / "scripts"
    assert (mount / "ic_boot.py").read_bytes() == (SOURCE / "ic_boot.py").read_bytes()
    assert (mount / "our_factory.usda").read_bytes() == (
        SOURCE / "our_factory.usda"
    ).read_bytes()

    expected_files = sorted(
        path.relative_to(SOURCE / "ic_cell")
        for path in (SOURCE / "ic_cell").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    installed_files = sorted(
        path.relative_to(mount / "ic_cell")
        for path in (mount / "ic_cell").rglob("*")
        if path.is_file()
    )
    assert installed_files == expected_files
    for relative in expected_files:
        assert (mount / "ic_cell" / relative).read_bytes() == (
            SOURCE / "ic_cell" / relative
        ).read_bytes()

    # A hostile remote DISPLAY is irrelevant to non-launching preparation.
    second_tmp = tmp_path / "second-invoke"
    second_tmp.mkdir()
    second = invoke(second_tmp, "--prepare", "--root", str(state_root))
    assert second.returncode == 0, second.stderr
    assert "unchanged=true" in second.stdout


def test_default_state_root_is_external_to_a_documented_checkout(tmp_path: Path) -> None:
    result = invoke(tmp_path, "--prepare")
    assert result.returncode == 0, result.stderr
    expected = (
        tmp_path / "home" / ".local" / "share" / "policy-gated-factory-robot-orchestrator-reference" / "isaac-sim"
    )
    assert f"state={expected}" in result.stdout
    assert (expected / "scripts" / "ic_boot.py").is_file()


def test_prepare_rejects_generated_state_or_mount_below_checkout(
    tmp_path: Path,
) -> None:
    state_result = invoke(
        tmp_path,
        "--prepare",
        "--root",
        str(ROOT / ".generated-state-for-test"),
    )
    assert state_result.returncode == 2
    assert "unsafe state root" in state_result.stderr

    mount_invoke = tmp_path / "mount-invoke"
    mount_invoke.mkdir()
    mount_result = invoke(
        mount_invoke,
        "--prepare",
        "--root",
        str(tmp_path / "state"),
        "--mount",
        str(ROOT / ".generated-mount-for-test"),
    )
    assert mount_result.returncode == 2
    assert "unsafe scripts mount" in mount_result.stderr


def test_prepare_refuses_tampered_bundle_without_overwrite(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    first = invoke(tmp_path, "--prepare", "--root", str(state_root))
    assert first.returncode == 0, first.stderr
    boot = state_root / "scripts" / "ic_boot.py"
    boot.write_text("tampered\\n", encoding="utf-8")

    second_tmp = tmp_path / "second-invoke"
    second_tmp.mkdir()
    second = invoke(second_tmp, "--prepare", "--root", str(state_root))
    assert second.returncode == 2
    assert "differs from this checkout" in second.stderr
    assert boot.read_text(encoding="utf-8") == "tampered\\n"


def test_prepare_refuses_existing_container_before_writing(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    result = invoke(
        tmp_path,
        "--prepare",
        "--root",
        str(state_root),
        container_exists=True,
    )
    assert result.returncode == 2
    assert "never replaces or removes containers" in result.stderr
    assert not state_root.exists()


def test_launch_contract_is_immutable_local_and_non_destructive() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "nvcr.io/nvidia/isaac-sim:6.0.0-dev2" in source
    assert "sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9" in source
    assert "run -d --pull never" in source
    assert "--exec /scripts/ic_boot.py" in source
    assert "source=$MOUNT,target=/scripts,readonly" in source
    assert "--ipc=shareable --shm-size 2g" in source
    assert "--ipc=host" not in source
    assert "ROS_LOCALHOST_ONLY=1" in source
    assert "ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST" in source
    assert "docker pull " not in source
    assert "docker stop " not in source
    assert "docker rm " not in source
    assert "--rm" not in source


def test_launch_forces_privacy_off_unless_operator_opts_in() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    privacy_block = source[source.index("if ! $PRIVACY_CONSENT; then") :]
    for setting in (
        "--/telemetry/enableAnonymousAppName=false",
        "--/telemetry/enableAnonymousData=false",
        "--/telemetry/useOpenEndpoint=false",
        "--/privacy/usage=false",
        "--/privacy/performance=false",
        "--/privacy/personalization=false",
        "--/crashreporter/enabled=false",
    ):
        assert setting in privacy_block
    assert "-e PRIVACY_CONSENT=Y" in source


def test_readiness_rejects_errors_before_accepting_ready_marker() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    wait_body = source[source.index("wait_for_cell() {") : source.index("run() {")]
    first_error_check = wait_body.index("IC_CELL_BOOT_ERR|IC_STEP_ERR")
    ready_check = wait_body.index("IC_CELL_UP markers=all")
    assert first_error_check < ready_check
    assert "post-ready stability window" in wait_body


def test_runbook_joins_bounded_ipc_with_matching_fastdds_owner() -> None:
    runbook = (ROOT / "ops" / "ISAAC-SIM-WORKSTATION.md").read_text(
        encoding="utf-8"
    )
    assert "--ipc=container:ic-isaac-sim-baseline" in runbook
    assert "--user 1234:1234" in runbook
    assert "-e HOME=/tmp" in runbook
    assert "--ipc=host" not in runbook
    assert "DISPLAY=:1 ops/isaac-sim-workstation.sh" not in runbook
    assert ': "${DISPLAY:?run from the local X11 desktop}"' in runbook
    assert runbook.index("sudo ufw allow in") < runbook.index(
        "systemctl is-active vncserver-x11-serviced.service"
    )


def test_run_requires_explicit_eula_acceptance(tmp_path: Path) -> None:
    result = invoke(tmp_path, "--run", "--root", str(tmp_path / "state"), display=":1")
    assert result.returncode == 2
    assert "--run requires --accept-eula" in result.stderr
