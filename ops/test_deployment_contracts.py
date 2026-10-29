# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free checks for the public clean-machine deployment contract."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
import time
import tomllib

import yaml

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_openclaw_template_and_ci_match_the_pinned_runtime_schema() -> None:
    template = json.loads(text("ops/openclaw.template.json"))
    assert template["agents"]["ownership"] == "explicit"
    assert "list" not in template["agents"]
    assert set(template["agents"]["entries"]) == {"main", "pgfr-console"}
    console_tools = template["agents"]["entries"]["pgfr-console"]["tools"]
    assert console_tools["loopDetection"] == {"enabled": True}

    workflow = text(".github/workflows/ci.yml")
    assert "npm ci" in workflow
    assert "npm ls --all" in workflow
    assert "npm audit --audit-level=high" in workflow
    assert workflow.count("./node_modules/.bin/openclaw config validate") == 2
    assert 'OPENCLAW_CONFIG_PATH="$PWD/ops/openclaw.template.json"' in workflow
    assert 'OPENCLAW_CONFIG_PATH="$rendered_config"' in workflow


def test_npm_lock_identities_exactly_match_third_party_notices() -> None:
    lock = json.loads(text("package-lock.json"))
    lock_identities = {
        (path.rsplit("node_modules/", 1)[1], package["version"])
        for path, package in lock["packages"].items()
        if path
    }
    notice = text("THIRD-PARTY-NOTICES.md")
    notice_rows = re.findall(
        r"^\| npm \| \[([^]]+)]\([^)]*\) \| <code>([^<]+)</code> \|",
        notice,
        flags=re.MULTILINE,
    )
    notice_identities = set(notice_rows)

    assert len(notice_rows) == len(notice_identities)
    assert notice_identities == lock_identities
    heading = re.search(r"^## npm dependency inventory \((\d+) identities\)$", notice, re.MULTILINE)
    assert heading is not None
    assert int(heading.group(1)) == len(lock_identities)


def test_python_lock_identities_exactly_match_third_party_notices() -> None:
    manifest = yaml.safe_load(text("deploy/reproducible-demo.yaml"))
    lock_paths = {
        name: path
        for name, path in manifest["dependency_locks"].items()
        if name != "node"
    }
    lock_identities: set[tuple[str, str]] = set()
    for path in lock_paths.values():
        lock = tomllib.loads(text(path))
        lock_identities.update(
            (package["name"], package["version"])
            for package in lock["package"]
            if "editable" not in package.get("source", {})
        )

    notice = text("THIRD-PARTY-NOTICES.md")
    notice_rows = re.findall(
        r"^\| python \| \[([^]]+)]\([^)]*\) \| <code>([^<]+)</code> \|",
        notice,
        flags=re.MULTILINE,
    )
    notice_identities = set(notice_rows)
    assert len(notice_rows) == len(notice_identities)
    assert notice_identities == lock_identities
    heading = re.search(
        r"^## Python dependency inventory \((\d+) external identities\)$",
        notice,
        re.MULTILINE,
    )
    assert heading is not None
    assert int(heading.group(1)) == len(lock_identities)



def test_training_dependencies_are_disclosed_and_ci_uses_the_declared_python() -> None:
    manifest = json.loads(text("reference/groot/security/manifest-training.json"))["training_project"]
    notice = text("THIRD-PARTY-NOTICES.md")
    rows = re.findall(
        r"^\| (python|training-python) \| \[([^]]+)]\([^)]*\) \| <code>([^<]+)</code> \|",
        notice, flags=re.MULTILINE,
    )
    identities = {(name, version) for _, name, version in rows}
    assert len(rows) == len(identities), "Training supplement must not duplicate the main inventory"
    assert set(manifest["installed_versions"].items()) <= identities
    training_rows = [row for row in rows if row[0] == "training-python"]
    heading = re.search(
        r"^## Workstation training dependency supplement \((\d+) external identities\)$",
        notice, re.MULTILINE,
    )
    assert heading is not None
    assert int(heading.group(1)) == len(training_rows)
    workflow = yaml.safe_load(text(".github/workflows/ci.yml"))
    profiles = workflow["jobs"]["model-dependency-security"]["strategy"]["matrix"]["include"]
    training_profile, = [profile for profile in profiles if profile["profile"] == "training"]
    assert training_profile["python"] == manifest["python_version"]

