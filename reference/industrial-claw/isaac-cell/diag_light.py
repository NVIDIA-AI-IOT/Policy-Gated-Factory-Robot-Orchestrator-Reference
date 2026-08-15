# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import omni.usd, carb
from pxr import Usd, UsdLux, UsdGeom, Gf, Sdf
M = "LIGHTDIAG"
stage = omni.usd.get_context().get_stage()
s = carb.settings.get_settings()

def g(k):
    try: return s.get(k)
    except Exception as e: return f"<err {e}>"

print(f"{M} ===== RENDER / EXPOSURE SETTINGS =====", flush=True)
for k in ["/rtx/post/histogram/enabled",
          "/rtx/post/tonemap/op",
          "/rtx/post/tonemap/cameraShutter",
          "/rtx/post/tonemap/iso",
          "/rtx/post/tonemap/fNumber",
          "/rtx/post/histogram/whiteScale",
          "/rtx/post/histogram/maxEV",
          "/rtx/post/histogram/minEV",
          "/rtx/post/colorcorr/enabled",
          "/rtx/sceneDb/ambientLightIntensity",
          "/rtx/indirectDiffuse/enabled",
          "/rtx/directLighting/sampledLighting/enabled",
          "/rtx/domeLight/upperLowerStrategy",
          "/rtx/rendermode",
          "/rtx-transient/resourcemanager/enableTextureStreaming"]:
    print(f"{M} setting {k} = {g(k)}", flush=True)

# tonemap op meaning: 0=Clamp,1=Linear?,... print what we see
print(f"{M} ===== STAGE INFO =====", flush=True)
print(f"{M} defaultPrim = {stage.GetDefaultPrim().GetPath() if stage.GetDefaultPrim() else None}", flush=True)
print(f"{M} upAxis = {UsdGeom.GetStageUpAxis(stage)}  mpu = {UsdGeom.GetStageMetersPerUnit(stage)}", flush=True)

print(f"{M} ===== ALL UsdLux LIGHT PRIMS =====", flush=True)
for prim in stage.Traverse():
    if not prim.HasAPI(UsdLux.LightAPI) and not prim.IsA(UsdLux.BoundableLightBase) and not prim.IsA(UsdLux.NonboundableLightBase):
        # fallback: type name contains "Light"
        if "Light" not in prim.GetTypeName():
            continue
    path = prim.GetPath()
    tn = prim.GetTypeName()
    api = UsdLux.LightAPI(prim)
    def attr(name):
        a = prim.GetAttribute(name)
        return a.Get() if (a and a.HasAuthoredValue()) else None
    # intensity: authored vs computed
    iA = prim.GetAttribute("inputs:intensity")
    iLegacy = prim.GetAttribute("intensity")
    imageable = UsdGeom.Imageable(prim)
    vis = imageable.ComputeVisibility() if imageable else "?"
    print(f"{M} ---- {path} type={tn}", flush=True)
    print(f"{M}      inputs:intensity authored={iA.HasAuthoredValue() if iA else False} val={iA.Get() if iA else None}", flush=True)
    print(f"{M}      legacy intensity authored={iLegacy.HasAuthoredValue() if iLegacy else False} val={iLegacy.Get() if iLegacy else None}", flush=True)
    print(f"{M}      inputs:exposure = {attr('inputs:exposure')}", flush=True)
    print(f"{M}      inputs:normalize = {attr('inputs:normalize')}", flush=True)
    print(f"{M}      inputs:color = {attr('inputs:color')}", flush=True)
    print(f"{M}      inputs:enableColorTemperature = {attr('inputs:enableColorTemperature')}", flush=True)
    print(f"{M}      inputs:texture:file = {attr('inputs:texture:file')}", flush=True)
    print(f"{M}      visibility(computed) = {vis}  activeprim={prim.IsActive()}", flush=True)
    # world transform + -Z aim for distant/etc
    xc = UsdGeom.XformCache(Usd.TimeCode.Default())
    m = xc.GetLocalToWorldTransform(prim)
    # local -Z transformed to world (direction a DistantLight points)
    negZ = m.TransformDir(Gf.Vec3d(0,0,-1))
    print(f"{M}      world -Z aim dir = ({negZ[0]:.3f},{negZ[1]:.3f},{negZ[2]:.3f})  (DistantLight shines this way)", flush=True)
    # xformOpOrder
    xf = UsdGeom.Xformable(prim)
    print(f"{M}      xformOpOrder = {[op.GetOpName() for op in xf.GetOrderedXformOps()]}", flush=True)

print(f"{M} ===== VIEWPORT / RENDERER =====", flush=True)
try:
    import omni.kit.viewport.utility as vu
    vp = vu.get_active_viewport()
    print(f"{M} active viewport renderer = {vp.hydra_engine if hasattr(vp,'hydra_engine') else '?'} camera={vp.camera_path}", flush=True)
except Exception as e:
    print(f"{M} viewport query err: {e}", flush=True)
print(f"{M} DONE", flush=True)
