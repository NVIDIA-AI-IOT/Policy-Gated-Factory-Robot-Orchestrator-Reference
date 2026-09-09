#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Live ROS acceptance for the packaged Isaac Sim scripted baseline.

The pinned ROS sidecar runs this client. Each state-changing command is
published exactly once and its result is correlated by a unique goal ID.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import uuid
from collections.abc import Callable
from typing import Any


COLORS = ("red", "blue", "green")
EXPECTED_CUBE_IDS = {"red": 0, "blue": 2, "green": 4}
ENDPOINTS = ("franka_left", "franka_right", "mobilebot")
IMAGE_TOPICS = (
    "/inspect_cam/image_raw",
    "/inspect_cam/depth",
    "/outside_cam/image_raw",
    "/rack_cam/image_raw",
    "/rack_cam/depth",
    "/table_cam/image_raw",
    "/table_cam/depth",
    "/wrist_cam/image_raw",
)
CAMERA_INFO_TOPICS = (
    "/inspect_cam/camera_info",
    "/outside_cam/camera_info",
    "/rack_cam/camera_info",
    "/table_cam/camera_info",
    "/wrist_cam/camera_info",
)
STRING_TOPICS = ("/pgfr/floor_state", "/pgfr/joints")
REQUIRED_TOPICS = STRING_TOPICS + IMAGE_TOPICS + CAMERA_INFO_TOPICS


class AcceptanceError(RuntimeError):
    """A deterministic live-acceptance failure."""


def parse_json_object(value: str, topic: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"{topic} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AcceptanceError(f"{topic} must contain a JSON object")
    return parsed


def validate_floor_state(value: str) -> dict[str, Any]:
    state = parse_json_object(value, "/pgfr/floor_state")
    endpoints = state.get("endpoints")
    if not isinstance(endpoints, list) or not set(ENDPOINTS).issubset(endpoints):
        raise AcceptanceError("/pgfr/floor_state is missing required endpoints")
    if not isinstance(state.get("conveyor_1"), list):
        raise AcceptanceError("/pgfr/floor_state conveyor_1 must be a list")
    if not isinstance(state.get("tote"), dict):
        raise AcceptanceError("/pgfr/floor_state tote must be an object")
    if not isinstance(state.get("tote_on_rack"), bool):
        raise AcceptanceError("/pgfr/floor_state tote_on_rack must be boolean")
    if not isinstance(state.get("cubes"), list):
        raise AcceptanceError("/pgfr/floor_state cubes must be a list")
    return state


def has_exact_cube_placements(
    cubes: Any,
    placements: dict[str, str],
) -> bool:
    if not isinstance(cubes, list) or len(cubes) != len(EXPECTED_CUBE_IDS):
        return False
    observed: dict[str, tuple[Any, Any]] = {}
    for cube in cubes:
        if not isinstance(cube, dict):
            return False
        color = cube.get("color")
        if color not in EXPECTED_CUBE_IDS or color in observed:
            return False
        observed[color] = (cube.get("i"), cube.get("where"))
    return observed == {
        color: (EXPECTED_CUBE_IDS[color], placements[color])
        for color in COLORS
    }


def is_deterministic_reset_state(state: dict[str, Any]) -> bool:
    cubes = state.get("cubes")
    return (
        state.get("conveyor_1") == list(COLORS)
        and state.get("tote") == {}
        and state.get("tote_on_rack") is False
        and has_exact_cube_placements(
            cubes,
            {"red": "conveyor", "blue": "conveyor", "green": "conveyor"},
        )
    )


def is_red_move_state(state: dict[str, Any]) -> bool:
    cubes = state.get("cubes")
    return (
        state.get("conveyor_1") == ["blue", "green"]
        and state.get("tote") == {"red": "in"}
        and state.get("tote_on_rack") is False
        and has_exact_cube_placements(
            cubes,
            {"red": "tote", "blue": "conveyor", "green": "conveyor"},
        )
    )


def validate_joints(value: str) -> dict[str, Any]:
    joints = parse_json_object(value, "/pgfr/joints")
    for arm in ("franka_left", "franka_right"):
        values = joints.get(arm)
        if not isinstance(values, list) or len(values) < 9:
            raise AcceptanceError(f"/pgfr/joints {arm} must contain at least 9 values")
        if any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in values
        ):
            raise AcceptanceError(f"/pgfr/joints {arm} contains a non-finite value")
    return joints


