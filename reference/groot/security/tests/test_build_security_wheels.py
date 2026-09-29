# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free checks of integrity, patch application and wheel reproducibility."""

from __future__ import annotations

import base64
import copy
import csv
import difflib
import hashlib
import importlib.util
import io
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SPEC = importlib.util.spec_from_file_location(
    "security_wheels", Path(__file__).resolve().parents[1] / "build_security_wheels.py"
)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class SecurityWheelBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pgfr-security-wheel-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "output"
        self.old = b'__version__ = "1.2.3"\n\nvalue = "before"\n'
        self.new = b'__version__ = "1.2.3+pgfr.security1"\n\nvalue = "after"\n'
        self.files = {
            "sample/__init__.py": self.old,
            "sample-1.2.3.dist-info/METADATA": b"Metadata-Version: 2.4\nName: sample\nVersion: 1.2.3\nLicense-File: LICENSE\n\nDescription\n",
            "sample-1.2.3.dist-info/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            "sample-1.2.3.dist-info/RECORD": b"",
            "sample-1.2.3.dist-info/licenses/LICENSE": b"Fixture license text\n",
        }
        self.base = self.archive(self.files.items())
        patch_data = "".join(
            difflib.unified_diff(
                self.old.decode().splitlines(True),
                self.new.decode().splitlines(True),
                fromfile="a/sample/__init__.py",
                tofile="b/sample/__init__.py",
            )
        ).encode()
        self.entry = {
            "name": "sample",
            "base_version": "1.2.3",
            "version": "1.2.3+pgfr.security1",
            "upstream": {
                "filename": "sample-1.2.3-py3-none-any.whl",
                "url": "https://files.pythonhosted.org/packages/sample.whl",
                "sha256": builder.sha256(self.base),
            },
            "patch": {
                "path": "fix.patch",
                "sha256": builder.sha256(patch_data),
                "files": {
                    "sample/__init__.py": {
                        "before": builder.sha256(self.old),
                        "after": builder.sha256(self.new),
                    }
                },
            },
            "notice": {
                "path": "NOTICE",
                "sha256": builder.sha256(b"Downstream modifications\n"),
            },
            "wheel": {
                "filename": "sample-1.2.3+pgfr.security1-py3-none-any.whl",
                "sha256": "0" * 64,
            },
        }
        (self.root / "fix.patch").write_bytes(patch_data)
        (self.root / "NOTICE").write_bytes(b"Downstream modifications\n")
        (self.root / self.entry["upstream"]["filename"]).write_bytes(self.base)
        self.expected = builder.wheel_bytes(self.entry, self.root, self.base)
        self.entry["wheel"]["sha256"] = builder.sha256(self.expected)

    def archive(self, items):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, value in items:
                archive.writestr(name, value)
        return output.getvalue()

    def build(self, entry=None, check=False):
        return builder.materialize(
            entry or self.entry, self.root, self.output, self.root, check
        )

    def test_output_is_identical_across_repeated_builds_and_input_member_order(self):
        self.assertEqual(
            builder.wheel_bytes(self.entry, self.root, self.base), self.expected
        )
        reordered = self.archive(reversed(list(self.files.items())))
        entry = copy.deepcopy(self.entry)
        entry["upstream"]["sha256"] = builder.sha256(reordered)
        self.assertEqual(
            builder.wheel_bytes(entry, self.root, reordered), self.expected
        )
        self.assertEqual(self.build().read_bytes(), self.expected)

    def test_version_license_notice_and_record_integrity(self):
        prefix = "sample-1.2.3+pgfr.security1.dist-info/"
        with zipfile.ZipFile(io.BytesIO(self.expected)) as archive:
            self.assertEqual(archive.read("sample/__init__.py"), self.new)
            self.assertIn(
                b"Version: 1.2.3+pgfr.security1\n", archive.read(prefix + "METADATA")
            )
            self.assertEqual(
                archive.read(prefix + "licenses/LICENSE"), b"Fixture license text\n"
            )
            self.assertEqual(
                archive.read(prefix + "licenses/NOTICE-PGFR"),
                b"Downstream modifications\n",
            )
            rows = list(
                csv.reader(io.StringIO(archive.read(prefix + "RECORD").decode()))
            )
            self.assertEqual({row[0] for row in rows}, set(archive.namelist()))
            for name, digest, size in rows:
                if name.endswith("/RECORD"):
                    self.assertEqual((digest, size), ("", ""))
                else:
                    data = archive.read(name)
                    expected = (
                        base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                        .rstrip(b"=")
                        .decode()
                    )
                    self.assertEqual(digest, "sha256=" + expected)
                    self.assertEqual(int(size), len(data))
            for info in archive.infolist():
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))

    def test_final_hash_mismatch_never_creates_output_directory(self):
        entry = copy.deepcopy(self.entry)
        entry["wheel"]["sha256"] = "0" * 64
        with self.assertRaises(builder.BuildError):
            self.build(entry)
        self.assertFalse(self.output.exists())

    def test_upstream_patch_before_and_after_hashes_are_required(self):
        mutations = (
            lambda e: e["upstream"].update(sha256="0" * 64),
            lambda e: e["patch"].update(sha256="0" * 64),
            lambda e: e["patch"]["files"]["sample/__init__.py"].update(before="0" * 64),
            lambda e: e["patch"]["files"]["sample/__init__.py"].update(after="0" * 64),
            lambda e: e["notice"].update(sha256="0" * 64),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                entry = copy.deepcopy(self.entry)
                mutate(entry)
                with self.assertRaises(builder.BuildError):
                    self.build(entry)
                self.assertFalse(self.output.exists())

    def test_invalid_patch_context_and_unlisted_targets_are_rejected(self):
        original = (self.root / "fix.patch").read_bytes()
        for corrupted in (
            original.replace(b'-value = "before"', b'-value = "different"'),
            original.replace(b"sample/__init__.py", b"../escape.py"),
            original.replace(b"sample/__init__.py", b"sample/other.py"),
            original[:-15],
            original + original,
        ):
            with self.subTest(patch=corrupted):
                (self.root / "fix.patch").write_bytes(corrupted)
                entry = copy.deepcopy(self.entry)
                entry["patch"]["sha256"] = builder.sha256(corrupted)
                with self.assertRaises(builder.BuildError):
                    self.build(entry)
                self.assertFalse(self.output.exists())
        (self.root / "fix.patch").write_bytes(original)

    def test_archive_traversal_absolute_symlink_and_duplicate_names_rejected(self):
        symlink = zipfile.ZipInfo("sample/link.py")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        for extra in (
            ("../escape.py", b"bad"),
            ("/escape.py", b"bad"),
            ("sample\\escape.py", b"bad"),
            (symlink, b"../../escape"),
            ("sample/__init__.py", b"duplicate"),
        ):
            with self.subTest(member=extra[0]):
                with (
                    self.assertWarns(UserWarning)
                    if extra[0] == "sample/__init__.py"
                    else self.subTest()
                ):
                    bad = self.archive([*self.files.items(), extra])
                entry = copy.deepcopy(self.entry)
                entry["upstream"]["sha256"] = builder.sha256(bad)
                with self.assertRaises(builder.BuildError):
                    builder.wheel_bytes(entry, self.root, bad)
                self.assertFalse((self.root / "escape.py").exists())

    def test_asset_paths_cannot_escape_or_use_symlinks(self):
        for name in ("../fix.patch", "/fix.patch", "a/../fix.patch"):
            entry = copy.deepcopy(self.entry)
            entry["patch"]["path"] = name
            with self.assertRaises(builder.BuildError):
                self.build(entry)
        (self.root / "linked.patch").symlink_to("fix.patch")
        entry = copy.deepcopy(self.entry)
        entry["patch"]["path"] = "linked.patch"
        with self.assertRaises(builder.BuildError):
            self.build(entry)

    def test_check_and_verified_reuse_never_download(self):
        with patch.object(
            builder.urllib.request,
            "urlopen",
            side_effect=AssertionError("network forbidden"),
        ):
            with self.assertRaises(builder.BuildError):
                self.build(check=True)
            target = self.build()
            self.assertEqual(
                builder.materialize(self.entry, self.root, self.output, None, True),
                target,
            )
            self.assertEqual(
                builder.materialize(self.entry, self.root, self.output, None, False),
                target,
            )
            target.write_bytes(b"corrupted")
            for check in (False, True):
                with self.assertRaises(builder.BuildError):
                    builder.materialize(self.entry, self.root, self.output, None, check)
                self.assertEqual(target.read_bytes(), b"corrupted")

    def test_missing_offline_upstream_fails_without_output_changes(self):
        (self.root / self.entry["upstream"]["filename"]).unlink()
        with self.assertRaises(builder.BuildError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_unpinned_network_sources_and_nonlocal_versions_are_rejected(self):
        for field, value in (
            ("url", "http://files.pythonhosted.org/sample.whl"),
            ("url", "https://example.com/sample.whl"),
            ("filename", "unrelated.whl"),
        ):
            entry = copy.deepcopy(self.entry)
            entry["upstream"][field] = value
            with self.assertRaises(builder.BuildError):
                self.build(entry)
        entry = copy.deepcopy(self.entry)
        entry["version"] = "2.0.0"
        with self.assertRaises(builder.BuildError):
            self.build(entry)


if __name__ == "__main__":
    unittest.main()
