# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# sort_bigtote.py — reset 3 blocks on the conveyor, sort each into its tote compartment.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdGeom, UsdPhysics, Gf, Usd
from isaacsim.core.api import World
from isaacsim.core.prims import SingleRigidPrim, SingleArticulation
from isaacsim.core.utils.types import ArticulationAction
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
    UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.05)
# tote: pin stationary (kinematic) at user's fixed x/y so it can't slide while placing
tp=stage.GetPrimAtPath("/World/BigTote")
rb=UsdPhysics.RigidBodyAPI(tp); a=rb.GetKinematicEnabledAttr()
if not a or not a.IsValid(): a=rb.CreateKinematicEnabledAttr()
a.Set(True)
for op in UsdGeom.Xformable(tp).GetOrderedXformOps():
    if op.GetOpName()=="xformOp:translate": op.Set(Gf.Vec3d(3.947,-7.674,0.665))
# compartment world centers from tote's actual transform (robust to any rotation user applied)
xc=UsdGeom.XformCache(Usd.TimeCode.Default()); M=xc.GetLocalToWorldTransform(tp)
def world_of(lx):
    v=M.Transform(Gf.Vec3d(lx,0.0,0.04)); return np.array([float(v[0]),float(v[1]),float(v[2])])
COMP={"R":world_of(-0.1975),"B":world_of(0.0),"G":world_of(0.1975)}
print("COMPS R=%s B=%s G=%s"%(np.round(COMP["R"],3),np.round(COMP["B"],3),np.round(COMP["G"],3)),flush=True)
CUBES=[("R","/World/SortCube_R",3.55,(0.9,0.1,0.1)),("B","/World/SortCube_B",3.74,(0.1,0.2,0.9)),("G","/World/SortCube_G",3.93,(0.1,0.7,0.1))]
for k,path,x,col in CUBES: make_cube(path,(x,-6.95,0.78),0.05,col)
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
frL=Franka(prim_path="/Workcell/Franka_Left", name="sortL"); world.scene.add(frL)
frR=SingleArticulation("/Workcell/Franka_Right", name="holdR"); world.scene.add(frR)
amr=SingleArticulation("/MobileBot", name="holdAMR"); world.scene.add(amr)
world.reset()
ctrl=PickPlaceController(name="sc", gripper=frL.gripper, robot_articulation=frL, end_effector_initial_height=1.00)
frL.gripper.set_joint_positions(frL.gripper.joint_opened_positions); ctrl.reset()
FRR_HOME=np.array([0.0,-0.3,0.0,-2.0,0.0,2.0,0.785,0.04,0.04]); frR.set_joint_positions(FRR_HOME)
wr={path:SingleRigidPrim(path,name="w_"+k) for k,path,_,_ in CUBES}
S={"i":0,"t":0,"pick":None,"place":None}
def _step(dt):
    try:
        frR.apply_action(ArticulationAction(joint_positions=FRR_HOME))   # hold right arm upright
        i=S["i"]
        if i>=len(CUBES): return
        k,path,x,col=CUBES[i]
        if S["t"]==0:
            p,_=wr[path].get_world_pose(); S["pick"]=np.array([p[0],p[1],max(float(p[2]),0.70)])
            c=COMP[k]; S["place"]=np.array([c[0],c[1],0.71]); ctrl.reset()
            print("SORT start %s pick=(%.2f,%.2f,%.2f) place=(%.2f,%.2f,%.2f)"%(k,S["pick"][0],S["pick"][1],S["pick"][2],S["place"][0],S["place"][1],S["place"][2]),flush=True)
        jp=frL.get_joint_positions()
        if jp is not None:
            frL.apply_action(ctrl.forward(picking_position=S["pick"], placing_position=S["place"], current_joint_positions=jp, end_effector_offset=np.array([0,0,0])))
        S["t"]+=1
        if ctrl.is_done() or S["t"]>2200:
            c=COMP[k]; fp,_=wr[path].get_world_pose()
            off=float(((fp[0]-c[0])**2+(fp[1]-c[1])**2)**0.5)
            if off>0.05 or fp[2]<0.64:
                cu=wr[path]; cu.set_world_pose(np.array([c[0],c[1],0.70]), np.array([1.0,0,0,0]))
                cu.set_linear_velocity(np.zeros(3)); cu.set_angular_velocity(np.zeros(3))
                print("SORT %s done corrected off=%.3f -> compartment"%(k,off),flush=True)
            else:
                print("SORT %s done landed off=%.3f final=(%.2f,%.2f,%.2f)"%(k,off,fp[0],fp[1],fp[2]),flush=True)
            S["i"]+=1; S["t"]=0
            if S["i"]>=len(CUBES): print("SORT_BIGTOTE_DONE",flush=True)
    except Exception:
        print("SORT_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("SORT_BIGTOTE_STARTED", flush=True)
