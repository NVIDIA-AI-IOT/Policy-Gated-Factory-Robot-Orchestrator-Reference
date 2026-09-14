# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# table_sort.py (v3) — reuse existing SortCubes (no prim create/delete). Franka_Left sorts them into bins.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from isaacsim.core.api import World
from isaacsim.core.prims import SingleRigidPrim
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController
stage=omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
fr=Franka(prim_path="/Workcell/Franka_Left", name="sortarm"); world.scene.add(fr); world.reset()
ctrl=PickPlaceController(name="sc", gripper=fr.gripper, robot_articulation=fr, end_effector_initial_height=1.30)
fr.gripper.set_joint_positions(fr.gripper.joint_opened_positions); ctrl.reset()
CUBES=[("R","/World/SortCube_R",(3.54,-7.72)),
       ("B","/World/SortCube_B",(3.74,-7.72)),
       ("G","/World/SortCube_G",(3.94,-7.72))]
wr={path:SingleRigidPrim(path, name="w_"+k) for k,path,_ in CUBES}
S={"i":0,"t":0,"pick":None,"place":None}
def _step(dt):
    try:
        i=S["i"]
        if i>=len(CUBES): return
        k,path,bn=CUBES[i]
        if S["t"]==0:
            p,_=wr[path].get_world_pose(); S["pick"]=np.array([p[0],p[1],max(float(p[2]),1.03)])
            S["place"]=np.array([bn[0],bn[1],1.02]); ctrl.reset()
            print("SORT start %s pick=(%.2f,%.2f,%.2f) place=(%.2f,%.2f)"%(k,S["pick"][0],S["pick"][1],S["pick"][2],bn[0],bn[1]),flush=True)
        jp=fr.get_joint_positions()
        if jp is not None:
            act=ctrl.forward(picking_position=S["pick"], placing_position=S["place"], current_joint_positions=jp, end_effector_offset=np.array([0,0,0]))
            fr.apply_action(act)
        S["t"]+=1
        if ctrl.is_done() or S["t"]>1500:
            fp,_=wr[path].get_world_pose()
            print("SORT %s DONE(%s) final=(%.2f,%.2f,%.2f)"%(k,"ok" if ctrl.is_done() else "TIMEOUT", fp[0],fp[1],fp[2]),flush=True)
            S["i"]+=1; S["t"]=0
            if S["i"]>=len(CUBES): print("SORT_ALL_DONE", flush=True)
    except Exception:
        print("SORT_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("SORTv3_STARTED", flush=True)
