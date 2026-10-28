# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Exercise local dataset persistence and the training interface without downloads."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec("datasets"), "requires dataset regression dependencies")
class DatasetCompatibilityTests(unittest.TestCase):
    def test_parquet_persistence_and_streaming_preserve_samples(self):
        from datasets import Dataset, load_dataset, load_from_disk

        samples = {"state": [[1.0, 2.0], [3.0, 4.0]], "task": ["move green", "move red"]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Dataset.from_dict(samples)
            parquet = root / "episode.parquet"
            source.to_parquet(parquet)
            loaded = Dataset.from_parquet(str(parquet))
            self.assertEqual(loaded.to_dict(), samples)
            loaded.save_to_disk(str(root / "saved"))
            self.assertEqual(load_from_disk(str(root / "saved")).to_dict(), samples)
            streamed = load_dataset(
                "parquet", data_files=str(parquet), split="train", streaming=True,
                cache_dir=str(root / "cache"),
            )
            self.assertEqual(list(streamed), list(source))

    def test_dataset_batches_reach_trainer_and_update_weights(self):
        from datasets import Dataset
        import torch
        from transformers import Trainer, TrainingArguments

        class TinyModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.projection = torch.nn.Linear(2, 1)

            def forward(self, input_ids, labels):
                predictions = self.projection(input_ids.float())
                return {"loss": torch.nn.functional.mse_loss(predictions, labels.float())}

        torch.manual_seed(7)
        model = TinyModel()
        before = model.projection.weight.detach().clone()
        dataset = Dataset.from_dict({
            "input_ids": [[1.0, 2.0], [2.0, 1.0]],
            "labels": [[0.5], [0.8]],
            "episode_note": ["unused metadata", "unused metadata"],
        })
        with tempfile.TemporaryDirectory() as directory:
            arguments = TrainingArguments(
                output_dir=directory, use_cpu=True, max_steps=1,
                per_device_train_batch_size=2, learning_rate=0.01,
                save_strategy="no", report_to=[], disable_tqdm=True,
                dataloader_pin_memory=False,
            )
            result = Trainer(model=model, args=arguments, train_dataset=dataset).train()
        self.assertEqual(result.global_step, 1)
        self.assertTrue(torch.isfinite(torch.tensor(result.training_loss)))
        self.assertFalse(torch.equal(before, model.projection.weight.detach()))


if __name__ == "__main__":
    unittest.main()
