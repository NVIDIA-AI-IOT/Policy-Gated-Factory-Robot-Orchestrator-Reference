# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# reset_physics.py — recover from an invalidated simulation view: stop+restart the timeline to rebuild PhysX.
import omni.timeline
from isaacsim.core.api import World
old=globals().get("_DEMO_SUB")
if old is not None:
    try: old.unsubscribe()
    except Exception: pass
    globals()["_DEMO_SUB"]=None
try: World.clear_instance()
except Exception: pass
tl=omni.timeline.get_timeline_interface()
tl.stop(); tl.play()
print("PHYS_RESET done", flush=True)
