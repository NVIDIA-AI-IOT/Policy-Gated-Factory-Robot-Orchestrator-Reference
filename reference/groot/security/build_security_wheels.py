#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Build hash-pinned downstream pure-Python wheels without modifying an environment."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile


class BuildError(ValueError):
    """A security artifact failed validation."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_hash(data: bytes, expected: str, label: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected or "") or sha256(data) != expected:
        raise BuildError(f"SHA256 mismatch: {label}")


def safe_name(name: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or "\0" in name
        or ":" in name
        or name.startswith("/")
        or any(part in ("", ".", "..") for part in name.split("/"))
    ):
        raise BuildError(f"Unsafe archive or asset path: {name!r}")
    return name


def read_asset(root: Path, descriptor: dict) -> bytes:
    relative = safe_name(descriptor["path"])
    path = root / relative
    if (
        path.is_symlink()
        or not path.is_file()
        or not path.resolve().is_relative_to(root.resolve())
    ):
        raise BuildError(f"Asset must be a contained regular file: {relative}")
    data = path.read_bytes()
    require_hash(data, descriptor["sha256"], relative)
    return data


def read_verified(path: Path, expected: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise BuildError(f"Expected a regular file: {path}")
    data = path.read_bytes()
    require_hash(data, expected, str(path))
    return data


def validate_entry(entry: dict) -> None:
    name, base, version = entry["name"], entry["base_version"], entry["version"]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise BuildError("Invalid package name")
    if not re.fullmatch(r"\d+\.\d+\.\d+", base) or version != base + "+pgfr.security1":
        raise BuildError("Expected an unchanged base API version with +pgfr.security1")
    for descriptor, wanted in (
        (entry["upstream"], f"{name}-{base}-py3-none-any.whl"),
        (entry["wheel"], f"{name}-{version}-py3-none-any.whl"),
    ):
        if descriptor["filename"] != wanted:
            raise BuildError(f"Unexpected wheel filename: {descriptor['filename']}")
        if not re.fullmatch(r"[0-9a-f]{64}", descriptor["sha256"]):
            raise BuildError("Missing pinned wheel SHA256")
    url = urllib.parse.urlsplit(entry["upstream"]["url"])
    if (
        url.scheme != "https"
        or url.hostname != "files.pythonhosted.org"
        or url.username
        or url.fragment
    ):
        raise BuildError("Upstream URL must identify the pinned PyPI wheel")
    if not entry["patch"]["files"]:
        raise BuildError("A patch must declare its modified files")
    for name in entry["patch"]["files"]:
        if not safe_name(name).startswith(entry["name"] + "/"):
            raise BuildError("Patch targets must remain inside the package")


def apply_exact_patch(files: dict[str, bytes], patch: bytes, expected: dict) -> None:
    """Apply a unified diff with exact context; no shell, extraction, offsets or fuzz."""
    lines = patch.decode("utf-8").splitlines(keepends=True)
    cursor, changed = 0, set()
    while cursor < len(lines):
        if not lines[cursor].startswith("--- a/") or cursor + 1 >= len(lines):
            raise BuildError("Expected a unified-diff source header")
        path = safe_name(lines[cursor][6:].rstrip("\n"))
        if (
            lines[cursor + 1] != f"+++ b/{path}\n"
            or path not in expected
            or path in changed
        ):
            raise BuildError(f"Unexpected or repeated patch target: {path}")
        if path not in files:
            raise BuildError(f"Patch target is absent: {path}")
        require_hash(files[path], expected[path]["before"], f"before {path}")
        source = files[path].decode("utf-8").splitlines(keepends=True)
        output, old_position = [], 0
        cursor += 2
        hunks = 0
        while cursor < len(lines) and lines[cursor].startswith("@@ "):
            match = re.fullmatch(
                r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n", lines[cursor]
            )
            if not match:
                raise BuildError(f"Invalid patch hunk: {path}")
            old_start, old_count, new_start, new_count = (
                int(value) if value is not None else 1 for value in match.groups()
            )
            start = old_start - (old_count != 0)
            if start < old_position or start > len(source):
                raise BuildError(f"Invalid hunk offset: {path}")
            output.extend(source[old_position:start])
            old_position = start
            if len(output) != new_start - (new_count != 0):
                raise BuildError(f"Invalid output hunk offset: {path}")
            old_used = new_used = 0
            cursor += 1
            while old_used < old_count or new_used < new_count:
                if cursor >= len(lines) or lines[cursor][:1] not in (" ", "+", "-"):
                    raise BuildError(f"Truncated patch hunk: {path}")
                kind, text = lines[cursor][0], lines[cursor][1:]
                if kind in (" ", "-"):
                    if old_position >= len(source) or source[old_position] != text:
                        raise BuildError(f"Patch context does not match: {path}")
                    old_position += 1
                    old_used += 1
                if kind in (" ", "+"):
                    output.append(text)
                    new_used += 1
                if old_used > old_count or new_used > new_count:
                    raise BuildError(f"Patch hunk count does not match: {path}")
                cursor += 1
            hunks += 1
        if not hunks:
            raise BuildError(f"Patch has no hunks: {path}")
        output.extend(source[old_position:])
        result = "".join(output).encode("utf-8")
        require_hash(result, expected[path]["after"], f"after {path}")
        files[path] = result
        changed.add(path)
    if changed != set(expected):
        raise BuildError("Patch modified-file list does not match the manifest")


def wheel_bytes(entry: dict, root: Path, upstream: bytes) -> bytes:
    """Return a deterministic wheel; callers must verify its final pinned hash."""
    validate_entry(entry)
    patch = read_asset(root, entry["patch"])
    notice = read_asset(root, entry["notice"])
    require_hash(upstream, entry["upstream"]["sha256"], "upstream wheel")
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(upstream)) as archive:
        seen = set()
        for info in archive.infolist():
            name = safe_name(
                info.filename.rstrip("/") if info.is_dir() else info.filename
            )
            if name in seen or stat.S_ISLNK(info.external_attr >> 16):
                raise BuildError(f"Duplicate or symlink wheel member: {name}")
            seen.add(name)
            if not info.is_dir():
                files[name] = archive.read(info)
    old_dist = f"{entry['name']}-{entry['base_version']}.dist-info"
    new_dist = f"{entry['name']}-{entry['version']}.dist-info"
    metadata_path = f"{old_dist}/METADATA"
    if metadata_path not in files or f"{old_dist}/RECORD" not in files:
        raise BuildError("Missing upstream distribution metadata")
    for name in files:
        if not (
            name.startswith(entry["name"] + "/") or name.startswith(old_dist + "/")
        ):
            raise BuildError(f"Unexpected upstream wheel member: {name}")
    wheel_metadata = files.get(f"{old_dist}/WHEEL", b"")
    if (
        b"Root-Is-Purelib: true\n" not in wheel_metadata
        or b"Tag: py3-none-any\n" not in wheel_metadata
    ):
        raise BuildError("Only pure-Python py3-none-any wheels are supported")
    if not any(
        PurePosixPath(name).name.upper().startswith("LICENSE") for name in files
    ):
        raise BuildError("Upstream wheel has no license file")
    apply_exact_patch(files, patch, entry["patch"]["files"])
    header, separator, description = files[metadata_path].partition(b"\n\n")
    old_version = f"Version: {entry['base_version']}".encode()
    headers = header.split(b"\n")
    if headers.count(old_version) != 1 or not separator:
        raise BuildError("Upstream metadata version does not match")
    headers[headers.index(old_version)] = f"Version: {entry['version']}".encode()
    headers.append(b"License-File: NOTICE-PGFR")
    files[metadata_path] = b"\n".join(headers) + separator + description
    del files[f"{old_dist}/RECORD"]
    for suffix in ("RECORD.jws", "RECORD.p7s"):
        files.pop(f"{old_dist}/{suffix}", None)
    files = {
        new_dist + name[len(old_dist) :]
        if name.startswith(old_dist + "/")
        else name: data
        for name, data in files.items()
    }
    notice_path = f"{new_dist}/licenses/NOTICE-PGFR"
    if notice_path in files:
        raise BuildError("Downstream notice would overwrite an existing artifact")
    files[notice_path] = notice
    record_path = f"{new_dist}/RECORD"
    records = io.StringIO(newline="")
    writer = csv.writer(records, lineterminator="\n")
    for name, data in sorted(files.items()):
        digest = (
            base64.urlsafe_b64encode(hashlib.sha256(data).digest())
            .rstrip(b"=")
            .decode()
        )
        writer.writerow((name, "sha256=" + digest, len(data)))
    writer.writerow((record_path, "", ""))
    files[record_path] = records.getvalue().encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def materialize(
    entry: dict, root: Path, output: Path, upstream_dir: Path | None, check: bool
) -> Path:
    validate_entry(entry)
    read_asset(root, entry["patch"])
    read_asset(root, entry["notice"])
    target = output / entry["wheel"]["filename"]
    if target.exists() or target.is_symlink():
        read_verified(target, entry["wheel"]["sha256"])
        return target
    if check:
        raise BuildError(f"Security wheel is missing: {target}")
    if upstream_dir is not None:
        data = read_verified(
            upstream_dir / entry["upstream"]["filename"], entry["upstream"]["sha256"]
        )
    else:
        with urllib.request.urlopen(entry["upstream"]["url"], timeout=60) as response:
            data = response.read()
    rebuilt = wheel_bytes(entry, root, data)
    require_hash(rebuilt, entry["wheel"]["sha256"], "rebuilt wheel")
    # All artifact checks finish before creating or changing the output directory.
    output.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".security-wheel-", dir=output)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(rebuilt)
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=Path(__file__).with_name("manifest.json")
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--upstream-dir",
        type=Path,
        help="Read upstream wheels here instead of using the network",
    )
    parser.add_argument(
        "--package", action="append", help="Build/check only this package (repeatable)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify existing artifacts without building/downloading",
    )
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        if manifest["schema_version"] != 1:
            raise BuildError("Unsupported security manifest version")
        entries = {entry["name"]: entry for entry in manifest["packages"]}
        if len(entries) != len(manifest["packages"]):
            raise BuildError("Duplicate package names in manifest")
        selected = args.package or list(entries)
        if not selected or any(name not in entries for name in selected):
            raise BuildError("Requested security package is absent from the manifest")
        for name in selected:
            path = materialize(
                entries[name],
                args.manifest.parent,
                args.output_dir,
                args.upstream_dir,
                args.check,
            )
            print(f"Verified {name}: {path}")
    except (
        BuildError,
        OSError,
        KeyError,
        TypeError,
        UnicodeError,
        zipfile.BadZipFile,
    ) as error:
        parser.exit(1, f"security-wheel: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
