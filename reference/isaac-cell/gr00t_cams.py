# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import os, traceback
os.environ.setdefault("ROS_DOMAIN_ID","0"); os.environ.setdefault("RMW_IMPLEMENTATION","rmw_fastrtps_cpp")
import omni, omni.graph.core as og, usdrt.Sdf
from isaacsim.core.utils import extensions
from pxr import UsdGeom, Gf
extensions.enable_extension("isaacsim.ros2.bridge")
stage = omni.usd.get_context().get_stage()

# FIX (verified 2026-06-22): instanced gripper geometry does NOT render in camera render
# products (arm links, also instanced, do). De-instance the gripper /geometry so it renders.
for arm in ["Franka_Left", "Franka_Right"]:
    for part in ["panda_hand/geometry", "panda_leftfinger/geometry", "panda_rightfinger/geometry"]:
        gp = stage.GetPrimAtPath("/Workcell/%s/%s" % (arm, part))
        if gp.IsValid():
            gp.SetInstanceable(False)

# WRIST cam parented to the LEFT arm's hand -> moves with the gripper (egocentric view for GR00T)
HAND = "/Workcell/Franka_Left/panda_hand"
WCAM = HAND + "/WristCam"
if stage.GetPrimAtPath(WCAM).IsValid():
    stage.RemovePrim(WCAM)
wc = UsdGeom.Camera.Define(stage, WCAM)
wc.GetFocalLengthAttr().Set(16.0); wc.GetClippingRangeAttr().Set(Gf.Vec2f(0.005, 12.0))
xf = UsdGeom.Xformable(wc.GetPrim()); xf.ClearXformOpOrder()
# user-tuned eye-in-hand pose, baked as a local-to-panda_hand matrix (captured 2026-06-22)
_M = Gf.Matrix4d(-0.659877, -0.127132, -0.740540, 0.0,
                 -0.214963,  0.976329,  0.023937, 0.0,
                  0.719968,  0.174984, -0.671585, 0.0,
                  0.270284,  0.045531, -0.041819, 1.0)
xf.AddTransformOp().Set(_M)

def build(graph_path, cam, prefix, vp):
    keys = og.Controller.Keys
    (g, _, _, _) = og.Controller.edit(
        {"graph_path": graph_path, "evaluator_name": "push", "pipeline_stage": og.GraphPipelineStage.GRAPH_PIPELINE_STAGE_ONDEMAND},
        {keys.CREATE_NODES: [
            ("OnTick", "omni.graph.action.OnTick"),
            ("cVP", "isaacsim.core.nodes.IsaacCreateViewport"),
            ("gRP", "isaacsim.core.nodes.IsaacGetViewportRenderProduct"),
            ("sC", "isaacsim.core.nodes.IsaacSetCameraOnRenderProduct"),
            ("rgb", "isaacsim.ros2.bridge.ROS2CameraHelper"),
            ("info", "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),
        ],
        keys.CONNECT: [
            ("OnTick.outputs:tick", "cVP.inputs:execIn"),
            ("cVP.outputs:execOut", "gRP.inputs:execIn"),
            ("cVP.outputs:viewport", "gRP.inputs:viewport"),
            ("gRP.outputs:execOut", "sC.inputs:execIn"),
            ("gRP.outputs:renderProductPath", "sC.inputs:renderProductPath"),
            ("sC.outputs:execOut", "rgb.inputs:execIn"),
            ("sC.outputs:execOut", "info.inputs:execIn"),
            ("gRP.outputs:renderProductPath", "rgb.inputs:renderProductPath"),
            ("gRP.outputs:renderProductPath", "info.inputs:renderProductPath"),
        ],
        keys.SET_VALUES: [
            ("cVP.inputs:viewportId", vp),
            ("rgb.inputs:frameId", prefix), ("rgb.inputs:topicName", prefix + "/image_raw"), ("rgb.inputs:type", "rgb"),
            ("info.inputs:frameId", prefix), ("info.inputs:topicName", prefix + "/camera_info"),
            ("sC.inputs:cameraPrim", [usdrt.Sdf.Path(cam)]),
        ]})
    og.Controller.evaluate_sync(g)

try:
    build("/ROS_WristCam",   WCAM,         "wrist_cam",   1)   # egocentric, on the arm
    build("/ROS_OutsideCam", "/RackCam_B", "outside_cam", 2)   # exterior POV
    import omni.timeline; omni.timeline.get_timeline_interface().play()
    print("GR00T_CAMS_BUILT", flush=True)
except Exception:
    print("GR00T_CAMS_ERR:\n" + traceback.format_exc(), flush=True)
