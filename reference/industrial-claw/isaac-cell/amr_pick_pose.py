# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_pick_pose.py — place AMR at WP5 facing the open floor (yaw=+90deg, toward bins),
# smoothly ramp arm to a forward+down reach with gripper OPEN, report gripper world pos.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation, SingleRigidPrim
from isaacsim.core.utils.types import ArticulationAction
stage=omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
amr=SingleArticulation(prim_path="/MobileBot", name="amr_pick"); world.scene.add(amr); world.reset()

WP5=np.array([3.76,-9.21]); YAW=np.pi/2.0
HOME_ARM=np.array([0.0,-1.0,0.0,-2.2,0.0,2.0,0.785])
REACH_ARM=np.array([0.0,0.55,0.0,-2.0,0.0,2.4,0.785])   # forward + down; tune from readout
GR_OPEN=0.04
# teleport base to WP5 facing north, arm at home (no cross-floor drive)
q=np.array(amr.get_joint_positions(),float)
q[0]=WP5[0]-4.54; q[1]=WP5[1]+4.8; q[2]=YAW
q[3:10]=HOME_ARM; q[10:12]=[GR_OPEN,GR_OPEN]
amr.set_joint_positions(q)
hand=SingleRigidPrim("/MobileBot/panda_hand", name="amr_hand")
S={"n":0}
def _step(dt):
    try:
        jp=np.array(amr.get_joint_positions(),float)
        a=min(1.0, S["n"]/90.0)                       # smooth 1.5s ramp
        tgt=jp.copy()
        tgt[0]=WP5[0]-4.54; tgt[1]=WP5[1]+4.8; tgt[2]=YAW
        tgt[3:10]=(1-a)*HOME_ARM + a*REACH_ARM
        tgt[10:12]=[GR_OPEN,GR_OPEN]
        amr.apply_action(ArticulationAction(joint_positions=tgt)); S["n"]+=1
        if S["n"]%60==0:
            hp,_=hand.get_world_pose()
            print("PICKPOSE t=%.1f base=(%.2f,%.2f,y%.0f) hand=(%.2f,%.2f,%.2f)"%(
                a, jp[0]+4.54, jp[1]-4.8, np.degrees(jp[2]), hp[0],hp[1],hp[2]),flush=True)
    except Exception:
        print("PICKPOSE_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("PICKPOSE_STARTED", flush=True)
