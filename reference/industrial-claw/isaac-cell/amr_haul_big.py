# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_haul_big.py — AMR hauls the loaded BigTote (3 blocks) to the rack. Grip handle, carry level, place on shelf.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation, SingleRigidPrim
from isaacsim.core.utils.types import ArticulationAction
from pxr import UsdPhysics, UsdGeom, Gf
stage=omni.usd.get_context().get_stage()
IDENT=np.array([1.0,0.0,0.0,0.0])
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
def b2j(w): return w[0]-4.54, w[1]+4.8
try: World.clear_instance()
except Exception: pass
TOTE="/World/BigTote"; BLOCKS=["/World/SortCube_R","/World/SortCube_B","/World/SortCube_G"]
tp=stage.GetPrimAtPath(TOTE)
a=UsdPhysics.RigidBodyAPI(tp).GetKinematicEnabledAttr()
if a and a.IsValid(): a.Set(False)
m=UsdPhysics.MassAPI(tp); (m.GetMassAttr() or m.CreateMassAttr()).Set(5.0)   # heavy so the approach doesn't shove it
# thick invisible pad on Shelf_1 so the tote rests (thin shelf tunnels)
PAD="/World/ShelfPad1"
if not stage.GetPrimAtPath(PAD).IsValid():
    c=UsdGeom.Cube.Define(stage,PAD); c.GetSizeAttr().Set(1.0); pdp=c.GetPrim()
    xf=UsdGeom.Xformable(pdp); xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(-0.26,-7.40,0.44)); xf.AddScaleOp().Set(Gf.Vec3f(0.7,1.55,0.07))
    UsdPhysics.CollisionAPI.Apply(pdp); UsdGeom.Imageable(pdp).MakeInvisible()
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
amr=SingleArticulation("/MobileBot", name="amrH"); world.scene.add(amr)
frL=SingleArticulation("/Workcell/Franka_Left", name="hL"); world.scene.add(frL)
frR=SingleArticulation("/Workcell/Franka_Right", name="hR"); world.scene.add(frR)
world.reset()
FR_HOME=np.array([0.0,-0.3,0.0,-2.0,0.0,2.0,0.785,0.04,0.04]); frL.set_joint_positions(FR_HOME); frR.set_joint_positions(FR_HOME)
DOCK=np.array([4.126,-8.667]); YAW_DOCK=np.pi/2.0; YAW_RACK=np.pi
HOME=np.array([0.0,-1.0,0.0,-2.2,0.0,2.0,0.785])
GRAB=np.array([0.0,0.134,0.0,-1.814,0.0,1.980,0.785])
PLACE=np.array([0.0,0.30,0.0,-1.95,0.0,2.20,0.785])
HAUL_WPS=[np.array([1.74,-8.667]),np.array([1.74,-7.84]),np.array([0.62,-7.40])]
SHELF_TOTE=np.array([-0.26,-7.40,0.52]); MAX_STEP=0.010
GR_OPEN=0.04; GR_GRIP=0.016
tote=SingleRigidPrim(TOTE, name="toteH"); blocks=[SingleRigidPrim(b, name="blk"+str(i)) for i,b in enumerate(BLOCKS)]
# reset tote+blocks to a known rested arrangement
TPOS0=np.array([4.126,-7.701,0.665]); COMPX=[-0.1975,0.0,0.1975]
tote.set_world_pose(TPOS0, IDENT); tote.set_linear_velocity(np.zeros(3)); tote.set_angular_velocity(np.zeros(3))
for i,b in enumerate(blocks):
    b.set_world_pose(TPOS0+np.array([COMPX[i],0.0,0.05]), IDENT); b.set_linear_velocity(np.zeros(3)); b.set_angular_velocity(np.zeros(3))
q=np.array(amr.get_joint_positions(),float); bj=b2j(DOCK); q[0]=bj[0]; q[1]=bj[1]; q[2]=YAW_DOCK; q[3:10]=HOME; q[10:12]=[GR_OPEN,GR_OPEN]
amr.set_joint_positions(q)
hand=SingleRigidPrim("/MobileBot/panda_hand", name="amrhand")
S={"st":"reach","t":0,"wp":0,"wpt":0,"toff":None,"boffs":None,"yaw":YAW_DOCK,"cbase":DOCK.copy()}
def setp(n): S["st"]=n; S["t"]=0; S["wp"]=0; S["wpt"]=0
def lockcap(hp):
    tpz,_=tote.get_world_pose(); S["toff"]=np.array(tpz)-np.array(hp)
    S["boffs"]=[]
    for b in blocks:
        bp,_=b.get_world_pose(); S["boffs"].append(np.array(bp)-np.array(hp))
