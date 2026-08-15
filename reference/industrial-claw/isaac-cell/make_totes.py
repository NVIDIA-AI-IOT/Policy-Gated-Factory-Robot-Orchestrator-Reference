# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# make_totes.py — replace KLT bins with small raw-USD open totes (~6cm, grippable). Cubes drop inside.
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
def make_cube(path, center, size, color):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    c=UsdGeom.Cube.Define(stage, path); c.GetSizeAttr().Set(1.0); p=c.GetPrim()
    xf=UsdGeom.Xformable(p); xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center])); xf.AddScaleOp().Set(Gf.Vec3f(size,size,size))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*col) for col in [color]][0:1] and [Gf.Vec3f(*color)])
    UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.05)
def make_tote(path, center, color):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    par=UsdGeom.Xform.Define(stage, path); pp=par.GetPrim()
    UsdGeom.Xformable(pp).AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center]))
    UsdPhysics.RigidBodyAPI.Apply(pp); UsdPhysics.MassAPI.Apply(pp).GetMassAttr().Set(0.15)
    parts=[("base",(0,0,0.0),(0.060,0.060,0.010)),
           ("wxp",(0.030,0,0.022),(0.008,0.060,0.045)),
           ("wxn",(-0.030,0,0.022),(0.008,0.060,0.045)),
           ("wyp",(0,0.030,0.022),(0.060,0.008,0.045)),
           ("wyn",(0,-0.030,0.022),(0.060,0.008,0.045))]
    for n,(lx,ly,lz),(sx,sy,sz) in parts:
        c=UsdGeom.Cube.Define(stage, path+"/"+n); c.GetSizeAttr().Set(1.0); cp=c.GetPrim()
        cx=UsdGeom.Xformable(cp); cx.AddTranslateOp().Set(Gf.Vec3d(lx,ly,lz)); cx.AddScaleOp().Set(Gf.Vec3f(sx,sy,sz))
        c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)]); UsdPhysics.CollisionAPI.Apply(cp)
# hide broken KLT bins
for n in ["Bin","Bin_B","Bin_C"]:
    pr=stage.GetPrimAtPath("/Workcell/"+n)
    if pr.IsValid(): UsdGeom.Imageable(pr).MakeInvisible()
TOTES=[("R","/World/Tote_R",3.54,(0.45,0.30,0.20)),("B","/World/Tote_B",3.74,(0.45,0.30,0.20)),("G","/World/Tote_G",3.94,(0.45,0.30,0.20))]
for k,path,x,col in TOTES: make_tote(path,(x,-7.75,0.955),col)
CUBES=[("/World/SortCube_R",3.54,(0.9,0.1,0.1)),("/World/SortCube_B",3.74,(0.1,0.2,0.9)),("/World/SortCube_G",3.94,(0.1,0.7,0.1))]
for path,x,col in CUBES: make_cube(path,(x,-6.95,1.05),0.025,col)
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0); world.reset()
tw={path:SingleRigidPrim(path,name="t_"+k) for k,path,_,_ in TOTES}
S={"n":0}
def _step(dt):
    try:
        S["n"]+=1
        if S["n"]%90==0:
            msg=" ".join("%s=(%.2f,%.2f,%.2f)"%(k, tw[p].get_world_pose()[0][0],tw[p].get_world_pose()[0][1],tw[p].get_world_pose()[0][2]) for k,p,_,_ in TOTES)
            print("TOTE",msg, flush=True)
    except Exception:
        print("TOTE_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("TOTES_STARTED", flush=True)
