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
CHECKER = ROOT / "ops" / "check-sim-host.sh"
RUNBOOK = ROOT / "ops" / "ISAAC-SIM-WORKSTATION.md"
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


def test_prepare_atomically_replaces_only_an_empty_mount(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    mount = state_root / "scripts"
    mount.mkdir(parents=True)

    result = invoke(tmp_path, "--prepare", "--root", str(state_root))

    assert result.returncode == 0, result.stderr
    assert (mount / "ic_boot.py").is_file()
    assert stat.S_IMODE(mount.stat().st_mode) == 0o755
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'stage="$(mktemp -d "${MOUNT}.prepare.XXXXXX")"' in source
    assert 'mv -T "$stage" "$MOUNT"' in source
    assert 'mv "$stage/ic_cell"' not in source


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


def test_launch_contract_is_stable_headless_rootless_and_non_destructive() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "nvcr.io/nvidia/isaac-sim:6.0.1" in source
    assert "sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb" in source
    assert 'PRESENTATION_PROFILE="headless"' in source
    assert "run -d --pull never" in source
    assert "--user 1234:1234" in source
    assert "--entrypoint /isaac-sim/runheadless.sh" in source
    assert '-e ISAACSIM_HOST="$WEBRTC_HOST"' in source
    assert '-e ISAACSIM_SIGNAL_PORT="$WEBRTC_SIGNAL_PORT"' in source
    assert '-e ISAACSIM_STREAM_PORT="$WEBRTC_STREAM_PORT"' in source
    assert "docker_args+=(-v)" in source
    assert "--exec /scripts/ic_boot.py" in source
    assert "source=$MOUNT,target=/scripts,readonly" in source
    assert "--ipc=shareable --shm-size 2g" in source
    assert "--ipc=host" not in source
    assert "ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST" in source
    assert "ROS_LOCALHOST_ONLY" not in source
    assert "docker pull " not in source
    assert "docker stop " not in source
    assert "docker rm " not in source
    run_body = source[source.index("run() {") :]
    assert "--rm" not in run_body


def test_check_runs_nvidia_compatibility_checker_at_the_same_digest() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index("run_nvidia_compatibility_check() {")
    check_body = source[start : source.index("\ncheck() {", start)]

    assert "docker run --pull never --rm --network host --gpus all" in check_body
    assert "--user 1234:1234" in check_body
    assert "--entrypoint bash" in check_body
    assert "/isaac-sim/isaac-sim.compatibility_check.sh" in check_body
    assert "--/app/quitAfter=10 --no-window" in check_body
    assert "System checking result: PASSED" in check_body
    assert "IC_ISAAC_NVIDIA_CHECK_OK" in check_body


def test_x11_is_an_explicit_compatibility_profile() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert '--profile PROFILE' in source
    assert 'if [ "$PRESENTATION_PROFILE" = x11 ]; then' in source
    assert "--entrypoint /isaac-sim/isaac-sim.sh" in source
    assert "prepare_xauthority" in source
    assert "--display is valid only with --profile x11" in source
    assert "--webrtc-* options are valid only with --profile headless" in source


def test_profile_and_webrtc_arguments_fail_closed_before_host_access(
    tmp_path: Path,
) -> None:
    cases = (
        (("--prepare", "--profile", "unknown"), "--profile must be headless or x11"),
        (("--prepare", "--display", ":1"), "--display is valid only"),
        (
            ("--prepare", "--profile", "x11", "--webrtc-host", "127.0.0.1"),
            "--webrtc-* options are valid only",
        ),
        (("--prepare", "--webrtc-host", "not-an-ip"), "literal IP address"),
        (("--prepare", "--webrtc-signal-port", "0"), "WebRTC ports"),
        (
            (
                "--prepare",
                "--webrtc-signal-port",
                "49100",
                "--webrtc-stream-port",
                "49100",
            ),
            "ports must differ",
        ),
    )
    for index, (arguments, expected) in enumerate(cases):
        invocation = tmp_path / str(index)
        invocation.mkdir()
        result = invoke(invocation, *arguments)
        assert result.returncode == 2
        assert expected in result.stderr


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
    assert source.count("OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1") == 2
    assert "-e PRIVACY_CONSENT=Y" in source
    run_body = source[source.index("run() {") :]
    opt_out = run_body.index("docker_args+=(-e OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1)")
    image_boundary = run_body.index('"$IMAGE_REF"', opt_out)
    assert opt_out < image_boundary


def test_host_checker_enforces_published_isaac_6_minimums_without_xhost() -> None:
    checker = CHECKER.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")

    for contract in (
        "MIN_CPU_CORES=4",
        "MIN_RAM_BYTES=32000000000",
        "MIN_STORAGE_CAPACITY_BYTES=50000000000",
        "MIN_VRAM_MIB=16384",
        "TESTED_DRIVER_BASELINE=595.58.03",
        "22.04|24.04",
        "--query-gpu=name,memory.total",
        'PROFILE=headless',
        'ip -o address show',
        'for command in ip python3 ss',
    ):
        assert contract in checker
    assert "xhost" not in checker
    assert "xhost +" not in runbook
    assert "x11-xserver-utils" not in runbook
    assert "50 GB total capacity" in runbook
    assert 'df -PB1 "$STATE_ROOT/cache"' in checker
    assert 'awk \'NR==2 {print $2, $4}\'' in checker
    assert "storage_available_bytes=" in checker
    assert '--state-root "$STATE_ROOT"' in SCRIPT.read_text(encoding="utf-8")
    assert "OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1" in runbook
    assert 'if [ "$PROFILE" = x11 ]; then' in checker
    assert "docker nvidia-smi xauth nproc" not in checker
    assert "nvcr.io/nvidia/isaac-sim:6.0.1" in checker
    assert "sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb" in checker


def test_host_checker_drains_multi_gpu_driver_output_under_pipefail(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    commands = {
        "awk": """#!/bin/sh
case "$*" in
  */proc/meminfo*) printf '64000000000\\n'; exit 0 ;;
esac
exec /usr/bin/awk "$@"
""",
        "df": """#!/bin/sh
printf 'Filesystem 1-blocks Used Available Use%% Mounted on\\n'
printf '/dev/fake 100000000000 1 99999999999 1%% /fake\\n'
""",
        "docker": """#!/bin/sh
if [ "$1" = info ] && [ "${2:-}" = --format ]; then
  printf '{"nvidia":{}}\\n'
  exit 0
fi
case "$1" in
  info) exit 0 ;;
  image) [ "$2" = inspect ] && exit 0 ;;
esac
exit 90
""",
        "ip": """#!/bin/sh
printf '1: lo    inet 127.0.0.1/8 scope host lo\\n'
""",
        "nproc": """#!/bin/sh
printf '8\\n'
""",
        "nvidia-smi": """#!/bin/sh
case "$*" in
  *driver_version*)
    trap 'exit 77' 13
    printf '595.78\\n'
    count=0
    while [ "$count" -lt 10000 ]; do
      printf '595.78\\n'
      count=$((count + 1))
    done
    ;;
  *name,memory.total*)
    printf 'NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 97887\\n'
    printf 'NVIDIA RTX 6000 Ada Generation, 49140\\n'
    ;;
  *) exit 90 ;;
esac
""",
        "ss": "#!/bin/sh\nexit 0\n",
    }
    for name, source in commands.items():
        command = fake_bin / name
        command.write_text(source, encoding="utf-8")
        command.chmod(0o755)

    state_root = tmp_path / "state"
    (state_root / "cache").mkdir(parents=True)
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    result = subprocess.run(
        [str(CHECKER), "--state-root", str(state_root)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "IC_SIM_HOST_READY" in result.stdout
    assert "gpu=NVIDIA RTX PRO 6000 Blackwell Workstation Edition" in result.stdout
    assert "head -n 1" not in CHECKER.read_text(encoding="utf-8")


def test_readiness_rejects_errors_before_accepting_ready_marker() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    wait_body = source[source.index("wait_for_cell() {") : source.index("run() {")]
    availability_body = source[
        source.index("assert_streaming_ports_available() {") : source.index(
            "wait_for_cell() {"
        )
    ]
    run_body = source[source.index("run() {") :]
    first_error_check = wait_body.index("IC_CELL_BOOT_ERR|IC_STEP_ERR")
    ready_check = wait_body.index("IC_CELL_UP markers=all")
    assert first_error_check < ready_check
    assert "Isaac Sim Full Streaming App is loaded." in wait_body
    assert "cell_ready && $stream_ready" in wait_body
    assert 'ss -H -ltn "sport = :$WEBRTC_SIGNAL_PORT"' in source
    assert "signaling TCP port" in source
    assert 'ss -H -lun "sport = :$WEBRTC_STREAM_PORT"' in availability_body
    assert "already in use" in availability_body
    assert run_body.index("assert_streaming_ports_available") < run_body.index(
        "docker_args=("
    )
    assert 'ss -H -lun' not in wait_body
    assert "post-ready stability window" in wait_body
    assert wait_body.count('docker logs "$CONTAINER_NAME" 2>&1 || true') == 2
    assert "tail -n 2000" not in wait_body


def test_readiness_finds_critical_marker_before_more_than_two_thousand_lines(
    tmp_path: Path,
) -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    wait_body = source[source.index("wait_for_cell() {") : source.index("run() {")]
    harness = tmp_path / "wait-for-cell.sh"
    harness.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "PRESENTATION_PROFILE=x11\n"
        "CONTAINER_NAME=ic-readiness-test\n"
        "READY_TIMEOUT=5\n"
        "fail() { printf 'FAIL: %s\\n' \"$*\" >&2; exit 2; }\n"
        "verify_streaming_listener() { :; }\n"
        f"{wait_body}\n"
        "wait_for_cell\n",
        encoding="utf-8",
    )
    harness.chmod(0o755)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        """#!/bin/sh
if [ "$1 $2" = "logs --tail" ]; then
  printf 'diagnostic tail intentionally omits the early marker\\n'
  exit 0
fi
if [ "$1" = logs ]; then
  printf 'IC_CELL_BOOT_ERR: early deterministic failure\\n'
  line=0
  while [ "$line" -lt 2100 ]; do
    printf 'benign noisy Kit startup line %s\\n' "$line"
    line=$((line + 1))
  done
  printf 'IC_CELL_UP markers=all\\n'
  printf 'Isaac Sim Full Streaming App is loaded.\\n'
  exit 0
fi
if [ "$1 $2" = "container inspect" ]; then
  printf 'running\\n'
  exit 0
fi
exit 90
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    sleep = fake_bin / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    sleep.chmod(0o755)

    result = subprocess.run(
        [str(harness)],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "physics/bootstrap error" in result.stderr
    assert "IC_ISAAC_BASELINE_READY" not in result.stdout


def test_runbook_joins_bounded_ipc_with_matching_fastdds_owner() -> None:
    runbook = (ROOT / "ops" / "ISAAC-SIM-WORKSTATION.md").read_text(
        encoding="utf-8"
    )
    assert "--ipc=container:ic-isaac-sim-baseline" in runbook
    assert "--user 1234:1234" in runbook
    assert "-e HOME=/tmp" in runbook
    assert "--ipc=host" not in runbook
    assert "DISPLAY=:1 ops/isaac-sim-workstation.sh" not in runbook
    assert 'ops/isaac-sim-workstation.sh --run --accept-eula' in runbook
    assert '--run --profile x11 --accept-eula' in runbook
    assert 'nlist "${DISPLAY:?run from the local X11 desktop}"' in runbook
    assert "49100/tcp" in runbook
    assert "47998/udp" in runbook
    assert runbook.index("sudo ufw allow in") < runbook.index(
        "Explicit local-X11 compatibility alternative"
    )
    assert "five-part local asset pack" in runbook
    assert "92149a1f50a21c0f04cca6507ab00653" in runbook
    assert "local/offline" in runbook
    assert "has not been qualified" in runbook
    assert (
        "docker pull --platform linux/amd64 \\\n"
        "  docker.io/library/ros:jazzy-ros-base-noble@sha256:"
        "2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4"
    ) in runbook


def test_run_requires_explicit_eula_acceptance(tmp_path: Path) -> None:
    result = invoke(tmp_path, "--run", "--root", str(tmp_path / "state"), display=":1")
    assert result.returncode == 2
    assert "--run requires --accept-eula" in result.stderr

    check_invoke = tmp_path / "check"
    check_invoke.mkdir()
    check = invoke(check_invoke, "--check", "--root", str(tmp_path / "state"))
    assert check.returncode == 2
    assert "--check requires --accept-eula" in check.stderr

    prepare_invoke = tmp_path / "prepare"
    prepare_invoke.mkdir()
    prepare = invoke(
        prepare_invoke,
        "--prepare",
        "--accept-eula",
        "--root",
        str(tmp_path / "state"),
    )
    assert prepare.returncode == 2
    assert "valid only with --check or --run" in prepare.stderr