def validate_image(message: Any, topic: str) -> dict[str, Any]:
    width = int(message.width)
    height = int(message.height)
    step = int(message.step)
    data_size = len(message.data)
    if width <= 0 or height <= 0 or step <= 0:
        raise AcceptanceError(f"{topic} has invalid dimensions or step")
    encoding = str(message.encoding)
    if not encoding:
        raise AcceptanceError(f"{topic} has no encoding")
    if topic.endswith("/image_raw"):
        if encoding != "rgb8":
            raise AcceptanceError(f"{topic} has unexpected RGB encoding {encoding!r}")
        bytes_per_pixel = 3
    elif topic.endswith("/depth"):
        depth_bytes_per_pixel = {"32FC1": 4, "16UC1": 2}
        if encoding not in depth_bytes_per_pixel:
            raise AcceptanceError(f"{topic} has unexpected depth encoding {encoding!r}")
        bytes_per_pixel = depth_bytes_per_pixel[encoding]
    else:
        raise AcceptanceError(f"{topic} is not a supported image topic")
    expected_step = width * bytes_per_pixel
    if step != expected_step:
        raise AcceptanceError(
            f"{topic} row step {step} does not match {width}x{bytes_per_pixel}="
            f"{expected_step} bytes"
        )
    expected_size = height * step
    if data_size != expected_size:
        raise AcceptanceError(
            f"{topic} payload size {data_size} does not match {expected_size} bytes"
        )
    return {
        "width": width,
        "height": height,
        "encoding": encoding,
        "bytes": data_size,
    }


def validate_camera_info(message: Any, topic: str) -> dict[str, Any]:
    width = int(message.width)
    height = int(message.height)
    matrix = [float(value) for value in message.k]
    if width <= 0 or height <= 0:
        raise AcceptanceError(f"{topic} has invalid dimensions")
    if len(matrix) != 9 or not all(math.isfinite(value) for value in matrix):
        raise AcceptanceError(f"{topic} has an invalid intrinsic matrix")
    if matrix[0] <= 0 or matrix[4] <= 0:
        raise AcceptanceError(f"{topic} has non-positive focal lengths")
    return {"width": width, "height": height, "k": matrix}


