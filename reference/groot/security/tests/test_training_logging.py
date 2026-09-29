# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Exercise W&B and Hugging Face logging without GitPython, credentials or cloud access."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def logging_worker(root: Path) -> None:
    """Run in a subprocess so SDK state and user settings cannot leak into tests."""
    import importlib.metadata

    import torch
    from transformers import Trainer, TrainingArguments
    import wandb
    from wandb.sdk.lib.gitlib import GitRepo

    assert wandb.__version__ == "0.30.0"
    for name in ("gitpython", "gitdb", "smmap"):
        try:
            importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
        else:
            raise AssertionError(f"Removed dependency is installed: {name}")
    assert importlib.util.find_spec("git") is None

    # Git metadata now uses the Git executable, exercised against a local fixture.
    repository = root / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    (repository / "fixture.txt").write_text("training metadata fixture\n")
    subprocess.run(["git", "-C", str(repository), "add", "fixture.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "-c", "user.name=PGFR test", "-c", "user.email=pgfr-test@example.invalid", "commit", "-qm", "fixture"],
        check=True,
    )
    expected_commit = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    git = GitRepo(root=str(repository))
    assert git.root_dir == str(repository)
    assert git.commit_for_ref("HEAD") == expected_commit
    assert not git.has_tracked_changes()

    # These arguments match GR00T's experiment.run logging entry point.
    run = wandb.init(
        project="pgfr-offline-regression", name="training-api", mode="offline",
        config={"git_commit_hash": expected_commit, "learning_rate": 0.001},
        tags=["finetune"], dir=str(root),
        settings=wandb.Settings(disable_git=True, disable_code=True, x_disable_stats=True, x_disable_meta=True, console="off"),
    )
    assert run.settings.mode == "offline"
    assert run.config["git_commit_hash"] == expected_commit
    run.log({"smoke/loss": 0.5})

    class TinyModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.projection = torch.nn.Linear(2, 1)

        def forward(self, input_ids, labels):
            logits = self.projection(input_ids.float())
            return {"loss": torch.nn.functional.mse_loss(logits, labels.float()), "logits": logits}

        def num_parameters(self):
            return sum(parameter.numel() for parameter in self.parameters())

    torch.manual_seed(7)
    args = TrainingArguments(
        output_dir=str(root / "trainer"), report_to=["wandb"], use_cpu=True,
        max_steps=2, per_device_train_batch_size=1, logging_steps=1,
        save_strategy="no", disable_tqdm=True,
    )
    samples = [{"input_ids": torch.tensor([1.0, 2.0]), "labels": torch.tensor([0.5])}] * 2
    trainer = Trainer(model=TinyModel(), args=args, train_dataset=samples)
    result = trainer.train()
    assert result.global_step == 2
    assert run.config["model/num_parameters"] == 3
    artifact_file = root / "checkpoint-note.txt"
    artifact_file.write_text("offline artifact compatibility\n")
    artifact = wandb.Artifact("pgfr-checkpoint-note", type="model")
    artifact.add_file(str(artifact_file))
    run.log_artifact(artifact, aliases=["final_model"])
    assert isinstance(run.summary["train_loss"], float)
    run.summary["regression_complete"] = True
    run.finish()
    assert wandb.run is None

    # Verify real persisted metric records, not just a mocked callback invocation.
    records = list(root.glob("wandb/offline-run-*/run-*.wandb"))
    assert len(records) == 1, records
    history = {"smoke/loss", "train/loss", "train/global_step"}
    recorded = records[0].read_bytes()
    assert all(name.encode() in recorded for name in history)
    print("PGFR_LOGGING_RESULT=" + json.dumps({"wandb": wandb.__version__, "torch": torch.__version__, "steps": result.global_step, "metrics": sorted(history), "gitpython_absent": True}))


@unittest.skipUnless(importlib.util.find_spec("wandb"), "requires the optional logging regression dependencies")
class TrainingLoggingTests(unittest.TestCase):
    def test_offline_training_logging_without_gitpython(self):
        with tempfile.TemporaryDirectory(prefix="pgfr-logging-") as directory:
            root = Path(directory)
            netrc = root / "empty.netrc"
            netrc.touch(mode=0o600)
            environment = {
                "PATH": os.environ.get("PATH", os.defpath),
                "WANDB_MODE": "offline", "WANDB_SILENT": "true",
                "WANDB_BASE_URL": "http://127.0.0.1:9",
                "WANDB_CONFIG_DIR": str(root / "config"),
                "WANDB_CACHE_DIR": str(root / "cache"),
                "WANDB_DATA_DIR": str(root / "data"),
                "WANDB_LOG_MODEL": "false", "WANDB_WATCH": "false",
                "NETRC": str(netrc), "CUDA_VISIBLE_DEVICES": "",
                "OTEL_SDK_DISABLED": "true", "OTEL_TRACES_EXPORTER": "none",
                "OTEL_METRICS_EXPORTER": "none", "OTEL_LOGS_EXPORTER": "none",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            }
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--worker", directory],
                cwd=root, env=environment, capture_output=True, text=True, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            line = next(line for line in result.stdout.splitlines() if line.startswith("PGFR_LOGGING_RESULT="))
            result_data = json.loads(line.split("=", 1)[1])
            self.assertEqual(result_data["wandb"], "0.30.0")
            self.assertTrue(result_data["gitpython_absent"])
            self.assertEqual(result_data["steps"], 2)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        logging_worker(Path(sys.argv[2]))
    else:
        unittest.main()
