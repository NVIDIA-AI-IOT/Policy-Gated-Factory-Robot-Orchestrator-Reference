# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free checks for the public clean-machine deployment contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_canonical_guide_installs_before_starting() -> None:
    guide = text("docs/REPRODUCIBLE-DEMO.md")
    runtime = guide.index("ops/prepare-groot-runtime.sh --install")
    bootstrap = guide.index("ops/bootstrap-brain.sh --check")
    fetch = guide.index("ops/fetch-groot-models.sh")
    prepare_sim = guide.index("ops/isaac-sim-workstation.sh --prepare")
    check_sim = guide.index('ops/check-sim-host.sh --mount "$IC_GROOT_ISAAC_MOUNT"')
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
    vlm = manifest["containers"]["perception_vllm"]
    isaac_launcher = text("ops/launch-groot-isaac.sh")
    vlm_launcher = text("ops/launch-perception-vlm.sh")
    vlm_env = text("ops/systemd/vlm.env")

    assert isaac["tag"] in isaac_launcher
    assert isaac["digest"] in isaac_launcher
    assert '"$IMAGE_REF"' in isaac_launcher
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
