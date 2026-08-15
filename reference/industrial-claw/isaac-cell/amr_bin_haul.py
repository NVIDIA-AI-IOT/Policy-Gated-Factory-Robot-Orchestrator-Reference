# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_bin_haul.py (v3) — AMR hauls a grippable TOTE (Tote_B + its cube) to the rack.
# gripper actually CLOSES on the ~6cm tote (real-looking grip), dynamic lock + slow speed keep it solid.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdPhysics
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation, SingleRigidPrim
from isaacsim.core.utils.types import ArticulationAction
stage=omni.usd.get_context().get_stage()
try: omni.usd.get_context().get_selection().clear_selected_prim_paths()   # stop GUI manipulator error spam
except Exception: pass
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
def quat_to_R(q):
    w,x,y,z=[float(v) for v in q]
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
def b2j(w): return w[0]-4.54, w[1]+4.8
TOTE="/World/Tote_B"; CUBE="/World/SortCube_B"
for path in [TOTE,CUBE]:
    p=stage.GetPrimAtPath(path)
    if p.IsValid():
        a=UsdPhysics.RigidBodyAPI(p).GetKinematicEnabledAttr()
        if a: a.Set(False)
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
amr=SingleArticulation(prim_path="/MobileBot", name="amr_bin"); world.scene.add(amr)
frL=SingleArticulation(prim_path="/Workcell/Franka_Left", name="holdL"); world.scene.add(frL)
frR=SingleArticulation(prim_path="/Workcell/Franka_Right", name="holdR"); world.scene.add(frR)
world.reset()
FR_HOME=np.array([0.0,-0.3,0.0,-2.0,0.0,2.0,0.785,0.04,0.04])   # upright pose so the table arms stay visible
frL.set_joint_positions(FR_HOME); frR.set_joint_positions(FR_HOME)
DOCK=np.array([3.74,-8.70]); YAW_DOCK=np.pi/2.0; YAW_RACK=np.pi
HOME=np.array([0.0,-1.0,0.0,-2.2,0.0,2.0,0.785])
UP  =np.array([0.0,0.0,0.0,-1.6,0.0,1.9,0.785])
PLACE=np.array([0.0,0.35,0.0,-1.95,0.0,2.25,0.785])
HAUL_WPS=[np.array([1.74,-8.70]),np.array([1.74,-7.84]),np.array([0.62,-7.40])]
GR_OPEN=0.04; GR_GRIP=0.028
binp=SingleRigidPrim(TOTE, name="toteB"); cube=SingleRigidPrim(CUBE, name="cubeB")
binp.set_world_pose(np.array([3.74,-7.75,0.955]), np.array([1.0,0,0,0])); binp.set_linear_velocity(np.zeros(3)); binp.set_angular_velocity(np.zeros(3))
cube.set_world_pose(np.array([3.74,-7.75,0.98]), np.array([1.0,0,0,0])); cube.set_linear_velocity(np.zeros(3)); cube.set_angular_velocity(np.zeros(3))
q=np.array(amr.get_joint_positions(),float)
bj=b2j(DOCK); q[0]=bj[0]; q[1]=bj[1]; q[2]=YAW_DOCK; q[3:10]=HOME; q[10:12]=[GR_OPEN,GR_OPEN]
amr.set_joint_positions(q)
hand=SingleRigidPrim("/MobileBot/panda_hand", name="amr_hand")
S={"st":"reach","t":0,"wp":0,"wpt":0,"boff":None,"coff":None,"yaw":YAW_DOCK,"cbase":DOCK.copy()}
MAX_STEP=0.010
def setp(n): S["st"]=n; S["t"]=0; S["wp"]=0; S["wpt"]=0
def lockcap(hp,hq):
    R=quat_to_R(hq).T
    bp,_=binp.get_world_pose(); cp,_=cube.get_world_pose()
    S["boff"]=R@(np.array(bp)-np.array(hp)); S["coff"]=R@(np.array(cp)-np.array(hp))
