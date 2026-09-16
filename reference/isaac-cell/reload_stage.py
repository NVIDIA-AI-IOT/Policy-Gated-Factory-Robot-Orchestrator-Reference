# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# reload_stage.py — recover from a sim-view invalidation (link_names): stop the
# erroring step callback, then reopen the saved cell scene fresh.
import omni.usd

for _k in ("_PGFR_SUB", "_DEMO_SUB"):
    _sub = globals().get(_k)
    if _sub is not None:
        try:
            _sub.unsubscribe()
        except Exception:
            pass
        globals()[_k] = None

_ok = omni.usd.get_context().open_stage("/scripts/our_factory.usda")
print("OPEN_STAGE_OK" if _ok else "OPEN_STAGE_FAIL", flush=True)
