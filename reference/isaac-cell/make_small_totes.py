# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# make_small_totes.py — small grippable totes (~7cm) + small cubes (~3.5cm). Replace big totes. Verify rest.
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
    c=UsdGeom.Cube.Define(stage,path); c.GetSizeAttr().Set(1.0); p=c.GetPrim()
    xf=UsdGeom.Xformable(p); xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center])); xf.AddScaleOp().Set(Gf.Vec3f(size,size,size))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.03)
def make_tote(path, center, color):
    if stage.GetPrimAtPath(path).IsValid(): stage.RemovePrim(path)
    par=UsdGeom.Xform.Define(stage,path); pp=par.GetPrim()
    UsdGeom.Xformable(pp).AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center]))
    UsdPhysics.RigidBodyAPI.Apply(pp); UsdPhysics.MassAPI.Apply(pp).GetMassAttr().Set(0.1)
    # outer ~7.2cm, thin walls -> gripper (8cm) closes around it; interior ~5cm holds a 3.5cm cube
    parts=[("base",(0,0,0.0),(0.072,0.072,0.014)),
           ("wxp",(0.032,0,0.03),(0.008,0.072,0.05)),("wxn",(-0.032,0,0.03),(0.008,0.072,0.05)),
           ("wyp",(0,0.032,0.03),(0.072,0.008,0.05)),("wyn",(0,-0.032,0.03),(0.072,0.008,0.05))]
    for n,(lx,ly,lz),(sx,sy,sz) in parts:
        c=UsdGeom.Cube.Define(stage,path+"/"+n); c.GetSizeAttr().Set(1.0); cp=c.GetPrim()
        cx=UsdGeom.Xformable(cp); cx.AddTranslateOp().Set(Gf.Vec3d(lx,ly,lz)); cx.AddScaleOp().Set(Gf.Vec3f(sx,sy,sz))
        c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)]); UsdPhysics.CollisionAPI.Apply(cp)
TCOL=(0.40,0.42,0.46)
for k,x in [("R",3.54),("B",3.74),("G",3.94)]: make_tote("/World/Tote_"+k,(x,-7.75,0.952),TCOL)
CUBES=[("R",3.54,(0.9,0.1,0.1)),("B",3.74,(0.1,0.2,0.9)),("G",3.94,(0.1,0.7,0.1))]
for k,x,col in CUBES: make_cube("/World/SortCube_"+k,(x,-6.95,1.04),0.035,col)
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0); world.reset()
tw={k:SingleRigidPrim("/World/Tote_"+k,name="t_"+k) for k,_ in [("R",0),("B",0),("G",0)]}
S={"n":0}
def _step(dt):
    try:
        S["n"]+=1
        if S["n"]%90==0:
            msg=" ".join("%s=(%.2f,%.2f,%.2f)"%(k, tw[k].get_world_pose()[0][0],tw[k].get_world_pose()[0][1],tw[k].get_world_pose()[0][2]) for k in tw)
            print("STOTE",msg, flush=True)
    except Exception:
        print("STOTE_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("SMALLTOTES_STARTED", flush=True)
