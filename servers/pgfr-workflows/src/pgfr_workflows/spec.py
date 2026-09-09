# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Workflow spec — the declarative, git-versioned artifact the builder edits.

Deliberately minimal execution semantics (v1): a linear list of steps, each a
single tool call with optional verified-gating and bounded retry. No branches,
no loops, no code — a workflow is reviewable YAML, not a program.

Dispatch constraints are enforced at the specification level: dispatch steps may only use
agent-class actions (the policy gate would refuse operator actions anyway;
the validator refuses to even save them).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Tool palette: the same verbs the MCP server exposes, addressed by seam route.
# Each tool carries per-param `params` (what the field means) AND `examples`
# (a concrete value the builder shows as the input placeholder), plus one
# `example` object — a fully-filled sample call the UI can insert with one click.
TOOLS: Dict[str, Dict[str, Any]] = {
    "floor_state": {
        "route": "/v1/floor-state",
        "description": "Snapshot of the whole floor.",
        "params": {},
        "examples": {},
        "example": {},
    },
    "perceive": {
        "route": "/v1/perceive",
        "description": "Observe one region.",
        "params": {"target": "string — which region to look at"},
        "examples": {"target": "conveyor_1"},
        "example": {"target": "conveyor_1"},
    },
    "dispatch_task": {
        "route": "/v1/dispatch",
        "description": "ONE floor action; returns verified only on physics confirmation.",
        "params": {
            "action": "move | pick_and_place",
            "endpoint": "which robot: franka_left | franka_right | mobilebot",
            "color": "cube color (move only): red | blue | green",
            "source": "where to pick from (move only)",
            "destination": "where to place (move only)",
            "backend": "optional: 'groot' routes the move to the learned GR00T policy stack",
            "object_id": "what to carry (pick_and_place only)",
            "target_id": "where to carry it (pick_and_place only)",
        },
        "examples": {
            "action": "move",
            "endpoint": "franka_left",
            "color": "red",
            "source": "conveyor_1",
            "destination": "tote",
            "object_id": "tote",
            "target_id": "rack_1",
        },
        # a complete, valid move() call for one-click insertion
        "example": {
            "action": "move",
            "endpoint": "franka_left",
            "color": "red",
            "source": "conveyor_1",
            "destination": "tote",
        },
    },
    "dispatch_parallel": {
        "route": "/v1/dispatch-parallel",
        "description": (
            "One readiness-gated atomic left/right GR00T pair for the fixed "
            "dual layout-3 scene. It requires both parallel and flexible-order "
            "capabilities and accepts only the next qualified mixed pair."
        ),
        "params": {
            "moves": (
                "exactly two moves: one franka_left/conveyor_1 and one "
                "franka_right/conveyor_2; each destination must match its color"
            ),
        },
        "examples": {"moves": "two validated GR00T move objects"},
        "example": {
            "moves": [
                {
                    "endpoint": "franka_left",
                    "color": "blue",
                    "source": "conveyor_1",
                    "destination": "tote_blue",
                    "backend": "groot",
                },
                {
                    "endpoint": "franka_right",
                    "color": "green",
                    "source": "conveyor_2",
                    "destination": "tote_green",
                    "backend": "groot",
                },
            ],
        },
    },
    "check_predicate": {
        "route": "/v1/verify",
        "description": "Fresh VLM yes/no check with a journaled evidence frame.",
        "params": {"predicate": "the statement to verify", "region": "where to look (optional)"},
        "examples": {"predicate": "the red cube is in the tote", "region": "tote"},
        "example": {"predicate": "the red cube is in the tote", "region": "tote"},
    },
}

AGENT_ACTIONS = {"move", "pick_and_place"}
_TEMPLATE_RE = re.compile(r"^\$\{(params\.[A-Za-z_][\w]*|steps\.\d+\.[\w.]+)\}$")


