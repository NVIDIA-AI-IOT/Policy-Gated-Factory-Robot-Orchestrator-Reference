# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import omni.usd, carb
M = "LIGHTDIAG2"
s = carb.settings.get_settings()
def g(k):
    try: return s.get(k)
    except Exception as e: return f"<err {e}>"
# More exposure-relevant keys
for k in ["/rtx/post/tonemap/op",
          "/rtx/post/tonemap/enabled",
          "/rtx/post/tonemap/maxBurnOut",
          "/rtx/post/tonemap/whitepoint",
          "/rtx/post/tonemap/exposure",
          "/rtx/post/histogram/enabled",
          "/rtx/post/histogram/minEV",
          "/rtx/post/histogram/maxEV",
          "/rtx/post/histogram/tau",
          "/rtx/post/histogram/whiteScale",
          "/rtx/post/histogram/useExposureClamping",
          "/rtx/post/histogram/filterType",
          "/rtx/pathtracing/maxBounces",
          "/rtx/pathtracing/totalSpp",
          "/rtx/sceneDb/ambientLightIntensity",
          "/rtx/scene/common/meterPerUnit",
          "/app/hydra/aperture/conform"]:
    print(f"{M} {k} = {g(k)}", flush=True)
print(f"{M} DONE", flush=True)
