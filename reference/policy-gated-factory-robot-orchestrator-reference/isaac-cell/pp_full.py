# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import asyncio, traceback
import numpy as np
import omni.timeline, omni.kit.app, omni.usd
from isaacsim.core.utils.stage import open_stage
from isaacsim.core.utils.viewports import set_camera_view
from isaacsim.core.api import World
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController

SCENE = "/scripts/my_pick_place.usda"
TASKS = [
    (np.array([-0.50, 0.00, 0.965]), np.array([-0.90, 0.38, 1.00])),
    (np.array([-0.40, 0.18, 0.965]), np.array([-0.90, 0.45, 1.00])),
    (np.array([-0.55, -0.18, 0.965]), np.array([-0.90, 0.52, 1.00])),
]
S = {"i": 0}


async def _run():
    try:
        app = omni.kit.app.get_app()
        ctx = omni.usd.get_context()
        open_stage(SCENE)
        # wait until the stage + remote assets finish loading
        for _ in range(2000):
            await app.next_update_async()
            msg, loaded, total = ctx.get_stage_loading_status()
            st = ctx.get_stage()
            ready = st and st.GetPrimAtPath("/Workcell/Franka_Left/panda_link0").IsValid()
            if ready and total == 0:
                break
        for _ in range(120):           # settle
            await app.next_update_async()

        set_camera_view(eye=[0.0, -6.0, 2.3], target=[0.0, 0.0, 1.2])

        world = World.instance() or World()
        franka = Franka(prim_path="/Workcell/Franka_Left", name="franka_live")
        world.scene.add(franka)
        await world.reset_async()      # editor-safe init -> creates physics view

        ctrl = PickPlaceController(name="pp_live", gripper=franka.gripper,
                                   robot_articulation=franka, end_effector_initial_height=1.30)
        franka.gripper.set_joint_positions(franka.gripper.joint_opened_positions)
        ctrl.reset()

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
                print("PP placed block", S["i"], flush=True); S["i"] += 1; ctrl.reset()

        world.add_physics_callback("pp_live_cb", _step)
        omni.timeline.get_timeline_interface().play()
        print(">>> PP_RUNNING: pick-and-place attached and playing", flush=True)
    except Exception:
        print("PP_SETUP_ERROR:\n" + traceback.format_exc(), flush=True)


asyncio.ensure_future(_run())
