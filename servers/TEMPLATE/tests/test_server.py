# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Template tests — every server ships at least these three."""
from __future__ import annotations

import json

from my_mcp import server


def test_instructions_are_shipped():
    text = server._instructions()
    assert text and "REPLACE ME" not in text, "write INSTRUCTIONS.md before shipping"


def test_tools_return_json_data():
    out = json.loads(server.read_something("probe"))
    assert isinstance(out, dict)


def test_effectful_tools_report_verification():
    out = json.loads(server.do_something("probe"))
    assert "verified" in out, "effectful tools must carry a verification field"
