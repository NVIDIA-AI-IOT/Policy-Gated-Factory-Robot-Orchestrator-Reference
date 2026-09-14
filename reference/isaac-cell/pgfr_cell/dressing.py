# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Scene dressing: tote compartment pads + matte materials (anti-glare).

The cell boot sequence adds the pads and materials before physics starts.
"""
import omni.usd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

TOTE = "/World/BigTote"
COMP_LOCAL = {"red": -0.1975, "blue": 0.0, "green": 0.1975}   # matches runtime
PAD_RGB = {"red": (0.9, 0.08, 0.08), "blue": (0.1, 0.2, 0.9), "green": (0.1, 0.75, 0.18)}
Z_PAD = 0.008
MATTE_SUBTREES = ["/Workcell/BigTable", "/Workcell/Conveyor", "/World/BigTote"]
MATTE_CUBES = ["/World/SortCube_R", "/World/SortCube_R2", "/World/SortCube_B",
               "/World/SortCube_B2", "/World/SortCube_G", "/World/SortCube_G2"]
MATTE_PADS = ["/World/BigTote/pad_red", "/World/BigTote/pad_blue", "/World/BigTote/pad_green"]


def add_tote_pads():
    stage = omni.usd.get_context().get_stage()
    tp = stage.GetPrimAtPath(TOTE)
    if not tp.IsValid():
        print("TOTE_COLORS_ERR: %s missing" % TOTE, flush=True)
        return
    for color, x in COMP_LOCAL.items():
        path = "%s/pad_%s" % (TOTE, color)
        if stage.GetPrimAtPath(path).IsValid():
            stage.RemovePrim(path)
        c = UsdGeom.Cube.Define(stage, path)   # visual-only (no collider)
        c.GetSizeAttr().Set(1.0)
        xf = UsdGeom.Xformable(c); xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(x, 0.0, Z_PAD))
        xf.AddScaleOp().Set(Gf.Vec3f(0.16, 0.16, 0.006))
        c.GetDisplayColorAttr().Set([Gf.Vec3f(*PAD_RGB[color])])
    print("TOTE_COLORS_DONE", flush=True)


def _bound_surface(prim):
    try:
        r = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        mat = r[0] if isinstance(r, tuple) else r
        if not (mat and mat.GetPrim().IsValid()):
            return None
        ss = mat.ComputeSurfaceSource()
        surf = ss[0] if isinstance(ss, tuple) else ss
        return surf if (surf and surf.GetPrim().IsValid()) else None
    except Exception:
        return None


def _setin(surf, name, tv, val):
    i = surf.GetInput(name)
    if not i:
        i = surf.CreateInput(name, tv)
    i.Set(val)


def _matte_surface(surf):
    _setin(surf, "roughness", Sdf.ValueTypeNames.Float, 1.0)
    _setin(surf, "metallic", Sdf.ValueTypeNames.Float, 0.0)
    _setin(surf, "clearcoat", Sdf.ValueTypeNames.Float, 0.0)
    _setin(surf, "clearcoatRoughness", Sdf.ValueTypeNames.Float, 1.0)
    for i in surf.GetInputs():
        bn = i.GetBaseName().lower()
        if "specular" in bn or "reflect" in bn:
            try:
                i.Set(0.0)
            except Exception:
                try:
                    i.Set(Gf.Vec3f(0, 0, 0))
                except Exception:
                    pass


def _bind_matte_color(stage, prim):
    g = UsdGeom.Gprim(prim)
    dc = g.GetDisplayColorAttr().Get()
    col = tuple(float(x) for x in dc[0]) if dc else (0.5, 0.5, 0.5)
    mp = prim.GetPath().pathString + "/MatteMtl"
    mat = UsdShade.Material.Define(stage, mp)
    sh = UsdShade.Shader.Define(stage, mp + "/Surface"); sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*col))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    sh.CreateInput("clearcoat", Sdf.ValueTypeNames.Float).Set(0.0)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(prim)
    UsdShade.MaterialBindingAPI(prim).Bind(mat)


def matte_scene():
    stage = omni.usd.get_context().get_stage()
    done_mats = set(); counts = {"surf": 0, "bind": 0}

    def process(prim):
        if not prim.IsValid() or not prim.IsA(UsdGeom.Gprim):
            return
        surf = _bound_surface(prim)
        if surf is not None:
            mpath = surf.GetPath().pathString
            if mpath not in done_mats:
                _matte_surface(surf); done_mats.add(mpath); counts["surf"] += 1
        elif UsdGeom.Gprim(prim).GetDisplayColorAttr().Get():
            _bind_matte_color(stage, prim); counts["bind"] += 1
    for st in MATTE_SUBTREES:
        root = stage.GetPrimAtPath(st)
        if root.IsValid():
            for q in Usd.PrimRange(root):
                process(q)
    for path in MATTE_CUBES + MATTE_PADS:
        process(stage.GetPrimAtPath(path))
    print("MATTE_DONE surfaces_matted=%d displaycolor_bound=%d" % (counts["surf"], counts["bind"]), flush=True)
