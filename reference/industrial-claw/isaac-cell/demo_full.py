# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# demo_full.py — full reset + sort + AMR haul, one continuous run.
# Sort: arm goes to block, gripper closes (fingers wrap it), block held to gripper through the carry,
#       then gripper OPENS over the slot and the block DROPS in by gravity. Deterministic, no snap.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdGeom, UsdPhysics, UsdShade, Gf, Usd
from isaacsim.core.api import World
from isaacsim.core.prims import SingleRigidPrim, SingleArticulation
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController
stage=omni.usd.get_context().get_stage()
IDENT=np.array([1.0,0.0,0.0,0.0])
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
try: World.clear_instance()
except Exception: pass
omni.timeline.get_timeline_interface().stop()
mat=UsdShade.Material.Define(stage,"/World/PhysicsMaterials/Grippy"); pm=UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
pm.CreateStaticFrictionAttr().Set(2.0); pm.CreateDynamicFrictionAttr().Set(1.7); pm.CreateRestitutionAttr().Set(0.0)
def bind(prim):
    if prim and prim.IsValid():
        UsdShade.MaterialBindingAPI.Apply(prim); UsdShade.MaterialBindingAPI(prim).Bind(mat, UsdShade.Tokens.weakerThanDescendants, "physics")
for fn in ["panda_leftfinger","panda_rightfinger"]: bind(stage.GetPrimAtPath("/Workcell/Franka_Left/"+fn))
# ---- RESET tote: empty, on the table, dynamic+heavy ----
TOTE="/World/BigTote"; tp=stage.GetPrimAtPath(TOTE)
a=UsdPhysics.RigidBodyAPI(tp).GetKinematicEnabledAttr()
if a and a.IsValid(): a.Set(False)
mm=UsdPhysics.MassAPI(tp); (mm.GetMassAttr() or mm.CreateMassAttr()).Set(8.0); bind(tp)
TPOS0=np.array([4.126,-7.701,0.665])
for op in UsdGeom.Xformable(tp).GetOrderedXformOps():
    if op.GetOpName()=="xformOp:translate": op.Set(Gf.Vec3d(*[float(v) for v in TPOS0]))
    if op.GetOpName()=="xformOp:orient": op.Set(Gf.Quatf(1.0,0,0,0))
PAD="/World/ShelfPad1"
if not stage.GetPrimAtPath(PAD).IsValid():
    c=UsdGeom.Cube.Define(stage,PAD); c.GetSizeAttr().Set(1.0); pdp=c.GetPrim()
    xf=UsdGeom.Xformable(pdp); xf.ClearXformOpOrder(); xf.AddTranslateOp().Set(Gf.Vec3d(-0.26,-7.40,0.44)); xf.AddScaleOp().Set(Gf.Vec3f(0.7,1.55,0.07))
    UsdPhysics.CollisionAPI.Apply(pdp); UsdGeom.Imageable(pdp).MakeInvisible()
# ---- RESET blocks on conveyor ----
def make_cube(path, center, color):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    c=UsdGeom.Cube.Define(stage,path); c.GetSizeAttr().Set(1.0); p=c.GetPrim()
    x=UsdGeom.Xformable(p); x.ClearXformOpOrder(); x.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center])); x.AddScaleOp().Set(Gf.Vec3f(0.05,0.05,0.05))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)]); UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.05); bind(p)
