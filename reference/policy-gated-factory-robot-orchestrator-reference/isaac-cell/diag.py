# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})
import omni.usd
from isaacsim.core.utils.stage import open_stage

open_stage("/scripts/my_pick_place.usda")
st = omni.usd.get_context().get_stage()
print("[diag] AFTER open_stage, top-level:", [p.GetName() for p in st.GetPseudoRoot().GetChildren()], flush=True)
for path in ["/Workcell", "/Workcell/BigTable/Top", "/Workcell/Block_Red",
             "/Workcell/Franka_Left", "/Workcell/Franka_Left/panda_link0", "/Root", "/PhysicsScene"]:
    print(f"[diag]   {path}: valid={st.GetPrimAtPath(path).IsValid()}", flush=True)

from isaacsim.core.api import World
w = World(stage_units_in_meters=1.0)
st2 = omni.usd.get_context().get_stage()
print("[diag] AFTER World(), top-level:", [p.GetName() for p in st2.GetPseudoRoot().GetChildren()], flush=True)
for path in ["/Workcell", "/Root", "/Workcell/Block_Red"]:
    print(f"[diag]   {path}: valid={st2.GetPrimAtPath(path).IsValid()}", flush=True)

print("[diag] DONE", flush=True)
sim.close()