def test_model_security_manifests_match_installer_locks_and_assets() -> None:
    security = ROOT / "reference/groot/security"
    lock = tomllib.loads(text("reference/groot/thor/uv.lock"))
    packages = {package["name"]: package for package in lock["package"]}
    for filename in ("manifest.json", "manifest-training.json"):
        manifest = json.loads((security / filename).read_text())
        assets = []
        for entry in manifest["packages"]:
            assets.extend((entry["patch"], entry["notice"]))
            if filename == "manifest.json":
                package = packages[entry["name"]]
                assert package["version"] == entry["version"]
                assert package["source"] == {"path": "wheels/security/" + entry["wheel"]["filename"]}
                assert package["wheels"] == [{
                    "filename": entry["wheel"]["filename"],
                    "hash": "sha256:" + entry["wheel"]["sha256"],
                }]
        if "training_project" in manifest:
            assets.append(manifest["training_project"]["patch"])
        for asset in assets:
            assert hashlib.sha256((security / asset["path"]).read_bytes()).hexdigest() == asset["sha256"]


def test_canonical_guide_installs_before_starting() -> None:
    guide = text("docs/REPRODUCIBLE-DEMO.md")
    runtime = guide.index("ops/prepare-groot-runtime.sh --install")
    bootstrap = guide.index("ops/bootstrap-brain.sh --check")
    fetch = guide.index("ops/fetch-groot-models.sh")
    prepare_sim = guide.index("ops/isaac-sim-workstation.sh --prepare")
    check_sim = guide.index(
        'ops/check-sim-host.sh --profile x11 --mount "$PGFR_GROOT_ISAAC_MOUNT"'
    )
    install_cell = guide.index("ops/install-groot-cell.sh")
    launch = guide.index("ops/launch-groot-isaac.sh")
    assert runtime < bootstrap < fetch < prepare_sim < check_sim
    assert check_sim < install_cell < launch


def test_clone_paths_use_the_github_repository_name() -> None:
    guide = text("docs/REPRODUCIBLE-DEMO.md")
    checkout = "~/Policy-Gated-Factory-Robot-Orchestrator-Reference"
    assert guide.count(f"cd {checkout}") == 2
    assert "git clone " + "https://github.com/NVIDIA-AI-IOT/" in guide

    training_guide = text(
        "reference/groot/training/README.md"
    )
    assert "/path/to/Policy-Gated-Factory-Robot-Orchestrator-Reference" in training_guide

    mcp_guide = text("servers/policy-gated-factory-robot-orchestrator-reference-mcp/README.md")
    assert f"{checkout}/servers/policy-gated-factory-robot-orchestrator-reference-mcp/.venv/bin/pgfr-mcp" in mcp_guide


