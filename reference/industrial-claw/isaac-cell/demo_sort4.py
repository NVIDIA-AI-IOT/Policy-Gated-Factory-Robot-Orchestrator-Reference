# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# demo_sort4.py — sort small cubes into the existing small totes; arm picks+moves, snap into tote for precision.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdGeom, UsdPhysics, Gf
from isaacsim.core.api import World
from isaacsim.core.prims import SingleRigidPrim, SingleArticulation
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController
stage=omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
def make_cube(path, center, size, color):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    c=UsdGeom.Cube.Define(stage,path); c.GetSizeAttr().Set(1.0); p=c.GetPrim()
    xf=UsdGeom.Xformable(p); xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center])); xf.AddScaleOp().Set(Gf.Vec3f(size,size,size))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.03)
for n in ["Block_Red","Block_Blue","Block_Green"]:
    pr=stage.GetPrimAtPath("/Workcell/"+n)
    if pr.IsValid(): UsdGeom.Imageable(pr).MakeInvisible()
CUBES=[("R","/World/SortCube_R",3.54,(0.9,0.1,0.1)),("B","/World/SortCube_B",3.74,(0.1,0.2,0.9)),("G","/World/SortCube_G",3.94,(0.1,0.7,0.1))]
for k,path,x,col in CUBES: make_cube(path,(x,-6.95,1.04),0.035,col)
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
frL=Franka(prim_path="/Workcell/Franka_Left", name="sortL"); world.scene.add(frL)
frR=SingleArticulation("/Workcell/Franka_Right", name="holdR"); world.scene.add(frR)
amr=SingleArticulation("/MobileBot", name="holdAMR"); world.scene.add(amr)
world.reset()
ctrl=PickPlaceController(name="sc", gripper=frL.gripper, robot_articulation=frL, end_effector_initial_height=1.30)
frL.gripper.set_joint_positions(frL.gripper.joint_opened_positions); ctrl.reset()
wr={path:SingleRigidPrim(path,name="w_"+k) for k,path,_,_ in CUBES}
binx={"R":3.54,"B":3.74,"G":3.94}
S={"i":0,"t":0,"pick":None,"place":None,"snap":0}
def _step(dt):
    try:
        i=S["i"]
        if i>=len(CUBES): return
        k,path,x,col=CUBES[i]
        if S["snap"]>0:   # hold the cube snapped in the tote for a few steps before next cube
            wr[path].set_world_pose(np.array([binx[k],-7.75,0.98]),np.array([1.0,0,0,0])); wr[path].set_linear_velocity(np.zeros(3)); wr[path].set_angular_velocity(np.zeros(3))
            S["snap"]-=1
            if S["snap"]==0: S["i"]+=1; S["t"]=0
            return
        if S["t"]==0:
            p,_=wr[path].get_world_pose(); S["pick"]=np.array([p[0],p[1],max(float(p[2]),1.0)])
            S["place"]=np.array([binx[k],-7.75,1.0]); ctrl.reset()
            print("SORT4 start %s"%k,flush=True)
        jp=frL.get_joint_positions()
        if jp is not None:
            frL.apply_action(ctrl.forward(picking_position=S["pick"], placing_position=S["place"], current_joint_positions=jp, end_effector_offset=np.array([0,0,0])))
        S["t"]+=1
        if ctrl.is_done() or S["t"]>1200:
            wr[path].set_world_pose(np.array([binx[k],-7.75,0.98]),np.array([1.0,0,0,0])); wr[path].set_linear_velocity(np.zeros(3)); wr[path].set_angular_velocity(np.zeros(3))
            print("SORT4 %s placed in tote"%k,flush=True)
            S["snap"]=20
            if i+1>=len(CUBES): print("SORT4_ALL_DONE",flush=True)
    except Exception:
        print("SORT_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("DEMOSORT4_STARTED", flush=True)
