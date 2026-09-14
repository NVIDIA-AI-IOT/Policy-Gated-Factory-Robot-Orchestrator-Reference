# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# warehouse_tools.py  — Stage 1
# Agentic warehouse tool registry. Run ONCE in the Script Editor.
# Then the agent calls:  wt.list_cameras(), wt.capture("overhead"),
#   wt.aim_camera("pantilt",[x,y,z]), wt.list_objects(),
#   wt.pick_and_place(pick,place), wt.pick_object("red_block",place),
#   wt.home(), wt.reset_scene(), wt.stack(["red_block","blue_block"], base)
import traceback
import numpy as np
import omni.timeline, omni.physx, omni.usd
from pxr import UsdGeom, Usd, Gf
from isaacsim.core.api import World
from isaacsim.core.api.objects import DynamicCuboid, FixedCuboid
from isaacsim.core.utils.viewports import set_camera_view
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController

BLOCKS = {  # name -> prim path
    "red_block": "/Workcell/Block_Red",
    "blue_block": "/Workcell/Block_Blue",
    "green_block": "/Workcell/Block_Green",
}
BIN = np.array([-0.90, 0.45, 1.00])

# Conveyor geometry (on the warehouse floor, away from the table)
BELT_CENTER = np.array([2.5, -1.5, 0.15])
BELT_SCALE = np.array([4.0, 0.7, 0.30])           # x len, y width, z height
BELT_TOP = BELT_CENTER[2] + BELT_SCALE[2] / 2.0    # = 0.30
BELT_X0, BELT_X1 = BELT_CENTER[0] - BELT_SCALE[0]/2, BELT_CENTER[0] + BELT_SCALE[0]/2
PKG_SIZE = 0.15


