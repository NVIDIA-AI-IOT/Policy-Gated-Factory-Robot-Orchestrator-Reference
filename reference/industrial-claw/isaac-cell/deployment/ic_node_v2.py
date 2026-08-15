# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# ic_node_v2.py — Isaac HIL floor node. Brain commands -> controller skills, physics-verified results.
import os, json, traceback, random
os.environ.setdefault("ROS_DOMAIN_ID","0"); os.environ.setdefault("RMW_IMPLEMENTATION","rmw_fastrtps_cpp")
import omni.usd, omni.timeline, omni.physx
import numpy as np
import rclpy
from std_msgs.msg import String
from pxr import UsdGeom, UsdPhysics, UsdShade, Gf, Sdf, Usd
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

# Canonical non-cube shape assets are authored before World/reset so adding a
# rigid body never invalidates an active Isaac tensor/articulation view.
def make_shape_assets():
    cyl=UsdGeom.Cylinder.Define(stage,"/World/ShapeCyl_blue"); cp=cyl.GetPrim()
    cyl.GetAxisAttr().Set(UsdGeom.Tokens.z); cyl.GetRadiusAttr().Set(0.025); cyl.GetHeightAttr().Set(0.050)
    cyl.GetDisplayColorAttr().Set([Gf.Vec3f(0.10,0.20,0.90)])
    cx=UsdGeom.Xformable(cp); cx.ClearXformOpOrder(); cx.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(6.6,-6.3,0.03)); cx.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(1.0,1.0,1.0))
    UsdPhysics.CollisionAPI.Apply(cp); cr=UsdPhysics.RigidBodyAPI.Apply(cp); (cr.GetKinematicEnabledAttr() or cr.CreateKinematicEnabledAttr()).Set(False)
    UsdPhysics.MassAPI.Apply(cp).GetMassAttr().Set(0.05); bind(cp)

    cyl_r=UsdGeom.Cylinder.Define(stage,"/World/ShapeCyl_blue_R"); cp_r=cyl_r.GetPrim()
    cyl_r.GetAxisAttr().Set(UsdGeom.Tokens.z); cyl_r.GetRadiusAttr().Set(0.025); cyl_r.GetHeightAttr().Set(0.050)
    cyl_r.GetDisplayColorAttr().Set([Gf.Vec3f(0.10,0.20,0.90)])
    cx_r=UsdGeom.Xformable(cp_r); cx_r.ClearXformOpOrder(); cx_r.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(6.8,-6.3,0.03)); cx_r.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(1.0,1.0,1.0))
    UsdPhysics.CollisionAPI.Apply(cp_r); cr_r=UsdPhysics.RigidBodyAPI.Apply(cp_r); (cr_r.GetKinematicEnabledAttr() or cr_r.CreateKinematicEnabledAttr()).Set(False)
    UsdPhysics.MassAPI.Apply(cp_r).GetMassAttr().Set(0.05); bind(cp_r)

    brick=UsdGeom.Cube.Define(stage,"/World/ShapeBrick_green"); bp=brick.GetPrim()
    brick.GetSizeAttr().Set(1.0); brick.GetDisplayColorAttr().Set([Gf.Vec3f(0.10,0.70,0.10)])
    bx=UsdGeom.Xformable(bp); bx.ClearXformOpOrder(); bx.AddTranslateOp().Set(Gf.Vec3d(6.6,-6.5,0.03)); bx.AddScaleOp().Set(Gf.Vec3f(0.060,0.040,0.050))
    UsdPhysics.CollisionAPI.Apply(bp); br=UsdPhysics.RigidBodyAPI.Apply(bp); (br.GetKinematicEnabledAttr() or br.CreateKinematicEnabledAttr()).Set(False)
    UsdPhysics.MassAPI.Apply(bp).GetMassAttr().Set(0.05); bind(bp)

    brick_r=UsdGeom.Cube.Define(stage,"/World/ShapeBrick_green_R"); bp_r=brick_r.GetPrim()
    brick_r.GetSizeAttr().Set(1.0); brick_r.GetDisplayColorAttr().Set([Gf.Vec3f(0.10,0.70,0.10)])
    bx_r=UsdGeom.Xformable(bp_r); bx_r.ClearXformOpOrder(); bx_r.AddTranslateOp().Set(Gf.Vec3d(6.8,-6.5,0.03)); bx_r.AddScaleOp().Set(Gf.Vec3f(0.060,0.040,0.050))
    UsdPhysics.CollisionAPI.Apply(bp_r); br_r=UsdPhysics.RigidBodyAPI.Apply(bp_r); (br_r.GetKinematicEnabledAttr() or br_r.CreateKinematicEnabledAttr()).Set(False)
    UsdPhysics.MassAPI.Apply(bp_r).GetMassAttr().Set(0.05); bind(bp_r)

    green_mat=UsdShade.Material.Define(stage,"/World/Looks/MatteGreenShape")
    green_shader=UsdShade.Shader.Define(stage,"/World/Looks/MatteGreenShape/PreviewSurface")
    green_shader.CreateIdAttr("UsdPreviewSurface")
    green_shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.10,0.70,0.10))
    green_shader.CreateInput("roughness",Sdf.ValueTypeNames.Float).Set(1.0)
    green_shader.CreateInput("metallic",Sdf.ValueTypeNames.Float).Set(0.0)
    green_shader.CreateInput("specularColor",Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.0,0.0,0.0))
    green_mat.CreateSurfaceOutput().ConnectToSource(green_shader.ConnectableAPI(),"surface")
    UsdShade.MaterialBindingAPI.Apply(bp); UsdShade.MaterialBindingAPI(bp).Bind(green_mat,UsdShade.Tokens.weakerThanDescendants)
    UsdShade.MaterialBindingAPI.Apply(bp_r); UsdShade.MaterialBindingAPI(bp_r).Bind(green_mat,UsdShade.Tokens.weakerThanDescendants)

