# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Synthetic offline contracts; no simulator, model, ROS, or GPU operations."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

PIPELINE = Path(__file__).resolve().parents[1]
REFERENCE = PIPELINE.parents[1]


def load(relative):
    path = PIPELINE / relative
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("pipeline/conversion/build_native_droid_dataset.py")
launcher = load("pipeline/training/launch_finetune.py")
prepare = load("pipeline/capture/prepare_capture.py")


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def joint_data(tmp_path):
    source = tmp_path / "joint"
    parquet = source / "data/chunk-000/episode_000000.parquet"
    parquet.parent.mkdir(parents=True)
    rows = 45
    state = np.zeros((rows, 8), dtype=np.float32)
    state[:, :7] = np.arange(rows)[:, None] * .001
    state[:, 7] = .04
    action = state.copy()
    action[:, :7] += .01
    action[:, 7] = .016
    pd.DataFrame({"observation.state": list(state), "action": list(action),
                  "timestamp": np.arange(rows) / 15, "frame_index": range(rows),
                  "episode_index": [0] * rows, "index": range(rows),
                  "task_index": [0] * rows}).to_parquet(parquet, index=False)
    dump(source / "meta/info.json", {"fps": 15})
    dump(source / "meta/episodes.jsonl", {"episode_index": 0, "length": rows, "tasks": ["pick green"]})
    dump(source / "meta/tasks.jsonl", {"task_index": 0, "task": "pick green"})
    for camera in ("front", "wrist"):
        path = source / f"videos/chunk-000/observation.images.{camera}/episode_000000.mp4"
        path.parent.mkdir(parents=True)
        # Not a playable video: these tests only exercise converter bookkeeping.
        path.write_bytes(b"synthetic video fixture")
    request = tmp_path / "request.json"
    builder.export_joint_request(source, request)
    episode = json.loads(request.read_text())["episodes"][0]
    pose = {"position": np.zeros((rows, 3)).tolist(), "rotation": np.tile(np.eye(3), (rows, 1, 1)).tolist()}
    fk = tmp_path / "fk.json"
    dump(fk, {"schema_version": 1, "frame": "panda_link8", "episodes": [{
        "episode_index": 0, "source_file": parquet.name,
        "source_sha256": episode["source_sha256"], "state": pose, "action": pose,
    }]})
    return source, fk


def write_fixture_stats(root):
    # Deliberately synthetic values to test schema rejection; never training inputs.
    for filename, shapes in (("stats.json", {"observation.state": (17,), "action": (17,)}),
                             ("relative_stats.json", {"eef_9d": (40, 9), "joint_position": (40, 7)})):
        dump(root / "meta" / filename, {
            name: {key: np.ones(shape).tolist() for key in ("mean", "std", "min", "max", "q01", "q99")}
            for name, shape in shapes.items()
        })


def test_native_build_preserves_commands_and_requires_computed_stats(joint_data, tmp_path):
    source, fk = joint_data
    encoder_report = {"schema_version": 1, "executable_sha256": "1" * 64, "fixture": True}
    dump(source / "meta/ffmpeg_provenance.json", encoder_report)
    native = tmp_path / "native"
    builder.build_dataset(source, fk, native)
    assert json.loads((native / "meta/ffmpeg_provenance.json").read_text()) == encoder_report
    frame = pd.read_parquet(native / "data/chunk-000/episode_000000.parquet")
    state = np.stack(frame["observation.state"])
    action = np.stack(frame["action"])
    assert state.shape == action.shape == (45, 17)
    np.testing.assert_allclose(action[:, 10:] - state[:, 10:], .01, atol=1e-7)
    np.testing.assert_allclose(state[:, 9], 0)
    np.testing.assert_allclose(action[:, 9], 1)
    assert not (native / "meta/stats.json").exists()
    assert not (native / "meta/relative_stats.json").exists()
    with pytest.raises(FileNotFoundError):
        launcher.validate_dataset(native)
    write_fixture_stats(native)
    assert launcher.validate_dataset(native)["frames"] == 45