def follow(hp,hq):
    R=quat_to_R(hq)
    binp.set_world_pose(np.array(hp)+R@S["boff"], np.array(hq)); binp.set_linear_velocity(np.zeros(3)); binp.set_angular_velocity(np.zeros(3))
    cube.set_world_pose(np.array(hp)+R@S["coff"], np.array(hq)); cube.set_linear_velocity(np.zeros(3)); cube.set_angular_velocity(np.zeros(3))
def gated(ax,ay):
    g=HAUL_WPS[S["wp"]]; d=((ax-g[0])**2+(ay-g[1])**2)**0.5; last=(S["wp"]==len(HAUL_WPS)-1); S["wpt"]+=1
    if d<(0.40 if last else 0.30) or S["wpt"]>1500:
        if not last: S["wp"]+=1; S["wpt"]=0
        else: return g,True
    return g,False
def _step(dt):
    try:
        t=S["t"]; st=S["st"]; jp=np.array(amr.get_joint_positions(),float); ax,ay=jp[0]+4.54,jp[1]-4.8
        base=DOCK.copy(); arm=HOME.copy(); yaw=S["yaw"]; fol=(S["boff"] is not None)
        if st=="reach":
            a=min(1.0,t/120.0); base=DOCK; yaw=YAW_DOCK; arm=(1-a)*HOME+a*UP
            if t>=150: setp("tuck")
        elif st=="tuck":
            a=min(1.0,t/120.0); base=DOCK; yaw=YAW_DOCK; arm=(1-a)*UP+a*HOME
            if t>=120: setp("turn")
        elif st=="turn":
            a=min(1.0,t/240.0); base=DOCK; yaw=YAW_DOCK+(YAW_RACK-YAW_DOCK)*a; arm=HOME; S["yaw"]=yaw
            if t>=240: S["yaw"]=YAW_RACK; setp("haul")
        elif st=="haul":
            yaw=YAW_RACK; arm=HOME; base,done=gated(ax,ay)
            if done: setp("place")
        elif st=="place":
            a=min(1.0,t/150.0); base=HAUL_WPS[-1]; yaw=YAW_RACK; arm=(1-a)*HOME+a*PLACE
            if t>=180: setp("release")
        elif st=="release":
            base=HAUL_WPS[-1]; yaw=YAW_RACK; arm=PLACE; fol=False
            if t>=120: setp("retract")
        elif st=="retract":
            a=min(1.0,t/150.0); base=HAUL_WPS[-1]; yaw=YAW_RACK; arm=(1-a)*PLACE+a*HOME; fol=False
            if t>=150: setp("done")
        else:
            base=HAUL_WPS[-1]; yaw=YAW_RACK; arm=HOME; fol=False
        grabbed=(S["boff"] is not None)
        grip = GR_GRIP if (grabbed and st in ("tuck","turn","haul","place")) else GR_OPEN
        d=base-S["cbase"]; dn=float(np.linalg.norm(d))
        S["cbase"]=(S["cbase"]+d/dn*MAX_STEP) if dn>MAX_STEP else base.copy()
        tgt=jp.copy(); bj=b2j(S["cbase"]); tgt[0]=bj[0]; tgt[1]=bj[1]; tgt[2]=yaw; tgt[3:10]=arm; tgt[10:12]=[grip,grip]
        amr.apply_action(ArticulationAction(joint_positions=tgt))
        frL.apply_action(ArticulationAction(joint_positions=FR_HOME))   # hold table arms upright
        frR.apply_action(ArticulationAction(joint_positions=FR_HOME))
        hp,hq=hand.get_world_pose()
        if st=="reach" and t==140: lockcap(hp,hq)
        if fol and S["boff"] is not None: follow(hp,hq)
        S["t"]+=1
        if t%30==0:
            bp,_=binp.get_world_pose()
            print("BH %-8s t=%d wp=%d base=(%.2f,%.2f) tote=(%.2f,%.2f,%.2f) grip=%.3f"%(
                st,t,S["wp"], ax,ay, bp[0],bp[1],bp[2], jp[10]),flush=True)
    except Exception:
        print("BH_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("BHv3_STARTED", flush=True)