class WarehouseTools:
    def __init__(self):
        prev = globals().get("wt")
        if prev is not None and getattr(prev, "_sub", None) is not None:
            try: prev._sub.unsubscribe()
            except Exception: pass
        try: World.clear_instance()
        except Exception: pass

        self.stage = omni.usd.get_context().get_stage()
        self.world = World(physics_dt=1.0/60.0, rendering_dt=1.0/60.0, stage_units_in_meters=1.0)
        self.arm = Franka(prim_path="/Workcell/Franka_Left", name="wt_arm")
        self.world.scene.add(self.arm)

        # --- conveyor: static belt + dynamic packages riding on it ---
        self._conv_speed = 0.0
        self._packages = []
        if not self.stage.GetPrimAtPath("/World/Conveyor/belt").IsValid():
            self.world.scene.add(FixedCuboid(prim_path="/World/Conveyor/belt",
                                             name="belt", position=BELT_CENTER,
                                             scale=BELT_SCALE, color=np.array([0.15, 0.15, 0.18])))
        for i in range(3):
            path = f"/World/Conveyor/pkg{i}"
            pos = np.array([BELT_X0 + 0.6 + i*0.8, BELT_CENTER[1], BELT_TOP + PKG_SIZE/2 + 0.01])
            pkg = DynamicCuboid(prim_path=path, name=f"pkg{i}", position=pos,
                                size=PKG_SIZE, color=np.array([0.8, 0.5, 0.1]))
            self.world.scene.add(pkg)
            self._packages.append(pkg)

        self.world.reset()
        self.ctrl = PickPlaceController(name="wt_ctrl", gripper=self.arm.gripper,
                                        robot_articulation=self.arm, end_effector_initial_height=1.30)
        self.arm.gripper.set_joint_positions(self.arm.gripper.joint_opened_positions)
        self.ctrl.reset()

        self._queue = []      # list of (pick, place)
        self._cur = None

        # create agent viewpoints (table center ~ (0,0,1))
        self._cams = {}
        self._ensure_cam("overhead", [0.0, 0.0, 4.5], [0.0, 0.0, 0.9])
        self._ensure_cam("front",    [0.0, -6.0, 2.3], [0.0, 0.0, 1.0])
        self._ensure_cam("side",     [4.5, 0.0, 2.3],  [0.0, 0.0, 1.0])
        self._ensure_cam("pantilt",  [2.5, -2.5, 2.5], [-0.4, 0.1, 1.0])

        omni.timeline.get_timeline_interface().play()
        self._sub = omni.physx.get_physx_interface().subscribe_physics_step_events(self._on_step)
        print(">>> wt READY. cameras:", list(self._cams.keys()))

    # ---------- helpers ----------
    def _ensure_cam(self, name, eye, target):
        path = "/World/AgentCams/" + name
        if not self.stage.GetPrimAtPath(path).IsValid():
            UsdGeom.Camera.Define(self.stage, path)
        set_camera_view(eye=eye, target=target, camera_prim_path=path)
        self._cams[name] = path
        return path

    def _world_pos(self, prim_path):
        p = self.stage.GetPrimAtPath(prim_path)
        if not p.IsValid():
            return None
        m = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(p)
        t = m.ExtractTranslation()
        return np.array([t[0], t[1], t[2]])

    # ---------- PERCEPTION ----------
    def list_cameras(self):
        return dict(self._cams)

    def capture(self, camera="front", out="/scripts/view.png"):
        try:
            import omni.kit.viewport.utility as vpu
            path = self._cams.get(camera, camera)
            vp = vpu.get_active_viewport()
            vp.camera_path = path
            vpu.capture_viewport_to_file(vp, out)
            print(f"[wt] capture {camera} -> {out}")
            return out
        except Exception:
            print("WT_CAPTURE_ERROR:\n" + traceback.format_exc()); return None

    def aim_camera(self, camera, target_xyz):
        # pan/tilt: keep camera position, re-aim at target
        path = self._cams.get(camera, camera)
        eye = self._world_pos(path)
        if eye is None:
            print("[wt] unknown camera", camera); return False
        set_camera_view(eye=eye.tolist(), target=list(target_xyz), camera_prim_path=path)
        return True

    # ---------- SCENE ----------
    def list_objects(self):
        out = {}
        for name, path in BLOCKS.items():
            pos = self._world_pos(path)
            if pos is not None:
                out[name] = [round(float(x), 3) for x in pos]
        for i in range(len(self._packages)):
            pos = self._world_pos(f"/World/Conveyor/pkg{i}")
            if pos is not None:
                out[f"package{i}"] = [round(float(x), 3) for x in pos]
        return out

    # ---------- ACTIONS ----------
    def pick_and_place(self, pick, place):
        self._queue.append((np.asarray(pick, float), np.asarray(place, float)))
        print(f"[wt] queued pick_and_place ({len(self._queue)} pending)")
        return True

    def pick_object(self, name, place):
        pos = self._world_pos(BLOCKS.get(name, name))
        if pos is None:
            print("[wt] unknown object", name); return False
        pos = pos.copy(); pos[2] = max(pos[2], 0.965)
        return self.pick_and_place(pos, place)

    def stack(self, names, base):
        base = np.asarray(base, float)
        for i, n in enumerate(names):
            self.pick_object(n, base + np.array([0, 0, 0.05 * i]))
        return True

    def reset_scene(self):
        self._queue.clear(); self._cur = None
        self.world.reset(); self.ctrl.reset()
        self.arm.gripper.set_joint_positions(self.arm.gripper.joint_opened_positions)
        print("[wt] scene reset")
        return True

    def home(self):
        self._queue.clear(); self._cur = None
        home_q = np.array([0.0, -1.0, 0.0, -2.2, 0.0, 2.0, 0.8, 0.04, 0.04])
        try:
            self.arm.set_joint_positions(home_q)
        except Exception:
            print("WT_HOME_ERROR:\n" + traceback.format_exc())
        return True

    def is_busy(self):
        return self._cur is not None or len(self._queue) > 0

    # ---------- CONVEYOR ----------
    def conveyor_set_speed(self, v):
        """Set belt speed in m/s along +x. 0 stops it. Negative reverses."""
        self._conv_speed = float(v)
        print(f"[wt] conveyor speed = {self._conv_speed} m/s")
        return True

    def conveyor_stop(self):
        return self.conveyor_set_speed(0.0)

    def _drive_conveyor(self):
        if not self._packages:
            return
        for pkg in self._packages:
            try:
                pos, _ = pkg.get_world_pose()
                on_belt = (BELT_X0 - 0.1 <= pos[0] <= BELT_X1 + 0.1
                           and abs(pos[2] - (BELT_TOP + PKG_SIZE/2)) < 0.2)
                if self._conv_speed != 0.0 and on_belt:
                    if pos[0] > BELT_X1:          # recycle to the start
                        pkg.set_world_pose(np.array([BELT_X0 + 0.3, BELT_CENTER[1],
                                                     BELT_TOP + PKG_SIZE/2 + 0.01]))
                        pkg.set_linear_velocity(np.zeros(3))
                    else:
                        lv = pkg.get_linear_velocity()
                        pkg.set_linear_velocity(np.array([self._conv_speed, 0.0, float(lv[2])]))
            except Exception:
                pass

    # ---------- driver ----------
    def _on_step(self, dt):
        try:
            self._drive_conveyor()
            if self._cur is None:
                if self._queue:
                    self._cur = self._queue.pop(0)
                    self.ctrl.reset()
                else:
                    return
            jp = self.arm.get_joint_positions()
            if jp is None:
                return
            pick, place = self._cur
            act = self.ctrl.forward(picking_position=pick, placing_position=place,
                                    current_joint_positions=jp, end_effector_offset=np.array([0, 0, 0]))
            self.arm.apply_action(act)
            if self.ctrl.is_done():
                print(f"[wt] DONE {pick.tolist()} -> {place.tolist()}")
                self._cur = None
        except Exception:
            print("WT_STEP_ERROR:\n" + traceback.format_exc())


wt = WarehouseTools()
print(">>> warehouse_tools ready. Try: wt.list_objects() ; wt.capture('overhead') ; wt.pick_object('red_block', wt.list_objects() and [-0.9,0.45,1.0])")
