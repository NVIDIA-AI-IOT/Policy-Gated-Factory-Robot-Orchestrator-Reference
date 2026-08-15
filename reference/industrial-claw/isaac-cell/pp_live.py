# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import asyncio
import numpy as np
import omni.timeline
from isaacsim.core.api import World
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController

TASKS = [
    (np.array([-0.50, 0.00, 0.965]), np.array([-0.90, 0.38, 1.00])),
    (np.array([-0.40, 0.18, 0.965]), np.array([-0.90, 0.45, 1.00])),
    (np.array([-0.55, -0.18, 0.965]), np.array([-0.90, 0.52, 1.00])),
]
S = {"i": 0}


async def _setup():
    world = World.instance() or World()
    # remove any stale callback/object from a previous run
    try:
        world.remove_physics_callback("pp_live_cb")
    except Exception:
        pass
    if world.scene.object_exists("franka_live"):
        franka = world.scene.get_object("franka_live")
    else:
        franka = Franka(prim_path="/Workcell/Franka_Left", name="franka_live")
        world.scene.add(franka)

    # async reset = the editor-safe way to initialize physics + the articulation
    await world.reset_async()

    ctrl = PickPlaceController(name="pp_live", gripper=franka.gripper,
                               robot_articulation=franka, end_effector_initial_height=1.30)
    franka.gripper.set_joint_positions(franka.gripper.joint_opened_positions)
    ctrl.reset()
    S["i"] = 0

    def _step(dt):
        if S["i"] >= len(TASKS):
            return
        jp = franka.get_joint_positions()
        if jp is None:
            return
        pick, place = TASKS[S["i"]]
        act = ctrl.forward(picking_position=pick, placing_position=place,
                           current_joint_positions=jp, end_effector_offset=np.array([0, 0, 0]))
        franka.apply_action(act)
        if ctrl.is_done():
            print("placed block", S["i"])
            S["i"] += 1
            ctrl.reset()

    world.add_physics_callback("pp_live_cb", _step)
    omni.timeline.get_timeline_interface().play()
    print(">>> pick-and-place attached and playing — the left arm will move now")


asyncio.ensure_future(_setup())
