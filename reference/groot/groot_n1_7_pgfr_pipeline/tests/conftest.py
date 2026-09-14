# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Synthetic CPU codec fixture; it does not produce playable media."""
import json
import sys

import pytest


@pytest.fixture
def fake_ffmpeg(tmp_path):
    def create(*, configuration="--enable-gpl --enable-libx264", license_report=None,
               smoke_error="", invalid_mp4=False):
        executable = tmp_path / "selected encoder" / "ffmpeg"
        executable.parent.mkdir(exist_ok=True)
        log = executable.parent / "calls.jsonl"
        settings = {
            "configuration": configuration,
            "license": license_report or "ffmpeg is free software under the GNU General Public License version 2 or later",
            "smoke_error": smoke_error,
            "invalid_mp4": invalid_mp4,
            "log": str(log),
        }
        executable.write_text(f"#!{sys.executable}\n" + "import json,sys\nfrom pathlib import Path\n" +
            f"settings = json.loads({json.dumps(settings)!r})\n" + '''
args = sys.argv[1:]
with open(settings["log"], "a") as stream:
    stream.write(json.dumps(args) + "\\n")
if "-version" in args:
    print("ffmpeg version synthetic-offline-test")
    if settings["configuration"] is not None:
        print("configuration: " + settings["configuration"])
elif "-L" in args:
    print(settings["license"])
elif "pipe:1" in args:
    assert len(sys.stdin.buffer.read()) == 16 * 16 * 3
    if settings["smoke_error"]:
        print(settings["smoke_error"], file=sys.stderr)
        sys.exit(1)
    sys.stdout.buffer.write(b"invalid" if settings["invalid_mp4"] else b"\\x00\\x00\\x00\\x18ftypisom00000000")
else:
    Path(args[-1]).write_bytes(b"synthetic video fixture, not playable")
''')
        executable.chmod(0o755)
        return executable, log
    return create
