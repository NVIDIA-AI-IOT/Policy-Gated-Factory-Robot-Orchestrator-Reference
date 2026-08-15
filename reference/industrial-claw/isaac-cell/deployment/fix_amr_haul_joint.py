# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Joint-era haul: physical FixedJoint carry, side-by-side Shelf_1 placement.

Replaces the teleport-ride run_haul (fix_amr_haul.py) with a physically
honest pipeline. Calibrated 2026-07-20 (static end-to-end proof: tote seated
at (-0.258,-6.998,0.53) flat and aligned on Shelf_1):

1. GRAB: runtime UsdPhysics.FixedJoint hand<->tote, frames from settled FK
   (two-phase lesson from INC-1). Joint ops run on the app update loop, not
   the physics callback.
2. CARRY_T: level-carry posture (spill-tilt 2.8 deg) + wrist twist q6=+2.356
   so the tote lands shelf-aligned after the +90 deg base yaw to the rack
   (roll about the downward axis inverts yaw - calibrated sign).
3. PLACE: both totes go side-by-side on the REAL Shelf_1 (top z=0.47):
   left tote seat (-0.26,-7.80), right tote seat (-0.26,-7.00). Approach:
   arrive OUTSIDE the rack at carry height, lower to PLACE_LOW (tote slides
   under Shelf_2), creep the base in, release only when the MEASURED tote
   position is over the seat, detach, unhook up, back out. ShelfPad2 (the
   invisible stacking hack) is removed - obsolete.

