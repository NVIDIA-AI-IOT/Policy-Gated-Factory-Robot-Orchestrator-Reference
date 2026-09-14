# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# pgfr_boot.py — run this once in the Script Editor after a container start:
#   exec(open("/scripts/pgfr_boot.py").read())
# Loads the stage and brings up the whole cell via the pgfr_cell package (T3 path).
# Safe to re-run after updating the package: the previous runtime is shut down
# and all pgfr_cell modules are reloaded. Fallback: classic startup.py + cmd.py.
import importlib
import sys

if "/scripts" not in sys.path:
    sys.path.insert(0, "/scripts")

# shut down a previous runtime BEFORE reloading (reload would orphan its step loop)
_prev_boot = sys.modules.get("pgfr_cell.boot")
if _prev_boot is not None:
    try:
        _rt = _prev_boot.runtime()
        if _rt is not None:
            _rt.shutdown()
            print(">>> pgfr_boot: previous runtime shut down", flush=True)
    except Exception:
        pass

import pgfr_cell
import pgfr_cell.boot
import pgfr_cell.cameras
import pgfr_cell.dressing
import pgfr_cell.runtime

for _m in (pgfr_cell.runtime, pgfr_cell.cameras, pgfr_cell.dressing, pgfr_cell.boot):
    importlib.reload(_m)

pgfr_cell.boot.bring_up()
