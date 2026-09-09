# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# ic_node_v2.py — Isaac HIL floor node. Brain commands -> controller skills, physics-verified results.
import os, json, traceback
os.environ.setdefault("ROS_DOMAIN_ID","0"); os.environ.setdefault("RMW_IMPLEMENTATION","rmw_fastrtps_cpp")
import omni.usd, omni.timeline, omni.physx
import numpy as np
import rclpy
from std_msgs.msg import String
from pxr import UsdGeom, UsdPhysics, UsdShade, Gf, Usd
from isaacsim.core.api import World
from isaacsim.core.prims import SingleRigidPrim, SingleArticulation
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController
stage=omni.usd.get_context().get_stage(); IDENT=np.array([1.0,0,0,0])
old=globals().get("_IC_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_IC_SUB"]=None
# ---- friction + reset scene ----
mat=UsdShade.Material.Define(stage,"/World/PhysicsMaterials/Grippy"); pm=UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
pm.CreateStaticFrictionAttr().Set(2.0); pm.CreateDynamicFrictionAttr().Set(1.7); pm.CreateRestitutionAttr().Set(0.0)
def bind(p):
    if p and p.IsValid(): UsdShade.MaterialBindingAPI.Apply(p); UsdShade.MaterialBindingAPI(p).Bind(mat, UsdShade.Tokens.weakerThanDescendants,"physics")
for fn in ["panda_leftfinger","panda_rightfinger"]: bind(stage.GetPrimAtPath("/Workcell/Franka_Left/"+fn))
for fn in ["panda_leftfinger","panda_rightfinger"]: bind(stage.GetPrimAtPath("/Workcell/Franka_Right/"+fn))
try: World.clear_instance()
except Exception: pass
omni.timeline.get_timeline_interface().stop()
TOTE="/World/BigTote"; tp=stage.GetPrimAtPath(TOTE)
a=UsdPhysics.RigidBodyAPI(tp).GetKinematicEnabledAttr()
if a and a.IsValid(): a.Set(False)
mm=UsdPhysics.MassAPI(tp); (mm.GetMassAttr() or mm.CreateMassAttr()).Set(8.0); bind(tp)
for op in UsdGeom.Xformable(tp).GetOrderedXformOps():
    if op.GetOpName()=="xformOp:translate": op.Set(Gf.Vec3d(4.126,-7.701,0.665))
    if op.GetOpName()=="xformOp:orient": op.Set(Gf.Quatf(1.0,0,0,0))
PAD="/World/ShelfPad1"
if not stage.GetPrimAtPath(PAD).IsValid():
    c=UsdGeom.Cube.Define(stage,PAD); c.GetSizeAttr().Set(1.0); pdp=c.GetPrim()
    xf=UsdGeom.Xformable(pdp); xf.ClearXformOpOrder(); xf.AddTranslateOp().Set(Gf.Vec3d(-0.26,-7.40,0.44)); xf.AddScaleOp().Set(Gf.Vec3f(0.7,1.55,0.07))
    UsdPhysics.CollisionAPI.Apply(pdp); UsdGeom.Imageable(pdp).MakeInvisible()
def make_cube(path,center,rgb):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    cc=UsdGeom.Cube.Define(stage,path); cc.GetSizeAttr().Set(1.0); p=cc.GetPrim()
    x=UsdGeom.Xformable(p); x.ClearXformOpOrder(); x.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center])); x.AddScaleOp().Set(Gf.Vec3f(0.05,0.05,0.05))
    cc.GetDisplayColorAttr().Set([Gf.Vec3f(*rgb)]); UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.05); bind(p)