Revert: /tmp/cmd_revert_joint_haul.py (re-execs the teleport-era patch,
restores shelf globals, removes the joint). Every scene reset also re-execs
the old patch.
"""

import math

import numpy as np
from pxr import Gf, Usd, UsdGeom, UsdPhysics

_g = globals()

# NO wrist twist: the tote's long axis is LOCAL X (0.60 m) - verified via the
# on-shelf overhang + red's resting spot. Landing at the natural +90 deg base
# yaw puts the long axis ALONG the shelf. (The q6=2.356 twist was built on a
# bad early bbox reading and made totes land ACROSS the 0.44 m shelf.)
CARRY_T = np.array(GRAB, float) + np.array([0.0, -0.3, 0.0, 0.6, 0.0, -0.9, 0.0])
# gentle 2.5 cm set-down: cargo cubes ride pads inside the tote within ~1 cm
# of the rim, and the 6 cm drop of the -0.08 era bounced one out on the rack.
# The wall-grab keeps the fingers outside the tote footprint at any height,
# so the low release carries no escape risk (the old -0.17 failures were all
# interior-grab escape hooks, never sweep contact).
PLACE_LOW = np.array(GRAB, float) + np.array([0.0, 0.0, 0.0, -0.17, 0.0, 0.17, 0.0])
# +0.90 raises the hand ~0.30 m: fingertips clear the seated tote rim by
# ~16 cm (0.45 left only ~1.5 cm - grab-to-grab variation made the fingers
# hook the rim on backout and the retract swing scooped the tote off)
UNHOOK = PLACE_LOW + np.array([0.0, 0.0, 0.0, 0.90, 0.0, -0.90, 0.0])
_JPATH = "/World/HaulJoint"
_TB_OFF = np.array(
    [-0.85, 0.0]
)  # tote-hang minus base at PLACE_LOW (initial; creep is closed-loop)
_STAGE_X = 1.30  # base x waiting outside the rack front
GR_PIN = 0.011  # finger gap that visually closes on the grab pin
_REACH_TICKS = 240  # smooth arm approach; avoid shocking cargo near the rim
_REACH_SETTLE_TICKS = 30
_GRIP_CLOSE_TICKS = 120  # close on the pin gradually instead of one-tick snap
_PREATTACH_SETTLE_TICKS = 30
_JOINT_SETTLE_TICKS = 60  # let the new constraint settle before lifting cargo
_LIFT_TICKS = 480  # extra-slow pickup with zero endpoint velocity/acceleration
_PREDROP_TICKS = 240  # extra-slow shelf lowering; preserve the 30-tick settle
_CARGO_HALF_EXTENTS_XY = (0.30, 0.18)
_CARGO_HEIGHT = 0.25
_CARGO_VERIFY_STABLE_TICKS = 30  # require 0.5 s of retained cargo at 60 Hz
_CARGO_VERIFY_TIMEOUT_TICKS = 300  # bound post-haul reconciliation to 5 s


def _smoothstep5(value):
    """Quintic 0..1 blend with zero velocity and acceleration at each end."""
    u = max(0.0, min(1.0, float(value)))
    return u * u * u * (u * (u * 6.0 - 15.0) + 10.0)


def _tote_local_position(tote_position, tote_orientation, world_position):
    """Transform a world point into the tote frame (quaternion is w, x, y, z)."""
    q = tuple(float(value) for value in tote_orientation)
    if len(q) != 4 or not all(math.isfinite(value) for value in q):
        raise ValueError("invalid tote orientation")
    q_norm = math.sqrt(sum(value * value for value in q))
    if q_norm < 1.0e-8:
        raise ValueError("invalid tote orientation")
    w, x, y, z = (value / q_norm for value in q)
    tote = tuple(float(value) for value in tote_position)
    world = tuple(float(value) for value in world_position)
    if len(tote) != 3 or len(world) != 3:
        raise ValueError("invalid tote or cargo position")
    dx, dy, dz = (world[index] - tote[index] for index in range(3))

    # R maps tote-local vectors into world coordinates. Multiplication by R^T
    # therefore expresses the world-space delta in the tote frame.
    r00 = 1.0 - 2.0 * (y * y + z * z)
    r01 = 2.0 * (x * y - z * w)
    r02 = 2.0 * (x * z + y * w)
    r10 = 2.0 * (x * y + z * w)
    r11 = 1.0 - 2.0 * (x * x + z * z)
    r12 = 2.0 * (y * z - x * w)
    r20 = 2.0 * (x * z - y * w)
    r21 = 2.0 * (y * z + x * w)
    r22 = 1.0 - 2.0 * (x * x + y * y)
    return (
        r00 * dx + r10 * dy + r20 * dz,
        r01 * dx + r11 * dy + r21 * dz,
        r02 * dx + r12 * dy + r22 * dz,
    )


def _cargo_is_inside(tote_position, tote_orientation, cargo_position):
    """Return whether a cargo center is inside the tote's oriented volume."""
    local = _tote_local_position(tote_position, tote_orientation, cargo_position)
    return bool(
        abs(float(local[0])) < float(_CARGO_HALF_EXTENTS_XY[0])
        and abs(float(local[1])) < float(_CARGO_HALF_EXTENTS_XY[1])
        and 0.0 < float(local[2]) < _CARGO_HEIGHT
    )


# grab beside the tote WALL, not over the interior: every escape failure
# (rim hook x2, tote landing on the fingers) came from the hand hovering
# over the 9 cm-tall tote's opening at release. +0.16 m dock shift puts the
# fingers ~5 cm outside the wall - at release they are entirely outside the
# tote footprint and the escape has nothing to catch. Originals stashed for
# the revert script.
if "_IC_DOCK_ORIG" not in _g:
    _g["_IC_DOCK_ORIG"] = (DOCK.copy(), DOCK_R.copy())
# -0.05 y shift centers the fingers on the tote's GrabPin handle (5 cm
# outside the long south wall) - fingers close on the pin, joint locks
_g["DOCK"] = _g["_IC_DOCK_ORIG"][0] + np.array([0.0, -0.05])
_g["DOCK_R"] = _g["_IC_DOCK_ORIG"][1] + np.array([0.0, -0.05])

# side-by-side Shelf_1 seats (overrides the stacked teleport-era targets;
# originals stashed for the revert script)
if "_IC_SHELF_ORIG" not in _g:
    _g["_IC_SHELF_ORIG"] = (SHELF_TOTE.copy(), SHELF_TOTE_R.copy())
_g["SHELF_TOTE"] = np.array([-0.26, -7.80, 0.52])
_g["SHELF_TOTE_R"] = np.array([-0.26, -7.00, 0.52])

