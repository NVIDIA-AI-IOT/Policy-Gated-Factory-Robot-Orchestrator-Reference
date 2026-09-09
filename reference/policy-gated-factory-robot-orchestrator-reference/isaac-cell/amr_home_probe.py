# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_home_probe.py — raise AMR arm to a visible home pose, and measure the workcell/table extent.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.types import ArticulationAction
from pxr import UsdGeom, Usd
stage=omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
amr=SingleArticulation(prim_path="/MobileBot", name="amr_home"); world.scene.add(amr); world.reset()
# --- measure workcell pieces (so I know the clear directions around WP5) ---
bbc=UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
wc=stage.GetPrimAtPath("/Workcell")
if wc and wc.IsValid():
    for ch in wc.GetChildren():
        b=bbc.ComputeWorldBound(ch).ComputeAlignedRange()
        if b.IsEmpty(): continue
        mn,mx=b.GetMin(),b.GetMax()
        print("WC %-22s x[%.2f,%.2f] y[%.2f,%.2f] z[%.2f,%.2f]"%(ch.GetName(),mn[0],mx[0],mn[1],mx[1],mn[2],mx[2]),flush=True)
# --- raise arm to a visible home pose, hold at WP5, gripper open ---
WP5=np.array([3.76,-9.21]); HOME=np.array([0.0,-1.0,0.0,-2.2,0.0,2.0,0.785])
q=np.array(amr.get_joint_positions(),float)
q[0]=WP5[0]-4.54; q[1]=WP5[1]+4.8; q[2]=0.0; q[3:10]=HOME; q[10:12]=[0.04,0.04]
amr.set_joint_positions(q)
def _step(dt):
    try:
        jp=np.array(amr.get_joint_positions(),float); tgt=jp.copy()
        tgt[0]=WP5[0]-4.54; tgt[1]=WP5[1]+4.8; tgt[2]=0.0; tgt[3:10]=HOME; tgt[10:12]=[0.04,0.04]
        amr.apply_action(ArticulationAction(joint_positions=tgt))
    except Exception:
        print("HOME_ERR:\n"+traceback.format_exc(),flush=True); globals()["_DEMO_SUB"].unsubscribe()
omni.timeline.get_timeline_interface().play()
_DEMO_SUB=omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
print("HOME_RAISED", flush=True)
