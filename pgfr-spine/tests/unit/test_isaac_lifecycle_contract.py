# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free contracts for Isaac stage preparation and readiness."""

from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ISAAC_CELL = (
    REPOSITORY_ROOT / "reference" / "policy-gated-factory-robot-orchestrator-reference" / "isaac-cell" / "pgfr_cell"
)
BOOT = ISAAC_CELL / "boot.py"
CAMERAS = ISAAC_CELL / "cameras.py"
RUNTIME = ISAAC_CELL / "runtime.py"


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _function(module: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _method(module: ast.Module, name: str) -> ast.FunctionDef:
    runtime = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "CellRuntime"
    )
    return next(
        node
        for node in runtime.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _source(path: Path, node: ast.AST) -> str:
    value = ast.get_source_segment(path.read_text(encoding="utf-8"), node)
    assert value is not None
    return value


def _call_line(node: ast.AST, name: str) -> int:
    matches = []
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Call):
            continue
        function = candidate.func
        called = function.id if isinstance(function, ast.Name) else getattr(function, "attr", None)
        if called == name:
            matches.append(candidate.lineno)
    assert matches, f"no call to {name} found"
    return min(matches)


def test_stage_topology_is_prepared_before_world_and_tensor_views() -> None:
    runtime_module = _module(RUNTIME)
    init = _method(runtime_module, "__init__")

    assert _call_line(init, "stop") < _call_line(init, "clear_instance")
    assert _call_line(init, "clear_instance") < _call_line(init, "_build_scene")
    assert _call_line(init, "_build_scene") < _call_line(init, "pre_physics_prepare")
    assert _call_line(init, "pre_physics_prepare") < _call_line(init, "_build_world")

    boot_module = _module(BOOT)
    bring_up = _function(boot_module, "bring_up")
    prepare = _function(boot_module, "prepare_stage")
    ordered_calls = (
        "prepare_robot_camera_geometry",
        "build_gr00t_cams",
        "add_tote_pads",
        "matte_scene",
        "build_floor_cams",
        "validate_prepared_camera_stage",
    )
    lines = [_call_line(prepare, name) for name in ordered_calls]
    assert lines == sorted(lines)

    bring_up_source = _source(BOOT, bring_up)
    assert "ident.endswith" not in bring_up_source
    assert "requested_identifier = _normalize_stage_identifier(path)" in bring_up_source
    assert "_normalize_stage_identifier(root.identifier) == requested_identifier" in bring_up_source
    assert "if not ctx.open_stage(path):" in bring_up_source
    assert 'raise RuntimeError("failed to open Isaac stage:' in bring_up_source
    assert 'raise RuntimeError("Isaac stage context has no current stage")' in bring_up_source
    assert 'raise RuntimeError("Isaac stage has no root layer")' in bring_up_source
    assert "if actual_identifier != requested_identifier:" in bring_up_source
    assert 'raise RuntimeError("Isaac stage is missing required /World prim")' in bring_up_source
    assert "CellRuntime(pre_physics_prepare=prepare_stage)" in bring_up_source
    assert bring_up_source.index("rt.run()") < bring_up_source.index("rt.request_reset()")
    assert "PGFR_CELL_UP" not in bring_up_source

    camera_source = CAMERAS.read_text(encoding="utf-8")
    assert "omni.timeline" not in camera_source
    assert ".play()" not in camera_source
    assert "from isaacsim.core.simulation_manager import SimulationManager" in camera_source

    build_all = _source(CAMERAS, _function(_module(CAMERAS), "build_all"))
    safe_calls = (
        "SimulationManager.get_physics_sim_view()",
        "prepare_robot_camera_geometry(stage)",
        "build_gr00t_cams()",
        "build_floor_cams()",
        "validate_prepared_camera_stage(stage)",
    )
    offsets = [build_all.index(call) for call in safe_calls]
    assert offsets == sorted(offsets)
    assert "is not None" in build_all
    assert "camera topology cannot be changed after physics initialization" in build_all