# the invisible stacking pad is an obstacle for the low sweep - drop it
if stage.GetPrimAtPath("/World/ShelfPad2").IsValid():
    stage.RemovePrim("/World/ShelfPad2")

# grab-pin handles (visual-only children; die on relaunch, so ensure here -
# this patch is exec'd by every scene reset)
for _tp_path in ("/World/BigTote", "/World/BigTote_R"):
    if not stage.GetPrimAtPath(_tp_path + "/GrabPin").IsValid():
        _pin = UsdGeom.Cylinder.Define(stage, _tp_path + "/GrabPin")
        _pin.CreateRadiusAttr().Set(0.009)
        _pin.CreateHeightAttr().Set(0.10)
        _pin.CreateAxisAttr().Set("Z")
        UsdGeom.XformCommonAPI(_pin.GetPrim()).SetTranslate(
            Gf.Vec3d(-0.04, -0.15, 0.03)
        )
        _pin.CreateDisplayColorAttr().Set([Gf.Vec3f(0.15, 0.15, 0.15)])
        _stem = UsdGeom.Cube.Define(stage, _tp_path + "/GrabPinStem")
        UsdGeom.XformCommonAPI(_stem.GetPrim()).SetTranslate(
            Gf.Vec3d(-0.04, -0.125, 0.0)
        )
        UsdGeom.XformCommonAPI(_stem.GetPrim()).SetScale(Gf.Vec3f(0.008, 0.028, 0.008))
        _stem.CreateDisplayColorAttr().Set([Gf.Vec3f(0.15, 0.15, 0.15)])
        print("IC_JHAUL_PIN ensured on %s" % _tp_path, flush=True)


def _joint_op_tick(_ev):
    """Deferred joint ops - runs on the app update loop (INC-1-safe context)."""
    req = _g.get("_IC_JOINT_REQ")
    if not req:
        return
    _g["_IC_JOINT_REQ"] = None
    try:
        if req["op"] == "attach":
            xc = UsdGeom.XformCache(Usd.TimeCode.Default())
            Mh = xc.GetLocalToWorldTransform(
                stage.GetPrimAtPath("/MobileBot/panda_hand")
            )
            Mt = xc.GetLocalToWorldTransform(stage.GetPrimAtPath(req["tote"]))
            dist = float(
                (Mt.ExtractTranslation() - Mh.ExtractTranslation()).GetLength()
            )
            if dist > 0.6:
                _g["_IC_JOINT_ACK"] = {
                    "ok": False,
                    "dist": dist,
                    "err": "hand-tote %.2fm - reach failed" % dist,
                }
                return
            rel = Mt * Mh.GetInverse()
            if stage.GetPrimAtPath(_JPATH).IsValid():
                stage.RemovePrim(_JPATH)
            j = UsdPhysics.FixedJoint.Define(stage, _JPATH)
            j.CreateBody0Rel().SetTargets(["/MobileBot/panda_hand"])
            j.CreateBody1Rel().SetTargets([req["tote"]])
            t = rel.ExtractTranslation()
            j.CreateLocalPos0Attr().Set(Gf.Vec3f(t[0], t[1], t[2]))
            j.CreateLocalRot0Attr().Set(Gf.Quatf(rel.ExtractRotationQuat()))
            j.CreateLocalPos1Attr().Set(Gf.Vec3f(0, 0, 0))
            j.CreateLocalRot1Attr().Set(Gf.Quatf(1, 0, 0, 0))
            _g["_IC_JOINT_ACK"] = {"ok": True, "dist": dist, "err": ""}
            print("IC_JHAUL_ATTACH dist=%.3f tote=%s" % (dist, req["tote"]), flush=True)
        elif req["op"] == "detach":
            if stage.GetPrimAtPath(_JPATH).IsValid():
                stage.RemovePrim(_JPATH)
            _g["_IC_JOINT_ACK"] = {"ok": True, "dist": 0.0, "err": ""}
            print("IC_JHAUL_DETACH", flush=True)
    except Exception as e:
        _g["_IC_JOINT_ACK"] = {"ok": False, "dist": -1.0, "err": repr(e)}
        print("IC_JHAUL_OP_ERR %r" % e, flush=True)


