# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# sort_real2.py — REAL grasp, reliable: heavier blocks (no punt), high friction, release above walls, retry on miss.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdGeom, UsdPhysics, UsdShade, Gf, Usd
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
try: World.clear_instance()
except Exception: pass
omni.timeline.get_timeline_interface().stop()
mp="/World/PhysicsMaterials/Grippy"
mat=UsdShade.Material.Define(stage,mp); pm=UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
pm.CreateStaticFrictionAttr().Set(2.0); pm.CreateDynamicFrictionAttr().Set(1.7); pm.CreateRestitutionAttr().Set(0.0)
def bind(prim):
    if prim and prim.IsValid():
        UsdShade.MaterialBindingAPI.Apply(prim)
        UsdShade.MaterialBindingAPI(prim).Bind(mat, UsdShade.Tokens.weakerThanDescendants, "physics")
for fn in ["panda_leftfinger","panda_rightfinger"]:
    bind(stage.GetPrimAtPath("/Workcell/Franka_Left/"+fn))
tp=stage.GetPrimAtPath("/World/BigTote")
a=UsdPhysics.RigidBodyAPI(tp).GetKinematicEnabledAttr()
if a and a.IsValid(): a.Set(False)
m=UsdPhysics.MassAPI(tp); (m.GetMassAttr() or m.CreateMassAttr()).Set(8.0); bind(tp)
def make_cube(path, center, size, color):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    c=UsdGeom.Cube.Define(stage,path); c.GetSizeAttr().Set(1.0); p=c.GetPrim()
    x=UsdGeom.Xformable(p); x.ClearXformOpOrder()
    x.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center])); x.AddScaleOp().Set(Gf.Vec3f(size,size,size))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.15)
    bind(p)
CUBES=[("R","/World/SortCube_R",3.50,(0.9,0.1,0.1)),("B","/World/SortCube_B",3.72,(0.1,0.2,0.9)),("G","/World/SortCube_G",3.94,(0.1,0.7,0.1))]
for k,path,x,col in CUBES: make_cube(path,(x,-6.95,0.80),0.05,col)
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
frL=Franka(prim_path="/Workcell/Franka_Left", name="sortL"); world.scene.add(frL)
frR=SingleArticulation("/Workcell/Franka_Right", name="holdR"); world.scene.add(frR)
amr=SingleArticulation("/MobileBot", name="holdAMR"); world.scene.add(amr)
world.reset()
TRANSIT=1.12; PLACE_Z=0.77
ctrl=PickPlaceController(name="sc", gripper=frL.gripper, robot_articulation=frL, end_effector_initial_height=TRANSIT)
frL.gripper.set_joint_positions(frL.gripper.joint_opened_positions); ctrl.reset()
FRR_HOME=np.array([0.0,-0.3,0.0,-2.0,0.0,2.0,0.785,0.04,0.04]); frR.set_joint_positions(FRR_HOME)
wr={path:SingleRigidPrim(path,name="w_"+k) for k,path,_,_ in CUBES}
tote=SingleRigidPrim("/World/BigTote", name="toteRP")
S={"i":-1,"t":0,"COMP":None,"pick":None,"place":None,"att":0}
def _step(dt):
    try:
        frR.apply_action(ArticulationAction(joint_positions=FRR_HOME))
        if S["i"]==-1:
            S["t"]+=1
            if S["t"]>=80:
                M=UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(tp)
                def wof(lx):
                    v=M.Transform(Gf.Vec3d(lx,0.0,0.04)); return np.array([float(v[0]),float(v[1]),float(v[2])])
                S["COMP"]={"R":wof(-0.1975),"B":wof(0.0),"G":wof(0.1975)}
                tpos,_=tote.get_world_pose()
                print("READY tote=(%.3f,%.3f,%.3f) comps R/B/G x=%.2f/%.2f/%.2f"%(tpos[0],tpos[1],tpos[2],S["COMP"]["R"][0],S["COMP"]["B"][0],S["COMP"]["G"][0]),flush=True)
                S["i"]=0; S["t"]=0; ctrl.reset()
            return
        i=S["i"]
        if i>=len(CUBES): return
        k,path,x,col=CUBES[i]; cu=wr[path]
        if S["t"]==0:
            p,_=cu.get_world_pose(); S["pick"]=np.array([float(p[0]),float(p[1]),max(float(p[2]),0.72)])
            c=S["COMP"][k]; S["place"]=np.array([c[0],c[1],PLACE_Z]); ctrl.reset()
            print("SORT %s attempt %d pick=%s"%(k,S["att"]+1,np.round(S["pick"],3)),flush=True)
        jp=frL.get_joint_positions()
        if jp is not None:
            frL.apply_action(ctrl.forward(picking_position=S["pick"], placing_position=S["place"], current_joint_positions=jp, end_effector_offset=np.array([0,0,0])))
        S["t"]+=1
        if ctrl.is_done() or S["t"]>1400:
            fp,_=cu.get_world_pose(); c=S["COMP"][k]; off=float(((fp[0]-c[0])**2+(fp[1]-c[1])**2)**0.5)
            ok=off<0.08
            print("SORT %s attempt %d -> off=%.3f final=(%.2f,%.2f,%.2f) %s"%(k,S["att"]+1,off,fp[0],fp[1],fp[2],"IN-SLOT" if ok else "miss"),flush=True)
            if ok or S["att"]>=2:
                if not ok: print("SORT %s GAVE UP after %d"%(k,S["att"]+1),flush=True)
                S["i"]+=1; S["t"]=0; S["att"]=0
                if S["i"]>=len(CUBES): print("SORT_REAL2_DONE",flush=True)
            else:
                S["att"]+=1; S["t"]=0  # retry: re-read live pose next step (warm controller)
    except Exception:
        print("SORT_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("SORT_REAL2_STARTED",flush=True)