@pytest.mark.parametrize("change", ["source_hash", "rotation", "nan_joint"])
def test_native_rejects_invalid_fk_or_data(joint_data, tmp_path, change):
    source, fk = joint_data
    payload = json.loads(fk.read_text())
    if change == "source_hash":
        payload["episodes"][0]["source_sha256"] = "0" * 64
    elif change == "rotation":
        payload["episodes"][0]["state"]["rotation"][0][0][0] = 3
    else:
        path = source / "data/chunk-000/episode_000000.parquet"
        frame = pd.read_parquet(path)
        bad = list(frame["action"])
        bad[0] = bad[0].copy()
        bad[0][0] = np.nan
        frame["action"] = bad
        frame.to_parquet(path, index=False)
        payload["episodes"][0]["source_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    dump(fk, payload)
    with pytest.raises(ValueError):
        builder.build_dataset(source, fk, tmp_path / "native")
    if change == "source_hash":
        assert not (tmp_path / "native").exists()


@pytest.mark.parametrize("change", ["empty_stats", "nan_stats", "wrong_horizon", "missing_video", "wrong_total", "swapped_cameras"])
def test_training_rejects_incomplete_dataset(joint_data, tmp_path, change):
    source, fk = joint_data
    native = tmp_path / "native"
    builder.build_dataset(source, fk, native)
    write_fixture_stats(native)
    if change == "empty_stats":
        dump(native / "meta/stats.json", {})
    elif change in ("nan_stats", "wrong_horizon"):
        path = native / "meta/relative_stats.json"
        stats = json.loads(path.read_text())
        if change == "nan_stats":
            stats["eef_9d"]["mean"][0][0] = float("nan")
        else:
            stats["eef_9d"]["mean"] = stats["eef_9d"]["mean"][:-1]
        dump(path, stats)
    elif change == "missing_video":
        next(native.glob("videos/*/*/*.mp4")).unlink()
    elif change == "wrong_total":
        path = native / "meta/info.json"
        info = json.loads(path.read_text()); info["total_frames"] += 1
        dump(path, info)
    else:
        path = native / "meta/modality.json"
        modality = json.loads(path.read_text())
        modality["video"] = dict(reversed(list(modality["video"].items())))
        dump(path, modality)
    with pytest.raises(ValueError):
        launcher.validate_dataset(native)


def args(tmp_path, lr):
    return argparse.Namespace(dataset=[tmp_path / "data one", tmp_path / "data two"],
                              base_model=tmp_path / "checkpoint", output_dir=tmp_path / "trained",
                              learning_rate=lr, max_steps=3000, batch_size=16, workers=4)


def test_continuation_lr_reaches_actual_subprocess_argv(tmp_path):
    # A fixture downstream program receives the exact argv: no shell/environment
    # expansion, duplicate learning rate, or hidden experiment subdirectory.
    receiver = tmp_path / "receive.py"
    receiver.write_text("import json,sys; print(json.dumps(sys.argv[1:]))")
    for rate in (1e-4, 1e-5):
        command = launcher.build_command(args(tmp_path, rate))
        result = subprocess.run([sys.executable, str(receiver), *command[2:]], capture_output=True, text=True, check=True)
        actual = json.loads(result.stdout)
        assert actual.count("--learning-rate") == 1
        assert float(actual[actual.index("--learning-rate") + 1]) == rate
        assert "--experiment-name" not in actual
        assert actual[actual.index("--output-dir") + 1] == str(tmp_path / "trained")
        assert actual[actual.index("--dataset-path") + 1] == f"{tmp_path}/data one:{tmp_path}/data two"
        assert "--save-only-model" in actual and "--no-use-wandb" in actual


@pytest.mark.parametrize("rate", [0, -1, float("nan"), float("inf")])
def test_bad_learning_rate_is_rejected(tmp_path, rate):
    with pytest.raises(ValueError, match="learning-rate"):
        launcher.build_command(args(tmp_path, rate))


def test_converters_never_erase_existing_destination(tmp_path):
    source = tmp_path / "raw"; (source / "ep_000").mkdir(parents=True)
    destination = tmp_path / "existing"; destination.mkdir()
    sentinel = destination / "operator-data.txt"; sentinel.write_text("retain")
    result = subprocess.run([sys.executable, str(PIPELINE / "pipeline/conversion/convert_pgfr_to_lerobot.py"),
                             "--src-root", str(source), "--dst", str(destination)], capture_output=True, text=True)
    assert result.returncode != 0 and "refusing to overwrite" in result.stderr
    assert sentinel.read_text() == "retain"
    with pytest.raises(FileExistsError):
        builder.build_dataset(source, tmp_path / "missing-fk", destination)


def test_required_action_source_must_cover_every_frame(tmp_path, fake_ffmpeg):
    executable, _ = fake_ffmpeg()
    source = tmp_path / "raw"; episode = source / "ep_000"; episode.mkdir(parents=True)
    states = [{"i": i, "t": i / 15, "fl_joints": [0] * 7 + [.04],
               "fl_action": [0] * 7 + [.016], "fl_action_source": "observed_exact_applied_joint_target"}
              for i in range(45)]
    del states[20]["fl_action_source"]
    dump(episode / "states.json", states); (episode / "task.txt").write_text("pick green")
    result = subprocess.run([sys.executable, str(PIPELINE / "pipeline/conversion/convert_pgfr_to_lerobot.py"),
                             "--src-root", str(source), "--dst", str(tmp_path / "output"),
                             "--ffmpeg", str(executable), "--require-command-actions", "--required-action-source", "observed_exact_applied_joint_target"],
                            capture_output=True, text=True)
    assert result.returncode != 0 and "every frame must declare" in result.stderr


def test_capture_staging_is_new_mount_only(tmp_path):
    mount = tmp_path / "capture"
    prepare.prepare(mount, REFERENCE)
    assert (mount / "our_factory.usda").is_file()
    assert (mount / "native_droid_work/pgfr_sync_capture_cell.py").is_file()
    assert not list(mount.rglob("*follow_groot*"))
    assert not list(mount.rglob("*policy_contract*"))
    with pytest.raises(FileExistsError):
        prepare.prepare(mount, REFERENCE)


def ast_exec(nodes, scope):
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "fixture", "exec"), scope)


