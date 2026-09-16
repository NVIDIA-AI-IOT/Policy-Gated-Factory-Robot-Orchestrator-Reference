# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Integrity and identity for explicitly supplied local GR00T checkpoints.

Checksums establish artifact consistency, not training quality or task success.
The two metadata files can be transferred without weights to the simulation host.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

METADATA_NAME = "pgfr_checkpoint.json"
EMBODIMENT_TAG = "OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT"
REQUIRED_JSON = {"config.json", "embodiment_id.json", "processor_config.json", "statistics.json"}
INDEX_NAME = "model.safetensors.index.json"


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required regular artifact is missing or is a symlink: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"artifact is empty: {path}")


def safe_name(name: object) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name):
        raise ValueError(f"unsafe artifact filename: {name!r}")
    return name


def json_object(path: Path) -> dict:
    regular_file(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not value:
        raise ValueError(f"artifact must contain a nonempty JSON object: {path}")
    return value


def validate_inventory(names: object) -> set[str]:
    if not isinstance(names, list) or not names:
        raise ValueError("checkpoint metadata requires inference_files")
    result = {safe_name(name) for name in names}
    if len(result) != len(names) or not REQUIRED_JSON <= result:
        raise ValueError("inference_files must be unique and contain all required JSON artifacts")
    weights = result - REQUIRED_JSON - {INDEX_NAME}
    if not weights or any(not name.endswith(".safetensors") for name in weights):
        raise ValueError("inference_files must declare safetensors weights only")
    if INDEX_NAME not in result and weights != {"model.safetensors"}:
        raise ValueError("sharded weights require model.safetensors.index.json")
    if INDEX_NAME in result and "model.safetensors" in weights:
        raise ValueError("checkpoint cannot mix sharded and unsharded weights")
    return result


def inference_files(root: Path) -> list[str]:
    for name in REQUIRED_JSON:
        json_object(root / name)
    names = set(REQUIRED_JSON)
    if (root / INDEX_NAME).exists():
        index = json_object(root / INDEX_NAME)
        weight_map = index.get("weight_map")
        if not isinstance(weight_map, dict) or not weight_map:
            raise ValueError("model index requires a nonempty weight_map")
        if any(not isinstance(key, str) or not key for key in weight_map):
            raise ValueError("model index has an invalid tensor name")
        names.add(INDEX_NAME)
        names.update(safe_name(name) for name in weight_map.values())
    else:
        names.add("model.safetensors")
    validate_inventory(sorted(names))
    for name in names:
        regular_file(root / name)
    unexpected_weights = {p.name for p in root.glob("*.safetensors")} - names
    if unexpected_weights:
        raise ValueError(f"unreferenced weights in checkpoint: {sorted(unexpected_weights)}")
    return sorted(names)


def read_identity(metadata_path: Path) -> dict:
    metadata_path = Path(metadata_path)
    if metadata_path.name != METADATA_NAME:
        raise ValueError(f"checkpoint metadata must be named {METADATA_NAME}")
    metadata = json_object(metadata_path)
    if type(metadata.get("schema_version")) is not int or metadata["schema_version"] != 1:
        raise ValueError("unsupported checkpoint metadata schema_version")
    if not isinstance(metadata.get("model_label"), str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,160}", metadata["model_label"]
    ):
        raise ValueError("checkpoint metadata requires a relay-safe model_label")
    if metadata.get("embodiment_tag") != EMBODIMENT_TAG:
        raise ValueError(f"checkpoint requires embodiment_tag {EMBODIMENT_TAG}")
    provenance = metadata.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("kind") != "user_trained":
        raise ValueError("checkpoint metadata requires user_trained provenance")
    for key in ("checkpoint", "dataset"):
        if not isinstance(provenance.get(key), str) or not provenance[key].strip():
            raise ValueError(f"checkpoint provenance requires {key}")
    names = validate_inventory(metadata.get("inference_files"))
    if "checkpoint_fingerprint" in metadata:
        raise ValueError("checkpoint_fingerprint is derived from SHA256SUMS, not stored in metadata")
    sums_path = metadata_path.parent / "SHA256SUMS"
    regular_file(sums_path)
    sums_bytes = sums_path.read_bytes()
    sums = {}
    for line in sums_bytes.decode("ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_][A-Za-z0-9_.-]*)", line)
        if not match or match[2] in sums:
            raise ValueError("SHA256SUMS contains malformed or duplicate entries")
        sums[match[2]] = match[1]
    if set(sums) != names | {METADATA_NAME}:
        raise ValueError("SHA256SUMS must cover exactly every inference artifact and checkpoint metadata")
    if digest_file(metadata_path) != sums[METADATA_NAME]:
        raise ValueError("checkpoint metadata checksum mismatch")
    return {**metadata, "checkpoint_fingerprint": hashlib.sha256(sums_bytes).hexdigest()}


def verify_checkpoint(root: Path) -> dict:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"checkpoint must be a regular directory: {root}")
    identity = read_identity(root / METADATA_NAME)
    declared = set(identity["inference_files"])
    if set(inference_files(root)) != declared:
        raise ValueError("checkpoint inference layout differs from its metadata")
    expected_files = declared | {METADATA_NAME, "SHA256SUMS"}
    if {path.name for path in root.iterdir()} != expected_files:
        raise ValueError("checkpoint export contains unexpected files; export inference artifacts to a fresh directory")
    for line in (root / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        regular_file(root / name)
        if digest_file(root / name) != expected:
            raise ValueError(f"checkpoint artifact checksum mismatch: {name}")
    return identity