RGB={"red":(0.9,0.1,0.1),"blue":(0.1,0.2,0.9),"green":(0.1,0.7,0.1)}
# pool of 6 cubes, 2 per color; spawner shows a random 2-6 of them per scene, parks the rest off-table
POOL=[("/World/SortCube_R","red"),("/World/SortCube_R2","red"),("/World/SortCube_B","blue"),("/World/SortCube_B2","blue"),("/World/SortCube_G","green"),("/World/SortCube_G2","green")]
POOL_COL=[c for _,c in POOL]
for i,(path,col) in enumerate(POOL): make_cube(path,(8.5+0.13*i,-9.8,0.05),RGB[col])
make_shape_assets()
CUBES={"red":("/World/SortCube_R",3.50,RGB["red"]),"blue":("/World/SortCube_B",3.72,RGB["blue"]),"green":("/World/SortCube_G",3.94,RGB["green"])}
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
frL=Franka(prim_path="/Workcell/Franka_Left", name="icL"); world.scene.add(frL)
frR=Franka(prim_path="/Workcell/Franka_Right", name="icR"); world.scene.add(frR)
amr=SingleArticulation("/MobileBot", name="icAMR"); world.scene.add(amr)
world.reset()
TRANSIT=1.12; PLACE_Z=0.76; GR_SNUG=0.027; GR_OPEN=0.04; GR_GRIP=0.016; MAX_STEP=0.010
# Official PickPlaceController timing with only phase 1 (descent) slowed from
# 0.005 to 0.0025.  The state machine is time-based; this gives RMPflow 400
# ticks instead of 200 to converge before physical finger closure at the edge
# of the declared workspace.  All other NVIDIA defaults remain unchanged.
RMPFLOW_EVENTS_DT=[0.008,0.0025,1.0,0.1,0.05,0.05,0.0025,1.0,0.008,0.08]
ctrl=PickPlaceController(name="icc", gripper=frL.gripper, robot_articulation=frL, end_effector_initial_height=TRANSIT, events_dt=RMPFLOW_EVENTS_DT)
frL.gripper.set_joint_positions(frL.gripper.joint_opened_positions); ctrl.reset()
ctrlR=PickPlaceController(name="iccR", gripper=frR.gripper, robot_articulation=frR, end_effector_initial_height=TRANSIT, events_dt=RMPFLOW_EVENTS_DT)
frR.gripper.set_joint_positions(frR.gripper.joint_opened_positions); ctrlR.reset()
FR_HOME=np.array([0.0,-0.3,0.0,-2.0,0.0,2.0,0.785,0.04,0.04]); frL.set_joint_positions(FR_HOME); frR.set_joint_positions(FR_HOME)
def b2j(w): return w[0]-4.54, w[1]+4.8
GRASP_L=0.103   # panda_hand origin -> fingertip grasp point, along the hand's local +Z (approach axis)
def qrot(q,v):  # rotate vector v by quaternion q=[w,x,y,z]
    w,x,y,z=float(q[0]),float(q[1]),float(q[2]),float(q[3]); qv=np.array([x,y,z])
    t=2.0*np.cross(qv,v); return v+w*t+np.cross(qv,t)
