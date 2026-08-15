# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# amr_stop_diag.py — stop the running loop, revert to clean authored pose, and read arm drive gains.
import omni.usd, omni.timeline, omni.physx, traceback
import numpy as np
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
stage=omni.usd.get_context().get_stage()
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
try: World.clear_instance()
except Exception: pass
world=World(physics_dt=1/60., rendering_dt=1/60., stage_units_in_meters=1.0)
amr=SingleArticulation(prim_path="/MobileBot", name="amr_diag"); world.scene.add(amr); world.reset()
try:
    ctrl=amr.get_articulation_controller()
    kp,kd=ctrl.get_gains()
    print("DOFS", list(amr.dof_names), flush=True)
    print("KP", np.array(kp).round(1).tolist(), flush=True)
    print("KD", np.array(kd).round(1).tolist(), flush=True)
except Exception:
    print("GAIN_READ_ERR:\n"+traceback.format_exc(), flush=True)
omni.timeline.get_timeline_interface().stop()   # revert to clean authored pose, physics halted
print("STOPPED_CLEAN", flush=True)
