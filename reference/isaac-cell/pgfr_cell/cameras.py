# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Cameras: wrist cam, RackCam_B final pose, and the ROS 2 publisher graphs.

Port of gr00t_cams.py + cam_final_pose.py + pub_cam.py + pub_cam_extra.py
(2026-07-07). The five graphs use distinct viewport ids so their render products
cannot alias; camera poses and ROS topics match the validated bring-up sequence.
"""
import os
import traceback

os.environ.setdefault("ROS_DOMAIN_ID", "0")
os.environ.setdefault("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")

import omni.graph.core as og
import omni.usd
import usdrt.Sdf
from pxr import Gf, UsdGeom

from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.core.utils import extensions

WRIST_HAND = "/Workcell/Franka_Left/panda_hand"
WRIST_CAM = WRIST_HAND + "/WristCam"
# user-tuned eye-in-hand pose, baked as a local-to-panda_hand matrix (captured 2026-06-22)
_WRIST_M = Gf.Matrix4d(-0.659877, -0.127132, -0.740540, 0.0,
                       -0.214963, 0.976329, 0.023937, 0.0,
                       0.719968, 0.174984, -0.671585, 0.0,
                       0.270284, 0.045531, -0.041819, 1.0)
# RackCam_B: operator's FINAL hand-tuned pose (PGFR_PRODUCTION_CONTRACT dump 2026-07-06)
_RACKB_M = Gf.Matrix4d(
    -1.0000000000000002, 0.0, 0.0, 0.0,
    0.0, -0.8821318585950626, 0.4710025308335628, 0.0,
    0.0, 0.47100253083356275, 0.8821318585950625, 0.0,
    3.8000000000000007, -5.773468356683304, 3.3742668912965272, 1.0000000000000002,
)


_ROBOT_CAMERA_GEOMETRY = tuple(
    "/Workcell/%s/%s" % (arm, part)
    for arm in ("Franka_Left", "Franka_Right")
    for part in (
        "panda_hand/geometry",
        "panda_leftfinger/geometry",
        "panda_rightfinger/geometry",
    )
)


def prepare_robot_camera_geometry(stage=None):
    """De-instance gripper visuals before tensor/physics views are created."""
    stage = stage or omni.usd.get_context().get_stage()
    changed = []
    for path in _ROBOT_CAMERA_GEOMETRY:
        prim = stage.GetPrimAtPath(path)
        if prim.IsValid() and prim.IsInstanceable():
            prim.SetInstanceable(False)
            changed.append(path)
    print("CAMERA_GEOMETRY_PREPARED changed=%d" % len(changed), flush=True)


def _require_prepared_robot_camera_geometry(stage):
    late = [
        path
        for path in _ROBOT_CAMERA_GEOMETRY
        if stage.GetPrimAtPath(path).IsValid()
        and stage.GetPrimAtPath(path).IsInstanceable()
    ]
    if late:
        raise RuntimeError(
            "robot camera geometry must be de-instanced before physics: %s" % late
        )


def validate_prepared_camera_stage(stage=None):
    """Fail before physics if camera preparation left an incomplete stage."""
    stage = stage or omni.usd.get_context().get_stage()
    _require_prepared_robot_camera_geometry(stage)
    required = _ROBOT_CAMERA_GEOMETRY + (
        "/Workcell/Franka_Left/panda_hand/geometry/panda_hand",
        "/Workcell/Franka_Right/panda_hand/geometry/panda_hand",
        WRIST_CAM,
        "/RackCam_A",
        "/RackCam_B",
        "/Cam_Table",
        "/ROS_WristCam",
        "/ROS_OutsideCam",
        "/ROS_TableCam",
        "/ROS_RackCam",
        "/ROS_InspectCam",
    )
    missing = [path for path in required if not stage.GetPrimAtPath(path).IsValid()]
    if missing:
        raise RuntimeError("prepared camera stage is missing prims: %s" % missing)
    print("CAMERA_STAGE_READY prims=%d" % len(required), flush=True)


def _build_graph(stage, graph_path, cam, prefix, vp, with_depth):
    keys = og.Controller.Keys
    nodes = [
        ("OnTick", "omni.graph.action.OnTick"),
        ("cVP", "isaacsim.core.nodes.IsaacCreateViewport"),
        ("gRP", "isaacsim.core.nodes.IsaacGetViewportRenderProduct"),
        ("sC", "isaacsim.core.nodes.IsaacSetCameraOnRenderProduct"),
        ("rgb", "isaacsim.ros2.bridge.ROS2CameraHelper"),
        ("info", "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),
    ]
    connects = [
        ("OnTick.outputs:tick", "cVP.inputs:execIn"),
        ("cVP.outputs:execOut", "gRP.inputs:execIn"),
        ("cVP.outputs:viewport", "gRP.inputs:viewport"),
        ("gRP.outputs:execOut", "sC.inputs:execIn"),
        ("gRP.outputs:renderProductPath", "sC.inputs:renderProductPath"),
        ("sC.outputs:execOut", "rgb.inputs:execIn"),
        ("sC.outputs:execOut", "info.inputs:execIn"),
        ("gRP.outputs:renderProductPath", "rgb.inputs:renderProductPath"),
        ("gRP.outputs:renderProductPath", "info.inputs:renderProductPath"),
    ]
    values = [
        ("cVP.inputs:viewportId", vp),
        ("rgb.inputs:frameId", prefix), ("rgb.inputs:topicName", prefix + "/image_raw"),
        ("rgb.inputs:type", "rgb"),
        ("info.inputs:frameId", prefix), ("info.inputs:topicName", prefix + "/camera_info"),
        ("sC.inputs:cameraPrim", [usdrt.Sdf.Path(cam)]),
    ]
    if with_depth:
        nodes.append(("depth", "isaacsim.ros2.bridge.ROS2CameraHelper"))
        connects += [
            ("sC.outputs:execOut", "depth.inputs:execIn"),
            ("gRP.outputs:renderProductPath", "depth.inputs:renderProductPath"),
        ]
        values += [
            ("depth.inputs:frameId", prefix), ("depth.inputs:topicName", prefix + "/depth"),
            ("depth.inputs:type", "depth"),
        ]
    (g, _, _, _) = og.Controller.edit(
        {"graph_path": graph_path, "evaluator_name": "push",
         "pipeline_stage": og.GraphPipelineStage.GRAPH_PIPELINE_STAGE_ONDEMAND},
        {keys.CREATE_NODES: nodes, keys.CONNECT: connects, keys.SET_VALUES: values})
    og.Controller.evaluate_sync(g)


def build_gr00t_cams():
    """Wrist cam on the left hand + RackCam_B final pose + wrist/outside publishers."""
    extensions.enable_extension("isaacsim.ros2.bridge")
    stage = omni.usd.get_context().get_stage()
    _require_prepared_robot_camera_geometry(stage)
    if stage.GetPrimAtPath(WRIST_CAM).IsValid():
        stage.RemovePrim(WRIST_CAM)
    wc = UsdGeom.Camera.Define(stage, WRIST_CAM)
    wc.GetFocalLengthAttr().Set(16.0)
    wc.GetClippingRangeAttr().Set(Gf.Vec2f(0.005, 12.0))
    xf = UsdGeom.Xformable(wc.GetPrim()); xf.ClearXformOpOrder()
    xf.AddTransformOp().Set(_WRIST_M)
    set_rackcam_b_final_pose()
    for gp in ("/ROS_WristCam", "/ROS_OutsideCam", "/ROS_TableCam", "/ROS_RackCam", "/ROS_InspectCam"):
        if stage.GetPrimAtPath(gp).IsValid():
            stage.RemovePrim(gp)
    _build_graph(stage, "/ROS_WristCam", WRIST_CAM, "wrist_cam", 1, with_depth=False)
    _build_graph(stage, "/ROS_OutsideCam", "/RackCam_B", "outside_cam", 2, with_depth=False)
    print("GR00T_CAMS_BUILT", flush=True)


def set_rackcam_b_final_pose():
    stage = omni.usd.get_context().get_stage()
    oc = stage.GetPrimAtPath("/RackCam_B")
    if oc.IsValid():
        xf = UsdGeom.Xformable(oc); xf.ClearXformOpOrder()
        xf.AddTransformOp().Set(_RACKB_M)
        UsdGeom.Camera(oc).GetFocalLengthAttr().Set(33.0)
    print("CAM_FINAL_POSE_OK", flush=True)


def build_floor_cams():
    """table_cam (Cam_Table) + rack_cam (RackCam_A) + inspect_cam (RackCam_B)."""
    extensions.enable_extension("isaacsim.ros2.bridge")
    stage = omni.usd.get_context().get_stage()
    cam = "/Cam_Table"
    if not stage.GetPrimAtPath(cam).IsValid():
        c = UsdGeom.Camera.Define(stage, cam)
        UsdGeom.XformCommonAPI(c).SetTranslate(Gf.Vec3d(4.1, -7.4, 2.6))
        print("created overhead camera", flush=True)
    _build_graph(stage, "/ROS_TableCam", cam, "table_cam", 3, with_depth=True)
    print("TABLECAM_GRAPH_BUILT", flush=True)
    _build_graph(stage, "/ROS_RackCam", "/RackCam_A", "rack_cam", 4, with_depth=True)
    _build_graph(stage, "/ROS_InspectCam", "/RackCam_B", "inspect_cam", 5, with_depth=True)
    print("EXTRA_CAMS_BUILT", flush=True)


def build_all():
    """Build every camera only while stage topology is safe to modify."""
    try:
        if SimulationManager.get_physics_sim_view() is not None:
            raise RuntimeError(
                "camera topology cannot be changed after physics initialization"
            )
        stage = omni.usd.get_context().get_stage()
        prepare_robot_camera_geometry(stage)
        build_gr00t_cams()
        build_floor_cams()
        validate_prepared_camera_stage(stage)
    except Exception:
        print("CAMS_ERR:\n" + traceback.format_exc(), flush=True)
        raise
