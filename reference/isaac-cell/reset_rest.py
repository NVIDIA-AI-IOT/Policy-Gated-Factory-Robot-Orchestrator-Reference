# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# reset_rest.py — author tote+blocks at their RESTING poses (stop-safe), play, verify gaps ~0.
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
# tote: dynamic, authored AT its table rest pose (origin 0.6655 -> bottom 0.658 = table surface)
tp=stage.GetPrimAtPath("/World/BigTote")
a=UsdPhysics.RigidBodyAPI(tp).GetKinematicEnabledAttr()
if a and a.IsValid(): a.Set(False)
m=UsdPhysics.MassAPI(tp); (m.GetMassAttr() or m.CreateMassAttr()).Set(8.0)
got_t=False; got_o=False
for op in UsdGeom.Xformable(tp).GetOrderedXformOps():
    if op.GetOpName()=="xformOp:translate": op.Set(Gf.Vec3d(4.126,-7.701,0.6655)); got_t=True
    if op.GetOpName()=="xformOp:orient": op.Set(Gf.Quatf(1.0,0,0,0)); got_o=True
# blocks: authored at conveyor rest (top 0.703 -> center 0.728)
def make_cube(path, center, color):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    c=UsdGeom.Cube.Define(stage,path); c.GetSizeAttr().Set(1.0); p=c.GetPrim()
    x=UsdGeom.Xformable(p); x.ClearXformOpOrder(); x.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center])); x.AddScaleOp().Set(Gf.Vec3f(0.05,0.05,0.05))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)]); UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.15)
CUBES=[("R","/World/SortCube_R",3.50,(0.9,0.1,0.1)),("B","/World/SortCube_B",3.72,(0.1,0.2,0.9)),("G","/World/SortCube_G",3.94,(0.1,0.7,0.1))]
for k,path,x,col in CUBES: make_cube(path,(x,-6.95,0.728),col)
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
amr=SingleArticulation("/MobileBot", name="rA"); world.scene.add(amr)
frL=SingleArticulation("/Workcell/Franka_Left", name="rL"); world.scene.add(frL)
frR=SingleArticulation("/Workcell/Franka_Right", name="rR"); world.scene.add(frR)
world.reset()
FR_HOME=np.array([0.0,-0.3,0.0,-2.0,0.0,2.0,0.785,0.04,0.04]); frL.set_joint_positions(FR_HOME); frR.set_joint_positions(FR_HOME)
cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
def zb(p):
    r=cache.ComputeWorldBound(stage.GetPrimAtPath(p)).ComputeAlignedRange(); return r.GetMin()[2]
S={"t":0}
def _step(dt):
    try:
        frL.apply_action(ArticulationAction(joint_positions=FR_HOME)); frR.apply_action(ArticulationAction(joint_positions=FR_HOME))
        S["t"]+=1
        if S["t"]==160:
            surf=0.658; conv=0.703; tb=zb("/World/BigTote")
            cz=[zb("/World/"+c[1].split('/')[-1]) for c in CUBES]
            print("RESTCHK tote_bottom=%.3f (vs surface %.3f gap %.3f) | blocks_bottom=%s (vs conveyor %.3f)"%(tb,surf,tb-surf,[round(v,3) for v in cz],conv),flush=True)
            print("RESET_REST_DONE (kept_translate=%s orient=%s)"%(got_t,got_o),flush=True)
    except Exception:
        print("RR_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("RESET_REST_STARTED",flush=True)
