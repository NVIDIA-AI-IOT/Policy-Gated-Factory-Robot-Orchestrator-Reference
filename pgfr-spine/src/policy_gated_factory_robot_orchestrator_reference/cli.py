# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""policy_gated_factory_robot_orchestrator_reference CLI — minimal entry point: `policy_gated_factory_robot_orchestrator_reference "<operator goal>"`.

Designed to be subprocess-spawned by the operator-gateway bridge skill. Wires the
agents, runs the mission, writes a per-mission audit trail, prints a one-line
human summary (or JSON), and exits 0 on goal_met / non-zero otherwise.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from policy_gated_factory_robot_orchestrator_reference import floor
from policy_gated_factory_robot_orchestrator_reference.action_endpoints.base import ActionEndpoint
from policy_gated_factory_robot_orchestrator_reference.action_endpoints.mock import (
    MockActionEndpoint,
)
from policy_gated_factory_robot_orchestrator_reference.agents.action import ActionAgent
from policy_gated_factory_robot_orchestrator_reference.agents.brain import BrainAgent, BrainConfig
from policy_gated_factory_robot_orchestrator_reference.agents.perception import PerceptionAgent
from policy_gated_factory_robot_orchestrator_reference.clients.llm.anthropic_client import (
    AnthropicLLMClient,
)
from policy_gated_factory_robot_orchestrator_reference.clients.llm.base import (
    LLMClient,
    LLMResponse,
)
from policy_gated_factory_robot_orchestrator_reference.clients.llm.mock import MockLLMClient
from policy_gated_factory_robot_orchestrator_reference.clients.vlm.anthropic_client import (
    AnthropicVLMClient,
)
from policy_gated_factory_robot_orchestrator_reference.clients.vlm.base import (
    VLMClient,
    VLMResponse,
)
from policy_gated_factory_robot_orchestrator_reference.clients.vlm.mock import MockVLMClient
from policy_gated_factory_robot_orchestrator_reference.input_sources.base import InputSource
from policy_gated_factory_robot_orchestrator_reference.input_sources.mock import (
    MockInputSource,
    MockSnapshot,
)
from policy_gated_factory_robot_orchestrator_reference.runs.recorder import RunRecorder
from policy_gated_factory_robot_orchestrator_reference.types import Capability, Pose


@dataclass
class WiredAgents:
    brain: BrainAgent
    perception: PerceptionAgent
    action: ActionAgent


def _build_default_mock_world() -> tuple[list[InputSource], list[ActionEndpoint]]:
    """Minimal mock scene: one camera at table_1 + one AMR+Franka with nav + pick_and_place."""
    sources: list[InputSource] = [
        MockInputSource(
            id="cam_1",
            modality="image",
            coverage_region="table_1",
            snapshots=[MockSnapshot(image_bytes=b"frame")] * 16,
        )
    ]
    nav = Capability(
        name="navigate_to",
        description="Move base to a named location.",
        goal_schema={"type": "object", "required": ["location_id"]},
        result_schema={"type": "object"},
    )
    pap = Capability(
        name="pick_and_place",
        description="Pick an object and place it at a target.",
        goal_schema={"type": "object", "required": ["object_id", "target_id"]},
        result_schema={"type": "object"},
    )
    endpoints: list[ActionEndpoint] = [
        MockActionEndpoint(
            id="amr_franka_1",
            type="mobile_manipulator",
            capabilities=[nav, pap],
            pose=Pose(x=0, y=0),
        )
    ]
    return sources, endpoints


