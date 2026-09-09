# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True, "width": 1280, "height": 720})
import omni.kit.app, omni.usd
from isaacsim.core.utils.stage import open_stage
from isaacsim.core.utils.viewports import set_camera_view
open_stage("/scripts/factory_scene.usda")
app = omni.kit.app.get_app(); ctx = omni.usd.get_context()
for _ in range(400):
    app.update()
    if ctx.get_stage_loading_status()[2] == 0:
        break
for _ in range(120): app.update()
set_camera_view(eye=[6.0, -6.0, 4.0], target=[0.0, 0.0, 0.8])
for _ in range(120): app.update()
try:
    import omni.kit.viewport.utility as vpu
    vp = vpu.get_active_viewport()
    vpu.capture_viewport_to_file(vp, "/scripts/factory_preview.png")
    for _ in range(120): app.update()
    print("PREVIEW_SAVED")
except Exception as e:
    print("PREVIEW_ERROR:", e)
sim.close()
