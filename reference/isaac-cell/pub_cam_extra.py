# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import os, traceback
os.environ.setdefault("ROS_DOMAIN_ID","0"); os.environ.setdefault("RMW_IMPLEMENTATION","rmw_fastrtps_cpp")
import omni, omni.graph.core as og, usdrt.Sdf
from isaacsim.core.utils import extensions
extensions.enable_extension("isaacsim.ros2.bridge")
def build(graph_path, cam, prefix, vp):
    keys=og.Controller.Keys
    (g,_,_,_)=og.Controller.edit(
        {"graph_path":graph_path,"evaluator_name":"push","pipeline_stage":og.GraphPipelineStage.GRAPH_PIPELINE_STAGE_ONDEMAND},
        {keys.CREATE_NODES:[
            ("OnTick","omni.graph.action.OnTick"),
            ("cVP","isaacsim.core.nodes.IsaacCreateViewport"),
            ("gRP","isaacsim.core.nodes.IsaacGetViewportRenderProduct"),
            ("sC","isaacsim.core.nodes.IsaacSetCameraOnRenderProduct"),
            ("rgb","isaacsim.ros2.bridge.ROS2CameraHelper"),
            ("info","isaacsim.ros2.bridge.ROS2CameraInfoHelper"),
            ("depth","isaacsim.ros2.bridge.ROS2CameraHelper"),
        ],
        keys.CONNECT:[
            ("OnTick.outputs:tick","cVP.inputs:execIn"),
            ("cVP.outputs:execOut","gRP.inputs:execIn"),
            ("cVP.outputs:viewport","gRP.inputs:viewport"),
            ("gRP.outputs:execOut","sC.inputs:execIn"),
            ("gRP.outputs:renderProductPath","sC.inputs:renderProductPath"),
            ("sC.outputs:execOut","rgb.inputs:execIn"),
            ("sC.outputs:execOut","info.inputs:execIn"),
            ("sC.outputs:execOut","depth.inputs:execIn"),
            ("gRP.outputs:renderProductPath","rgb.inputs:renderProductPath"),
            ("gRP.outputs:renderProductPath","info.inputs:renderProductPath"),
            ("gRP.outputs:renderProductPath","depth.inputs:renderProductPath"),
        ],
        keys.SET_VALUES:[
            ("cVP.inputs:viewportId",vp),
            ("rgb.inputs:frameId",prefix),("rgb.inputs:topicName",prefix+"/image_raw"),("rgb.inputs:type","rgb"),
            ("info.inputs:frameId",prefix),("info.inputs:topicName",prefix+"/camera_info"),
            ("depth.inputs:frameId",prefix),("depth.inputs:topicName",prefix+"/depth"),("depth.inputs:type","depth"),
            ("sC.inputs:cameraPrim",[usdrt.Sdf.Path(cam)]),
        ]})
    og.Controller.evaluate_sync(g)
try:
    build("/ROS_RackCam","/RackCam_A","rack_cam",2)
    build("/ROS_InspectCam","/RackCam_B","inspect_cam",3)
    import omni.timeline; omni.timeline.get_timeline_interface().play()
    print("EXTRA_CAMS_BUILT", flush=True)
except Exception:
    print("EXTRA_CAMS_ERR:\n"+traceback.format_exc(), flush=True)
