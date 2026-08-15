# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# make_handle_totes.py (v2) — wide-opening tote + a SIDE handle on the south wall (not on top).
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from pxr import UsdGeom, UsdPhysics, Gf
from isaacsim.core.api import World
from isaacsim.core.prims import SingleRigidPrim
stage=omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
def part(parent_path, name, lpos, scale, color):
    p=parent_path+"/"+name
    if stage.GetPrimAtPath(p).IsValid(): stage.RemovePrim(p)
    c=UsdGeom.Cube.Define(stage,p); c.GetSizeAttr().Set(1.0); cp=c.GetPrim()
    cx=UsdGeom.Xformable(cp); cx.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in lpos])); cx.AddScaleOp().Set(Gf.Vec3f(*[float(v) for v in scale]))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)]); UsdPhysics.CollisionAPI.Apply(cp)
def make_handle_tote(path, center, color, hcolor):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    par=UsdGeom.Xform.Define(stage,path); pp=par.GetPrim()
    UsdGeom.Xformable(pp).AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center]))
    UsdPhysics.RigidBodyAPI.Apply(pp); UsdPhysics.MassAPI.Apply(pp).GetMassAttr().Set(0.5)
    # body: wide opening (~10cm) so the Franka's 8cm gripper fits in to place
    part(path,"base",(0,0,0.0),(0.12,0.12,0.015),color)
    part(path,"wxp",(0.055,0,0.04),(0.012,0.12,0.07),color)
    part(path,"wxn",(-0.055,0,0.04),(0.012,0.12,0.07),color)
    part(path,"wyp",(0,0.055,0.04),(0.12,0.012,0.07),color)
    part(path,"wyn",(0,-0.055,0.04),(0.12,0.012,0.07),color)
    # SIDE handle on the south (-y) wall: horizontal bar held off the wall by 2 posts (gripper closes around it)
    part(path,"hpL",(-0.032,-0.072,0.04),(0.012,0.03,0.016),hcolor)
    part(path,"hpR",( 0.032,-0.072,0.04),(0.012,0.03,0.016),hcolor)
    part(path,"hbar",(0,-0.090,0.04),(0.085,0.014,0.02),hcolor)
for k,x in [("R",3.54),("B",3.74),("G",3.94)]:
    make_handle_tote("/World/HTote_"+k,(x,-7.75,0.952),(0.40,0.42,0.46),(0.95,0.75,0.1))
for n in ["Tote_R","Tote_B","Tote_G","SortBin_R","SortBin_B","SortBin_C"]:
    pr=stage.GetPrimAtPath("/World/"+n)
    if pr.IsValid():
        UsdGeom.Imageable(pr).MakeInvisible()
        for op in UsdGeom.Xformable(pr).GetOrderedXformOps():
            if "translate" in op.GetOpName(): op.Set(Gf.Vec3d(0.0,-16.0,-5.0)); break
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0); world.reset()
tw={k:SingleRigidPrim("/World/HTote_"+k,name="ht_"+k) for k in ["R","B","G"]}
S={"n":0}
def _step(dt):
    try:
        S["n"]+=1
        if S["n"]%90==0:
            print("HTOTE "+" ".join("%s=(%.2f,%.2f,%.2f)"%(k,tw[k].get_world_pose()[0][0],tw[k].get_world_pose()[0][1],tw[k].get_world_pose()[0][2]) for k in tw),flush=True)
    except Exception:
        print("HTOTE_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("HANDLE_TOTES2_STARTED", flush=True)
