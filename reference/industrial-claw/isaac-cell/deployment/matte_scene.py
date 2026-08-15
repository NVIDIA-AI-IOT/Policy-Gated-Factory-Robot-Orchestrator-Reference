# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Matte-ify table/conveyor/tote/pads/blocks to kill specular glare (roughness->1, no specular/clearcoat/metallic).
from pxr import Usd, UsdShade, UsdGeom, Gf, Sdf
import traceback
try:
    SUBTREES = ["/Workcell/BigTable", "/Workcell/Conveyor", "/World/BigTote", "/World/BigTote_R"]
    _MS_CUBES = ["/World/SortCube_R", "/World/SortCube_R2", "/World/SortCube_B",
             "/World/SortCube_B2", "/World/SortCube_G", "/World/SortCube_G2"]
    _MS_PADS = ["/World/BigTote/pad_red", "/World/BigTote/pad_blue", "/World/BigTote/pad_green",
            "/World/BigTote_R/pad_red", "/World/BigTote_R/pad_blue", "/World/BigTote_R/pad_green"]

    def bound_surface(prim):
        try:
            r = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            mat = r[0] if isinstance(r, tuple) else r
            if not (mat and mat.GetPrim().IsValid()): return None
            ss = mat.ComputeSurfaceSource()
            surf = ss[0] if isinstance(ss, tuple) else ss
            return surf if (surf and surf.GetPrim().IsValid()) else None
        except Exception:
            return None

    def setin(surf, name, tv, val):
        i = surf.GetInput(name)
        if not i: i = surf.CreateInput(name, tv)
        i.Set(val)

    def matte_surface(surf):
        setin(surf, "roughness", Sdf.ValueTypeNames.Float, 1.0)
        setin(surf, "metallic", Sdf.ValueTypeNames.Float, 0.0)
        setin(surf, "clearcoat", Sdf.ValueTypeNames.Float, 0.0)
        setin(surf, "clearcoatRoughness", Sdf.ValueTypeNames.Float, 1.0)
        for i in surf.GetInputs():
            bn = i.GetBaseName().lower()
            if "specular" in bn or "reflect" in bn:
                try: i.Set(0.0)
                except Exception:
                    try: i.Set(Gf.Vec3f(0, 0, 0))
                    except Exception: pass

    def bind_matte_color(prim):
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
        UsdShade.MaterialBindingAPI.Apply(prim); UsdShade.MaterialBindingAPI(prim).Bind(mat)

    done_mats = set(); n_surf = 0; n_bind = 0
    def process(prim):
        global n_surf, n_bind
        if not prim.IsValid() or not prim.IsA(UsdGeom.Gprim): return
        surf = bound_surface(prim)
        if surf is not None:
            mpath = surf.GetPath().pathString
            if mpath not in done_mats:
                matte_surface(surf); done_mats.add(mpath); n_surf += 1
        elif UsdGeom.Gprim(prim).GetDisplayColorAttr().Get():
            bind_matte_color(prim); n_bind += 1

    for st in SUBTREES:
        root = stage.GetPrimAtPath(st)
        if root.IsValid():
            for q in Usd.PrimRange(root): process(q)
    for path in _MS_CUBES + _MS_PADS:
        process(stage.GetPrimAtPath(path))
    print("MATTE_DONE surfaces_matted=%d displaycolor_bound=%d" % (n_surf, n_bind), flush=True)
except Exception:
    print("MATTE_ERR:\n" + traceback.format_exc(), flush=True)
