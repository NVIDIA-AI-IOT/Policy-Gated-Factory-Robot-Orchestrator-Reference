# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Select and check the local CPU encoder used by dataset conversion."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


class FFmpegError(RuntimeError):
    pass


def default_executable() -> str:
    return os.environ.get("PGFR_FFMPEG_BIN", "ffmpeg")


def _run(executable: str, args: list[str], data: bytes | None = None) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            [executable, "-hide_banner", *args], input=data,
            capture_output=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FFmpegError(f"FFmpeg preflight failed for {executable}: {exc}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[-1500:]
        raise FFmpegError(f"FFmpeg preflight failed for {executable}: {detail}")
    return result


def check_ffmpeg(requested: str) -> dict:
    """Reject reported nonfree builds and exercise scale/libx264/MP4 in memory.

    GPL builds are supported. This is a reproduction profile check, not a full
    license or shared-library audit. No dataset or temporary files are written.
    """
    selected = shutil.which(os.path.expanduser(requested))
    if selected is None:
        raise FFmpegError(
            f"FFmpeg executable not found: {requested!r}. Select your reviewed CPU build "
            "with --ffmpeg /absolute/path/to/ffmpeg or PGFR_FFMPEG_BIN."
        )
    executable = str(Path(selected).resolve(strict=True))
    version_probe = _run(executable, ["-version"])
    version_text = (version_probe.stdout + version_probe.stderr).decode("utf-8", errors="replace")
    license_probe = _run(executable, ["-L"])
    license_text = (license_probe.stdout + license_probe.stderr).decode("utf-8", errors="replace")
    reports = " ".join((version_text + " " + license_text).split())
    if "--enable-nonfree" in reports or "nonfree and unredistributable" in reports.lower():
        raise FFmpegError(
            f"Selected FFmpeg reports a nonfree build: {executable}. This reproduction "
            "profile requires a build without --enable-nonfree, with CPU scale, libx264 "
            "and MP4 support. GPL builds are allowed; select another reviewed executable "
            "with --ffmpeg or PGFR_FFMPEG_BIN."
        )
    configuration = re.search(r"^configuration:\s*(.*)$", version_text, flags=re.MULTILINE)
    if configuration is None or not any(name in reports for name in (
        "GNU Lesser General Public License", "GNU General Public License",
    )):
        raise FFmpegError(
            f"Cannot identify the FFmpeg configuration/license for {executable}; "
            "select a reviewed standard FFmpeg build with --ffmpeg or PGFR_FFMPEG_BIN."
        )
    # A pipe avoids creating an output before validation. Fragmented MP4 permits
    # non-seekable output; conversion later writes ordinary MP4 files.
    try:
        smoke = _run(executable, [
            "-loglevel", "error", "-filter_threads", "1", "-f", "rawvideo",
            "-pixel_format", "rgb24", "-video_size", "16x16", "-framerate", "15",
            "-i", "pipe:0", "-frames:v", "1", "-vf", "scale=320:180",
            "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p",
            "-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "pipe:1",
        ], bytes([24, 96, 160]) * (16 * 16))
    except FFmpegError as exc:
        raise FFmpegError(
            "Selected FFmpeg must support CPU scale, libx264 and MP4 encoding. "
            "Choose a compatible executable with --ffmpeg or PGFR_FFMPEG_BIN. " + str(exc)
        ) from exc
    if len(smoke.stdout) < 16 or smoke.stdout[4:8] != b"ftyp":
        raise FFmpegError(f"FFmpeg CPU encoding probe produced no recognizable MP4: {executable}")
    digest = hashlib.sha256()
    with open(executable, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "schema_version": 1,
        "executable": executable,
        "executable_sha256": digest.hexdigest(),
        "version_report": version_text.strip(),
        "configuration": configuration.group(1).strip(),
        "license_report": license_text.strip(),
        "cpu_encode_probe": "16x16 RGB -> scale=320:180 -> libx264/yuv420p -> fragmented MP4",
        "scope": "Executable report/hash and CPU encode check; linked libraries and redistribution rights require separate review.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", default=default_executable(), help="Executable path/name; defaults to PGFR_FFMPEG_BIN or PATH ffmpeg.")
    args = parser.parse_args()
    try:
        provenance = check_ffmpeg(args.ffmpeg)
    except FFmpegError as exc:
        parser.error(str(exc))
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
