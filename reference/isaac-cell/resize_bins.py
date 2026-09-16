# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# resize_bins.py — shrink the 3 bins to grippable size (~4-7cm) + shrink sort-cubes to fit. Verify rest.
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
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.1)
SCALE=0.22
BINS=[("Bin",3.54),("Bin_B",3.74),("Bin_C",3.94)]
for name,x in BINS:
    p=stage.GetPrimAtPath("/Workcell/"+name)
    if not p.IsValid(): continue
    a=UsdPhysics.RigidBodyAPI(p).GetKinematicEnabledAttr()
    if a: a.Set(False)
    xf=UsdGeom.Xformable(p); xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(x,-7.75,1.02)); xf.AddScaleOp().Set(Gf.Vec3f(SCALE,SCALE,SCALE))
CUBES=[("/World/SortCube_R",3.54,(0.9,0.1,0.1)),("/World/SortCube_B",3.74,(0.1,0.2,0.9)),("/World/SortCube_G",3.94,(0.1,0.7,0.1))]
for path,x,col in CUBES: make_cube(path,(x,-6.95,1.05),0.025,col)
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0); world.reset()
bw={name:SingleRigidPrim("/Workcell/"+name,name="b_"+name) for name,_ in BINS}
cw={path:SingleRigidPrim(path,name="c"+path[-1]) for path,_,_ in CUBES}
S={"n":0}
def _step(dt):
    try:
        S["n"]+=1
        if S["n"]%90==0:
            bz=" ".join("%s=(%.2f,%.2f,%.2f)"%(n, bw[n].get_world_pose()[0][0],bw[n].get_world_pose()[0][1],bw[n].get_world_pose()[0][2]) for n,_ in BINS)
            cz=" ".join("%s z%.2f"%(p[-1], cw[p].get_world_pose()[0][2]) for p,_,_ in CUBES)
            print("RZ bins:",bz," cubes:",cz, flush=True)
    except Exception:
        print("RZ_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("RESIZE_STARTED", flush=True)
