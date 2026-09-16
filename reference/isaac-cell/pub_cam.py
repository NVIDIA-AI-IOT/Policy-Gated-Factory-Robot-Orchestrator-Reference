# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import os, traceback
os.environ.setdefault("ROS_DOMAIN_ID","0"); os.environ.setdefault("RMW_IMPLEMENTATION","rmw_fastrtps_cpp")
import omni, omni.graph.core as og, usdrt.Sdf
from isaacsim.core.utils import extensions
from pxr import UsdGeom, Gf
extensions.enable_extension("isaacsim.ros2.bridge")
stage=omni.usd.get_context().get_stage()
CAM="/Cam_Table"
try:
    if not stage.GetPrimAtPath(CAM).IsValid():
        c=UsdGeom.Camera.Define(stage,CAM); UsdGeom.XformCommonAPI(c).SetTranslate(Gf.Vec3d(4.1,-7.4,2.6))
        print("created overhead camera", flush=True)
    keys=og.Controller.Keys
    (g,_,_,_)=og.Controller.edit(
        {"graph_path":"/ROS_TableCam","evaluator_name":"push","pipeline_stage":og.GraphPipelineStage.GRAPH_PIPELINE_STAGE_ONDEMAND},
        {keys.CREATE_NODES:[
            ("OnTick","omni.graph.action.OnTick"),
            ("createVP","isaacsim.core.nodes.IsaacCreateViewport"),
            ("getRP","isaacsim.core.nodes.IsaacGetViewportRenderProduct"),
            ("setCam","isaacsim.core.nodes.IsaacSetCameraOnRenderProduct"),
            ("rgb","isaacsim.ros2.bridge.ROS2CameraHelper"),
            ("info","isaacsim.ros2.bridge.ROS2CameraInfoHelper"),
            ("depth","isaacsim.ros2.bridge.ROS2CameraHelper"),
        ],
        keys.CONNECT:[
            ("OnTick.outputs:tick","createVP.inputs:execIn"),
            ("createVP.outputs:execOut","getRP.inputs:execIn"),
            ("createVP.outputs:viewport","getRP.inputs:viewport"),
            ("getRP.outputs:execOut","setCam.inputs:execIn"),
            ("getRP.outputs:renderProductPath","setCam.inputs:renderProductPath"),
            ("setCam.outputs:execOut","rgb.inputs:execIn"),
            ("setCam.outputs:execOut","info.inputs:execIn"),
            ("setCam.outputs:execOut","depth.inputs:execIn"),
            ("getRP.outputs:renderProductPath","rgb.inputs:renderProductPath"),
            ("getRP.outputs:renderProductPath","info.inputs:renderProductPath"),
            ("getRP.outputs:renderProductPath","depth.inputs:renderProductPath"),
        ],
        keys.SET_VALUES:[
            ("createVP.inputs:viewportId",1),
            ("rgb.inputs:frameId","table_cam"),("rgb.inputs:topicName","table_cam/image_raw"),("rgb.inputs:type","rgb"),
            ("info.inputs:frameId","table_cam"),("info.inputs:topicName","table_cam/camera_info"),
            ("depth.inputs:frameId","table_cam"),("depth.inputs:topicName","table_cam/depth"),("depth.inputs:type","depth"),
            ("setCam.inputs:cameraPrim",[usdrt.Sdf.Path(CAM)]),
        ]})
    og.Controller.evaluate_sync(g)
    import omni.timeline; omni.timeline.get_timeline_interface().play()
    print("TABLECAM_GRAPH_BUILT", flush=True)
except Exception:
    print("TABLECAM_ERR:\n"+traceback.format_exc(), flush=True)