def _ic_apply_rmpflow_gripper(arm,target):
    """Persist a physical finger target without overwriting RMPflow's arm command."""
    indices=np.asarray(arm.gripper.active_joint_indices,dtype=int)
    values=np.full(indices.shape,float(target),dtype=float)
    arm.apply_action(ArticulationAction(joint_positions=values,joint_indices=indices))
def _ic_rmpflow_gripper_positions(arm):
    try: return np.asarray(arm.gripper.get_joint_positions(),dtype=float)
    except Exception: return np.asarray([],dtype=float)
DOCK=np.array([4.126,-8.667]); YAW_DOCK=np.pi/2.0; YAW_RACK=np.pi
HOME=np.array([0.0,-1.0,0.0,-2.2,0.0,2.0,0.785]); GRAB=np.array([0.0,0.134,0.0,-1.814,0.0,1.980,0.785]); PLACE_A=np.array([0.0,0.30,0.0,-1.95,0.0,2.20,0.785])
HAUL_WPS=[np.array([1.74,-8.667]),np.array([1.74,-7.84]),np.array([0.62,-7.40])]; SHELF_TOTE=np.array([-0.26,-7.40,0.49])
COMP_LOCAL={"red":-0.1975,"blue":0.0,"green":0.1975}
q=np.array(amr.get_joint_positions(),float); bj=b2j(DOCK); q[0]=bj[0]; q[1]=bj[1]; q[2]=YAW_DOCK; q[3:10]=HOME; q[10:12]=[GR_OPEN,GR_OPEN]; amr.set_joint_positions(q)
wr={col:SingleRigidPrim(path,name="w_"+col) for col,(path,_,_) in CUBES.items()}
wrp=[SingleRigidPrim(p,name="wp%d"%i) for i,(p,_) in enumerate(POOL)]
ACTIVE=set(); ZSPAWN=[(3.15,4.35),(4.80,5.35)]  # left=franka_left reach, right=franka_right reach
def spawn_scene(n=None, zone="left"):
    try: tote.set_world_pose(np.array([4.126,-7.701,0.665]),IDENT); tote.set_linear_velocity(np.zeros(3)); tote.set_angular_velocity(np.zeros(3))  # re-stand the (dynamic) tote each episode so a tip-over can't accumulate
    except Exception: pass
    try:
        if tote_r is not None and not floor_state().get("tote_r_on_rack"):
            tote_r.set_world_pose(TOTE_R_POS,TOTE_R_QUAT); tote_r.set_linear_velocity(np.zeros(3)); tote_r.set_angular_velocity(np.zeros(3))
    except Exception: pass
    n=int(n) if n else random.randint(4,6)
    if n>=3:
        base=[random.choice([0,1]),random.choice([2,3]),random.choice([4,5])]   # >=1 of each color so targets can be balanced
        rest=[x for x in range(6) if x not in base]; random.shuffle(rest); sel=base+rest[:n-3]; random.shuffle(sel)
    else:
        idx=list(range(6)); random.shuffle(idx); sel=idx[:n]
    if zone=="left": zsel=[(3.20,4.30)]*n   # all in franka_left's reach -> wrist cam sees several cubes (often same-color)
    elif zone=="right": zsel=[ZSPAWN[1]]*n  # all in franka_right's reach (right-cell capture)
    else: sides=[k%2 for k in range(n)]; random.shuffle(sides); zsel=[ZSPAWN[s] for s in sides]   # dual-arm split
    ACTIVE.clear(); ACTIVE.update(sel); placed=[]
    for k,i in enumerate(sel):
        lo,hi=zsel[k]; x=round(random.uniform(lo,hi),3); y=round(random.uniform(-7.04,-6.88),3)
        for _t in range(25):
            if all((x-px)**2+(y-py)**2>0.013 for px,py in placed): break
            x=round(random.uniform(lo,hi),3); y=round(random.uniform(-7.04,-6.88),3)
        placed.append((x,y))
        wrp[i].set_world_pose(np.array([x,y,0.74]),IDENT); wrp[i].set_linear_velocity(np.zeros(3)); wrp[i].set_angular_velocity(np.zeros(3))
    for i in range(6):
        if i not in ACTIVE:
            wrp[i].set_world_pose(np.array([8.5+0.13*i,-9.8,0.05]),IDENT); wrp[i].set_linear_velocity(np.zeros(3)); wrp[i].set_angular_velocity(np.zeros(3))
    print("SPAWN n=%d active=%s cols=%s"%(n,sorted(ACTIVE),[POOL_COL[i] for i in sel]),flush=True)
