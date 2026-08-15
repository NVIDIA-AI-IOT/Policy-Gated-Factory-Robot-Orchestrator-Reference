# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# make_big_tote.py — big tote, 3 compartments + one side handle. WIDE version (y 0.15) restored.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdGeom, UsdPhysics, Gf, Usd
from isaacsim.core.api import World
from isaacsim.core.prims import SingleRigidPrim
stage=omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
# ---- inspect any "table" prims (path, world bbox, xform ops) ----
cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
for prim in stage.Traverse():
    if "table" in prim.GetName().lower() or "Table" in str(prim.GetPath()):
        try:
            bb=cache.ComputeWorldBound(prim).ComputeAlignedRange(); mn=bb.GetMin(); mx=bb.GetMax()
            print("TBL %-40s x[%.2f,%.2f] y[%.2f,%.2f] z[%.2f,%.2f]"%(str(prim.GetPath()),mn[0],mx[0],mn[1],mx[1],mn[2],mx[2]),flush=True)
        except Exception as e:
            print("TBL %-40s bbox_err %s"%(str(prim.GetPath()),e),flush=True)
        for op in UsdGeom.Xformable(prim).GetOrderedXformOps():
            print("    op %-22s = %s"%(op.GetOpName(), op.Get()),flush=True)
        if prim.HasAuthoredReferences():
            print("    (has references)",flush=True)
# ---- revert BigTote to WIDE 3-compartment ----
def part(parent_path, name, lpos, scale, color):
    p=parent_path+"/"+name
    if stage.GetPrimAtPath(p).IsValid(): stage.RemovePrim(p)
    c=UsdGeom.Cube.Define(stage,p); c.GetSizeAttr().Set(1.0); cp=c.GetPrim()
    cx=UsdGeom.Xformable(cp); cx.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in lpos])); cx.AddScaleOp().Set(Gf.Vec3f(*[float(v) for v in scale]))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)]); UsdPhysics.CollisionAPI.Apply(cp)
path="/World/BigTote"
if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
par=UsdGeom.Xform.Define(stage,path); pp=par.GetPrim()
UsdGeom.Xformable(pp).AddTranslateOp().Set(Gf.Vec3d(3.74,-7.75,0.952))
UsdPhysics.RigidBodyAPI.Apply(pp); UsdPhysics.MassAPI.Apply(pp).GetMassAttr().Set(1.0)
GREY=(0.40,0.42,0.46); YEL=(0.95,0.75,0.1)
part(path,"base",(0,0,0.0),(0.60,0.15,0.015),GREY)
part(path,"wback",(0,0.072,0.045),(0.60,0.012,0.075),GREY)
part(path,"wfront",(0,-0.072,0.045),(0.60,0.012,0.075),GREY)
part(path,"wleft",(-0.295,0,0.045),(0.012,0.15,0.075),GREY)
part(path,"wright",(0.295,0,0.045),(0.012,0.15,0.075),GREY)
part(path,"div1",(-0.10,0,0.045),(0.012,0.15,0.075),GREY)
part(path,"div2",( 0.10,0,0.045),(0.012,0.15,0.075),GREY)
part(path,"hpL",(-0.13,-0.088,0.045),(0.016,0.035,0.02),YEL)
part(path,"hpR",( 0.13,-0.088,0.045),(0.016,0.035,0.02),YEL)
part(path,"hbar",(0,-0.108,0.045),(0.32,0.018,0.026),YEL)
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0); world.reset()
bt=SingleRigidPrim(path,name="bt")
S={"n":0}
def _step(dt):
    try:
        S["n"]+=1
        if S["n"]%120==0:
            wp,_=bt.get_world_pose(); print("BIGTOTE=(%.2f,%.2f,%.2f)"%(wp[0],wp[1],wp[2]),flush=True)
    except Exception:
        print("BT_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("TOTE_REVERTED", flush=True)