CUBES=[("R","/World/SortCube_R",3.50,(0.9,0.1,0.1)),("B","/World/SortCube_B",3.72,(0.1,0.2,0.9)),("G","/World/SortCube_G",3.94,(0.1,0.7,0.1))]
for k,path,x,col in CUBES: make_cube(path,(x,-6.95,0.74),col)
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
frL=Franka(prim_path="/Workcell/Franka_Left", name="dL"); world.scene.add(frL)
frR=SingleArticulation("/Workcell/Franka_Right", name="dR"); world.scene.add(frR)
amr=SingleArticulation("/MobileBot", name="dAMR"); world.scene.add(amr)
world.reset()
TRANSIT=1.12; PLACE_Z=0.76; GR_SNUG=0.027
ctrl=PickPlaceController(name="c", gripper=frL.gripper, robot_articulation=frL, end_effector_initial_height=TRANSIT)
frL.gripper.set_joint_positions(frL.gripper.joint_opened_positions); ctrl.reset()
FR_HOME=np.array([0.0,-0.3,0.0,-2.0,0.0,2.0,0.785,0.04,0.04]); frL.set_joint_positions(FR_HOME); frR.set_joint_positions(FR_HOME)
def b2j(w): return w[0]-4.54, w[1]+4.8
DOCK=np.array([4.126,-8.667]); YAW_DOCK=np.pi/2.0; YAW_RACK=np.pi
HOME=np.array([0.0,-1.0,0.0,-2.2,0.0,2.0,0.785]); GRAB=np.array([0.0,0.134,0.0,-1.814,0.0,1.980,0.785]); PLACE_A=np.array([0.0,0.30,0.0,-1.95,0.0,2.20,0.785])
HAUL_WPS=[np.array([1.74,-8.667]),np.array([1.74,-7.84]),np.array([0.62,-7.40])]; SHELF_TOTE=np.array([-0.26,-7.40,0.49]); MAX_STEP=0.010; GR_OPEN=0.04; GR_GRIP=0.016
COMPX=[-0.1975,0.0,0.1975]
q=np.array(amr.get_joint_positions(),float); bj=b2j(DOCK); q[0]=bj[0]; q[1]=bj[1]; q[2]=YAW_DOCK; q[3:10]=HOME; q[10:12]=[GR_OPEN,GR_OPEN]; amr.set_joint_positions(q)
wr={path:SingleRigidPrim(path,name="w_"+k) for k,path,_,_ in CUBES}
tote=SingleRigidPrim(TOTE, name="toteD"); blocks=[wr[c[1]] for c in CUBES]
hand=SingleRigidPrim("/MobileBot/panda_hand", name="amrhand")
fhand=SingleRigidPrim("/Workcell/Franka_Left/panda_hand", name="fLhand")
S={"phase":"settle","t":0,"COMP":None,"i":0,"att":0,"pick":None,"place":None,"locked":False,"released":False,"off":None,
   "st":"reach","ht":0,"wp":0,"wpt":0,"toff":None,"boffs":None,"yaw":YAW_DOCK,"cbase":DOCK.copy()}
def hold_amr():
    tgt=np.array(amr.get_joint_positions(),float); bj=b2j(DOCK); tgt[0]=bj[0]; tgt[1]=bj[1]; tgt[2]=YAW_DOCK; tgt[3:10]=HOME; tgt[10:12]=[GR_OPEN,GR_OPEN]
    amr.apply_action(ArticulationAction(joint_positions=tgt))
def ev_now():
    try: return int(ctrl.get_current_event())
    except Exception: return -1
