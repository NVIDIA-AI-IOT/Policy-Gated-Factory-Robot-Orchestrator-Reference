# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Policy-Gated Factory Robot Orchestrator Reference GR00T V36 executor.

This is the directly materialized runtime used by the public integration.  It
preserves the proven physical-friction action path and measured home-convergence
contract without runtime source rewriting.
"""

# GR00T follow-mode patch (reusable). Rebinds run_move->run_groot for backend=="groot".
# grasp_th=0.033, _GN_LIMIT=2800, _GEXEC=16. Underscore-safe (no cell-global clobber).
import numpy as np, traceback, socket, struct, pickle, os as _groot_os
import cv2 as _groot_cv2
try:
    from sensor_msgs.msg import Image
    from scipy.spatial.transform import Rotation as _DroidRotation
    from isaacsim.robot_motion.motion_generation import LulaKinematicsSolver
    g = globals(); g.setdefault("_GRF", {}); g.setdefault("_GN_LIMIT", 2800); g["_GEXEC"] = int(g.get("_GEXEC_OVERRIDE", 16)); g.setdefault("_SMOOTH_A", 1.0)   # 1.0 = OFF (EMA lag hurt grasp precision); rely on training for smoothness
    g.setdefault("_GROOT_RECOVERY_AFTER", 700)
    if g.get("_GRWSUB") is None:
        def _mk(nm):
            def cb(m): g["_GRF"][nm] = m
            return cb
        g["_GRWSUB"] = node.create_subscription(Image, "/wrist_cam/image_raw", _mk("wrist"), 10)
        g["_GROSUB"] = node.create_subscription(Image, "/outside_cam/image_raw", _mk("outside"), 10)

    def _grquery(obs):
        s = g.get("_GRSOCK")
        if s is None:
            _relay_host = str(g.get("_GROOT_RELAY_HOST", "127.0.0.1"))
            _relay_port = int(g.get("_GROOT_RELAY_PORT", 5601))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.connect((_relay_host, _relay_port)); s.settimeout(120); g["_GRSOCK"] = s
        try:
            b = pickle.dumps(obs, protocol=4); s.sendall(struct.pack(">I", len(b)) + b)
            def ra(n):
                buf = b""
                while len(buf) < n:
                    c = s.recv(n - len(buf))
                    if not c: raise IOError("relay closed")
                    buf += c
                return buf
            return pickle.loads(ra(struct.unpack(">I", ra(4))[0]))
        except Exception:
            try: s.close()
            except Exception: pass
            g["_GRSOCK"] = None; raise

    GRASP_TH = 0.033; REL_TH = 0.036
    g.setdefault("_GROOT_SETTLE_FRAMES", 30)
    g.setdefault("_GROOT_MAX_TARGET_STATE_ERROR", 0.12)
    g.setdefault("_GROOT_PHYSICAL_CLOSE_WAIT_LIMIT", 45)
    g.setdefault("_GROOT_PHYSICAL_GRASP_CONFIRM_LIMIT", 45)
    _FRANKA_JOINT_LOWER = np.asarray(
        [-2.8973, -1.7628, -2.8973, -3.0718, -2.8973, -0.0175, -2.8973],
        dtype=float,
    )
    _FRANKA_JOINT_UPPER = np.asarray(
        [2.8973, 1.7628, 2.8973, -0.0698, 2.8973, 3.7525, 2.8973],
        dtype=float,
    )
    if g.get("_GROOT_DROID_KINEMATICS") is None:
        g["_GROOT_DROID_KINEMATICS"] = LulaKinematicsSolver(
            robot_description_path=(
                "/isaac-sim/exts/isaacsim.robot_motion.motion_generation/"
                "motion_policy_configs/franka/rmpflow/robot_descriptor.yaml"
            ),
            urdf_path=(
                "/isaac-sim/exts/isaacsim.robot_motion.motion_generation/"
                "motion_policy_configs/franka/lula_franka_gen.urdf"
            ),
        )
    _DROID_EEF_ROTATION_CORRECT = np.asarray(
        [[0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=float
    )

    def _native_droid_state():
        """Return the stock DROID 17D state components from live Franka joints."""
        positions = np.asarray(frL.get_joint_positions(), dtype=float)
        joints = positions[:7]
        eef_position, eef_rotation = g["_GROOT_DROID_KINEMATICS"].compute_forward_kinematics(
            "panda_link8", joints
        )
        euler_xyz = _DroidRotation.from_matrix(eef_rotation).as_euler("xyz")
        droid_rotation = _DroidRotation.from_euler("XYZ", euler_xyz).as_matrix()
        droid_rotation = droid_rotation @ _DROID_EEF_ROTATION_CORRECT
        eef_9d = np.concatenate(
            [np.asarray(eef_position, dtype=float), droid_rotation[:2].reshape(6)]
        )
        gripper_position = np.asarray(
            [np.clip((0.040 - positions[7]) / (0.040 - 0.016), 0.0, 1.0)],
            dtype=float,
        )
        return joints, eef_9d, gripper_position

    def _groot_language_instruction(color):
        """Use an explicit command instruction, or the staged shape noun."""
        explicit = S["task"].get("language_instruction")
        if explicit:
            return str(explicit)
        noun = g.get("SHAPE_TASK_NOUN", {}).get(color, "cube")
        return "pick the %s %s and place it on the %s pad" % (
            color,
            noun,
            color,
        )

    def _groot_position_action(values, joint_indices=None, joint_velocities=None):
        """Position control with an explicit velocity target (zero by default).

        Isaac Sim retains the last velocity target when ArticulationAction omits
        joint_velocities.  RMPflow therefore leaked stale velocity feed-forward
        into later GR00T rollouts unless it is cleared on every command.
        """
        positions = np.asarray(values, dtype=float)
        velocities = (
            np.zeros_like(positions)
            if joint_velocities is None
            else np.asarray(joint_velocities, dtype=float)
        )
        return ArticulationAction(
            joint_positions=positions,
            joint_velocities=velocities,
            joint_indices=joint_indices,
        )

    def _pgfr_apply_rmpflow_gripper(arm, target):
        """Persist a physical finger target without replacing the arm action."""
        indices = np.asarray(arm.gripper.active_joint_indices, dtype=int)
        values = np.full(indices.shape, float(target), dtype=float)
        arm.apply_action(ArticulationAction(joint_positions=values, joint_indices=indices))

    def _pgfr_rmpflow_gripper_positions(arm):
        try:
            return np.asarray(arm.gripper.get_joint_positions(), dtype=float)
        except Exception:
            return np.asarray([], dtype=float)

    def _record_groot_outside_frame():
        """Record the staged rollout from Isaac's outside camera, when requested."""
        record_dir = S["task"].get("record_dir")
        memory_key = S["task"].get("record_memory_key")
        if not record_dir and not memory_key:
            return
        tick = int(S.get("grecord_tick", 0))
        S["grecord_tick"] = tick + 1
        record_every = max(1, int(S["task"].get("record_every_ticks", 5)))
        if tick % record_every:
            return
        message = g["_GRF"].get("outside")
        if message is None:
            return
        if memory_key:
            frames = g.setdefault(memory_key, [])
            frames.append(message)
            if len(frames) == 1:
                print(
                    "GROOT_MEMORY_RECORD_STARTED key=%s every_ticks=%d"
                    % (memory_key, record_every),
                    flush=True,
                )
            return
        frame = np.frombuffer(bytes(message.data), np.uint8).reshape(
            message.height, message.width, -1
        )
        encoding = str(getattr(message, "encoding", "")).lower()
        if frame.shape[2] == 4:
            conversion = (
                _groot_cv2.COLOR_RGBA2BGR
                if encoding.startswith("rgba")
                else _groot_cv2.COLOR_BGRA2BGR
            )
            frame = _groot_cv2.cvtColor(frame, conversion)
        elif encoding.startswith("rgb"):
            frame = frame[:, :, ::-1]
        frame = np.ascontiguousarray(frame)
        frame_index = int(S.get("grecord_frame", 0))
        _groot_os.makedirs(record_dir, exist_ok=True)
        frame_path = _groot_os.path.join(record_dir, "%06d.jpg" % frame_index)
        if not _groot_cv2.imwrite(
            frame_path, frame, [_groot_cv2.IMWRITE_JPEG_QUALITY, 92]
        ):
            print("GROOT_RECORD_ERROR path=%s" % frame_path, flush=True)
            return
        S["grecord_frame"] = frame_index + 1
        if frame_index == 0:
            print(
                "GROOT_RECORD_STARTED dir=%s every_ticks=%d"
                % (record_dir, record_every),
                flush=True,
            )

    def _run_groot_physical_friction(dt):
        """Execute GR00T joint chunks with a real friction grasp.

        This branch deliberately never changes a cube pose or velocity.  The
        arm receives the seven policy joint targets, while the fingers receive
        a separate indexed position action exactly like the RMPflow expert used
        for the friction demonstrations.  Release is recognized only after a
        near-cube physical close has occurred and the measured fingers reopen.
        """
        col = S["task"].get("color")
        _record_groot_outside_frame()
        if S["task"].get("groot_retrying_home"):
            home_target = np.asarray(
                S["task"].get("groot_home_target", FR_HOME), dtype=float
            )
            if home_target.shape != np.asarray(FR_HOME).shape:
                finish(False, False, "invalid GR00T home target shape")
                return
            frL.apply_action(_groot_position_action(home_target))
            g["_gretry_home_t"] = g.get("_gretry_home_t", 0) + 1
            home_tolerance = float(
                S["task"].get("groot_home_convergence_tolerance", 0.030)
            )
            home_min_ticks = int(
                S["task"].get("groot_home_min_ticks", 120)
            )
            home_settle_ticks = int(
                S["task"].get("groot_home_settle_ticks", 12)
            )
            home_timeout_ticks = int(
                S["task"].get("groot_home_timeout_ticks", 600)
            )
            if (
                abs(home_tolerance - 0.030) > 1e-12
                or home_min_ticks != 120
                or home_settle_ticks != 12
                or home_timeout_ticks != 600
            ):
                finish(False, False, "invalid GR00T home convergence contract")
                return
            home_actual = np.asarray(
                frL.get_joint_positions(), dtype=float
            ).reshape(-1)
            if (
                home_actual.size < 7
                or not np.isfinite(home_actual[:7]).all()
                or not np.isfinite(home_target[:7]).all()
            ):
                finish(False, False, "invalid measured GR00T home joints")
                return
            home_max_error = float(
                np.max(np.abs(home_actual[:7] - home_target[:7]))
            )
            if (
                g["_gretry_home_t"] >= home_min_ticks
                and home_max_error <= home_tolerance
            ):
                g["_gretry_home_settle_t"] = (
                    g.get("_gretry_home_settle_t", 0) + 1
                )
            else:
                g["_gretry_home_settle_t"] = 0
            if g["_gretry_home_settle_t"] >= home_settle_ticks:
                S["task"]["groot_retrying_home"] = False
                S["gbuf"] = None; S["gi"] = 0; S["ghold"] = 0; S["gexec"] = 0; S["gn"] = 0
                S["gphysical_grasp_seen"] = False
                S["gphysical_target_index"] = None
                S["gtracking_replans"] = 0
                S["gpregrasp_alignment_active"] = False
                S["gpregrasp_alignment_done"] = False
                S["gpregrasp_alignment_ticks"] = 0
                S["gpregrasp_alignment_settle"] = 0
                S["gpregrasp_alignment_start_error"] = None
                S["gphysical_grasp_candidate_index"] = None
                S["gphysical_grasp_candidate_cube"] = None
                S["gphysical_grasp_candidate_relative"] = None
                S["gphysical_grasp_candidate_confirm_ticks"] = 0
                S["gphysical_close_wait"] = False
                S["gphysical_close_wait_ticks"] = 0
                S["gphysical_close_target"] = None
                S["gphysical_close_latched"] = False
                S["gphysical_close_latch_ticks"] = 0
                S["gphysical_close_last_action_key"] = None
                S["gphysical_release_zone_ticks"] = 0
                S["gphysical_release_candidate_actions"] = 0
                S["gphysical_release_candidate_key"] = None
                S["gphysical_release_committed"] = False
                S["greleased"] = False; S["greleased_index"] = None
                S["grelease_tick"] = None; S["gsettle"] = 0; S["gsettle_prev"] = None
                S["gpost_success_active"] = False
                S["gpost_success_remaining"] = 0
                g["_grmin"] = 1.0; g["_gdistmin"] = 999.0; g["_smooth"] = None
                ctrl.reset()
                print(
                    "GROOT_PHYSICAL_HOME_READY mode=friction_no_attachment "
                    "ticks=%d settle=%d max_error=%.6f tolerance=%.3f"
                    % (
                        g["_gretry_home_t"],
                        g["_gretry_home_settle_t"],
                        home_max_error,
                        home_tolerance,
                    ),
                    flush=True,
                )
            elif g["_gretry_home_t"] >= home_timeout_ticks:
                finish(
                    False,
                    False,
                    "GR00T home convergence timeout ticks=%d max_error=%.6f "
                    "tolerance=%.3f settle=%d/%d"
                    % (
                        g["_gretry_home_t"],
                        home_max_error,
                        home_tolerance,
                        g["_gretry_home_settle_t"],
                        home_settle_ticks,
                    ),
                )
            return

        if S["gbuf"] is None or S["gi"] >= S["gexec"]:
            w = g["_GRF"].get("wrist"); o = g["_GRF"].get("outside")
            if w is None or o is None:
                S["gnoframe"] = S.get("gnoframe", 0) + 1
                if S["gnoframe"] == 300:
                    print("GROOT_FRAME_WAIT no wrist/outside frames for ~5s", flush=True)
                if S["gnoframe"] >= 1200:
                    finish(False, False, "camera stall: no wrist/outside frames for ~20s — camera pipeline down, task aborted")
                return
            S["gnoframe"] = 0

            def im(message):
                return np.frombuffer(bytes(message.data), np.uint8).reshape(
                    message.height, message.width, -1
                )

            wrist_image, outside_image = im(w), im(o)
            obs = {
                "joints": [float(x) for x in frL.get_joint_positions()[:8]],
                "task": _groot_language_instruction(col),
                "wrist": (wrist_image.tobytes(), wrist_image.shape),
                "outside": (outside_image.tobytes(), outside_image.shape),
            }
            if S["task"].get("native_droid"):
                native_joints, native_eef, native_gripper = _native_droid_state()
                obs.update(
                    {
                        "joint_position": native_joints.tolist(),
                        "eef_9d": native_eef.tolist(),
                        "gripper_position": native_gripper.tolist(),
                    }
                )
            seed_base = g.get("_GROOT_INFERENCE_SEED_BASE")
            query_index = int(g.get("_GROOT_QUERY_INDEX", 0))
            if seed_base is not None:
                obs["inference_seed"] = int(seed_base) + query_index
            print(
                "GROOT_PHYSICAL_QUERY index=%d seed=%s relay=%s:%d"
                % (
                    query_index,
                    obs.get("inference_seed"),
                    g.get("_GROOT_RELAY_HOST", "127.0.0.1"),
                    int(g.get("_GROOT_RELAY_PORT", 5601)),
                ),
                flush=True,
            )
            try:
                trajectory = _grquery(obs)
            except Exception as error:
                finish(False, False, "groot query err: %s" % error)
                return
            g["_GROOT_QUERY_INDEX"] = query_index + 1
            if S["task"].get("native_droid") and not S["task"].get("native_direct"):
                native_arm = np.asarray(trajectory["single_arm"], dtype=float)
                native_rate_hz = float(g.get("_GROOT_NATIVE_CONTROL_HZ", 12.0))
                native_physics_hz = float(g.get("_GROOT_PHYSICS_HZ", 60.0))
                native_substeps = int(round(native_physics_hz / native_rate_hz))
                native_horizon = min(int(g.get("_GEXEC", 15)), len(native_arm))
                if (
                    native_arm.ndim != 2
                    or native_arm.shape[1] != 7
                    or native_horizon < 1
                    or native_substeps < 1
                    or abs(native_substeps * native_rate_hz - native_physics_hz) > 1e-6
                ):
                    finish(False, False, "invalid native-DROID control-rate contract")
                    return
                native_start = np.asarray(frL.get_joint_positions()[:7], dtype=float)
                native_positions = []
                native_velocities = []
                for native_index in range(native_horizon):
                    segment_start = (
                        native_start if native_index == 0 else native_arm[native_index - 1]
                    )
                    segment_end = native_arm[native_index]
                    segment_delta = segment_end - segment_start
                    segment_velocity = segment_delta * native_rate_hz
                    for native_substep in range(1, native_substeps + 1):
                        native_positions.append(
                            segment_start
                            + (float(native_substep) / native_substeps) * segment_delta
                        )
                        native_velocities.append(segment_velocity)
                native_position = np.asarray(native_positions, dtype=float)
                native_velocity = np.asarray(native_velocities, dtype=float)
                native_velocity_limits = np.asarray(
                    [2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61], dtype=float
                )
                if (
                    native_position.shape != native_velocity.shape
                    or not np.isfinite(native_velocity).all()
                    or not np.isfinite(native_position).all()
                    or np.any(np.abs(native_velocity) > native_velocity_limits)
                ):
                    finish(
                        False,
                        False,
                        "native-DROID joint velocity trajectory is invalid or out of range",
                    )
                    return
                native_gripper = np.asarray(trajectory["gripper"][:native_horizon], dtype=float)
                trajectory["single_arm"] = native_position
                trajectory["single_arm_velocity"] = native_velocity
                trajectory["gripper"] = np.repeat(native_gripper, native_substeps, axis=0)
                trajectory["_native_resampled"] = True
                print(
                    "GROOT_NATIVE_DROID_TRAJECTORY policy_hz=%.1f physics_hz=%.1f "
                    "waypoints=%d targets=%d max_velocity=%.4f"
                    % (
                        native_rate_hz,
                        native_physics_hz,
                        native_horizon,
                        len(native_position),
                        float(np.max(np.abs(native_velocity))),
                    ),
                    flush=True,
                )
            S["gbuf"] = trajectory; S["gi"] = 0; S["ghold"] = 0
            S["gexec"] = (
                len(trajectory["single_arm"])
                if trajectory.get("_native_resampled")
                else min(g.get("_GEXEC", 16), len(trajectory["single_arm"]))
            )

        arm7 = np.asarray(S["gbuf"]["single_arm"][S["gi"]], dtype=float)
        arm_velocity = np.asarray(
            S["gbuf"].get("single_arm_velocity", np.zeros_like(S["gbuf"]["single_arm"]))[
                S["gi"]
            ],
            dtype=float,
        )
        gripcmd = float(np.asarray(S["gbuf"]["gripper"][S["gi"]]).reshape(-1)[0])
        if (
            arm7.shape != (7,)
            or arm_velocity.shape != (7,)
            or not np.isfinite(arm7).all()
            or not np.isfinite(arm_velocity).all()
            or not np.isfinite(gripcmd)
        ):
            finish(False, False, "non-finite or malformed GR00T action")
            return
        if not 0.0 <= gripcmd <= 0.05:
            finish(
                False,
                False,
                "GR00T gripper target is outside the permitted range: %.6f" % gripcmd,
            )
            return
        lower_excess = np.maximum(_FRANKA_JOINT_LOWER - arm7, 0.0)
        upper_excess = np.maximum(arm7 - _FRANKA_JOINT_UPPER, 0.0)
        joint_limit_excess = float(
            np.max(np.maximum(lower_excess, upper_excess))
        )
        if joint_limit_excess > 1e-6:
            marginal_margin = float(
                S["task"].get("raw_joint_limit_replan_margin", 0.015)
            )
            marginal_limit = int(
                S["task"].get("raw_joint_limit_replan_limit", 4)
            )
            marginal_count = int(
                S["task"].get("raw_joint_limit_replans_used", 0)
            )
            if (
                not 0.0 <= marginal_margin <= 0.040
                or not 0 <= marginal_limit <= 6
            ):
                finish(
                    False,
                    False,
                    "invalid raw joint-limit replan contract "
                    "margin=%.6f limit=%d"
                    % (marginal_margin, marginal_limit),
                )
                return
            if (
                joint_limit_excess <= marginal_margin
                and marginal_count < marginal_limit
            ):
                S["task"]["raw_joint_limit_replans_used"] = (
                    marginal_count + 1
                )
                print(
                    "GROOT_RAW_JOINT_LIMIT_REQUERY query=%d gi=%d "
                    "max_excess=%.6f replan=%d/%d "
                    "chunk_discarded=true waypoint_applied=false raw=%s"
                    % (
                        int(g.get("_GROOT_QUERY_INDEX", 0)),
                        int(S["gi"]),
                        joint_limit_excess,
                        marginal_count + 1,
                        marginal_limit,
                        [round(float(value), 6) for value in arm7],
                    ),
                    flush=True,
                )
                S["gbuf"] = None
                S["gi"] = 0
                S["ghold"] = 0
                S["gexec"] = 0
                return
            print(
                "GROOT_RAW_JOINT_LIMIT_ABORT query=%d gi=%d "
                "max_excess=%.6f margin=%.6f replans=%d/%d raw=%s"
                % (
                    int(g.get("_GROOT_QUERY_INDEX", 0)),
                    int(S["gi"]),
                    joint_limit_excess,
                    marginal_margin,
                    marginal_count,
                    marginal_limit,
                    [round(float(value), 6) for value in arm7],
                ),
                flush=True,
            )
            finish(
                False,
                False,
                "raw GR00T joint waypoint outside Franka limits "
                "query=%d gi=%d excess=%.6f replans=%d/%d"
                % (
                    int(g.get("_GROOT_QUERY_INDEX", 0)),
                    int(S["gi"]),
                    joint_limit_excess,
                    marginal_count,
                    marginal_limit,
                ),
            )
            return

        hand_position, hand_quaternion = fhand.get_world_pose()
        grasp = np.asarray(hand_position) + qrot(
            hand_quaternion, np.array([0.0, 0.0, GRASP_L])
        )
        target_candidates = [
            index for index in ACTIVE if POOL_COL[index] == col
        ]
        nearest_index = None
        nearest_distance = float("inf")
        if target_candidates:
            nearest_index, nearest_distance = min(
                (
                    index,
                    float(
                        np.linalg.norm(
                            grasp - np.asarray(wrp[index].get_world_pose()[0], dtype=float)
                        )
                    ),
                )
                for index in target_candidates
            )
            g["_gdistmin"] = min(g.get("_gdistmin", 999.0), nearest_distance)

        near_limit = float(g.get("_PGFR_LOCK_R", 0.06))
        actual_arm = np.asarray(frL.get_joint_positions()[:7], dtype=float)
        raw_close_requested = gripcmd < g.get("_PGFR_GRASP_TH", GRASP_TH)
        target_close_guard_enabled = bool(
            S["task"].get("target_aware_pregrasp_close_gate", False)
        )
        target_close_admission_radius = float(
            S["task"].get("target_close_admission_radius", near_limit)
        )
        if (
            target_close_guard_enabled
            and not 0.0 < target_close_admission_radius <= near_limit
        ):
            finish(
                False,
                False,
                "invalid target close admission radius %.4f"
                % target_close_admission_radius,
            )
            return
        target_close_guard = bool(
            target_close_guard_enabled
            and not S.get("gphysical_grasp_seen")
            and raw_close_requested
            and (
                nearest_index is None
                or nearest_distance >= target_close_admission_radius
            )
        )
        close_requested = bool(raw_close_requested and not target_close_guard)
        if target_close_guard and not S.get("gtarget_close_suppressed", False):
            print(
                "GROOT_TARGET_CLOSE_SUPPRESSED query=%d gi=%d "
                "cube=%s hand2target=%.4f admission=%.4f "
                "gripper_forced_open=true close_wait_blocked=true"
                % (
                    int(g.get("_GROOT_QUERY_INDEX", 0)),
                    int(S["gi"]),
                    nearest_index,
                    nearest_distance,
                    target_close_admission_radius,
                ),
                flush=True,
            )
        S["gtarget_close_suppressed"] = target_close_guard

        alignment_pose_value = S["task"].get("pregrasp_alignment_pose")
        alignment_enabled = (
            alignment_pose_value is not None
            and not S.get("gpregrasp_alignment_done")
            and not S.get("gphysical_grasp_seen")
        )
        if (
            alignment_enabled
            and not S.get("gpregrasp_alignment_active")
            and not close_requested
            and nearest_index is not None
            and nearest_distance
            <= float(S["task"].get("pregrasp_alignment_radius", 0.055))
        ):
            alignment_pose = np.asarray(alignment_pose_value, dtype=float)
            if (
                alignment_pose.shape != (7,)
                or not np.isfinite(alignment_pose).all()
            ):
                finish(False, False, "invalid pregrasp alignment pose")
                return
            S["gpregrasp_alignment_active"] = True
            S["gpregrasp_alignment_ticks"] = 0
            S["gpregrasp_alignment_settle"] = 0
            S["gpregrasp_alignment_start_error"] = float(
                np.max(np.abs(alignment_pose - actual_arm))
            )
            print(
                "GROOT_PREGRASP_ALIGN_START gn=%d layout=%s cube=%d "
                "hand2cube=%.4f state_error=%.4f source=%s"
                % (
                    S["gn"],
                    S["task"].get("rollout_layout"),
                    nearest_index,
                    nearest_distance,
                    S["gpregrasp_alignment_start_error"],
                    S["task"].get("pregrasp_alignment_source"),
                ),
                flush=True,
            )

        if S.get("gpregrasp_alignment_active"):
            alignment_pose = np.asarray(
                S["task"]["pregrasp_alignment_pose"], dtype=float
            )
            alignment_error = float(
                np.max(np.abs(alignment_pose - actual_arm))
            )
            alignment_velocity_limits = np.asarray(
                [2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61],
                dtype=float,
            )
            alignment_max_step = (
                alignment_velocity_limits
                * float(
                    S["task"].get(
                        "pregrasp_alignment_velocity_fraction", 0.20
                    )
                )
                / float(g.get("_GROOT_PHYSICS_HZ", 60.0))
            )
            alignment_target = actual_arm + np.clip(
                alignment_pose - actual_arm,
                -alignment_max_step,
                alignment_max_step,
            )
            frL.apply_action(
                _groot_position_action(
                    alignment_target,
                    joint_indices=np.arange(7, dtype=int),
                    joint_velocities=np.zeros(7, dtype=float),
                )
            )
            _pgfr_apply_rmpflow_gripper(frL, GR_OPEN)
            S["gpregrasp_alignment_ticks"] = (
                int(S.get("gpregrasp_alignment_ticks", 0)) + 1
            )
            if (
                S["gpregrasp_alignment_ticks"] == 1
                or S["gpregrasp_alignment_ticks"] % 60 == 0
            ):
                print(
                    "GROOT_PREGRASP_ALIGN_PROGRESS gn=%d ticks=%d "
                    "state_error=%.4f actual=%s delta=%s"
                    % (
                        S["gn"],
                        S["gpregrasp_alignment_ticks"],
                        alignment_error,
                        np.round(actual_arm, 5).tolist(),
                        np.round(alignment_pose - actual_arm, 5).tolist(),
                    ),
                    flush=True,
                )
            alignment_tolerance = float(
                S["task"].get("pregrasp_alignment_tolerance", 0.012)
            )
            if alignment_error <= alignment_tolerance:
                S["gpregrasp_alignment_settle"] = (
                    int(S.get("gpregrasp_alignment_settle", 0)) + 1
                )
            else:
                S["gpregrasp_alignment_settle"] = 0
            if S["gpregrasp_alignment_settle"] >= 3:
                print(
                    "GROOT_PREGRASP_ALIGN_DONE gn=%d ticks=%d "
                    "state_error=%.4f hand2cube=%.4f requery=true"
                    % (
                        S["gn"],
                        S["gpregrasp_alignment_ticks"],
                        alignment_error,
                        nearest_distance,
                    ),
                    flush=True,
                )
                S["gpregrasp_alignment_active"] = False
                S["gpregrasp_alignment_done"] = True
                S["gbuf"] = None
                S["gi"] = 0
                S["ghold"] = 0
                S["gtracking_replans"] = 0
                g["_smooth"] = actual_arm.copy()
            elif S["gpregrasp_alignment_ticks"] >= int(
                S["task"].get("pregrasp_alignment_tick_limit", 240)
            ):
                finish(
                    False,
                    False,
                    "pregrasp alignment timeout error=%.4f"
                    % alignment_error,
                )
                return
            S["gn"] += 1
            return
        close_action_key = (
            int(g.get("_GROOT_QUERY_INDEX", 0)),
            int(S["gi"]),
        )
        if (
            not S.get("gphysical_close_wait")
            and not S.get("gphysical_close_latched")
            and not S.get("gphysical_grasp_seen")
            and close_requested
            and nearest_index is not None
            and nearest_distance < near_limit
            and close_action_key != S.get("gphysical_close_last_action_key")
        ):
            S["gphysical_close_wait"] = True
            S["gphysical_close_wait_ticks"] = 0
            S["gphysical_close_target"] = actual_arm.copy()
            S["gphysical_close_latched"] = True
            S["gphysical_close_latch_ticks"] = 0
            S["gphysical_close_last_action_key"] = close_action_key
            print(
                "GROOT_PHYSICAL_CLOSE_WAIT_START gn=%d cube=%d "
                "hand2cube=%.4f native_direct=%s"
                % (
                    S["gn"],
                    nearest_index,
                    nearest_distance,
                    S["task"].get("native_direct"),
                ),
                flush=True,
            )

        close_waiting = bool(S.get("gphysical_close_wait"))
        smooth_alpha = g.get("_SMOOTH_A", 1.0)
        previous_arm = g.get("_smooth")
        requested_arm_target = (
            np.asarray(S["gphysical_close_target"], dtype=float)
            if close_waiting
            else (
                arm7
                if previous_arm is None
                else smooth_alpha * arm7 + (1.0 - smooth_alpha) * previous_arm
            )
        )
        requested_target_state_error = float(
            np.max(np.abs(requested_arm_target - actual_arm))
        )
        arm_target = requested_arm_target
        if S["task"].get("tracking_gated_progress") and not close_waiting:
            # Rate-limit the transition toward the recorded/predicted DROID
            # waypoint using Franka's native per-joint velocity limits.  The
            # waypoint itself remains unchanged and the progression gate below
            # does not advance until the articulation reaches it.
            tracking_velocity_fraction = float(
                S["task"].get("tracking_command_velocity_fraction", 1.0)
            )
            tracking_velocity_limits = np.asarray(
                [2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61], dtype=float
            )
            tracking_max_step = (
                tracking_velocity_limits
                * tracking_velocity_fraction
                / float(g.get("_GROOT_PHYSICS_HZ", 60.0))
            )
            arm_target = actual_arm + np.clip(
                requested_arm_target - actual_arm,
                -tracking_max_step,
                tracking_max_step,
            )
        commanded_arm_velocity = np.zeros(7, dtype=float) if close_waiting else arm_velocity
        target_state_error = float(np.max(np.abs(arm_target - actual_arm)))
        target_state_limit = float(g.get("_GROOT_MAX_TARGET_STATE_ERROR", 0.12))
        tracking_guard_enabled = bool(
            S["task"].get("tracking_guard_enabled", True)
        )
        if tracking_guard_enabled and target_state_error > target_state_limit:
            print(
                "GROOT_TARGET_TRACKING_ABORT gn=%d target_state_error=%.4f limit=%.4f"
                % (S["gn"], target_state_error, target_state_limit),
                flush=True,
            )
            finish(
                False,
                False,
                "arm target-state error exceeded the configured limit: %.4f > %.4f"
                % (target_state_error, target_state_limit),
            )
            return
        g["_smooth"] = arm_target
        frL.apply_action(
            _groot_position_action(
                arm_target,
                joint_indices=np.arange(7, dtype=int),
                joint_velocities=commanded_arm_velocity,
            )
        )

        # A freshly queried action chunk can contain a short, contradictory
        # gripper-open prefix.  Once a friction grasp is physically verified,
        # reject those transit-time pulses.  Release remains policy-triggered,
        # but is admitted only over the destination and after consecutive
        # open actions; after admission it is latched open for this one-pick
        # task so a later chunk cannot re-grasp the object.
        applied_gripcmd = (
            GR_OPEN
            if target_close_guard
            else (
                float(S["task"].get("physical_grip_hold_target", 0.016))
                if (
                    S.get("gphysical_close_wait")
                    or (
                        S.get("gphysical_close_latched")
                        and not S.get("gphysical_grasp_seen")
                    )
                )
                else gripcmd
            )
        )
        release_zone = False
        release_xy_error = float("inf")
        release_height = float("inf")
        release_gate_enabled = bool(
            S["task"].get("physical_release_gate", False)
        )
        target_index = S.get("gphysical_target_index")
        if (
            release_gate_enabled
            and S.get("gphysical_grasp_seen")
            and target_index in ACTIVE
        ):
            target_position = np.asarray(
                wrp[target_index].get_world_pose()[0], dtype=float
            )
            compartment = np.asarray(comp_world(col), dtype=float)
            release_xy_error = float(
                np.linalg.norm(target_position[:2] - compartment[:2])
            )
            release_height = float(target_position[2] - compartment[2])
            release_zone = bool(
                release_xy_error
                <= float(S["task"].get("physical_release_xy_radius", 0.06))
                and release_height
                >= float(S["task"].get("physical_release_min_height", -0.01))
                and release_height
                <= float(S["task"].get("physical_release_max_height", 0.20))
            )
            S["gphysical_release_zone_ticks"] = (
                int(S.get("gphysical_release_zone_ticks", 0)) + 1
                if release_zone
                else 0
            )
            policy_open_requested = gripcmd > g.get("_PGFR_REL_TH", REL_TH)
            release_action_key = (
                int(g.get("_GROOT_QUERY_INDEX", 0)),
                int(S["gi"]),
            )
            fallback_stall_ticks = max(
                0,
                int(
                    S["task"].get(
                        "physical_release_fallback_stall_ticks",
                        45,
                    )
                ),
            )
            fallback_ready = bool(
                release_zone
                and fallback_stall_ticks
                and int(S.get("gphysical_release_zone_ticks", 0))
                >= fallback_stall_ticks
            )
            if S.get("gphysical_release_committed"):
                applied_gripcmd = GR_OPEN
            elif fallback_ready:
                S["gphysical_release_committed"] = True
                applied_gripcmd = GR_OPEN
                print(
                    "GROOT_PHYSICAL_RELEASE_COMMITTED "
                    "mode=geometry_fallback gn=%d policy=%.4f xy=%.4f "
                    "height=%.4f held_ticks=%d threshold=%d"
                    % (
                        S["gn"],
                        gripcmd,
                        release_xy_error,
                        release_height,
                        int(S.get("gphysical_release_zone_ticks", 0)),
                        fallback_stall_ticks,
                    ),
                    flush=True,
                )
            elif policy_open_requested and release_zone:
                if (
                    release_action_key
                    != S.get("gphysical_release_candidate_key")
                ):
                    S["gphysical_release_candidate_key"] = release_action_key
                    S["gphysical_release_candidate_actions"] = (
                        int(S.get("gphysical_release_candidate_actions", 0)) + 1
                    )
                required_actions = max(
                    1,
                    int(
                        S["task"].get(
                            "physical_release_confirm_actions",
                            2,
                        )
                    ),
                )
                if (
                    S["gphysical_release_candidate_actions"]
                    >= required_actions
                ):
                    S["gphysical_release_committed"] = True
                    applied_gripcmd = GR_OPEN
                    print(
                        "GROOT_PHYSICAL_RELEASE_COMMITTED "
                        "mode=policy gn=%d policy=%.4f xy=%.4f "
                        "height=%.4f actions=%d"
                        % (
                            S["gn"],
                            gripcmd,
                            release_xy_error,
                            release_height,
                            S["gphysical_release_candidate_actions"],
                        ),
                        flush=True,
                    )
                else:
                    applied_gripcmd = float(
                        S["task"].get("physical_grip_hold_target", 0.016)
                    )
            elif policy_open_requested:
                S["gphysical_release_candidate_actions"] = 0
                S["gphysical_release_candidate_key"] = None
                applied_gripcmd = float(
                    S["task"].get("physical_grip_hold_target", 0.016)
                )
                if release_action_key != S.get(
                    "gphysical_release_last_suppressed_key"
                ):
                    S["gphysical_release_last_suppressed_key"] = release_action_key
                    print(
                        "GROOT_PHYSICAL_RELEASE_SUPPRESSED "
                        "gn=%d policy=%.4f xy=%.4f height=%.4f"
                        % (
                            S["gn"],
                            gripcmd,
                            release_xy_error,
                            release_height,
                        ),
                        flush=True,
                    )
            else:
                S["gphysical_release_candidate_actions"] = 0
                S["gphysical_release_candidate_key"] = None

        _pgfr_apply_rmpflow_gripper(frL, applied_gripcmd)
        measured = _pgfr_rmpflow_gripper_positions(frL)
        g["_grmin"] = min(g.get("_grmin", 1.0), applied_gripcmd)

        physically_closed = (
            applied_gripcmd < g.get("_PGFR_GRASP_TH", GRASP_TH)
            and measured.size > 0
            and float(np.max(measured)) <= GR_SNUG + 0.006
        )
        if not S.get("gphysical_grasp_seen"):
            candidate_index = S.get("gphysical_grasp_candidate_index")
            candidate_ready = bool(
                physically_closed
                and nearest_index is not None
                and nearest_distance < near_limit
            )
            if candidate_ready:
                cube_position = np.asarray(
                    wrp[nearest_index].get_world_pose()[0],
                    dtype=float,
                )
                hand_to_cube = cube_position - grasp
                if candidate_index != nearest_index:
                    S["gphysical_grasp_candidate_index"] = nearest_index
                    S["gphysical_grasp_candidate_cube"] = cube_position.copy()
                    S["gphysical_grasp_candidate_relative"] = hand_to_cube.copy()
                    S["gphysical_grasp_candidate_confirm_ticks"] = 0
                    print(
                        "GROOT_PHYSICAL_GRASP_CANDIDATE "
                        "cube=%d col=%s gn=%d fingers=%s hand2cube=%.4f"
                        % (
                            nearest_index,
                            col,
                            S["gn"],
                            [round(float(value), 4) for value in measured],
                            nearest_distance,
                        ),
                        flush=True,
                    )
                else:
                    candidate_cube = np.asarray(
                        S["gphysical_grasp_candidate_cube"],
                        dtype=float,
                    )
                    candidate_relative = np.asarray(
                        S["gphysical_grasp_candidate_relative"],
                        dtype=float,
                    )
                    lift = float(cube_position[2] - candidate_cube[2])
                    relative_drift = float(
                        np.linalg.norm(hand_to_cube - candidate_relative)
                    )
                    confirm_lift = float(
                        S["task"].get("physical_grasp_confirm_lift", 0.004)
                    )
                    confirm_drift = float(
                        S["task"].get("physical_grasp_confirm_drift", 0.012)
                    )
                    if lift >= confirm_lift and relative_drift <= confirm_drift:
                        S["gphysical_grasp_candidate_confirm_ticks"] = (
                            int(
                                S.get(
                                    "gphysical_grasp_candidate_confirm_ticks",
                                    0,
                                )
                            )
                            + 1
                        )
                    else:
                        S["gphysical_grasp_candidate_confirm_ticks"] = 0
                    required_ticks = max(
                        1,
                        int(S["task"].get("physical_grasp_confirm_ticks", 3)),
                    )
                    if (
                        S["gphysical_grasp_candidate_confirm_ticks"]
                        >= required_ticks
                    ):
                        S["gphysical_grasp_seen"] = True
                        S["gphysical_target_index"] = nearest_index
                        S["physical_grip_closed"] = True
                        S["gphysical_close_latched"] = False
                        print(
                            "GROOT_PHYSICAL_GRASP "
                            "cube=%d col=%s gn=%d fingers=%s "
                            "hand2cube=%.4f lift=%.4f drift=%.4f ticks=%d"
                            % (
                                nearest_index,
                                col,
                                S["gn"],
                                [round(float(value), 4) for value in measured],
                                nearest_distance,
                                lift,
                                relative_drift,
                                S["gphysical_grasp_candidate_confirm_ticks"],
                            ),
                            flush=True,
                        )
            elif candidate_index is not None and not close_waiting:
                print(
                    "GROOT_PHYSICAL_GRASP_CANDIDATE_REJECTED "
                    "cube=%s col=%s gn=%d closed=%s hand2cube=%.4f"
                    % (
                        candidate_index,
                        col,
                        S["gn"],
                        physically_closed,
                        nearest_distance,
                    ),
                    flush=True,
                )
                S["gphysical_grasp_candidate_index"] = None
                S["gphysical_grasp_candidate_cube"] = None
                S["gphysical_grasp_candidate_relative"] = None
                S["gphysical_grasp_candidate_confirm_ticks"] = 0
                S["gphysical_close_latched"] = False

        if close_waiting:
            S["gphysical_close_wait_ticks"] = (
                int(S.get("gphysical_close_wait_ticks", 0)) + 1
            )
            if (
                physically_closed
                and nearest_index is not None
                and nearest_distance < near_limit
            ):
                S["gphysical_close_wait"] = False
                S["gphysical_close_target"] = None
                print(
                    "GROOT_PHYSICAL_CLOSE_WAIT_DONE gn=%d ticks=%d "
                    "result=physical_contact"
                    % (S["gn"], S["gphysical_close_wait_ticks"]),
                    flush=True,
                )
            elif S["gphysical_close_wait_ticks"] >= int(
                g.get("_GROOT_PHYSICAL_CLOSE_WAIT_LIMIT", 45)
            ):
                S["gphysical_close_wait"] = False
                S["gphysical_close_target"] = None
                S["gphysical_close_latched"] = False
                S["gphysical_grasp_candidate_index"] = None
                S["gphysical_grasp_candidate_cube"] = None
                S["gphysical_grasp_candidate_relative"] = None
                S["gphysical_grasp_candidate_confirm_ticks"] = 0
                print(
                    "GROOT_PHYSICAL_CLOSE_WAIT_DONE gn=%d ticks=%d result=timeout"
                    % (S["gn"], S["gphysical_close_wait_ticks"]),
                    flush=True,
                )
            else:
                S["gn"] += 1
                return

        if S.get("gphysical_close_latched") and not S.get("gphysical_grasp_seen"):
            S["gphysical_close_latch_ticks"] = (
                int(S.get("gphysical_close_latch_ticks", 0)) + 1
            )
            if S["gphysical_close_latch_ticks"] >= int(
                g.get("_GROOT_PHYSICAL_GRASP_CONFIRM_LIMIT", 45)
            ):
                S["gphysical_close_latched"] = False
                S["gphysical_grasp_candidate_index"] = None
                S["gphysical_grasp_candidate_cube"] = None
                S["gphysical_grasp_candidate_relative"] = None
                S["gphysical_grasp_candidate_confirm_ticks"] = 0
                print(
                    "GROOT_PHYSICAL_GRASP_CONFIRM_TIMEOUT gn=%d ticks=%d"
                    % (S["gn"], S["gphysical_close_latch_ticks"]),
                    flush=True,
                )

        measured_open = (
            measured.size > 0
            and float(np.min(measured)) >= GR_OPEN - 0.005
        )
        if (
            S.get("gphysical_grasp_seen")
            and not S.get("greleased")
            and applied_gripcmd > g.get("_PGFR_REL_TH", REL_TH)
            and measured_open
        ):
            S["greleased"] = True
            S["greleased_index"] = S.get("gphysical_target_index")
            S["grelease_tick"] = S["gn"]
            S["gsettle"] = 0; S["gsettle_prev"] = None
            print(
                "GROOT_PHYSICAL_RELEASE cube=%s col=%s gn=%d command=%.4f fingers=%s"
                % (
                    S["greleased_index"],
                    col,
                    S["gn"],
                    applied_gripcmd,
                    [round(float(value), 4) for value in measured],
                ),
                flush=True,
            )

        if S["gn"] % 60 == 0:
            print(
                "GRDBG_PHYSICAL gn=%d policy_grip=%.4f applied_grip=%.4f "
                "fingers=%s jerr=%.4f hand2cube=%.4f grasp_seen=%s "
                "release_zone=%s release_xy=%.4f release_height=%.4f released=%s"
                % (
                    S["gn"],
                    gripcmd,
                    applied_gripcmd,
                    [round(float(value), 4) for value in measured],
                    float(np.max(np.abs(arm7 - actual_arm))),
                    nearest_distance,
                    S.get("gphysical_grasp_seen", False),
                    release_zone,
                    release_xy_error,
                    release_height,
                    S.get("greleased", False),
                ),
                flush=True,
            )

        S["ghold"] += 1
        hold_ticks = 1 if S["gbuf"].get("_native_resampled") else g.get("_GHOLD", 5)
        if S["task"].get("tracking_gated_progress"):
            # The official DROID client emits joint-position actions at 12 Hz.
            # Preserve that minimum cadence, but do not advance farther along
            # an open-loop chunk while the simulated articulation is still
            # catching the current target.  This keeps the unchanged 0.12-rad
            # tracking guard meaningful and prevents tracking lag from
            # accumulating across the carry phase.
            tracking_tolerance = float(
                S["task"].get("tracking_progress_tolerance", 0.03)
            )
            tracking_hold_limit = int(
                S["task"].get("tracking_progress_hold_limit", 180)
            )
            if (
                S["ghold"] >= hold_ticks
                and requested_target_state_error <= tracking_tolerance
            ):
                if S["ghold"] > hold_ticks and S["gi"] % 15 == 0:
                    print(
                        "GROOT_TRACKING_GATE_CAUGHT_UP gi=%d held_ticks=%d error=%.4f"
                        % (S["gi"], S["ghold"], requested_target_state_error),
                        flush=True,
                    )
                S["gi"] += 1
                S["ghold"] = 0
                if (
                    S.get("gphysical_grasp_seen")
                    and int(S.get("gtracking_replans", 0))
                ):
                    print(
                        "GROOT_TRACKING_REPLAN_RECOVERED "
                        "phase=post_grasp successful_action_progress=true "
                        "prior_replans=%d"
                        % int(S["gtracking_replans"]),
                        flush=True,
                    )
                    S["gtracking_replans"] = 0
            elif S["ghold"] >= tracking_hold_limit:
                replans = int(S.get("gtracking_replans", 0))
                replan_limit = int(
                    S["task"].get("tracking_replan_limit", 6)
                )
                print(
                    "GROOT_TRACKING_REPLAN_DETAIL "
                    "query=%d gi=%d held_ticks=%d replan=%d/%d "
                    "requested=%s measured=%s delta=%s"
                    % (
                        int(g.get("_GROOT_QUERY_INDEX", 0)),
                        S["gi"],
                        S["ghold"],
                        replans,
                        replan_limit,
                        [
                            round(float(value), 5)
                            for value in requested_arm_target
                        ],
                        [round(float(value), 5) for value in actual_arm],
                        [
                            round(float(value), 5)
                            for value in requested_arm_target - actual_arm
                        ],
                    ),
                    flush=True,
                )
                if replans >= replan_limit:
                    finish(
                        False,
                        False,
                        "groot tracking replan limit reached "
                        "gi=%d error=%.4f tolerance=%.4f replans=%d"
                        % (
                            S["gi"],
                            requested_target_state_error,
                            tracking_tolerance,
                            replans,
                        ),
                    )
                    return
                S["gtracking_replans"] = replans + 1
                S["gbuf"] = None
                S["gi"] = 0
                S["ghold"] = 0
                S["gexec"] = 0
                g["_smooth"] = actual_arm.copy()
                print(
                    "GROOT_TRACKING_REPLAN query=%d next_replan=%d "
                    "action_clock_advanced=false"
                    % (
                        int(g.get("_GROOT_QUERY_INDEX", 0)),
                        S["gtracking_replans"],
                    ),
                    flush=True,
                )
                return
        elif S["ghold"] >= hold_ticks:
            S["gi"] += 1; S["ghold"] = 0
        S["gn"] += 1

        if S.get("gpost_success_active"):
            remaining = int(S.get("gpost_success_remaining", 0)) - 1
            S["gpost_success_remaining"] = remaining
            if remaining <= 0:
                released_index = S.get("greleased_index")
                position = np.asarray(wrp[released_index].get_world_pose()[0], dtype=float)
                compartment = comp_world(col)
                offset = float(np.linalg.norm(position[:2] - np.asarray(compartment[:2])))
                finish(
                    True,
                    True,
                    "groot physical-friction released+settled %s off=%.3f z=%.3f "
                    "release_gn=%d gn=%d post_success_tail=true"
                    % (col, offset, position[2], S["grelease_tick"], S["gn"]),
                )
            return

        released_index = S.get("greleased_index")
        if S.get("greleased") and released_index in ACTIVE:
            position = np.asarray(wrp[released_index].get_world_pose()[0], dtype=float)
            compartment = comp_world(col)
            previous_position = S.get("gsettle_prev")
            motion = (
                float(np.linalg.norm(position - previous_position))
                if previous_position is not None
                else float("inf")
            )
            S["gsettle_prev"] = position.copy()
            in_compartment = (
                abs(position[0] - compartment[0]) < 0.08
                and abs(position[1] - compartment[1]) < 0.08
                and 0.68 < position[2] < 0.715
            )
            S["gsettle"] = S.get("gsettle", 0) + 1 if in_compartment and motion < 0.0005 else 0
            if S["gsettle"] >= g["_GROOT_SETTLE_FRAMES"]:
                offset = float(np.linalg.norm(position[:2] - np.asarray(compartment[:2])))
                post_success_ticks = max(
                    0, int(S["task"].get("post_success_ticks", 0))
                )
                if post_success_ticks:
                    S["gpost_success_active"] = True
                    S["gpost_success_remaining"] = post_success_ticks
                    print(
                        "GROOT_POST_SUCCESS_TAIL_STARTED ticks=%d off=%.3f"
                        % (post_success_ticks, offset),
                        flush=True,
                    )
                    return
                finish(
                    True,
                    True,
                    "groot physical-friction released+settled %s off=%.3f z=%.3f release_gn=%d gn=%d"
                    % (col, offset, position[2], S["grelease_tick"], S["gn"]),
                )
                return

        if S["gn"] > g.get("_GN_LIMIT", 2800):
            finish(
                False,
                False,
                "groot physical-friction timeout gn=%d grmin=%.3f grasp_seen=%s released=%s settle=%d"
                % (
                    S["gn"],
                    g.get("_grmin", -1.0),
                    S.get("gphysical_grasp_seen", False),
                    S.get("greleased", False),
                    S.get("gsettle", 0),
                ),
            )


    def run_groot(dt):
        if S["task"].get("physical_friction"):
            _run_groot_physical_friction(dt)
            return
        col = S["task"].get("color")
        if S["task"].get("groot_retrying_home"):
            # Re-run the stochastic policy from its demonstrated home pose,
            # keeping the cube and scene unchanged.
            frL.apply_action(_groot_position_action(FR_HOME))
            g["_gretry_home_t"] = g.get("_gretry_home_t", 0) + 1
            if g["_gretry_home_t"] >= 120:
                S["task"]["groot_retrying_home"] = False
                S["gbuf"] = None; S["gi"] = 0; S["ghold"] = 0; S["gexec"] = 0; S["gn"] = 0
                g["_grmin"] = 1.0; g["_gdistmin"] = 999.0; g["_smooth"] = None
                ctrl.reset()
                print(
                    "GROOT_RETRY_READY attempt=%d"
                    % (S["task"].get("groot_retry_count", 0) + 1),
                    flush=True,
                )
            return
        if S["gbuf"] is None or S["gi"] >= S["gexec"]:
            w = g["_GRF"].get("wrist"); o = g["_GRF"].get("outside")
            if w is None or o is None:
                # frame-stall watchdog: fail loud instead of holding the task
                # slot forever when the camera pipeline is down (2026-07-16 class)
                S["gnoframe"] = S.get("gnoframe", 0) + 1
                if S["gnoframe"] == 300:
                    print("GROOT_FRAME_WAIT no wrist/outside frames for ~5s", flush=True)
                if S["gnoframe"] >= 1200:
                    finish(False, False, "camera stall: no wrist/outside frames for ~20s — camera pipeline down, task aborted")
                return
            S["gnoframe"] = 0
            def im(m): return np.frombuffer(bytes(m.data), np.uint8).reshape(m.height, m.width, -1)
            wi, oi = im(w), im(o)
            obs = {"joints": [float(x) for x in frL.get_joint_positions()[:8]],
                   "task": _groot_language_instruction(col),
                   "wrist": (wi.tobytes(), wi.shape), "outside": (oi.tobytes(), oi.shape)}
            _seed_base = g.get("_GROOT_INFERENCE_SEED_BASE")
            _query_index = int(g.get("_GROOT_QUERY_INDEX", 0))
            if _seed_base is not None:
                obs["inference_seed"] = int(_seed_base) + _query_index
            print(
                "GROOT_QUERY index=%d seed=%s"
                % (_query_index, obs.get("inference_seed")),
                flush=True,
            )
            try: traj = _grquery(obs)
            except Exception as e: finish(False, False, "groot query err: %s" % e); return
            g["_GROOT_QUERY_INDEX"] = _query_index + 1
            S["gbuf"] = traj; S["gi"] = 0; S["ghold"] = 0; S["gexec"] = min(g.get("_GEXEC", 8), len(traj["single_arm"]))
        arm7 = np.asarray(S["gbuf"]["single_arm"][S["gi"]], dtype=float)
        gripcmd = float(np.asarray(S["gbuf"]["gripper"][S["gi"]]).flatten()[0])
        g["_grmin"] = min(g.get("_grmin", 1.0), gripcmd)
        hp, hq = fhand.get_world_pose(); hp = np.array(hp); grasp = hp + qrot(hq, np.array([0.0, 0.0, GRASP_L]))
        _acubes = [np.array(wrp[i].get_world_pose()[0]) for i in ACTIVE if POOL_COL[i] == col]
        _hc = min([float(np.linalg.norm(grasp - c)) for c in _acubes]) if _acubes else -1.0
        if _hc >= 0.0:
            g["_gdistmin"] = min(g.get("_gdistmin", 999.0), _hc)
        if S["gn"] % 60 == 0:
            cc = comp_world(col)
            _ach = np.asarray(frL.get_joint_positions()[:7], dtype=float); _je = float(np.max(np.abs(arm7 - _ach)))
            print("GRDBG gn=%d grip=%.3f grmin=%.3f graspXYZ=(%.2f,%.2f,%.2f) jerr=%.4f hand2cube=%.3f pad=(%.2f,%.2f) locked=%s" % (
                S["gn"], gripcmd, g["_grmin"], grasp[0], grasp[1], grasp[2], _je, _hc, cc[0], cc[1], S["glocked"]), flush=True)
        # Optional production guard.  The result remains explicitly labelled
        # as a hybrid recovery so it cannot be counted as a pure-policy pass.
        if (
            S["task"].get("auto_recovery", g.get("_GROOT_AUTO_RECOVERY", False))
            and not S["task"].get("capture_recovery")
            and not S["glocked"]
            and S["gn"] >= g.get("_GROOT_RECOVERY_AFTER", 700)
        ):
            _old = dict(S["task"])
            _dmin = g.get("_gdistmin", 999.0)
            _retry_count = int(_old.get("groot_retry_count", 0))
            if _retry_count < 2:
                S["task"]["groot_retry_count"] = _retry_count + 1
                S["task"]["groot_retrying_home"] = True
                g["_gretry_home_t"] = 0
                S["gbuf"] = None; S["gi"] = 0; S["ghold"] = 0
                print(
                    "GROOT_RETRY_HOME color=%s completed_attempt=%d dmin=%.3f"
                    % (col, _retry_count + 1, _dmin),
                    flush=True,
                )
                return
            print(
                "GROOT_AUTO_RECOVERY color=%s gn=%d grmin=%.3f dmin=%.3f retries=%d"
                % (col, S["gn"], g.get("_grmin", -1.0), _dmin, _retry_count),
                flush=True,
            )
            S["gbuf"] = None; S["gi"] = 0; S["ghold"] = 0
            start(
                {
                    "action": "move",
                    "color": col,
                    "endpoint": _old.get("endpoint", "franka_left"),
                    "groot_recovery": True,
                    "recovery_home_done": _dmin <= 0.18,
                }
            )
            return
        # DAgger-style recovery capture.  Capture either an early near miss or
        # a position-dependent failure that never got close by the deadline.
        if S["task"].get("capture_recovery") and not S["glocked"]:
            _rc = [
                (i, float(np.linalg.norm(grasp - np.array(wrp[i].get_world_pose()[0]))))
                for i in ACTIVE
                if POOL_COL[i] == col
            ]
            if _rc:
                _ri, _rd = min(_rc, key=lambda t: t[1])
                _trigger_distance = float(
                    S["task"].get("recovery_trigger_distance", 0.18)
                )
                _trigger_min_steps = int(
                    S["task"].get("recovery_trigger_min_steps", 200)
                )
                _trigger_requires_close = bool(
                    S["task"].get("recovery_trigger_requires_close", True)
                )
                _near_miss = (
                    _trigger_requires_close
                    and gripcmd < g.get("_PGFR_GRASP_TH", GRASP_TH)
                    and S["gn"] >= _trigger_min_steps
                    and 0.065 <= _rd <= 0.18
                )
                _policy_orbit = (
                    not _trigger_requires_close
                    and S["gn"] >= _trigger_min_steps
                    and 0.065 <= _rd <= _trigger_distance
                )
                _deadline = S["gn"] >= 1200
                if _near_miss or _policy_orbit or _deadline:
                    _old = dict(S["task"])
                    _cube_position = np.asarray(wrp[_ri].get_world_pose()[0], dtype=float)
                    if _near_miss:
                        _mode = "near_miss"
                    elif _policy_orbit:
                        _mode = "policy_orbit"
                    else:
                        _mode = "deadline"
                    _evt = {
                        "action": "recovery_ready",
                        "args": _old,
                        "success": False,
                        "verified": False,
                        "reason": "groot recovery_ready mode=%s color=%s gn=%d hand2cube=%.3f"
                        % (_mode, col, S["gn"], _rd),
                        "failure_state": {
                            "mode": _mode,
                            "gn": int(S["gn"]),
                            "hand2cube": float(_rd),
                            "min_hand2cube": float(g.get("_gdistmin", _rd)),
                            "gripper": float(gripcmd),
                            "min_gripper": float(g.get("_grmin", gripcmd)),
                            "cube_xyz": _cube_position.tolist(),
                            "grasp_xyz": grasp.tolist(),
                        },
                    }
                    RES.publish(String(data=json.dumps(_evt)))
                    print("GROOT_RECOVERY_HANDOFF %s" % _evt, flush=True)
                    S["gbuf"] = None; S["gi"] = 0; S["ghold"] = 0
                    start(
                        {
                            "action": "move",
                            "color": col,
                            "endpoint": _old.get("endpoint", "franka_left"),
                            "groot_recovery": True,
                            "recovery_home_done": _near_miss or _policy_orbit,
                        }
                    )
                    return
            elif S["gn"] >= 1200:
                finish(False, False, "groot recovery_no_state color=%s gn=%d" % (col, S["gn"]))
                return
        if not S["glocked"] and gripcmd < g.get("_PGFR_GRASP_TH", GRASP_TH):
            cs = [(i, float(np.linalg.norm(grasp - np.array(wrp[i].get_world_pose()[0])))) for i in ACTIVE]
            cs = [(i, d) for i, d in cs if d < g.get("_PGFR_LOCK_R", 0.06)]
            if cs:
                ci = min(cs, key=lambda t: t[1])[0]; cp, _ = wrp[ci].get_world_pose()
                S["gcube"] = wrp[ci]; S["gcube_index"] = ci
                S["goff"] = np.array(cp) - grasp; S["glocked"] = True
                S["greleased"] = False; S["greleased_index"] = None
                S["grelease_tick"] = None; S["gsettle"] = 0; S["gsettle_prev"] = None
                print("GROOT_GRASP cube=%d col=%s gn=%d grip=%.3f" % (ci, POOL_COL[ci], S["gn"], gripcmd), flush=True)
        if S["glocked"]:
            if gripcmd > g.get("_PGFR_REL_TH", REL_TH):
                S["greleased"] = True
                S["greleased_index"] = S.get("gcube_index")
                S["grelease_tick"] = S["gn"]
                S["gsettle"] = 0; S["gsettle_prev"] = None
                print(
                    "GROOT_RELEASE cube=%s col=%s gn=%d grip=%.3f"
                    % (S["greleased_index"], col, S["gn"], gripcmd),
                    flush=True,
                )
                S["glocked"] = False; S["gcube"] = None
            elif S["gcube"] is not None:
                S["gcube"].set_world_pose(grasp + S["goff"], hq); S["gcube"].set_linear_velocity(np.zeros(3)); S["gcube"].set_angular_velocity(np.zeros(3))
        _a = g.get("_SMOOTH_A", 0.4); _pv = g.get("_smooth")
        arm7s = arm7 if _pv is None else (_a * arm7 + (1.0 - _a) * _pv)   # EMA low-pass on arm joints -> smooth motion
        g["_smooth"] = arm7s
        fingers = GR_SNUG if S["glocked"] else gripcmd
        frL.apply_action(_groot_position_action(np.concatenate([arm7s, [fingers, fingers]])))
        S["ghold"] += 1
        if S["ghold"] >= g.get("_GHOLD", 5):
            if S["gn"] % 180 < g.get("_GHOLD", 5):   # settled residual: arm held arm7 the full ghold
                _se = float(np.max(np.abs(arm7 - np.asarray(frL.get_joint_positions()[:7], dtype=float))))
                print("SETTLED gn=%d jerr_settled=%.4f" % (S["gn"], _se), flush=True)
            S["gi"] += 1; S["ghold"] = 0
        S["gn"] += 1
        cc = comp_world(col)
        _released_index = S.get("greleased_index")
        if S.get("greleased") and _released_index in ACTIVE:
            p, _ = wrp[_released_index].get_world_pose(); p = np.asarray(p, dtype=float)
            _previous = S.get("gsettle_prev")
            _motion = float(np.linalg.norm(p - _previous)) if _previous is not None else float("inf")
            S["gsettle_prev"] = p.copy()
            _in_compartment = (
                abs(p[0] - cc[0]) < 0.08
                and abs(p[1] - cc[1]) < 0.08
                and 0.68 < p[2] < 0.715
            )
            if _in_compartment and _motion < 0.0005:
                S["gsettle"] += 1
            else:
                S["gsettle"] = 0
            if S["gsettle"] >= g["_GROOT_SETTLE_FRAMES"]:
                _off = ((p[0] - cc[0]) ** 2 + (p[1] - cc[1]) ** 2) ** 0.5
                _retries = int(S["task"].get("groot_retry_count", 0))
                _prefix = "groot retry%d" % _retries if _retries else "groot"
                finish(
                    True,
                    True,
                    "%s released+settled %s off=%.3f z=%.3f release_gn=%d gn=%d"
                    % (_prefix, col, _off, p[2], S["grelease_tick"], S["gn"]),
                )
                return
        if S["gn"] > g.get("_GN_LIMIT", 2800):
            finish(
                False,
                False,
                "groot timeout gn=%d grmin=%.3f locked=%s released=%s settle=%d"
                % (
                    S["gn"],
                    g.get("_grmin", -1),
                    S["glocked"],
                    S.get("greleased", False),
                    S.get("gsettle", 0),
                ),
            )
            return

    def start(cmd):
        S["task"]=cmd; S["t"]=0; S["locked"]=False; S["rel"]=False; S["off"]=None; S["hpmin"]=None; S["offc"]=None; S["release_wait"]=0; S["physical_grip_closed"]=False
        act=cmd.get("action")
        if act=="move":
            if cmd.get("backend")=="groot":
                # Production GR00T inference is deterministic by default.  A
                # command may explicitly pass inference_seed_base=None only
                # for an intentional unseeded diagnostic.
                g["_GROOT_INFERENCE_SEED_BASE"] = cmd.get("inference_seed_base", 4242)
                S["gbuf"]=None; S["gi"]=0; S["ghold"]=0; S["gexec"]=0; S["glocked"]=False; S["gcube"]=None; S["gcube_index"]=None; S["gn"]=0
                S["greleased"]=False; S["greleased_index"]=None; S["grelease_tick"]=None; S["gsettle"]=0; S["gsettle_prev"]=None
                S["gphysical_grasp_seen"]=False; S["gphysical_target_index"]=None
                S["gtracking_replans"]=0
                S["gpregrasp_alignment_active"]=False; S["gpregrasp_alignment_done"]=False
                S["gpregrasp_alignment_ticks"]=0; S["gpregrasp_alignment_settle"]=0
                S["gpregrasp_alignment_start_error"]=None
                S["gphysical_grasp_candidate_index"]=None; S["gphysical_grasp_candidate_cube"]=None
                S["gphysical_grasp_candidate_relative"]=None; S["gphysical_grasp_candidate_confirm_ticks"]=0
                S["gphysical_close_wait"]=False; S["gphysical_close_wait_ticks"]=0; S["gphysical_close_target"]=None
                S["gphysical_close_latched"]=False; S["gphysical_close_latch_ticks"]=0
                S["gphysical_close_last_action_key"]=None
                S["gphysical_release_zone_ticks"]=0
                S["gphysical_release_candidate_actions"]=0
                S["gphysical_release_candidate_key"]=None
                S["gphysical_release_last_suppressed_key"]=None
                S["gphysical_release_committed"]=False
                g["_grmin"]=1.0; g["_gdistmin"]=999.0; g["_smooth"]=None
                g["_GROOT_QUERY_INDEX"] = 0
                g["_gretry_home_t"] = 0
                g["_gretry_home_settle_t"] = 0
                ctrl.reset()
                print(
                    "GROOT_INFERENCE seed_base=%s schedule=base+query_index"
                    % g["_GROOT_INFERENCE_SEED_BASE"],
                    flush=True,
                )
                if cmd.get("physical_friction"):
                    print(
                        "GROOT_PHYSICAL_FRICTION_ENABLED no_attachment=true relay=%s:%d"
                        % (
                            g.get("_GROOT_RELAY_HOST", "127.0.0.1"),
                            int(g.get("_GROOT_RELAY_PORT", 5601)),
                        ),
                        flush=True,
                    )
                print("PGFR_START %s"%cmd, flush=True); return
            col=cmd.get("color"); dest=(cmd.get("destination") or "").replace("tote_","") or col
            ep=cmd.get("endpoint"); bp,_=(frR if ep=="franka_right" else frL).get_world_pose()
            ti=target_cube(col,float(bp[0])); S["cube"]=(wrp[ti] if ti is not None else None)
            if ti is not None:
                p,_=wrp[ti].get_world_pose(); S["pick"]=np.array([float(p[0]),float(p[1]),max(float(p[2]),0.72)])
                S["destcol"]=dest if dest in COMP_LOCAL else col
            _tpt=g.get("tp_r") if (ep=="franka_right" and g.get("tote_r") is not None) else None
            c=comp_world(S["destcol"], _tpt); S["place"]=np.array([c[0],c[1],PLACE_Z]); (ctrlR if ep=="franka_right" else ctrl).reset()
        elif act in ("pick_and_place","haul"):
            _obj=str(cmd.get("object_id") or "tote").lower()
            S["haul_tote"]="tote_r" if (_obj in ("tote_right","tote_r","bigtote_r","tote2") and g.get("tote_r") is not None) else "tote"
            S["dock"]=(DOCK_R if S["haul_tote"]=="tote_r" else DOCK).copy()
            S["shelf"]=(SHELF_TOTE_R if S["haul_tote"]=="tote_r" else SHELF_TOTE).copy()
            S["ph"]="reach"; S["yaw"]=YAW_DOCK; S["cbase"]=S["dock"].copy(); S["wp"]=0; S["wpt"]=0; S["toff"]=None; S["boffs"]=None
        print("PGFR_START %s"%cmd, flush=True)

    def run_move(dt):
        if S["task"].get("backend")=="groot": run_groot(dt); return
        ep=(S["task"].get("endpoint") or "franka_left")
        arm,c,hand=(frR,ctrlR,fhandR) if ep=="franka_right" else (frL,ctrl,fhand)
        if S["task"].get("groot_recovery") and not S["task"].get("recovery_home_done"):
            # A failed GR00T rollout can leave the arm in a poor initial pose
            # for PickPlaceController.  Interpolate home over three seconds so
            # the correction remains within the demonstration velocity limits.
            if "recovery_home_start" not in S["task"]:
                _current = np.asarray(arm.get_joint_positions(), dtype=float)
                S["task"]["recovery_home_start"] = _current[: len(FR_HOME)].tolist()
            _home_start = np.asarray(S["task"]["recovery_home_start"], dtype=float)
            _alpha = min(1.0, float(S["t"] + 1) / 180.0)
            _home_target = (1.0 - _alpha) * _home_start + _alpha * FR_HOME
            arm.apply_action(_groot_position_action(_home_target))
            S["t"] += 1
            if S["t"] >= 180:
                S["task"]["recovery_home_done"] = True
                S["t"] = 0
                c.reset()
                _jp = np.asarray(arm.get_joint_positions(), dtype=float)
                _jerr = float(np.max(np.abs(_jp[: len(FR_HOME)] - FR_HOME)))
                print("GROOT_RECOVERY_HOME_READY jerr=%.4f" % _jerr, flush=True)
            return
        cu=S.get("cube")
        if cu is None: finish(False,False,"no matching cube"); return
        jp=arm.get_joint_positions()
        phase=int(c.get_current_event())
        act=c.forward(picking_position=S["pick"], placing_position=S["place"], current_joint_positions=jp, end_effector_offset=np.array([0,0,0]))
        hp,hq=hand.get_world_pose(); hp=np.array(hp)
        grasp=hp+qrot(hq,np.array([0.0,0.0,GRASP_L]))
        if not S["locked"]:
            cp,_=cu.get_world_pose(); cp=np.array(cp)
            if float(((grasp[0]-cp[0])**2+(grasp[1]-cp[1])**2)**0.5)<0.07:
                if S["hpmin"] is None or hp[2]<=S["hpmin"]: S["hpmin"]=hp[2]; S["offc"]=cp-grasp
                elif hp[2]>S["hpmin"]+0.012:
                    if float(np.linalg.norm(S["offc"]))<0.045: S["off"]=S["offc"]; S["locked"]=True
                    else: S["hpmin"]=None; S["offc"]=None
        if jp is not None:
            arm.apply_action(act)
            finger_target=GR_GRIP if 3<=phase<7 else GR_OPEN
            _pgfr_apply_rmpflow_gripper(arm,finger_target)
            measured=_pgfr_rmpflow_gripper_positions(arm)
            if 3<=phase<7 and measured.size and float(np.max(measured))<=GR_SNUG+0.006:
                if not S.get("physical_grip_closed"):
                    print("PGFR_RMPFLOW_GRIP_CLOSED phase=%d fingers=%s"%(phase,[round(float(x),4) for x in measured]),flush=True)
                S["physical_grip_closed"]=True
            if phase>=7 and S.get("physical_grip_closed") and measured.size and float(np.min(measured))>=GR_OPEN-0.005:
                if not S.get("rel"):
                    print("PGFR_RMPFLOW_RELEASE_OPEN phase=%d fingers=%s"%(phase,[round(float(x),4) for x in measured]),flush=True)
                S["rel"]=True
        S["t"]+=1
        if c.is_done() or S["t"]>1700:
            fp,_=cu.get_world_pose(); cc=comp_world(S["destcol"]); off=float(((fp[0]-cc[0])**2+(fp[1]-cc[1])**2)**0.5); ok=off<0.08
            _recovery_retry = int(S["task"].get("recovery_retry_count", 0))
            if S["task"].get("groot_recovery") and not ok and _recovery_retry < 1:
                print(
                    "GROOT_DETERMINISTIC_RETRY color=%s prior_off=%.3f"
                    % (S["task"].get("color"), off),
                    flush=True,
                )
                start(
                    {
                        "action": "move",
                        "color": S["task"].get("color"),
                        "endpoint": S["task"].get("endpoint", "franka_left"),
                        "groot_recovery": True,
                        "recovery_retry_count": _recovery_retry + 1,
                    }
                )
                return
            reason = ("in tote_%s off=%.3f"%(S["destcol"],off)) if ok else ("missed off=%.3f"%off)
            if S["task"].get("groot_recovery"):
                _retry_label = " retry%d" % _recovery_retry if _recovery_retry else ""
                reason = "groot auto-recovery%s: %s" % (_retry_label, reason)
            finish(ok, ok, reason)

    g["_grquery"]=_grquery; g["run_groot"]=run_groot; g["start"]=start; g["run_move"]=run_move
    print("GROOT_FOLLOW_PATCHED grasp_th=%.3f gn_limit=%d gexec=%d recovery_handoff=enabled" % (GRASP_TH, g["_GN_LIMIT"], g["_GEXEC"]), flush=True)
except Exception:
    print("GROOT_PATCH_ERR:\n"+traceback.format_exc(), flush=True)

globals()["_PGFR_GROOT_EXECUTION_REVISION"] = "home_convergence_v36_direct"
print(
    "GROOT_HOME_CONVERGENCE_V36_READY "
    "home_min_ticks=120 home_tolerance_rad=0.030 home_settle_ticks=12 "
    "home_timeout_ticks=600 canonical_joint_limits=unchanged "
    "raw_requery_margin_max=0.040 raw_requery_limit_max=6",
    flush=True,
)
