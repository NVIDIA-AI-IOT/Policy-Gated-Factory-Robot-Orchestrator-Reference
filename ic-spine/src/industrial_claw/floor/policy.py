# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The action policy gate — ONE gate, at the seam, for every harness (T5).

Replaces the per-adapter allow-list (the OpenClaw plugin's policy.ts was the
only gate before; MCP/raw-HTTP callers were ungated). Every dispatch is checked
here before it can reach the floor:

- unknown actions are refused,
- required parameters must be present,
- operator-class actions (reset/cancel/spawn) require the x-role: operator
  header — separating agent missions from operator control. (Role assertion is
  intent-separation today; cryptographic auth arrives with the remote-access work.)

Policy is data, not code: a YAML file selected by IC_FLOOR_POLICY can add or
override reviewed actions without editing this module. Refusals are in-band results (dispatched=false,
reason "policy: ...") so agents can read and adapt to them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

DEFAULT_POLICY: dict[str, dict[str, Any]] = {
    "move": {"required": ["color", "source", "destination"], "role": "agent"},
    "pick_and_place": {"required": ["object_id", "target_id"], "role": "agent"},
    "inspect": {"required": [], "role": "agent"},
    "navigate_to": {"required": ["location_id"], "role": "agent"},
    "reset": {"required": [], "role": "operator"},
    "cancel": {"required": [], "role": "operator"},
    "spawn": {"required": [], "role": "operator"},
    "reset_scene": {"required": [], "role": "operator"},
}


@dataclass
class ActionPolicy:
    actions: dict[str, dict[str, Any]] = field(default_factory=lambda: dict(DEFAULT_POLICY))

    @classmethod
    def load(cls) -> ActionPolicy:
        path = os.environ.get("IC_FLOOR_POLICY")
        if not path:
            return cls()
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f) or {}
        schema_version = data.get("schema_version", 1)
        if schema_version != 1:
            raise ValueError(f"unsupported floor policy schema_version: {schema_version!r}")
        configured = data.get("actions", {})
        if not isinstance(configured, dict):
            raise ValueError("floor policy actions must be a mapping")
        return cls(actions={**DEFAULT_POLICY, **configured})

    def check(self, action: str, params: dict[str, Any], role: str | None) -> str | None:
        """None if allowed; else the refusal reason."""
        spec = self.actions.get(action)
        if spec is None:
            allowed = ", ".join(sorted(self.actions))
            return f"policy: unknown action '{action}' (allowed: {allowed})"
        missing = [k for k in spec.get("required", []) if params.get(k) in (None, "")]
        if missing:
            return f"policy: action '{action}' missing required params: {', '.join(missing)}"
        if spec.get("role") == "operator" and role != "operator":
            return f"policy: action '{action}' is operator-only (send x-role: operator)"
        return None
