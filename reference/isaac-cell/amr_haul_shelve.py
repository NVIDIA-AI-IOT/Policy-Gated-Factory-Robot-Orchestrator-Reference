# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_haul_shelve.py (v3) — gated state machine.
# pick (south, gripper closes + box locks to hand) -> lift & turn to face rack ->
# haul (GATED waypoints: west fully, then north) -> place over rack -> release on Shelf_1 -> retract.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdGeom, UsdPhysics, Gf
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation, SingleRigidPrim
from isaacsim.core.utils.types import ArticulationAction
stage=omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
def make_box(path, center, scale, color, dynamic, mass=0.2):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    cube=UsdGeom.Cube.Define(stage, path); cube.GetSizeAttr().Set(1.0); p=cube.GetPrim()
    xf=UsdGeom.Xformable(p); xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center]))
    xf.AddScaleOp().Set(Gf.Vec3f(*[float(v) for v in scale]))
    cube.GetDisplayColorAttr().Set([Gf.Vec3f(*[float(c) for c in color])])
    UsdPhysics.CollisionAPI.Apply(p)
    if dynamic:
        UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(mass)
    return path
def quat_to_R(q):
    w,x,y,z=[float(v) for v in q]
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
def b2j(w): return w[0]-4.54, w[1]+4.8
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
amr=SingleArticulation(prim_path="/MobileBot", name="amr_pick"); world.scene.add(amr)
YAW_PICK=-np.pi/2.0; YAW_HAUL=np.pi
WP5=np.array([3.76,-9.21])
WPS=[np.array([1.74,-9.21]), np.array([1.74,-7.84]), np.array([0.62,-7.40])]
REACH=np.array([0.0,0.55,0.0,-2.0,0.0,2.4,0.785])
LIFT =np.array([0.0,0.10,0.0,-1.7,0.0,2.0,0.785])
PLACE=np.array([0.0,0.35,0.0,-1.95,0.0,2.25,0.785])
GRASP=np.array([3.76,-10.09,0.40]); BOXSZ=0.06; ct=GRASP[2]-BOXSZ/2.0
SHELF=np.array([-0.26,-7.40,0.51])
make_box("/World/HaulCrate", [GRASP[0],GRASP[1],ct/2.0], [0.20,0.20,ct], [0.35,0.27,0.18], False)
make_box("/World/HaulBox", GRASP, [BOXSZ,BOXSZ,BOXSZ], [0.90,0.12,0.10], True)
world.reset()
q=np.array(amr.get_joint_positions(),float)
bj=b2j(WP5); q[0]=bj[0]; q[1]=bj[1]; q[2]=YAW_PICK; q[3:10]=REACH; q[10:12]=[0.04,0.04]
amr.set_joint_positions(q)
box=SingleRigidPrim("/World/HaulBox", name="hb"); hand=SingleRigidPrim("/MobileBot/panda_hand", name="amr_hand")
S={"st":"pick","t":0,"wp":0,"off":None,"yaw":YAW_PICK}
def setp(name): S["st"]=name; S["t"]=0
def _step(dt):
    try:
        t=S["t"]; st=S["st"]; jp=np.array(amr.get_joint_positions(),float)
        ax,ay=jp[0]+4.54, jp[1]-4.8
        base=WP5.copy(); arm=LIFT.copy(); grip=0.03; yaw=S["yaw"]; follow=False
        if st=="pick":
            base=WP5; arm=REACH; yaw=YAW_PICK; grip=0.04 if t<90 else 0.03; follow=(t>=90)
            if t>=180: setp("turn")
        elif st=="turn":
            a=min(1.0,t/180.0); base=WP5; arm=(1-a)*REACH+a*LIFT
            yaw=YAW_PICK+(YAW_HAUL-YAW_PICK)*a; grip=0.03; follow=True; S["yaw"]=yaw
            if t>=180: S["yaw"]=YAW_HAUL; setp("haul")
        elif st=="haul":
            yaw=YAW_HAUL; arm=LIFT; grip=0.03; follow=True
            goal=WPS[S["wp"]]; base=goal
            d=((ax-goal[0])**2+(ay-goal[1])**2)**0.5
            last=(S["wp"]==len(WPS)-1)
            tol=0.35 if last else 0.25
            if d<tol:
                if not last: S["wp"]+=1
                else: setp("place")
            if t>1200: print("HS WARN haul timeout wp%d d=%.2f"%(S["wp"],d),flush=True); setp("place")
        elif st=="place":
            a=min(1.0,t/150.0); base=WPS[-1]; arm=(1-a)*LIFT+a*PLACE; yaw=YAW_HAUL; grip=0.03; follow=True
            if t>=150: setp("release")
        elif st=="release":
            base=WPS[-1]; arm=PLACE; yaw=YAW_HAUL; grip=0.03; follow=False
            if t==0:
                box.set_world_pose(SHELF, np.array([1.0,0,0,0])); box.set_linear_velocity(np.zeros(3)); box.set_angular_velocity(np.zeros(3))
            if t>=90: setp("retract")
        elif st=="retract":
            a=min(1.0,t/150.0); base=WPS[-1]; arm=(1-a)*PLACE+a*LIFT; yaw=YAW_HAUL; grip=0.04; follow=False
            if t>=150: setp("done")
        else:
            base=WPS[-1]; arm=LIFT; yaw=YAW_HAUL; grip=0.04; follow=False
        tgt=jp.copy(); bj=b2j(base); tgt[0]=bj[0]; tgt[1]=bj[1]; tgt[2]=yaw; tgt[3:10]=arm; tgt[10:12]=[grip,grip]
        amr.apply_action(ArticulationAction(joint_positions=tgt))
        hp,hq=hand.get_world_pose()
        if st=="pick" and t==90:
            bp,_=box.get_world_pose(); S["off"]=quat_to_R(hq).T @ (np.array(bp)-np.array(hp))
        if follow and S["off"] is not None:
            wp=np.array(hp)+quat_to_R(hq)@S["off"]
            box.set_world_pose(wp, np.array(hq)); box.set_linear_velocity(np.zeros(3)); box.set_angular_velocity(np.zeros(3))
        S["t"]+=1
        if t%30==0:
            bp,_=box.get_world_pose()
            print("HS %-8s t=%d wp=%d base=(%.2f,%.2f) hand=(%.2f,%.2f,%.2f) box=(%.2f,%.2f,%.2f)"%(
                st,t,S["wp"], ax,ay, hp[0],hp[1],hp[2], bp[0],bp[1],bp[2]),flush=True)
    except Exception:
        print("HS_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("HS_STARTED", flush=True)
