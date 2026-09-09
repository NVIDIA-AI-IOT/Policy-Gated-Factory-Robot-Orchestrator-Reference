# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""ic_cell — the Isaac cell brought up as a proper package (T3).

Replaces the cmd.py script-injection channel: everything that used to be exec'd
into shared globals (ic_node_v2.py, camera builders, scene dressing, resets)
lives here as modules with owned state. One call brings the cell up:

    import ic_cell.boot; ic_cell.boot.bring_up()

The legacy startup.py + cmd.py path remains on disk as the emergency fallback.
"""
__version__ = "0.1.0"
