# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_reach_test.py — dock AMR south of BigTote handle, reach down, measure hand vs handle (table now lowered).
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdPhysics, UsdGeom, Usd, Gf
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
omni.timeline.get_timeline_interface().stop()
tp=stage.GetPrimAtPath("/World/BigTote")     # lighten for lifting, keep dynamic
a=UsdPhysics.RigidBodyAPI(tp).GetKinematicEnabledAttr()
if a and a.IsValid(): a.Set(False)
m=UsdPhysics.MassAPI(tp); (m.GetMassAttr() or m.CreateMassAttr()).Set(1.0)
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
amr=SingleArticulation("/MobileBot", name="amrR"); world.scene.add(amr)
frL=SingleArticulation("/Workcell/Franka_Left", name="hL"); world.scene.add(frL)
frR=SingleArticulation("/Workcell/Franka_Right", name="hR"); world.scene.add(frR)
world.reset()
FR_HOME=np.array([0.0,-0.3,0.0,-2.0,0.0,2.0,0.785,0.04,0.04])
frL.set_joint_positions(FR_HOME); frR.set_joint_positions(FR_HOME)
def b2j(w): return w[0]-4.54, w[1]+4.8
DOCK=np.array([4.126,-8.55]); YAW=np.pi/2.0
HOME=np.array([0.0,-1.0,0.0,-2.2,0.0,2.0,0.785]); UP=np.array([0.0,0.0,0.0,-1.6,0.0,1.9,0.785])
q=np.array(amr.get_joint_positions(),float); bj=b2j(DOCK); q[0]=bj[0]; q[1]=bj[1]; q[2]=YAW; q[3:10]=HOME; q[10:12]=[0.04,0.04]
amr.set_joint_positions(q)
hand=SingleRigidPrim("/MobileBot/panda_hand", name="amrhand"); tote=SingleRigidPrim("/World/BigTote", name="toteR")
S={"t":0}
def _step(dt):
    try:
        frL.apply_action(ArticulationAction(joint_positions=FR_HOME)); frR.apply_action(ArticulationAction(joint_positions=FR_HOME))
        t=S["t"]; al=min(1.0,t/200.0); arm=(1-al)*HOME+al*UP
        tgt=np.array(amr.get_joint_positions(),float); bj=b2j(DOCK); tgt[0]=bj[0]; tgt[1]=bj[1]; tgt[2]=YAW; tgt[3:10]=arm; tgt[10:12]=[0.04,0.04]
        amr.apply_action(ArticulationAction(joint_positions=tgt))
        S["t"]+=1
        if t==280:
            hp,_=hand.get_world_pose(); tpos,_=tote.get_world_pose()
            handle=np.array([tpos[0],tpos[1]-0.085,tpos[2]+0.045])
            print("HAND=(%.3f,%.3f,%.3f)  HANDLE=(%.3f,%.3f,%.3f)  d=(%.3f,%.3f,%.3f)"%(hp[0],hp[1],hp[2],handle[0],handle[1],handle[2],hp[0]-handle[0],hp[1]-handle[1],hp[2]-handle[2]),flush=True)
            print("REACH_TEST_DONE",flush=True)
    except Exception:
        print("RT_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("REACH_TEST_STARTED",flush=True)
