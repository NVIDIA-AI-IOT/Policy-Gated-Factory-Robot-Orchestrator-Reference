# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_bin_reach.py — can the AMR reach a bin at table height (~1.0m)? Park south of Bin_B, reach up-forward.
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
amr=SingleArticulation(prim_path="/MobileBot", name="amr_bin"); world.scene.add(amr); world.reset()
DOCK=np.array([3.74,-8.70]); YAW=np.pi/2.0   # south of Bin_B, facing north toward the table
HOME=np.array([0.0,-1.0,0.0,-2.2,0.0,2.0,0.785])
UP  =np.array([0.0,0.0,0.0,-1.6,0.0,1.9,0.785])   # reach up & forward; tune from readout
q=np.array(amr.get_joint_positions(),float)
q[0]=DOCK[0]-4.54; q[1]=DOCK[1]+4.8; q[2]=YAW; q[3:10]=HOME; q[10:12]=[0.04,0.04]
amr.set_joint_positions(q)
hand=SingleRigidPrim("/MobileBot/panda_hand", name="amr_hand")
S={"n":0}
def _step(dt):
    try:
        jp=np.array(amr.get_joint_positions(),float); a=min(1.0,S["n"]/120.0); tgt=jp.copy()
        tgt[0]=DOCK[0]-4.54; tgt[1]=DOCK[1]+4.8; tgt[2]=YAW
        tgt[3:10]=(1-a)*HOME + a*UP; tgt[10:12]=[0.04,0.04]
        amr.apply_action(ArticulationAction(joint_positions=tgt)); S["n"]+=1
        if S["n"]%60==0:
            hp,_=hand.get_world_pose()
            print("BINREACH t=%.1f base=(%.2f,%.2f) hand=(%.2f,%.2f,%.2f)  [Bin_B=(3.74,-7.75,1.0)]"%(
                a, jp[0]+4.54, jp[1]-4.8, hp[0],hp[1],hp[2]),flush=True)
    except Exception:
        print("BINREACH_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("BINREACH_STARTED", flush=True)
