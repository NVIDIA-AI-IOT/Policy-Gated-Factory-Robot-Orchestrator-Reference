# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Reset the Policy-Gated Factory Robot Orchestrator Reference two-arm scene and restore the GR00T runtime.

The public GR00T profile uses layout 3, seed 31302, the direct V36 executor,
the shared Order744-cont24 deployment, and mixed-color independent-B=1
concurrency.  Every reset rebuilds and validates that runtime before admission.
"""

import json
import os
import traceback


try:
    import numpy as np

    g = globals()
    _full_scene_ready_before_reset = bool(
        g.get("_IC_FULL_SCENE_READY", False)
    )
    g["_IC_FULL_SCENE_READY"] = False
    g["_IC_RESET_SCENE_READY"] = False
    g["_IC_LAST_RESET_PROFILE"] = None
    g["_IC_LAST_RESET_SCENE"] = None

    _task_object = S.get("task") if g.get("S") is not None else None
    _task = _task_object or {}
    if _task and _task.get("action") != "reset_scene":
        raise RuntimeError("refusing: cell task active — stop/finish the mission first")
    _live_reset = bool(_task and _task.get("action") == "reset_scene")
    _state_identity = id(S)

    _contract = dict(g.get("_IC_SCENE_RESET_CONTRACT") or {})
    _bootstrap_request = dict(g.get("_IC_RESET_SCENE_REQUEST") or {})
    if _bootstrap_request:
        _request = dict(_contract)
        _request.update(_bootstrap_request)
    elif _live_reset:
        if not _contract:
            raise RuntimeError(
                "live reset requires the cached startup scene contract"
            )
        _request = dict(_contract)
        for _key in (
            "scene_profile",
            "arm",
            "color",
            "layout",
            "layout_left",
            "layout_right",
            "seed",
            "shared_color_canary",
            "canary_arm",
        ):
            if _key in _task:
                _request[_key] = _task[_key]
        # ``endpoint`` is transport routing metadata.  A hardened operator
        # reset may explicitly request ``arm=both`` while sending through one
        # existing endpoint, so the explicit scene selector must win.
        if "endpoint" in _task and "arm" not in _task:
            _request["arm"] = _task["endpoint"]
        if "target_color" in _task:
            _request["color"] = _task["target_color"]
        if "n" in _task:
            _request["seed"] = _task["n"]
    else:
        _request = {"scene_profile": "ic_two_arm"}

    _profile = str(_request.get("scene_profile", "ic_two_arm")).strip().lower()
    if _profile not in ("ic_two_arm", "groot_three_object"):
        raise RuntimeError(
            "scene_profile must be ic_two_arm or groot_three_object"
        )
    _camera_profile = str(
        _contract.get(
            "camera_profile",
            os.environ.get("IC_CAMERA_PROFILE", ""),
        )
    ).strip().lower()

    # Remove passive capture wrappers before replacing the follower functions.
    # The modern sync adapter and the older expert-action adapter are mutually
    # exclusive, but clean both defensively so reset is repeatable.
    _sync_original = g.pop("_IC_SYNC_ORIGINAL_RUN_MOVE", None)
    if _sync_original is not None:
        g["run_move"] = _sync_original
    _sync_publisher = g.pop("_IC_SYNC_SAMPLE_PUBLISHER", None)
    if _sync_publisher is not None:
        try:
            node.destroy_publisher(_sync_publisher)
        except Exception:
            pass
    for _key in (
        "_IC_SYNC_ACTION_TARGET",
        "_IC_SYNC_SEQUENCE",
        "_IC_SYNC_CAPTURE_READY",
    ):
        g.pop(_key, None)

    _legacy_original = g.pop("_IC_EXPERT_ACTION_ORIGINAL_RUN_MOVE", None)
    if _legacy_original is not None:
        g["run_move"] = _legacy_original
    _legacy_publisher = g.pop("_IC_EXPERT_ACTION_PUB", None)
    if _legacy_publisher is not None:
        try:
            node.destroy_publisher(_legacy_publisher)
        except Exception:
            pass
    for _key in (
        "_IC_EXPERT_ACTION_LAST",
        "_IC_EXPERT_ACTION_TARGET",
        "_IC_EXPERT_ACTION_SIGNATURES",
        "_IC_EXPERT_ACTION_RUN_CALLS",
        "_IC_EXPERT_ACTION_APPLY_CALLS",
    ):
        g.pop(_key, None)

    # Tear down a possibly interrupted physical-friction audit completely.
    # Merely dropping its subscription leaves finish() wrapped and can leave
    # set_world_pose/velocity methods monkeypatched on the active rigid handle.
    _old_a1_sub = g.get("_IC_SHAPE_A1_SUB")
    if _old_a1_sub is not None:
        try:
            _old_a1_sub.unsubscribe()
        except Exception:
            pass
    _a1_state = g.get("_IC_SHAPE_A1") or {}
    _a1_target = _a1_state.get("target")
    _a1_methods = _a1_state.get("original_methods")
    if _a1_target is not None and _a1_methods is not None:
        _a1_target.set_world_pose = _a1_methods["set_world_pose"]
        _a1_target.set_linear_velocity = _a1_methods["set_linear_velocity"]
        _a1_target.set_angular_velocity = _a1_methods[
            "set_angular_velocity"
        ]
    _base_finish = g.get("_IC_BASE_FINISH")
    _a1_original_finish = g.get("_IC_SHAPE_A1_ORIGINAL_FINISH")
    if _base_finish is not None:
        g["finish"] = _base_finish
    elif _a1_original_finish is not None:
        g["finish"] = _a1_original_finish
    g["_IC_SHAPE_A1_SUB"] = None
    g["_IC_SHAPE_A1_ORIGINAL_FINISH"] = None
    for _key in (
        "_IC_SHAPE_A1",
        "_IC_SHAPE_A1_TRIALS_OVERRIDE",
        "_IC_SHAPE_FRICTION_TIER",
        "_IC_SHAPE_PHASE_TELEMETRY",
    ):
        g.pop(_key, None)

    # Shape mode aliases wr/wrp and wraps start().  Restore its exact snapshot
    # before the baseline reset; otherwise the blue cylinder can be mistaken
    # for the original blue cube and follower reloads leave a stale wrapper.
    _shape_original = g.get("_IC_SHAPE_ORIG")
    if _shape_original:
        wr.clear()
        wr.update(_shape_original["wr"])
        wrp[:] = list(_shape_original["wrp"])
        g["GR_SNUG"] = _shape_original["GR_SNUG"]
        g["spawn_scene"] = _shape_original["spawn_scene"]
        g["start"] = _shape_original["start"]
    for _key in (
        "_IC_GROOT_DEPLOYMENT_ORIGINAL_START",
        "_IC_GROOT_DEPLOYMENT_READY",
        "_IC_GROOT_CERTIFIED_CASES",
        "_ic_groot_certified_start",
    ):
        g.pop(_key, None)

    import omni.usd
    from pxr import Gf, UsdGeom
    from isaacsim.core.prims import SingleRigidPrim as _ResetRigidPrim

    stage = omni.usd.get_context().get_stage()

    def _quaternion_matches(_actual, _expected, _tolerance=0.01):
        _actual = np.asarray(_actual, dtype=float).reshape(4)
        _expected = np.asarray(_expected, dtype=float).reshape(4)
        if not np.isfinite(_actual).all() or not np.isfinite(_expected).all():
            return False
        _actual_norm = float(np.linalg.norm(_actual))
        _expected_norm = float(np.linalg.norm(_expected))
        if _actual_norm <= 1e-9 or _expected_norm <= 1e-9:
            return False
        _alignment = abs(
            float(
                np.dot(
                    _actual / _actual_norm,
                    _expected / _expected_norm,
                )
            )
        )
        return 1.0 - _alignment <= _tolerance

    # Park all canonical non-cube assets even when the requested profile is the
    # two-cube fallback. They may still be on the table from a previous
    # single- or dual-arm scene, and restoring wr/wrp aliases does not move the
    # underlying rigid bodies.
    _reset_shape_handles = {}
    for (
        _shape_record_key,
        _shape_global_key,
        _shape_path,
        _shape_park,
    ) in (
        (
            "blue_left",
            "_shape_rp_blue",
            "/World/ShapeCyl_blue",
            np.array([6.6, -6.3, 0.03]),
        ),
        (
            "green_left",
            "_shape_rp_green",
            "/World/ShapeBrick_green",
            np.array([6.6, -6.5, 0.03]),
        ),
        (
            "blue_right",
            "_shape_rp_blue_right",
            "/World/ShapeCyl_blue_R",
            np.array([6.8, -6.3, 0.03]),
        ),
        (
            "green_right",
            "_shape_rp_green_right",
            "/World/ShapeBrick_green_R",
            np.array([6.8, -6.5, 0.03]),
        ),
    ):
        _shape_handle = g.get(_shape_global_key)
        if (
            _shape_handle is None
            or str(getattr(_shape_handle, "prim_path", "")) != _shape_path
        ):
            _shape_handle = _ResetRigidPrim(
                _shape_path,
                name="reset_shape_" + _shape_record_key,
            )
        _shape_handle.set_world_pose(_shape_park, IDENT)
        _shape_handle.set_linear_velocity(np.zeros(3))
        _shape_handle.set_angular_velocity(np.zeros(3))
        _reset_shape_handles[_shape_record_key] = (
            _shape_handle,
            _shape_park,
        )

    for _key in (
        "_IC_SHAPE_ORIG",
        "_IC_SHAPE_ACTIVE",
        "_IC_SHAPE_LAST_SCENE",
        "_IC_SHAPE_ASSET_AUDIT",
        "_IC_SHAPE_DUAL_ASSET_AUDIT",
        "_IC_SHAPE_MODE_READY",
        "_shape_rp_red",
        "_shape_rp_blue",
        "_shape_rp_green",
        "_shape_rp_red_right",
        "_shape_rp_blue_right",
        "_shape_rp_green_right",
        "_shape_prims",
        "_shape_dual_prims",
        "_shape_spawn_scene",
        "_shape_start",
        "_IC_SHAPE_SPAWN_BAND",
        "_IC_SHAPE_SPAWN_XY",
        "_IC_SHAPE_DISTRACTORS",
        "_IC_SHAPE_SEED",
        "SHAPE_BANDS",
        "SHAPE_TRIPLE_SLOTS",
        "SHAPE_TRIPLE_LAYOUTS",
        "SHAPE_ARM_X_OFFSET",
        "SHAPE_DEFS",
        "SHAPE_DUAL_DEFS",
        "SHAPE_TASK_NOUN",
    ):
        g.pop(_key, None)

    # A failed/interrupted tote haul can leave both a live FixedJoint and a
    # deferred joint callback behind.  Detach before writing either tote pose,
    # then reload exactly one callback with the canonical haul implementation.
    _old_joint_sub = g.pop("_IC_JOINTOP_SUB", None)
    if _old_joint_sub is not None:
        try:
            _old_joint_sub.unsubscribe()
        except Exception:
            pass
    g["_IC_JOINT_REQ"] = None
    g["_IC_JOINT_ACK"] = None
    if stage.GetPrimAtPath("/World/HaulJoint").IsValid():
        stage.RemovePrim("/World/HaulJoint")

    # Baseline physical reset on original handles.
    _red_index = [i for i, c in enumerate(POOL_COL) if c == "red"][0]
    _blue_index = [i for i, c in enumerate(POOL_COL) if c == "blue"][0]
    ACTIVE.clear()
    ACTIVE.update((_red_index, _blue_index))
    for _index in range(len(wrp)):
        if _index not in (_red_index, _blue_index):
            wrp[_index].set_world_pose(
                np.array([8.5 + 0.13 * _index, -9.8, 0.05]),
                IDENT,
            )
            wrp[_index].set_linear_velocity(np.zeros(3))
            wrp[_index].set_angular_velocity(np.zeros(3))

    _red_position = np.array([3.50, -6.95, 0.728])
    _blue_position = np.array([5.045, -6.95, 0.728])
    wrp[_red_index].set_world_pose(_red_position, IDENT)
    wrp[_red_index].set_linear_velocity(np.zeros(3))
    wrp[_red_index].set_angular_velocity(np.zeros(3))
    wrp[_blue_index].set_world_pose(_blue_position, IDENT)
    wrp[_blue_index].set_linear_velocity(np.zeros(3))
    wrp[_blue_index].set_angular_velocity(np.zeros(3))

    _left_tote_position = np.array([4.126, -7.701, 0.665])
    _right_tote_position = np.array([5.451, -7.701, 0.665])
    tote.set_world_pose(_left_tote_position, IDENT)
    tote.set_linear_velocity(np.zeros(3))
    tote.set_angular_velocity(np.zeros(3))
    if g.get("tote_r") is not None:
        tote_r.set_world_pose(
            _right_tote_position,
            np.array([1.0, 0.0, 0.0, 0.0]),
        )
        tote_r.set_linear_velocity(np.zeros(3))
        tote_r.set_angular_velocity(np.zeros(3))

    # A reset is a state operation, not a trajectory.  Write the home state
    # immediately from the deferred update tick and clear stale velocity
    # targets, then reset both RMPflow state machines.
    for _arm, _controller in ((frL, ctrl), (frR, ctrlR)):
        _arm.set_joint_positions(FR_HOME)
        try:
            _arm.set_joint_velocities(np.zeros(len(FR_HOME)))
        except Exception:
            pass
        _arm.apply_action(
            ArticulationAction(
                joint_positions=FR_HOME,
                joint_velocities=np.zeros(len(FR_HOME)),
            )
        )
        _controller.reset()

    # Park the AMR by the rack, outside the GR00T camera domain.
    _park = (1.74, -8.667)
    _amr_joints = np.array(amr.get_joint_positions(), float)
    _amr_joints[0] = _park[0] - 4.54
    _amr_joints[1] = _park[1] + 4.8
    _amr_joints[2] = YAW_DOCK
    _amr_joints[3:10] = HOME
    _amr_joints[10:12] = [GR_OPEN, GR_OPEN]
    amr.set_joint_positions(_amr_joints)
    try:
        amr.set_joint_velocities(np.zeros(len(_amr_joints)))
    except Exception:
        pass
    amr.apply_action(
        ArticulationAction(
            joint_positions=_amr_joints,
            joint_velocities=np.zeros(len(_amr_joints)),
        )
    )
    g["AMR_PARK"] = _park

    # Close every cached relay socket before restoring the direct
    # dual-arm executor.  The relays accept one persistent client each, so a
    # stale arm context must never survive a scene/task boundary.
    for _socket_key in ("_GRSOCK", "_GRSOCK_R"):
        _old_socket = g.get(_socket_key)
        if _old_socket is not None:
            try:
                _old_socket.close()
            except Exception:
                pass
        g[_socket_key] = None
    for _old_contexts in (
        g.get("_IC_DUAL_GROOT_V25_CONTEXTS") or {},
        g.get("_IC_DUAL_GROOT_V26_CONTEXTS") or {},
        g.get("_IC_DUAL_GROOT_V27_CONTEXTS") or {},
        g.get("_IC_DUAL_GROOT_V28_CONTEXTS") or {},
        g.get("_IC_DUAL_GROOT_V29_CONTEXTS") or {},
        g.get("_IC_DUAL_GROOT_V30_CONTEXTS") or {},
        g.get("_IC_GROOT_CONCURRENT_CONTEXTS") or {},
    ):
        for _old_context in _old_contexts.values():
            _old_socket = _old_context.get("_GRSOCK")
            if _old_socket is not None:
                try:
                    _old_socket.close()
                except Exception:
                    pass
            _old_context["_GRSOCK"] = None
            if g.get("_IC_BASE_FINISH") is not None:
                _old_context["finish"] = g["_IC_BASE_FINISH"]
    _old_concurrent_group = g.get("_IC_GROOT_CONCURRENT_GROUP") or {}
    _old_pair_socket = _old_concurrent_group.get("pair_socket")
    if _old_pair_socket is not None:
        try:
            _old_pair_socket.close()
        except Exception:
            pass
        _old_concurrent_group["pair_socket"] = None
    _old_query_pool = g.pop("_IC_GROOT_QUERY_POOL", None)
    if _old_query_pool is not None:
        _old_query_pool.shutdown(wait=True, cancel_futures=False)
    for _concurrent_key in (
        "_IC_GROOT_CONCURRENT_CONTEXTS",
        "_IC_GROOT_CONCURRENT_GROUP",
        "_IC_GROOT_SERIAL_START",
        "_IC_GROOT_SERIAL_RUN_MOVE",
        "_IC_GROOT_CONCURRENT_READY",
        "_IC_GROOT_CONCURRENT_MIXED_READY",
        "_IC_GROOT_CONCURRENT_MIXED_REVISION",
        "_concurrent_start",
        "_concurrent_run_move",
    ):
        g.pop(_concurrent_key, None)
    g["_GEXEC_OVERRIDE"] = 15
    g["_GROOT_AUTO_RECOVERY"] = False
    _shared_executor_requested = True
    if (
        g.get("_IC_GROOT_POLICY_ROUTE") != "shared"
        or not isinstance(g.get("_IC_GROOT_SHARED_POLICY_CONTRACT"), dict)
    ):
        raise RuntimeError(
            "the public GR00T reset requires the shared policy route and contract"
        )
    _executor_revision = "v36h"
    _executor_runtime_revision = "home_convergence_v36_direct"
    _executor_loader_path = (
        "/scripts/native_droid_work/follow_groot_dual_physical_v36.py"
    )
    _executor_context_key = "_IC_DUAL_GROOT_V36H_CONTEXTS"

    # The live Isaac globals dictionary is the left executor namespace.  Clear
    # both derivative caches so every reset rebuilds exactly the selected,
    # validated executor instead of taking an older reuse path.
    for _executor_cache_key in (
        "_IC_DUAL_GROOT_V27_CONTEXTS",
        "_IC_DUAL_GROOT_V27_STARTS",
        "_IC_DUAL_GROOT_V27_RUNS",
        "_IC_DUAL_GROOT_V29_CONTEXTS",
        "_IC_DUAL_GROOT_V29_STARTS",
        "_IC_DUAL_GROOT_V29_RUNS",
        "_IC_DUAL_GROOT_V30_CONTEXTS",
        "_IC_DUAL_GROOT_V30_STARTS",
        "_IC_DUAL_GROOT_V30_RUNS",
        "_IC_DUAL_GROOT_V31_CONTEXTS",
        "_IC_DUAL_GROOT_V31_STARTS",
        "_IC_DUAL_GROOT_V31_RUNS",
        "_IC_DUAL_GROOT_V32_CONTEXTS",
        "_IC_DUAL_GROOT_V32_STARTS",
        "_IC_DUAL_GROOT_V32_RUNS",
        "_IC_DUAL_GROOT_V36H_CONTEXTS",
        "_IC_DUAL_GROOT_V36H_STARTS",
        "_IC_DUAL_GROOT_V36H_RUNS",
    ):
        g.pop(_executor_cache_key, None)

    with open(_executor_loader_path, encoding="utf-8") as _executor_loader_stream:
        _executor_loader_source = _executor_loader_stream.read()
    compile(_executor_loader_source, _executor_loader_path, "exec")
    exec(
        compile(_executor_loader_source, _executor_loader_path, "exec"),
        g,
    )
    for _path in (
        "/scripts/fix_amr_haul_joint.py",
        "/scripts/ic_serving_health.py",
    ):
        with open(_path, encoding="utf-8") as _handle:
            exec(compile(_handle.read(), _path, "exec"), g)

    def _source_path(_callable):
        return str(getattr(getattr(_callable, "__code__", None), "co_filename", ""))

    _executor_contexts = g.get(_executor_context_key) or {}
    if set(_executor_contexts) != {"franka_left", "franka_right"}:
        raise RuntimeError(
            "%s dual-arm GR00T contexts were not restored"
            % _executor_revision
        )
    for _context_arm, _context in _executor_contexts.items():
        if (
            _context.get("_IC_GROOT_EXECUTION_REVISION")
            != _executor_runtime_revision
        ):
            raise RuntimeError(
                "%s executor identity mismatch in %s"
                % (_executor_revision, _context_arm)
            )
    if (
        g.get("start") is not g.get("_dual_start")
        or g.get("run_move") is not g.get("_dual_run_move")
    ):
        raise RuntimeError(
            "%s dual-arm GR00T router was not restored"
            % _executor_revision
        )
    if (
        _source_path(g.get("_IC_BASE_FINISH")) != "/scripts/ic_node_v2.py"
        or g.get("finish") is not g.get("_IC_BASE_FINISH")
    ):
        raise RuntimeError("canonical result finalizer was not restored")

    if _profile == "groot_three_object":
        _arm = str(_request.get("arm", "franka_right")).strip().lower()
        _color = str(_request.get("color", "red")).strip().lower()
        _layout = int(_request.get("layout", 1))
        _layout_left = int(_request.get("layout_left", _layout))
        _layout_right = int(_request.get("layout_right", _layout))
        _default_seed = {
            "franka_left": 30100,
            "franka_right": 40100,
            "both": 31302,
        }.get(_arm, 31302)
        _seed = int(_request.get("seed", _default_seed))
        _shared_color_canary = bool(
            _request.get("shared_color_canary", False)
        )
        _canary_arm = str(
            _request.get("canary_arm", "franka_left")
        ).strip().lower()
        if _arm not in ("franka_left", "franka_right", "both"):
            raise RuntimeError("three-object reset arm is invalid: %s" % _arm)
        if _color not in ("red", "blue", "green"):
            raise RuntimeError(
                "three-object reset color is invalid: %s" % _color
            )
        for _layout_name, _layout_value in (
            ("layout", _layout),
            ("layout_left", _layout_left),
            ("layout_right", _layout_right),
        ):
            if not 0 <= _layout_value <= 5:
                raise RuntimeError(
                    "three-object reset %s must be 0 through 5"
                    % _layout_name
                )

        # The normal shared route remains pinned to layout 3.  This explicit
        # operator-only reset record admits exactly one no-alignment action on
        # a declared permuted layout, allowing color selection to be measured
        # without a target-aware pre-grasp pose confounding the result.
        g.pop("_IC_GROOT_SHARED_COLOR_CANARY", None)
        if _shared_color_canary:
            if not _shared_executor_requested:
                raise RuntimeError(
                    "shared color canary requires the pinned shared policy route"
                )
            if _arm != "both" or _layout_left != _layout_right:
                raise RuntimeError(
                    "shared color canary requires both arms on one common layout"
                )
            if _layout_left == 3:
                raise RuntimeError(
                    "shared color canary requires a non-training layout"
                )
            if _seed != 31302:
                raise RuntimeError(
                    "shared color canary requires pinned seed 31302"
                )
            if _canary_arm not in ("franka_left", "franka_right"):
                raise RuntimeError(
                    "shared color canary arm must be franka_left or franka_right"
                )
            g["_IC_GROOT_SHARED_COLOR_CANARY"] = {
                "schema_version": 1,
                "mode": "color-slot-canary-v1",
                "layout": _layout_left,
                "seed": _seed,
                "arm": _canary_arm,
                "color": _color,
                "used": False,
            }

        with open("/scripts/ic_shape_mode.py", encoding="utf-8") as _handle:
            exec(compile(_handle.read(), "/scripts/ic_shape_mode.py", "exec"), g)
        if not g.get("_IC_SHAPE_MODE_READY", False):
            raise RuntimeError("shape mode returned without its ready marker")
        if _arm == "both":
            spawn_scene(
                n=_seed,
                zone="shape6:%s:%d:%d"
                % (_color, _layout_left, _layout_right),
            )
            _expected_active = set(range(6))
            _expected_scene_layout = _layout_left
            _expected_layouts = {
                "franka_left": _layout_left,
                "franka_right": _layout_right,
            }
        else:
            spawn_scene(
                n=_seed,
                zone="shape3:%s:%d:%s" % (_color, _layout, _arm),
            )
            _expected_active = {0, 2, 4}
            _expected_scene_layout = _layout
            _expected_layouts = None
        _scene = dict(g.get("_IC_SHAPE_LAST_SCENE") or {})
        _protocol = dict(_scene.get("capture_protocol") or {})
        if (
            _scene.get("target") != _color
            or _scene.get("layout") != _expected_scene_layout
            or _scene.get("seed") != _seed
            or _protocol.get("arm") != _arm
            or (
                _expected_layouts is not None
                and dict(_scene.get("layouts") or {}) != _expected_layouts
            )
            or set(ACTIVE) != _expected_active
        ):
            raise RuntimeError(
                "three-object reset contract mismatch: %s active=%s"
                % (_scene, sorted(ACTIVE))
            )
        if float(_scene.get("minimum_separation_m", 0.0)) < 0.13:
            raise RuntimeError(
                "three-object reset separation is below 0.13 m: %s" % _scene
            )
        if set(g.get("_IC_SHAPE_ASSET_AUDIT") or {}) != {"blue", "green"}:
            raise RuntimeError(
                "three-object reset lacks the shape A0 audit: %s"
                % g.get("_IC_SHAPE_ASSET_AUDIT")
            )
        if (
            _arm == "both"
            and set(g.get("_IC_SHAPE_DUAL_ASSET_AUDIT") or {})
            != {"blue", "green"}
        ):
            raise RuntimeError(
                "dual-arm reset lacks duplicate shape audit: %s"
                % g.get("_IC_SHAPE_DUAL_ASSET_AUDIT")
            )
        if _arm == "both":
            _expected_paths = {
                0: "/World/SortCube_R",
                1: "/World/SortCube_R2",
                2: "/World/ShapeCyl_blue",
                3: "/World/ShapeCyl_blue_R",
                4: "/World/ShapeBrick_green",
                5: "/World/ShapeBrick_green_R",
            }
        else:
            _expected_paths = {
                0: "/World/SortCube_R",
                2: "/World/ShapeCyl_blue",
                4: "/World/ShapeBrick_green",
            }
        for _index, _expected_path in _expected_paths.items():
            if str(getattr(wrp[_index], "prim_path", "")) != _expected_path:
                raise RuntimeError(
                    "shape alias %d is %s, expected %s"
                    % (
                        _index,
                        getattr(wrp[_index], "prim_path", None),
                        _expected_path,
                    )
                )
        if _arm == "both":
            _pose_records = [
                (
                    _scene_arm,
                    _scene_color,
                    SHAPE_DUAL_DEFS[_scene_arm][_scene_color][1],
                    _expected_xyz,
                )
                for _scene_arm, _arm_positions in _scene[
                    "positions_xyz"
                ].items()
                for _scene_color, _expected_xyz in _arm_positions.items()
            ]
        else:
            _pose_records = [
                (
                    _arm,
                    _scene_color,
                    SHAPE_DEFS[_scene_color][1],
                    _expected_xyz,
                )
                for _scene_color, _expected_xyz in _scene[
                    "positions_xyz"
                ].items()
            ]
        for (
            _scene_arm,
            _scene_color,
            _index,
            _expected_xyz,
        ) in _pose_records:
            _actual_xyz, _actual_quaternion = wrp[_index].get_world_pose()
            _actual_xyz = np.asarray(_actual_xyz, dtype=float)
            if (
                not np.isfinite(_actual_xyz).all()
                or float(
                    np.linalg.norm(
                        _actual_xyz
                        - np.asarray(_expected_xyz, dtype=float)
                    )
                )
                > 0.02
                or not _quaternion_matches(_actual_quaternion, IDENT)
            ):
                raise RuntimeError(
                    "shape pose mismatch arm=%s color=%s actual=%s quaternion=%s "
                    "expected=%s"
                    % (
                        _scene_arm,
                        _scene_color,
                        _actual_xyz.tolist(),
                        np.asarray(_actual_quaternion, dtype=float).tolist(),
                        _expected_xyz,
                    )
                )
        if g.get("start") is not g.get("_shape_start"):
            raise RuntimeError("shape-aware start wrapper was not installed")
        if g.get("spawn_scene") is not g.get("_shape_spawn_scene"):
            raise RuntimeError("shape-aware spawn wrapper was not installed")
        _saved_start = (g.get("_IC_SHAPE_ORIG") or {}).get("start")
        if _saved_start is not g.get("_dual_start"):
            raise RuntimeError(
                "shape mode saved a stale follower start function"
            )
        _deployment_path = (
            "/scripts/native_droid_work/ic_groot_certified_deployment_v36.py"
        )
        with open(_deployment_path, encoding="utf-8") as _deployment_stream:
            _deployment_source = _deployment_stream.read()
        compile(_deployment_source, _deployment_path, "exec")
        exec(
            compile(_deployment_source, _deployment_path, "exec"),
            g,
        )
        if (
            not g.get("_IC_GROOT_DEPLOYMENT_READY", False)
            or g.get("start") is not g.get("_ic_groot_certified_start")
            or g.get("_IC_GROOT_DEPLOYMENT_ORIGINAL_START")
            is not g.get("_shape_start")
            or len(g.get("_IC_GROOT_CERTIFIED_CASES") or {}) != 18
        ):
            raise RuntimeError(
                "certified GR00T deployment adapter was not restored"
            )
        _concurrent_path = (
            "/scripts/native_droid_work/ic_groot_dual_concurrent_mixed.py"
        )
        with open(_concurrent_path, encoding="utf-8") as _concurrent_stream:
            _concurrent_source = _concurrent_stream.read()
        compile(_concurrent_source, _concurrent_path, "exec")
        exec(
            compile(_concurrent_source, _concurrent_path, "exec"),
            g,
        )
        if (
            not g.get("_IC_GROOT_CONCURRENT_READY", False)
            or not g.get("_IC_GROOT_CONCURRENT_MIXED_READY", False)
            or g.get("_IC_GROOT_CONCURRENT_MIXED_REVISION")
            != "per_arm_seed_v1"
            or g.get("start") is not g.get("_concurrent_start")
            or g.get("run_move") is not g.get("_concurrent_run_move")
            or set(g.get("_IC_GROOT_CONCURRENT_CONTEXTS") or {})
            != {"franka_left", "franka_right"}
        ):
            raise RuntimeError(
                "concurrent GR00T adapter was not restored"
            )
        _scene_record = _scene
    else:
        if g.get("_IC_SHAPE_ORIG") is not None:
            raise RuntimeError("ic_two_arm fallback retained shape aliases")
        if set(ACTIVE) != {_red_index, _blue_index}:
            raise RuntimeError(
                "ic_two_arm active set is wrong: %s" % sorted(ACTIVE)
            )
        _expected_paths = {
            _red_index: "/World/SortCube_R",
            _blue_index: "/World/SortCube_B",
        }
        for _index, _expected_path in _expected_paths.items():
            if str(getattr(wrp[_index], "prim_path", "")) != _expected_path:
                raise RuntimeError(
                    "baseline alias %d is %s, expected %s"
                    % (
                        _index,
                        getattr(wrp[_index], "prim_path", None),
                        _expected_path,
                    )
                )
        for _index, _expected_xyz in (
            (_red_index, _red_position),
            (_blue_index, _blue_position),
        ):
            _actual_xyz, _actual_quaternion = wrp[_index].get_world_pose()
            _actual_xyz = np.asarray(_actual_xyz, dtype=float)
            if (
                not np.isfinite(_actual_xyz).all()
                or float(np.linalg.norm(_actual_xyz - _expected_xyz)) > 0.02
                or not _quaternion_matches(_actual_quaternion, IDENT)
            ):
                raise RuntimeError(
                    "baseline object pose mismatch index=%d actual=%s "
                    "quaternion=%s expected=%s"
                    % (
                        _index,
                        _actual_xyz.tolist(),
                        np.asarray(_actual_quaternion, dtype=float).tolist(),
                        _expected_xyz.tolist(),
                    )
                )
        for _shape_color, (
            _shape_handle,
            _shape_park,
        ) in _reset_shape_handles.items():
            _actual_xyz, _actual_quaternion = _shape_handle.get_world_pose()
            _actual_xyz = np.asarray(_actual_xyz, dtype=float)
            if (
                not np.isfinite(_actual_xyz).all()
                or float(np.linalg.norm(_actual_xyz - _shape_park)) > 0.02
                or not _quaternion_matches(_actual_quaternion, IDENT)
            ):
                raise RuntimeError(
                    "fallback retained visible %s shape: actual=%s "
                    "quaternion=%s expected=%s"
                    % (
                        _shape_color,
                        _actual_xyz.tolist(),
                        np.asarray(
                            _actual_quaternion,
                            dtype=float,
                        ).tolist(),
                        _shape_park.tolist(),
                    )
                )
        _scene_record = {
            "profile": "ic_two_arm",
            "active": sorted(ACTIVE),
            "red_xyz": _red_position.tolist(),
            "blue_xyz": _blue_position.tolist(),
        }

    # Follower reload replaces run_move.  Restore the passive observer only
    # after follower + optional shape wrappers are final.
    if _camera_profile == "capture":
        with open(
            "/scripts/native_droid_work/ic_sync_capture_cell.py",
            encoding="utf-8",
        ) as _handle:
            exec(
                compile(
                    _handle.read(),
                    "/scripts/native_droid_work/ic_sync_capture_cell.py",
                    "exec",
                ),
                g,
            )
        if (
            not g.get("_IC_SYNC_CAPTURE_READY", False)
            or g.get("_IC_SYNC_ORIGINAL_RUN_MOVE") is None
        ):
            raise RuntimeError("capture telemetry was not restored")
    elif g.get("_IC_SYNC_ORIGINAL_RUN_MOVE") is not None:
        raise RuntimeError("production reset unexpectedly retained capture telemetry")

    # Validate the physical reset markers after every profile.
    for _name, _handle, _expected_xyz in (
        ("left_tote", tote, _left_tote_position),
        ("right_tote", tote_r, _right_tote_position),
    ):
        if _handle is None:
            raise RuntimeError("%s handle is missing" % _name)
        _actual_xyz, _actual_quaternion = _handle.get_world_pose()
        _actual_xyz = np.asarray(_actual_xyz, dtype=float)
        if (
            not np.isfinite(_actual_xyz).all()
            or float(np.linalg.norm(_actual_xyz - _expected_xyz)) > 0.03
            or not _quaternion_matches(_actual_quaternion, IDENT)
        ):
            raise RuntimeError(
                "%s was not reset: actual=%s quaternion=%s expected=%s"
                % (
                    _name,
                    _actual_xyz.tolist(),
                    np.asarray(_actual_quaternion, dtype=float).tolist(),
                    _expected_xyz.tolist(),
                )
            )
    for _name, _arm in (("franka_left", frL), ("franka_right", frR)):
        _joints = np.asarray(_arm.get_joint_positions(), dtype=float)
        if (
            len(_joints) < len(FR_HOME)
            or not np.isfinite(_joints[: len(FR_HOME)]).all()
            or float(np.max(np.abs(_joints[: len(FR_HOME)] - FR_HOME))) > 0.02
        ):
            raise RuntimeError(
                "%s did not reach reset home: %s"
                % (_name, _joints[: len(FR_HOME)].tolist())
            )
    if tuple(g.get("AMR_PARK", ())) != _park:
        raise RuntimeError("AMR reset/park marker is missing")
    _actual_amr_joints = np.asarray(amr.get_joint_positions(), dtype=float)
    if (
        len(_actual_amr_joints) < len(_amr_joints)
        or not np.isfinite(_actual_amr_joints[: len(_amr_joints)]).all()
        or float(
            np.max(
                np.abs(
                    _actual_amr_joints[: len(_amr_joints)]
                    - _amr_joints
                )
            )
        )
        > 0.02
    ):
        raise RuntimeError(
            "AMR did not reach reset target: actual=%s expected=%s"
            % (
                _actual_amr_joints[: len(_amr_joints)].tolist(),
                _amr_joints.tolist(),
            )
        )

    # The camera graph is built once at startup and intentionally survives
    # scene resets.  Fail the reset if another command moved Cam_Table or
    # removed its viewport-independent publisher, rather than silently
    # returning a scene whose operator view differs from the hardened contract.
    _table_contract = g.get("_IC_TABLE_CAM_CONTRACT") or {}
    _camera_topic_contract = g.get("_IC_CAMERA_TOPIC_CONTRACT") or {}
    _expected_image_topics = {
        "wrist": "/wrist_cam/image_raw",
        "outside": "/outside_cam/image_raw",
        "wrist_right": "/wrist_right_cam/image_raw",
        "outside_right": "/outside_right_cam/image_raw",
        "table": "/table_cam/image_raw",
        "inspect": "/inspect_cam/image_raw",
        "rack": "/rack_cam/image_raw",
    }
    if (
        not g.get("_IC_CAMS_RP_READY", False)
        or _camera_topic_contract.get("image_topics")
        != _expected_image_topics
        or _camera_topic_contract.get("unique_render_product_count") != 6
        or _table_contract.get("prim") != "/Cam_Table"
        or _table_contract.get("topic") != "/table_cam/image_raw"
        or not stage.GetPrimAtPath("/ROS_CamsRP").IsValid()
        or not stage.GetPrimAtPath(
            str(_table_contract.get("render_product", ""))
        ).IsValid()
    ):
        raise RuntimeError(
            "table-camera publisher contract is unavailable: %s"
            % {
                "table": _table_contract,
                "all_cameras": _camera_topic_contract,
            }
        )
    _table_prim = stage.GetPrimAtPath("/Cam_Table")
    if not _table_prim.IsValid() or not _table_prim.IsA(UsdGeom.Camera):
        raise RuntimeError("hardened table camera is missing")
    _table_xform = UsdGeom.Xformable(_table_prim)
    _table_camera = UsdGeom.Camera(_table_prim)

    def _read_table_ops():
        return {
            str(_op.GetOpName()): np.asarray(_op.Get(), dtype=float)
            for _op in _table_xform.GetOrderedXformOps()
        }

    _table_ops = _read_table_ops()
    _table_expected_ops = {
        "xformOp:translate": np.asarray(
            _table_contract.get("translation"), dtype=float
        ),
        "xformOp:rotateYXZ": np.asarray(
            _table_contract.get("rotation_yxz_deg"), dtype=float
        ),
        "xformOp:scale": np.asarray(
            _table_contract.get("scale"), dtype=float
        ),
    }
    # USD stores rotateYXZ as float32, so its readback has a few microdegrees
    # of normal quantization.  Keep translation/scale checks tight while
    # allowing only that representational tolerance for the rotation op.
    _table_op_tolerances = {
        "xformOp:translate": 1e-8,
        "xformOp:rotateYXZ": 1e-5,
        "xformOp:scale": 1e-6,
    }
    def _table_camera_matches_contract():
        return not (
            set(_table_ops) != set(_table_expected_ops)
            or any(
                _table_ops[_name].shape != (3,)
                or _expected.shape != (3,)
                or not np.isfinite(_table_ops[_name]).all()
                or float(
                    np.max(np.abs(_table_ops[_name] - _expected))
                )
                > _table_op_tolerances[_name]
                for _name, _expected in _table_expected_ops.items()
            )
            or abs(
                float(_table_camera.GetFocalLengthAttr().Get())
                - float(_table_contract.get("focal_length_mm"))
            )
            > 1e-6
        )

    if not _table_camera_matches_contract():
        _table_ops_before_restore = {
            _name: _value.tolist() for _name, _value in _table_ops.items()
        }
        # A scene reset owns restoration of the canonical camera pose just as
        # it owns restoration of object and robot poses. Re-author the exact
        # startup contract on the existing prim; the render product remains
        # attached and no camera graph or Isaac restart is required.
        _table_xform.ClearXformOpOrder()
        _table_xform.AddTranslateOp(
            precision=UsdGeom.XformOp.PrecisionDouble
        ).Set(Gf.Vec3d(*_table_expected_ops["xformOp:translate"].tolist()))
        _table_xform.AddRotateYXZOp(
            precision=UsdGeom.XformOp.PrecisionFloat
        ).Set(Gf.Vec3f(*_table_expected_ops["xformOp:rotateYXZ"].tolist()))
        _table_xform.AddScaleOp(
            precision=UsdGeom.XformOp.PrecisionFloat
        ).Set(Gf.Vec3f(*_table_expected_ops["xformOp:scale"].tolist()))
        _table_camera.GetFocalLengthAttr().Set(
            float(_table_contract.get("focal_length_mm"))
        )
        _table_camera.GetClippingRangeAttr().Set(
            Gf.Vec2f(
                *[
                    float(_value)
                    for _value in _table_contract.get("clipping_range_m")
                ]
            )
        )
        _table_ops = _read_table_ops()
        print(
            "IC_TABLE_CAMERA_RESTORED before=%s after=%s"
            % (
                _table_ops_before_restore,
                {
                    _name: _value.tolist()
                    for _name, _value in _table_ops.items()
                },
            ),
            flush=True,
        )

    if not _table_camera_matches_contract():
        raise RuntimeError(
            "table-camera contract restore failed: actual=%s expected=%s"
            % (
                {
                    _name: _value.tolist()
                    for _name, _value in _table_ops.items()
                },
                {
                    _name: _value.tolist()
                    for _name, _value in _table_expected_ops.items()
                },
            )
        )
    if _live_reset:
        if id(S) != _state_identity or S.get("task") is not _task_object:
            raise RuntimeError("reset transaction replaced or lost its task state")
        if g.get("_IC_PENDING_RESET") is not None:
            raise RuntimeError("pending reset marker survived reset execution")

    # Never let the first policy query reuse images from the prior pose/layout.
    # The existing ROS subscriptions refill these dictionaries; mission
    # admission below waits thirty physics ticks so the objects settle and
    # fresh camera messages replace any queued pre-reset frames.
    for _frame_key in ("_GRF", "_GRFR"):
        _frame_map = g.get(_frame_key)
        if isinstance(_frame_map, dict):
            _frame_map.clear()
        else:
            g[_frame_key] = {}
    for _context in _executor_contexts.values():
        _frame_map = _context.get("_GRF")
        if isinstance(_frame_map, dict):
            _frame_map.clear()
    g["_IC_SCENE_SETTLE_UNTIL_TICK"] = int(S.get("n", 0)) + 30

    g["_IC_LAST_RESET_PROFILE"] = _profile
    g["_IC_LAST_RESET_SCENE"] = _scene_record
    g["_IC_RESET_SCENE_READY"] = True
    if not _bootstrap_request and not _live_reset:
        g["_IC_FULL_SCENE_READY"] = _full_scene_ready_before_reset
    print(
        "IC_GROOT_RUNTIME_READY executor=home_convergence_v36_direct "
        "concurrent=per_arm_seed_v1 route=shared",
        flush=True,
    )
    print(
        "IC_SCENE_RESET_READY "
        + json.dumps(
            {
                "profile": _profile,
                "camera_profile": _camera_profile or "production",
                "scene": _scene_record,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    print(
        "IC_TWO_ARM_RESET_DONE profile=%s totes=table arms=home "
        "AMR=parked gexec=%d"
        % (_profile, int(g.get("_GEXEC_OVERRIDE", -1))),
        flush=True,
    )
except Exception:
    globals()["_IC_RESET_SCENE_READY"] = False
    print("IC_DEMO_RESET_ERR:\n" + traceback.format_exc(), flush=True)
    raise
