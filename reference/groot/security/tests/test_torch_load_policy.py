# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Exercise scoped Torch loading controls without changing the Torch package."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import torch


REPO = Path(__file__).resolve().parents[4]
POLICY_UNIT = REPO / "ops/systemd/groot/pgfr-groot-policy@.service"
PIPELINE = REPO / "reference/groot/groot_n1_7_pgfr_pipeline"
FORCE = "TORCH_FORCE_WEIGHTS_ONLY_LOAD"
UNSAFE = "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"
MARKER = "PGFR_UNSAFE_PICKLE_EXECUTED"


def policy_environment():
    environment = {**os.environ, FORCE: "0", UNSAFE: "1", "CUDA_VISIBLE_DEVICES": ""}
    lines = POLICY_UNIT.read_text().splitlines()
    for line in lines:
        if line.startswith("Environment=TORCH_"):
            key, value = line.removeprefix("Environment=").split("=", 1)
            environment[key] = value
        if line.startswith("UnsetEnvironment="):
            for key in line.removeprefix("UnsetEnvironment=").split():
                environment.pop(key, None)
    return environment


class UnsafeMarker:
    def __reduce__(self):
        # No shell commands or filesystem side effects, even if the guard regresses.
        return print, (MARKER,)


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.ones(1))

    def forward(self, value):
        return value + self.weight


class TorchLoadPolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgfr-torch-policy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_policy_unit_selects_safe_loading_and_clears_conflicting_setting(self):
        environment = policy_environment()
        self.assertEqual(environment[FORCE], "1")
        self.assertNotIn(UNSAFE, environment)

    def test_specialist_child_inherits_enforced_loading_policy(self):
        script = self.root / "gr00t/experiment/launch_finetune.py"
        script.parent.mkdir(parents=True)
        script.write_text(
            "import json,os\nprint(json.dumps({k:os.environ.get(k) for k in "
            f"{[FORCE, UNSAFE]!r}}}))\n"
        )
        environment = {
            **os.environ, FORCE: "0", UNSAFE: "1",
            "PGFR_GROOT_PYTHON": sys.executable,
            "PGFR_GROOT_BASE_MODEL_PATH": str(self.root),
        }
        result = subprocess.run(
            ["bash", str(REPO / "reference/groot/training/finetune-specialist.sh"),
             "green", "left:right", "output"], cwd=self.root, env=environment,
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout), {FORCE: "1", UNSAFE: None})

    def test_pipeline_child_inherits_enforced_loading_policy(self):
        spec = importlib.util.spec_from_file_location(
            "pgfr_finetune_policy_test", PIPELINE / "pipeline/training/launch_finetune.py"
        )
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        script = self.root / "gr00t/experiment/launch_finetune.py"
        script.parent.mkdir(parents=True)
        received = self.root / "received.json"
        script.write_text(
            "import json,os\nfrom pathlib import Path\n"
            f"Path({str(received)!r}).write_text(json.dumps({{k:os.environ.get(k) "
            f"for k in {[FORCE, UNSAFE]!r}}}))\n"
        )
        args = ["launcher", "--groot-root", str(self.root), "--base-model", str(self.root),
                "--dataset", str(self.root), "--output-dir", str(self.root / "output"),
                "--learning-rate", "0.0001", "--max-steps", "1"]
        with (
            patch.object(sys, "argv", args),
            patch.dict(os.environ, {FORCE: "0", UNSAFE: "1"}),
            patch.object(launcher.subprocess, "check_output", return_value=launcher.UPSTREAM_REVISION),
            patch.object(launcher, "validate_dataset", return_value={}),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            launcher.main()
        self.assertEqual(json.loads(received.read_text()), {FORCE: "1", UNSAFE: None})

    def save_export(self):
        path = self.root / "benign.pt2"
        torch.export.save(torch.export.export(TinyModel(), (torch.zeros(1),)), path)
        return path

    def run_loader(self, path, *, artifact=False):
        code = (
            "from pathlib import Path;from torch._export.serde.serialize import deserialize_torch_artifact;"
            "import sys;deserialize_torch_artifact(Path(sys.argv[1]).read_bytes())"
            if artifact else
            "import torch,sys;model=torch.export.load(sys.argv[1]).module();"
            "torch.testing.assert_close(model(torch.zeros(1)),torch.ones(1))"
        )
        return subprocess.run(
            [sys.executable, "-c", code, str(path)], env=policy_environment(),
            capture_output=True, text=True, timeout=30,
        )

    def test_tensor_export_round_trip_remains_supported(self):
        result = self.run_loader(self.save_export())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_export_weights_and_constants_reject_unsafe_pickle(self):
        benign = self.save_export()
        payload = io.BytesIO()
        torch.save({"marker": UnsafeMarker()}, payload)
        for kind in ("weights", "constants"):
            with self.subTest(kind=kind):
                crafted = self.root / f"crafted-{kind}.pt2"
                modified = False
                with zipfile.ZipFile(benign) as source, zipfile.ZipFile(crafted, "w") as target:
                    for item in source.infolist():
                        data = source.read(item.filename)
                        if item.filename.endswith(f"model_{kind}_config.json"):
                            config = json.loads(data)
                            config["config"]["marker"] = {
                                "path_name": "tensor_pgfr_marker", "is_param": False,
                                "use_pickle": True, "tensor_meta": None,
                            }
                            data = json.dumps(config).encode()
                            prefix = item.filename.split("/")[0]
                            target.writestr(f"{prefix}/data/{kind}/tensor_pgfr_marker", payload.getvalue())
                            modified = True
                        # Torch2.7 uses the legacy format instead of a payload config.
                        legacy = "serialized_state_dict.pt" if kind == "weights" else "serialized_constants.pt"
                        if item.filename == legacy:
                            data = payload.getvalue()
                            modified = True
                        target.writestr(item, data)
                self.assertTrue(modified, "The expected export payload member was not exercised")
                result = self.run_loader(crafted)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(MARKER, result.stdout)
                self.assertIn("Weights only load failed", result.stderr)

    def test_legacy_artifact_fallback_cannot_enable_pickle(self):
        path = self.root / "legacy.pt"
        torch.save({"marker": UnsafeMarker()}, path)
        result = self.run_loader(path, artifact=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(MARKER, result.stdout)
        self.assertIn("Weights only load failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