def _build_clients(config: dict[str, Any]) -> tuple[LLMClient, VLMClient]:
    """Mock clients if config.mock.enabled or no API key; real Anthropic otherwise."""
    use_mock = config.get("mock", {}).get("enabled", False)
    if use_mock or not os.environ.get("ANTHROPIC_API_KEY"):
        # Canned 4-subtask color-sort plan — enough to show the full mission loop
        # (navigate → pick-and-place green → pick-and-place red → return to dock)
        # with verification after every action.
        canned_plan = json.dumps(
            {
                "plan": [
                    {
                        "kind": "action",
                        "endpoint_id": "amr_franka_1",
                        "capability": "navigate_to",
                        "args": {"location_id": "table_1_approach"},
                        "verify": "robot at table_1?",
                    },
                    {
                        "kind": "action",
                        "endpoint_id": "amr_franka_1",
                        "capability": "pick_and_place",
                        "args": {"object_id": "green_block_1", "target_id": "green_rack"},
                        "verify": "is green_block_1 in green_rack?",
                    },
                    {
                        "kind": "action",
                        "endpoint_id": "amr_franka_1",
                        "capability": "pick_and_place",
                        "args": {"object_id": "red_block_1", "target_id": "red_rack"},
                        "verify": "is red_block_1 in red_rack?",
                    },
                    {
                        "kind": "action",
                        "endpoint_id": "amr_franka_1",
                        "capability": "navigate_to",
                        "args": {"location_id": "home_dock"},
                        "verify": "robot at home_dock?",
                    },
                ]
            }
        )
        llm: LLMClient = MockLLMClient(responses=[LLMResponse(text=canned_plan)])
        vlm: VLMClient = MockVLMClient(
            responses=[
                VLMResponse(
                    answer="Two green blocks and one red block on table_1; racks empty",
                    evidence="initial scene",
                ),
                VLMResponse(answer="yes", evidence="robot at table_1_approach"),
                VLMResponse(answer="yes", evidence="green_block_1 placed in green_rack"),
                VLMResponse(answer="yes", evidence="red_block_1 placed in red_rack"),
                VLMResponse(answer="yes", evidence="robot at home_dock"),
            ]
        )
        return llm, vlm
    return (
        AnthropicLLMClient(model=config["brain"]["model"]),
        AnthropicVLMClient(model=config["perception"]["vlm"]["model"]),
    )


def _build_agents(config: dict[str, Any]) -> WiredAgents:
    sources, endpoints = _build_default_mock_world()
    llm, vlm = _build_clients(config)
    perception = PerceptionAgent(sources=sources, vlm=vlm)
    action = ActionAgent(endpoints=endpoints)
    brain = BrainAgent(
        llm=llm,
        perception=perception,
        action=action,
        config=BrainConfig(
            max_subtasks=config["brain"]["max_subtasks"],
            max_replans=config["brain"]["max_replans"],
            max_mission_seconds=float(config["brain"]["max_mission_seconds"]),
            default_max_attempts=config["action"]["default_max_attempts"],
        ),
    )
    return WiredAgents(brain=brain, perception=perception, action=action)


def _load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        path = Path(__file__).resolve().parents[2] / "configs" / "config.example.yaml"
    loaded: Any = yaml.safe_load(path.read_text())
    if not isinstance(loaded, dict):
        raise ValueError(f"config.yaml must parse to a mapping; got {type(loaded).__name__}")
    return loaded


async def _run(goal: str, config_path: Path | None, json_out: bool, dry_run: bool) -> int:
    config = _load_config(config_path)
    agents = _build_agents(config)
    # One-shot path computation; not in a hot loop. Async-strict lint is overkill here.
    runs_dir = Path(config.get("runs_dir", "~/.policy_gated_factory_robot_orchestrator_reference/runs")).expanduser()  # noqa: ASYNC240

    if dry_run:
        plan = await agents.brain.plan(goal)
        items = [s.model_dump() for s in plan]
        if json_out:
            print(json.dumps({"plan": items}, indent=2))
        else:
            print(f"[dry-run] planned {len(items)} subtask(s):")
            for i, s in enumerate(items, 1):
                print(
                    f"  {i}. {s.get('kind')} :: "
                    f"{s.get('capability') or s.get('query')} args={s.get('args')}"
                )
        return 0

    result = await agents.brain.run_mission(goal)
    recorder = RunRecorder(base_dir=runs_dir, mission_id=result.mission_id)
    recorder.event("mission_complete", result.model_dump())
    recorder.close()

    if json_out:
        out = result.model_dump()
        out["trace"] = str(recorder.directory)
        print(json.dumps(out, indent=2))
    else:
        outcome = "goal_met=true" if result.goal_met else "goal_met=false"
        dur = result.duration_seconds if result.duration_seconds is not None else 0.0
        print(
            f"[mission {result.mission_id}] {outcome} · "
            f"{result.subtask_count} subtasks · {result.retries} retries · "
            f"{dur:.1f}s · trace: {recorder.directory}"
        )
        if result.reason:
            print(f"  reason: {result.reason}")
    return 0 if result.goal_met else 2


