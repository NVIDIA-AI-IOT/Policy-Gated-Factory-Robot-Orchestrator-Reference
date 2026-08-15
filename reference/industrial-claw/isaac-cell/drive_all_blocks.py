#!/isaac-sim/python.sh
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Left Franka picks all 3 blocks off the table and drops each into the KLT bin.
from isaacsim import SimulationApp
import os
HEADLESS = os.environ.get("HEADLESS", "0") == "1"
# Base app: it reliably initializes the robot articulation so the arm actually
# moves. (The full editor experience renders nicer but fails to init the
# articulation in a standalone control loop.) Enable RTX real-time + material
# loading so the scene still renders with materials rather than flat white.
simulation_app = SimulationApp({
    "headless": HEADLESS,
    "renderer": "RayTracedLighting",
})
# Make sure the material/MDL loader extensions are on so MDL-textured assets
# (warehouse, bin) don't render as flat white.
import carb
from isaacsim.core.utils.extensions import enable_extension
for _ext in ("omni.kit.material.library", "omni.mdl"):
    try:
        enable_extension(_ext)
    except Exception as _e:
        carb.log_warn(f"could not enable {_ext}: {_e}")

import numpy as np
from isaacsim.core.api import World
from isaacsim.core.utils.stage import open_stage
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController

SCENE = "/scripts/my_pick_place.usda"
ARM = "/Workcell/Franka_Left"
EE_OFFSET = np.array([0.0, 0.0, 0.0])
EE_INIT_H = 1.30

# (pick world pos, place world pos). Bin is at (-0.9, 0.45); drop spots spread in y.
TASKS = [
    (np.array([-0.50, 0.00, 0.965]), np.array([-0.90, 0.38, 1.00])),   # red
    (np.array([-0.40, 0.18, 0.965]), np.array([-0.90, 0.45, 1.00])),   # blue
    (np.array([-0.55, -0.18, 0.965]), np.array([-0.90, 0.52, 1.00])),  # green
]

assert open_stage(SCENE), "failed to open scene"
world = World(physics_dt=1.0/60.0, rendering_dt=1.0/60.0, stage_units_in_meters=1.0)
franka = world.scene.add(Franka(prim_path=ARM, name="franka_left"))
world.reset()

# The full editor experience starts paused — explicitly play + warm up so the
# robot Articulation gets its physics handles before we command it.
import omni.timeline
omni.timeline.get_timeline_interface().play()
for _ in range(40):
    world.step(render=not HEADLESS)

controller = PickPlaceController(name="pp_left", gripper=franka.gripper,
                                 robot_articulation=franka, end_effector_initial_height=EE_INIT_H)
franka.gripper.set_joint_positions(franka.gripper.joint_opened_positions)
controller.reset()

# Aim the viewport camera at the workcell (table + left arm) so the user sees
# the action, not a default faraway angle.
try:
    from isaacsim.core.utils.viewports import set_camera_view
    set_camera_view(eye=[0.0, -6.0, 2.3], target=[0.0, 0.0, 1.2])
    print("[drive] camera aimed at workcell", flush=True)
except Exception as e:
    print("[drive] camera set failed:", e, flush=True)

print("[drive] ready; placing", len(TASKS), "blocks into the bin", flush=True)

idx, step = 0, 0
while simulation_app.is_running():
    world.step(render=not HEADLESS)
    step += 1
    if step % 100 == 0:
        print(f"[drive] heartbeat step={step} working_on_block={idx}", flush=True)
    if idx >= len(TASKS):
        # loop: reset the scene and run the pick-and-place again so it's watchable
        print("[drive] cycle done -> resetting to loop", flush=True)
        world.reset()
        franka.gripper.set_joint_positions(franka.gripper.joint_opened_positions)
        controller.reset()
        idx = 0
        continue
    jp = franka.get_joint_positions()
    if jp is None:
        continue  # articulation not ready yet
    pick, place = TASKS[idx]
    try:
        actions = controller.forward(picking_position=pick, placing_position=place,
                                     current_joint_positions=jp,
                                     end_effector_offset=EE_OFFSET)
        franka.apply_action(actions)
    except Exception as e:
        print("[drive] error at step", step, ":", e, flush=True); break
    if controller.is_done():
        print(f"[drive] placed block #{idx} at step {step}", flush=True)
        idx += 1
        controller.reset()
        if idx >= len(TASKS):
            print("[drive] >>> ALL_BLOCKS_DONE at step", step, flush=True)
            if HEADLESS:
                break

print("[drive] closing", flush=True)
simulation_app.close()
