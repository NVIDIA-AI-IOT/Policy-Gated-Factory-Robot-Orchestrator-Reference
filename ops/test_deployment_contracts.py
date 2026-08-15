# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free checks for the public clean-machine deployment contract."""

from __future__ import annotations

import os
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
    install_cell = guide.index("ops/install-groot-cell.sh")
    launch = guide.index("ops/launch-groot-isaac.sh")
    assert runtime < bootstrap < fetch < install_cell < launch


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
    assert f'{isaac["tag"]}@{isaac["digest"]}' in guide
    assert f'{vlm["tag"]}@{vlm["digest"]}' in guide
    assert runtime["python"] == "3.12.3"
    assert runtime["node"] == "22.22.3"
    assert runtime["uv"] == "0.11.32"
    assert runtime["huggingface_hub"] == "0.36.2"


def test_doctors_and_units_use_immutable_or_user_owned_contracts() -> None:
    sim_doctor = text("ops/check-sim-host.sh")
    vlm_launcher = text("ops/launch-perception-vlm.sh")
    vlm_unit = text("ops/systemd/ic-perception-vlm.service")
    assert 'docker image inspect "$IMAGE_REF"' in sim_doctor
    assert 'docker image inspect "$IMAGE"' not in sim_doctor
    assert "IC_VLM_READY_TIMEOUT_S must be an integer" in vlm_launcher
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