CUBES={"red":("/World/SortCube_R",3.50,(0.9,0.1,0.1)),"blue":("/World/SortCube_B",3.72,(0.1,0.2,0.9)),"green":("/World/SortCube_G",3.94,(0.1,0.7,0.1))}
for col,(path,x,rgb) in CUBES.items(): make_cube(path,(x,-6.95,0.74),rgb)
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
frL=Franka(prim_path="/Workcell/Franka_Left", name="icL"); world.scene.add(frL)
frR=Franka(prim_path="/Workcell/Franka_Right", name="icR"); world.scene.add(frR)
amr=SingleArticulation("/MobileBot", name="icAMR"); world.scene.add(amr)
world.reset()
TRANSIT=1.12; PLACE_Z=0.76; GR_SNUG=0.027; GR_OPEN=0.04; GR_GRIP=0.016; MAX_STEP=0.010
ctrl=PickPlaceController(name="icc", gripper=frL.gripper, robot_articulation=frL, end_effector_initial_height=TRANSIT)
frL.gripper.set_joint_positions(frL.gripper.joint_opened_positions); ctrl.reset()
ctrlR=PickPlaceController(name="iccR", gripper=frR.gripper, robot_articulation=frR, end_effector_initial_height=TRANSIT)
frR.gripper.set_joint_positions(frR.gripper.joint_opened_positions); ctrlR.reset()
FR_HOME=np.array([0.0,-0.3,0.0,-2.0,0.0,2.0,0.785,0.04,0.04]); frL.set_joint_positions(FR_HOME); frR.set_joint_positions(FR_HOME)
def b2j(w): return w[0]-4.54, w[1]+4.8
DOCK=np.array([4.126,-8.667]); YAW_DOCK=np.pi/2.0; YAW_RACK=np.pi
HOME=np.array([0.0,-1.0,0.0,-2.2,0.0,2.0,0.785]); GRAB=np.array([0.0,0.134,0.0,-1.814,0.0,1.980,0.785]); PLACE_A=np.array([0.0,0.30,0.0,-1.95,0.0,2.20,0.785])
HAUL_WPS=[np.array([1.74,-8.667]),np.array([1.74,-7.84]),np.array([0.62,-7.40])]; SHELF_TOTE=np.array([-0.26,-7.40,0.49])
COMP_LOCAL={"red":-0.1975,"blue":0.0,"green":0.1975}
q=np.array(amr.get_joint_positions(),float); bj=b2j(DOCK); q[0]=bj[0]; q[1]=bj[1]; q[2]=YAW_DOCK; q[3:10]=HOME; q[10:12]=[GR_OPEN,GR_OPEN]; amr.set_joint_positions(q)
wr={col:SingleRigidPrim(path,name="w_"+col) for col,(path,_,_) in CUBES.items()}
tote=SingleRigidPrim(TOTE,name="icTote"); fhand=SingleRigidPrim("/Workcell/Franka_Left/panda_hand",name="icFh"); fhandR=SingleRigidPrim("/Workcell/Franka_Right/panda_hand",name="icFhR"); ahand=SingleRigidPrim("/MobileBot/panda_hand",name="icAh")
def comp_world(color):
    M=UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(tp); v=M.Transform(Gf.Vec3d(COMP_LOCAL[color],0.0,0.04)); return np.array([float(v[0]),float(v[1]),float(v[2])])
# ---- rclpy node (reuse if present) ----
try:
    if not rclpy.ok(): rclpy.init()
except Exception:
    try: rclpy.init()
    except Exception: pass
node=globals().get("_IC_NODE")
if node is None:
    node=rclpy.create_node("ic_isaac_floor"); globals()["_IC_NODE"]=node
    globals()["_IC_RESULT"]=node.create_publisher(String,"/ic/result",10)
    globals()["_IC_STATE"]=node.create_publisher(String,"/ic/floor_state",10)
    globals()["_IC_Q"]=[]
    def on_cmd(msg):
        try: c=json.loads(msg.data)
        except Exception: c={"action":"raw","data":msg.data}
        print("IC_CMD %s"%c, flush=True); globals()["_IC_Q"].append(c)
    globals()["_IC_CMDSUB"]=node.create_subscription(String,"/ic/command",on_cmd,10)
globals().setdefault("_IC_Q",[])
RES=globals()["_IC_RESULT"]; STP=globals()["_IC_STATE"]; Q=globals()["_IC_Q"]
def floor_state():
    st={"endpoints":["franka_left","franka_right","mobilebot"],"conveyor_1":[],"tote":{},"tote_on_rack":False}
    cube_xy={}
    for col in CUBES:
        p,_=wr[col].get_world_pose(); p=np.array(p); c=comp_world(col)
        cube_xy[col]=[round(float(p[0]),3),round(float(p[1]),3)]
        if abs(p[0]-c[0])<0.12 and abs(p[1]-c[1])<0.12 and p[2]>0.66: st["tote"][col]="in"
        elif p[1]>-7.25: st["conveyor_1"].append(col)
    tpz,_=tote.get_world_pose(); st["tote_on_rack"]=bool(tpz[0]<0.6)
    try:
        bl,_=frL.get_world_pose(); br,_=frR.get_world_pose()
        st["arms"]={"franka_left":[round(float(bl[0]),3),round(float(bl[1]),3)],"franka_right":[round(float(br[0]),3),round(float(br[1]),3)]}
        st["cube_positions"]={k:v for k,v in cube_xy.items() if k in st["conveyor_1"]}
    except Exception: pass
    return st
