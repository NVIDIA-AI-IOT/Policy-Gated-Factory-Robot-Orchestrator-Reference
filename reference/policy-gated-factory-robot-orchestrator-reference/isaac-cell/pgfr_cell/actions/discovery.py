# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Import and validate every action plugin in :mod:`pgfr_cell.actions`."""

from __future__ import annotations

import importlib
import pkgutil

from pgfr_cell.actions.base import ActionRegistrationError, ActionRegistry


_INFRASTRUCTURE_MODULES = {"base", "discovery"}


def discover_actions(package_name: str = "pgfr_cell.actions") -> ActionRegistry:
    """Return a fail-fast registry built from modules exporting ACTION_HANDLERS."""

    package = importlib.import_module(package_name)
    registry = ActionRegistry()
    modules = sorted(
        pkgutil.iter_modules(package.__path__, package.__name__ + "."),
        key=lambda item: item.name,
    )
    for module_info in modules:
        leaf = module_info.name.rsplit(".", 1)[-1]
        if leaf in _INFRASTRUCTURE_MODULES or leaf.startswith("_"):
            continue
        module = importlib.import_module(module_info.name)
        handlers = getattr(module, "ACTION_HANDLERS", None)
        if handlers is None:
            raise ActionRegistrationError(
                f"{module_info.name} must export an ACTION_HANDLERS iterable"
            )
        try:
            items = tuple(handlers)
        except TypeError as exc:
            raise ActionRegistrationError(
                f"{module_info.name}.ACTION_HANDLERS must be iterable"
            ) from exc
        if not items:
            raise ActionRegistrationError(
                f"{module_info.name}.ACTION_HANDLERS must not be empty"
            )
        for handler in items:
            registry.register(handler)

    if not registry.action_names:
        raise ActionRegistrationError(f"no action handlers discovered in {package_name}")
    return registry