_FLOOR_COMMANDS = {"floor-state", "perceive", "dispatch", "verify"}

DEFAULT_FLOOR_STATE_PATH = "~/.policy_gated_factory_robot_orchestrator_reference/floor_state.json"


def _resolve_floor_state_path(explicit: Path | None) -> Path:
    """Where the shared mock-floor state lives: --state flag, then $PGFR_FLOOR_STATE, then default."""
    if explicit is not None:
        return explicit.expanduser()
    env = os.environ.get("PGFR_FLOOR_STATE")
    if env:
        return Path(env).expanduser()
    return Path(DEFAULT_FLOOR_STATE_PATH).expanduser()


@contextmanager
def _floor_lock(state_path: Path):
    """Cross-process exclusive lock so concurrent dispatch read-modify-writes serialize
    (otherwise parallel dispatches race the shared floor file → lost writes / corruption)."""
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def _floor_command_main(argv: list[str]) -> int:
    """Granular floor primitives the gateway plugin shells out to — JSON in, JSON out.

    All three share one ``--state`` file so a ``perceive`` invocation reflects what a
    prior ``dispatch`` invocation did, even though each runs in its own process.
    """
    parser = argparse.ArgumentParser(prog="policy_gated_factory_robot_orchestrator_reference")
    sub = parser.add_subparsers(dest="command", required=True)

    p_state = sub.add_parser("floor-state", help="List the floor's action endpoints.")
    p_state.add_argument("--state", type=Path, default=None)

    p_perceive = sub.add_parser("perceive", help="Observe a floor target (e.g. table_1).")
    p_perceive.add_argument("target")
    p_perceive.add_argument("--state", type=Path, default=None)

    p_dispatch = sub.add_parser("dispatch", help="Send one action to one endpoint.")
    p_dispatch.add_argument("--endpoint", required=True)
    p_dispatch.add_argument("--action", required=True)
    p_dispatch.add_argument("--color", default=None)
    p_dispatch.add_argument("--from", dest="source", default=None)
    p_dispatch.add_argument("--destination", default=None)
    p_dispatch.add_argument("--object-id", dest="object_id", default=None)
    p_dispatch.add_argument("--target-id", dest="target_id", default=None)
    p_dispatch.add_argument("--location-id", dest="location_id", default=None)
    p_dispatch.add_argument("--state", type=Path, default=None)

    p_verify = sub.add_parser("verify", help="VLM yes/no check of a predicate from a camera (ros2 backend).")
    p_verify.add_argument("predicate")
    p_verify.add_argument("--region", default=None)

    args = parser.parse_args(argv)
    # ROS 2 backend = live Isaac cell: no shared state file, the cell IS the state.
    if (os.environ.get("PGFR_FLOOR_BACKEND") or "mock").strip().lower() == "ros2":
        return _ros2_floor_command(args)
    state_path = _resolve_floor_state_path(args.state)
    # Seed an absent floor from the scene ($PGFR_FLOOR_SCENE / bundled default) so a
    # configured floor (incl. faulty endpoints) survives the per-session reset.
    scene = floor.load_scene(None)

    if args.command == "floor-state":
        state = floor.FloorState.load_or_seed(state_path, scene)
        print(json.dumps(floor.floor_state(state), indent=2))
        return 0
    if args.command == "perceive":
        state = floor.FloorState.load_or_seed(state_path, scene)
        print(json.dumps(floor.perceive(state, args.target), indent=2))
        return 0
    if args.command == "verify":
        print(json.dumps(
            {"error": "verify requires the ros2 backend + a VLM (set PGFR_FLOOR_BACKEND=ros2 and PGFR_VLM_URL)"},
            indent=2,
        ))
        return 2

    # dispatch mutates the shared floor file. Lock the WHOLE read-modify-write (load
    # inside the lock too) so concurrent dispatch processes serialize — no lost writes.
    with _floor_lock(state_path):
        state = floor.FloorState.load_or_seed(state_path, scene)
        result = asyncio.run(
            floor.dispatch(
                state,
                endpoint=args.endpoint,
                action=args.action,
                color=args.color,
                source=args.source,
                destination=args.destination,
            )
        )
        if result["dispatched"]:
            state.save(state_path)
    print(json.dumps(result, indent=2))
    # Act-and-confirm: an accepted-but-unverified action is a failure for scripting.
    return 0 if (result["dispatched"] and result.get("verified", True)) else 2