def validate_result(value: str, command: dict[str, Any]) -> dict[str, Any]:
    result = parse_json_object(value, "/pgfr/result")
    goal_id = command["goal_id"]
    if result.get("goal_id") != goal_id:
        raise AcceptanceError(
            f"received mismatched result {result.get('goal_id')!r} for {goal_id!r}"
        )
    if result.get("success") is not True or result.get("verified") is not True:
        raise AcceptanceError(
            f"goal {goal_id} failed: success={result.get('success')!r} "
            f"verified={result.get('verified')!r} reason={result.get('reason')!r}"
        )
    if result.get("action") != command["action"]:
        raise AcceptanceError(
            f"goal {goal_id} returned action {result.get('action')!r}, "
            f"expected {command['action']!r}"
        )
    arguments = result.get("args")
    if not isinstance(arguments, dict):
        raise AcceptanceError(f"goal {goal_id} result has no command arguments")
    for key, expected in command.items():
        if arguments.get(key) != expected:
            raise AcceptanceError(
                f"goal {goal_id} result changed {key}: "
                f"{arguments.get(key)!r} != {expected!r}"
            )
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stream-timeout", type=float, default=90.0)
    parser.add_argument("--result-timeout", type=float, default=180.0)
    parser.add_argument("--discovery-timeout", type=float, default=30.0)
    parser.add_argument(
        "--run-id",
        help="unique acceptance run identifier (generated when omitted)",
    )
    args = parser.parse_args(argv)
    for name in ("stream_timeout", "result_timeout", "discovery_timeout"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if args.run_id is not None and not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}", args.run_id
    ):
        parser.error(
            "--run-id must be 1..32 letters, digits, underscores, or hyphens"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import CameraInfo, Image
        from std_msgs.msg import String
    except ImportError as exc:
        raise AcceptanceError(
            "ROS Jazzy Python messages are unavailable in the acceptance sidecar"
        ) from exc

    class AcceptanceNode(Node):
        def __init__(self) -> None:
            super().__init__("pgfr_isaac_acceptance")
            self.samples: dict[str, dict[str, Any]] = {}
            self.floor_state: dict[str, Any] | None = None
            self.results: dict[str, dict[str, Any]] = {}
            self.errors: dict[str, str] = {}
            self.control_graph_attested = False
            self.command = self.create_publisher(String, "/pgfr/command", 10)
            self._application_subscriptions: list[Any] = [
                self.create_subscription(
                    String, "/pgfr/floor_state", self._on_floor_state, 10
                ),
                self.create_subscription(String, "/pgfr/joints", self._on_joints, 10),
                self.create_subscription(String, "/pgfr/result", self._on_result, 10),
            ]
            for topic in IMAGE_TOPICS:
                self._application_subscriptions.append(
                    self.create_subscription(
                        Image,
                        topic,
                        lambda message, name=topic: self._on_image(name, message),
                        10,
                    )
                )
            for topic in CAMERA_INFO_TOPICS:
                self._application_subscriptions.append(
                    self.create_subscription(
                        CameraInfo,
                        topic,
                        lambda message, name=topic: self._on_camera_info(name, message),
                        10,
                    )
                )

        def _record(
            self, topic: str, validator: Callable[[], dict[str, Any]]
        ) -> None:
            try:
                self.samples[topic] = validator()
            except AcceptanceError as exc:
                self.errors[topic] = str(exc)

        def _on_floor_state(self, message: Any) -> None:
            def validate() -> dict[str, Any]:
                state = validate_floor_state(message.data)
                self.floor_state = state
                return state

            self._record("/pgfr/floor_state", validate)

        def _on_joints(self, message: Any) -> None:
            self._record("/pgfr/joints", lambda: validate_joints(message.data))

        def _on_image(self, topic: str, message: Any) -> None:
            self._record(topic, lambda: validate_image(message, topic))

        def _on_camera_info(self, topic: str, message: Any) -> None:
            self._record(topic, lambda: validate_camera_info(message, topic))

        def _on_result(self, message: Any) -> None:
            try:
                result = parse_json_object(message.data, "/pgfr/result")
                goal_id = result.get("goal_id")
                if isinstance(goal_id, str) and goal_id:
                    self.results[goal_id] = result
            except AcceptanceError as exc:
                self.errors["/pgfr/result"] = str(exc)

        def spin_until(
            self, predicate: Callable[[], bool], timeout: float, description: str
        ) -> None:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                rclpy.spin_once(self, timeout_sec=0.2)
                if self.control_graph_attested:
                    self.assert_exclusive_control_graph()
                if self.errors:
                    topic, error = next(iter(self.errors.items()))
                    raise AcceptanceError(f"{topic}: {error}")
                if predicate():
                    return
            raise AcceptanceError(f"timed out waiting for {description}")

        def wait_for_control_graph(self) -> None:
            self.spin_until(
                lambda: self.count_subscribers("/pgfr/command") == 1
                and self.count_publishers("/pgfr/result") == 1
                and self.count_publishers("/pgfr/command") == 1,
                args.discovery_timeout,
                "one command subscriber, one result publisher, and no competing command publisher",
            )
            self.control_graph_attested = True
            self.assert_exclusive_control_graph()

        def assert_exclusive_control_graph(self) -> None:
            command_subscribers = self.count_subscribers("/pgfr/command")
            result_publishers = self.count_publishers("/pgfr/result")
            command_publishers = self.count_publishers("/pgfr/command")
            if (command_subscribers, result_publishers, command_publishers) != (
                1,
                1,
                1,
            ):
                raise AcceptanceError(
                    "control graph changed: expected command subscribers=1, "
                    "result publishers=1, command publishers=1; found "
                    f"{command_subscribers}, {result_publishers}, "
                    f"{command_publishers}"
                )

        def wait_for_fresh_streams(self) -> None:
            self.samples.clear()
            self.floor_state = None
            self.spin_until(
                lambda: set(REQUIRED_TOPICS).issubset(self.samples),
                args.stream_timeout,
                "all 15 required fresh camera/state payloads",
            )

        def publish_once_and_wait(
            self, command: dict[str, Any]
        ) -> dict[str, Any]:
            goal_id = command["goal_id"]
            self.results.pop(goal_id, None)
            self.assert_exclusive_control_graph()
            self.command.publish(String(data=json.dumps(command, separators=(",", ":"))))
            print(
                f"PGFR_ACCEPT_COMMAND_PUBLISHED action={command['action']} "
                f"goal_id={goal_id}",
                flush=True,
            )
            self.spin_until(
                lambda: goal_id in self.results,
                args.result_timeout,
                f"matching result for {goal_id}; command was not retried",
            )
            return validate_result(json.dumps(self.results[goal_id]), command)

        def wait_for_reset_state(self) -> dict[str, Any]:
            self.floor_state = None
            self.spin_until(
                lambda: self.floor_state is not None
                and is_deterministic_reset_state(self.floor_state),
                args.stream_timeout,
                "deterministic reset floor state",
            )
            assert self.floor_state is not None
            return self.floor_state

        def wait_for_red_move_state(self) -> dict[str, Any]:
            self.floor_state = None
            self.spin_until(
                lambda: self.floor_state is not None
                and is_red_move_state(self.floor_state),
                args.stream_timeout,
                "red cube to leave the conveyor and enter tote_red",
            )
            assert self.floor_state is not None
            return self.floor_state

    run_id = args.run_id or uuid.uuid4().hex[:12]
    rclpy.init(args=None)
    node: AcceptanceNode | None = None
    try:
        node = AcceptanceNode()
        node.wait_for_control_graph()
        reset_before_command = {
            "action": "reset",
            "goal_id": f"accept-{run_id}-reset-before",
        }
        reset_before = node.publish_once_and_wait(reset_before_command)
        node.wait_for_reset_state()
        node.wait_for_fresh_streams()
        print(
            f"PGFR_ACCEPT_STREAMS_OK count={len(node.samples)} run_id={run_id}",
            flush=True,
        )

        move_command = {
            "action": "move",
            "color": "red",
            "destination": "tote_red",
            "endpoint": "franka_left",
            "goal_id": f"accept-{run_id}-move-red",
        }
        move = node.publish_once_and_wait(move_command)
        if not str(move.get("reason", "")).startswith("in tote_red off="):
            raise AcceptanceError(
                f"red Franka move has unexpected proof: {move.get('reason')!r}"
            )
        moved_state = node.wait_for_red_move_state()
        reset_after_command = {
            "action": "reset",
            "goal_id": f"accept-{run_id}-reset-after",
        }
        reset_after = node.publish_once_and_wait(reset_after_command)
        final_state = node.wait_for_reset_state()
        summary = {
            "run_id": run_id,
            "stream_count": len(node.samples),
            "stream_topics": sorted(node.samples),
            "reset_before": reset_before,
            "move": move,
            "moved_conveyor": moved_state["conveyor_1"],
            "moved_tote": moved_state["tote"],
            "reset_after": reset_after,
            "final_conveyor": final_state["conveyor_1"],
        }
        print(
            "PGFR_ISAAC_ROS_ACCEPTANCE_PASS "
            + json.dumps(summary, sort_keys=True, separators=(",", ":")),
            flush=True,
        )
        return 0
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcceptanceError as exc:
        print(f"PGFR_ISAAC_ROS_ACCEPTANCE_FAIL: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(2)