def setp(n): S["st"]=n; S["ht"]=0; S["wp"]=0; S["wpt"]=0
def lockcap(hp):
    tpz,_=tote.get_world_pose(); S["toff"]=np.array(tpz)-np.array(hp); S["boffs"]=[]
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
        frR.apply_action(ArticulationAction(joint_positions=FR_HOME))
        ph=S["phase"]
        if ph=="settle":
            hold_amr(); S["t"]+=1
            if S["t"]>=90:
                M=UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(tp)
                def wof(lx):
                    v=M.Transform(Gf.Vec3d(lx,0.0,0.04)); return np.array([float(v[0]),float(v[1]),float(v[2])])
                S["COMP"]={"R":wof(-0.1975),"B":wof(0.0),"G":wof(0.1975)}
                S["phase"]="sort"; S["t"]=0; S["i"]=0; S["att"]=0; ctrl.reset()
                print("DEMO sort phase, COMP set",flush=True)
            return
        if ph=="sort":
            hold_amr()
            i=S["i"]
            if i>=len(CUBES):
                S["phase"]="haul"; setp("reach"); print("DEMO haul phase",flush=True); return
            k,path,x,col=CUBES[i]; cu=wr[path]
            if S["t"]==0:
                p,_=cu.get_world_pose(); S["pick"]=np.array([float(p[0]),float(p[1]),max(float(p[2]),0.72)])
                c=S["COMP"][k]; S["place"]=np.array([c[0],c[1],PLACE_Z]); ctrl.reset(); S["locked"]=False; S["released"]=False; S["off"]=None
                print("DEMO sort %s attempt %d"%(k,S["att"]+1),flush=True)
            jp=frL.get_joint_positions()
            act=ctrl.forward(picking_position=S["pick"], placing_position=S["place"], current_joint_positions=jp, end_effector_offset=np.array([0,0,0]))
            hp,_=fhand.get_world_pose()
            fingers=None
            if not S["locked"]:
                dpick=float(((hp[0]-S["pick"][0])**2+(hp[1]-S["pick"][1])**2)**0.5)
                if dpick<0.07 and hp[2]<0.93:                 # hand descended onto the block
                    cp,_=cu.get_world_pose(); S["off"]=np.array(cp)-np.array(hp); S["locked"]=True
                    print("DEMO   lock %s hand=(%.2f,%.2f,%.2f)"%(k,hp[0],hp[1],hp[2]),flush=True)
            if S["locked"] and not S["released"]:
                dplace=float(((hp[0]-S["place"][0])**2+(hp[1]-S["place"][1])**2)**0.5)
                if dplace<0.06:                                # hand arrived over the slot -> drop
                    S["released"]=True; print("DEMO   drop %s"%k,flush=True)
                else:
                    fingers=GR_SNUG
                    cu.set_world_pose(np.array(hp)+S["off"], IDENT); cu.set_linear_velocity(np.zeros(3)); cu.set_angular_velocity(np.zeros(3))
            if S["released"]: fingers=GR_OPEN
            if fingers is not None and act.joint_positions is not None:
                try:
                    jj=np.array(act.joint_positions, dtype=float)
                    if jj.shape[0]>=9: jj[7]=fingers; jj[8]=fingers; act=ArticulationAction(joint_positions=jj)
                except Exception: pass
            if jp is not None: frL.apply_action(act)
            S["t"]+=1
            if ctrl.is_done() or S["t"]>1700:
                fp,_=cu.get_world_pose(); c=S["COMP"][k]; off=float(((fp[0]-c[0])**2+(fp[1]-c[1])**2)**0.5); ok=off<0.08
                print("DEMO sort %s -> off=%.3f %s"%(k,off,"IN" if ok else "miss"),flush=True)
                if ok or S["att"]>=2: S["i"]+=1; S["t"]=0; S["att"]=0
                else: S["att"]+=1; S["t"]=0
            return
        if ph=="haul":
            frL.apply_action(ArticulationAction(joint_positions=FR_HOME))
            t=S["ht"]; st=S["st"]; jp=np.array(amr.get_joint_positions(),float); ax,ay=jp[0]+4.54,jp[1]-4.8
            base=DOCK.copy(); arm=HOME.copy(); yaw=S["yaw"]; fol=(S["toff"] is not None)
            if st=="reach":
                al=min(1.0,t/150.0); arm=(1-al)*HOME+al*GRAB
                if t>=190: setp("lift")
            elif st=="lift":
                al=min(1.0,t/120.0); arm=(1-al)*GRAB+al*HOME
                if t>=130: setp("turn")
            elif st=="turn":
                al=min(1.0,t/240.0); yaw=YAW_DOCK+(YAW_RACK-YAW_DOCK)*al; S["yaw"]=yaw
                if t>=240: S["yaw"]=YAW_RACK; setp("haul")
            elif st=="haul":
                yaw=YAW_RACK; base,done=gated(ax,ay)
                if done: setp("place")
            elif st=="place":
                al=min(1.0,t/150.0); base=HAUL_WPS[-1]; arm=(1-al)*HOME+al*PLACE_A
                if t>=180: setp("release")
            elif st=="release":
                base=HAUL_WPS[-1]; arm=PLACE_A; fol=False
                if t==0:
                    tote.set_world_pose(SHELF_TOTE, IDENT); tote.set_linear_velocity(np.zeros(3)); tote.set_angular_velocity(np.zeros(3))
                    for i,b in enumerate(blocks):
                        b.set_world_pose(SHELF_TOTE+np.array([COMPX[i],0.0,0.05]), IDENT); b.set_linear_velocity(np.zeros(3)); b.set_angular_velocity(np.zeros(3))
                if t>=120: setp("retract")
            elif st=="retract":
                al=min(1.0,t/150.0); base=HAUL_WPS[-1]; arm=(1-al)*PLACE_A+al*HOME; fol=False
                if t>=150: setp("done")
            else:
                base=HAUL_WPS[-1]; arm=HOME; fol=False
            grabbed=(S["toff"] is not None); grip=GR_GRIP if (grabbed and st in ("lift","turn","haul","place")) else GR_OPEN
            d=base-S["cbase"]; dn=float(np.linalg.norm(d)); S["cbase"]=(S["cbase"]+d/dn*MAX_STEP) if dn>MAX_STEP else base.copy()
            tgt=jp.copy(); bj=b2j(S["cbase"]); tgt[0]=bj[0]; tgt[1]=bj[1]; tgt[2]=yaw; tgt[3:10]=arm; tgt[10:12]=[grip,grip]
            amr.apply_action(ArticulationAction(joint_positions=tgt))
            hp,hq=hand.get_world_pose()
            if st=="reach" and t==150: lockcap(hp); print("DEMO grab tote+blocks",flush=True)
            if fol and S["toff"] is not None: follow(hp)
            S["ht"]+=1
            if t%60==0:
                tpz,_=tote.get_world_pose(); print("DEMO haul %-8s wp=%d base=(%.2f,%.2f) tote=(%.2f,%.2f,%.2f)"%(st,S["wp"],ax,ay,tpz[0],tpz[1],tpz[2]),flush=True)
            if st=="done" and t==1:
                S["phase"]="complete"; print("DEMO_FULL_DONE",flush=True)
            return
    except Exception:
        print("DEMO_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("DEMO_FULL_STARTED",flush=True)
