# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the InputSource abstract base and MockInputSource."""
from __future__ import annotations

import pytest

from industrial_claw.input_sources.base import InputSource
from industrial_claw.input_sources.mock import MockInputSource, MockSnapshot


def test_abstract_cannot_instantiate() -> None:
    with pytest.raises(TypeError):
        InputSource()  # type: ignore[abstract]


async def test_mock_snapshot_returns_canned() -> None:
    src = MockInputSource(
        id="cam_1",
        modality="image",
        coverage_region="table_1",
        snapshots=[MockSnapshot(image_bytes=b"frame-1"), MockSnapshot(image_bytes=b"frame-2")],
    )
    s1 = await src.snapshot()
    s2 = await src.snapshot()
    s3 = await src.snapshot()  # exhausts and repeats last
    assert s1.image_bytes == b"frame-1"
    assert s2.image_bytes == b"frame-2"
    assert s3.image_bytes == b"frame-2"


def test_mock_advertises_query_kinds() -> None:
    src = MockInputSource(id="cam_1", modality="image", coverage_region="table_1")
    assert "predicate" in src.query_kinds()
    assert "describe" in src.query_kinds()


def test_mock_metadata() -> None:
    src = MockInputSource(id="cam_2", modality="image", coverage_region="table_1")
    meta = src.metadata()
    assert meta["id"] == "cam_2"
    assert meta["modality"] == "image"
    assert meta["coverage_region"] == "table_1"
