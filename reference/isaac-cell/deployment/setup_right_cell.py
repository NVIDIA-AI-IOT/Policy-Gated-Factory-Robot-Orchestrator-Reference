# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# setup_right_cell.py — mirror the left workcell for franka_right (+1.8m x offset).
# Creates (idempotent, pure USD — run BEFORE pgfr_node_v2 so it can bind handles):
#   /World/BigTote_R        second tote at the right arm's relative tote position
#   (colored pads on it, same layout as add_tote_colors)
#   /Workcell/Franka_Right/panda_hand/WristCam   same baked eye-in-hand matrix as left
#   /RackCam_BR             right outside cam at the CONTRACT pose + (1.8, 0, 0)
import json
import traceback

try:
    import omni
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

    stage = omni.usd.get_context().get_stage()

    # --- second tote: copy the BigTote spec (carries physics APIs), reposition ---
    TOTE_R = "/World/BigTote_R"
    if not stage.GetPrimAtPath(TOTE_R).IsValid():
        Sdf.CopySpec(stage.GetRootLayer(), Sdf.Path("/World/BigTote"),
                     stage.GetRootLayer(), Sdf.Path(TOTE_R))
    tp = stage.GetPrimAtPath(TOTE_R)
    for op in UsdGeom.Xformable(tp).GetOrderedXformOps():
        if op.GetOpName() == "xformOp:translate":
            op.Set(Gf.Vec3d(5.451, -7.701, 0.665))  # STRICT twin offset from the shifted arm (4.965 + 0.486)
        if op.GetOpName() == "xformOp:orient":
            op.Set(Gf.Quatf(1.0, 0, 0, 0))  # identity: pads read exactly like the left tote (north twin)
    a = UsdPhysics.RigidBodyAPI(tp).GetKinematicEnabledAttr()
    if a and a.IsValid():
        a.Set(False)

    # --- colored pads on the right tote (same layout as add_tote_colors) ---
    COMP_LOCAL = {"red": -0.1975, "blue": 0.0, "green": 0.1975}
    RGB = {"red": (0.9, 0.08, 0.08), "blue": (0.1, 0.2, 0.9), "green": (0.1, 0.75, 0.18)}
    for color, x in COMP_LOCAL.items():
        path = "%s/pad_%s" % (TOTE_R, color)
        if stage.GetPrimAtPath(path).IsValid():
            stage.RemovePrim(path)
        c = UsdGeom.Cube.Define(stage, path)
        c.GetSizeAttr().Set(1.0)
        xf = UsdGeom.Xformable(c.GetPrim())
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(x, 0.0, 0.008))
        xf.AddScaleOp().Set(Gf.Vec3f(0.16, 0.16, 0.006))  # same 16x16cm pads as the left tote
        c.GetDisplayColorAttr().Set([Gf.Vec3f(*RGB[color])])

    # 2026-07-18 (user-directed): north-facing twin, shifted inboard so the
    # STRICT twin layout (all left-cell offsets) fits fully on the table.
    # Arm world x: 5.44 -> 4.965 (Workcell-local 0.9 -> 0.425).
    fr = stage.GetPrimAtPath("/Workcell/Franka_Right")
    if fr.IsValid():
        for op in UsdGeom.Xformable(fr).GetOrderedXformOps():
            if op.GetOpName() == "xformOp:orient":
                op.Set(Gf.Quatd(1.0, 0.0, 0.0, 0.0))
            if op.GetOpName() == "xformOp:rotateZ":
                op.Set(0.0)
            if op.GetOpName() == "xformOp:translate":
                v = op.Get()
                op.Set(Gf.Vec3d(0.425, v[1], v[2]))

    # --- right wrist cam: same baked hand-local matrix as the left (06-22) ---
    HAND_R = "/Workcell/Franka_Right/panda_hand"
    WCAM_R = HAND_R + "/WristCam"
    if stage.GetPrimAtPath(WCAM_R).IsValid():
        stage.RemovePrim(WCAM_R)
    wc = UsdGeom.Camera.Define(stage, WCAM_R)
    wc.GetFocalLengthAttr().Set(16.0)
    wc.GetClippingRangeAttr().Set(Gf.Vec2f(0.005, 12.0))
    xf = UsdGeom.Xformable(wc.GetPrim())
    xf.ClearXformOpOrder()
    _M = Gf.Matrix4d(-0.659877, -0.127132, -0.740540, 0.0,
                     -0.214963,  0.976329,  0.023937, 0.0,
                      0.719968,  0.174984, -0.671585, 0.0,
                      0.270284,  0.045531, -0.041819, 1.0)
    xf.AddTransformOp().Set(_M)

    # --- right outside cam: CONTRACT pose shifted by the arm-base offset (+1.8 x) ---
    exp = json.load(open("/scripts/production_contract_expected.json"))
    cam = exp["cameras"]["outside"]
    q = cam["quaternion_opengl_xyzw"]
    rot = Gf.Quatd(float(q[3]), Gf.Vec3d(float(q[0]), float(q[1]), float(q[2])))
    M = Gf.Matrix4d().SetRotate(rot)
    pos = [float(v) for v in cam["position"]]
    M.SetTranslateOnly(Gf.Vec3d(pos[0] + 1.325, pos[1], pos[2]))  # contract offset from the shifted arm (4.965-3.64)
    OCAM_R = "/RackCam_BR"
    if stage.GetPrimAtPath(OCAM_R).IsValid():
        stage.RemovePrim(OCAM_R)
    oc = UsdGeom.Camera.Define(stage, OCAM_R)
    oc.GetFocalLengthAttr().Set(float(cam["focal_length"]))
    xfo = UsdGeom.Xformable(oc.GetPrim())
    xfo.ClearXformOpOrder()
    xfo.AddTransformOp().Set(M)

    # invisible collider for the rack's SECOND shelf level (mirror of ShelfPad1
    # at the level above) so the right tote lands solidly instead of bouncing
    PAD2 = "/World/ShelfPad2"
    if not stage.GetPrimAtPath(PAD2).IsValid():
        c2 = UsdGeom.Cube.Define(stage, PAD2)
        c2.GetSizeAttr().Set(1.0)
        p2 = c2.GetPrim()
        xf2 = UsdGeom.Xformable(p2)
        xf2.ClearXformOpOrder()
        xf2.AddTranslateOp().Set(Gf.Vec3d(-0.26, -7.40, 0.79))
        xf2.AddScaleOp().Set(Gf.Vec3f(0.7, 1.55, 0.07))
        UsdPhysics.CollisionAPI.Apply(p2)
        UsdGeom.Imageable(p2).MakeInvisible()

    print("PGFR_RIGHT_CELL_SETUP tote_R@(5.451,-7.701) pads wristR outsideR@(%.2f,%.3f,%.3f)"
          % (pos[0] + 1.8, pos[1], pos[2]), flush=True)
except Exception:
    print("PGFR_RIGHT_CELL_ERR:\n" + traceback.format_exc(), flush=True)