def test_container_pins_match_manifest_and_launchers() -> None:
    manifest = yaml.safe_load(text("deploy/reproducible-demo.yaml"))
    guide = text("docs/REPRODUCIBLE-DEMO.md")
    runtime = manifest["runtime"]
    isaac = manifest["containers"]["isaac_sim"]
    scripted = manifest["containers"]["isaac_sim_scripted_baseline"]
    ros_sidecar = manifest["containers"]["ros_sidecar"]
    thor_cuda = manifest["containers"]["thor_cuda_build"]
    thor_torchcodec = manifest["runtime_artifacts"]["thor_torchcodec"]
    vlm = manifest["containers"]["perception_vllm"]
    isaac_launcher = text("ops/launch-groot-isaac.sh")
    scripted_launcher = text("ops/isaac-sim-workstation.sh")
    scripted_runbook = text("ops/ISAAC-SIM-WORKSTATION.md")
    thor_installer = text(
        "reference/groot/thor/install_deps.sh"
    )
    thor_lock = text(
        "reference/groot/thor/uv.lock"
    )
    notices = text("THIRD-PARTY-NOTICES.md")
    vlm_launcher = text("ops/launch-perception-vlm.sh")
    vlm_env = text("ops/systemd/vlm.env")

    assert isaac["tag"] in isaac_launcher
    assert isaac["digest"] in isaac_launcher
    assert '"$IMAGE_REF"' in isaac_launcher
    assert "6.0.0-dev2" in isaac["tag"]
    for value in (scripted["tag"], scripted["digest"]):
        assert value in scripted_launcher
        assert value in scripted_runbook
        assert value in notices
    assert scripted["platform"] == "linux/amd64"
    assert scripted["profile"] == "headless_webrtc"
    assert (
        scripted["qualification_scope"]
        == "scripted_baseline_without_webrtc_client_connection"
    )
    assert scripted["qualified_on"].isoformat() == "2026-09-09"
    assert scripted["qualification_run_id"] == "d70ed0c3940f"
    assert scripted["historical_qualification_run_id"] == "953020d69491"
    qualification_record = text("docs/VALIDATION.md")
    assert scripted["qualified_on"].isoformat() in qualification_record
    for run_key in ("qualification_run_id", "historical_qualification_run_id"):
        assert f"`{scripted[run_key]}`" in qualification_record
    for value in (ros_sidecar["tag"], ros_sidecar["digest"]):
        assert value in scripted_runbook
        assert value in notices
    assert ros_sidecar["platform"] == "linux/amd64"
    assert thor_cuda["purpose"] == "upstream_gpu_smoke_check"
    thor_smoke_ref = f'docker.io/{thor_cuda["tag"]}@{thor_cuda["digest"]}'
    assert (
        f'docker run --rm --platform {thor_cuda["platform"]} '
        "--runtime=nvidia --gpus all"
    ) in guide
    assert thor_smoke_ref in guide
    thor_smoke = guide[guide.index(thor_smoke_ref) :]
    assert "nvidia-smi -L" in thor_smoke.split("```", 1)[0]
    assert thor_cuda["digest"] in notices
    assert thor_cuda["platform_digest"] in notices
    for value in (
        thor_torchcodec["filename"],
        thor_torchcodec["sha256"],
        thor_torchcodec["source_revision"],
    ):
        assert value in notices
    assert thor_torchcodec["filename"] in thor_installer
    assert thor_torchcodec["sha256"] in thor_installer
    assert 'name = "torchcodec"' not in thor_lock
    assert "validated_on: 2026-08-08" in text("deploy/reproducible-demo.yaml")
    for value in (vlm["tag"], vlm["digest"], vlm["model"], vlm["revision"]):
        assert value in vlm_launcher
        assert value in vlm_env
    assert '"$IMAGE_REF"' in vlm_launcher
    assert 'IMAGE_REF="$IMAGE@$DIGEST"' not in vlm_launcher
    assert 'IMAGE_REPOSITORY="${IMAGE_REPOSITORY%:*}"' in vlm_launcher
    assert f'{isaac["tag"]}@{isaac["digest"]}' in guide
    assert f'{vlm["tag"]}@{vlm["digest"]}' in guide
    assert runtime["python"] == "3.12.3"
    assert runtime["node"] == "22.22.3"
    assert runtime["uv"] == "0.11.32"
    assert runtime["huggingface_hub"] == "0.36.2"


def test_brain_host_prereqs_require_all_installable_cuda_candidates() -> None:
    script = text("ops/install-brain-host-prereqs.sh")
    expected = (
        "cuda-cupti-13-0",
        "libcufft-13-0",
        "libcurand-13-0",
        "libcusparse-13-0",
        "libnvjitlink-13-0",
    )
    package_block = script.split("CUDA_RUNTIME_PACKAGES=(", 1)[1].split("\n)", 1)[0]
    configured = tuple(
        line.strip()
        for line in package_block.splitlines()
        if line.strip()
    )
    assert configured == expected
    assert 'LC_ALL=C apt-cache policy "$package"' in script
    assert '[ -n "$candidate" ] && [ "$candidate" != "(none)" ]' in script
    assert "apt-cache show cuda-cupti-13-0" not in script

    repo_check = script.index("if ! cuda_runtime_candidates_available;")
    refresh = script.index("$SUDO apt-get update", repo_check)
    recheck = script.index("MISSING_CUDA_RUNTIME_PACKAGES=()", refresh)
    install = script.index('"${CUDA_RUNTIME_PACKAGES[@]}"', recheck)
    assert repo_check < refresh < recheck < install
    assert "ca-certificates curl git-lfs gnupg" in script
    assert "git lfs version" in script


