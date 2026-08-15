# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Swap the environment floor LIVE (no reload): warehouse -> clean industrial grid floor.
import omni.usd
stage = omni.usd.get_context().get_stage()
root = stage.GetRootLayer()
new = []
for p in root.subLayerPaths:
    if "Simple_Warehouse/warehouse.usd" in p:
        new.append(p.replace("Simple_Warehouse/warehouse.usd", "Grid/default_environment.usd"))
    else:
        new.append(p)
root.subLayerPaths = new
print(">>> floor swapped. sublayers now:", list(root.subLayerPaths))
