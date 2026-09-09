# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Install the Policy-Gated Factory Robot Orchestrator Reference V36 executor for both Franka arms.

The executor is ordinary source installed beside this loader.  It is evaluated
once in the left cell context and once in an isolated right-arm context, then
the public ``start`` and ``run_move`` callbacks route by endpoint.
"""

import traceback


_V36_EXECUTOR_PATH = (
    "/scripts/native_droid_work/executors/"
    "follow_groot_home_convergence_v36.py"
)
_V36_REVISION = "home_convergence_v36_direct"
_V36_CONTEXTS_KEY = "_IC_DUAL_GROOT_V36H_CONTEXTS"
_V36_STARTS_KEY = "_IC_DUAL_GROOT_V36H_STARTS"
_V36_RUNS_KEY = "_IC_DUAL_GROOT_V36H_RUNS"


def _ic_groot_install_task_allowed(task):
    """Allow installation only while idle or inside the owned reset transaction."""
    return task is None or (
        isinstance(task, dict) and task.get("action") == "reset_scene"
    )


try:
    _dual_globals = globals()
    if not _ic_groot_install_task_allowed(S.get("task")):
        raise RuntimeError("refusing dual GR00T install during an active task")

    if _dual_globals.get(_V36_CONTEXTS_KEY) is None:
        with open(_V36_EXECUTOR_PATH, "r", encoding="utf-8") as _stream:
            _executor_source = _stream.read()
        compile(_executor_source, _V36_EXECUTOR_PATH, "exec")

        exec(
            compile(_executor_source, _V36_EXECUTOR_PATH, "exec"),
            _dual_globals,
        )
        _left_start = _dual_globals.get("start")
        _left_run_move = _dual_globals.get("run_move")
        if (
            not callable(_left_start)
            or not callable(_left_run_move)
            or _dual_globals.get("_IC_GROOT_EXECUTION_REVISION")
            != _V36_REVISION
        ):
            raise RuntimeError("left V36 executor did not install")

        _right_frames = _dual_globals.get("_GRFR")
        if _right_frames is None:
            _right_frames = {}

            def _right_image_callback(_name):
                def _callback(_message):
                    _right_frames[_name] = _message

                return _callback

            _dual_globals["_IC_DUAL_RIGHT_WRIST_SUB"] = node.create_subscription(
                Image,
                "/wrist_right_cam/image_raw",
                _right_image_callback("wrist"),
                10,
            )
            _dual_globals["_IC_DUAL_RIGHT_OUTSIDE_SUB"] = node.create_subscription(
                Image,
                "/outside_right_cam/image_raw",
                _right_image_callback("outside"),
                10,
            )

        _right_context = dict(_dual_globals)
        _right_context.update(
            {
                "__name__": "_ic_groot_right_physical_v36",
                "__file__": _V36_EXECUTOR_PATH,
                "frL": frR,
                "fhand": fhandR,
                "ctrl": ctrlR,
                "_GRF": _right_frames,
                "_GRWSUB": _dual_globals.get("_GRWSUB_R") or object(),
                "_GROSUB": _dual_globals.get("_GROSUB_R") or object(),
                "_GRSOCK": None,
            }
        )
        _main_comp_world = _dual_globals["comp_world"]
        _right_tote = _dual_globals.get("tp_r")

        def _right_comp_world(_color, _unused_tote=None):
            return _main_comp_world(_color, _right_tote)

        _right_context["comp_world"] = _right_comp_world
        exec(
            compile(_executor_source, _V36_EXECUTOR_PATH, "exec"),
            _right_context,
        )
        if (
            not callable(_right_context.get("start"))
            or not callable(_right_context.get("run_move"))
            or _right_context.get("_IC_GROOT_EXECUTION_REVISION")
            != _V36_REVISION
        ):
            raise RuntimeError("right V36 executor did not install")

        _contexts = {
            "franka_left": _dual_globals,
            "franka_right": _right_context,
        }
        _starts = {
            "franka_left": _left_start,
            "franka_right": _right_context["start"],
        }
        _runs = {
            "franka_left": _left_run_move,
            "franka_right": _right_context["run_move"],
        }

        def _dual_start(_command):
            _endpoint = _command.get("endpoint") or "franka_left"
            if _endpoint not in _starts:
                if (
                    _endpoint == "mobilebot"
                    and _command.get("action") in ("pick_and_place", "haul")
                ):
                    return _left_start(_command)
                raise ValueError("unsupported GR00T endpoint: %s" % _endpoint)
            return _starts[_endpoint](_command)

        def _dual_run_move(_dt):
            _task = S.get("task") or {}
            _endpoint = _task.get("endpoint") or "franka_left"
            if _endpoint not in _runs:
                raise ValueError("unsupported GR00T endpoint: %s" % _endpoint)
            return _runs[_endpoint](_dt)

        _dual_globals[_V36_CONTEXTS_KEY] = _contexts
        _dual_globals[_V36_STARTS_KEY] = _starts
        _dual_globals[_V36_RUNS_KEY] = _runs
        _dual_globals["_dual_start"] = _dual_start
        _dual_globals["_dual_run_move"] = _dual_run_move
    else:
        _contexts = _dual_globals[_V36_CONTEXTS_KEY]
        _revisions = {
            _context.get("_IC_GROOT_EXECUTION_REVISION")
            for _context in _contexts.values()
        }
        if _revisions != {_V36_REVISION}:
            raise RuntimeError(
                "refusing dual executor reuse with revisions %s"
                % sorted(str(_value) for _value in _revisions)
            )

    if (
        not callable(_dual_globals.get("_dual_start"))
        or not callable(_dual_globals.get("_dual_run_move"))
        or not _dual_globals.get(_V36_CONTEXTS_KEY)
    ):
        raise RuntimeError("V36 dual router did not install")
    _dual_globals["start"] = _dual_globals["_dual_start"]
    _dual_globals["run_move"] = _dual_globals["_dual_run_move"]
    print(
        "GROOT_DUAL_PHYSICAL_V36_READY "
        "revision=%s arms=franka_left,franka_right "
        "right_kinematic_lock=false" % _V36_REVISION,
        flush=True,
    )
except Exception:
    print("GROOT_DUAL_PHYSICAL_V36_ERROR:\n" + traceback.format_exc(), flush=True)
    raise
