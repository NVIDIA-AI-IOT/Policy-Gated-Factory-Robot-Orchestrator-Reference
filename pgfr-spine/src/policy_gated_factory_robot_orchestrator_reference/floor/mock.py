# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The mock floor: in-memory state (tables, racks, endpoints) persisted to JSON,
plus a FloorActionEndpoint that applies moves to it.

This is the offline / CI backend. A ROS 2 / Isaac / Thor backend implements the
same ActionEndpoint contract (see floor/ros2.py and docs/floor-ros2-contract.md);
the agents and the backend-agnostic ops (floor/ops.py) stay unchanged.
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from policy_gated_factory_robot_orchestrator_reference.action_endpoints.base import (
    ActionEndpoint,
    ActionResult,
)
from policy_gated_factory_robot_orchestrator_reference.floor.scene import Scene
from policy_gated_factory_robot_orchestrator_reference.input_sources.base import InputSource
from policy_gated_factory_robot_orchestrator_reference.input_sources.mock import (
    MockInputSource,
    MockSnapshot,
)
from policy_gated_factory_robot_orchestrator_reference.types import Capability, EndpointState


class Block(BaseModel):
    item: str = "block"
    color: str


class Endpoint(BaseModel):
    """A controllable floor endpoint as the Control UI / PGFR sees it."""

    id: str
    kind: str
    status: str = "idle"
    battery: float | None = None
    location: str = ""
    # When true the endpoint reports success but the effect never lands (e.g. a
    # dropped grasp) — used to exercise dispatch's act-and-confirm verification.
    faulty: bool = False


class FloorState(BaseModel):
    """The whole mock floor: what is on each table, rack tallies, and endpoints."""

    tables: dict[str, list[Block]] = Field(default_factory=dict)
    racks: dict[str, int] = Field(default_factory=dict)
    endpoints: list[Endpoint] = Field(default_factory=list)

    @classmethod
    def seed_default(cls) -> FloorState:
        """The demo scene: table_1 with two red + one green block, empty racks, three endpoints."""
        return cls(
            tables={
                "table_1": [
                    Block(color="red"),
                    Block(color="green"),
                    Block(color="red"),
                ]
            },
            racks={"red_rack": 0, "green_rack": 0},
            endpoints=[
                Endpoint(id="amr_franka_1", kind="arm+base", battery=0.92, location="dock_1"),
                Endpoint(id="amr_franka_2", kind="arm+base", battery=0.78, location="dock_2"),
                Endpoint(id="conveyor_1", kind="conveyor", battery=None, location="line_a"),
            ],
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: temp file + os.replace so a concurrent reader (perceive)
        # never sees a half-written file (the cause of the corrupt-JSON bug).
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(self.model_dump_json(indent=2))
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    @classmethod
    def load(cls, path: Path) -> FloorState:
        return cls.model_validate_json(path.read_text())

    @classmethod
    def load_or_seed(cls, path: Path, scene: Scene | None = None) -> FloorState:
        if path.exists():
            return cls.load(path)
        # Seed from the scene when given (so a configured floor — including faulty
        # endpoints — survives the per-session reset), else the hardcoded default.
        state = cls.from_scene(scene) if scene is not None else cls.seed_default()
        state.save(path)
        return state

    @classmethod
    def from_scene(cls, scene: Scene) -> FloorState:
        """Build mock state from a scene config (the config-driven replacement for seed)."""
        return cls(
            tables={t: [Block(color=c) for c in colors] for t, colors in scene.tables.items()},
            racks=dict(scene.racks),
            endpoints=[
                Endpoint(
                    id=e.id, kind=e.kind, battery=e.battery, location=e.location, faulty=e.faulty
                )
                for e in scene.endpoints
            ],
        )


class FloorActionEndpoint(ActionEndpoint):
    """ActionEndpoint that applies moves to a shared :class:`FloorState` (mock backend)."""

    def __init__(self, state: FloorState, endpoint: Endpoint) -> None:
        self._state = state
        self.id = endpoint.id
        self.type = endpoint.kind
        self.pose = None
        self._endpoint = endpoint
        self.capabilities = [
            Capability(
                name="move",
                description="Move a colored block from a table to a rack.",
                goal_schema={
                    "type": "object",
                    "required": ["color", "source", "destination"],
                },
                result_schema={"type": "object"},
            )
        ]

    async def execute(self, capability_name: str, goal_args: dict[str, Any]) -> ActionResult:
        if capability_name != "move":
            return ActionResult(
                success=False, result={}, reason=f"unknown capability: {capability_name}"
            )
        color = goal_args.get("color")
        source = goal_args.get("source") or goal_args.get("from")
        destination = goal_args.get("destination")
        moved = {"color": color, "from": source, "destination": destination}
        if self._endpoint.faulty:
            # Reports success without touching the floor — the dropped-grasp case
            # that dispatch's act-and-confirm step is meant to catch.
            return ActionResult(success=True, result={"moved": moved}, reason="reported success")
        blocks = self._state.tables.get(source or "")
        if blocks is None:
            return ActionResult(success=False, result={}, reason=f"no table named {source}")
        idx = next((i for i, b in enumerate(blocks) if b.color == color), -1)
        if idx == -1:
            return ActionResult(
                success=False, result={}, reason=f"no {color} block on {source}"
            )
        blocks.pop(idx)
        self._state.racks[destination or ""] = self._state.racks.get(destination or "", 0) + 1
        return ActionResult(success=True, result={"moved": moved}, reason=None)

    def state(self) -> EndpointState:
        return EndpointState(
            busy=self._endpoint.status != "idle",
            battery_pct=100.0 if self._endpoint.battery is None else self._endpoint.battery * 100.0,
        )


class MockFloorBackend:
    """Backend over an in-memory FloorState seeded from a Scene (the offline/CI floor)."""

    def __init__(self, scene: Scene | None = None) -> None:
        self.state = FloorState.from_scene(scene) if scene else FloorState.seed_default()

    def endpoints(self) -> list[FloorActionEndpoint]:
        return [FloorActionEndpoint(self.state, e) for e in self.state.endpoints]

    def sources(self) -> list[InputSource]:
        return [
            MockInputSource(
                id="cam_1",
                modality="image",
                coverage_region="table_1",
                snapshots=[MockSnapshot(image_bytes=b"frame")],
            )
        ]
