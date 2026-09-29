# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Real CPU loader compatibility and malicious-index rejection tests."""

import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import accelerate
from accelerate import dispatch_model, init_empty_weights, load_checkpoint_and_dispatch
from accelerate.utils import load_checkpoint_in_model
from safetensors.torch import save_file
import torch
from torch import nn


class RealTorchCheckpointTests(unittest.TestCase):
    cases = 0

    @classmethod
    def setUpClass(cls):
        if accelerate.__version__ not in (
            "1.12.0+pgfr.security1",
            "1.13.0+pgfr.security1",
        ):
            raise AssertionError(
                "Tests require the pinned downstream Accelerate security wheel"
            )
        if version("accelerate") != accelerate.__version__:
            raise AssertionError("Installed package metadata and code versions differ")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pgfr-accelerate-real-torch-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        torch.manual_seed(177)
        self.source = self.make_model()
        self.input = torch.tensor([[1.0, -2.0, 3.0], [0.5, 0.0, 1.0]])
        self.expected = self.source(self.input).detach()

    def make_model(self):
        return nn.Sequential(nn.Linear(3, 4), nn.Tanh(), nn.Linear(4, 2))

    def new_model(self, meta=False):
        torch.manual_seed(178)
        if meta:
            with init_empty_weights():
                return self.make_model()
        return self.make_model()

    def write_checkpoint(self, folder, format, sharded):
        folder.mkdir(parents=True, exist_ok=True)
        state = self.source.state_dict()
        if sharded:
            pieces = [
                {k: v for k, v in state.items() if k.startswith(prefix)}
                for prefix in ("0.", "2.")
            ]
            names = [
                f"model-{i + 1:05d}-of-00002.{'safetensors' if format == 'safe' else 'bin'}"
                for i in range(2)
            ]
            index = {
                "metadata": {"total_size": sum(v.nbytes for v in state.values())},
                "weight_map": {
                    k: name for name, piece in zip(names, pieces) for k in piece
                },
            }
            index_path = (
                folder
                / f"{'model.safetensors' if format == 'safe' else 'pytorch_model.bin'}.index.json"
            )
            index_path.write_text(json.dumps(index))
        else:
            names = ["model.safetensors" if format == "safe" else "pytorch_model.bin"]
            pieces = [state]
            index_path = folder / names[0]
        for name, piece in zip(names, pieces):
            if format == "safe":
                save_file(piece, str(folder / name), metadata={"format": "pt"})
            else:
                torch.save(piece, folder / name)
        return index_path

    def assert_equal_parameters_and_forward(self, target, dtype=torch.float32):
        for name, parameter in target.state_dict().items():
            torch.testing.assert_close(
                parameter, self.source.state_dict()[name].to(dtype), rtol=0, atol=0
            )
        expected = self.source.to(dtype)(self.input.to(dtype)).detach()
        torch.testing.assert_close(
            target(self.input.to(dtype)), expected, rtol=0, atol=0
        )
        type(self).cases += 1

    def test_plain_and_sharded_formats_both_apis_with_directory_or_file_and_cpu_map(
        self,
    ):
        for format in ("safe", "bin"):
            for sharded in (False, True):
                folder = self.root / f"{format}-{sharded}"
                file = self.write_checkpoint(folder, format, sharded)
                for api in (load_checkpoint_in_model, load_checkpoint_and_dispatch):
                    for checkpoint in (folder, file):
                        for device_map in (None, {"": "cpu"}):
                            with self.subTest(
                                format=format,
                                sharded=sharded,
                                api=api.__name__,
                                file=checkpoint.name,
                                map=device_map,
                            ):
                                target = self.new_model()
                                result = api(
                                    target, str(checkpoint), device_map=device_map
                                )
                                if api is load_checkpoint_and_dispatch:
                                    self.assertIs(result, target)
                                self.assert_equal_parameters_and_forward(target)

    def test_meta_initialization_and_dtype_conversion(self):
        folder = self.root / "meta"
        self.write_checkpoint(folder, "safe", True)
        for api in (load_checkpoint_in_model, load_checkpoint_and_dispatch):
            for dtype in (torch.float32, torch.float64):
                with self.subTest(api=api.__name__, dtype=dtype):
                    target = self.new_model(meta=True)
                    api(target, str(folder), device_map={"": "cpu"}, dtype=dtype)
                    self.assert_equal_parameters_and_forward(target, dtype)

    def test_cpu_temporary_state_dict_offloading(self):
        for format in ("safe", "bin"):
            folder = self.root / format
            self.write_checkpoint(folder, format, True)
            for api in (load_checkpoint_in_model, load_checkpoint_and_dispatch):
                with self.subTest(api=api.__name__, format=format):
                    target = self.new_model()
                    api(
                        target,
                        str(folder),
                        device_map={"": "cpu"},
                        offload_state_dict=True,
                    )
                    self.assert_equal_parameters_and_forward(target)

    def test_cpu_disk_offload_hooks_and_inference(self):
        for format in ("safe", "bin"):
            folder = self.root / format
            self.write_checkpoint(folder, format, True)
            for api in (load_checkpoint_in_model, load_checkpoint_and_dispatch):
                with self.subTest(api=api.__name__, format=format):
                    target = self.new_model(meta=True)
                    offload = self.root / f"offload-{format}-{api.__name__}"
                    device_map = {"0": "cpu", "2": "disk"}
                    result = api(
                        target,
                        str(folder),
                        device_map=device_map,
                        offload_folder=str(offload),
                        offload_state_dict=True,
                    )
                    if api is load_checkpoint_in_model:
                        result = dispatch_model(
                            target, device_map=device_map, offload_dir=str(offload)
                        )
                    self.assertIs(result, target)
                    self.assertTrue((offload / "index.json").is_file())
                    self.assertEqual(target[2].weight.device.type, "meta")
                    for _ in range(2):
                        torch.testing.assert_close(
                            target(self.input), self.expected, rtol=0, atol=0
                        )
                    self.assertEqual(target[2].weight.device.type, "meta")
                    type(self).cases += 1

    def test_hugging_face_snapshot_links_real_safetensors_loading(self):
        for subfolder in ("", "component", "component/nested"):
            repo = self.root / f"models--test--model-{len(subfolder)}"
            snapshot = repo / "snapshots" / ("a" * 40)
            checkpoint = snapshot / subfolder
            index_path = self.write_checkpoint(checkpoint, "safe", True)
            blobs = repo / "blobs"
            blobs.mkdir()
            for shard in checkpoint.glob("*.safetensors"):
                digest = hashlib.sha256(shard.read_bytes()).hexdigest()
                target = blobs / digest
                shard.rename(target)
                shard.symlink_to(os.path.relpath(target, checkpoint))
            for api in (load_checkpoint_in_model, load_checkpoint_and_dispatch):
                for path in (checkpoint, index_path):
                    with self.subTest(
                        api=api.__name__, path=path.name, subfolder=subfolder
                    ):
                        target = self.new_model(meta=True)
                        api(target, str(path), device_map={"": "cpu"})
                        self.assert_equal_parameters_and_forward(target)

    def test_path_traversal_rejected_before_model_changes(self):
        outside = self.root / "outside.safetensors"
        save_file(self.source.state_dict(), str(outside), metadata={"format": "pt"})
        folder = self.root / "evil"
        folder.mkdir()
        for shard in ("../outside.safetensors", str(outside)):
            index = folder / "model.safetensors.index.json"
            index.write_text(json.dumps({"weight_map": {"0.weight": shard}}))
            for api in (load_checkpoint_in_model, load_checkpoint_and_dispatch):
                with self.subTest(api=api.__name__, shard=shard):
                    target = self.new_model()
                    original = {k: v.clone() for k, v in target.state_dict().items()}
                    with self.assertRaises(ValueError):
                        api(target, str(folder), device_map={"": "cpu"})
                    for name, value in target.state_dict().items():
                        torch.testing.assert_close(
                            value, original[name], rtol=0, atol=0
                        )
                    type(self).cases += 1

    def assert_bad_index_rejected(self, folder, data):
        index = folder / "model.safetensors.index.json"
        index.write_text(json.dumps(data))
        for api in (load_checkpoint_in_model, load_checkpoint_and_dispatch):
            for argument in (folder, index):
                with self.subTest(api=api.__name__, argument=argument.name, data=data):
                    # A regression must fail immediately rather than open a FIFO.
                    with patch(
                        "accelerate.utils.modeling.load_state_dict",
                        side_effect=AssertionError("Unsafe shard reached deserializer"),
                    ) as loader:
                        with self.assertRaises(ValueError):
                            api(self.new_model(), str(argument), device_map={"": "cpu"})
                        loader.assert_not_called()

    def test_malformed_indexes_and_cross_platform_paths_rejected(self):
        folder = self.root / "invalid"
        folder.mkdir()
        for data in (
            [],
            None,
            "x",
            42,
            {},
            {"weight_map": []},
            {"weight_map": None},
            {"weight_map": {}},
            {"weight_map": {"weight": None}},
            {"weight_map": {"weight": 1}},
            {"weight_map": {"weight": []}},
            {"weight_map": {"weight": {}}},
            {"weight_map": {"weight": ""}},
            {"weight_map": {"weight": "bad\0.safetensors"}},
        ):
            self.assert_bad_index_rejected(folder, data)
        for name in (
            "../outside.safetensors",
            "nested/../../outside.safetensors",
            "/outside.safetensors",
            "C:/outside.safetensors",
            "C:outside.safetensors",
            r"C:\outside.safetensors",
            r"..\outside.safetensors",
            r"\\server\share\outside.safetensors",
            "//server/share/outside",
        ):
            self.assert_bad_index_rejected(folder, {"weight_map": {"weight": name}})

    def test_fifo_missing_directories_and_external_symlinks_rejected(self):
        folder = self.root / "invalid"
        folder.mkdir()
        os.mkfifo(folder / "fifo.safetensors")
        (folder / "directory.safetensors").mkdir()
        outside = self.root / "outside.safetensors"
        outside.write_bytes(b"fixture")
        (folder / "outside-link.safetensors").symlink_to(outside)
        (folder / "outside-directory").symlink_to(self.root, target_is_directory=True)
        (folder / "fifo-link.safetensors").symlink_to("fifo.safetensors")
        (folder / "missing-link.safetensors").symlink_to("missing.safetensors")
        for name in (
            "fifo.safetensors",
            "directory.safetensors",
            "missing.safetensors",
            "outside-link.safetensors",
            "outside-directory/outside.safetensors",
            "fifo-link.safetensors",
            "missing-link.safetensors",
        ):
            self.assert_bad_index_rejected(folder, {"weight_map": {"weight": name}})
        (folder / "a.safetensors").write_bytes(b"fixture")
        self.assert_bad_index_rejected(
            folder,
            {"weight_map": {"weight": "a.safetensors", "bias": "fifo.safetensors"}},
        )

    def test_hub_subfolder_outside_and_redirected_blob_links_rejected(self):
        repo = self.root / "models--test--model"
        snapshot = repo / "snapshots" / ("a" * 40)
        folder = snapshot / "component" / "nested"
        folder.mkdir(parents=True)
        blobs = repo / "blobs"
        blobs.mkdir()
        digest = "b" * 64
        outside = self.root / digest
        outside.write_bytes(b"fixture")
        other = self.root / "other-cache" / "blobs" / digest
        other.parent.mkdir(parents=True)
        other.write_bytes(b"fixture")
        unhashed = blobs / "not-a-hash"
        unhashed.write_bytes(b"fixture")
        sibling = snapshot / "sibling.safetensors"
        sibling.write_bytes(b"fixture")
        for i, target in enumerate((outside, other, unhashed, sibling)):
            name = f"{i}.safetensors"
            (folder / name).symlink_to(os.path.relpath(target, folder))
            self.assert_bad_index_rejected(folder, {"weight_map": {"weight": name}})
        target = blobs / digest
        (folder / "shard.safetensors").symlink_to(os.path.relpath(target, folder))
        os.mkfifo(target)
        self.assert_bad_index_rejected(
            folder, {"weight_map": {"weight": "shard.safetensors"}}
        )
        target.unlink()
        target.symlink_to(outside)
        self.assert_bad_index_rejected(
            folder, {"weight_map": {"weight": "shard.safetensors"}}
        )
        target.unlink()
        unhashed.unlink()
        blobs.rmdir()
        blobs.symlink_to(self.root, target_is_directory=True)
        self.assert_bad_index_rejected(
            folder, {"weight_map": {"weight": "shard.safetensors"}}
        )

    def test_snapshot_lookalikes_do_not_allow_external_links(self):
        repo = self.root / "models--test--model"
        folder = repo / "snapshots" / "not-a-commit" / "component"
        folder.mkdir(parents=True)
        target = repo / "blobs" / ("b" * 64)
        target.parent.mkdir()
        target.write_bytes(b"fixture")
        (folder / "shard.safetensors").symlink_to(os.path.relpath(target, folder))
        self.assert_bad_index_rejected(
            folder, {"weight_map": {"weight": "shard.safetensors"}}
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