@pytest.mark.parametrize("settings,valid", [
    ({"PGFR_CAPTURE_ONLY": "1", "ROS_DOMAIN_ID": "83", "PGFR_CAMERA_PROFILE": "capture"}, True),
    ({"PGFR_CAPTURE_ONLY": "1", "ROS_DOMAIN_ID": "0", "PGFR_CAMERA_PROFILE": "capture"}, False),
    ({"ROS_DOMAIN_ID": "83", "PGFR_CAMERA_PROFILE": "capture"}, False),
    ({"PGFR_CAPTURE_ONLY": "1", "ROS_DOMAIN_ID": "83", "PGFR_CAMERA_PROFILE": "production"}, False),
])
def test_expert_guard_runs_before_any_scene_or_ros_initialization(settings, valid):
    path = REFERENCE / "isaac-cell/deployment/full_scene_bootstrap.py"
    nodes = ast.parse(path.read_text()).body
    first = next(i for i, n in enumerate(nodes) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "_scene_profile")
    stop = next(i for i, n in enumerate(nodes) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                and ast.unparse(n.value.func) == "_exec_setup")
    assert first < stop
    scope = {"_bootstrap_os": SimpleNamespace(environ={**settings, "PGFR_SCENE_PROFILE": "expert_capture"})}
    if valid:
        ast_exec(nodes[first:stop], scope)
        assert scope["_expert_capture"]
    else:
        with pytest.raises(RuntimeError):
            ast_exec(nodes[first:stop], scope)


