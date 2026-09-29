# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Keep excluded legacy converters out of the pinned runtime packages.

Artifact applicability is recorded in legacy-advisories.json. The loader checks
below prevent regressions; they do not independently establish CVE applicability.
"""

import ast
import importlib
from importlib.metadata import version
import inspect
import json
from pathlib import Path
import pickle
import tempfile
import unittest
from unittest.mock import patch

from safetensors.torch import save_file
import torch
import transformers
from transformers import modeling_utils


SECURITY = Path(__file__).resolve().parents[1]
EVIDENCE = json.loads((SECURITY / "legacy-advisories.json").read_text())
UNPICKLED = []


def unexpected_reducer():
    """A harmless sentinel that a weights-only loader must never execute."""
    UNPICKLED.append(True)
    return 0


class UntrustedCheckpointValue:
    def __reduce__(self):
        return unexpected_reducer, ()


class LegacyConverterExposureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        allowed = []
        for name in ("manifest.json", "manifest-training.json"):
            manifest = json.loads((SECURITY / name).read_text())
            allowed.extend(
                entry["version"]
                for entry in manifest["packages"]
                if entry["name"] == "transformers"
            )
        if transformers.__version__ not in allowed:
            raise AssertionError("Tests require a pinned PGFR Transformers security wheel")
        if version("transformers") != transformers.__version__:
            raise AssertionError("Installed package metadata and code versions differ")
        cls.package = Path(transformers.__file__).resolve().parent

    def setUp(self):
        UNPICKLED.clear()
        self.temporary = tempfile.TemporaryDirectory(prefix="pgfr-legacy-checkpoint-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_evidence_matches_pinned_upstream_artifacts(self):
        artifacts = {
            item["version"]: item for item in EVIDENCE["artifacts"]
            if item["kind"] == "wheel"
        }
        for name in ("manifest.json", "manifest-training.json"):
            manifest = json.loads((SECURITY / name).read_text())
            entry = next(item for item in manifest["packages"] if item["name"] == "transformers")
            evidence = artifacts[entry["base_version"]]
            for key in ("filename", "sha256", "url"):
                self.assertEqual(entry["upstream"][key], evidence[key])

    def test_upstream_excluded_conversion_modules_cannot_be_imported(self):
        for relative in EVIDENCE["release_removal"]["paths"]:
            path = Path(relative.removeprefix("src/transformers/"))
            module = "transformers." + ".".join(path.with_suffix("").parts)
            with self.subTest(module=module):
                self.assertFalse((self.package / path).exists())
                with self.assertRaises(ModuleNotFoundError) as raised:
                    importlib.import_module(module)
                self.assertEqual(raised.exception.name, module)

    def test_shipped_model_sources_have_no_unsafe_converter_entrypoints(self):
        for finding in EVIDENCE["findings"]:
            model = finding["model"]
            forbidden = {
                entry["function"] for entry in finding["source_evidence"]
                if entry["function"] != "main"
            }
            files = list((self.package / "models" / model).rglob("*.py"))
            self.assertTrue(files, model)
            for path in files:
                tree = ast.parse(path.read_text())
                for node in ast.walk(tree):
                    with self.subTest(cve=finding["cve"], file=path.name):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            self.assertNotIn(node.name, forbidden)
                        if not isinstance(node, ast.Call):
                            continue
                        callee = ast.unparse(node.func)
                        self.assertNotIn(
                            callee,
                            {"eval", "exec", "pickle.load", "pickle.loads",
                             "torch.hub.load_state_dict_from_url"},
                        )
                        if callee == "torch.load":
                            keywords = {item.arg: item.value for item in node.keywords}
                            self.assertIn("weights_only", keywords)
                            self.assertIsInstance(keywords["weights_only"], ast.Constant)
                            self.assertIs(keywords["weights_only"].value, True)

    def test_model_loaders_inherit_the_safe_default(self):
        classes = (
            "PerceiverPreTrainedModel", "GPT2PreTrainedModel", "SEWPreTrainedModel", "SEWDPreTrainedModel",
            "HubertPreTrainedModel", "XCLIPPreTrainedModel", "Glm4PreTrainedModel",
        )
        for name in classes:
            with self.subTest(model=name):
                loader = getattr(transformers, name).from_pretrained
                self.assertIs(loader.__func__, modeling_utils.PreTrainedModel.from_pretrained.__func__)
                self.assertIs(inspect.signature(loader).parameters["weights_only"].default, True)

    def test_default_checkpoint_loader_accepts_tensors(self):
        expected = {"weight": torch.tensor([1.0, 2.0])}
        for filename in ("pytorch_model.bin", "model.safetensors"):
            with self.subTest(format=filename):
                checkpoint = self.directory / filename
                if filename.endswith(".safetensors"):
                    save_file(expected, str(checkpoint), metadata={"format": "pt"})
                else:
                    torch.save(expected, checkpoint)
                actual = modeling_utils.load_state_dict(str(checkpoint))
                torch.testing.assert_close(actual["weight"], expected["weight"], rtol=0, atol=0)

    def test_default_checkpoint_loader_rejects_object_deserialization(self):
        checkpoint = self.directory / "pytorch_model.bin"
        torch.save({"weight": UntrustedCheckpointValue()}, checkpoint)
        with self.assertRaises(OSError):
            modeling_utils.load_state_dict(str(checkpoint))
        self.assertEqual(UNPICKLED, [])

    def test_remaining_megatron_loader_accepts_tensors_and_rejects_objects(self):
        module = importlib.import_module(
            "transformers.models.megatron_gpt2.checkpoint_reshaping_and_interoperability"
        )
        checkpoint = self.directory / "pytorch_model-00001-of-00001.bin"
        expected = {"weight": torch.tensor([1.0, 2.0])}
        torch.save(expected, checkpoint)
        actual = module.merge_transformers_sharded_states(str(self.directory), 1)
        torch.testing.assert_close(actual["weight"], expected["weight"], rtol=0, atol=0)
        torch.save({"weight": UntrustedCheckpointValue()}, checkpoint)
        with self.assertRaises(pickle.UnpicklingError):
            module.merge_transformers_sharded_states(str(self.directory), 1)
        self.assertEqual(UNPICKLED, [])

    def test_torch_version_guard_precedes_checkpoint_deserialization(self):
        module = importlib.import_module(
            "transformers.models.megatron_gpt2.checkpoint_reshaping_and_interoperability"
        )
        loaders = (
            (modeling_utils, lambda: modeling_utils.load_state_dict("unused.bin")),
            (module, lambda: module.merge_transformers_sharded_states(str(self.directory), 1)),
        )
        for owner, load in loaders:
            with self.subTest(module=owner.__name__):
                with patch.object(owner, "check_torch_load_is_safe", side_effect=ValueError("unsafe torch")):
                    with patch.object(torch, "load") as deserialize:
                        with self.assertRaisesRegex(ValueError, "unsafe torch"):
                            load()
                        deserialize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