if _g.get("_IC_JOINTOP_SUB") is not None:
    _g["_IC_JOINTOP_SUB"] = None
import omni.kit.app

_g["_IC_JOINTOP_SUB"] = (
    omni.kit.app.get_app()
    .get_update_event_stream()
    .create_subscription_to_pop(_joint_op_tick, name="ic_joint_op")
)


def run_haul(dt):
    frL.apply_action(ArticulationAction(joint_positions=FR_HOME))
    t = S["t"]
    st = S["ph"]
    jp = np.array(amr.get_joint_positions(), float)
    ax, ay = jp[0] + 4.54, jp[1] - 4.8
    _dock = S.get("dock", DOCK)
    _shelf = S.get("shelf", SHELF_TOTE)
    _tote = (_g.get("tote_r") if S.get("haul_tote") == "tote_r" else tote) or tote
    _stage = np.array([_STAGE_X, _shelf[1] - _TB_OFF[1]])
    _pbase = np.array([_shelf[0] - _TB_OFF[0], _shelf[1] - _TB_OFF[1]])
    base = _dock.copy()
    arm = HOME.copy()
    yaw = S["yaw"]

    if "cargo_manifest" not in S:
        # Snapshot cargo before the AMR, arm, or fingers move.  Capturing this
        # in grabwait was too late: initial contact could eject a rim-height
        # object and silently reduce the expected set (for example 3 -> 2),
        # allowing the final gate to certify cargo_retained=2/2 incorrectly.
        _mtz, _mtq = _tote.get_world_pose()
        S["cargo_manifest"] = [
            _cargo_index
            for _cargo_index in sorted(ACTIVE)
            if _cargo_is_inside(
                _mtz,
                _mtq,
                wrp[_cargo_index].get_world_pose()[0],
            )
        ]
        S["cargo_manifest_phase"] = "pre_reach"
        print("IC_HAUL_MANIFEST %s phase=pre_reach" % S["cargo_manifest"], flush=True)

    def setp(n):
        S["ph"] = n
        S["t"] = 0
        S["wp"] = 0
        S["wpt"] = 0

    if st == "reach":
        S["joint_on"] = False  # S persists across tasks; never inherit a stale flag
        if ((ax - _dock[0]) ** 2 + (ay - _dock[1]) ** 2) ** 0.5 > 0.25 and t < 1200:
            S["t"] = 0
            arm = HOME  # hold grab timer until the base actually docks
        al = _smoothstep5(t / float(_REACH_TICKS))
        arm = (1 - al) * HOME + al * GRAB
        if t >= _REACH_TICKS + _REACH_SETTLE_TICKS:
            _g["_IC_JOINT_ACK"] = None
            setp("grabwait")
    elif st == "grabwait":
        arm = GRAB
        _attach_tick = _GRIP_CLOSE_TICKS + _PREATTACH_SETTLE_TICKS
        if t == _attach_tick:
            # The pre-contact snapshot is authoritative.  Refuse to lift if
            # the approach or finger close displaced any expected cargo.
            _mtz, _mtq = _tote.get_world_pose()
            _missing_before_attach = [
                _cargo_index
                for _cargo_index in S.get("cargo_manifest", [])
                if not _cargo_is_inside(
                    _mtz,
                    _mtq,
                    wrp[_cargo_index].get_world_pose()[0],
                )
            ]
            if _missing_before_attach:
                finish(
                    False,
                    False,
                    "cargo displaced before attach indices=%s"
                    % _missing_before_attach,
                )
                return
            _g["_IC_JOINT_REQ"] = {"op": "attach", "tote": _tote.prim_path}
        ack = _g.get("_IC_JOINT_ACK")
        if ack is not None:
            if ack["ok"]:
                S["joint_on"] = True
                setp("jointsettle")
            else:
                finish(False, False, "grab failed: %s" % ack["err"])
                return
        elif t > _attach_tick + 240:
            finish(False, False, "grab failed: joint op timeout")
            return
    elif st == "jointsettle":
        # FixedJoint creation can impart a solver impulse if motion starts in
        # the same physics tick.  Hold the dock and grab pose for one second
        # before commanding any lift.
        base = _dock
        arm = GRAB
        if t >= _JOINT_SETTLE_TICKS:
            setp("lift")
    elif st == "lift":
        al = _smoothstep5(t / float(_LIFT_TICKS))
        arm = (1 - al) * GRAB + al * CARRY_T
        if t >= _LIFT_TICKS + 10:
            setp("turn")
    elif st == "turn":
        arm = CARRY_T
        al = _smoothstep5(t / 240.0)
        yaw = YAW_DOCK + (YAW_RACK - YAW_DOCK) * al
        S["yaw"] = yaw
        if t >= 240:
            S["yaw"] = YAW_RACK
            setp("haul")
    elif st == "haul":
        arm = CARRY_T
        yaw = YAW_RACK
        g = HAUL_WPS[S["wp"]]
        d = ((ax - g[0]) ** 2 + (ay - g[1]) ** 2) ** 0.5
        last = S["wp"] == len(HAUL_WPS) - 1
        S["wpt"] += 1
        base = g
        if d < (0.30 if not last else 0.50) or S["wpt"] > 1800:
            if not last:
                S["wp"] += 1
                S["wpt"] = 0
            else:
                setp("approach")
    elif st == "approach":
        yaw = YAW_RACK
        base = _stage
        arm = CARRY_T
        if ((ax - _stage[0]) ** 2 + (ay - _stage[1]) ** 2) ** 0.5 < 0.25 or t > 600:
            setp("predrop")
    elif st == "predrop":
        base = _stage
        al = _smoothstep5(t / float(_PREDROP_TICKS))
        arm = (1 - al) * CARRY_T + al * PLACE_LOW
        if t >= _PREDROP_TICKS + 30:
            setp("creep")
    elif st == "creep":
        # closed-loop: servo the base on the MEASURED tote-to-seat error each
        # tick (a fixed target never converges - the base PD carries a large
        # steady-state error with the arm extended)
        tpz, _ = _tote.get_world_pose()
        base = np.array(
            [ax + (_shelf[0] - float(tpz[0])), ay + (_shelf[1] - float(tpz[1]))]
        )
        arm = PLACE_LOW
        if (
            abs(float(tpz[0]) - _shelf[0]) < 0.06
            and abs(float(tpz[1]) - _shelf[1]) < 0.10
        ):
            _g["_IC_JOINT_ACK"] = None
            _g["_IC_JOINT_REQ"] = {"op": "detach"}
            setp("release")
        elif t > 900:
            print(
                "IC_JHAUL_CREEP_TIMEOUT tote=(%.2f,%.2f) seat=(%.2f,%.2f)"
                % (tpz[0], tpz[1], _shelf[0], _shelf[1]),
                flush=True,
            )
            _g["_IC_JOINT_ACK"] = None
            _g["_IC_JOINT_REQ"] = {"op": "detach"}
            setp("release")  # depart gate will report honestly
    elif st == "release":
        base = _pbase
        arm = PLACE_LOW
        ack = _g.get("_IC_JOINT_ACK")
        if ack is not None and t >= 60:
            S["joint_on"] = False
            setp("unhook")
        elif ack is None and t > 240:
            finish(False, False, "release failed: joint op timeout")
            return
    elif st == "unhook":
        base = _pbase
        al = _smoothstep5(t / 80.0)
        arm = (1 - al) * PLACE_LOW + al * UNHOOK
        if t >= 90:
            setp("backout")
    elif st == "backout":
        base = _stage
        arm = UNHOOK
        if ((ax - _stage[0]) ** 2 + (ay - _stage[1]) ** 2) ** 0.5 < 0.15 or t > 600:
            setp("retract")
    elif st == "retract":
        base = _stage
        al = _smoothstep5(t / 150.0)
        arm = (1 - al) * UNHOOK + al * HOME
        if t >= 150:
            setp("depart")
    elif st == "depart":
        park = np.array(_g.get("AMR_PARK", tuple(DOCK)), float)
        yaw = YAW_RACK
        base = park
        arm = HOME
        d = ((ax - park[0]) ** 2 + (ay - park[1]) ** 2) ** 0.5
        if d < 0.5 or t > 2400:
            S["cargo_stable_ticks"] = 0
            setp("validate")
    elif st == "validate":
        # The tote has rotated 90 degrees relative to its table pose.  Check
        # cargo in the tote's local frame, not against fixed world X/Y bounds,
        # and require a short stable window after the final solver motion.
        park = np.array(_g.get("AMR_PARK", tuple(DOCK)), float)
        yaw = YAW_RACK
        base = park
        arm = HOME
        tpz, tqz = _tote.get_world_pose()
        up_z = 1.0 - 2.0 * (float(tqz[1]) ** 2 + float(tqz[2]) ** 2)
        tote_ok = bool(
            abs(float(tpz[0]) - _shelf[0]) < 0.15
            and abs(float(tpz[1]) - _shelf[1]) < 0.20
            and 0.45 < float(tpz[2]) < 0.65
            and up_z > 0.9
        )
        missing = [
            _cargo_index
            for _cargo_index in S.get("cargo_manifest", [])
            if not _cargo_is_inside(
                tpz,
                tqz,
                wrp[_cargo_index].get_world_pose()[0],
            )
        ]
        if tote_ok and not missing:
            S["cargo_stable_ticks"] = int(S.get("cargo_stable_ticks", 0)) + 1
            if S["cargo_stable_ticks"] >= _CARGO_VERIFY_STABLE_TICKS:
                retained = len(S.get("cargo_manifest", []))
                finish(
                    True,
                    True,
                    "tote seated on shelf cargo_retained=%d/%d stable_ticks=%d"
                    % (retained, retained, S["cargo_stable_ticks"]),
                )
                return
        else:
            S["cargo_stable_ticks"] = 0
        if t >= _CARGO_VERIFY_TIMEOUT_TICKS:
            if missing:
                reason = (
                    "tote seated but cargo lost indices=%s after %d validation ticks"
                    % (
                        missing,
                        t,
                    )
                )
            else:
                reason = "tote=(%.2f,%.2f,%.2f) up_z=%.2f not on seat (%.2f,%.2f)" % (
                    tpz[0],
                    tpz[1],
                    tpz[2],
                    up_z,
                    _shelf[0],
                    _shelf[1],
                )
            finish(False, False, reason)
            return

    carrying = bool(S.get("joint_on"))
    # GR_PIN closes the fingers onto the grab-pin handle (visual hold; the
    # joint is the lock); slim closed profile also through the escape
    if st == "grabwait":
        _close_alpha = _smoothstep5(t / float(_GRIP_CLOSE_TICKS))
        grip = (1.0 - _close_alpha) * GR_OPEN + _close_alpha * GR_PIN
    else:
        grip = (
            GR_PIN
            if (carrying or st in ("release", "unhook", "backout"))
            else GR_OPEN
        )
    d = base - S["cbase"]
    dn = float(np.linalg.norm(d))
    S["cbase"] = (S["cbase"] + d / dn * MAX_STEP) if dn > MAX_STEP else base.copy()
    tgt = jp.copy()
    bj = b2j(S["cbase"])
    tgt[0] = bj[0]
    tgt[1] = bj[1]
    tgt[2] = yaw
    tgt[3:10] = arm
    tgt[10:12] = [grip, grip]
    amr.apply_action(ArticulationAction(joint_positions=tgt))
    S["t"] += 1


_g["run_haul"] = run_haul
print(
    "IC_JHAUL_PATCHED joint-carry v4: pre-contact manifest + impulse-safe grab",
    flush=True,
)

# heal the shared GR00T query port on every reset: cert staging repoints it
# to 5602 and a mistimed reset can strand it there (both arms then dial a
# dead socket - "Connection refused" on every dispatch)
if int(_g.get("_GR_RELAY_PORT_R", 5601)) != 5601:
    _s_stale = _g.get("_GRSOCK_R")
    if _s_stale is not None:
        try:
            _s_stale.close()
        except Exception:
            pass
    _g["_GRSOCK_R"] = None
    _g["_GR_RELAY_PORT_R"] = 5601
    print("IC_JHAUL_PORT_HEALED 5601", flush=True)
