# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import omni.usd
from isaacsim.core.utils.stage import open_stage
from isaacsim.core.api import World
from isaacsim.robot.manipulators.examples.franka import Franka
from pxr import UsdGeom, Usd

open_stage("/scripts/my_pick_place.usda")
w = World(stage_units_in_meters=1.0)
fl = w.scene.add(Franka(prim_path="/Workcell/Franka_Left", name="fl"))
fr = w.scene.add(Franka(prim_path="/Workcell/Franka_Right", name="fr"))
w.reset()
for _ in range(90):
    w.step(render=False)

pl, _ = fl.get_world_pose()
pr, _ = fr.get_world_pose()
print(f"[pos] LEFT arm base  = ({pl[0]:.3f}, {pl[1]:.3f}, {pl[2]:.3f})  (expected ~ -0.9, 0, 0.94)", flush=True)
print(f"[pos] RIGHT arm base = ({pr[0]:.3f}, {pr[1]:.3f}, {pr[2]:.3f})  (expected ~  0.9, 0, 0.94)", flush=True)

st = omni.usd.get_context().get_stage()
bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
r = bb.ComputeWorldBound(st.GetPrimAtPath("/Workcell/BigTable")).ComputeAlignedRange()
mn, mx = r.GetMin(), r.GetMax()
print(f"[bbox] table spans x[{mn[0]:.2f},{mx[0]:.2f}] y[{mn[1]:.2f},{mx[1]:.2f}] z[{mn[2]:.2f},{mx[2]:.2f}]", flush=True)
print("[diag2] DONE", flush=True)
sim.close()