def target_cube(col,arm_x):
    # Only a matching object still reported on the conveyor is eligible.
    # Without this state filter, a stale concurrent mission can select a cube
    # already inside a tote (including a tote that has moved to the rack).
    conveyor_ids={
        int(c["i"]) for c in floor_state().get("cubes",[])
        if c.get("where")=="conveyor" and c.get("color")==col
    }
    cands=[i for i in ACTIVE if i in conveyor_ids]
    if not cands: return None
    return min(cands,key=lambda i:abs(float(wrp[i].get_world_pose()[0][0])-arm_x))
tote=SingleRigidPrim(TOTE,name="icTote"); fhand=SingleRigidPrim("/Workcell/Franka_Left/panda_hand",name="icFh"); fhandR=SingleRigidPrim("/Workcell/Franka_Right/panda_hand",name="icFhR"); ahand=SingleRigidPrim("/MobileBot/panda_hand",name="icAh")
# right workcell (mirrored, +1.8m x): present only when setup_right_cell.py ran at bring-up
TOTE_R="/World/BigTote_R"; tp_r=stage.GetPrimAtPath(TOTE_R)
tote_r=SingleRigidPrim(TOTE_R,name="icToteR") if tp_r.IsValid() else None
DOCK_R=np.array([5.451,-8.667]); SHELF_TOTE_R=np.array([-0.26,-7.40,0.84])  # NEXT shelf level, same column — 0.5m lateral gap overlapped (totes are 0.62m long)
TOTE_R_POS=np.array([5.451,-7.701,0.665]); TOTE_R_QUAT=np.array([1.0,0.0,0.0,0.0])  # north twin — THE canonical pose, used by spawn/reset alike
def comp_world(color, prim=None):
    M=UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(prim if prim is not None else tp); v=M.Transform(Gf.Vec3d(COMP_LOCAL[color],0.0,0.04)); return np.array([float(v[0]),float(v[1]),float(v[2])])
def in_compartment(p,c):
    # Compartment height follows the tote.  A fixed p[2] threshold worked on
    # the table but reclassified every carried cube after the tote was lowered
    # onto a rack shelf.
    return abs(p[0]-c[0])<0.12 and abs(p[1]-c[1])<0.12 and abs(p[2]-c[2])<0.20
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
    globals()["_IC_JOINTS"]=node.create_publisher(String,"/ic/joints",10)
    globals()["_IC_Q"]=[]
    def on_cmd(msg):
        try: c=json.loads(msg.data)
        except Exception: c={"action":"raw","data":msg.data}
        gid=c.get("goal_id")
        if gid and gid in globals().setdefault("_IC_SEEN_GOALS",set()):
            print("IC_CMD_DUP ignored goal_id=%s"%gid, flush=True); return
        if gid: globals()["_IC_SEEN_GOALS"].add(gid)
        print("IC_CMD %s"%c, flush=True); globals()["_IC_Q"].append(c)
    globals()["_IC_CMDSUB"]=node.create_subscription(String,"/ic/command",on_cmd,10)
globals().setdefault("_IC_Q",[])
RES=globals()["_IC_RESULT"]; STP=globals()["_IC_STATE"]; Q=globals()["_IC_Q"]
def _ic_scene_op_tick(_e):
    cmd = globals().pop("_IC_PENDING_RESET", None)
    if cmd is None: return
    globals()["_IC_FULL_SCENE_READY"] = False
    globals()["_IC_RESET_SCENE_READY"] = False
    try:
        if S.get("task") is not cmd:
            raise RuntimeError("reset command lost ownership of the active task")
        with open("/scripts/reset_two_arm.py", encoding="utf-8") as _rh:
            exec(compile(_rh.read(), "/scripts/reset_two_arm.py", "exec"), globals())
        if not globals().get("_IC_RESET_SCENE_READY", False):
            raise RuntimeError("reset transaction returned without its ready marker")
        if S.get("task") is not cmd:
            raise RuntimeError("reset transaction replaced the active task")
        expected_profile = str(
            cmd.get("scene_profile")
            or (globals().get("_IC_SCENE_RESET_CONTRACT") or {}).get(
                "scene_profile",
                "",
            )
        ).strip().lower()
        actual_profile = str(
            globals().get("_IC_LAST_RESET_PROFILE") or ""
        ).strip().lower()
        if not expected_profile or actual_profile != expected_profile:
            raise RuntimeError(
                "reset profile mismatch expected=%s actual=%s"
                % (expected_profile or "<missing>", actual_profile or "<missing>")
            )
        scene = dict(globals().get("_IC_LAST_RESET_SCENE") or {})
        globals()["_IC_FULL_SCENE_READY"] = True
        if actual_profile == "groot_three_object":
            protocol = dict(scene.get("capture_protocol") or {})
            reason = (
                "scene reset profile=%s target=%s layout=%s seed=%s arm=%s"
                % (
                    actual_profile,
                    scene.get("target"),
                    scene.get("layout"),
                    scene.get("seed"),
                    protocol.get("arm"),
                )
            )
        else:
            reason = "scene reset profile=%s active=%s" % (
                actual_profile,
                scene.get("active"),
            )
        reset_finish = globals().get("_IC_BASE_FINISH") or finish
        reset_finish(True,True,reason)
    except Exception:
        globals()["_IC_FULL_SCENE_READY"] = False
        reset_finish = globals().get("_IC_BASE_FINISH") or finish
        reset_finish(False,False,"reset err\n"+traceback.format_exc())
