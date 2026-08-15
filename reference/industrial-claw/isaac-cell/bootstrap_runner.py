# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# PASTE ONCE. Installs an auto-runner: any code written to /scripts/cmd.py runs
# automatically in this editor (shares globals, so `wt` etc. are available).
import omni.kit.app, os, traceback

_R = {"path": "/scripts/cmd.py", "mtime": None}
try:
    _R["mtime"] = os.path.getmtime(_R["path"]) if os.path.exists(_R["path"]) else None
except Exception:
    _R["mtime"] = None

def _poll(e=None):
    try:
        p = _R["path"]
        if not os.path.exists(p):
            return
        m = os.path.getmtime(p)
        if _R["mtime"] is None or m != _R["mtime"]:
            _R["mtime"] = m
            code = open(p).read()
            if code.strip():
                print(">>> [runner] executing /scripts/cmd.py", flush=True)
                try:
                    exec(compile(code, p, "exec"), globals())
                except Exception:
                    print("CMD_ERROR:\n" + traceback.format_exc(), flush=True)
    except Exception:
        print("RUNNER_ERROR:\n" + traceback.format_exc(), flush=True)

_old = globals().get("_CMD_RUNNER_SUB")
if _old is not None:
    try: _old.unsubscribe()
    except Exception: pass
_CMD_RUNNER_SUB = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(_poll, name="cmd_runner")
print(">>> COMMAND RUNNER INSTALLED — I can now run code automatically (no more pasting).", flush=True)
