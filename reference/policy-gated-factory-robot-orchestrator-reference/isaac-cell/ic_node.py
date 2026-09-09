# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# ic_node.py — Isaac-side HIL command channel (rclpy, spun from the physics loop).
import os, json, traceback
os.environ.setdefault("ROS_DOMAIN_ID","0"); os.environ.setdefault("RMW_IMPLEMENTATION","rmw_fastrtps_cpp")
import omni.physx, omni.timeline
import rclpy
from std_msgs.msg import String
old=globals().get("_IC_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_IC_SUB"]=None
try:
    if not rclpy.ok(): rclpy.init()
except Exception:
    try: rclpy.init()
    except Exception: pass
node=globals().get("_IC_NODE")
if node is None:
    node=rclpy.create_node("ic_isaac_floor"); globals()["_IC_NODE"]=node
    globals()["_IC_RESULT"]=node.create_publisher(String,"/ic/result",10)
    globals()["_IC_STATE"]=node.create_publisher(String,"/ic/floor_state",10)
    globals()["_IC_Q"]=[]
    def on_cmd(msg):
        try: cmd=json.loads(msg.data)
        except Exception: cmd={"raw":msg.data}
        print("IC_CMD_RECV %s"%cmd, flush=True); globals()["_IC_Q"].append(cmd)
    globals()["_IC_CMDSUB"]=node.create_subscription(String,"/ic/command",on_cmd,10)
result_pub=globals()["_IC_RESULT"]; state_pub=globals()["_IC_STATE"]; Q=globals()["_IC_Q"]
S={"n":0}
def _step(dt):
    try:
        rclpy.spin_once(node, timeout_sec=0.0)
        while Q:
            cmd=Q.pop(0)
            res={"ack":cmd,"success":True,"note":"channel-proof"}
            result_pub.publish(String(data=json.dumps(res))); print("IC_RESULT_PUB %s"%res, flush=True)
        S["n"]+=1
        if S["n"]%120==0:
            state_pub.publish(String(data=json.dumps({"alive":True,"tick":S["n"],
                "endpoints":["franka_left","franka_right","mobilebot"]})))
    except Exception:
        print("IC_NODE_ERR:\n"+traceback.format_exc(), flush=True)
omni.timeline.get_timeline_interface().play()
_IC_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("IC_NODE_STARTED", flush=True)
