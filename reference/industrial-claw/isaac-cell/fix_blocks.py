# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# fix_blocks.py (v3) — replace the broken referenced blocks with raw-USD cubes (proven collision).
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
    xf.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center]))
    xf.AddScaleOp().Set(Gf.Vec3f(size,size,size))
    c.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p); UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.1)
    return path
# hide the broken originals
for n in ["Block_Red","Block_Blue","Block_Green"]:
    pr=stage.GetPrimAtPath("/Workcell/"+n)
    if pr.IsValid(): UsdGeom.Imageable(pr).MakeInvisible()
NEW={"SortCube_R":(np.array([3.54,-6.95,1.05]),(0.9,0.1,0.1)),
     "SortCube_B":(np.array([3.74,-6.95,1.05]),(0.1,0.2,0.9)),
     "SortCube_G":(np.array([3.94,-6.95,1.05]),(0.1,0.7,0.1))}
for n,(pos,col) in NEW.items(): make_cube("/World/"+n, pos, 0.05, col)
make_cube("/World/FloorTest", np.array([2.0,-9.0,0.5]), 0.05, (0.9,0.9,0.1))   # control: should land on floor
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0); world.reset()
prims={n:SingleRigidPrim("/World/"+n, name="c_"+n) for n in list(NEW)+["FloorTest"]}
S={"n":0}
def _step(dt):
    try:
        S["n"]+=1
        if S["n"]%60==0:
            msg=" ".join("%s=%.2f"%(n.replace("SortCube_","").replace("FloorTest","FLOOR"), prims[n].get_world_pose()[0][2]) for n in prims)
            print("REST n=%d %s"%(S["n"],msg), flush=True)
    except Exception:
        print("REST_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("FIX_STARTED", flush=True)