import omni.kit.app as _ick_app
_old_scene_op_sub = globals().get("_IC_SCENE_OP_SUB")
if _old_scene_op_sub is not None:
    try: _old_scene_op_sub.unsubscribe()
    except Exception: pass
globals()["_IC_PENDING_RESET"] = None
globals()["_IC_SCENE_OP_SUB"]=_ick_app.get_app().get_update_event_stream().create_subscription_to_pop(_ic_scene_op_tick, name="ic_scene_ops")
def floor_state():
    st={"endpoints":["franka_left","franka_right","mobilebot"],"conveyor_1":[],"tote":{},"tote_on_rack":False,"cubes":[]}
    if tote_r is not None: st["tote_r"]={}; st["tote_r_on_rack"]=False
    for i in sorted(ACTIVE):
        col=POOL_COL[i]; p,_=wrp[i].get_world_pose(); p=np.array(p); c=comp_world(col)
        intote=in_compartment(p,c)
        intote_r=False
        if tote_r is not None and not intote:
            cr=comp_world(col, tp_r)
            intote_r=in_compartment(p,cr)
        where="tote" if intote else ("tote_r" if intote_r else ("conveyor" if p[1]>-7.25 else "off"))
        st["cubes"].append({"i":i,"color":col,"x":round(float(p[0]),3),"y":round(float(p[1]),3),"where":where})
        if intote: st["tote"][col]="in"
        elif intote_r: st["tote_r"][col]="in"
        elif where=="conveyor": st["conveyor_1"].append(col)
    tpz,_=tote.get_world_pose(); st["tote_on_rack"]=bool(tpz[0]<0.6 and tpz[2]>0.30)
    if tote_r is not None:
        trz,_=tote_r.get_world_pose(); st["tote_r_on_rack"]=bool(trz[0]<0.6 and trz[2]>0.30)
    try:
        bl,_=frL.get_world_pose(); br,_=frR.get_world_pose()
        st["arms"]={"franka_left":[round(float(bl[0]),3),round(float(bl[1]),3)],"franka_right":[round(float(br[0]),3),round(float(br[1]),3)]}
    except Exception: pass
    return st
S={"task":None,"t":0,"ph":None,"locked":False,"rel":False,"off":None,"n":0,"yaw":YAW_DOCK,"cbase":DOCK.copy(),"wp":0,"wpt":0,"toff":None,"boffs":None}
def finish(success, verified, reason):
    task=S["task"] or {}
    # With a physical friction grasp, the controller reaches is_done while the
    # released cube is still falling into the tote.  Keep the task/action
    # stream alive for 45 physics ticks so capture includes the real opening
    # and drop, and evaluate the settled cube rather than its mid-air pose.
    if task.get("action")=="move" and task.get("backend")!="groot" and S.get("rel"):
        S["release_wait"]=int(S.get("release_wait",0))+1
        if S["release_wait"]<45:
            return
    res={"action":task.get("action"),"args":S["task"],"success":bool(success),"verified":bool(verified),"reason":reason}
    RES.publish(String(data=json.dumps(res))); print("IC_RESULT %s"%res, flush=True); S["task"]=None; S["t"]=0
