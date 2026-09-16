# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import os, traceback
os.environ.setdefault("ROS_DOMAIN_ID","0")
os.environ.setdefault("RMW_IMPLEMENTATION","rmw_fastrtps_cpp")
try:
    from isaacsim.core.utils.extensions import enable_extension
    ok=enable_extension("isaacsim.ros2.bridge"); print("BRIDGE_ENABLE ok=%s"%ok, flush=True)
    import omni.graph.core as og
    og.Controller.edit({"graph_path":"/ROSClockTest","evaluator_name":"execution"}, {
        og.Controller.Keys.CREATE_NODES:[
            ("tick","omni.graph.action.OnPlaybackTick"),
            ("ctx","isaacsim.ros2.bridge.ROS2Context"),
            ("pub","isaacsim.ros2.bridge.ROS2PublishClock"),
        ],
        og.Controller.Keys.SET_VALUES:[("ctx.inputs:domain_id",0)],
        og.Controller.Keys.CONNECT:[
            ("tick.outputs:tick","pub.inputs:execIn"),
            ("ctx.outputs:context","pub.inputs:context"),
        ],
    })
    import omni.timeline; omni.timeline.get_timeline_interface().play()
    print("ROSCLOCK_BUILT", flush=True)
except Exception:
    print("ROSTEST_ERR:\n"+traceback.format_exc(), flush=True)
