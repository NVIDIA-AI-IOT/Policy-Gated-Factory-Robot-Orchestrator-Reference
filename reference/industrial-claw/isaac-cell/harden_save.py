# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# harden_save.py — author tote+blocks at RESTING poses (stop-safe), save scene to our_factory.usda.
import omni.usd, omni.timeline, traceback
from pxr import UsdGeom, UsdPhysics, Gf, Usd
from isaacsim.core.api import World
stage=omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
try: World.clear_instance()
except Exception: pass
omni.timeline.get_timeline_interface().stop()
def set_rest(path, xyz, ident_orient=False):
    p=stage.GetPrimAtPath(path)
    if not p.IsValid(): print("MISS %s"%path,flush=True); return
    for op in UsdGeom.Xformable(p).GetOrderedXformOps():
        if op.GetOpName()=="xformOp:translate": op.Set(Gf.Vec3d(*xyz))
        if ident_orient and op.GetOpName()=="xformOp:orient": op.Set(Gf.Quatf(1.0,0,0,0))
# tote dynamic, resting on the table; blocks resting on the conveyor
tp=stage.GetPrimAtPath("/World/BigTote")
a=UsdPhysics.RigidBodyAPI(tp).GetKinematicEnabledAttr()
if a and a.IsValid(): a.Set(False)
set_rest("/World/BigTote",(4.126,-7.701,0.6655),ident_orient=True)
set_rest("/World/SortCube_R",(3.50,-6.95,0.728))
set_rest("/World/SortCube_B",(3.72,-6.95,0.728))
set_rest("/World/SortCube_G",(3.94,-6.95,0.728))
# save the scene
root=stage.GetRootLayer()
ok=root.Save()
# verify resting while STOPPED (this is the stop-safe check: authored poses, no float)
cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
def zb(p):
    r=cache.ComputeWorldBound(stage.GetPrimAtPath(p)).ComputeAlignedRange(); return r.GetMin()[2]
tb=zb("/World/BigTote"); cz=[zb("/World/SortCube_"+k) for k in ["R","B","G"]]
print("HARDEN_SAVED ok=%s  STOPPED tote_bottom=%.3f (surface 0.658) blocks_bottom=%s (conveyor 0.703)"%(ok,tb,[round(v,3) for v in cz]),flush=True)
omni.timeline.get_timeline_interface().play()
print("HARDEN_DONE",flush=True)
