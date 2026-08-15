# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# setup_rest.py — fix floating: tote DYNAMIC rests on table, blocks rest on conveyor. Settle + report.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdGeom, UsdPhysics, Gf, Usd
from isaacsim.core.api import World
from isaacsim.core.prims import SingleRigidPrim, SingleArticulation
from isaacsim.core.utils.types import ArticulationAction
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
# tote -> DYNAMIC, keep its x,y, set z just above table so it drops and rests
tp=stage.GetPrimAtPath("/World/BigTote")
a=UsdPhysics.RigidBodyAPI(tp).GetKinematicEnabledAttr()
if a and a.IsValid(): a.Set(False)
M=UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(tp); w=M.Transform(Gf.Vec3d(0,0,0))
tx,ty=float(w[0]),float(w[1])
for op in UsdGeom.Xformable(tp).GetOrderedXformOps():
    if op.GetOpName()=="xformOp:translate": op.Set(Gf.Vec3d(tx,ty,0.70))
print("TOTE set dynamic at (%.3f,%.3f, drop from 0.70)"%(tx,ty),flush=True)
def make_cube(path, center, size, color):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    c=UsdGeom.Cube.Define(stage,path); c.GetSizeAttr().Set(1.0); p=c.GetPrim()
    x=UsdGeom.Xformable(p); x.ClearXformOpOrder()
    x.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center])); x.AddScaleOp().Set(Gf.Vec3f(size,size,size))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.05)
CUBES=[("R","/World/SortCube_R",3.55,(0.9,0.1,0.1)),("B","/World/SortCube_B",3.74,(0.1,0.2,0.9)),("G","/World/SortCube_G",3.93,(0.1,0.7,0.1))]
for k,path,x,col in CUBES: make_cube(path,(x,-6.95,0.80),0.05,col)
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
frL=SingleArticulation("/Workcell/Franka_Left", name="hL"); world.scene.add(frL)
frR=SingleArticulation("/Workcell/Franka_Right", name="hR"); world.scene.add(frR)
amr=SingleArticulation("/MobileBot", name="hAMR"); world.scene.add(amr)
world.reset()
FR_HOME=np.array([0.0,-0.3,0.0,-2.0,0.0,2.0,0.785,0.04,0.04])
frL.set_joint_positions(FR_HOME); frR.set_joint_positions(FR_HOME)
cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
def zb(p):
    r=cache.ComputeWorldBound(stage.GetPrimAtPath(p)).ComputeAlignedRange(); return r.GetMin()[2],r.GetMax()[2]
S={"n":0}
def _step(dt):
    try:
        frL.apply_action(ArticulationAction(joint_positions=FR_HOME)); frR.apply_action(ArticulationAction(joint_positions=FR_HOME))
        S["n"]+=1
        if S["n"]==200:
            surf=zb("/Workcell/BigTable/Top")[1]; tb=zb("/World/BigTote")[0]
            cz=[zb("/World/"+c[1].split('/')[-1])[0] for c in CUBES]
            print("REST surface=%.3f tote_bottom=%.3f (gap %.3f) cubes_bottom=%s"%(surf,tb,tb-surf,[round(v,3) for v in cz]),flush=True)
            print("SETUP_REST_DONE",flush=True)
    except Exception:
        print("SR_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("SETUP_REST_STARTED",flush=True)
