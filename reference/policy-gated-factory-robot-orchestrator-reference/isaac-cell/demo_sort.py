# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# demo_sort.py — clean restore (cubes->conveyor, bins->table, un-kinematic) then Franka_Left sorts.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdPhysics, UsdGeom
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
# un-kinematic everything we touched (must be before reset)
for path in ["/World/SortCube_R","/World/SortCube_B","/World/SortCube_G","/Workcell/Bin","/Workcell/Bin_B","/Workcell/Bin_C"]:
    p=stage.GetPrimAtPath(path)
    if p.IsValid():
        a=UsdPhysics.RigidBodyAPI(p).GetKinematicEnabledAttr()
        if a: a.Set(False)
for n in ["Block_Red","Block_Blue","Block_Green"]:
    pr=stage.GetPrimAtPath("/Workcell/"+n)
    if pr.IsValid(): UsdGeom.Imageable(pr).MakeInvisible()
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
fr=Franka(prim_path="/Workcell/Franka_Left", name="sortarm"); world.scene.add(fr); world.reset()
ctrl=PickPlaceController(name="sc", gripper=fr.gripper, robot_articulation=fr, end_effector_initial_height=1.30)
fr.gripper.set_joint_positions(fr.gripper.joint_opened_positions); ctrl.reset()
# restore positions
CUBES=[("R","/World/SortCube_R",(3.54,-6.95,1.05),(3.54,-7.72)),
       ("B","/World/SortCube_B",(3.74,-6.95,1.05),(3.74,-7.72)),
       ("G","/World/SortCube_G",(3.94,-6.95,1.05),(3.94,-7.72))]
wr={path:SingleRigidPrim(path, name="w_"+k) for k,path,_,_ in CUBES}
binB=SingleRigidPrim("/Workcell/Bin_B", name="binB")
for k,path,pos,bn in CUBES:
    wr[path].set_world_pose(np.array(pos), np.array([1.0,0,0,0])); wr[path].set_linear_velocity(np.zeros(3)); wr[path].set_angular_velocity(np.zeros(3))
binB.set_world_pose(np.array([3.74,-7.75,1.00]), np.array([1.0,0,0,0]))
print("RESTORED cubes->conveyor, BinB->table", flush=True)
S={"i":0,"t":0,"pick":None,"place":None}
def _step(dt):
    try:
        i=S["i"]
        if i>=len(CUBES): return
        k,path,pos,bn=CUBES[i]
        if S["t"]==0:
            p,_=wr[path].get_world_pose(); S["pick"]=np.array([p[0],p[1],max(float(p[2]),1.03)])
            S["place"]=np.array([bn[0],bn[1],1.02]); ctrl.reset()
            print("SORT start %s pick=(%.2f,%.2f,%.2f)"%(k,S["pick"][0],S["pick"][1],S["pick"][2]),flush=True)
        jp=fr.get_joint_positions()
        if jp is not None:
            fr.apply_action(ctrl.forward(picking_position=S["pick"], placing_position=S["place"], current_joint_positions=jp, end_effector_offset=np.array([0,0,0])))
        S["t"]+=1
        if ctrl.is_done() or S["t"]>1500:
            fp,_=wr[path].get_world_pose()
            print("SORT %s done final=(%.2f,%.2f,%.2f)"%(k, fp[0],fp[1],fp[2]),flush=True)
            S["i"]+=1; S["t"]=0
            if S["i"]>=len(CUBES): print("SORT_ALL_DONE", flush=True)
    except Exception:
        print("SORT_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("DEMOSORT_STARTED", flush=True)
