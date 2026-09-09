#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate discoverable Isaac action plugins without starting Isaac Sim."""

from pgfr_cell.actions import discover_actions


def main() -> int:
    registry = discover_actions()
    print("PGFR_ACTIONS_VALID names=%s" % ",".join(registry.action_names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
