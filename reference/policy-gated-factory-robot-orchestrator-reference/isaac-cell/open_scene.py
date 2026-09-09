# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import omni.usd
ok = omni.usd.get_context().open_stage("/scripts/my_pick_place.usda")
print("[open_scene] open_stage ->", ok)
