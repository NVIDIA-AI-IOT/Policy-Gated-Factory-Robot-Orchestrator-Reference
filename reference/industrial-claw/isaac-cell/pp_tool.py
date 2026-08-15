# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# pp_tool.py
# Persistent pick-and-place TOOL for an external/agentic caller (e.g. over ROS).
# Run this ONCE in the Script Editor. It sets up the arm and idles.
# Then the agent simply calls:
#     pp_tool.pick_and_place([px, py, pz], [qx, qy, qz])
# where the two args are world positions in meters (pick from -> place to).

import traceback
import numpy as np
import omni.timeline, omni.physx
from isaacsim.core.api import World
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController


class PickPlaceTool:
    def __init__(self, arm_prim_path="/Workcell/Franka_Left", lift_height=1.30):
        # tear down any previous instance/subscription
        prev = globals().get("pp_tool")
        if prev is not None:
            try:
                prev._sub.unsubscribe()
            except Exception:
                pass
        try:
            World.clear_instance()
        except Exception:
            pass

        self.world = World(physics_dt=1.0/60.0, rendering_dt=1.0/60.0, stage_units_in_meters=1.0)
        self.franka = Franka(prim_path=arm_prim_path, name="pp_tool_arm")
        self.world.scene.add(self.franka)
        self.world.reset()

        self.ctrl = PickPlaceController(name="pp_tool_ctrl", gripper=self.franka.gripper,
                                        robot_articulation=self.franka,
                                        end_effector_initial_height=lift_height)
        self.franka.gripper.set_joint_positions(self.franka.gripper.joint_opened_positions)
        self.ctrl.reset()

        self._job = None      # (pick, place) or None when idle
        self._busy = False

        omni.timeline.get_timeline_interface().play()
        self._sub = omni.physx.get_physx_interface().subscribe_physics_step_events(self._on_step)

    # ---- the API the agent calls ----
    def pick_and_place(self, pick, place):
        """Command one pick-and-place. pick/place = [x, y, z] world meters. Returns True if accepted."""
        if self._busy:
            print("[pp_tool] busy — ignoring new command until current one finishes")
            return False
        self._job = (np.asarray(pick, dtype=float), np.asarray(place, dtype=float))
        self._busy = True
        self.ctrl.reset()
        print(f"[pp_tool] accepted: {self._job[0].tolist()} -> {self._job[1].tolist()}")
        return True

    def is_busy(self):
        return self._busy

    # ---- internal physics-step driver ----
    def _on_step(self, dt):
        try:
            if self._job is None:
                return
            jp = self.franka.get_joint_positions()
            if jp is None:
                return
            pick, place = self._job
            act = self.ctrl.forward(picking_position=pick, placing_position=place,
                                    current_joint_positions=jp, end_effector_offset=np.array([0, 0, 0]))
            self.franka.apply_action(act)
            if self.ctrl.is_done():
                print(f"[pp_tool] DONE: {pick.tolist()} -> {place.tolist()}")
                self._job = None
                self._busy = False
        except Exception:
            print("PP_TOOL_ERROR:\n" + traceback.format_exc())


pp_tool = PickPlaceTool()
print(">>> pp_tool READY.  Agent calls:  pp_tool.pick_and_place([px,py,pz], [qx,qy,qz])")
