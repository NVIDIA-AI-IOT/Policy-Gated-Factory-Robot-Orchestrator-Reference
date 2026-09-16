# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Manifest validation stays identical through file, authoring, and publish APIs."""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from pgfr_workflows.app import Store, build_app
from pgfr_workflows.authoring import author
from pgfr_workflows.spec import Workflow

from test_authoring import GOOD_SKILL, JsonBackend
from test_workflows import HDR, wf_dict


@pytest.fixture
def conformance_kit(monkeypatch):
    # The kit remains optional at runtime. Load its repository source so the
    # standard Workflows CI job also exercises these integration checks.
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "packages/conformance-kit/src"))
    return importlib.import_module("pgfr_conformance.kit")


@pytest.mark.parametrize(("overrides", "failures"), [
    ({}, []),
    ({"allowed_actions": ["reset"]}, ["allowed_actions are agent-class policy actions"]),
    ({"allowed_actions": ["move", "spawn"]}, ["allowed_actions are agent-class policy actions"]),
    ({"allowed_actions": ["inspect", "navigate_to"]}, []),
    ({"done_criteria": ""}, ["manifest field: done_criteria"]),
])
def test_file_and_dictionary_manifest_results_match(conformance_kit, tmp_path, overrides, failures):
    manifest = {**json.loads(GOOD_SKILL), **overrides}
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest))
    results = conformance_kit.check_skill_manifest_data(manifest)
    assert conformance_kit.check_skill_manifest(str(path)) == results
    assert [result.name for result in results if not result.passed] == failures


@pytest.mark.parametrize("manifest", [None, False, {}, []])
def test_empty_manifest_results_match(conformance_kit, tmp_path, manifest):
    path = tmp_path / "empty.yaml"
    path.write_text(yaml.safe_dump(manifest))
    results = conformance_kit.check_skill_manifest_data(manifest)
    assert conformance_kit.check_skill_manifest(str(path)) == results
    assert len(results) == 7
    assert sum(not result.passed for result in results) == 6


@pytest.mark.parametrize("manifest", [42, "not a mapping", ["unexpected"],
                                      {"allowed_actions": [["move"]]}])
def test_invalid_manifest_types_preserve_existing_failures(conformance_kit, tmp_path, manifest):
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(manifest))
    # Parseable inputs of the wrong type historically raise here. The pure
    # extraction preserves that contract instead of changing error handling.
    with pytest.raises((TypeError, AttributeError)) as file_error:
        conformance_kit.check_skill_manifest(str(path))
    with pytest.raises(type(file_error.value)) as data_error:
        conformance_kit.check_skill_manifest_data(manifest)
    assert str(data_error.value) == str(file_error.value)


def test_unparseable_file_still_reports_parse_failure(conformance_kit, tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("name: [")
    results = conformance_kit.check_skill_manifest(str(path))
    assert len(results) == 1
    assert results[0].name == "manifest parses"
    assert results[0].passed is False
    assert results[0].detail


@pytest.mark.parametrize("kit_available", [True, False])
async def test_authoring_and_publish_keep_optional_validation(
    conformance_kit, monkeypatch, tmp_path, kit_available,
):
    if not kit_available:
        monkeypatch.setitem(sys.modules, "pgfr_conformance.kit", None)
    store = Store(tmp_path / "workflows")
    store.save(Workflow.model_validate(wf_dict()))
    client = TestClient(build_app(store=store, skills_dir=tmp_path / "skills", backend=None))

    def no_temporary_manifest(*args, **kwargs):
        raise AssertionError("Validation should not serialize a temporary manifest")

    monkeypatch.setattr(tempfile, "mkstemp", no_temporary_manifest)
    drafted = await author(JsonBackend([GOOD_SKILL]), "skill", "Sort the cubes")
    assert drafted["ok"] is True
    assert drafted["draft"] == json.loads(GOOD_SKILL)
    response = client.post("/api/workflows/sort-one-cube/publish", headers=HDR)
    assert response.status_code == 200
    assert response.json()["conformance"] == ("passed" if kit_available else "skipped")
    manifest = Path(response.json()["manifest"])
    assert all(result.passed for result in conformance_kit.check_skill_manifest(str(manifest)))


async def test_conformance_failures_still_block_authoring_and_publish(
    conformance_kit, monkeypatch, tmp_path,
):
    failure = conformance_kit.CheckResult("fixture conformance rule", False, "rejected")
    seen = []

    def reject(manifest):
        seen.append(manifest)
        return [failure]

    monkeypatch.setattr(conformance_kit, "check_skill_manifest_data", reject)
    drafted = await author(JsonBackend([GOOD_SKILL]), "skill", "Sort the cubes", max_attempts=1)
    assert drafted["ok"] is False
    assert drafted["error"] == "conformance failures: ['fixture conformance rule']"
    store = Store(tmp_path / "workflows")
    workflow = Workflow.model_validate(wf_dict())
    store.save(workflow)
    skills = tmp_path / "skills"
    client = TestClient(build_app(store=store, skills_dir=skills, backend=None))
    response = client.post("/api/workflows/sort-one-cube/publish", headers=HDR)
    assert response.status_code == 422
    assert response.json() == {"detail": {"conformance_failures": ["fixture conformance rule"]}}
    assert not (skills / "wf-sort-one-cube").exists()
    assert seen == [json.loads(GOOD_SKILL), workflow.to_skill_manifest()]
