# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""GUI --exec entrypoint: load and harden the complete IC scene, then arm cmd.py.

`STARTUP_DONE` is intentionally emitted only after the full scene contract
passes.  The host GUI launcher waits for that marker, so it can no longer
return successfully with only the base USD loaded.
"""

import os
import traceback

import omni.kit.app
import omni.usd


_STAGE_PATH = "/scripts/our_factory.usda"
_BOOTSTRAP_PATH = "/scripts/full_scene_bootstrap.py"
_CMD_PATH = "/scripts/cmd.py"
_STARTUP_REQUIRED_BASE_PRIMS = (
    "/World",
    "/World/BigTote",
    "/Workcell/Franka_Left",
    "/Workcell/Franka_Right",
    "/MobileBot",
    "/RackCam_A",
    "/RackCam_B",
)

_ctx = omni.usd.get_context()
_ctx.open_stage(_STAGE_PATH)
_R = {
    "path": _CMD_PATH,
    "mtime": None,
    "base_stable_ticks": 0,
    "auto_attempted": False,
    "full_scene_ready": False,
}
try:
    _R["mtime"] = os.path.getmtime(_CMD_PATH) if os.path.exists(_CMD_PATH) else None
except Exception:
    _R["mtime"] = None


def _base_stage_ready():
    _stage = _ctx.get_stage()
    if _stage is None:
        return False
    return all(_stage.GetPrimAtPath(_path).IsValid() for _path in _STARTUP_REQUIRED_BASE_PRIMS)


def _exec_file(_path, _label):
    if not os.path.exists(_path):
        raise RuntimeError("missing startup command file: %s" % _path)
    _code = open(_path, encoding="utf-8").read()
    if not _code.strip():
        raise RuntimeError("startup command file is empty: %s" % _path)
    print(">>> [runner] %s %s" % (_label, _path), flush=True)
    exec(compile(_code, _path, "exec"), globals())


def _poll(_event=None):
    try:
        if not _R["auto_attempted"]:
            if not _base_stage_ready():
                _R["base_stable_ticks"] = 0
                return
            _R["base_stable_ticks"] += 1
            # Let referenced USD payloads settle before World/tensor creation.
            if _R["base_stable_ticks"] < 180:
                return
            _R["auto_attempted"] = True
            try:
                _exec_file(_BOOTSTRAP_PATH, "auto full-scene bootstrap")
                if not globals().get("_IC_FULL_SCENE_READY", False):
                    raise RuntimeError(
                        "full_scene_bootstrap.py returned without _IC_FULL_SCENE_READY"
                    )
                _R["full_scene_ready"] = True
                print(">>> STARTUP_DONE full_scene+runner", flush=True)
            except Exception:
                print("IC_FULL_SCENE_BOOT_ERR:\n" + traceback.format_exc(), flush=True)
            return

        if not _R["full_scene_ready"]:
            return
        _path = _R["path"]
        if not os.path.exists(_path):
            return
        _mtime = os.path.getmtime(_path)
        if _R["mtime"] is None or _mtime != _R["mtime"]:
            _R["mtime"] = _mtime
            try:
                _exec_file(_path, "exec updated")
            except Exception:
                print("CMD_ERROR:\n" + traceback.format_exc(), flush=True)
    except Exception:
        print("RUNNER_ERROR:\n" + traceback.format_exc(), flush=True)


_CMD_RUNNER_SUB = (
    omni.kit.app.get_app()
    .get_update_event_stream()
    .create_subscription_to_pop(_poll, name="cmd_runner")
)
print(">>> STARTUP_ARMED waiting_for_full_scene", flush=True)
