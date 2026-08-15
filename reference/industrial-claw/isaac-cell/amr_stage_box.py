# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_stage_box.py — hold AMR south-reach pose; stage a graspable box on a low crate at the
# gripper grasp point, gripper OPEN. (Verify alignment via screenshot before closing.)
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from isaacsim.core.api import World
from isaacsim.core.api.objects import DynamicCuboid, FixedCuboid
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
amr=SingleArticulation(prim_path="/MobileBot", name="amr_pick"); world.scene.add(amr)
WP5=np.array([3.76,-9.21]); YAW=-np.pi/2.0
REACH=np.array([0.0,0.55,0.0,-2.0,0.0,2.4,0.785])
GRASP=np.array([3.76,-10.09,0.40]); BOXSZ=0.06
for p in ("/World/HaulBox","/World/HaulCrate"):
    if stage.GetPrimAtPath(p).IsValid(): stage.RemovePrim(p)
crate_top=GRASP[2]-BOXSZ/2.0
world.scene.add(FixedCuboid(prim_path="/World/HaulCrate", name="haulcrate",
    position=np.array([GRASP[0],GRASP[1],crate_top/2.0]), scale=np.array([0.20,0.20,crate_top]),
    color=np.array([0.35,0.27,0.18])))
box=DynamicCuboid(prim_path="/World/HaulBox", name="haulbox", position=GRASP, size=BOXSZ,
    color=np.array([0.85,0.15,0.12]))
world.scene.add(box)
q=np.array(amr.get_joint_positions(),float)
q[0]=WP5[0]-4.54; q[1]=WP5[1]+4.8; q[2]=YAW; q[3:10]=REACH; q[10:12]=[0.04,0.04]
amr.set_joint_positions(q); world.reset()
hand=SingleRigidPrim("/MobileBot/panda_hand", name="amr_hand")
def _step(dt):
    try:
        jp=np.array(amr.get_joint_positions(),float); tgt=jp.copy()
        tgt[0]=WP5[0]-4.54; tgt[1]=WP5[1]+4.8; tgt[2]=YAW; tgt[3:10]=REACH; tgt[10:12]=[0.04,0.04]
        amr.apply_action(ArticulationAction(joint_positions=tgt))
    except Exception:
        print("STAGE_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
hp,_=hand.get_world_pose()
print("STAGED hand=(%.2f,%.2f,%.2f) box@%s"%(hp[0],hp[1],hp[2], GRASP.tolist()), flush=True)
