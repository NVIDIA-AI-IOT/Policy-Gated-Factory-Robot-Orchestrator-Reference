# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_grasp.py — REAL gripper grasp on the AMR. Stage a graspable box at the reach point,
# hold AMR at WP5 with arm down + gripper OPEN. (Phase 1: position & verify before closing.)
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from isaacsim.core.api import World
from isaacsim.core.api.objects import DynamicCuboid, FixedCuboid
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

# --- tunables ---
BOXC = np.array([4.69, -9.21, 0.56])   # grasp center (between fingers); tune from screenshot
BOXSZ = 0.05
PED_TOP = BOXC[2]-BOXSZ/2.0            # pedestal top supports the box
ARM = [0.0,0.3,0.0,-1.8,0.0,2.1,0.785]
WP5 = np.array([3.76,-9.21])
GR_OPEN = 0.04

for p in ("/World/HaulBox","/World/HaulPed"):
    if stage.GetPrimAtPath(p).IsValid(): stage.RemovePrim(p)
world.scene.add(FixedCuboid(prim_path="/World/HaulPed", name="haulped",
    position=np.array([BOXC[0],BOXC[1],PED_TOP/2.0]), scale=np.array([0.18,0.18,PED_TOP]),
    color=np.array([0.3,0.3,0.35])))
box=DynamicCuboid(prim_path="/World/HaulBox", name="haulbox",
    position=BOXC, size=BOXSZ, color=np.array([0.9,0.2,0.15]))
world.scene.add(box); world.reset()
S={"n":0}
def _step(dt):
    try:
        jp=np.array(amr.get_joint_positions(),float); tgt=jp.copy()
        tgt[0]=WP5[0]-4.54; tgt[1]=WP5[1]+4.8; tgt[2]=0.0
        tgt[3:10]=ARM; tgt[10:12]=[GR_OPEN,GR_OPEN]
        amr.apply_action(ArticulationAction(joint_positions=tgt)); S["n"]+=1
        if S["n"]%120==0:
            bp,_=box.get_world_pose()
            print("GRASP1 base=(%.2f,%.2f) box=(%.2f,%.2f,%.2f) fingers=%.3f"%(
                jp[0]+4.54, jp[1]-4.8, bp[0],bp[1],bp[2], jp[10]),flush=True)
    except Exception:
        print("GRASP_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("GRASP1_STARTED", flush=True)