@pytest.mark.parametrize("requested,cached", [("expert_capture", "groot_three_object"), ("groot_three_object", "expert_capture")])
def test_reset_cannot_switch_capture_profiles(requested, cached):
    path = REFERENCE / "groot/runtime/cell/reset_two_arm.py"
    nodes = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.Try)).body
    guard = next(n for n in nodes if isinstance(n, ast.If) and ast.unparse(n.test).startswith("_expert_capture or"))
    with pytest.raises(RuntimeError, match="fixed at isolated startup"):
        ast_exec([guard], {"_expert_capture": requested == "expert_capture", "_contract": {"scene_profile": cached},
                           "_camera_profile": "capture", "g": {"_PGFR_EXPERT_CAPTURE_CALLBACKS": (1, 2)},
                           "os": SimpleNamespace(environ={"PGFR_CAPTURE_ONLY": "1", "ROS_DOMAIN_ID": "83"})})


def test_expert_callback_branch_loads_no_learned_policy():
    path = REFERENCE / "groot/runtime/cell/reset_two_arm.py"
    nodes = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.Try)).body
    branch = next(n for n in nodes if isinstance(n, ast.If) and ast.unparse(n.test) == "_expert_capture")
    stock = {}; exec(compile("def start(): pass\ndef run_move(): pass\ndef finish(): pass", "/scripts/pgfr_node_v2.py", "exec"), stock)
    state = {"_PGFR_EXPERT_CAPTURE_CALLBACKS": (stock["start"], stock["run_move"]), "_PGFR_BASE_FINISH": stock["finish"]}
    scope = {"_expert_capture": True, "g": state}
    ast_exec([branch], scope)
    assert state["start"] is stock["start"] and state["run_move"] is stock["run_move"]
    assert scope["_executor_contexts"] == {} and not scope["_shared_executor_requested"]


def test_uncertain_capture_command_is_never_republished():
    path = PIPELINE / "pipeline/capture/record_pgfr_green_red_blue_staged_synced.py"
    function = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == "send_until_result")
    ticks = iter(i / 100 for i in range(100))
    sent = []
    scope = {"publisher": SimpleNamespace(get_subscription_count=lambda: 1),
             "time": SimpleNamespace(monotonic=lambda: next(ticks)), "send": sent.append,
             "rclpy": SimpleNamespace(spin_once=lambda *a, **k: None), "node": None,
             "state": {"result": None}, "goal_id": lambda result: None}
    ast_exec([function], scope)
    with pytest.raises(RuntimeError, match="completion unknown"):
        scope["send_until_result"]({"goal_id": "fixture", "action": "move"}, .1)
    assert len(sent) == 1


def test_documented_backbone_pin_is_exact_for_clean_offline_cache(tmp_path, monkeypatch):
    import re
    revision = "9ce19a195e423419c349abfc86fd07178b230561"
    snapshot = tmp_path / "models--nvidia--Cosmos-Reason2-2B" / "snapshots" / revision
    snapshot.mkdir(parents=True)
    calls = []
    def fake_download(repo_id, **kwargs):
        calls.append((repo_id, kwargs))
        return str(snapshot)
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=fake_download))
    recipe = (PIPELINE / "docs/FINETUNING_RECIPE.md").read_text()
    snippet = re.search(r"<<'PIN_BACKBONE'\n(.*?)\nPIN_BACKBONE", recipe, flags=re.S).group(1)
    exec(compile(snippet, "documented-backbone-pin", "exec"), {})
    assert calls == [("nvidia/Cosmos-Reason2-2B", {"revision": revision})]
    # Hugging Face uses the complete ref file as the snapshot name, so a
    # trailing newline would break a genuinely clean offline cache.
    assert (snapshot.parent.parent / "refs/main").read_bytes() == revision.encode()