def test_camera_preparation_is_idempotent_and_has_unique_viewports() -> None:
    camera_module = _module(CAMERAS)
    prepare = _function(camera_module, "prepare_robot_camera_geometry")
    build = _function(camera_module, "build_gr00t_cams")
    validate = _function(camera_module, "validate_prepared_camera_stage")

    prepare_source = _source(CAMERAS, prepare)
    assert "prim.IsInstanceable()" in prepare_source
    assert "prim.SetInstanceable(False)" in prepare_source

    build_source = _source(CAMERAS, build)
    assert "_require_prepared_robot_camera_geometry(stage)" in build_source
    assert "SetInstanceable" not in build_source

    validate_source = _source(CAMERAS, validate)
    assert "required = _ROBOT_CAMERA_GEOMETRY +" in validate_source
    assert "prepared camera stage is missing prims" in validate_source

    viewport_ids = {}
    for call in ast.walk(camera_module):
        if not isinstance(call, ast.Call):
            continue
        function = call.func
        called = function.id if isinstance(function, ast.Name) else getattr(function, "attr", None)
        if called != "_build_graph" or len(call.args) < 5:
            continue
        graph_path = ast.literal_eval(call.args[1])
        viewport_ids[graph_path] = ast.literal_eval(call.args[4])

    assert viewport_ids == {
        "/ROS_WristCam": 1,
        "/ROS_OutsideCam": 2,
        "/ROS_TableCam": 3,
        "/ROS_RackCam": 4,
        "/ROS_InspectCam": 5,
    }


def test_physics_wrappers_are_initialized_by_the_single_world_reset() -> None:
    runtime_module = _module(RUNTIME)
    build_world = _method(runtime_module, "_build_world")
    build_source = _source(RUNTIME, build_world)
    reset_line = _call_line(build_world, "reset")

    rigid_constructor_lines = [
        node.lineno
        for node in ast.walk(build_world)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "SingleRigidPrim"
    ]
    assert rigid_constructor_lines
    assert max(rigid_constructor_lines) < reset_line
    assert build_source.count("self.world.reset()") == 1
    assert build_source.index("self.world.scene.add(wrapper)") < build_source.index(
        "self.world.reset()"
    )
    assert "wrappers_by_path[path]" in build_source
    assert 'name="w_"' not in build_source

    validate = _method(runtime_module, "_validate_runtime_ready")
    validate_source = _source(RUNTIME, validate)
    for check in (
        "get_world_pose",
        "get_linear_velocity",
        "get_angular_velocity",
        "get_joint_positions",
        "np.isfinite",
    ):
        assert check in validate_source
    assert "articulation.handles_initialized" in validate_source
    assert "wrapper._rigid_prim_view.is_physics_handle_valid()" in validate_source
    assert 'getattr(wrapper, "is_physics_handle_valid"' not in validate_source


def test_ready_requires_reset_two_clean_ticks_and_no_startup_error() -> None:
    runtime_module = _module(RUNTIME)
    runtime_source = RUNTIME.read_text(encoding="utf-8")
    boot_source = BOOT.read_text(encoding="utf-8")
    step = _method(runtime_module, "_step")
    step_source = _source(RUNTIME, step)

    assert "PGFR_CELL_UP" not in boot_source
    assert runtime_source.count('print("PGFR_CELL_UP markers=all"') == 1
    assert step_source.index("self.reset_scene()") < step_source.index(
        "self._boot_reset_complete = True"
    )
    assert step_source.index("self._validate_runtime_ready()") < step_source.index(
        'print("PGFR_CELL_UP markers=all"'
    )
    assert "self._startup_clean_ticks >= 2" in step_source
    assert "if self._boot_ready:" in step_source
    assert "self._latch_startup_failure()" in step_source

    latch = _source(RUNTIME, _method(runtime_module, "_latch_startup_failure"))
    assert "if self._startup_failed:" in latch
    assert 'print("PGFR_CELL_BOOT_ERR:' in latch
    assert "self._sub.unsubscribe()" in latch
    assert "get_timeline_interface().stop()" in latch

    run = _source(RUNTIME, _method(runtime_module, "run"))
    assert run.index("subscribe_physics_step_events") < run.index(
        "get_timeline_interface().play()"
    )
    shutdown = _source(RUNTIME, _method(runtime_module, "shutdown"))
    assert "get_timeline_interface().stop()" in shutdown
