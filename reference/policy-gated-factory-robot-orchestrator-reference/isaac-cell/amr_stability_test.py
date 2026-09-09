# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_stability_test.py — confirm AMR stays planted while driving base+arm (no link wrapping)
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.types import ArticulationAction
stage = omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
amr=SingleArticulation(prim_path="/MobileBot", name="amr_pick"); world.scene.add(amr); world.reset()
P0,Q0=amr.get_world_pose(); P0=np.array(P0,float); Q0=np.array(Q0,float)
print("ROOT_Z0 %.3f"%P0[2], flush=True)
cur=np.array(amr.get_joint_positions(), dtype=float)
ROOTXY=np.array([4.54,-4.8]); WP5=np.array([3.76,-9.21]); base=WP5-ROOTXY
tgt=cur.copy(); tgt[0]=base[0]; tgt[1]=base[1]
tgt[3:10]=[0.0,0.3,0.0,-1.8,0.0,2.1,0.785]; tgt[10:12]=[0.04,0.04]
S={"n":0}
def _step(dt):
    try:
        amr.apply_action(ArticulationAction(joint_positions=tgt)); S["n"]+=1
        if S["n"]%120==0:
            wp,_=amr.get_world_pose()
            print("ROOT_NOW (%.2f,%.2f,%.3f)"%(wp[0],wp[1],wp[2]), flush=True)
    except Exception:
        print("STAB_ERR:\n"+traceback.format_exc(), flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("STAB_STARTED", flush=True)
