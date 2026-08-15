# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Discoverable Isaac action handlers.

Adding a module to this package is enough to make its ``ACTION_HANDLERS``
available to :class:`ic_cell.runtime.CellRuntime`. The registry is deliberately
free of Isaac imports so it can be validated in CI without launching Kit.
"""

from ic_cell.actions.discovery import discover_actions

__all__ = ["discover_actions"]
