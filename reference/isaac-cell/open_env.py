# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import omni.usd

URL = "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Environments/Simple_Warehouse/warehouse.usd"

ctx = omni.usd.get_context()
ok = ctx.open_stage(URL)
print(f"[open_env] open_stage('{URL}') -> {ok}")
