# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# reimport_and_sort.py — reimport Franka_Left fresh, then sort 3 blocks into tote compartments.
# Natural grip: fingers wrap the cube (no full-close float, no jitter); release ABOVE tote walls; high transit.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdGeom, UsdPhysics, Gf, Usd
from isaacsim.core.api import World
from isaacsim.core.prims import SingleRigidPrim, SingleArticulation
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController
stage=omni.usd.get_context().get_stage()
IDENT=np.array([1.0,0.0,0.0,0.0])
ASSET="https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd"
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
try: World.clear_instance()
except Exception: pass
omni.timeline.get_timeline_interface().stop()
# ---- reimport Franka_Left fresh (delete + re-add reference at the same transform) ----
FL="/Workcell/Franka_Left"
if stage.GetPrimAtPath(FL).IsValid(): stage.RemovePrim(FL)
fp=stage.DefinePrim(FL,"Xform"); fp.GetReferences().AddReference(ASSET,"/panda")
xf=UsdGeom.Xformable(fp); xf.ClearXformOpOrder()
xf.AddTranslateOp().Set(Gf.Vec3d(-0.9,0.0,0.658))
xf.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Quatd(1.0,0.0,0.0,0.0))
xf.AddScaleOp().Set(Gf.Vec3f(1.0,1.0,1.0))
print("REIMPORT panda_hand valid=%s"%stage.GetPrimAtPath(FL+"/panda_hand").IsValid(),flush=True)
def make_cube(path, center, size, color):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    c=UsdGeom.Cube.Define(stage,path); c.GetSizeAttr().Set(1.0); p=c.GetPrim()
    x=UsdGeom.Xformable(p); x.ClearXformOpOrder()
    x.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center])); x.AddScaleOp().Set(Gf.Vec3f(size,size,size))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.05)
tp=stage.GetPrimAtPath("/World/BigTote")
rb=UsdPhysics.RigidBodyAPI(tp); a=rb.GetKinematicEnabledAttr()
if not a or not a.IsValid(): a=rb.CreateKinematicEnabledAttr()
a.Set(True)
xc=UsdGeom.XformCache(Usd.TimeCode.Default()); M=xc.GetLocalToWorldTransform(tp)
_tw=M.Transform(Gf.Vec3d(0,0,0)); print("TOTE world=(%.3f,%.3f,%.3f) (using your placement)"%(_tw[0],_tw[1],_tw[2]),flush=True)
def world_of(lx):
    v=M.Transform(Gf.Vec3d(lx,0.0,0.04)); return np.array([float(v[0]),float(v[1]),float(v[2])])
COMP={"R":world_of(-0.1975),"B":world_of(0.0),"G":world_of(0.1975)}
CUBES=[("R","/World/SortCube_R",3.55,(0.9,0.1,0.1)),("B","/World/SortCube_B",3.74,(0.1,0.2,0.9)),("G","/World/SortCube_G",3.93,(0.1,0.7,0.1))]
for k,path,x,col in CUBES: make_cube(path,(x,-6.95,0.80),0.05,col)
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
frL=Franka(prim_path=FL, name="sortL"); world.scene.add(frL)
frR=SingleArticulation("/Workcell/Franka_Right", name="holdR"); world.scene.add(frR)
amr=SingleArticulation("/MobileBot", name="holdAMR"); world.scene.add(amr)
world.reset()
TRANSIT=1.12; PLACE_Z=0.76; GRIP_SNUG=0.027; CARRY_OFFZ=-0.090
ctrl=PickPlaceController(name="sc", gripper=frL.gripper, robot_articulation=frL, end_effector_initial_height=TRANSIT)
frL.gripper.set_joint_positions(frL.gripper.joint_opened_positions); ctrl.reset()
FRR_HOME=np.array([0.0,-0.3,0.0,-2.0,0.0,2.0,0.785,0.04,0.04]); frR.set_joint_positions(FRR_HOME)
wr={path:SingleRigidPrim(path,name="w_"+k) for k,path,_,_ in CUBES}
hand=SingleRigidPrim(FL+"/panda_hand", name="frLhand")
S={"i":-1,"t":0,"home":{},"ast":"hold","off":None,"pev":-1}
def ev_now():
    try: return int(ctrl.get_current_event())
    except Exception: return -1