def _ros2_floor_command(args: argparse.Namespace) -> int:
    """Floor primitives over the live ROS 2 / Isaac backend — no state file; the cell verifies."""
    from policy_gated_factory_robot_orchestrator_reference.floor import ros2
    from policy_gated_factory_robot_orchestrator_reference.floor.backend import load_backend

    backend = load_backend()
    if args.command == "floor-state":
        print(json.dumps(ros2.live_floor_state(backend), indent=2))
        return 0
    if args.command == "perceive":
        print(json.dumps(asyncio.run(ros2.live_perceive(backend, args.target)), indent=2))
        return 0
    if args.command == "verify":
        result = asyncio.run(ros2.live_verify(backend, args.predicate, args.region))
        print(json.dumps(result, indent=2))
        return 0 if result.get("answer") == "yes" else 2

    goal_args = {k: v for k, v in {
        "color": args.color, "source": args.source, "destination": args.destination,
        "object_id": args.object_id, "target_id": args.target_id, "location_id": args.location_id,
    }.items() if v is not None}
    result = asyncio.run(ros2.live_dispatch(backend, args.endpoint, args.action, goal_args))
    print(json.dumps(result, indent=2))
    return 0 if (result["dispatched"] and result["verified"]) else 2


def _mission_main(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(
        prog="policy_gated_factory_robot_orchestrator_reference",
        description="Run a Policy-Gated Factory Robot Orchestrator Reference mission from a natural-language operator goal.",
    )
    parser.add_argument("goal", help="The operator's natural-language goal.")
    parser.add_argument(
        "--config", type=Path, default=None, help="Path to config.yaml (default: configs/config.example.yaml)."
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Plan only; do not execute any subtasks."
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.goal, args.config, args.json, args.dry_run))


def _serve_main(argv: list[str]) -> int:
    """Run the persistent HTTP floor service (holds one backend for its lifetime)."""
    parser = argparse.ArgumentParser(prog="policy_gated_factory_robot_orchestrator_reference serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    import logging

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from policy_gated_factory_robot_orchestrator_reference.floor.service import build_service

    httpd = build_service((args.host, args.port))
    url = f"http://{args.host}:{httpd.server_address[1]}"
    backend = os.environ.get("PGFR_FLOOR_BACKEND", "mock")
    print(f"policy_gated_factory_robot_orchestrator_reference floor service: {url} (backend={backend})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch granular floor subcommands; otherwise run a mission from a bare goal.

    ``policy_gated_factory_robot_orchestrator_reference floor-state|perceive|dispatch ...`` → floor primitives.
    ``policy_gated_factory_robot_orchestrator_reference serve`` → persistent HTTP floor service.
    ``policy_gated_factory_robot_orchestrator_reference "sort table 1"`` (or ``mission "sort table 1"``) → full mission.
    """
    tokens = list(sys.argv[1:] if argv is None else argv)
    if tokens and tokens[0] in _FLOOR_COMMANDS:
        code = _floor_command_main(tokens)
        # The ros2 backend spins an rclpy executor thread that doesn't tear down
        # cleanly on one-shot exit (SIGABRT after the result is printed). Flush and
        # hard-exit to avoid the noisy abort; the long-lived `serve` path is unaffected.
        if (os.environ.get("PGFR_FLOOR_BACKEND") or "").strip().lower() == "ros2":
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(code)
        return code
    if tokens and tokens[0] == "serve":
        return _serve_main(tokens[1:])
    if tokens and tokens[0] == "mission":
        tokens = tokens[1:]
    return _mission_main(tokens)


if __name__ == "__main__":
    sys.exit(main())