globals()["_IC_BASE_FINISH"] = finish
def start(cmd):
    S["task"]=cmd; S["t"]=0; S["locked"]=False; S["rel"]=False; S["off"]=None; S["hpmin"]=None; S["offc"]=None; S["release_wait"]=0; S["physical_grip_closed"]=False
    act=cmd.get("action")
    if act=="move":
        col=cmd.get("color"); dest=(cmd.get("destination") or "").replace("tote_","") or col
        ep=cmd.get("endpoint"); bp,_=(frR if ep=="franka_right" else frL).get_world_pose()
        ti=target_cube(col,float(bp[0])); S["cube"]=(wrp[ti] if ti is not None else None)
        if ti is not None:
            p,_=wrp[ti].get_world_pose(); S["pick"]=np.array([float(p[0]),float(p[1]),max(float(p[2]),0.72)])
            S["destcol"]=dest if dest in COMP_LOCAL else col
            _tp_task=tp_r if (ep=="franka_right" and tote_r is not None) else None
            S["task_tote"]="tote_r" if _tp_task is not None else "tote"
            c=comp_world(S["destcol"], _tp_task); S["place"]=np.array([c[0],c[1],PLACE_Z]); (ctrlR if ep=="franka_right" else ctrl).reset()
    elif act in ("pick_and_place","haul"):
        _obj=str(cmd.get("object_id") or "tote").lower()
        S["haul_tote"]="tote_r" if (_obj in ("tote_right","tote_r","bigtote_r","tote2") and tote_r is not None) else "tote"
        S["dock"]=(DOCK_R if S["haul_tote"]=="tote_r" else DOCK).copy()
        S["shelf"]=(SHELF_TOTE_R if S["haul_tote"]=="tote_r" else SHELF_TOTE).copy()
        S.pop("cargo_manifest",None)
        S["ph"]="reach"; S["yaw"]=YAW_DOCK; S["cbase"]=S["dock"].copy(); S["wp"]=0; S["wpt"]=0; S["toff"]=None; S["boffs"]=None
    print("IC_START %s"%cmd, flush=True)
def do_inspect(cmd):
    S["task"]=cmd  # own the slot so finish() echoes goal_id (anonymous results poisoned sync waiters)
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
    cu=S.get("cube")
    if cu is None: finish(False,False,"no matching cube"); return
    jp=arm.get_joint_positions()
    phase=int(c.get_current_event())
    act=c.forward(picking_position=S["pick"], placing_position=S["place"], current_joint_positions=jp, end_effector_offset=np.array([0,0,0]))
    hp,hq=hand.get_world_pose(); hp=np.array(hp)
    grasp=hp+qrot(hq,np.array([0.0,0.0,GRASP_L]))   # the point between the fingertips, follows hand orientation
    if not S["locked"]:
        cp,_=cu.get_world_pose(); cp=np.array(cp)
        if float(np.linalg.norm(grasp-cp))<0.05:   # gripper genuinely near the cube (3D) -> only then track, so the captured offset stays snug
            if S["hpmin"] is None or hp[2]<=S["hpmin"]: S["hpmin"]=hp[2]; S["offc"]=cp-grasp   # track lowest point + its offset
            elif hp[2]>S["hpmin"]+0.012:
                if float(np.linalg.norm(S["offc"]))<0.045: S["off"]=S["offc"]; S["locked"]=True   # bottomed & snug -> lock
                else: S["hpmin"]=None; S["offc"]=None   # non-snug bottom (rare floating capture) -> reset, keep tracking for the real grasp
    if jp is not None:
        arm.apply_action(act)
        # RMPflow normally emits only seven arm joints. Drive the fingers in a
        # second indexed action every tick so the grasp is physical and the
        # command is observable by the demonstration recorder.
        finger_target=GR_GRIP if 3<=phase<7 else GR_OPEN
        _ic_apply_rmpflow_gripper(arm,finger_target)
        measured=_ic_rmpflow_gripper_positions(arm)
        if 3<=phase<7 and measured.size and float(np.max(measured))<=GR_SNUG+0.006:
            if not S.get("physical_grip_closed"):
                print("IC_RMPFLOW_GRIP_CLOSED phase=%d fingers=%s"%(phase,[round(float(x),4) for x in measured]),flush=True)
            S["physical_grip_closed"]=True
        if phase>=7 and S.get("physical_grip_closed") and measured.size and float(np.min(measured))>=GR_OPEN-0.005:
            if not S.get("rel"):
                print("IC_RMPFLOW_RELEASE_OPEN phase=%d fingers=%s"%(phase,[round(float(x),4) for x in measured]),flush=True)
            S["rel"]=True
    S["t"]+=1
    if c.is_done() or S["t"]>1700:
        fp,_=cu.get_world_pose(); cc=comp_world(S["destcol"]); off=float(((fp[0]-cc[0])**2+(fp[1]-cc[1])**2)**0.5); ok=off<0.08
        finish(ok, ok, ("in tote_%s off=%.3f"%(S["destcol"],off)) if ok else ("missed off=%.3f"%off))
