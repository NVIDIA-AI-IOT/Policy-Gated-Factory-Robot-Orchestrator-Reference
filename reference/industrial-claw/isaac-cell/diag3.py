# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import omni.usd
from isaacsim.core.utils.stage import open_stage
open_stage("/scripts/my_pick_place.usda")
from pxr import Usd, UsdGeom
st = omni.usd.get_context().get_stage()
bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
for path in ["/Workcell/Franka_Left","/Workcell/Franka_Right",
             "/Workcell/Franka_Left/Camera_Azure_Left","/Workcell/Franka_Right/Camera_Azure_Right",
             "/Workcell/Rack","/Workcell/Bin"]:
    p = st.GetPrimAtPath(path)
    if not p.IsValid(): print(f"[bb] {path}: INVALID"); continue
    r = bb.ComputeWorldBound(p).ComputeAlignedRange()
    mn,mx = r.GetMin(), r.GetMax()
    if mx[0]>1e30: print(f"[bb] {path}: empty/no-geom"); continue
    print(f"[bb] {path}: x[{mn[0]:.2f},{mx[0]:.2f}] y[{mn[1]:.2f},{mx[1]:.2f}] z[{mn[2]:.2f},{mx[2]:.2f}] size=({mx[0]-mn[0]:.2f},{mx[1]-mn[1]:.2f},{mx[2]-mn[2]:.2f})", flush=True)
print("[diag3] DONE", flush=True)
sim.close()
