# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""One-shot hardened full-scene bootstrap for isaac-gui-auto.sh --exec.

This file is deliberately separate from mutable cmd.py.  It is executed once
by startup.py after the base USD is stable, then startup.py arms cmd.py for
normal commands without ever treating the last command as a boot recipe.
"""

import json as _bootstrap_json
import os as _bootstrap_os


_PGFR_FULL_SCENE_READY = False
_old_a1_sub = globals().get("_PGFR_SHAPE_A1_SUB")
if _old_a1_sub is not None:
    try:
        _old_a1_sub.unsubscribe()
    except Exception:
        pass
globals()["_PGFR_SHAPE_A1_SUB"] = None
globals()["_PGFR_SHAPE_A1_ORIGINAL_FINISH"] = None
globals().pop("_PGFR_SHAPE_ORIG", None)
globals().pop("_PGFR_SHAPE_LAST_SCENE", None)
globals().pop("_PGFR_SHAPE_MODE_READY", None)
for _shape_key in (
    "_shape_rp_red",
    "_shape_rp_blue",
    "_shape_rp_green",
    "_shape_rp_red_right",
    "_shape_rp_blue_right",
    "_shape_rp_green_right",
):
    globals().pop(_shape_key, None)


def _exec_setup(_path):
    with open(_path, encoding="utf-8") as _setup_file:
        exec(compile(_setup_file.read(), _path, "exec"), globals())


# Physics-affecting USD additions must precede World/tensor creation.
_exec_setup("/scripts/setup_right_cell.py")
_exec_setup("/scripts/pgfr_node_v2.py")

# Runtime/camera/visual/reset layers use the established working stack.
for _setup_path in (
    "/scripts/pgfr_cams_rp.py",
    "/scripts/add_tote_colors.py",
    "/scripts/matte_scene.py",
):
    _exec_setup(_setup_path)

_scene_profile = _bootstrap_os.environ.get(
    "PGFR_SCENE_PROFILE",
    "groot_three_object",
).strip().lower()
if _scene_profile not in ("pgfr_two_arm", "groot_three_object"):
    raise RuntimeError(
        "PGFR_SCENE_PROFILE must be pgfr_two_arm or groot_three_object"
    )
_ready_arm = _bootstrap_os.environ.get(
    "PGFR_GROOT_READY_ARM",
    "both",
).strip().lower()
_ready_color = _bootstrap_os.environ.get(
    "PGFR_GROOT_READY_COLOR",
    "red",
).strip().lower()
_ready_layout = int(
    _bootstrap_os.environ.get("PGFR_GROOT_READY_LAYOUT", "3")
)
_ready_seed_default = {
    "franka_left": "30100",
    "franka_right": "40100",
    "both": "31302",
}.get(_ready_arm, "31302")
_ready_seed = int(
    _bootstrap_os.environ.get(
        "PGFR_GROOT_READY_SEED",
        _ready_seed_default,
    )
)
if _ready_arm not in ("franka_left", "franka_right", "both"):
    raise RuntimeError(
        "PGFR_GROOT_READY_ARM must be franka_left, franka_right, or both"
    )
if _ready_color not in ("red", "blue", "green"):
    raise RuntimeError(
        "PGFR_GROOT_READY_COLOR must be red, blue, or green"
    )
if not 0 <= _ready_layout <= 5:
    raise RuntimeError("PGFR_GROOT_READY_LAYOUT must be from 0 through 5")

# Cache one immutable startup contract for every subsequent live reset.  Both
# startup and reset_scene execute the same reset_two_arm.py transaction, so
# aliases, followers, telemetry, and validation cannot drift into two paths.
_camera_profile = _bootstrap_os.environ.get(
    "PGFR_CAMERA_PROFILE",
    "production",
).strip().lower() or "production"
if _scene_profile == "groot_three_object" and _camera_profile != "capture":
    raise RuntimeError(
        "groot_three_object requires PGFR_CAMERA_PROFILE=capture so every "
        "policy camera uses the certified native-DROID 320x180 contract"
    )
_groot_relay_ports = {
    "red": int(
        _bootstrap_os.environ.get("PGFR_GROOT_RED_RELAY_PORT", "5681")
    ),
    "blue": int(
        _bootstrap_os.environ.get("PGFR_GROOT_BLUE_RELAY_PORT", "5682")
    ),
    "green": int(
        _bootstrap_os.environ.get("PGFR_GROOT_GREEN_RELAY_PORT", "5683")
    ),
    # Retained only as an explicit comparison/fallback artifact.  Normal
    # color dispatch always selects the three 1000-step specialists above.
    "red500": int(
        _bootstrap_os.environ.get("PGFR_GROOT_RED500_RELAY_PORT", "5684")
    ),
}
if (
    len(set(_groot_relay_ports.values())) != 4
    or any(
        not 1024 <= _port <= 65535
        for _port in _groot_relay_ports.values()
    )
):
    raise RuntimeError(
        "GR00T relay ports must be four unique user ports: %s"
        % _groot_relay_ports
    )
globals()["_PGFR_GROOT_RELAY_CONTRACT"] = {
    "host": "127.0.0.1",
    "ports": _groot_relay_ports,
    "transport": "workstation-loopback-to-thor-loopback-ssh",
}
_groot_policy_route = _bootstrap_os.environ.get(
    "PGFR_GROOT_POLICY_ROUTE",
    "specialist",
).strip().lower() or "specialist"
if _groot_policy_route not in ("specialist", "shared"):
    raise RuntimeError(
        "PGFR_GROOT_POLICY_ROUTE must be specialist or shared"
    )
globals()["_PGFR_GROOT_POLICY_ROUTE"] = _groot_policy_route
if _groot_policy_route == "shared":
    _shared_policy_contract_path = _bootstrap_os.environ.get(
        "PGFR_GROOT_SHARED_POLICY_CONTRACT_PATH",
        "/scripts/groot_shared_policy_contract.json",
    ).strip()
    if not _shared_policy_contract_path:
        raise RuntimeError(
            "shared GR00T routing requires PGFR_GROOT_SHARED_POLICY_CONTRACT_PATH"
        )
    if not _bootstrap_os.path.isfile(_shared_policy_contract_path):
        raise RuntimeError(
            "shared-policy contract is missing: %s"
            % _shared_policy_contract_path
        )
    with open(_shared_policy_contract_path, encoding="utf-8") as _contract_file:
        _shared_policy_contract = _bootstrap_json.load(_contract_file)
    if not isinstance(_shared_policy_contract, dict):
        raise RuntimeError("shared-policy contract must be a JSON object")
    globals()["_PGFR_GROOT_SHARED_POLICY_CONTRACT"] = dict(
        _shared_policy_contract
    )
else:
    globals().pop("_PGFR_GROOT_SHARED_POLICY_CONTRACT", None)
_scene_reset_contract = {
    "scene_profile": _scene_profile,
    "arm": _ready_arm,
    "color": _ready_color,
    "layout": _ready_layout,
    "seed": _ready_seed,
    "camera_profile": _camera_profile,
}
globals()["_PGFR_SCENE_RESET_CONTRACT"] = dict(_scene_reset_contract)
globals()["_PGFR_RESET_SCENE_REQUEST"] = dict(_scene_reset_contract)
try:
    _exec_setup("/scripts/reset_two_arm.py")
finally:
    globals().pop("_PGFR_RESET_SCENE_REQUEST", None)
if not globals().get("_PGFR_RESET_SCENE_READY", False):
    raise RuntimeError("startup reset returned without its ready marker")
if globals().get("_PGFR_LAST_RESET_PROFILE") != _scene_profile:
    raise RuntimeError(
        "startup reset profile mismatch: %s"
        % globals().get("_PGFR_LAST_RESET_PROFILE")
    )

if _scene_profile == "groot_three_object":
    _ready_scene = globals().get("_PGFR_LAST_RESET_SCENE") or {}
    print(
        "PGFR_GROOT_THREE_OBJECT_READY "
        "target=%s layout=%d seed=%d arm=%s"
        % (_ready_color, _ready_layout, _ready_seed, _ready_arm),
        flush=True,
    )
    if _ready_arm == "both":
        print(
            "PGFR_GROOT_DUAL_THREE_OBJECT_READY "
            "objects=6 arms=franka_left,franka_right",
            flush=True,
        )


_required_prims = (
    "/World/BigTote_R",
    "/World/BigTote/pad_red",
    "/World/BigTote/pad_blue",
    "/World/BigTote/pad_green",
    "/World/BigTote_R/pad_red",
    "/World/BigTote_R/pad_blue",
    "/World/BigTote_R/pad_green",
    "/Workcell/Franka_Left/panda_hand/WristCam",
    "/Workcell/Franka_Right/panda_hand/WristCam",
    "/RackCam_BR",
    "/Cam_Table",
    "/ROS_CamsRP",
    "/World/ShapeCyl_blue",
    "/World/ShapeCyl_blue_R",
    "/World/ShapeBrick_green",
    "/World/ShapeBrick_green_R",
)
_missing_prims = [
    _path for _path in _required_prims if not stage.GetPrimAtPath(_path).IsValid()
]
if _missing_prims:
    raise RuntimeError("full-scene bootstrap missing prims: %s" % _missing_prims)
if not globals().get("_PGFR_CAMS_RP_READY", False):
    raise RuntimeError("camera render-product graph is not ready")
_camera_topic_contract = globals().get("_PGFR_CAMERA_TOPIC_CONTRACT") or {}
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
    _camera_topic_contract.get("image_topics") != _expected_image_topics
    or _camera_topic_contract.get("unique_render_product_count") != 6
):
    raise RuntimeError(
        "full camera topic contract is incomplete: %s"
        % _camera_topic_contract
    )
_table_camera_contract = globals().get("_PGFR_TABLE_CAM_CONTRACT") or {}
if (
    _table_camera_contract.get("prim") != "/Cam_Table"
    or _table_camera_contract.get("topic") != "/table_cam/image_raw"
    or not stage.GetPrimAtPath(
        str(_table_camera_contract.get("render_product", ""))
    ).IsValid()
):
    raise RuntimeError(
        "hardened table-camera contract is incomplete: %s"
        % _table_camera_contract
    )
if tote_r is None:
    raise RuntimeError("right tote handle was not created")
if S.get("task") is not None:
    raise RuntimeError("full-scene bootstrap ended with an active task: %s" % S.get("task"))
if (
    _scene_profile == "groot_three_object"
    and set(globals().get("_PGFR_SHAPE_ASSET_AUDIT") or {}) != {"blue", "green"}
):
    raise RuntimeError(
        "shape A0 audit is incomplete: %s"
        % globals().get("_PGFR_SHAPE_ASSET_AUDIT")
    )
if (
    _scene_profile == "groot_three_object"
    and _ready_arm == "both"
    and set(globals().get("_PGFR_SHAPE_DUAL_ASSET_AUDIT") or {})
    != {"blue", "green"}
):
    raise RuntimeError(
        "dual-arm shape A0 audit is incomplete: %s"
        % globals().get("_PGFR_SHAPE_DUAL_ASSET_AUDIT")
    )
if tuple(globals().get("AMR_PARK", ())) != (1.74, -8.667):
    raise RuntimeError("AMR reset/park marker is missing")
if (
    _camera_profile == "capture"
    and (
        globals().get("_PGFR_SYNC_ORIGINAL_RUN_MOVE") is None
        or not globals().get("_PGFR_SYNC_CAPTURE_READY", False)
    )
):
    raise RuntimeError("capture profile ended without synchronized telemetry")

_PGFR_FULL_SCENE_READY = True
print(
    "PGFR_FULL_SCENE_RESTORED "
    "right_cell+cameras+pads+matte+two_arm_reset"
    + (
        "+shape_a0+groot_three_object"
        if _scene_profile == "groot_three_object"
        else "+pgfr_two_arm"
    )
    + (
        "+dual_arm_six_object"
        if _scene_profile == "groot_three_object" and _ready_arm == "both"
        else ""
    )
    + (
        "+dual_arm_sync_capture"
        if _bootstrap_os.environ.get("PGFR_CAMERA_PROFILE", "").strip().lower()
        == "capture"
        else ""
    ),
    flush=True,
)
