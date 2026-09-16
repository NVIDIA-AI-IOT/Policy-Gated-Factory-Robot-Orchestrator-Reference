# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdGeom
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation, SingleRigidPrim
stage=omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
for p in ["/Workcell/Franka_Left","/Workcell/Franka_Right"]:
    pr=stage.GetPrimAtPath(p)
    v=UsdGeom.Imageable(pr).ComputeVisibility() if pr.IsValid() else "-"
    print("VIS %s valid=%s visibility=%s"%(p, pr.IsValid(), v), flush=True)
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
frL=SingleArticulation("/Workcell/Franka_Left",name="pL"); world.scene.add(frL)
frR=SingleArticulation("/Workcell/Franka_Right",name="pR"); world.scene.add(frR)
world.reset()
print("L ndof=%s joints=%s"%(frL.num_dof, np.round(np.array(frL.get_joint_positions(),float),2).tolist()), flush=True)
hL=SingleRigidPrim("/Workcell/Franka_Left/panda_hand",name="hpl")
hR=SingleRigidPrim("/Workcell/Franka_Right/panda_hand",name="hpr")
S={"n":0}
def _step(dt):
    try:
        S["n"]+=1
        if S["n"] in (15,150):
            lp=hL.get_world_pose()[0]; rp=hR.get_world_pose()[0]
            print("HANDS n=%d Lhand=(%.2f,%.2f,%.2f) Rhand=(%.2f,%.2f,%.2f)"%(S["n"],lp[0],lp[1],lp[2],rp[0],rp[1],rp[2]), flush=True)
    except Exception as e:
        print("HANDS_ERR",repr(e),flush=True)
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("PANDAPROBE_STARTED", flush=True)
