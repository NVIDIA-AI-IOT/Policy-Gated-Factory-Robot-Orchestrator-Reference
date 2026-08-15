# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pytest fixtures shared across unit and integration tests."""
from __future__ import annotations

import os

import pytest


def _has_anthropic_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.fixture(autouse=True)
def _skip_real_anthropic_without_key(request: pytest.FixtureRequest) -> None:
    """Skip tests marked `real_anthropic` unless ANTHROPIC_API_KEY is set."""
    if request.node.get_closest_marker("real_anthropic") and not _has_anthropic_key():
        pytest.skip("ANTHROPIC_API_KEY not set; skipping real Anthropic test.")
