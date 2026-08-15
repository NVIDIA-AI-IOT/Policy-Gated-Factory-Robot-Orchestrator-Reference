#!/isaac-sim/python.sh
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Drive the LEFT Franka in our custom scene to pick a block off the table
# and place it at a reachable spot on the table.
from isaacsim import SimulationApp

# headless can be overridden with env HEADLESS=1
import os
HEADLESS = os.environ.get("HEADLESS", "0") == "1"
simulation_app = SimulationApp({"headless": HEADLESS})

import numpy as np
from isaacsim.core.api import World
from isaacsim.core.utils.stage import open_stage
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController

SCENE = "/scripts/my_pick_place.usda"
ARM_PRIM = "/Workcell/Franka_Left"

# World positions (meters). Table top is z=0.94; red block center ~0.9635.
PICK_POS  = np.array([-0.50, 0.00, 0.965])   # Block_Red on the table
PLACE_POS = np.array([-0.55, 0.45, 0.965])   # empty reachable spot near the bin
EE_OFFSET = np.array([0.0, 0.0, 0.0])
EE_INIT_H = 1.30                              # lift height in world frame (above table)

print("[drive] opening scene:", SCENE, flush=True)
assert open_stage(SCENE), "failed to open scene"

world = World(physics_dt=1.0/60.0, rendering_dt=1.0/60.0, stage_units_in_meters=1.0)
franka = world.scene.add(Franka(prim_path=ARM_PRIM, name="franka_left"))
print("[drive] added Franka, resetting world...", flush=True)
world.reset()

controller = PickPlaceController(
    name="pp_left",
    gripper=franka.gripper,
    robot_articulation=franka,
    end_effector_initial_height=EE_INIT_H,
)
franka.gripper.set_joint_positions(franka.gripper.joint_opened_positions)
controller.reset()
print("[drive] controller ready; starting loop. pick=", PICK_POS, "place=", PLACE_POS, flush=True)

done_announced = False
step = 0
while simulation_app.is_running():
    world.step(render=not HEADLESS)
    step += 1
    try:
        actions = controller.forward(
            picking_position=PICK_POS,
            placing_position=PLACE_POS,
            current_joint_positions=franka.get_joint_positions(),
            end_effector_offset=EE_OFFSET,
        )
        franka.apply_action(actions)
    except Exception as e:
        print("[drive] forward() error at step", step, ":", e, flush=True)
        break
    if controller.is_done() and not done_announced:
        print("[drive] >>> PICK_PLACE_DONE at step", step, flush=True)
        done_announced = True
        if HEADLESS:
            break

print("[drive] closing", flush=True)
simulation_app.close()
