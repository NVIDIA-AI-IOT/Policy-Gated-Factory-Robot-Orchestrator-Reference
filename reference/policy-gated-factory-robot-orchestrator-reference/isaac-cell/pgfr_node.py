# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# pgfr_node.py — Isaac-side HIL command channel (rclpy, spun from the physics loop).
import os, json, traceback
os.environ.setdefault("ROS_DOMAIN_ID","0"); os.environ.setdefault("RMW_IMPLEMENTATION","rmw_fastrtps_cpp")
import omni.physx, omni.timeline
import rclpy
from std_msgs.msg import String
old=globals().get("_PGFR_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_PGFR_SUB"]=None
try:
    if not rclpy.ok(): rclpy.init()
except Exception:
    try: rclpy.init()
    except Exception: pass
node=globals().get("_PGFR_NODE")
if node is None:
    node=rclpy.create_node("pgfr_isaac_floor"); globals()["_PGFR_NODE"]=node
    globals()["_PGFR_RESULT"]=node.create_publisher(String,"/pgfr/result",10)
    globals()["_PGFR_STATE"]=node.create_publisher(String,"/pgfr/floor_state",10)
    globals()["_PGFR_Q"]=[]
    def on_cmd(msg):
        try: cmd=json.loads(msg.data)
        except Exception: cmd={"raw":msg.data}
        print("PGFR_CMD_RECV %s"%cmd, flush=True); globals()["_PGFR_Q"].append(cmd)
    globals()["_PGFR_CMDSUB"]=node.create_subscription(String,"/pgfr/command",on_cmd,10)
result_pub=globals()["_PGFR_RESULT"]; state_pub=globals()["_PGFR_STATE"]; Q=globals()["_PGFR_Q"]
S={"n":0}
def _step(dt):
    try:
        rclpy.spin_once(node, timeout_sec=0.0)
        while Q:
            cmd=Q.pop(0)
            res={"ack":cmd,"success":True,"note":"channel-proof"}
            result_pub.publish(String(data=json.dumps(res))); print("PGFR_RESULT_PUB %s"%res, flush=True)
        S["n"]+=1
        if S["n"]%120==0:
            state_pub.publish(String(data=json.dumps({"alive":True,"tick":S["n"],
                "endpoints":["franka_left","franka_right","mobilebot"]})))
    except Exception:
        print("PGFR_NODE_ERR:\n"+traceback.format_exc(), flush=True)
omni.timeline.get_timeline_interface().play()
_PGFR_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("PGFR_NODE_STARTED", flush=True)
