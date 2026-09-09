# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import omni, traceback
from pxr import UsdGeom, Usd, Gf
stage = omni.usd.get_context().get_stage()
TOTE = "/World/BigTote"
COMP_LOCAL = {"red": -0.1975, "blue": 0.0, "green": 0.1975}   # matches pgfr_node_v2
RGB = {"red": (0.9, 0.08, 0.08), "blue": (0.1, 0.2, 0.9), "green": (0.1, 0.75, 0.18)}
Z_PAD = 0.008        # just above the tote's inner floor (cube target sits at local z~0.04)
try:
    tp = stage.GetPrimAtPath(TOTE)
    if not tp.IsValid():
        print("TOTE_COLORS_ERR: %s missing" % TOTE, flush=True)
    else:
        bb = UsdGeom.Imageable(tp).ComputeLocalBound(Usd.TimeCode.Default(), UsdGeom.Tokens.default_).ComputeAlignedRange()
        print("tote local z range: %.3f .. %.3f" % (float(bb.GetMin()[2]), float(bb.GetMax()[2])), flush=True)
        for color, x in COMP_LOCAL.items():
            path = "%s/pad_%s" % (TOTE, color)
            if stage.GetPrimAtPath(path).IsValid():
                stage.RemovePrim(path)
            c = UsdGeom.Cube.Define(stage, path)          # visual-only (no collider) -> won't affect physics
            c.GetSizeAttr().Set(1.0)
            xf = UsdGeom.Xformable(c); xf.ClearXformOpOrder()
            xf.AddTranslateOp().Set(Gf.Vec3d(x, 0.0, Z_PAD))
            xf.AddScaleOp().Set(Gf.Vec3f(0.16, 0.16, 0.006))   # 16x16x0.6 cm pad
            c.GetDisplayColorAttr().Set([Gf.Vec3f(*RGB[color])])
            print("pad_%s at local x=%.4f z=%.3f" % (color, x, Z_PAD), flush=True)
        print("TOTE_COLORS_DONE", flush=True)
except Exception:
    print("TOTE_COLORS_ERR:\n" + traceback.format_exc(), flush=True)