def follow(hp):
    tote.set_world_pose(np.array(hp)+S["toff"], IDENT); tote.set_linear_velocity(np.zeros(3)); tote.set_angular_velocity(np.zeros(3))
    for i,b in enumerate(blocks):
        b.set_world_pose(np.array(hp)+S["boffs"][i], IDENT); b.set_linear_velocity(np.zeros(3)); b.set_angular_velocity(np.zeros(3))
def gated(ax,ay):
    g=HAUL_WPS[S["wp"]]; d=((ax-g[0])**2+(ay-g[1])**2)**0.5; last=(S["wp"]==len(HAUL_WPS)-1); S["wpt"]+=1
    if d<(0.40 if last else 0.30) or S["wpt"]>1800:
        if not last: S["wp"]+=1; S["wpt"]=0
        else: return g,True
    return g,False
def _step(dt):
    try:
        frL.apply_action(ArticulationAction(joint_positions=FR_HOME)); frR.apply_action(ArticulationAction(joint_positions=FR_HOME))
        t=S["t"]; st=S["st"]; jp=np.array(amr.get_joint_positions(),float); ax,ay=jp[0]+4.54,jp[1]-4.8
        base=DOCK.copy(); arm=HOME.copy(); yaw=S["yaw"]; fol=(S["toff"] is not None)
        if st=="reach":
            al=min(1.0,t/150.0); base=DOCK; yaw=YAW_DOCK; arm=(1-al)*HOME+al*GRAB
            if t>=190: setp("lift")
        elif st=="lift":
            al=min(1.0,t/120.0); base=DOCK; yaw=YAW_DOCK; arm=(1-al)*GRAB+al*HOME
            if t>=130: setp("turn")
        elif st=="turn":
            al=min(1.0,t/240.0); base=DOCK; yaw=YAW_DOCK+(YAW_RACK-YAW_DOCK)*al; arm=HOME; S["yaw"]=yaw
            if t>=240: S["yaw"]=YAW_RACK; setp("haul")
        elif st=="haul":
            yaw=YAW_RACK; arm=HOME; base,done=gated(ax,ay)
            if done: setp("place")
        elif st=="place":
            al=min(1.0,t/150.0); base=HAUL_WPS[-1]; yaw=YAW_RACK; arm=(1-al)*HOME+al*PLACE
            if t>=180: setp("release")
        elif st=="release":
            base=HAUL_WPS[-1]; yaw=YAW_RACK; arm=PLACE; fol=False
            if t==0:
                tote.set_world_pose(SHELF_TOTE, IDENT); tote.set_linear_velocity(np.zeros(3)); tote.set_angular_velocity(np.zeros(3))
                for i,b in enumerate(blocks):
                    b.set_world_pose(SHELF_TOTE+np.array([COMPX[i],0.0,0.05]), IDENT); b.set_linear_velocity(np.zeros(3)); b.set_angular_velocity(np.zeros(3))
            if t>=120: setp("retract")
        elif st=="retract":
            al=min(1.0,t/150.0); base=HAUL_WPS[-1]; yaw=YAW_RACK; arm=(1-al)*PLACE+al*HOME; fol=False
            if t>=150: setp("done")
        else:
            base=HAUL_WPS[-1]; yaw=YAW_RACK; arm=HOME; fol=False
        grabbed=(S["toff"] is not None)
        grip=GR_GRIP if (grabbed and st in ("lift","turn","haul","place")) else GR_OPEN
        d=base-S["cbase"]; dn=float(np.linalg.norm(d)); S["cbase"]=(S["cbase"]+d/dn*MAX_STEP) if dn>MAX_STEP else base.copy()
        tgt=jp.copy(); bj=b2j(S["cbase"]); tgt[0]=bj[0]; tgt[1]=bj[1]; tgt[2]=yaw; tgt[3:10]=arm; tgt[10:12]=[grip,grip]
        amr.apply_action(ArticulationAction(joint_positions=tgt))
        hp,hq=hand.get_world_pose()
        if st=="reach" and t==150: lockcap(hp); print("LOCK tote+%d blocks"%len(blocks),flush=True)
        if fol and S["toff"] is not None: follow(hp)
        S["t"]+=1
        if t%60==0:
            tpz,_=tote.get_world_pose(); print("H %-8s t=%d wp=%d base=(%.2f,%.2f) tote=(%.2f,%.2f,%.2f)"%(st,t,S["wp"],ax,ay,tpz[0],tpz[1],tpz[2]),flush=True)
        if st=="done" and t==1: print("HAUL_BIG_DONE",flush=True)
    except Exception:
        print("HB_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("HAUL_BIG_STARTED",flush=True)