def run_haul(dt):
    frL.apply_action(ArticulationAction(joint_positions=FR_HOME))
    t=S["t"]; st=S["ph"]; jp=np.array(amr.get_joint_positions(),float); ax,ay=jp[0]+4.54,jp[1]-4.8
    _dock=S.get("dock",DOCK); _shelf=S.get("shelf",SHELF_TOTE); _tote=(tote_r if S.get("haul_tote")=="tote_r" else tote)
    base=_dock.copy(); arm=HOME.copy(); yaw=S["yaw"]; fol=(S["toff"] is not None)
    def setp(n): S["ph"]=n; S["t"]=0; S["wp"]=0; S["wpt"]=0
    if st=="reach":
        if t==0 and "cargo_manifest" not in S:
            _mtz,_=_tote.get_world_pose()
            S["cargo_manifest"]=[
                _cargo_index
                for _cargo_index in sorted(ACTIVE)
                if (
                    # Tote compartments span x offsets -0.1975..+0.1975 m.
                    # Use the physical tote footprint, not a center-only box.
                    lambda bp: abs(bp[0]-_mtz[0])<0.30
                    and abs(bp[1]-_mtz[1])<0.18
                    and bp[2]>0.6
                )(wrp[_cargo_index].get_world_pose()[0])
            ]
            print("IC_HAUL_MANIFEST %s"%S["cargo_manifest"], flush=True)
        if ((ax-_dock[0])**2+(ay-_dock[1])**2)**0.5>0.25 and t<1200:
            S["t"]=0; arm=HOME  # hold the reach timer until the base docks (was: fixed timer -> wild grab offsets)
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
        if t<=1:
            _tote.set_world_pose(_shelf,IDENT); _tote.set_linear_velocity(np.zeros(3)); _tote.set_angular_velocity(np.zeros(3))
            for _cargo_index in (S.get("boffs") or {}):
                _cargo_color=POOL_COL[_cargo_index]
                wrp[_cargo_index].set_world_pose(_shelf+np.array([COMP_LOCAL[_cargo_color],0.0,0.05]),IDENT)
                wrp[_cargo_index].set_linear_velocity(np.zeros(3)); wrp[_cargo_index].set_angular_velocity(np.zeros(3))
        if t>=120: setp("retract")
    elif st=="retract":
        al=min(1.0,t/150.0); base=HAUL_WPS[-1]; arm=(1-al)*PLACE_A+al*HOME; fol=False
        if t>=150: setp("depart")
    elif st=="depart":
        # Back away from the rack to the dock so the rack camera has an unobstructed view
        # for visual verification (the AMR no longer blocks the shelf + tote).
        park=np.array(globals().get("AMR_PARK",tuple(DOCK)),float)
        yaw=YAW_RACK; base=park; arm=HOME; fol=False
        d=((ax-park[0])**2+(ay-park[1])**2)**0.5
        if d<0.5 or t>2400:
            tpz,_=_tote.get_world_pose(); ok=bool(tpz[0]<0.6 and tpz[2]>0.30)
            finish(ok, ok, "tote on rack" if ok else "tote x=%.2f z=%.2f"%(tpz[0],tpz[2])); return
    grabbed=(S["toff"] is not None); grip=GR_GRIP if (grabbed and st in ("lift","turn","haul","place")) else GR_OPEN
    d=base-S["cbase"]; dn=float(np.linalg.norm(d)); S["cbase"]=(S["cbase"]+d/dn*MAX_STEP) if dn>MAX_STEP else base.copy()
    tgt=jp.copy(); bj=b2j(S["cbase"]); tgt[0]=bj[0]; tgt[1]=bj[1]; tgt[2]=yaw; tgt[3:10]=arm; tgt[10:12]=[grip,grip]
    amr.apply_action(ArticulationAction(joint_positions=tgt))
    hp,_=ahand.get_world_pose()
    if st=="reach" and t==150:
        tpz,_=_tote.get_world_pose(); raw=np.array(tpz)-np.array(hp)
        dxy=float(np.linalg.norm(raw[:2]))
        if dxy>0.30: raw[:2]*=0.30/dxy  # snap-grab: tote rides at the gripper, never floats afar
        S["toff"]=raw; S["boffs"]={}
        for _cargo_index in sorted(ACTIVE):
            _cargo_color=POOL_COL[_cargo_index]
            bp,_=wrp[_cargo_index].get_world_pose()
            _in=abs(bp[0]-tpz[0])<0.30 and abs(bp[1]-tpz[1])<0.18 and bp[2]>0.6
            _ej=(not _in) and _cargo_index in S.get("cargo_manifest",[]) and abs(bp[0]-tpz[0])<0.38 and abs(bp[1]-tpz[1])<0.30 and bp[2]>0.55
            if _in or _ej:
                if _ej: print("IC_HAUL_CARGO_RESCUE %d re-seated at grab"%_cargo_index, flush=True)
                S["boffs"][_cargo_index]=S["toff"]+np.array([COMP_LOCAL[_cargo_color],0.0,0.03])  # cargo (incl. reach-ejected) seated to its compartment
        print("IC_HAUL_GRAB toff=%.2fm cargo=%s"%(min(dxy,0.30),list(S["boffs"])), flush=True)
    if fol and S["toff"] is not None:
        _tote.set_world_pose(np.array(hp)+S["toff"],IDENT); _tote.set_linear_velocity(np.zeros(3)); _tote.set_angular_velocity(np.zeros(3))
        for _cargo_index in S["boffs"]:
            wrp[_cargo_index].set_world_pose(np.array(hp)+S["boffs"][_cargo_index],IDENT)
            wrp[_cargo_index].set_linear_velocity(np.zeros(3)); wrp[_cargo_index].set_angular_velocity(np.zeros(3))
    S["t"]+=1
