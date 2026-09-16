# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""FFmpeg selection, rejection and dataset provenance without a real codec/GPU."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

PIPELINE = Path(__file__).resolve().parents[1]
CONVERSION = PIPELINE / "pipeline/conversion"
spec = importlib.util.spec_from_file_location("ffmpeg_contract", CONVERSION / "ffmpeg_contract.py")
codec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codec)


def test_gpl_build_is_allowed_and_required_cpu_encode_is_exercised(fake_ffmpeg):
    executable, log = fake_ffmpeg()
    provenance = codec.check_ffmpeg(str(executable))
    assert provenance["executable"] == str(executable.resolve())
    assert provenance["executable_sha256"] == hashlib.sha256(executable.read_bytes()).hexdigest()
    assert "--enable-gpl" in provenance["configuration"]
    probe = json.loads(log.read_text().splitlines()[-1])
    for flag, value in (("-vf", "scale=320:180"), ("-c:v", "libx264"), ("-f", "rawvideo")):
        assert probe[probe.index(flag) + 1] == value
    assert ["-f", "mp4"] == probe[probe.index("mp4") - 1:probe.index("mp4") + 1]


@pytest.mark.parametrize("settings,expected", [
    ({"configuration": "--enable-gpl --enable-nonfree --enable-libx264"}, "nonfree build"),
    ({"license_report": "This version of ffmpeg has nonfree parts compiled in; it is nonfree and unredistributable."}, "nonfree build"),
    ({"configuration": None}, "Cannot identify"),
    ({"license_report": "Unknown license"}, "Cannot identify"),
    ({"smoke_error": "Unknown encoder 'libx264'"}, "CPU scale, libx264 and MP4"),
    ({"smoke_error": "No such filter: scale"}, "CPU scale, libx264 and MP4"),
    ({"smoke_error": "Requested output format 'mp4' is not known"}, "CPU scale, libx264 and MP4"),
    ({"invalid_mp4": True}, "no recognizable MP4"),
])
def test_rejects_nonfree_unverifiable_or_incapable_build_before_output(tmp_path, fake_ffmpeg, settings, expected):
    executable, _ = fake_ffmpeg(**settings)
    source = tmp_path / "raw"
    (source / "ep_000").mkdir(parents=True)
    destination = tmp_path / "dataset"
    result = subprocess.run([
        sys.executable, str(CONVERSION / "convert_pgfr_to_lerobot.py"),
        "--src-root", str(source), "--dst", str(destination), "--ffmpeg", str(executable),
    ], capture_output=True, text=True)
    assert result.returncode != 0 and expected in result.stderr
    assert not destination.exists()


def test_missing_executable_has_actionable_selection_error(tmp_path):
    with pytest.raises(codec.FFmpegError, match="PGFR_FFMPEG_BIN"):
        codec.check_ffmpeg(str(tmp_path / "missing"))


def test_explicit_executable_overrides_environment_for_every_encode(tmp_path, fake_ffmpeg, monkeypatch):
    executable, log = fake_ffmpeg()
    monkeypatch.setenv("PGFR_FFMPEG_BIN", str(tmp_path / "unavailable-default"))
    assert codec.default_executable() == str(tmp_path / "unavailable-default")
    source = tmp_path / "raw"
    episode = source / "ep_000"
    episode.mkdir(parents=True)
    states = [{"i": i, "t": i / 15, "fl_joints": [0] * 7 + [.04],
               "fl_action": [0] * 7 + [.016], "fl_action_source": "observed_exact_applied_joint_target"}
              for i in range(45)]
    (episode / "states.json").write_text(json.dumps(states))
    (episode / "task.txt").write_text("pick green")
    for camera in ("wrist", "outside"):
        (episode / camera).mkdir()
        for index in range(45):
            (episode / camera / f"{index:04d}.jpg").write_bytes(b"synthetic camera fixture")
    destination = tmp_path / "dataset"
    subprocess.run([
        sys.executable, str(CONVERSION / "convert_pgfr_to_lerobot.py"),
        "--src-root", str(source), "--dst", str(destination), "--ffmpeg", str(executable),
        "--require-command-actions", "--required-action-source", "observed_exact_applied_joint_target",
        "--strict-frame-sequences",
    ], capture_output=True, text=True, check=True)
    provenance = json.loads((destination / "meta/ffmpeg_provenance.json").read_text())
    assert provenance["executable"] == str(executable.resolve())
    calls = [json.loads(row) for row in log.read_text().splitlines()]
    conversions = [call for call in calls if "-y" in call]
    assert len(conversions) == 2
    assert len(list(destination.glob("videos/*/*/*.mp4"))) == 2
    assert {call[call.index("-i") + 1] for call in conversions} == {
        str(episode / camera / "%04d.jpg") for camera in ("wrist", "outside")}