class Step(BaseModel):
    tool: Literal[
        "floor_state",
        "perceive",
        "dispatch_task",
        "dispatch_parallel",
        "check_predicate",
    ]
    args: Dict[str, Any] = Field(default_factory=dict)
    # Gate the workflow on this step's outcome. Defaults: serial dispatch gates
    # on physics verification; parallel dispatch additionally gates on
    # independent B=1 verification; check_predicate gates on answer == yes;
    # reads never gate.
    require_verified: Optional[bool] = None
    # NOTE: ignored for both dispatch tools — physical actuation never
    # auto-retries (an unverified dispatch may already have moved an arm).
    # Applies to reads.
    max_retries: int = Field(default=0, ge=0, le=3)

    @field_validator("args")
    @classmethod
    def _no_operator_actions(cls, v: Dict[str, Any], info: Any) -> Dict[str, Any]:
        action = v.get("action")
        if action is None:
            return v
        if not isinstance(action, str):
            raise ValueError("action must be a string")
        if not action.startswith("${") and action not in AGENT_ACTIONS:
            raise ValueError(
                f"action '{action}' is not agent-class; allowed: {sorted(AGENT_ACTIONS)}"
            )
        # Templated actions (${params.*}) are allowed at save time but are
        # re-checked against AGENT_ACTIONS at run time in the runner, so an
        # operator action cannot be smuggled in via a run param.
        return v

    def gates(self) -> bool:
        # Physical actuation is ALWAYS verified-gated — require_verified cannot
        # downgrade a dispatch (a run must halt on an unverified move).
        if self.tool in {"dispatch_task", "dispatch_parallel"}:
            return True
        if self.require_verified is not None:
            return self.require_verified
        return self.tool == "check_predicate"


class Schedule(BaseModel):
    # Run this workflow automatically every interval_s seconds with `params`.
    # Opt-in: disabled by default, min 30s so a periodic run can't hammer the
    # cell. Each scheduled run goes through the same policy gate as a manual one.
    interval_s: int = Field(ge=30, le=86400)
    enabled: bool = False
    params: Dict[str, Any] = Field(default_factory=dict)


class Workflow(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{1,48}$")
    version: str = "0.1.0"
    description: str = ""
    owner: str = ""
    # Free-form input parameters, referenced from step args as ${params.<name>}.
    params: Dict[str, str] = Field(default_factory=dict)
    steps: List[Step] = Field(min_length=1, max_length=20)
    done_criteria: str = ""
    schedule: Optional[Schedule] = None

    @field_validator("steps")
    @classmethod
    def _template_refs_resolve(cls, steps: List[Step]) -> List[Step]:
        for i, step in enumerate(steps):
            for key, value in step.args.items():
                if isinstance(value, str) and value.startswith("${"):
                    m = _TEMPLATE_RE.match(value)
                    if not m:
                        raise ValueError(f"step {i} arg '{key}': bad template '{value}'")
                    ref = m.group(1)
                    if ref.startswith("steps."):
                        target = int(ref.split(".")[1])
                        if target >= i:
                            raise ValueError(
                                f"step {i} arg '{key}': forward reference to step {target}"
                            )
        return steps

    def dispatch_actions(self) -> List[str]:
        return sorted(
            {
                str(s.args.get("action"))
                for s in self.steps
                if s.tool == "dispatch_task" and s.args.get("action")
            }
            | ({"move"} if any(s.tool == "dispatch_parallel" for s in self.steps) else set())
        )

    def to_skill_manifest(self) -> Dict[str, Any]:
        """Machine-readable half of a published skill (conformance-kit shape)."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description or f"Published workflow: {self.name}",
            "owner": self.owner or "pgfr-workflows",
            "requires_tools": sorted({s.tool for s in self.steps}),
            "allowed_actions": [
                a for a in self.dispatch_actions() if not a.startswith("${")
            ],
            "done_criteria": self.done_criteria or "All gated steps verified.",
        }


def resolve_args(
    args: Dict[str, Any],
    params: Dict[str, Any],
    step_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str) and value.startswith("${"):
            m = _TEMPLATE_RE.match(value)
            if not m:
                raise ValueError(f"arg '{key}': bad template '{value}'")
            ref = m.group(1)
            if ref.startswith("params."):
                name = ref.split(".", 1)[1]
                if name not in params:
                    raise KeyError(f"missing workflow param '{name}'")
                out[key] = params[name]
            else:
                parts = ref.split(".")
                node: Any = step_results[int(parts[1])]
                for part in parts[2:]:
                    node = node[part]
                out[key] = node
        else:
            out[key] = value
    return out
