# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Static system topology + live-status schemas.

The console never invents system state: nodes/edges are the declared
architecture; every live field is measured by a poller in ``aggregator.py``.
The console is read-only by construction — it holds no dispatch capability.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel

Status = Literal["ok", "degraded", "down", "unknown"]


class NodeStatus(BaseModel):
    id: str
    label: str
    kind: Literal["agent", "service", "sim", "store", "model", "tool", "endpoint", "camera"]
    host: str = ""
    layer: int = 0          # column in the layered layout
    status: Status = "unknown"
    detail: Dict[str, object] = {}


class Edge(BaseModel):
    id: str
    source: str
    target: str
    label: str = ""
    status: Status = "unknown"


class Topology(BaseModel):
    nodes: List[NodeStatus]
    edges: List[Edge]
    generated_at: str


# The declared architecture. Live status is filled in by the aggregator;
# anything it cannot measure stays "unknown" rather than being guessed.
# Tool verbs the MCP server exposes (each shown individually).
TOOLS = [("t_floor_state", "floor_state"), ("t_perceive", "perceive"),
         ("t_dispatch", "dispatch_task"), ("t_verify", "check_predicate")]
# Action endpoints on the floor — the two arms and the AMR (arm+base).
ENDPOINTS = [("franka_left", "Franka L · arm"), ("franka_right", "Franka R · arm"),
             ("mobilebot", "AMR · arm+base")]
# Cameras in the cell that feed the VLM.
CAMERAS = [("cam_outside", "Outside cam"), ("cam_wrist_l", "Wrist cam L"),
           ("cam_wrist_r", "Wrist cam R"), ("cam_rack", "Rack cam")]

NODES: List[NodeStatus] = [
    NodeStatus(id="brain", label="Brain · OpenClaw", kind="agent", host="thor", layer=0),
    NodeStatus(id="vlm", label="Cosmos VLM", kind="model", host="thor", layer=1),
    NodeStatus(id="mcp", label="MCP server", kind="service", host="thor", layer=1),
    *[NodeStatus(id=i, label=l, kind="tool", host="thor", layer=2) for i, l in TOOLS],
    NodeStatus(id="seam", label="Floor seam v1", kind="service", host="gpu-box", layer=3),
    NodeStatus(id="gym", label="NeMo Gym", kind="service", host="gpu-box", layer=3),
    NodeStatus(id="floor", label="Floor gate", kind="service", host="gpu-box", layer=4),
    NodeStatus(id="cell", label="Isaac cell", kind="sim", host="gpu-box", layer=5),
    NodeStatus(id="groot", label="GR00T policy stack", kind="model", host="gpu-box", layer=5),
    *[NodeStatus(id=i, label=l, kind="endpoint", host="cell", layer=6) for i, l in ENDPOINTS],
    *[NodeStatus(id=i, label=l, kind="camera", host="cell", layer=6) for i, l in CAMERAS],
    NodeStatus(id="journal", label="Audit journal", kind="store", host="gpu-box", layer=6),
]

EDGES: List[Edge] = [
    Edge(id="brain-mcp", source="brain", target="mcp", label="tool calls"),
    Edge(id="brain-vlm", source="brain", target="vlm", label="reason"),
    *[Edge(id=f"mcp-{i}", source="mcp", target=i) for i, _ in TOOLS],
    *[Edge(id=f"{i}-seam", source=i, target="seam") for i, _ in TOOLS],
    Edge(id="gym-seam", source="gym", target="seam", label="HTTP /v1"),
    Edge(id="seam-floor", source="seam", target="floor", label="policy gate"),
    Edge(id="floor-cell", source="floor", target="cell", label="ROS2"),
    Edge(id="cell-groot", source="cell", target="groot", label="backend=groot"),
    *[Edge(id=f"cell-{i}", source="cell", target=i) for i, _ in ENDPOINTS],
    *[Edge(id=f"cell-{i}", source="cell", target=i) for i, _ in CAMERAS],
    *[Edge(id=f"{i}-vlm", source=i, target="vlm", label="feed") for i, _ in CAMERAS],
    Edge(id="floor-journal", source="floor", target="journal", label="ops + frames"),
]


def blank_topology() -> Dict[str, object]:
    return {
        "nodes": {n.id: n.model_copy(deep=True) for n in NODES},
        "edges": {e.id: e.model_copy(deep=True) for e in EDGES},
    }


def derive_edge_status(nodes: Dict[str, NodeStatus], edge: Edge) -> Status:
    """An edge is at most as healthy as its endpoints; unknown stays unknown."""
    a, b = nodes[edge.source].status, nodes[edge.target].status
    order: Dict[Status, int] = {"down": 0, "degraded": 1, "unknown": 2, "ok": 3}
    worst: Status = a if order[a] <= order[b] else b
    return worst


def resolve(nodes: Dict[str, NodeStatus], edges: Dict[str, Edge]) -> Dict[str, object]:
    for edge in edges.values():
        edge.status = derive_edge_status(nodes, edge)
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def get_optional(detail: Dict[str, object], key: str) -> Optional[object]:
    value = detail.get(key)
    return value if value is not None else None
