# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_grasp_lock.py — gripper closes on box (visible) AND box is locked to the hand frame so it
# rides reliably. Verify box follows the hand through a lift.
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
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
amr=SingleArticulation(prim_path="/MobileBot", name="amr_pick"); world.scene.add(amr)
WP5=np.array([3.76,-9.21]); YAW=-np.pi/2.0
REACH=np.array([0.0,0.55,0.0,-2.0,0.0,2.4,0.785]); LIFT=np.array([0.0,0.10,0.0,-1.7,0.0,2.0,0.785])
GRASP=np.array([3.76,-10.09,0.40]); BOXSZ=0.06; ct=GRASP[2]-BOXSZ/2.0
make_box("/World/HaulCrate", [GRASP[0],GRASP[1],ct/2.0], [0.20,0.20,ct], [0.35,0.27,0.18], False)
make_box("/World/HaulBox", GRASP, [BOXSZ,BOXSZ,BOXSZ], [0.85,0.15,0.12], True)
world.reset()
q=np.array(amr.get_joint_positions(),float)
q[0]=WP5[0]-4.54; q[1]=WP5[1]+4.8; q[2]=YAW; q[3:10]=REACH; q[10:12]=[0.04,0.04]
amr.set_joint_positions(q)
box=SingleRigidPrim("/World/HaulBox", name="hb"); hand=SingleRigidPrim("/MobileBot/panda_hand", name="amr_hand")
S={"n":0,"off":None}
def _step(dt):
    try:
        n=S["n"]; jp=np.array(amr.get_joint_positions(),float); tgt=jp.copy()
        tgt[0]=WP5[0]-4.54; tgt[1]=WP5[1]+4.8; tgt[2]=YAW
        if n<60:    arm=REACH; grip=0.04
        elif n<150: arm=REACH; grip=0.03
        else:       a=min(1.0,(n-150)/150.0); arm=(1-a)*REACH+a*LIFT; grip=0.03
        tgt[3:10]=arm; tgt[10:12]=[grip,grip]
        amr.apply_action(ArticulationAction(joint_positions=tgt))
        hp,hq=hand.get_world_pose()
        if n==60:
            bp,_=box.get_world_pose(); S["off"]=quat_to_R(hq).T @ (np.array(bp)-np.array(hp))
        if n>=60 and S["off"] is not None:
            wp=np.array(hp)+quat_to_R(hq)@S["off"]
            box.set_world_pose(wp, np.array(hq)); box.set_linear_velocity(np.zeros(3)); box.set_angular_velocity(np.zeros(3))
        S["n"]+=1
        if n%30==0:
            bp,_=box.get_world_pose()
            print("GL n=%d grip=%.3f hand_z=%.2f box=(%.2f,%.2f,%.2f)"%(n,jp[10],hp[2],bp[0],bp[1],bp[2]),flush=True)
    except Exception:
        print("GL_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("GL_STARTED", flush=True)
