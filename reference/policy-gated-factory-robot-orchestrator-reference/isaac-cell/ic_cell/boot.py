# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""One-call cell bring-up: stage prep -> physics runtime -> deterministic reset.

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


def _normalize_stage_identifier(identifier):
    """Canonicalize local stage paths while preserving asset-server URLs."""
    if not identifier:
        return ""
    identifier = os.path.expanduser(str(identifier))
    if "://" in identifier:
        return identifier.rstrip("/")
    return os.path.normcase(os.path.realpath(os.path.abspath(identifier)))


def runtime():
    return _runtime


def bring_up(stage_path: str = None):
    global _runtime
    try:
        path = stage_path or STAGE_PATH
        requested_identifier = _normalize_stage_identifier(path)
        ctx = omni.usd.get_context()
        if _runtime is not None:
            _runtime.shutdown()
            _runtime = None
        stage = ctx.get_stage()
        root = stage.GetRootLayer() if stage is not None else None
        needs_open = True
        if (
            root is not None
            and _normalize_stage_identifier(root.identifier) == requested_identifier
            and stage.GetPrimAtPath("/World").IsValid()
        ):
            needs_open = False
        # A previous bring-up leaves physics views + OmniGraphs that cannot be
        # rebuilt on a live stage (stale-view Franka error, existing /ROS_* graphs).
        # Evidence of one -> force a clean stage reload first (~1-3 min).
        if not needs_open and stage.GetPrimAtPath("/ROS_TableCam").IsValid():
            print(">>> ic_cell: previous bring-up detected — reloading the stage for a clean rebuild", flush=True)
            needs_open = True
        if needs_open:
            print(">>> ic_cell: opening stage %s" % path, flush=True)
            if not ctx.open_stage(path):
                raise RuntimeError("failed to open Isaac stage: %s" % path)
        stage = ctx.get_stage()
        if stage is None:
            raise RuntimeError("Isaac stage context has no current stage")
        root = stage.GetRootLayer()
        if root is None:
            raise RuntimeError("Isaac stage has no root layer")
        actual_identifier = _normalize_stage_identifier(root.identifier)
        if actual_identifier != requested_identifier:
            raise RuntimeError(
                "Isaac stage identity mismatch: requested=%s actual=%s"
                % (requested_identifier, actual_identifier)
            )
        if not stage.GetPrimAtPath("/World").IsValid():
            raise RuntimeError("Isaac stage is missing required /World prim")
        from ic_cell import cameras, dressing
        from ic_cell.runtime import CellRuntime

        def prepare_stage(stage):
            # Every topology edit must precede World.reset()/tensor view creation.
            cameras.prepare_robot_camera_geometry(stage)
            cameras.build_gr00t_cams()
            dressing.add_tote_pads()
            dressing.matte_scene()
            cameras.build_floor_cams()
            cameras.validate_prepared_camera_stage(stage)

        rt = CellRuntime(pre_physics_prepare=prepare_stage)
        rt.run()                                 # play + physics-step subscription
        rt.request_reset()                       # demo start, applied after physics ticks
        _runtime = rt
        return rt
    except Exception:
        print("IC_CELL_BOOT_ERR:\n" + traceback.format_exc(), flush=True)
        raise
