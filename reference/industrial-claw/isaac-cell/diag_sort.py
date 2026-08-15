# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# diag_sort.py — sort WITHOUT snap; log where the arm actually places each cube vs its tote + reach.
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
CUBES=[("R","/World/SortCube_R",3.54,(0.9,0.1,0.1)),("B","/World/SortCube_B",3.74,(0.1,0.2,0.9)),("G","/World/SortCube_G",3.94,(0.1,0.7,0.1))]
for k,path,x,col in CUBES: make_cube(path,(x,-6.95,1.04),0.035,col)
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
frL=Franka(prim_path="/Workcell/Franka_Left", name="sortL"); world.scene.add(frL)
world.reset()
ctrl=PickPlaceController(name="sc", gripper=frL.gripper, robot_articulation=frL, end_effector_initial_height=1.30)
frL.gripper.set_joint_positions(frL.gripper.joint_opened_positions); ctrl.reset()
base=SingleRigidPrim("/Workcell/Franka_Left/panda_link0", name="base"); bp,_=base.get_world_pose()
totes={k:SingleRigidPrim("/World/Tote_"+k, name="tt_"+k) for k in ["R","B","G"]}
for k in totes:
    tp,_=totes[k].get_world_pose()
    print("TOTE %s at (%.2f,%.2f,%.2f) dist_from_base=%.2f"%(k,tp[0],tp[1],tp[2], ((bp[0]-tp[0])**2+(bp[1]-tp[1])**2)**.5), flush=True)
wr={path:SingleRigidPrim(path,name="w_"+k) for k,path,_,_ in CUBES}
binx={"R":3.54,"B":3.74,"G":3.94}
S={"i":0,"t":0,"pick":None,"place":None}
def _step(dt):
    try:
        i=S["i"]
        if i>=len(CUBES): return
        k,path,x,col=CUBES[i]
        if S["t"]==0:
            p,_=wr[path].get_world_pose(); S["pick"]=np.array([p[0],p[1],max(float(p[2]),1.0)])
            S["place"]=np.array([binx[k],-7.75,1.0]); ctrl.reset()
        jp=frL.get_joint_positions()
        if jp is not None:
            frL.apply_action(ctrl.forward(picking_position=S["pick"], placing_position=S["place"], current_joint_positions=jp, end_effector_offset=np.array([0,0,0])))
        S["t"]+=1
        if ctrl.is_done() or S["t"]>1400:
            fp,_=wr[path].get_world_pose(); tp,_=totes[k].get_world_pose()
            d=((fp[0]-tp[0])**2+(fp[1]-tp[1])**2)**.5
            print("DIAG %s: cube_final=(%.2f,%.2f,%.2f) tote=(%.2f,%.2f,%.2f) miss=%.3f done=%s"%(k,fp[0],fp[1],fp[2],tp[0],tp[1],tp[2],d, ctrl.is_done()), flush=True)
            S["i"]+=1; S["t"]=0
            if S["i"]>=len(CUBES): print("DIAG_DONE",flush=True)
    except Exception:
        print("DIAG_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("DIAG_STARTED base=(%.2f,%.2f,%.2f)"%(bp[0],bp[1],bp[2]), flush=True)