def _step(dt):
    try:
        rclpy.spin_once(node, timeout_sec=0.0)
        hold=lambda *aa: [x.apply_action(ArticulationAction(joint_positions=FR_HOME)) for x in aa]
        if S["task"] is None:
            hold(frL,frR)
            if Q:
                cmd=Q.pop(0); act=cmd.get("action")
                settle_until = int(
                    globals().get("_IC_SCENE_SETTLE_UNTIL_TICK", 0)
                )
                if act!="reset_scene" and S["n"] < settle_until:
                    # Preserve FIFO order while physics settles and the camera
                    # subscriptions refill after a reset.
                    Q.insert(0, cmd)
                elif (
                    not globals().get("_IC_FULL_SCENE_READY", False)
                    and act!="reset_scene"
                ):
                    S["task"]=cmd
                    finish(
                        False,
                        False,
                        "scene is not ready; run reset_scene before any mission",
                    )
                elif act=="inspect": do_inspect(cmd)
                elif act=="spawn":
                    try: spawn_scene(cmd.get("n"), cmd.get("zone") or "left"); S["task"]=cmd; finish(True,True,"spawned %d"%len(ACTIVE))
                    except Exception: S["task"]=cmd; finish(False,False,"spawn err\n"+traceback.format_exc())
                elif act=="reset_scene":
                    # pose writes from inside the physics callback are silently
                    # clobbered by the engine write-back — defer to the update tick
                    S["task"]=cmd; globals()["_IC_PENDING_RESET"]=cmd
                elif act in ("move","move_pair","pick_and_place","haul"):
                    # Own the result slot before invoking deployment wrappers.
                    # A wrapper may reject a command synchronously (for example,
                    # a GR00T scene/target contract mismatch) before the base
                    # start() records it.  Publish that rejection immediately so
                    # Seam does not wait for its full action timeout.
                    S["task"]=cmd
                    try:
                        start(cmd)
                    except Exception as exc:
                        print("IC_START_ERR:\n"+traceback.format_exc(), flush=True)
                        finish(
                            False,
                            False,
                            "start rejected: %s: %s" %
                            (type(exc).__name__, str(exc)),
                        )
                else: S["task"]=cmd; finish(False,False,"unknown action %s"%act)
        else:
            act=S["task"].get("action")
            if act in ("move","move_pair"):
                ep=(S["task"].get("endpoint") or "franka_left")
                if act=="move":
                    hold(frL if ep=="franka_right" else frR)
                run_move(dt)
            elif act=="reset_scene":
                # The update-event transaction owns reset execution.  While it
                # is pending, keep both Frankas stationary and never enter the
                # unrelated AMR haul state machine.
                hold(frL,frR)
            else:
                hold(frR); run_haul(dt)
        S["n"]+=1
        if S["n"]%60==0: STP.publish(String(data=json.dumps(floor_state())))
        if S["n"]%3==0:
            try: globals()["_IC_JOINTS"].publish(String(data=json.dumps({"t":S["n"],"franka_left":[round(float(x),5) for x in frL.get_joint_positions()],"franka_right":[round(float(x),5) for x in frR.get_joint_positions()]})))
            except Exception: pass
    except Exception:
        print("IC_STEP_ERR:\n"+traceback.format_exc(), flush=True)
try: spawn_scene()
except Exception: print("SPAWN_INIT_ERR:\n"+traceback.format_exc(), flush=True)
omni.timeline.get_timeline_interface().play()
_IC_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("IC_NODE_V2_STARTED", flush=True)
