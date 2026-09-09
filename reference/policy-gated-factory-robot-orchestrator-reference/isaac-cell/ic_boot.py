# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# ic_boot.py — run this once in the Script Editor after a container start:
#   exec(open("/scripts/ic_boot.py").read())
# Loads the stage and brings up the whole cell via the ic_cell package (T3 path).
# Safe to re-run after updating the package: the previous runtime is shut down
# and all ic_cell modules are reloaded. Fallback: classic startup.py + cmd.py.
import importlib
import sys

if "/scripts" not in sys.path:
    sys.path.insert(0, "/scripts")

# shut down a previous runtime BEFORE reloading (reload would orphan its step loop)
_prev_boot = sys.modules.get("ic_cell.boot")
if _prev_boot is not None:
    try:
        _rt = _prev_boot.runtime()
        if _rt is not None:
            _rt.shutdown()
            print(">>> ic_boot: previous runtime shut down", flush=True)
    except Exception:
        pass

import ic_cell
import ic_cell.boot
import ic_cell.cameras
import ic_cell.dressing
import ic_cell.runtime

for _m in (ic_cell.runtime, ic_cell.cameras, ic_cell.dressing, ic_cell.boot):
    importlib.reload(_m)

ic_cell.boot.bring_up()