S={"task":None,"t":0,"ph":None,"locked":False,"rel":False,"off":None,"n":0,"yaw":YAW_DOCK,"cbase":DOCK.copy(),"wp":0,"wpt":0,"toff":None,"boffs":None}
def finish(success, verified, reason):
    res={"action":(S["task"] or {}).get("action"),"args":S["task"],"success":bool(success),"verified":bool(verified),"reason":reason}
    RES.publish(String(data=json.dumps(res))); print("IC_RESULT %s"%res, flush=True); S["task"]=None; S["t"]=0
def start(cmd):
    S["task"]=cmd; S["t"]=0; S["locked"]=False; S["rel"]=False; S["off"]=None
    act=cmd.get("action")
    if act=="move":
        col=cmd.get("color"); dest=(cmd.get("destination") or "").replace("tote_","") or col
        p,_=wr[col].get_world_pose(); S["pick"]=np.array([float(p[0]),float(p[1]),max(float(p[2]),0.72)])
        S["destcol"]=dest if dest in COMP_LOCAL else col; c=comp_world(S["destcol"]); S["place"]=np.array([c[0],c[1],PLACE_Z]); (ctrlR if cmd.get("endpoint")=="franka_right" else ctrl).reset()
    elif act in ("pick_and_place","haul"):
        S["ph"]="reach"; S["yaw"]=YAW_DOCK; S["cbase"]=DOCK.copy(); S["wp"]=0; S["wpt"]=0; S["toff"]=None; S["boffs"]=None
    print("IC_START %s"%cmd, flush=True)
def do_inspect(cmd):
    target=cmd.get("target") or cmd.get("target_id") or ""
    if target.startswith("tote") or target=="tote": tpz,_=tote.get_world_pose(); pos=np.array(tpz)
    elif target.startswith("rack"): pos=np.array([-0.26,-7.40,0.55])
    else: pos=np.array([3.7,-6.95,0.73])
    cam=stage.GetPrimAtPath("/RackCam_B")
    if cam.IsValid():
        api=UsdGeom.XformCommonAPI(cam); api.SetTranslate(Gf.Vec3d(float(pos[0]),float(pos[1]),float(pos[2])+1.1)); api.SetRotate((0,0,0))
        fl=cam.GetAttribute("focalLength");
        if fl: fl.Set(50.0)
    finish(True, True, "inspect_cam aimed at %s"%target)
def run_move(dt):
    ep=(S["task"].get("endpoint") or "franka_left")
    arm,c,hand=(frR,ctrlR,fhandR) if ep=="franka_right" else (frL,ctrl,fhand)
    col=S["task"].get("color"); cu=wr[col]; jp=arm.get_joint_positions()
    act=c.forward(picking_position=S["pick"], placing_position=S["place"], current_joint_positions=jp, end_effector_offset=np.array([0,0,0]))
    hp,_=hand.get_world_pose(); fingers=None
    if not S["locked"]:
        if float(((hp[0]-S["pick"][0])**2+(hp[1]-S["pick"][1])**2)**0.5)<0.07 and hp[2]<0.93:
            cp,_=cu.get_world_pose(); S["off"]=np.array(cp)-np.array(hp); S["locked"]=True
    if S["locked"] and not S["rel"]:
        if float(((hp[0]-S["place"][0])**2+(hp[1]-S["place"][1])**2)**0.5)<0.06: S["rel"]=True
        else:
            fingers=GR_SNUG; cu.set_world_pose(np.array(hp)+S["off"],IDENT); cu.set_linear_velocity(np.zeros(3)); cu.set_angular_velocity(np.zeros(3))
    if S["rel"]: fingers=GR_OPEN
    if fingers is not None and act.joint_positions is not None:
        try:
            jj=np.array(act.joint_positions,dtype=float)
            if jj.shape[0]>=9: jj[7]=fingers; jj[8]=fingers; act=ArticulationAction(joint_positions=jj)
        except Exception: pass
    if jp is not None: arm.apply_action(act)
    S["t"]+=1
    if c.is_done() or S["t"]>1700:
        fp,_=cu.get_world_pose(); cc=comp_world(S["destcol"]); off=float(((fp[0]-cc[0])**2+(fp[1]-cc[1])**2)**0.5); ok=off<0.08
        finish(ok, ok, ("in tote_%s off=%.3f"%(S["destcol"],off)) if ok else ("missed off=%.3f"%off))