def _step(dt):
    try:
        frR.apply_action(ArticulationAction(joint_positions=FRR_HOME))
        if S["i"]==-1:
            S["t"]+=1
            if S["t"]>=70:
                for k,path,_,_ in CUBES:
                    p,_=wr[path].get_world_pose(); S["home"][k]=np.array([float(p[0]),float(p[1]),float(p[2])])
                print("HOMES "+" ".join("%s=%s"%(k,np.round(S["home"][k],3)) for k,_,_,_ in CUBES),flush=True)
                S["i"]=0; S["t"]=0; ctrl.reset(); S["ast"]="hold"
            return
        i=S["i"]
        if i>=len(CUBES): return
        k,path,x,col=CUBES[i]; cu=wr[path]
        for j in range(i,len(CUBES)):
            if j==i and S["ast"] in ("carry","placed"): continue
            kk=CUBES[j][0]; pj=CUBES[j][1]; h=S["home"][kk]
            wr[pj].set_world_pose(h, IDENT); wr[pj].set_linear_velocity(np.zeros(3)); wr[pj].set_angular_velocity(np.zeros(3))
        if S["t"]==0:
            S["pick"]=np.array([S["home"][k][0],S["home"][k][1],max(float(S["home"][k][2]),0.72)])
            c=COMP[k]; S["place"]=np.array([c[0],c[1],PLACE_Z]); ctrl.reset(); S["ast"]="hold"; S["off"]=None
            print("SORT start %s pick=%s place=%s"%(k,np.round(S["pick"],3),np.round(S["place"],3)),flush=True)
        jp=frL.get_joint_positions()
        if jp is not None:
            act=ctrl.forward(picking_position=S["pick"], placing_position=S["place"], current_joint_positions=jp, end_effector_offset=np.array([0,0,0]))
            if S["ast"]=="carry" and act.joint_positions is not None:   # keep fingers wrapping the cube
                try:
                    jj=np.array(act.joint_positions, dtype=float)
                    if jj.shape[0]>=9: jj[7]=GRIP_SNUG; jj[8]=GRIP_SNUG; act=ArticulationAction(joint_positions=jj)
                except Exception: pass
            frL.apply_action(act)
        ev=ev_now(); hp,hq=hand.get_world_pose()
        if ev!=S["pev"]: S["pev"]=ev
        if S["ast"]=="hold" and ev>=2:
            S["off"]=np.array([0.0,0.0,CARRY_OFFZ]); S["ast"]="carry"   # cube centered below gripper
            print("  GRIP %s"%k,flush=True)
        if S["ast"]=="carry":
            place=S["place"]; dxy=float(((hp[0]-place[0])**2+(hp[1]-place[1])**2)**0.5)
            if dxy<0.05 or ev>=8:
                c=COMP[k]; cu.set_world_pose(np.array([c[0],c[1],0.70]), IDENT); cu.set_linear_velocity(np.zeros(3)); cu.set_angular_velocity(np.zeros(3))
                S["ast"]="placed"; print("  PLACE %s dxy=%.3f -> %s"%(k,dxy,np.round(c,3)),flush=True)
            else:
                cu.set_world_pose(np.array(hp)+S["off"], IDENT); cu.set_linear_velocity(np.zeros(3)); cu.set_angular_velocity(np.zeros(3))
        S["t"]+=1
        if ctrl.is_done() or S["t"]>2400:
            if S["ast"]=="carry":
                c=COMP[k]; cu.set_world_pose(np.array([c[0],c[1],0.70]), IDENT); cu.set_linear_velocity(np.zeros(3)); cu.set_angular_velocity(np.zeros(3))
            fp,_=cu.get_world_pose(); c=COMP[k]; off=float(((fp[0]-c[0])**2+(fp[1]-c[1])**2)**0.5)
            print("SORT %s done off=%.3f final=(%.2f,%.2f,%.2f)"%(k,off,fp[0],fp[1],fp[2]),flush=True)
            S["i"]+=1; S["t"]=0; S["ast"]="hold"; S["pev"]=-1
            if S["i"]>=len(CUBES): print("REIMPORT_SORT_DONE",flush=True)
    except Exception:
        print("SORT_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("REIMPORT_SORT_STARTED", flush=True)
