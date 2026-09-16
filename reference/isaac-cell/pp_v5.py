# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import traceback
import numpy as np
import omni.timeline, omni.physx
from isaacsim.core.api import World
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController

TASKS = [
    (np.array([-0.50, 0.00, 0.965]), np.array([-0.90, 0.38, 1.00])),
    (np.array([-0.40, 0.18, 0.965]), np.array([-0.90, 0.45, 1.00])),
    (np.array([-0.55, -0.18, 0.965]), np.array([-0.90, 0.52, 1.00])),
]
S = {"i": 0}

# unsubscribe a previous run's callback if present
_old = globals().get("_PP_SUB")
if _old is not None:
    try:
        _old.unsubscribe()
    except Exception:
        pass
    globals()["_PP_SUB"] = None

try:
    try:
        World.clear_instance()
    except Exception:
        pass

    world = World(physics_dt=1.0/60.0, rendering_dt=1.0/60.0, stage_units_in_meters=1.0)
    franka = Franka(prim_path="/Workcell/Franka_Left", name="franka_live")
    world.scene.add(franka)
    world.reset()

    ctrl = PickPlaceController(name="pp_live", gripper=franka.gripper,
                               robot_articulation=franka, end_effector_initial_height=1.30)
    franka.gripper.set_joint_positions(franka.gripper.joint_opened_positions)
    ctrl.reset()
    S["i"] = 0

    def _step(dt):
        try:
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
                print("placed block", S["i"]); S["i"] += 1; ctrl.reset()
        except Exception:
            print("PP_STEP_ERROR:\n" + traceback.format_exc())

    omni.timeline.get_timeline_interface().play()
    _PP_SUB = omni.physx.get_physx_interface().subscribe_physics_step_events(_step)
    print(">>> OK: subscribed to physics; arm should move now")
except Exception:
    print("PP_SETUP_ERROR:\n" + traceback.format_exc())
