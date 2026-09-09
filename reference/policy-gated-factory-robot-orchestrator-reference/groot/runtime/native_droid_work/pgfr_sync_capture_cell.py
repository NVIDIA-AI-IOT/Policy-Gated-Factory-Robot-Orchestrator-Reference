# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Install a passive 60 Hz expert state/action observer in the live cell.

The capture camera profile is built at startup and publishes both arm domains
at 30 Hz for native-DROID 15 fps retention.  This adapter creates no camera
graph and applies no robot action.  It observes whichever Franka endpoint owns
the active expert move and the exact arm/finger targets that the certified
RMPflow path applies during the same physics callback.
"""

import json
import os
import traceback


def _capture_render_product_contract(core_contract, vlm_contract, rendered):
    core_products = set(
        (core_contract.get("render_products") or {}).values()
    )
    vlm_products = set(
        (vlm_contract.get("render_products") or {}).values()
    )
    additional_products = vlm_products - core_products
    return bool(
        core_contract.get("camera_profile") == "capture"
        and vlm_contract.get("camera_profile") == "capture"
        and len(core_products) == 6
        and len(additional_products) == 1
        and vlm_contract.get("additional_render_product_count") == 1
        and set(rendered) == core_products | vlm_products
    )


try:
    g = globals()
    g["_PGFR_SYNC_CAPTURE_READY"] = False
    if g.get("_PGFR_EXPERT_ACTION_ORIGINAL_RUN_MOVE") is not None:
        raise RuntimeError("remove the legacy expert-action capture wrapper first")
    if g.get("_PGFR_SYNC_ORIGINAL_RUN_MOVE") is not None:
        raise RuntimeError("synchronized telemetry is already installed")
    sync_install_task = S.get("task") or {}
    if sync_install_task and sync_install_task.get("action") != "reset_scene":
        raise RuntimeError("refusing telemetry install during an active task")
    if os.environ.get("PGFR_CAMERA_PROFILE", "").strip().lower() != "capture":
        raise RuntimeError("Isaac was not launched with PGFR_CAMERA_PROFILE=capture")

    replicator_prefix = "/Render/OmniverseKit/HydraTextures/Replicator"
    render_products = [
        str(prim.GetPath())
        for prim in stage.Traverse()
        if str(prim.GetPath()).startswith(replicator_prefix)
        and str(prim.GetTypeName()) == "RenderProduct"
    ]
    core_camera_contract = dict(g.get("_PGFR_CAMERA_TOPIC_CONTRACT") or {})
    vlm_camera_contract = dict(
        g.get("_PGFR_VLM_CAMERA_TOPIC_CONTRACT") or {}
    )
    if (
        not _capture_render_product_contract(
            core_camera_contract,
            vlm_camera_contract,
            render_products,
        )
        or not stage.GetPrimAtPath("/ROS_CamsRP").IsValid()
    ):
        raise RuntimeError(
            "dual-arm capture contract requires six core products "
            "(inspect shares outside) plus one dedicated VLM product: "
            f"actual={render_products} core={core_camera_contract} "
            f"vlm={vlm_camera_contract}"
        )
    camera_rates = {}
    for camera_path in (
        "/Workcell/Franka_Left/panda_hand/WristCam",
        "/RackCam_B",
        "/Workcell/Franka_Right/panda_hand/WristCam",
        "/RackCam_BR",
        "/Cam_Table",
        "/RackCam_A",
    ):
        attribute = stage.GetPrimAtPath(camera_path).GetAttribute(
            "omni:sensor:tickRate"
        )
        camera_rates[camera_path] = (
            float(attribute.Get()) if attribute.IsValid() else None
        )
    if any(abs((rate or 0.0) - 30.0) > 1e-6 for rate in camera_rates.values()):
        raise RuntimeError(f"capture cameras are not scheduled at 30 Hz: {camera_rates}")

    original_run_move = g["run_move"]
    publisher = node.create_publisher(String, "/pgfr/sync_sample", 200)
    g["_PGFR_SYNC_ORIGINAL_RUN_MOVE"] = original_run_move
    g["_PGFR_SYNC_SAMPLE_PUBLISHER"] = publisher
    g["_PGFR_SYNC_ACTION_TARGET"] = None
    g["_PGFR_SYNC_SEQUENCE"] = 0

    def synchronized_run_move(dt):
        task = S.get("task") or {}
        endpoint = task.get("endpoint") or "franka_left"
        is_franka_expert = (
            task.get("action") == "move"
            and endpoint in ("franka_left", "franka_right")
            and task.get("backend") != "groot"
        )
        if not is_franka_expert:
            return original_run_move(dt)

        arm = frR if endpoint == "franka_right" else frL
        tick = int(S.get("n", 0))
        sim_time_ns = int(round(tick * (1e9 / 60.0)))
        observation = np.asarray(arm.get_joint_positions(), dtype=float).copy()
        if S.get("t", 0) == 0 or g.get("_PGFR_SYNC_ACTION_TARGET") is None:
            g["_PGFR_SYNC_ACTION_TARGET"] = observation.copy()

        action_controller = arm.get_articulation_controller()
        original_apply = action_controller.apply_action

        def capture_apply(*args, **kwargs):
            action = args[0] if args else kwargs.get("control_actions")
            positions = getattr(action, "joint_positions", None)
            indices = getattr(action, "joint_indices", None)
            if positions is not None:
                values = np.asarray(positions, dtype=float).reshape(-1)
                if indices is not None:
                    joint_indices = np.asarray(indices, dtype=int).reshape(-1)
                elif len(values) == 7:
                    joint_indices = np.arange(7, dtype=int)
                elif len(values) == 2:
                    joint_indices = np.asarray([7, 8], dtype=int)
                else:
                    joint_indices = np.arange(len(values), dtype=int)
                target = g["_PGFR_SYNC_ACTION_TARGET"]
                if (
                    len(values) == len(joint_indices)
                    and np.isfinite(values).all()
                    and np.all(joint_indices >= 0)
                    and np.all(joint_indices < len(target))
                ):
                    target[joint_indices] = values
            return original_apply(*args, **kwargs)

        action_controller.apply_action = capture_apply
        try:
            result = original_run_move(dt)
        finally:
            action_controller.apply_action = original_apply

        target = np.asarray(g["_PGFR_SYNC_ACTION_TARGET"], dtype=float).copy()
        if len(observation) >= 8 and len(target) >= 8:
            sequence = int(g["_PGFR_SYNC_SEQUENCE"])
            g["_PGFR_SYNC_SEQUENCE"] = sequence + 1
            publisher.publish(
                String(
                    data=json.dumps(
                        {
                            "schema": 2,
                            "physics_hz": 60,
                            "camera_sensor_hz": 30,
                            "camera_hz": 15,
                            "arm": endpoint,
                            "sequence": sequence,
                            "tick": tick,
                            "task_tick": int(S.get("t", 0)),
                            "sim_time_ns": sim_time_ns,
                            "observation": [
                                round(float(value), 7)
                                for value in observation[:7].tolist()
                                + [float(observation[7])]
                            ],
                            "action": [
                                round(float(value), 7)
                                for value in target[:7].tolist()
                                + [float(target[7])]
                            ],
                            "action_source": "observed_exact_applied_joint_target",
                        }
                    )
                )
            )
        return result

    g["run_move"] = synchronized_run_move
    g["_PGFR_SYNC_CAPTURE_READY"] = True
    print(
        "PGFR_SYNC_CAPTURE_READY schema=2 telemetry_hz=60 "
        "camera_sensor_hz=30 dataset_hz=15 "
        "arms=franka_left,franka_right "
        "cameras=left+right_wrist/outside "
        "telemetry=/pgfr/sync_sample passive_observer=true",
        flush=True,
    )
except Exception:
    globals()["_PGFR_SYNC_CAPTURE_READY"] = False
    install_error = traceback.format_exc()
    old_run_move = globals().pop("_PGFR_SYNC_ORIGINAL_RUN_MOVE", None)
    if old_run_move is not None:
        globals()["run_move"] = old_run_move
    old_publisher = globals().pop("_PGFR_SYNC_SAMPLE_PUBLISHER", None)
    if old_publisher is not None:
        try:
            node.destroy_publisher(old_publisher)
        except Exception:
            pass
    globals().pop("_PGFR_SYNC_ACTION_TARGET", None)
    globals().pop("_PGFR_SYNC_SEQUENCE", None)
    print("PGFR_SYNC_CAPTURE_ERROR:\n" + install_error, flush=True)
    raise
