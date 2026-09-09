# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free checks for the public clean-machine deployment contract."""

from __future__ import annotations

import json
import os
import re
import subprocess
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
    assert set(template["agents"]["entries"]) == {"main", "ic-console"}
    console_tools = template["agents"]["entries"]["ic-console"]["tools"]
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


def test_canonical_guide_installs_before_starting() -> None:
    guide = text("docs/REPRODUCIBLE-DEMO.md")
    runtime = guide.index("ops/prepare-groot-runtime.sh --install")
    bootstrap = guide.index("ops/bootstrap-brain.sh --check")
    fetch = guide.index("ops/fetch-groot-models.sh")
    prepare_sim = guide.index("ops/isaac-sim-workstation.sh --prepare")
    check_sim = guide.index(
        'ops/check-sim-host.sh --profile x11 --mount "$IC_GROOT_ISAAC_MOUNT"'
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

    checkout_examples = (
        text("reference/policy-gated-factory-robot-orchestrator-reference/groot/training/README.md"),
        text("connectors/nemo-gym/resources_servers/ic_cell/README.md"),
    )
    expected_example = "/path/to/Policy-Gated-Factory-Robot-Orchestrator-Reference"
    assert all(expected_example in item for item in checkout_examples)

    mcp_guide = text("servers/policy-gated-factory-robot-orchestrator-reference-mcp/README.md")
    assert f"{checkout}/servers/policy-gated-factory-robot-orchestrator-reference-mcp/.venv/bin/ic-mcp" in mcp_guide


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
    thor_dockerfile = text(
        "reference/policy-gated-factory-robot-orchestrator-reference/groot/thor/Dockerfile"
    )
    thor_installer = text(
        "reference/policy-gated-factory-robot-orchestrator-reference/groot/thor/install_deps.sh"
    )
    thor_lock = text(
        "reference/policy-gated-factory-robot-orchestrator-reference/groot/thor/uv.lock"
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
    for qualification_record in (text("CHANGELOG.md"), text("docs/SUPPORT.md")):
        assert "2026-09-09" in qualification_record
        assert "`d70ed0c3940f`" in qualification_record
        assert "`953020d69491`" in qualification_record
    for value in (ros_sidecar["tag"], ros_sidecar["digest"]):
        assert value in scripted_runbook
        assert value in notices
    assert ros_sidecar["platform"] == "linux/amd64"
    assert f'{thor_cuda["tag"]}@{thor_cuda["digest"]}' in thor_dockerfile
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
        "reference/policy-gated-factory-robot-orchestrator-reference/groot/thor/install_deps.sh"
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
        "reference/policy-gated-factory-robot-orchestrator-reference/groot/thor"
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
    for name, status in (("python3", 0), ("systemctl", 1)):
        command = fake_bin / name
        command.write_text(f"#!/bin/sh\nexit {status}\n", encoding="utf-8")
        command.chmod(0o755)

    destination = tmp_path / "published" / "Isaac-GR00T"
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "HOME": str(tmp_path / "home"),
        "IC_GROOT_SOURCE_ROOT": str(destination),
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
    assert "IC_GROOT_RUNTIME_PREPARED" in first_stdout
    assert second.returncode == 2
    assert "another preparation owns the destination lock" in second.stderr
    assert (tmp_path / "clone.calls").read_text(encoding="utf-8").splitlines() == [
        "clone"
    ]
    assert (destination / "scripts" / "deployment" / "thor" / "uv.lock").is_file()
    assert not any(destination.glob(".groot-source.*"))


def test_doctors_and_units_use_immutable_or_user_owned_contracts() -> None:
    sim_doctor = text("ops/check-sim-host.sh")
    vlm_launcher = text("ops/launch-perception-vlm.sh")
    vlm_unit = text("ops/systemd/ic-perception-vlm.service")
    assert 'docker image inspect "$IMAGE_REF"' in sim_doctor
    assert 'docker image inspect "$IMAGE"' not in sim_doctor
    assert "IC_VLM_READY_TIMEOUT_S must be an integer" in vlm_launcher
    assert "--runtime=nvidia --gpus all" in vlm_launcher
    assert "VLM container exited before readiness" in vlm_launcher
    assert "docker.service" not in vlm_unit


def test_write_capable_templates_are_loopback_first() -> None:
    chat = text("ops/systemd/chat.env")
    workflows = text("ops/systemd/workflows.env")
    console = text("ops/systemd/console.env")
    assert "IC_CHAT_HOST=127.0.0.1" in chat
    assert "IC_WORKFLOWS_HOST=127.0.0.1" in workflows
    assert "IC_CONSOLE_HOST=127.0.0.1" in console
    assert "IC_CHAT_TOKEN=" in chat
    assert "IC_WORKFLOWS_TOKEN=" in workflows
    assert "IC_CHAT_URL=http://127.0.0.1:8620" in console
    assert "\nIC_CHAT_PUBLIC_URL=\n" in console


def test_brain_bootstrap_seeds_one_shared_openclaw_gateway_token() -> None:
    bootstrap = text("ops/bootstrap-brain.sh")
    chat_backend = text("servers/ic-chat/src/ic_chat/backends.py")
    gateway_unit = text("ops/systemd/ic-openclaw.service")
    chat_unit = text("ops/systemd/ic-chat.service")
    secrets_file = "EnvironmentFile=-__IC_HOME__/.openclaw/secrets.env"
    assert "OPENCLAW_GATEWAY_TOKEN" in bootstrap
    assert "secrets.token_hex(32)" in bootstrap
    assert 'chmod 0600 "$secrets_file"' in bootstrap
    assert secrets_file in gateway_unit
    assert secrets_file in chat_unit
    assert 'os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")' in chat_backend


def test_vlm_has_one_supported_service_owner() -> None:
    unit = text("ops/systemd/ic-perception-vlm.service")
    bootstrap = text("ops/bootstrap-brain.sh")
    deploy = text("ops/thor-deploy.sh")
    assert "ops/launch-perception-vlm.sh --run" in unit
    assert '"$REPO"/ops/systemd/*.service' in bootstrap
    assert "ic-perception-vlm.service" in deploy
    assert "/api/ready" in deploy


def test_machine_specific_workflow_units_are_removed() -> None:
    assert not (ROOT / "servers/ic-workflows/ic-workflows.env").exists()
    assert not (ROOT / "servers/ic-workflows/ic-workflows.service").exists()


def test_new_operational_scripts_are_executable() -> None:
    for relative in ("ops/check-sim-host.sh", "ops/launch-perception-vlm.sh"):
        mode = os.stat(ROOT / relative).st_mode
        assert mode & 0o111, f"{relative} is not executable"


def test_playbook_sync_replaces_a_marker_from_a_previous_source_path(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    previous_begin = (
        "<!-- IC-PLAYBOOK-BEGIN (synced from skills/previous-orchestrator/PLAYBOOK.md) -->"
    )
    target.write_text(
        "# Agent profile\n\n"
        f"{previous_begin}\n\nprevious playbook\n\n<!-- IC-PLAYBOOK-END -->\n\n"
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
    assert updated.count("<!-- IC-PLAYBOOK-BEGIN") == 1
    assert updated.count("<!-- IC-PLAYBOOK-END -->") == 1
    assert "## Floor operating rule (Policy-Gated Factory Robot Orchestrator Reference)" in updated
    assert "## Local notes\n\nKeep this section." in updated
