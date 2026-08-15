# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_attach_test.py — box kinematically follows the end-effector (no gripper).
# Hand pose derived from base joints + fixed arm offset; no link-wrapping (that blew up the solver).
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from isaacsim.core.api import World
from isaacsim.core.api.objects import DynamicCuboid
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.types import ArticulationAction
stage=omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
amr=SingleArticulation(prim_path="/MobileBot", name="amr_pick"); world.scene.add(amr)
if stage.GetPrimAtPath("/World/HaulBox").IsValid(): stage.RemovePrim("/World/HaulBox")
box=DynamicCuboid(prim_path="/World/HaulBox", name="haulbox",
                  position=np.array([4.69,-9.21,0.66]), size=0.12, color=np.array([0.9,0.55,0.1]))
world.scene.add(box); world.reset()
OFF=np.array([0.93,0.0]); HZ=0.66; ARM=[0.0,0.3,0.0,-1.8,0.0,2.1,0.785]
def hand(jp):
    bx=jp[0]+4.54; by=jp[1]-4.8; yaw=jp[2]
    return bx,by,yaw, bx+OFF[0]*np.cos(yaw)-OFF[1]*np.sin(yaw), by+OFF[0]*np.sin(yaw)+OFF[1]*np.cos(yaw)
S={"n":0}
def wgoal(n):  # hold WP5 ~4s then drive to (1.74,-9.21) to test following
    return np.array([3.76,-9.21]) if n<240 else np.array([1.74,-9.21])
def _step(dt):
    try:
        jp=np.array(amr.get_joint_positions(),float)
        w=wgoal(S["n"]); tgt=jp.copy()
        tgt[0]=w[0]-4.54; tgt[1]=w[1]+4.8; tgt[2]=0.0; tgt[3:10]=ARM; tgt[10:12]=[0.04,0.04]
        amr.apply_action(ArticulationAction(joint_positions=tgt))
        bx,by,yaw,hx,hy=hand(jp)
        box.set_world_pose(np.array([hx,hy,HZ])); box.set_linear_velocity(np.zeros(3)); box.set_angular_velocity(np.zeros(3))
        S["n"]+=1
        if S["n"]%120==0:
            bp,_=box.get_world_pose()
            print("ATT base=(%.2f,%.2f,y%.2f) box=(%.2f,%.2f,%.2f)"%(bx,by,yaw,bp[0],bp[1],bp[2]),flush=True)
    except Exception:
        print("ATT_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("ATT_STARTED", flush=True)