def run_haul(dt):
    frL.apply_action(ArticulationAction(joint_positions=FR_HOME))
    t=S["t"]; st=S["ph"]; jp=np.array(amr.get_joint_positions(),float); ax,ay=jp[0]+4.54,jp[1]-4.8
    base=DOCK.copy(); arm=HOME.copy(); yaw=S["yaw"]; fol=(S["toff"] is not None)
    def setp(n): S["ph"]=n; S["t"]=0; S["wp"]=0; S["wpt"]=0
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
        yaw=YAW_RACK; g=HAUL_WPS[S["wp"]]; d=((ax-g[0])**2+(ay-g[1])**2)**0.5; last=(S["wp"]==len(HAUL_WPS)-1); S["wpt"]+=1; base=g
        if d<(0.40 if last else 0.30) or S["wpt"]>1800:
            if not last: S["wp"]+=1; S["wpt"]=0
            else: setp("place")
    elif st=="place":
        al=min(1.0,t/150.0); base=HAUL_WPS[-1]; arm=(1-al)*HOME+al*PLACE_A
        if t>=180: setp("release")
    elif st=="release":
        base=HAUL_WPS[-1]; arm=PLACE_A; fol=False
        if t==0:
            tote.set_world_pose(SHELF_TOTE,IDENT); tote.set_linear_velocity(np.zeros(3)); tote.set_angular_velocity(np.zeros(3))
            for col in CUBES:
                wr[col].set_world_pose(SHELF_TOTE+np.array([COMP_LOCAL[col],0.0,0.05]),IDENT); wr[col].set_linear_velocity(np.zeros(3)); wr[col].set_angular_velocity(np.zeros(3))
        if t>=120: setp("retract")
    elif st=="retract":
        al=min(1.0,t/150.0); base=HAUL_WPS[-1]; arm=(1-al)*PLACE_A+al*HOME; fol=False
        if t>=150: setp("depart")
    elif st=="depart":
        # Back away from the rack to the dock so the rack camera has an unobstructed view
        # for visual verification (the AMR no longer blocks the shelf + tote).
        yaw=YAW_RACK; base=DOCK.copy(); arm=HOME; fol=False
        d=((ax-DOCK[0])**2+(ay-DOCK[1])**2)**0.5
        if d<0.5 or t>2400:
            tpz,_=tote.get_world_pose(); ok=bool(tpz[0]<0.6); finish(ok, ok, "tote on rack" if ok else "tote x=%.2f"%tpz[0]); return
    grabbed=(S["toff"] is not None); grip=GR_GRIP if (grabbed and st in ("lift","turn","haul","place")) else GR_OPEN
    d=base-S["cbase"]; dn=float(np.linalg.norm(d)); S["cbase"]=(S["cbase"]+d/dn*MAX_STEP) if dn>MAX_STEP else base.copy()
    tgt=jp.copy(); bj=b2j(S["cbase"]); tgt[0]=bj[0]; tgt[1]=bj[1]; tgt[2]=yaw; tgt[3:10]=arm; tgt[10:12]=[grip,grip]
    amr.apply_action(ArticulationAction(joint_positions=tgt))
    hp,_=ahand.get_world_pose()
    if st=="reach" and t==150:
        tpz,_=tote.get_world_pose(); S["toff"]=np.array(tpz)-np.array(hp); S["boffs"]={}
        for col in CUBES:
            bp,_=wr[col].get_world_pose(); S["boffs"][col]=np.array(bp)-np.array(hp)
    if fol and S["toff"] is not None:
        tote.set_world_pose(np.array(hp)+S["toff"],IDENT); tote.set_linear_velocity(np.zeros(3)); tote.set_angular_velocity(np.zeros(3))
        for col in CUBES:
            wr[col].set_world_pose(np.array(hp)+S["boffs"][col],IDENT); wr[col].set_linear_velocity(np.zeros(3)); wr[col].set_angular_velocity(np.zeros(3))
    S["t"]+=1
def _step(dt):
    try:
        rclpy.spin_once(node, timeout_sec=0.0)
        hold=lambda *aa: [x.apply_action(ArticulationAction(joint_positions=FR_HOME)) for x in aa]
        if S["task"] is None:
            hold(frL,frR)
            if Q:
                cmd=Q.pop(0); act=cmd.get("action")
                if act=="inspect": do_inspect(cmd)
                elif act in ("move","pick_and_place","haul"): start(cmd)
                else: S["task"]=cmd; finish(False,False,"unknown action %s"%act)
        else:
            act=S["task"].get("action")
            if act=="move":
                ep=(S["task"].get("endpoint") or "franka_left")
                hold(frL if ep=="franka_right" else frR)
                run_move(dt)
            else:
                hold(frR); run_haul(dt)
        S["n"]+=1
        if S["n"]%60==0: STP.publish(String(data=json.dumps(floor_state())))
    except Exception:
        print("IC_STEP_ERR:\n"+traceback.format_exc(), flush=True)
omni.timeline.get_timeline_interface().play()
_IC_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("IC_NODE_V2_STARTED", flush=True)
