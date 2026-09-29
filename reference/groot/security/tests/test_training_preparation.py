# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Training preparation must fail closed and retain local sources on repetition."""

from __future__ import annotations

import difflib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SECURITY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SECURITY))
spec = importlib.util.spec_from_file_location("prepare_training", SECURITY / "prepare_training.py")
training = importlib.util.module_from_spec(spec)
spec.loader.exec_module(training)


class TrainingPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "assets"
        self.checkout = Path(self.temporary.name) / "checkout"
        self.root.mkdir()
        self.checkout.mkdir()
        self.before = {
            "pyproject.toml": b'[project]\nname = "gr00t"\n',
            "uv.lock": b'version = 1\nrevision = 3\n',
        }
        self.after = {name: data + b'# pinned security source\n' for name, data in self.before.items()}
        hashes = {}
        chunks = []
        for name, data in self.before.items():
            (self.checkout / name).write_bytes(data)
            hashes[name] = {"before": training.sha256(data), "after": training.sha256(self.after[name])}
            chunks.extend(difflib.unified_diff(data.decode().splitlines(True), self.after[name].decode().splitlines(True), fromfile=f"a/{name}", tofile=f"b/{name}"))
        patch_bytes = "".join(chunks).encode()
        (self.root / "project.patch").write_bytes(patch_bytes)
        self.manifest = {"packages": [{"name": "transformers"}, {"name": "accelerate"}], "training_project": {"patch": {"path": "project.patch", "sha256": training.sha256(patch_bytes), "files": hashes}}}

    def assert_original(self):
        for name, data in self.before.items():
            self.assertEqual((self.checkout / name).read_bytes(), data)

    def test_preparation_is_idempotent_and_offline_checks_existing_wheels(self):
        with patch.object(training, "materialize") as build:
            training.prepare(self.checkout, self.root, self.manifest, None, True)
            first = {name: (self.checkout / name).stat().st_mtime_ns for name in self.after}
            training.prepare(self.checkout, self.root, self.manifest, None, True)
        for name, data in self.after.items():
            self.assertEqual((self.checkout / name).read_bytes(), data)
            self.assertEqual((self.checkout / name).stat().st_mtime_ns, first[name])
        self.assertEqual(build.call_count, 4)
        self.assertTrue(all(call.kwargs["check"] for call in build.call_args_list))

    def test_missing_offline_wheel_cannot_change_project(self):
        with patch.object(training, "materialize", side_effect=training.BuildError("missing wheel")):
            with self.assertRaisesRegex(training.BuildError, "missing wheel"):
                training.prepare(self.checkout, self.root, self.manifest, None, True)
        self.assert_original()

    def test_explicit_offline_originals_are_passed_to_builder(self):
        originals = Path(self.temporary.name) / "originals"
        with patch.object(training, "materialize") as build:
            training.prepare(self.checkout, self.root, self.manifest, originals, True)
        self.assertTrue(all(call.args[3] == originals and not call.kwargs["check"] for call in build.call_args_list))

    def test_tampered_configuration_refused_before_any_build(self):
        (self.checkout / "uv.lock").write_text("unreviewed dependency\n")
        with patch.object(training, "materialize") as build:
            with self.assertRaisesRegex(training.BuildError, "Unexpected training configuration"):
                training.prepare(self.checkout, self.root, self.manifest, None, False)
        build.assert_not_called()
        self.assertEqual((self.checkout / "pyproject.toml").read_bytes(), self.before["pyproject.toml"])

    def test_mixed_pair_refused(self):
        (self.checkout / "uv.lock").write_bytes(self.after["uv.lock"])
        with self.assertRaisesRegex(training.BuildError, "mixed"):
            training.project_files(self.checkout, self.root, self.manifest["training_project"]["patch"])

    def test_tampered_patch_refused(self):
        (self.root / "project.patch").write_bytes(b"changed")
        with self.assertRaisesRegex(training.BuildError, "SHA256 mismatch"):
            training.prepare(self.checkout, self.root, self.manifest, None, False)
        self.assert_original()

    def test_symlinked_project_and_external_wheel_directory_refused(self):
        (self.checkout / "uv.lock").unlink()
        (self.root / "outside.lock").write_bytes(self.before["uv.lock"])
        (self.checkout / "uv.lock").symlink_to(self.root / "outside.lock")
        with self.assertRaisesRegex(training.BuildError, "regular training project file"):
            training.prepare(self.checkout, self.root, self.manifest, None, False)
        (self.checkout / "uv.lock").unlink()
        (self.checkout / "uv.lock").write_bytes(self.before["uv.lock"])
        (self.checkout / ".pgfr-security").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(training.BuildError, "inside the checkout"):
            training.prepare(self.checkout, self.root, self.manifest, None, False)

    def test_linked_virtual_environment_refused_before_modifying_project(self):
        (self.checkout / ".venv").symlink_to(self.root, target_is_directory=True)
        with patch.object(training, "materialize") as build:
            with self.assertRaisesRegex(training.BuildError, "cannot be a symlink"):
                training.prepare(self.checkout, self.root, self.manifest, None, False)
        build.assert_not_called()
        self.assert_original()


if __name__ == "__main__":
    unittest.main()
