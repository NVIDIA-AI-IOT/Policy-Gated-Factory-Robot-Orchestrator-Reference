# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""CellRuntime — the floor node as a class (port of ic_node_v2.py, 2026-07-07).

Brain commands -> controller skills, physics-verified results. All state that
used to live in exec'd module globals (S, wr, wrp, CUBES, Q, ...) is owned by
the instance; nothing here can be clobbered by another script.
"""
import json
import os
import random
import traceback

os.environ.setdefault("ROS_DOMAIN_ID", "0")
os.environ.setdefault("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")

import numpy as np
import omni.physx
import omni.timeline
import omni.usd
import rclpy
from pxr import Gf, Usd, UsdGeom, UsdPhysics, UsdShade
from std_msgs.msg import String

from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation, SingleRigidPrim
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController

from ic_cell.actions import discover_actions

IDENT = np.array([1.0, 0, 0, 0])
TOTE = "/World/BigTote"
RGB = {"red": (0.9, 0.1, 0.1), "blue": (0.1, 0.2, 0.9), "green": (0.1, 0.7, 0.1)}
POOL = [("/World/SortCube_R", "red"), ("/World/SortCube_R2", "red"),
        ("/World/SortCube_B", "blue"), ("/World/SortCube_B2", "blue"),
        ("/World/SortCube_G", "green"), ("/World/SortCube_G2", "green")]
POOL_COL = [c for _, c in POOL]
CUBES = {"red": ("/World/SortCube_R", 3.50, RGB["red"]),
         "blue": ("/World/SortCube_B", 3.72, RGB["blue"]),
         "green": ("/World/SortCube_G", 3.94, RGB["green"])}
CLASSIC_START = {"red": 3.50, "blue": 3.72, "green": 3.94}   # conveyor x per color
TRANSIT = 1.12; PLACE_Z = 0.76; GR_SNUG = 0.027; GR_OPEN = 0.04; GR_GRIP = 0.016; MAX_STEP = 0.010
GRASP_L = 0.103   # panda_hand origin -> fingertip grasp point, along local +Z
DOCK = np.array([4.126, -8.667]); YAW_DOCK = np.pi / 2.0; YAW_RACK = np.pi
HOME = np.array([0.0, -1.0, 0.0, -2.2, 0.0, 2.0, 0.785])
GRAB = np.array([0.0, 0.134, 0.0, -1.814, 0.0, 1.980, 0.785])
PLACE_A = np.array([0.0, 0.30, 0.0, -1.95, 0.0, 2.20, 0.785])
HAUL_WPS = [np.array([1.74, -8.667]), np.array([1.74, -7.84]), np.array([0.62, -7.40])]
SHELF_TOTE = np.array([-0.26, -7.40, 0.49])
COMP_LOCAL = {"red": -0.1975, "blue": 0.0, "green": 0.1975}
FR_HOME = np.array([0.0, -0.3, 0.0, -2.0, 0.0, 2.0, 0.785, 0.04, 0.04])
ZSPAWN = [(3.15, 4.35), (4.75, 5.90)]   # left=franka_left reach, right=franka_right reach


def _b2j(w):
    return w[0] - 4.54, w[1] + 4.8


def _qrot(q, v):  # rotate vector v by quaternion q=[w,x,y,z]
    w, x, y, z = float(q[0]), float(q[1]), float(q[2]), float(q[3])
    qv = np.array([x, y, z])
    t = 2.0 * np.cross(qv, v)
    return v + w * t + np.cross(qv, t)


class CellRuntime:
    """Owns the world, prims, controllers, ROS node, and the FIFO task loop."""

    def __init__(self):
        self.stage = omni.usd.get_context().get_stage()
        self._sub = None
        self._build_scene()
        self._build_world()
        self._build_ros()
        self.S = {"task": None, "t": 0, "ph": None, "locked": False, "rel": False,
                  "off": None, "n": 0, "yaw": YAW_DOCK, "cbase": DOCK.copy(),
                  "wp": 0, "wpt": 0, "toff": None, "boffs": None}
        self.ACTIVE = set()
        self._pending_reset = False
        self.action_registry = discover_actions()
        print("IC_ACTIONS_REGISTERED %s" % ",".join(self.action_registry.action_names), flush=True)

    # ---- scene: friction, tote, shelf pad, cube pool --------------------------
    def _build_scene(self):
        stage = self.stage
        mat = UsdShade.Material.Define(stage, "/World/PhysicsMaterials/Grippy")
        pm = UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
        pm.CreateStaticFrictionAttr().Set(2.0); pm.CreateDynamicFrictionAttr().Set(1.7)
        pm.CreateRestitutionAttr().Set(0.0)
        self._grippy = mat

        def bind(p):
            if p and p.IsValid():
                UsdShade.MaterialBindingAPI.Apply(p)
                UsdShade.MaterialBindingAPI(p).Bind(mat, UsdShade.Tokens.weakerThanDescendants, "physics")
        self._bind_grippy = bind
        for arm in ("Franka_Left", "Franka_Right"):
            for fn in ("panda_leftfinger", "panda_rightfinger"):
                bind(stage.GetPrimAtPath("/Workcell/%s/%s" % (arm, fn)))
        try:
            World.clear_instance()
        except Exception:
            pass
        omni.timeline.get_timeline_interface().stop()
        self.tp = stage.GetPrimAtPath(TOTE)
        a = UsdPhysics.RigidBodyAPI(self.tp).GetKinematicEnabledAttr()
        if a and a.IsValid():
            a.Set(False)
        mm = UsdPhysics.MassAPI(self.tp)
        (mm.GetMassAttr() or mm.CreateMassAttr()).Set(8.0)
        bind(self.tp)
        for op in UsdGeom.Xformable(self.tp).GetOrderedXformOps():
            if op.GetOpName() == "xformOp:translate":
                op.Set(Gf.Vec3d(4.126, -7.701, 0.665))
            if op.GetOpName() == "xformOp:orient":
                op.Set(Gf.Quatf(1.0, 0, 0, 0))
        pad = "/World/ShelfPad1"
        if not stage.GetPrimAtPath(pad).IsValid():
            c = UsdGeom.Cube.Define(stage, pad); c.GetSizeAttr().Set(1.0)
            pdp = c.GetPrim()
            xf = UsdGeom.Xformable(pdp); xf.ClearXformOpOrder()
            xf.AddTranslateOp().Set(Gf.Vec3d(-0.26, -7.40, 0.44))
            xf.AddScaleOp().Set(Gf.Vec3f(0.7, 1.55, 0.07))
            UsdPhysics.CollisionAPI.Apply(pdp); UsdGeom.Imageable(pdp).MakeInvisible()
        for i, (path, col) in enumerate(POOL):
            self._make_cube(path, (8.5 + 0.13 * i, -9.8, 0.05), RGB[col])

    def _make_cube(self, path, center, rgb):
        stage = self.stage
        if stage.GetPrimAtPath(path).IsValid():
            stage.RemovePrim(path)
        cc = UsdGeom.Cube.Define(stage, path); cc.GetSizeAttr().Set(1.0)
        p = cc.GetPrim()
        x = UsdGeom.Xformable(p); x.ClearXformOpOrder()
        x.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in center]))
        x.AddScaleOp().Set(Gf.Vec3f(0.05, 0.05, 0.05))
        cc.GetDisplayColorAttr().Set([Gf.Vec3f(*rgb)])
        UsdPhysics.CollisionAPI.Apply(p); UsdPhysics.RigidBodyAPI.Apply(p)
        UsdPhysics.MassAPI.Apply(p).GetMassAttr().Set(0.05)
        self._bind_grippy(p)

    # ---- world: robots, controllers, wrappers ---------------------------------
    def _build_world(self):
        self.world = World(physics_dt=1 / 60., rendering_dt=1 / 60., stage_units_in_meters=1.0)
        self.frL = Franka(prim_path="/Workcell/Franka_Left", name="icL"); self.world.scene.add(self.frL)
        self.frR = Franka(prim_path="/Workcell/Franka_Right", name="icR"); self.world.scene.add(self.frR)
        self.amr = SingleArticulation("/MobileBot", name="icAMR"); self.world.scene.add(self.amr)
        self.world.reset()
        self.ctrl = PickPlaceController(name="icc", gripper=self.frL.gripper,
                                        robot_articulation=self.frL, end_effector_initial_height=TRANSIT)
        self.frL.gripper.set_joint_positions(self.frL.gripper.joint_opened_positions); self.ctrl.reset()
        self.ctrlR = PickPlaceController(name="iccR", gripper=self.frR.gripper,
                                         robot_articulation=self.frR, end_effector_initial_height=TRANSIT)
        self.frR.gripper.set_joint_positions(self.frR.gripper.joint_opened_positions); self.ctrlR.reset()
        self.frL.set_joint_positions(FR_HOME); self.frR.set_joint_positions(FR_HOME)
        self._dock_amr()
        self.wr = {col: SingleRigidPrim(path, name="w_" + col) for col, (path, _, _) in CUBES.items()}
        self.wrp = [SingleRigidPrim(p, name="wp%d" % i) for i, (p, _) in enumerate(POOL)]
        self.tote = SingleRigidPrim(TOTE, name="icTote")
        self.fhand = SingleRigidPrim("/Workcell/Franka_Left/panda_hand", name="icFh")
        self.fhandR = SingleRigidPrim("/Workcell/Franka_Right/panda_hand", name="icFhR")
        self.ahand = SingleRigidPrim("/MobileBot/panda_hand", name="icAh")

    def _dock_amr(self):
        q = np.array(self.amr.get_joint_positions(), float)
        bj = _b2j(DOCK)
        q[0] = bj[0]; q[1] = bj[1]; q[2] = YAW_DOCK
        q[3:10] = HOME; q[10:12] = [GR_OPEN, GR_OPEN]
        self.amr.set_joint_positions(q)

    # ---- ROS node --------------------------------------------------------------
    def _build_ros(self):
        try:
            if not rclpy.ok():
                rclpy.init()
        except Exception:
            try:
                rclpy.init()
            except Exception:
                pass
        self.node = rclpy.create_node("ic_isaac_floor")
        self.RES = self.node.create_publisher(String, "/ic/result", 10)
        self.STP = self.node.create_publisher(String, "/ic/floor_state", 10)
        self.JNT = self.node.create_publisher(String, "/ic/joints", 10)
        self.FBK = self.node.create_publisher(String, "/ic/feedback", 10)
        self.Q = []
        self._seen_goals = []   # dedupe window (a duplicate publish must not re-execute)

        def on_cmd(msg):
            try:
                c = json.loads(msg.data)
            except Exception:
                c = {"action": "raw", "data": msg.data}
            gid = c.get("goal_id")
            if gid:
                if gid in self._seen_goals:
                    print("IC_DUP goal_id=%s dropped" % gid, flush=True)
                    return
                self._seen_goals.append(gid)
                del self._seen_goals[:-64]
            print("IC_CMD %s" % c, flush=True)
            self.Q.append(c)
        self._cmdsub = self.node.create_subscription(String, "/ic/command", on_cmd, 10)

    # ---- scene helpers ----------------------------------------------------------
    def comp_world(self, color):
        M = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(self.tp)
        v = M.Transform(Gf.Vec3d(COMP_LOCAL[color], 0.0, 0.04))
        return np.array([float(v[0]), float(v[1]), float(v[2])])

    def _park(self, i):
        self.wrp[i].set_world_pose(np.array([8.5 + 0.13 * i, -9.8, 0.05]), IDENT)
        self.wrp[i].set_linear_velocity(np.zeros(3)); self.wrp[i].set_angular_velocity(np.zeros(3))

    def _stand_tote(self):
        self.tote.set_world_pose(np.array([4.126, -7.701, 0.665]), IDENT)
        self.tote.set_linear_velocity(np.zeros(3)); self.tote.set_angular_velocity(np.zeros(3))

    def spawn_scene(self, n=None, zone="left"):
        """GR00T-style random spawn: 2-6 pool cubes on the conveyor, rest parked."""
        try:
            self._stand_tote()
        except Exception:
            pass
        n = int(n) if n else random.randint(4, 6)
        if n >= 3:
            base = [random.choice([0, 1]), random.choice([2, 3]), random.choice([4, 5])]
            rest = [x for x in range(6) if x not in base]
            random.shuffle(rest); sel = base + rest[:n - 3]; random.shuffle(sel)
        else:
            idx = list(range(6)); random.shuffle(idx); sel = idx[:n]
        if zone == "left":
            zsel = [(3.20, 4.30)] * n
        else:
            sides = [k % 2 for k in range(n)]; random.shuffle(sides)
            zsel = [ZSPAWN[s] for s in sides]
        self.ACTIVE.clear(); self.ACTIVE.update(sel)
        placed = []
        for k, i in enumerate(sel):
            lo, hi = zsel[k]
            x = round(random.uniform(lo, hi), 3); y = round(random.uniform(-7.04, -6.88), 3)
            for _t in range(25):
                if all((x - px) ** 2 + (y - py) ** 2 > 0.013 for px, py in placed):
                    break
                x = round(random.uniform(lo, hi), 3); y = round(random.uniform(-7.04, -6.88), 3)
            placed.append((x, y))
            self.wrp[i].set_world_pose(np.array([x, y, 0.74]), IDENT)
            self.wrp[i].set_linear_velocity(np.zeros(3)); self.wrp[i].set_angular_velocity(np.zeros(3))
        for i in range(6):
            if i not in self.ACTIVE:
                self._park(i)
        print("SPAWN n=%d active=%s cols=%s" % (n, sorted(self.ACTIVE), [POOL_COL[i] for i in sel]), flush=True)

    def reset_scene(self):
        """Deterministic demo start: R/B/G on the conveyor at classic positions,
        spares parked, tote on the table, AMR docked, arms home, queue cleared."""
        self.Q.clear()
        self.S.update({"task": None, "t": 0, "ph": None, "locked": False, "rel": False,
                       "off": None, "yaw": YAW_DOCK, "cbase": DOCK.copy(),
                       "wp": 0, "wpt": 0, "toff": None, "boffs": None})
        self.ACTIVE.clear(); self.ACTIVE.update({0, 2, 4})   # SortCube_R/B/G
        for col, x in CLASSIC_START.items():
            self.wr[col].set_world_pose(np.array([x, -6.95, 0.74]), IDENT)
            self.wr[col].set_linear_velocity(np.zeros(3)); self.wr[col].set_angular_velocity(np.zeros(3))
        for i in (1, 3, 5):
            self._park(i)
        self._stand_tote()
        self._dock_amr()
        self.frL.set_joint_positions(FR_HOME); self.frR.set_joint_positions(FR_HOME)
        try:
            # demo-start is a VISUAL state too: undo any inspect re-aim of RackCam_B
            from ic_cell import cameras
            cameras.set_rackcam_b_final_pose()
        except Exception:
            print("SCENE_RESET_CAM_WARN:\n" + traceback.format_exc(), flush=True)
        print("SCENE_RESET_DONE", flush=True)

    def target_cube(self, col, arm_x):
        cands = [i for i in self.ACTIVE if POOL_COL[i] == col]
        if not cands:
            return None
        return min(cands, key=lambda i: abs(float(self.wrp[i].get_world_pose()[0][0]) - arm_x))

    # ---- floor state ------------------------------------------------------------
    def floor_state(self):
        st = {"endpoints": ["franka_left", "franka_right", "mobilebot"],
              "conveyor_1": [], "tote": {}, "tote_on_rack": False, "cubes": []}
        for i in sorted(self.ACTIVE):
            col = POOL_COL[i]
            p, _ = self.wrp[i].get_world_pose(); p = np.array(p)
            c = self.comp_world(col)
            intote = abs(p[0] - c[0]) < 0.12 and abs(p[1] - c[1]) < 0.12 and p[2] > 0.66
            where = "tote" if intote else ("conveyor" if p[1] > -7.25 else "off")
            st["cubes"].append({"i": i, "color": col, "x": round(float(p[0]), 3),
                                "y": round(float(p[1]), 3), "where": where})
            if intote:
                st["tote"][col] = "in"
            elif where == "conveyor":
                st["conveyor_1"].append(col)
        tpz, _ = self.tote.get_world_pose()
        st["tote_on_rack"] = bool(tpz[0] < 0.6)
        try:
            bl, _ = self.frL.get_world_pose(); br, _ = self.frR.get_world_pose()
            st["arms"] = {"franka_left": [round(float(bl[0]), 3), round(float(bl[1]), 3)],
                          "franka_right": [round(float(br[0]), 3), round(float(br[1]), 3)]}
        except Exception:
            pass
        return st

    # ---- task lifecycle -----------------------------------------------------------
    def feedback(self, phase, goal_id=None):
        gid = goal_id or (self.S["task"] or {}).get("goal_id")
        try:
            self.FBK.publish(String(data=json.dumps({"goal_id": gid, "phase": phase})))
        except Exception:
            pass

    def finish(self, success, verified, reason, task=None):
        task = task if task is not None else self.S["task"]
        res = {"action": (task or {}).get("action"), "args": task,
               "goal_id": (task or {}).get("goal_id"),
               "success": bool(success), "verified": bool(verified), "reason": reason}
        self.RES.publish(String(data=json.dumps(res)))
        print("IC_RESULT %s" % res, flush=True)
        if task is self.S["task"] or self.S["task"] is None:
            self.S["task"] = None; self.S["t"] = 0

    def start(self, cmd):
        S = self.S
        S["task"] = cmd; S["t"] = 0; S["locked"] = False; S["rel"] = False
        S["off"] = None; S["hpmin"] = None; S["offc"] = None
        act = cmd.get("action")
        if act == "move":
            col = cmd.get("color")
            dest = (cmd.get("destination") or "").replace("tote_", "") or col
            ep = cmd.get("endpoint")
            bp, _ = (self.frR if ep == "franka_right" else self.frL).get_world_pose()
            ti = self.target_cube(col, float(bp[0]))
            S["cube"] = (self.wrp[ti] if ti is not None else None)
            if ti is not None:
                p, _ = self.wrp[ti].get_world_pose()
                S["pick"] = np.array([float(p[0]), float(p[1]), max(float(p[2]), 0.72)])
                S["destcol"] = dest if dest in COMP_LOCAL else col
                c = self.comp_world(S["destcol"])
                S["place"] = np.array([c[0], c[1], PLACE_Z])
                (self.ctrlR if ep == "franka_right" else self.ctrl).reset()
        elif act in ("pick_and_place", "haul"):
            S["ph"] = "reach"; S["yaw"] = YAW_DOCK; S["cbase"] = DOCK.copy()
            S["wp"] = 0; S["wpt"] = 0; S["toff"] = None; S["boffs"] = None
        print("IC_START %s" % cmd, flush=True)
        self.feedback("accepted", cmd.get("goal_id"))

    def do_inspect(self, cmd):
        target = cmd.get("target") or cmd.get("target_id") or ""
        if target.startswith("tote") or target == "tote":
            tpz, _ = self.tote.get_world_pose(); pos = np.array(tpz)
        elif target.startswith("rack"):
            pos = np.array([-0.26, -7.40, 0.55])
        else:
            pos = np.array([3.7, -6.95, 0.73])
        cam = self.stage.GetPrimAtPath("/RackCam_B")
        if cam.IsValid():
            api = UsdGeom.XformCommonAPI(cam)
            api.SetTranslate(Gf.Vec3d(float(pos[0]), float(pos[1]), float(pos[2]) + 1.1))
            api.SetRotate((0, 0, 0))
            fl = cam.GetAttribute("focalLength")
            if fl:
                fl.Set(50.0)
        self.finish(True, True, "inspect_cam aimed at %s" % target)

    # ---- skills -------------------------------------------------------------------
    def run_move(self, dt):
        S = self.S
        ep = (S["task"].get("endpoint") or "franka_left")
        arm, c, hand = ((self.frR, self.ctrlR, self.fhandR) if ep == "franka_right"
                        else (self.frL, self.ctrl, self.fhand))
        cu = S.get("cube")
        if cu is None:
            self.finish(False, False, "no matching cube"); return
        jp = arm.get_joint_positions()
        act = c.forward(picking_position=S["pick"], placing_position=S["place"],
                        current_joint_positions=jp, end_effector_offset=np.array([0, 0, 0]))
        hp, hq = hand.get_world_pose(); hp = np.array(hp)
        fingers = None
        grasp = hp + _qrot(hq, np.array([0.0, 0.0, GRASP_L]))
        if not S["locked"]:
            cp, _ = cu.get_world_pose(); cp = np.array(cp)
            if float(np.linalg.norm(grasp - cp)) < 0.05:
                if S["hpmin"] is None or hp[2] <= S["hpmin"]:
                    S["hpmin"] = hp[2]; S["offc"] = cp - grasp
                elif hp[2] > S["hpmin"] + 0.012:
                    if float(np.linalg.norm(S["offc"])) < 0.045:
                        S["off"] = S["offc"]; S["locked"] = True
                    else:
                        S["hpmin"] = None; S["offc"] = None
        if S["locked"] and not S["rel"]:
            dp = float(((grasp[0] - S["place"][0]) ** 2 + (grasp[1] - S["place"][1]) ** 2) ** 0.5)
            if dp < 0.05 and hp[2] < S["place"][2] + 0.16:
                S["rel"] = True
            else:
                fingers = GR_SNUG
                cu.set_world_pose(grasp + S["off"], hq)
                cu.set_linear_velocity(np.zeros(3)); cu.set_angular_velocity(np.zeros(3))
        if S["rel"]:
            fingers = GR_OPEN
        if fingers is not None and act.joint_positions is not None:
            try:
                jj = np.array(act.joint_positions, dtype=float)
                if jj.shape[0] >= 9:
                    jj[7] = fingers; jj[8] = fingers
                    act = ArticulationAction(joint_positions=jj)
            except Exception:
                pass
        if jp is not None:
            arm.apply_action(act)
        S["t"] += 1
        if c.is_done() or S["t"] > 1700:
            fp, _ = cu.get_world_pose()
            cc = self.comp_world(S["destcol"])
            off = float(((fp[0] - cc[0]) ** 2 + (fp[1] - cc[1]) ** 2) ** 0.5)
            ok = off < 0.08
            self.finish(ok, ok, ("in tote_%s off=%.3f" % (S["destcol"], off)) if ok
                        else ("missed off=%.3f" % off))

    def run_haul(self, dt):
        S = self.S
        self.frL.apply_action(ArticulationAction(joint_positions=FR_HOME))
        t = S["t"]; st = S["ph"]
        jp = np.array(self.amr.get_joint_positions(), float)
        ax, ay = jp[0] + 4.54, jp[1] - 4.8
        base = DOCK.copy(); arm = HOME.copy(); yaw = S["yaw"]
        fol = (S["toff"] is not None)

        def setp(n):
            S["ph"] = n; S["t"] = 0; S["wp"] = 0; S["wpt"] = 0
            self.feedback(n)
        if st == "reach":
            al = min(1.0, t / 150.0); arm = (1 - al) * HOME + al * GRAB
            if t >= 190:
                setp("lift")
        elif st == "lift":
            al = min(1.0, t / 120.0); arm = (1 - al) * GRAB + al * HOME
            if t >= 130:
                setp("turn")
        elif st == "turn":
            al = min(1.0, t / 240.0); yaw = YAW_DOCK + (YAW_RACK - YAW_DOCK) * al; S["yaw"] = yaw
            if t >= 240:
                S["yaw"] = YAW_RACK; setp("haul")
        elif st == "haul":
            yaw = YAW_RACK; g = HAUL_WPS[S["wp"]]
            d = ((ax - g[0]) ** 2 + (ay - g[1]) ** 2) ** 0.5
            last = (S["wp"] == len(HAUL_WPS) - 1); S["wpt"] += 1; base = g
            if d < (0.40 if last else 0.30) or S["wpt"] > 1800:
                if not last:
                    S["wp"] += 1; S["wpt"] = 0
                else:
                    setp("place")
        elif st == "place":
            al = min(1.0, t / 150.0); base = HAUL_WPS[-1]; arm = (1 - al) * HOME + al * PLACE_A
            if t >= 180:
                setp("release")
        elif st == "release":
            base = HAUL_WPS[-1]; arm = PLACE_A; fol = False
            if t == 0:
                self.tote.set_world_pose(SHELF_TOTE, IDENT)
                self.tote.set_linear_velocity(np.zeros(3)); self.tote.set_angular_velocity(np.zeros(3))
                for col in CUBES:
                    self.wr[col].set_world_pose(SHELF_TOTE + np.array([COMP_LOCAL[col], 0.0, 0.05]), IDENT)
                    self.wr[col].set_linear_velocity(np.zeros(3)); self.wr[col].set_angular_velocity(np.zeros(3))
            if t >= 120:
                setp("retract")
        elif st == "retract":
            al = min(1.0, t / 150.0); base = HAUL_WPS[-1]; arm = (1 - al) * PLACE_A + al * HOME; fol = False
            if t >= 150:
                setp("depart")
        elif st == "depart":
            # Back to the dock so the rack camera has an unobstructed view for verify.
            yaw = YAW_RACK; base = DOCK.copy(); arm = HOME; fol = False
            d = ((ax - DOCK[0]) ** 2 + (ay - DOCK[1]) ** 2) ** 0.5
            if d < 0.5 or t > 2400:
                tpz, _ = self.tote.get_world_pose()
                ok = bool(tpz[0] < 0.6)
                self.finish(ok, ok, "tote on rack" if ok else "tote x=%.2f" % tpz[0])
                return
        grabbed = (S["toff"] is not None)
        grip = GR_GRIP if (grabbed and st in ("lift", "turn", "haul", "place")) else GR_OPEN
        d = base - S["cbase"]; dn = float(np.linalg.norm(d))
        S["cbase"] = (S["cbase"] + d / dn * MAX_STEP) if dn > MAX_STEP else base.copy()
        tgt = jp.copy(); bj = _b2j(S["cbase"])
        tgt[0] = bj[0]; tgt[1] = bj[1]; tgt[2] = yaw; tgt[3:10] = arm; tgt[10:12] = [grip, grip]
        self.amr.apply_action(ArticulationAction(joint_positions=tgt))
        hp, _ = self.ahand.get_world_pose()
        if st == "reach" and t == 150:
            tpz, _ = self.tote.get_world_pose()
            S["toff"] = np.array(tpz) - np.array(hp)
            S["boffs"] = {}
            for col in CUBES:
                bp, _ = self.wr[col].get_world_pose()
                S["boffs"][col] = np.array(bp) - np.array(hp)
        if fol and S["toff"] is not None:
            self.tote.set_world_pose(np.array(hp) + S["toff"], IDENT)
            self.tote.set_linear_velocity(np.zeros(3)); self.tote.set_angular_velocity(np.zeros(3))
            for col in CUBES:
                self.wr[col].set_world_pose(np.array(hp) + S["boffs"][col], IDENT)
                self.wr[col].set_linear_velocity(np.zeros(3)); self.wr[col].set_angular_velocity(np.zeros(3))
        S["t"] += 1

    def hold_arms(self, *arms):
        """Keep idle fixed Frankas at the canonical home pose."""
        for arm in arms:
            arm.apply_action(ArticulationAction(joint_positions=FR_HOME))

    # ---- step loop --------------------------------------------------------------
    def request_reset(self):
        """Reset once physics is actually stepping (boot-time teleports would be
        stomped by the first frame — kit can't tick while bring_up still runs)."""
        self._pending_reset = True

    def _step(self, dt):
        S = self.S
        try:
            rclpy.spin_once(self.node, timeout_sec=0.0)
            if self._pending_reset and S["n"] > 10 and S["task"] is None:
                self._pending_reset = False
                self.reset_scene()

            if S["task"] is None:
                self.hold_arms(self.frL, self.frR)
                if self.Q:
                    cmd = self.Q.pop(0); act = cmd.get("action")
                    if act == "cancel":
                        self.finish(True, True, "nothing to cancel", task=cmd)
                    else:
                        handler = self.action_registry.resolve(act)
                        if handler is None:
                            S["task"] = cmd
                            self.finish(False, False, "unknown action %s" % act)
                        else:
                            handler.start(self, cmd)
            else:
                if self.Q and self.Q[0].get("action") == "cancel":
                    cancel_cmd = self.Q.pop(0)
                    canceled = S["task"]
                    S["task"] = None; S["t"] = 0
                    self.finish(False, False, "canceled by operator", task=canceled)
                    self.finish(True, True, "cancel applied", task=cancel_cmd)
                    return
                act = S["task"].get("action")
                handler = self.action_registry.resolve(act)
                if handler is None:
                    self.finish(False, False, "active action handler disappeared: %s" % act)
                else:
                    handler.step(self, dt)
            S["n"] += 1
            if S["n"] % 60 == 0:
                self.STP.publish(String(data=json.dumps(self.floor_state())))
            if S["n"] % 3 == 0:
                try:
                    self.JNT.publish(String(data=json.dumps(
                        {"t": S["n"],
                         "franka_left": [round(float(x), 5) for x in self.frL.get_joint_positions()],
                         "franka_right": [round(float(x), 5) for x in self.frR.get_joint_positions()]})))
                except Exception:
                    pass
        except Exception:
            print("IC_STEP_ERR:\n" + traceback.format_exc(), flush=True)

    # ---- lifecycle ----------------------------------------------------------------
    def run(self):
        omni.timeline.get_timeline_interface().play()
        self._sub = omni.physx.get_physx_interface().subscribe_physics_step_events(self._step)
        print("IC_NODE_V2_STARTED", flush=True)

    def shutdown(self):
        if self._sub is not None:
            try:
                self._sub.unsubscribe()
            except Exception:
                pass
            self._sub = None
        try:
            self.node.destroy_node()
        except Exception:
            pass