def test_host_and_thor_installers_share_the_verified_uv_pin() -> None:
    host = text("ops/install-brain-host-prereqs.sh")
    thor = text(
        "reference/groot/thor/install_deps.sh"
    )

    for setting in (
        'UV_VERSION="0.11.32"',
        'UV_INSTALLER_SHA256="43aff33a967fe40e8c17949d8c85c65bc43f3b5c94742393c957f56ab5ba80f4"',
    ):
        assert setting in host
        assert setting in thor
    assert 'https://astral.sh/uv/$UV_VERSION/install.sh' in host
    assert 'https://astral.sh/uv/$UV_VERSION/install.sh' in thor


def test_ci_checks_thor_lock_without_syncing_the_arch_specific_environment() -> None:
    workflow = text(".github/workflows/ci.yml")
    command = (
        "uv lock --check --project "
        "reference/groot/thor"
    )
    assert workflow.count(command) == 1


def test_ci_runs_hardware_free_groot_deployment_contracts() -> None:
    workflow = text(".github/workflows/ci.yml")
    for test_file in (
        "test_cont24_v36_runtime.py",
        "test_native_droid_relay_batch2.py",
        "test_two_host_bridge.py",
    ):
        assert workflow.count(test_file) == 1


def test_groot_runtime_prepare_reports_missing_flock_before_mutation(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "dirname").symlink_to("/usr/bin/dirname")

    result = subprocess.run(
        ["/bin/bash", str(ROOT / "ops" / "prepare-groot-runtime.sh")],
        cwd=ROOT,
        env={"HOME": str(tmp_path / "home"), "PATH": str(fake_bin)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "missing command: flock" in result.stderr
    assert not (tmp_path / "home" / "groot_shadow").exists()


def test_groot_runtime_prepare_serializes_concurrent_first_publication(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text(
        """#!/bin/sh
if [ "$1 $2" = "lfs version" ]; then
  exit 0
fi
if [ "$1" = clone ]; then
  destination="$4"
  mkdir -p "$destination/gr00t" "$destination/scripts/deployment/thor/wheels"
  printf 'materialized wheel\\n' > "$destination/scripts/deployment/thor/wheels/torchcodec-0.10.0a0-cp312-cp312-linux_aarch64.whl"
  printf 'obsolete upstream recipe\\n' > "$destination/scripts/deployment/thor/Dockerfile"
  printf 'clone\\n' >> "$FAKE_CLONE_CALLS"
  : > "$FAKE_CLONE_STARTED"
  sleep 1
  exit 0
fi
if [ "$1" = -C ] && [ "$3" = diff ]; then
  printf 'fake patch bytes\\n'
fi
exit 0
""",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    fake_sha = fake_bin / "sha256sum"
    fake_sha.write_text(
        """#!/bin/sh
while IFS= read -r _line; do :; done
if [ "${1:-}" = --check ]; then
  exit 0
fi
printf '51ca0f19912b264a1e5091e94e45ea8bb0d719a0fefacb9fb1e7b44bef1e98f5  -\\n'
""",
        encoding="utf-8",
    )
    fake_sha.chmod(0o755)
    fake_python = fake_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text(
        "#!/bin/sh\n"
        'if [ "$2" = list-units ]; then exit 0; fi\n'
        "exit 1\n",
        encoding="utf-8",
    )
    fake_systemctl.chmod(0o755)

    destination = tmp_path / "published" / "Isaac-GR00T"
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "HOME": str(tmp_path / "home"),
        "PGFR_GROOT_SOURCE_ROOT": str(destination),
        "FAKE_CLONE_CALLS": str(tmp_path / "clone.calls"),
        "FAKE_CLONE_STARTED": str(tmp_path / "clone.started"),
    }
    command = [str(ROOT / "ops" / "prepare-groot-runtime.sh"), "--source-only"]
    first = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 5
    while not (tmp_path / "clone.started").exists():
        assert first.poll() is None
        assert time.monotonic() < deadline
        time.sleep(0.02)

    second = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    first_stdout, first_stderr = first.communicate(timeout=10)

    assert first.returncode == 0, first_stderr
    assert "PGFR_GROOT_RUNTIME_PREPARED" in first_stdout
    assert second.returncode == 2
    assert "another preparation owns the destination lock" in second.stderr
    assert (tmp_path / "clone.calls").read_text(encoding="utf-8").splitlines() == [
        "clone"
    ]
    assert (destination / "scripts" / "deployment" / "thor" / "uv.lock").is_file()
    assert not (destination / "scripts" / "deployment" / "thor" / "Dockerfile").exists()
    security = destination / "scripts" / "deployment" / "security"
    assert (security / "manifest.json").is_file()
    assert (security / "build_security_wheels.py").is_file()
    assert not any(destination.glob(".groot-source.*"))


def test_doctors_and_units_use_immutable_or_user_owned_contracts() -> None:
    sim_doctor = text("ops/check-sim-host.sh")
    vlm_launcher = text("ops/launch-perception-vlm.sh")
    vlm_unit = text("ops/systemd/pgfr-perception-vlm.service")
    assert 'docker image inspect "$IMAGE_REF"' in sim_doctor
    assert 'docker image inspect "$IMAGE"' not in sim_doctor
    assert "PGFR_VLM_READY_TIMEOUT_S must be an integer" in vlm_launcher
    assert "--runtime=nvidia --gpus all" in vlm_launcher
    assert "VLM container exited before readiness" in vlm_launcher
    assert "docker.service" not in vlm_unit


def test_write_capable_templates_are_loopback_first() -> None:
    chat = text("ops/systemd/chat.env")
    workflows = text("ops/systemd/workflows.env")
    console = text("ops/systemd/console.env")
    assert "PGFR_CHAT_HOST=127.0.0.1" in chat
    assert "PGFR_WORKFLOWS_HOST=127.0.0.1" in workflows
    assert "PGFR_CONSOLE_HOST=127.0.0.1" in console
    assert "PGFR_CHAT_TOKEN=" in chat
    assert "PGFR_WORKFLOWS_TOKEN=" in workflows
    assert "PGFR_CHAT_URL=http://127.0.0.1:8620" in console
    assert "\nPGFR_CHAT_PUBLIC_URL=\n" in console


def test_legacy_runtime_guard_is_centralized_and_fail_closed(tmp_path: Path) -> None:
    guard_path = ROOT / "ops" / "pgfr-legacy-guard.sh"
    guard = guard_path.read_text(encoding="utf-8")
    unit_match = re.search(
        r"PGFR_LEGACY_UNIT_PATTERNS=\(\n\s+'([^']+)'", guard
    )
    container_match = re.search(
        r"PGFR_LEGACY_CONTAINER_PATTERNS=\(\n\s+'([^']+)'", guard
    )
    assert unit_match is not None
    assert container_match is not None
    legacy_unit = unit_match.group(1).replace("*", "seam")
    legacy_container = container_match.group(1).replace("*", "simulator")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text(
        "#!/bin/sh\n"
        'printf "%s loaded active running migration-test\\n" "$FAKE_ACTIVE_UNIT"\n',
        encoding="utf-8",
    )
    fake_systemctl.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$FAKE_ACTIVE_CONTAINER"\n',
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_ACTIVE_UNIT": legacy_unit,
        "FAKE_ACTIVE_CONTAINER": legacy_container,
    }

    for function, expected in (
        ("pgfr_refuse_active_legacy_units", legacy_unit),
        ("pgfr_refuse_active_legacy_containers", legacy_container),
    ):
        result = subprocess.run(
            ["/bin/bash", "-c", f'. "$1"; {function}', "guard-test", str(guard_path)],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2
        assert expected in result.stderr

    prefix_lower = "".join(("i", "c"))
    prefix_upper = prefix_lower.upper()
    legacy_pattern = re.compile(
        rf"(?<![A-Za-z0-9_])(?:{prefix_upper}_|{prefix_lower}_|"
        rf"{prefix_upper}-|{prefix_lower}-|/{prefix_lower}(?:/|\b)|"
        rf"{prefix_upper}\b|{prefix_lower}\b|X-{prefix_upper})"
    )
    for root_name in (".github", "ops", "deploy"):
        for candidate in (ROOT / root_name).rglob("*"):
            if not candidate.is_file() or candidate == guard_path:
                continue
            try:
                candidate_text = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            assert legacy_pattern.search(candidate_text) is None, candidate


def test_mutating_deployment_tools_call_the_legacy_guard() -> None:
    unit_guarded = (
        "ops/bootstrap-brain.sh",
        "ops/install-brain-host-prereqs.sh",
        "ops/prepare-groot-runtime.sh",
        "ops/fetch-groot-models.sh",
        "ops/install-groot-thor-shared-profiles.sh",
        "ops/install-groot-two-host-bridge.sh",
        "ops/launch-groot-isaac.sh",
        "ops/thor-deploy.sh",
        "ops/gw.sh",
    )
    container_guarded = (
        "ops/bootstrap-brain.sh",
        "ops/install-brain-host-prereqs.sh",
        "ops/install-groot-cell.sh",
        "ops/isaac-sim-workstation.sh",
        "ops/launch-groot-isaac.sh",
        "ops/launch-perception-vlm.sh",
    )
    for relative in set(unit_guarded + container_guarded):
        assert "pgfr-legacy-guard.sh" in text(relative)
    for relative in unit_guarded:
        assert "pgfr_refuse_active_legacy_units" in text(relative)
    for relative in container_guarded:
        assert "pgfr_refuse_active_legacy_containers" in text(relative)


def test_floor_bootstrap_selects_locked_ros_image_dependencies(tmp_path: Path) -> None:
    """Exercise floor setup without invoking uv, ROS, or a host package manager."""
    project = tomllib.loads(text("pgfr-spine/pyproject.toml"))
    assert set(project["project"]["optional-dependencies"]["ros"]) == {
        "numpy==1.26.4", "Pillow==13.0.0"
    }
    lock = tomllib.loads(text("pgfr-spine/uv.lock"))
    packages = {package["name"]: package for package in lock["package"]}
    assert packages["numpy"]["version"] == "1.26.4"
    assert packages["pillow"]["version"] == "13.0.0"
    spine = packages["policy-gated-factory-robot-orchestrator-reference"]
    assert {entry["name"] for entry in spine["optional-dependencies"]["ros"]} == {
        "numpy", "pillow"
    }

    repo = tmp_path / "repo"
    floor = repo / "pgfr-spine"
    floor.mkdir(parents=True)
    log = tmp_path / "uv-calls.jsonl"
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "with open(os.environ['PGFR_TEST_UV_LOG'], 'a') as stream:\n"
        "    stream.write(json.dumps({'argv': sys.argv[1:], 'venv': os.environ.get('VIRTUAL_ENV')}) + '\\n')\n"
        "if sys.argv[1] == 'venv':\n"
        "    env = pathlib.Path(sys.argv[-1])\n"
        "    env.mkdir()\n"
        "    (env / 'pyvenv.cfg').write_text('include-system-site-packages = true\\n')\n"
    )
    fake_uv.chmod(0o755)
    source = text("ops/bootstrap-brain.sh")
    function = source[source.index("sync_floor_project() {") : source.index("\nrender() {")]
    # The second call also checks the existing ROS-enabled environment path.
    subprocess.run(
        ["/bin/bash", "-c", "set -euo pipefail\n" + function
         + "\nsync_floor_project\nsync_floor_project\n"],
        env={"PATH": "/usr/bin:/bin", "REPO": str(repo), "UV_BIN": str(fake_uv),
             "PGFR_TEST_UV_LOG": str(log)},
        check=True, text=True, capture_output=True,
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls[0]["argv"] == [
        "venv", "--python", "python3.12", "--system-site-packages", str(floor / ".venv")
    ]
    assert calls[1:] == [{
        "argv": ["sync", "--active", "--frozen", "--extra", "ros", "--project", str(floor)],
        "venv": str(floor / ".venv"),
    }] * 2


def test_brain_bootstrap_seeds_one_shared_openclaw_gateway_token() -> None:
    bootstrap = text("ops/bootstrap-brain.sh")
    chat_backend = text("servers/pgfr-chat/src/pgfr_chat/backends.py")
    gateway_unit = text("ops/systemd/pgfr-openclaw.service")
    chat_unit = text("ops/systemd/pgfr-chat.service")
    secrets_file = "EnvironmentFile=-__PGFR_HOME__/.openclaw/secrets.env"
    assert "OPENCLAW_GATEWAY_TOKEN" in bootstrap
    assert "secrets.token_hex(32)" in bootstrap
    assert 'chmod 0600 "$secrets_file"' in bootstrap
    assert secrets_file in gateway_unit
    assert secrets_file in chat_unit
    assert 'os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")' in chat_backend


def test_brain_template_install_preserves_operator_configuration(tmp_path: Path) -> None:
    bootstrap = text("ops/bootstrap-brain.sh")
    functions = bootstrap[bootstrap.index("render() {") : bootstrap.index('case "$MODE" in')]
    home = tmp_path / "home"
    config = home / ".config"
    systemd_dir = config / "systemd/user"
    env_dir = config / "pgfr-spine"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "python3.12").symlink_to(sys.executable)
    systemctl = fake_bin / "systemctl"
    systemctl.write_text(
        '#!/bin/sh\n[ "$*" = "--user daemon-reload" ] || exit 1\n'
        'printf "%s\\n" "$*" >> "$PGFR_TEST_SYSTEMCTL_LOG"\n',
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    reload_log = tmp_path / "reload.log"
    child_env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "REPO": str(ROOT),
        "SYSTEMD_DIR": str(systemd_dir),
        "ENV_DIR": str(env_dir),
        "PGFR_TEST_SYSTEMCTL_LOG": str(reload_log),
    }
    command = [
        "bash", "-c",
        "set -euo pipefail\nsay() { :; }\nfail() { exit 2; }\n"
        + functions + "\ninstall_templates\n",
    ]
    subprocess.run(command, env=child_env, check=True, capture_output=True, text=True)

    templates = ROOT / "ops/systemd"
    installed_envs = []
    for template in (*templates.iterdir(), *(templates / "groot").iterdir()):
        if template.suffix not in {".env", ".service", ".target"}:
            continue
        is_env = template.suffix == ".env"
        destination = (
            env_dir / template.relative_to(templates)
            if is_env else systemd_dir / template.name
        )
        if is_env and template.parent.name == "groot":
            # A model identity is selected by the dedicated profile installer.
            # Bootstrap must neither seed unresolved placeholders nor replace
            # an operator's existing checkpoint profile on a later install.
            assert not destination.exists()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("# Operator settings\nCUSTOM_VALUE=retained\n", encoding="utf-8")
            destination.chmod(0o600)
            installed_envs.append(destination)
            continue
        expected = template.read_text(encoding="utf-8").replace(
            "__PGFR_REPO__", str(ROOT)
        ).replace("__PGFR_HOME__", str(home))
        assert destination.read_text(encoding="utf-8") == expected
        assert destination.stat().st_mode & 0o777 == (0o600 if is_env else 0o644)
        if is_env:
            installed_envs.append(destination)
            destination.write_text("# Operator settings\nCUSTOM_VALUE=retained\n", encoding="utf-8")

    assert not (systemd_dir / "pgfr-groot-two-host-bridge.service").exists()

    secrets = home / ".openclaw/secrets.env"
    original_secrets = secrets.read_bytes()
    assert re.search(rb"^OPENCLAW_GATEWAY_TOKEN=[a-f0-9]{64}$", original_secrets, re.MULTILINE)
    assert secrets.stat().st_mode & 0o777 == 0o600
    subprocess.run(command, env=child_env, check=True, capture_output=True, text=True)
    assert secrets.read_bytes() == original_secrets
    assert secrets.stat().st_mode & 0o777 == 0o600
    for destination in installed_envs:
        assert destination.read_text(encoding="utf-8") == "# Operator settings\nCUSTOM_VALUE=retained\n"
        assert destination.stat().st_mode & 0o777 == 0o600
    assert reload_log.read_text(encoding="utf-8").splitlines() == ["--user daemon-reload"] * 2


def test_vlm_has_one_supported_service_owner() -> None:
    unit = text("ops/systemd/pgfr-perception-vlm.service")
    bootstrap = text("ops/bootstrap-brain.sh")
    deploy = text("ops/thor-deploy.sh")
    assert "ops/launch-perception-vlm.sh --run" in unit
    assert '"$REPO"/ops/systemd/*.service' in bootstrap
    assert "pgfr-perception-vlm.service" in deploy
    assert "/api/ready" in deploy


def test_machine_specific_workflow_units_are_removed() -> None:
    assert not (ROOT / "servers/pgfr-workflows/pgfr-workflows.env").exists()
    assert not (ROOT / "servers/pgfr-workflows/pgfr-workflows.service").exists()


def test_new_operational_scripts_are_executable() -> None:
    for relative in ("ops/check-sim-host.sh", "ops/launch-perception-vlm.sh"):
        mode = os.stat(ROOT / relative).st_mode
        assert mode & 0o111, f"{relative} is not executable"


def test_playbook_sync_replaces_a_marker_from_a_previous_source_path(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    previous_begin = (
        "<!-- PGFR-PLAYBOOK-BEGIN (synced from skills/previous-orchestrator/PLAYBOOK.md) -->"
    )
    target.write_text(
        "# Agent profile\n\n"
        f"{previous_begin}\n\nprevious playbook\n\n<!-- PGFR-PLAYBOOK-END -->\n\n"
        "## Local notes\n\nKeep this section.\n",
        encoding="utf-8",
    )

    subprocess.run(
        [str(ROOT / "ops/sync-playbook.sh"), str(target)],
        check=True,
        cwd=ROOT,
        env={**os.environ, "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
    )

    updated = target.read_text(encoding="utf-8")
    assert previous_begin not in updated
    assert updated.count("<!-- PGFR-PLAYBOOK-BEGIN") == 1
    assert updated.count("<!-- PGFR-PLAYBOOK-END -->") == 1
    playbook = text(
        "skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/PLAYBOOK.md"
    )
    # Sync omits the document title and maintenance comment.
    sections = playbook[playbook.index("\n## ") :].strip()
    assert sections in updated
    assert "## Local notes\n\nKeep this section." in updated


def test_playbook_sync_replaces_the_centralized_legacy_marker(tmp_path: Path) -> None:
    guard = text("ops/pgfr-legacy-guard.sh")
    marker_match = re.search(
        r"PGFR_LEGACY_PLAYBOOK_MARKER='([^']+)'", guard
    )
    assert marker_match is not None
    legacy_marker = marker_match.group(1)
    target = tmp_path / "AGENTS.md"
    target.write_text(
        "# Agent profile\n\n"
        f"<!-- {legacy_marker}-BEGIN (synced from an earlier checkout) -->\n\n"
        "previous playbook\n\n"
        f"<!-- {legacy_marker}-END -->\n\n"
        "## Local notes\n\nKeep this section.\n",
        encoding="utf-8",
    )

    subprocess.run(
        [str(ROOT / "ops/sync-playbook.sh"), str(target)],
        check=True,
        cwd=ROOT,
        env={**os.environ, "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
    )

    updated = target.read_text(encoding="utf-8")
    assert legacy_marker not in updated
    assert updated.count("<!-- PGFR-PLAYBOOK-BEGIN") == 1
    assert updated.count("<!-- PGFR-PLAYBOOK-END -->") == 1
    assert "previous playbook" not in updated
    assert "## Local notes\n\nKeep this section." in updated


def test_thor_codec_install_selects_abi6_libraries_without_cli(tmp_path: Path) -> None:
    source = text(
        "reference/groot/thor/install_deps.sh"
    )
    start = source.index("TORCHCODEC_FFMPEG6_RUNTIME=(")
    end = source.index('echo "Installing torchcodec from validated wheel:', start)
    # Execute the actual package-selection block against an isolated apt recorder.
    # No installer preamble, Python/GPU setup, network, or host package manager runs.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "apt-argv.jsonl"
    fake_apt = fake_bin / "apt-get"
    fake_apt.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['PGFR_TEST_APT_LOG'], 'a') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
    )
    fake_apt.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", "-c", "set -euo pipefail\n" + source[start:end]],
        env={"PATH": str(fake_bin), "SUDO": "", "PGFR_TEST_APT_LOG": str(log)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls == [
        ["update", "-qq"],
        ["install", "-y", "--no-remove", "--no-install-recommends",
         "libavfilter9", "libavformat60", "libavcodec60", "libavutil58",
         "libswresample4", "libswscale7"],
    ]
