# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""One-call cell bring-up: stage -> runtime -> cameras -> dressing -> demo reset.

Replaces the 8-step cmd.py sequence (and its timing hazards) with one in-process,
sequential call. Same log markers as the classic bring-up, so existing monitoring
and the runbook stay valid.

    import ic_cell.boot
    ic_cell.boot.bring_up()          # full bring-up (loads the stage if needed)

Re-running tears down the previous runtime's physics subscription first — safe to
call again in the same session. The classic startup.py + cmd.py path is untouched
and remains the emergency fallback.
"""
import os
import traceback

import omni.usd

STAGE_PATH = os.environ.get("IC_STAGE", "/scripts/our_factory.usda")

_runtime = None   # singleton per kit session


def runtime():
    return _runtime


def bring_up(stage_path: str = None):
    global _runtime
    try:
        path = stage_path or STAGE_PATH
        ctx = omni.usd.get_context()
        if _runtime is not None:
            _runtime.shutdown()
            _runtime = None
        stage = ctx.get_stage()
        needs_open = True
        if stage is not None:
            ident = stage.GetRootLayer().identifier if stage.GetRootLayer() else ""
            if ident.endswith(os.path.basename(path)) and stage.GetPrimAtPath("/World").IsValid():
                needs_open = False
        # A previous bring-up leaves physics views + OmniGraphs that cannot be
        # rebuilt on a live stage (stale-view Franka error, existing /ROS_* graphs).
        # Evidence of one -> force a clean stage reload first (~1-3 min).
        if not needs_open and stage.GetPrimAtPath("/ROS_TableCam").IsValid():
            print(">>> ic_cell: previous bring-up detected — reloading the stage for a clean rebuild", flush=True)
            needs_open = True
        if needs_open:
            print(">>> ic_cell: opening stage %s" % path, flush=True)
            ctx.open_stage(path)
        from ic_cell import cameras, dressing
        from ic_cell.runtime import CellRuntime

        rt = CellRuntime()                       # world + robots + ROS node (cubes created)
        cameras.build_gr00t_cams()               # wrist cam + RackCam_B final pose + publishers
        dressing.add_tote_pads()                 # pads before matte (matte processes them)
        dressing.matte_scene()
        cameras.build_floor_cams()               # table_cam / rack_cam / inspect_cam
        rt.run()                                 # play + physics-step subscription
        rt.request_reset()                       # demo start, applied after physics ticks
        _runtime = rt
        print("IC_CELL_UP markers=all", flush=True)
        return rt
    except Exception:
        print("IC_CELL_BOOT_ERR:\n" + traceback.format_exc(), flush=True)
        raise
