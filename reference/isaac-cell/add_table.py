# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import omni.usd
from pxr import UsdGeom, Gf

# A warehouse "packing table" from NVIDIA's asset library (confirmed to exist).
URL = "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Props/PackingTable/packing_table.usd"
PRIM_PATH = "/World/PackingTable"

stage = omni.usd.get_context().get_stage()

# Create an Xform and reference the table asset into it (non-destructive layering).
prim = stage.DefinePrim(PRIM_PATH, "Xform")
prim.GetReferences().AddReference(URL)

# Place it at the world origin on the floor. Change these numbers to move it
# (units are meters; X, Y on the floor, Z is up).
xform = UsdGeom.Xformable(prim)
xform.ClearXformOpOrder()
xform.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.0))

print(f"[add_table] Added table at {PRIM_PATH} -> {URL}")
