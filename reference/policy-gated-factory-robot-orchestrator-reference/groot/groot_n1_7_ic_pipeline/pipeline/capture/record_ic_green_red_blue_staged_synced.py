#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Capture verified episodes from an evolving three-object scene.

By default this preserves the certified green->red->blue capture contract: the
green move is verified physical context setup and the following red and blue
moves are recorded without another reset.  ``--order`` permits a complete
color permutation and ``--record-first`` records all three stages.  A sequence
enters the dataset only when every recorded stage passes the same timing, data,
and physical gates as the isolated capture recorder.
"""

import argparse
from bisect import bisect_left
import json
from pathlib import Path
import statistics
import time
import zlib

import numpy as np
import rclpy
from policy_gated_factory_robot_orchestrator_reference.floor.ros2 import _image_to_jpeg
from sensor_msgs.msg import Image
from std_msgs.msg import String


PHYSICS_HZ = 60
DATASET_HZ = 15
CAMERA_SENSOR_HZ = 30
RETAIN_EVERY_TICKS = PHYSICS_HZ // DATASET_HZ
CAMERA_TOLERANCE_NS = 16_667_000
MIN_RETAINED_FRAMES = 60
MIN_PAIRED_CAMERA_FRACTION = 0.98
MIN_UNIQUE_IMAGE_FRACTION = 0.95
MAX_ARM_STEP_RAD = 0.12
MAX_DISTRACTOR_DISPLACEMENT_M = 0.005
FLOOR_STATE_TIMEOUT_S = 5.0
SHAPE_NOUN = {"red": "cube", "blue": "cylinder", "green": "brick"}


def image_stamp_ns(message):
    return int(message.header.stamp.sec) * 1_000_000_000 + int(
        message.header.stamp.nanosec
    )


def percentile(values, quantile):
    values = sorted(values)
    if not values:
        return None
    return values[round((len(values) - 1) * quantile)]


def object_record(floor, color):
    matches = [item for item in floor.get("cubes", []) if item.get("color") == color]
    return matches[0] if len(matches) == 1 else None


def displacement_xy(initial, final):
    if initial is None or final is None:
        return float("inf")
    return float(
        np.linalg.norm(
            np.asarray([final["x"], final["y"]], dtype=float)
            - np.asarray([initial["x"], initial["y"]], dtype=float)
        )
    )


def goal_id(result):
    if not result:
        return None
    return result.get("goal_id") or (result.get("args") or {}).get("goal_id")


parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--sequences", type=int, default=24)
parser.add_argument(
    "--arm",
    choices=("franka_left", "franka_right"),
    default="franka_left",
)
parser.add_argument("--layout", type=int, choices=range(6), default=0)
parser.add_argument(
    "--order",
    nargs=3,
    choices=tuple(SHAPE_NOUN),
    default=("green", "red", "blue"),
    metavar=("FIRST", "SECOND", "THIRD"),
)
parser.add_argument(
    "--record-first",
    action="store_true",
    help="record all three stages instead of using the first as context only",
)
parser.add_argument("--seed-start", type=int, default=5000)
parser.add_argument("--timeout", type=float, default=45.0)
parser.add_argument("--max-attempts", type=int, default=None)
args = parser.parse_args()
order = tuple(args.order)
if len(set(order)) != len(SHAPE_NOUN) or set(order) != set(SHAPE_NOUN):
    parser.error("--order must contain green, red, and blue exactly once")
recorded_colors = order if args.record_first else order[1:]
camera_topics = (
    ("/wrist_cam/image_raw", "/outside_cam/image_raw")
    if args.arm == "franka_left"
    else ("/wrist_right_cam/image_raw", "/outside_right_cam/image_raw")
)

if args.sequences < 1:
    raise ValueError("--sequences must be positive")
max_attempts = args.max_attempts or args.sequences * 3
if max_attempts < args.sequences:
    raise ValueError("--max-attempts cannot be smaller than --sequences")

output = args.output.expanduser().resolve()
if output.exists() and any(output.iterdir()):
    raise FileExistsError(f"refusing non-empty capture output: {output}")
output.mkdir(parents=True, exist_ok=True)
(output / "rejected").mkdir()
(output / "attempts").mkdir()
for recorded_color in recorded_colors:
    (output / recorded_color).mkdir()

rclpy.init()
node = rclpy.create_node("ic_green_red_blue_staged_synced_recorder")
state = {"result": None, "floor": None}
capture = {"wrist": {}, "outside": {}, "samples": []}


def image_callback(name):
    def callback(message):
        capture[name].setdefault(image_stamp_ns(message), message)

    return callback


def sample_callback(message):
    try:
        payload = json.loads(message.data)
    except (TypeError, ValueError):
        return
    if (
        payload.get("schema") == 2
        and payload.get("arm") == args.arm
        and payload.get("physics_hz") == PHYSICS_HZ
        and payload.get("camera_sensor_hz") == CAMERA_SENSOR_HZ
        and payload.get("camera_hz") == DATASET_HZ
    ):
        capture["samples"].append(payload)


def json_callback(name):
    def callback(message):
        try:
            state[name] = json.loads(message.data)
        except (TypeError, ValueError):
            state[name] = None

    return callback


node.create_subscription(Image, camera_topics[0], image_callback("wrist"), 300)
node.create_subscription(
    Image, camera_topics[1], image_callback("outside"), 300
)
node.create_subscription(String, "/ic/sync_sample", sample_callback, 500)
node.create_subscription(String, "/ic/result", json_callback("result"), 50)
node.create_subscription(String, "/ic/floor_state", json_callback("floor"), 50)
publisher = node.create_publisher(String, "/ic/command", 30)


def spin(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.01)


def send(payload):
    publisher.publish(String(data=json.dumps(payload)))


def send_until_result(payload, timeout, retry_period=0.25):
    """Publish an idempotent command until DDS discovery delivers it.

    Recorder containers are intentionally short lived.  A one-shot publish can
    occur before Fast DDS has matched the publisher to Isaac's subscriber,
    especially when several verified jobs run back-to-back.  Goal IDs make
    bounded retransmission safe: Isaac executes the first delivered command
    and rejects duplicates.
    """

    expected_goal_id = payload["goal_id"]
    deadline = time.monotonic() + timeout
    next_publish = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_publish:
            send(payload)
            next_publish = now + retry_period
        rclpy.spin_once(node, timeout_sec=0.02)
        result = state["result"]
        if goal_id(result) == expected_goal_id:
            state["result"] = None
            return result
    return None


def wait_fresh_floor(timeout):
    state["floor"] = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.02)
        if state["floor"] is not None:
            return state["floor"]
    return None


def reset_capture():
    capture["wrist"].clear()
    capture["outside"].clear()
    capture["samples"].clear()


def match_camera_frames(samples, paired_stamps):
    sample_times = [int(sample["sim_time_ns"]) for sample in samples]
    used_ticks = set()
    matches = []
    for camera_stamp in paired_stamps:
        position = bisect_left(sample_times, camera_stamp)
        candidate_indices = range(max(0, position - 1), min(len(samples), position + 2))
        candidate_indices = [
            index
            for index in candidate_indices
            if int(samples[index]["tick"]) not in used_ticks
        ]
        if not candidate_indices:
            continue
        sample_index = min(
            candidate_indices,
            key=lambda index: abs(sample_times[index] - camera_stamp),
        )
        if abs(sample_times[sample_index] - camera_stamp) > CAMERA_TOLERANCE_NS:
            continue
        sample = samples[sample_index]
        used_ticks.add(int(sample["tick"]))
        matches.append((sample, camera_stamp))

    # ROS2CameraHelper publishes on the render schedule. Retain one globally
    # phased sample every four 60 Hz physics ticks (native-DROID 15 fps) so
    # images, observations, and applied actions share one clock.
    return [
        (sample, camera_stamp)
        for sample, camera_stamp in matches
        if int(sample["tick"]) % RETAIN_EVERY_TICKS == 0
    ]


def evaluate_attempt(result, initial_floor, final_floor, target_color):
    all_samples = sorted(capture["samples"], key=lambda item: int(item["tick"]))
    all_ticks = [int(item["tick"]) for item in all_samples]
    unique_ticks = set(all_ticks)
    raw_tick_steps = np.diff(all_ticks) if len(all_ticks) > 1 else np.asarray([])

    wrist_stamps = set(capture["wrist"])
    outside_stamps = set(capture["outside"])
    paired_stamps = sorted(wrist_stamps & outside_stamps)
    paired_fraction = len(paired_stamps) / max(
        min(len(wrist_stamps), len(outside_stamps)), 1
    )
    matches = match_camera_frames(all_samples, paired_stamps)
    retained_ticks = [int(sample["tick"]) for sample, _ in matches]
    retained_tick_steps = (
        np.diff(retained_ticks) if len(retained_ticks) > 1 else np.asarray([])
    )
    camera_tick_steps = (
        np.rint(np.diff([stamp for _, stamp in matches]) * PHYSICS_HZ / 1e9)
        .astype(int)
        if len(matches) > 1
        else np.asarray([])
    )
    camera_offsets_ms = [
        (stamp - int(sample["sim_time_ns"])) / 1e6 for sample, stamp in matches
    ]
    wrist_hashes = [
        zlib.crc32(bytes(capture["wrist"][stamp].data)) for _, stamp in matches
    ]
    outside_hashes = [
        zlib.crc32(bytes(capture["outside"][stamp].data)) for _, stamp in matches
    ]
    observations = np.asarray(
        [sample["observation"] for sample, _ in matches], dtype=np.float64
    )
    actions = np.asarray(
        [sample["action"] for sample, _ in matches], dtype=np.float64
    )
    max_arm_step = (
        float(np.max(np.abs(np.diff(observations[:, :7], axis=0))))
        if len(observations) > 1
        else float("inf")
    )
    required_colors = tuple(SHAPE_NOUN)
    distractor_displacements = {
        color: displacement_xy(
            object_record(initial_floor, color), object_record(final_floor, color)
        )
        for color in required_colors
        if color != target_color
    }
    max_distractor_displacement = max(distractor_displacements.values(), default=0.0)
    image_shapes = {
        name: sorted(
            {
                (int(message.width), int(message.height), str(message.encoding))
                for message in capture[name].values()
            }
        )
        for name in ("wrist", "outside")
    }

    quality = {
        "schema_version": 2,
        "capture_clock": "global_simulator_physics_tick",
        "physics_hz": PHYSICS_HZ,
        "dataset_hz": DATASET_HZ,
        "camera_schedule": (
            "OmniSensorAPI omni:sensor:tickRate=30; "
            "ROS2CameraHelper globally decimated every 4 physics ticks "
            "to native-DROID 15 fps"
        ),
        "result": result,
        "telemetry_samples": len(all_samples),
        "unique_telemetry_ticks": len(unique_ticks),
        "duplicate_telemetry_ticks": len(all_ticks) - len(unique_ticks),
        "raw_tick_step_min": int(raw_tick_steps.min()) if len(raw_tick_steps) else None,
        "raw_tick_step_max": int(raw_tick_steps.max()) if len(raw_tick_steps) else None,
        "wrist_camera_frames": len(wrist_stamps),
        "outside_camera_frames": len(outside_stamps),
        "paired_camera_frames": len(paired_stamps),
        "paired_camera_fraction": paired_fraction,
        "matched_retained_samples": len(matches),
        "retained_tick_step_min": (
            int(retained_tick_steps.min()) if len(retained_tick_steps) else None
        ),
        "retained_tick_step_max": (
            int(retained_tick_steps.max()) if len(retained_tick_steps) else None
        ),
        "camera_tick_step_min": (
            int(camera_tick_steps.min()) if len(camera_tick_steps) else None
        ),
        "camera_tick_step_max": (
            int(camera_tick_steps.max()) if len(camera_tick_steps) else None
        ),
        "camera_offset_ms_median": (
            statistics.median(camera_offsets_ms) if camera_offsets_ms else None
        ),
        "camera_offset_ms_p05": percentile(camera_offsets_ms, 0.05),
        "camera_offset_ms_p95": percentile(camera_offsets_ms, 0.95),
        "camera_offset_ms_max_abs": (
            max(abs(value) for value in camera_offsets_ms)
            if camera_offsets_ms
            else None
        ),
        "camera_shapes": image_shapes,
        "wrist_unique_fraction": len(set(wrist_hashes)) / max(len(wrist_hashes), 1),
        "outside_unique_fraction": len(set(outside_hashes))
        / max(len(outside_hashes), 1),
        "max_adjacent_measured_arm_step_rad": max_arm_step,
        "min_gripper_action": float(actions[:, 7].min()) if len(actions) else None,
        "distractor_displacements_xy_m": distractor_displacements,
        "max_distractor_displacement_xy_m": max_distractor_displacement,
    }
    timing_passed = bool(
        len(matches) >= MIN_RETAINED_FRAMES
        and len(all_ticks) == len(unique_ticks)
        and len(raw_tick_steps)
        and int(raw_tick_steps.min()) == 1
        and int(raw_tick_steps.max()) == 1
        and paired_fraction >= MIN_PAIRED_CAMERA_FRACTION
        and len(retained_tick_steps)
        and int(retained_tick_steps.min()) == RETAIN_EVERY_TICKS
        and int(retained_tick_steps.max()) == RETAIN_EVERY_TICKS
        and len(camera_tick_steps)
        and int(camera_tick_steps.min()) == RETAIN_EVERY_TICKS
        and int(camera_tick_steps.max()) == RETAIN_EVERY_TICKS
        and quality["camera_offset_ms_max_abs"] is not None
        and quality["camera_offset_ms_max_abs"] <= CAMERA_TOLERANCE_NS / 1e6
        and len(image_shapes["wrist"]) == 1
        and image_shapes["wrist"][0][:2] == (320, 180)
        and image_shapes["wrist"][0][2] in ("rgb8", "rgba8")
        and len(image_shapes["outside"]) == 1
        and image_shapes["outside"][0][:2] == (320, 180)
        and image_shapes["outside"][0][2] in ("rgb8", "rgba8")
    )
    data_passed = bool(
        timing_passed
        and observations.shape == actions.shape
        and observations.ndim == 2
        and observations.shape[1] == 8
        and np.isfinite(observations).all()
        and np.isfinite(actions).all()
        and max_arm_step <= MAX_ARM_STEP_RAD
        and quality["wrist_unique_fraction"] >= MIN_UNIQUE_IMAGE_FRACTION
        and quality["outside_unique_fraction"] >= MIN_UNIQUE_IMAGE_FRACTION
        and quality["min_gripper_action"] is not None
        and quality["min_gripper_action"] < 0.033
    )
    physical_passed = bool(
        result
        and result.get("success")
        and result.get("verified")
        and max_distractor_displacement <= MAX_DISTRACTOR_DISPLACEMENT_M
    )
    quality["timing_passed"] = timing_passed
    quality["data_passed"] = data_passed
    quality["physical_passed"] = physical_passed
    quality["passed"] = bool(data_passed and physical_passed)
    return quality, matches, distractor_displacements


def write_episode(
    episode_dir,
    sequence_index,
    stage,
    color,
    seed,
    quality,
    matches,
    initial_floor,
    final_floor,
    distractor_displacements,
):
    (episode_dir / "wrist").mkdir(parents=True)
    (episode_dir / "outside").mkdir(parents=True)
    first_tick = int(matches[0][0]["tick"])
    steps = []
    for frame_index, (sample, camera_stamp) in enumerate(matches):
        (episode_dir / "wrist" / f"{frame_index:04d}.jpg").write_bytes(
            _image_to_jpeg(capture["wrist"][camera_stamp])
        )
        (episode_dir / "outside" / f"{frame_index:04d}.jpg").write_bytes(
            _image_to_jpeg(capture["outside"][camera_stamp])
        )
        sample_tick = int(sample["tick"])
        steps.append(
            {
                "i": frame_index,
                "t": round((sample_tick - first_tick) / float(PHYSICS_HZ), 7),
                "sim_tick": sample_tick,
                "source_sequence": int(sample["sequence"]),
                "source_task_tick": int(sample["task_tick"]),
                "sync_sim_time_ns": int(sample["sim_time_ns"]),
                "camera_stamp_ns": camera_stamp,
                "camera_sync_offset_ms": round(
                    (camera_stamp - int(sample["sim_time_ns"])) / 1e6, 6
                ),
                "fl_joints": sample["observation"],
                "fl_action": sample["action"],
                "fl_action_source": sample["action_source"],
            }
        )
    (episode_dir / "states.json").write_text(json.dumps(steps) + "\n")
    (episode_dir / "task.txt").write_text(
        f"pick the {color} {SHAPE_NOUN[color]} and place it on the "
        f"{color} pad\n"
    )
    (episode_dir / "scene.json").write_text(
        json.dumps(
            {
                "capture_mode": "green_red_blue_staged_native_droid_15fps",
                "capture_spec": {
                    "arm": args.arm,
                    "color": color,
                    "shape": SHAPE_NOUN[color],
                    "layout": args.layout,
                    "seed": seed,
                    "sequence_index": sequence_index,
                    "sequence_stage": stage,
                    "sequence_order": list(order),
                    "preceding_colors": list(order[: stage - 1]),
                },
                "physical_only": True,
                "controller": "NVIDIA Franka PickPlaceController RMPflow",
                "software_attachment": None,
                "action_source": "observed_exact_applied_joint_target",
                "initial_floor": initial_floor,
                "final_floor": final_floor,
                "distractor_displacements_xy_m": distractor_displacements,
                "result": quality["result"],
            },
            indent=2,
        )
        + "\n"
    )
    (episode_dir / "capture_quality.json").write_text(
        json.dumps(quality, indent=2) + "\n"
    )


def expected_tote_location():
    return "tote" if args.arm == "franka_left" else "tote_r"


def setup_first_context(initial_floor, final_floor, result, target_color):
    displacements = {
        color: displacement_xy(
            object_record(initial_floor, color), object_record(final_floor, color)
        )
        for color in SHAPE_NOUN
        if color != target_color
    }
    target = object_record(final_floor, target_color)
    distractors = [
        object_record(final_floor, color)
        for color in SHAPE_NOUN
        if color != target_color
    ]
    passed = bool(
        result
        and result.get("success")
        and result.get("verified")
        and target
        and target.get("where") == expected_tote_location()
        and all(item and item.get("where") == "conveyor" for item in distractors)
        and max(displacements.values(), default=0.0)
        <= MAX_DISTRACTOR_DISPLACEMENT_M
    )
    return {
        "passed": passed,
        "result": result,
        "initial_floor": initial_floor,
        "final_floor": final_floor,
        "distractor_displacements_xy_m": displacements,
        "max_distractor_displacement_xy_m": max(
            displacements.values(), default=0.0
        ),
    }


def annotate_quality(quality, attempt, accepted, color, seed, stage):
    quality.update(
        {
            "attempt": attempt,
            "accepted_index": None,
            "candidate_sequence_index": accepted,
            "pair_accepted": False,
            "arm": args.arm,
            "color": color,
            "shape": SHAPE_NOUN[color],
            "layout": args.layout,
            "seed": seed,
            "sequence_stage": stage,
            "sequence_order": list(order),
        }
    )


def fail_if_systemic(quality):
    if not quality["timing_passed"] or not quality["data_passed"]:
        raise RuntimeError(
            "systemic synchronization/data gate failed; refusing more sequences"
        )


started_run = time.monotonic()
run_nonce = time.time_ns()
run_key = (
    f"droid15-{args.arm}-{'-'.join(order)}-layout{args.layout}-"
    f"seed{args.seed_start}-run{run_nonce}"
)
accepted_reports = []
accepted = 0
attempt = 0
try:
    spin(2.0)
    if not capture["wrist"] or not capture["outside"]:
        raise RuntimeError("capture camera topics are not live")
    print(
        "STAGED_CAPTURE_START "
        f"target={accepted}/{args.sequences} arm={args.arm} "
        f"order={','.join(order)} recorded={','.join(recorded_colors)} "
        f"layout={args.layout} "
        f"cameras={camera_topics} seed_start={args.seed_start} output={output}",
        flush=True,
    )

    while accepted < args.sequences and attempt < max_attempts:
        attempt += 1
        seed = args.seed_start + accepted
        attempt_dir = output / "attempts" / f"attempt_{attempt:03d}_seed_{seed}"
        attempt_dir.mkdir()

        state["result"] = None
        spawn_result = send_until_result(
            {
                "action": "spawn",
                "n": seed,
                "zone": f"shape3:green:{args.layout}:{args.arm}",
                "goal_id": f"{run_key}-spawn-{attempt:03d}",
            },
            8.0,
        )
        spawn_floor = wait_fresh_floor(FLOOR_STATE_TIMEOUT_S) or {}
        required_colors = tuple(SHAPE_NOUN)
        if (
            not spawn_result
            or not spawn_result.get("verified")
            or any(
                object_record(spawn_floor, color) is None
                for color in required_colors
            )
        ):
            raise RuntimeError(
                f"shape-triple scene setup failed seed={seed}: "
                f"result={spawn_result} floor={spawn_floor}"
            )

        current_floor = spawn_floor
        staged_candidates = []
        staged_qualities = {}
        setup_context = None
        rejected_stage = None
        for stage, color in enumerate(order, start=1):
            reset_capture()
            state["result"] = None
            result = send_until_result(
                {
                    "action": "move",
                    "color": color,
                    "endpoint": args.arm,
                    "destination": f"tote_{color}",
                    "goal_id": f"{run_key}-{color}-{attempt:03d}",
                },
                args.timeout,
            )
            next_floor = wait_fresh_floor(FLOOR_STATE_TIMEOUT_S) or {}

            if stage == 1 and not args.record_first:
                setup_context = setup_first_context(
                    current_floor, next_floor, result, color
                )
                (attempt_dir / f"{color}_setup.json").write_text(
                    json.dumps(setup_context, indent=2) + "\n"
                )
                if not setup_context["passed"]:
                    rejected_stage = f"{color}_setup"
                    break
                current_floor = next_floor
                continue

            quality, matches, displacements = evaluate_attempt(
                result, current_floor, next_floor, color
            )
            annotate_quality(quality, attempt, accepted, color, seed, stage)
            staged_qualities[color] = quality
            (attempt_dir / f"{color}_quality.json").write_text(
                json.dumps(quality, indent=2) + "\n"
            )
            if not quality["passed"]:
                rejected_stage = color
                fail_if_systemic(quality)
                break

            candidate = attempt_dir / f"{color}_candidate"
            write_episode(
                candidate,
                accepted,
                stage,
                color,
                seed,
                quality,
                matches,
                current_floor,
                next_floor,
                displacements,
            )
            staged_candidates.append((quality, candidate, color))
            current_floor = next_floor

        if rejected_stage is not None:
            failed_quality = staged_qualities.get(rejected_stage)
            print(
                "STAGED_SEQUENCE_REJECTED "
                f"attempt={attempt} seed={seed} stage={rejected_stage}"
                + (
                    f" timing={failed_quality['timing_passed']}"
                    f" data={failed_quality['data_passed']}"
                    f" physical={failed_quality['physical_passed']}"
                    if failed_quality
                    else ""
                ),
                flush=True,
            )
            continue

        for quality, candidate, color in staged_candidates:
            quality["accepted_index"] = accepted
            quality["pair_accepted"] = True
            (candidate / "capture_quality.json").write_text(
                json.dumps(quality, indent=2) + "\n"
            )
            candidate.rename(output / color / f"ep_{accepted:03d}")

        sequence_report = {
            "schema_version": 1,
            "accepted_index": accepted,
            "attempt": attempt,
            "seed": seed,
            "arm": args.arm,
            "layout": args.layout,
            "order": list(order),
            "recorded_colors": list(recorded_colors),
            "first_stage_setup": setup_context,
            "stages": staged_qualities,
        }
        if order == ("green", "red", "blue") and not args.record_first:
            # Preserve the original manifest fields for existing assemblers.
            sequence_report.update(
                {
                    "green_setup": setup_context,
                    "red": staged_qualities["red"],
                    "blue": staged_qualities["blue"],
                }
            )
        (attempt_dir / "sequence_result.json").write_text(
            json.dumps(sequence_report, indent=2) + "\n"
        )
        accepted_reports.append(sequence_report)
        accepted += 1
        (output / "capture_manifest.json").write_text(
            json.dumps(accepted_reports, indent=2) + "\n"
        )
        with (output / "attempts.jsonl").open("a") as stream:
            stream.write(json.dumps(sequence_report) + "\n")
        elapsed = time.monotonic() - started_run
        eta = elapsed / accepted * (args.sequences - accepted)
        print(
            "STAGED_SEQUENCE_ACCEPTED "
            f"sequence={accepted - 1:03d} seed={seed} "
            + " ".join(
                f"{color}_frames={quality['matched_retained_samples']}"
                for quality, _, color in staged_candidates
            )
            + " "
            f"progress={accepted}/{args.sequences} eta_seconds={eta:.1f}",
            flush=True,
        )

    if accepted != args.sequences:
        raise RuntimeError(
            "staged capture attempt budget exhausted: "
            f"accepted={accepted}/{args.sequences}"
        )
    elapsed = time.monotonic() - started_run
    print(
        f"STAGED_CAPTURE_DONE accepted={accepted}/{args.sequences} "
        f"attempts={attempt} elapsed_seconds={elapsed:.1f} output={output}",
        flush=True,
    )
finally:
    node.destroy_node()
    rclpy.shutdown()
