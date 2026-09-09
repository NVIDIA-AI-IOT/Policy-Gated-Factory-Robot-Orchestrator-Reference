# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardened shape assets and color-slot aliases for physical-friction capture.

Canonical targets are the existing red cube, a blue 50 mm cylinder, and a
matte-green 60 x 40 x 50 mm brick.  The non-cube assets are created
idempotently and audited before handles are changed.  This module only stages
objects before an episode; it never attaches an object or writes its pose
during a grasp/carry/release.

Exec via cmd.py while no task is active, before arming capture.  A scene reset
reverts the live aliases.  Exec /scripts/ic_shape_mode_off.py to restore the
original handles without resetting the scene.
"""

import numpy as np
import traceback

from pxr import Usd, UsdGeom, UsdPhysics, UsdShade

_g = globals()
_g["_IC_SHAPE_MODE_READY"] = False

try:
    from isaacsim.core.prims import SingleRigidPrim

    _shape_load_task = S.get("task") or {}
    if _shape_load_task and _shape_load_task.get("action") != "reset_scene":
        raise RuntimeError("refusing shape-mode load while a task is active")

    _GRIPPY_PATH = "/World/PhysicsMaterials/Grippy"
    _CYLINDER_PATH = "/World/ShapeCyl_blue"
    _CYLINDER_RIGHT_PATH = "/World/ShapeCyl_blue_R"
    _BRICK_PATH = "/World/ShapeBrick_green"
    _BRICK_RIGHT_PATH = "/World/ShapeBrick_green_R"
    _MATTE_GREEN_PATH = "/World/Looks/MatteGreenShape"

    def _physics_binding_targets(_prim):
        return [str(_target) for _target in _prim.GetRelationship(
            "material:binding:physics"
        ).GetTargets()]

    def _audit_shape_assets():
        _grippy = stage.GetPrimAtPath(_GRIPPY_PATH)
        if not _grippy.IsValid():
            raise RuntimeError("Grippy material prim is invalid")
        _friction = UsdPhysics.MaterialAPI(_grippy)
        _static = float(_friction.GetStaticFrictionAttr().Get())
        _dynamic = float(_friction.GetDynamicFrictionAttr().Get())
        _restitution = float(_friction.GetRestitutionAttr().Get())
        if abs(_static - 2.0) > 1e-6 or abs(_dynamic - 1.7) > 1e-6 or abs(_restitution) > 1e-6:
            raise RuntimeError(
                "noncanonical Grippy material: static=%.3f dynamic=%.3f restitution=%.3f"
                % (_static, _dynamic, _restitution)
            )

        for _arm_name in ("Franka_Left", "Franka_Right"):
            for _finger_name in ("panda_leftfinger", "panda_rightfinger"):
                _finger_path = "/Workcell/%s/%s" % (_arm_name, _finger_name)
                _finger = stage.GetPrimAtPath(_finger_path)
                if (
                    not _finger.IsValid()
                    or _GRIPPY_PATH not in _physics_binding_targets(_finger)
                ):
                    raise RuntimeError("finger is not bound to Grippy: " + _finger_path)

        _matte_prim = stage.GetPrimAtPath(_MATTE_GREEN_PATH)
        _matte_shader = UsdShade.Shader.Get(
            stage, _MATTE_GREEN_PATH + "/PreviewSurface"
        )
        if not _matte_prim.IsValid() or not _matte_shader.GetPrim().IsValid():
            raise RuntimeError("matte-green preview material is missing")
        _roughness = float(_matte_shader.GetInput("roughness").Get())
        _metallic = float(_matte_shader.GetInput("metallic").Get())
        _specular = np.asarray(
            _matte_shader.GetInput("specularColor").Get(), dtype=float
        )
        if abs(_roughness - 1.0) > 1e-6 or abs(_metallic) > 1e-6 or not np.allclose(
            _specular, np.zeros(3), atol=1e-6
        ):
            raise RuntimeError(
                "green material is not matte: roughness=%.3f metallic=%.3f specular=%s"
                % (_roughness, _metallic, _specular.tolist())
            )

        _expected = {
            "blue": (
                _CYLINDER_PATH,
                np.array([0.050, 0.050, 0.050]),
                "blue",
            ),
            "green": (
                _BRICK_PATH,
                np.array([0.060, 0.040, 0.050]),
                "green",
            ),
            "blue_right": (
                _CYLINDER_RIGHT_PATH,
                np.array([0.050, 0.050, 0.050]),
                "blue",
            ),
            "green_right": (
                _BRICK_RIGHT_PATH,
                np.array([0.060, 0.040, 0.050]),
                "green",
            ),
        }
        _records = {}
        for _record_key, (
            _path,
            _dimensions,
            _shape_color,
        ) in _expected.items():
            _prim = stage.GetPrimAtPath(_path)
            if not _prim.IsValid():
                raise RuntimeError("invalid shape prim: " + _path)
            if not _prim.HasAPI(UsdPhysics.RigidBodyAPI) or not _prim.HasAPI(UsdPhysics.CollisionAPI):
                raise RuntimeError("shape lacks rigid body/collider: " + _path)
            _kinematic = UsdPhysics.RigidBodyAPI(_prim).GetKinematicEnabledAttr().Get()
            _mass = float(UsdPhysics.MassAPI(_prim).GetMassAttr().Get())
            _binding = _physics_binding_targets(_prim)
            # Validate authored local geometry, not a world-aligned bounding
            # box.  A dynamic object can settle with a tiny rotation, which
            # legitimately changes its world AABB without changing its size.
            _scale = np.ones(3, dtype=float)
            for _op in UsdGeom.Xformable(_prim).GetOrderedXformOps():
                if _op.GetOpType() == UsdGeom.XformOp.TypeScale:
                    _scale *= np.asarray(_op.Get(), dtype=float)
            if _shape_color == "blue":
                _cylinder = UsdGeom.Cylinder(_prim)
                _radius = float(_cylinder.GetRadiusAttr().Get())
                _height = float(_cylinder.GetHeightAttr().Get())
                _axis = _cylinder.GetAxisAttr().Get()
                if _axis != UsdGeom.Tokens.z:
                    raise RuntimeError("blue cylinder axis is not Z: %s" % _axis)
                _actual_dimensions = np.array(
                    [2.0 * _radius, 2.0 * _radius, _height], dtype=float
                ) * _scale
            else:
                _size = float(UsdGeom.Cube(_prim).GetSizeAttr().Get())
                _actual_dimensions = np.full(3, _size, dtype=float) * _scale
            if (
                _kinematic
                or abs(_mass - 0.050) > 1e-6
                or _GRIPPY_PATH not in _binding
                or not np.allclose(_actual_dimensions, _dimensions, atol=1e-5)
            ):
                raise RuntimeError(
                    "shape audit failed path=%s dimensions=%s kinematic=%s mass=%.4f binding=%s"
                    % (_path, _actual_dimensions.tolist(), _kinematic, _mass, _binding)
                )
            if _shape_color == "green":
                _visual_targets = [
                    str(_target)
                    for _target in _prim.GetRelationship("material:binding").GetTargets()
                ]
                if _MATTE_GREEN_PATH not in _visual_targets:
                    raise RuntimeError(
                        "green brick lacks matte visual binding: %s" % _visual_targets
                    )
            _records[_record_key] = {
                "path": _path,
                "dimensions_m": _actual_dimensions.round(6).tolist(),
                "mass_kg": _mass,
                "kinematic": bool(_kinematic),
                "physics_material": _GRIPPY_PATH,
            }
            if _shape_color == "green":
                _records[_record_key]["visual_material"] = _MATTE_GREEN_PATH
                _records[_record_key]["roughness"] = _roughness
                _records[_record_key]["metallic"] = _metallic
        _g["_IC_SHAPE_ASSET_AUDIT"] = {
            "blue": _records["blue"],
            "green": _records["green"],
        }
        _g["_IC_SHAPE_DUAL_ASSET_AUDIT"] = {
            "blue": _records["blue_right"],
            "green": _records["green_right"],
        }
        print(
            "IC_SHAPE_A0_AUDIT primary=%s dual=%s"
            % (
                _g["_IC_SHAPE_ASSET_AUDIT"],
                _g["_IC_SHAPE_DUAL_ASSET_AUDIT"],
            ),
            flush=True,
        )

    _audit_shape_assets()

    SHAPE_BANDS = {
        "left": ((3.46, 3.55), (-7.02, -6.91)),
        "right": ((3.66, 3.76), (-7.02, -6.91)),
    }
    # Conservative three-object layout used before attempting broad spawning.
    # The middle slot is offset in Y so adjacent objects remain well separated
    # while all three stay inside the already-certified reachable region.
    SHAPE_TRIPLE_SLOTS = {
        "left": np.array([3.49, -7.005]),
        "middle": np.array([3.61, -6.915]),
        "right": np.array([3.73, -7.005]),
    }
    SHAPE_TRIPLE_LAYOUTS = [
        ("red", "blue", "green"),
        ("red", "green", "blue"),
        ("blue", "red", "green"),
        ("green", "red", "blue"),
        ("blue", "green", "red"),
        ("green", "blue", "red"),
    ]
    # The right cell is the canonical left cell translated by the measured
    # arm-base delta (4.965 - 3.640).  Keep one layout definition and apply
    # only this audited rigid translation for right-arm capture.
    SHAPE_ARM_X_OFFSET = {"franka_left": 0.0, "franka_right": 1.325}
    # color -> (shape prim path, pool index to alias, grasp xy offset, snug grip)
    SHAPE_DEFS = {
        "red":   ("/World/SortCube_R", 0, np.array([0.0, 0.0]), 0.027),      # cube: unchanged
        "blue":  (_CYLINDER_PATH, 2, np.array([0.0, 0.0]), 0.027),            # cylinder d=5cm: center grasp
        "green": (_BRICK_PATH, 4, np.array([0.0, 0.0]), 0.027),               # brick: close across 40mm width
    }
    SHAPE_DUAL_DEFS = {
        "franka_left": SHAPE_DEFS,
        "franka_right": {
            "red": (
                "/World/SortCube_R2",
                1,
                np.array([0.0, 0.0]),
                0.027,
            ),
            "blue": (
                _CYLINDER_RIGHT_PATH,
                3,
                np.array([0.0, 0.0]),
                0.027,
            ),
            "green": (
                _BRICK_RIGHT_PATH,
                5,
                np.array([0.0, 0.0]),
                0.027,
            ),
        },
    }
    SHAPE_TASK_NOUN = {"red": "cube", "blue": "cylinder", "green": "brick"}

    if "_IC_SHAPE_ORIG" not in _g:
        _g["_IC_SHAPE_ORIG"] = {
            "wr": dict(wr), "wrp": list(wrp), "GR_SNUG": GR_SNUG,
            "spawn_scene": spawn_scene, "start": start,
        }

    _shape_prims = {}
    for _col, (_path, _idx, _off, _snug) in SHAPE_DEFS.items():
        _key = "_shape_rp_" + _col
        _existing = _g.get(_key)
        if _existing is None or str(getattr(_existing, "prim_path", "")) != _path:
            _g[_key] = SingleRigidPrim(_path, name="shp_" + _col)
        _shape_prims[_col] = _g[_key]
    _shape_dual_prims = {"franka_left": dict(_shape_prims), "franka_right": {}}
    for _col, (
        _path,
        _idx,
        _off,
        _snug,
    ) in SHAPE_DUAL_DEFS["franka_right"].items():
        _key = "_shape_rp_" + _col + "_right"
        _existing = _g.get(_key)
        if (
            _existing is None
            or str(getattr(_existing, "prim_path", "")) != _path
        ):
            _g[_key] = SingleRigidPrim(
                _path,
                name="shp_" + _col + "_right",
            )
        _shape_dual_prims["franka_right"][_col] = _g[_key]

    def _shape_spawn_scene(n=None, zone="left"):
        """Stage one target in a declared band, with optional declared distractors."""
        _orig = _g["_IC_SHAPE_ORIG"]
        # The normal ROS spawn API passes only ``n`` and ``zone``.  A
        # schedule-aware recorder can request a deterministic, counterbalanced
        # shape scene without writing this command file by using
        # zone="shape:<blue|green>:<left|right>" and n as the positive seed.
        _zone_text = str(zone).lower()
        _protocol = None
        if _zone_text.startswith("shape:"):
            _parts = _zone_text.split(":")
            if len(_parts) != 3 or _parts[1] not in ("blue", "green"):
                raise ValueError("shape capture zone must be shape:<blue|green>:<left|right>")
            if _parts[2] not in SHAPE_BANDS:
                raise ValueError("shape capture band must be left or right")
            _protocol = {
                "mode": "shape_pair",
                "target": _parts[1],
                "band": _parts[2],
                "seed": int(n if n is not None else 0),
            }
        elif _zone_text.startswith("shape3:"):
            _parts = _zone_text.split(":")
            if (
                len(_parts) not in (3, 4)
                or _parts[1] not in ("red", "blue", "green")
            ):
                raise ValueError(
                    "shape3 zone must be "
                    "shape3:<red|blue|green>:<layout-0..5>[:franka_left|franka_right]"
                )
            try:
                _layout_index = int(_parts[2])
            except ValueError as _error:
                raise ValueError("shape3 layout must be an integer from 0 through 5") from _error
            if not 0 <= _layout_index < len(SHAPE_TRIPLE_LAYOUTS):
                raise ValueError("shape3 layout must be from 0 through 5")
            _capture_arm = _parts[3] if len(_parts) == 4 else "franka_left"
            if _capture_arm not in SHAPE_ARM_X_OFFSET:
                raise ValueError("shape3 arm must be franka_left or franka_right")
            _protocol = {
                "mode": "shape_triple",
                "target": _parts[1],
                "layout": _layout_index,
                "seed": int(n if n is not None else 0),
                "arm": _capture_arm,
            }
        elif _zone_text.startswith("shape6:"):
            _parts = _zone_text.split(":")
            if (
                len(_parts) not in (3, 4)
                or _parts[1] not in ("red", "blue", "green")
            ):
                raise ValueError(
                    "shape6 zone must be "
                    "shape6:<red|blue|green>:<left-layout-0..5>"
                    "[:<right-layout-0..5>]"
                )
            try:
                _left_layout_index = int(_parts[2])
                _right_layout_index = int(
                    _parts[3] if len(_parts) == 4 else _parts[2]
                )
            except ValueError as _error:
                raise ValueError(
                    "shape6 layouts must be integers from 0 through 5"
                ) from _error
            if (
                not 0 <= _left_layout_index < len(SHAPE_TRIPLE_LAYOUTS)
                or not 0 <= _right_layout_index < len(SHAPE_TRIPLE_LAYOUTS)
            ):
                raise ValueError("shape6 layouts must be from 0 through 5")
            _protocol = {
                "mode": "shape_dual_triple",
                "target": _parts[1],
                # Preserve the historical scalar field for existing readers.
                "layout": _left_layout_index,
                "layouts": {
                    "franka_left": _left_layout_index,
                    "franka_right": _right_layout_index,
                },
                "seed": int(n if n is not None else 0),
                "arm": "both",
                "arms": ["franka_left", "franka_right"],
            }
        _col = _protocol["target"] if _protocol else _g.get("_IC_SHAPE_ACTIVE", "blue")
        _g["_IC_SHAPE_ACTIVE"] = _col
        try:
            tote.set_world_pose(np.array([4.126, -7.701, 0.665]), IDENT)
            tote.set_linear_velocity(np.zeros(3)); tote.set_angular_velocity(np.zeros(3))
        except Exception:
            pass
        try:
            if tote_r is not None and not floor_state().get("tote_r_on_rack"):
                tote_r.set_world_pose(TOTE_R_POS, TOTE_R_QUAT)
                tote_r.set_linear_velocity(np.zeros(3)); tote_r.set_angular_velocity(np.zeros(3))
        except Exception:
            pass
        # park the whole cube pool off-table (original handles, not aliases)
        for _i, _rp in enumerate(_orig["wrp"]):
            _rp.set_world_pose(np.array([8.5 + 0.13 * _i, -9.8, 0.05]), IDENT)
            _rp.set_linear_velocity(np.zeros(3)); _rp.set_angular_velocity(np.zeros(3))
        # Park all four non-cube assets before explicitly staging this scene.
        if _col not in SHAPE_DEFS:
            raise ValueError("unknown active shape color: %s" % _col)
        _parks = {
            "franka_left": {
                "blue": (6.6, -6.3, 0.03),
                "green": (6.6, -6.5, 0.03),
            },
            "franka_right": {
                "blue": (6.8, -6.3, 0.03),
                "green": (6.8, -6.5, 0.03),
            },
        }
        for _park_arm, _park_colors in _parks.items():
            for _park_color, _park_xyz in _park_colors.items():
                _park_prim = _shape_dual_prims[_park_arm][_park_color]
                _park_prim.set_world_pose(np.array(_park_xyz), IDENT)
                _park_prim.set_linear_velocity(np.zeros(3))
                _park_prim.set_angular_velocity(np.zeros(3))

        if _protocol and _protocol.get("mode") == "shape_dual_triple":
            import random as _rnd

            _rng = _rnd.Random(int(_protocol["seed"]))
            _slot_names = ("left", "middle", "right")
            _positions_by_arm = {}
            _zmap = {"red": 0.75, "blue": 0.75, "green": 0.75}
            for _stage_arm in ("franka_left", "franka_right"):
                _layout = SHAPE_TRIPLE_LAYOUTS[
                    int(_protocol["layouts"][_stage_arm])
                ]
                _arm_x_offset = SHAPE_ARM_X_OFFSET[_stage_arm]
                _arm_positions = {}
                for _slot_name, _slot_color in zip(_slot_names, _layout):
                    _center = SHAPE_TRIPLE_SLOTS[_slot_name] + np.array(
                        [_arm_x_offset, 0.0],
                        dtype=float,
                    )
                    _jitter = np.array(
                        [
                            _rng.uniform(-0.006, 0.006),
                            _rng.uniform(-0.004, 0.004),
                        ],
                        dtype=float,
                    )
                    _arm_positions[_slot_color] = _center + _jitter
                _positions_by_arm[_stage_arm] = _arm_positions

            _position_values = [
                _xy
                for _arm_positions in _positions_by_arm.values()
                for _xy in _arm_positions.values()
            ]
            _minimum_separation = min(
                float(
                    np.linalg.norm(
                        _position_values[_left] - _position_values[_right]
                    )
                )
                for _left in range(len(_position_values))
                for _right in range(_left + 1, len(_position_values))
            )
            if _minimum_separation < 0.13:
                raise RuntimeError(
                    "shape6 sampled separation below 0.13 m: %.6f"
                    % _minimum_separation
                )

            for _stage_arm, _arm_positions in _positions_by_arm.items():
                for _stage_color, _stage_xy in _arm_positions.items():
                    _stage_prim = _shape_dual_prims[_stage_arm][_stage_color]
                    _stage_prim.set_world_pose(
                        np.array(
                            [
                                float(_stage_xy[0]),
                                float(_stage_xy[1]),
                                _zmap[_stage_color],
                            ]
                        ),
                        IDENT,
                    )
                    _stage_prim.set_linear_velocity(np.zeros(3))
                    _stage_prim.set_angular_velocity(np.zeros(3))

            wr.update(_orig["wr"])
            for _alias_color, _alias_prim in _shape_prims.items():
                wr[_alias_color] = _alias_prim
            for _j in range(len(wrp)):
                wrp[_j] = _orig["wrp"][_j]
            for _stage_arm, _arm_defs in SHAPE_DUAL_DEFS.items():
                for _alias_color, (
                    _path,
                    _alias_index,
                    _off,
                    _snug,
                ) in _arm_defs.items():
                    wrp[_alias_index] = _shape_dual_prims[_stage_arm][
                        _alias_color
                    ]
            ACTIVE.clear()
            ACTIVE.update(range(6))

            _g["GR_SNUG"] = SHAPE_DEFS[_col][3]
            _g["_IC_SHAPE_LAST_SCENE"] = {
                "target": _col,
                "layout": int(_protocol["layout"]),
                "layouts": dict(_protocol["layouts"]),
                "seed": int(_protocol["seed"]),
                "positions_xyz": {
                    _stage_arm: {
                        _stage_color: [
                            float(_stage_xy[0]),
                            float(_stage_xy[1]),
                            _zmap[_stage_color],
                        ]
                        for _stage_color, _stage_xy in _arm_positions.items()
                    }
                    for _stage_arm, _arm_positions in _positions_by_arm.items()
                },
                "minimum_separation_m": _minimum_separation,
                "capture_protocol": _protocol,
            }
            print(
                "IC_SHAPE6_SPAWN %s snug=%.3f"
                % (_g["_IC_SHAPE_LAST_SCENE"], _g["GR_SNUG"]),
                flush=True,
            )
            return

        if _protocol and _protocol.get("mode") == "shape_triple":
            import random as _rnd

            _rng = _rnd.Random(int(_protocol["seed"]))
            _slot_names = ("left", "middle", "right")
            _layout = SHAPE_TRIPLE_LAYOUTS[int(_protocol["layout"])]
            _arm_x_offset = SHAPE_ARM_X_OFFSET[_protocol["arm"]]
            _positions = {}
            for _slot_name, _slot_color in zip(_slot_names, _layout):
                _center = SHAPE_TRIPLE_SLOTS[_slot_name] + np.array(
                    [_arm_x_offset, 0.0], dtype=float
                )
                _jitter = np.array(
                    [_rng.uniform(-0.006, 0.006), _rng.uniform(-0.004, 0.004)],
                    dtype=float,
                )
                _positions[_slot_color] = _center + _jitter

            _position_values = list(_positions.values())
            _minimum_separation = min(
                float(np.linalg.norm(_position_values[_i] - _position_values[_j]))
                for _i in range(len(_position_values))
                for _j in range(_i + 1, len(_position_values))
            )
            if _minimum_separation < 0.13:
                raise RuntimeError(
                    "shape3 sampled separation below 0.13 m: %.6f" % _minimum_separation
                )

            _zmap = {"red": 0.75, "blue": 0.75, "green": 0.75}
            for _stage_color, _stage_xy in _positions.items():
                _stage_prim = _shape_prims[_stage_color]
                _stage_prim.set_world_pose(
                    np.array(
                        [float(_stage_xy[0]), float(_stage_xy[1]), _zmap[_stage_color]]
                    ),
                    IDENT,
                )
                _stage_prim.set_linear_velocity(np.zeros(3))
                _stage_prim.set_angular_velocity(np.zeros(3))

            # Alias every canonical color and expose all three objects to target
            # selection and floor-state reporting.
            wr.update(_orig["wr"])
            for _alias_color, _alias_prim in _shape_prims.items():
                wr[_alias_color] = _alias_prim
            for _j in range(len(wrp)):
                wrp[_j] = _orig["wrp"][_j]
            for _alias_color, (_path, _alias_index, _off, _snug) in SHAPE_DEFS.items():
                wrp[_alias_index] = _shape_prims[_alias_color]
            ACTIVE.clear()
            ACTIVE.update(SHAPE_DEFS[_stage_color][1] for _stage_color in _positions)

            _g["GR_SNUG"] = SHAPE_DEFS[_col][3]
            _g["_IC_SHAPE_LAST_SCENE"] = {
                "target": _col,
                "layout": int(_protocol["layout"]),
                "seed": int(_protocol["seed"]),
                "positions_xyz": {
                    _stage_color: [
                        float(_stage_xy[0]),
                        float(_stage_xy[1]),
                        _zmap[_stage_color],
                    ]
                    for _stage_color, _stage_xy in _positions.items()
                },
                "minimum_separation_m": _minimum_separation,
                "capture_protocol": _protocol,
            }
            print(
                "IC_SHAPE3_SPAWN %s snug=%.3f"
                % (_g["_IC_SHAPE_LAST_SCENE"], _g["GR_SNUG"]),
                flush=True,
            )
            return

        # Sample from a named, logged band.  An explicit XY is accepted for a
        # deterministic certification trial, but undeclared free-table random
        # spawning is intentionally unsupported.
        import random as _rnd
        _band = (
            _protocol["band"]
            if _protocol
            else str(_g.get("_IC_SHAPE_SPAWN_BAND", zone)).lower()
        )
        if _band not in SHAPE_BANDS:
            raise ValueError("shape spawn band must be left or right, got %s" % _band)
        _seed = int(_protocol["seed"] if _protocol else _g.get("_IC_SHAPE_SEED", 0))
        _rng = _rnd.Random(_seed)
        _explicit_xy = None if _protocol else _g.get("_IC_SHAPE_SPAWN_XY")
        if _explicit_xy is None:
            (_xlo, _xhi), (_ylo, _yhi) = SHAPE_BANDS[_band]
            _xy = np.array([_rng.uniform(_xlo, _xhi), _rng.uniform(_ylo, _yhi)])
        else:
            _xy = np.asarray(_explicit_xy, dtype=float).reshape(2)
        _zmap = {"red": 0.75, "blue": 0.75, "green": 0.75}
        _sp = np.array([float(_xy[0]), float(_xy[1]), _zmap[_col]])
        _shape_prims[_col].set_world_pose(_sp, IDENT)
        _shape_prims[_col].set_linear_velocity(np.zeros(3))
        _shape_prims[_col].set_angular_velocity(np.zeros(3))

        # Alias every canonical object consistently; ACTIVE controls which
        # staged objects are visible to targeting/floor-state logic.
        _idx = SHAPE_DEFS[_col][1]
        wr.update(_orig["wr"])
        for _alias_color, _alias_prim in _shape_prims.items():
            wr[_alias_color] = _alias_prim
        for _j in range(len(wrp)):
            wrp[_j] = _orig["wrp"][_j]
        for _alias_color, (_path, _alias_index, _off, _snug) in SHAPE_DEFS.items():
            wrp[_alias_index] = _shape_prims[_alias_color]
        ACTIVE.clear()
        ACTIVE.add(_idx)

        # Optional distractor positions must be explicit: {"red": [x, y], ...}.
        # This keeps certification scenes reproducible and prevents target side
        # from leaking the instruction.
        if _protocol:
            _other_color = "green" if _col == "blue" else "blue"
            _other_band = "right" if _band == "left" else "left"
            (_dxlo, _dxhi), (_dylo, _dyhi) = SHAPE_BANDS[_other_band]
            _dxy = None
            for _ in range(100):
                _candidate = np.array(
                    [_rng.uniform(_dxlo, _dxhi), _rng.uniform(_dylo, _dyhi)],
                    dtype=float,
                )
                if float(np.linalg.norm(_candidate - _xy)) >= 0.16:
                    _dxy = _candidate
                    break
            if _dxy is None:
                raise RuntimeError("could not sample separated counter-band distractor")
            _distractors = {_other_color: _dxy.tolist()}
        else:
            _distractors = dict(_g.get("_IC_SHAPE_DISTRACTORS") or {})
        for _dcolor, _dxy_value in _distractors.items():
            if _dcolor not in SHAPE_DEFS or _dcolor == _col:
                raise ValueError("invalid distractor color: %s" % _dcolor)
            _dxy = np.asarray(_dxy_value, dtype=float).reshape(2)
            if float(np.linalg.norm(_dxy - _xy)) < 0.16:
                raise ValueError("target/distractor separation below 0.16 m")
            _dprim = _shape_prims[_dcolor]
            _dprim.set_world_pose(
                np.array([float(_dxy[0]), float(_dxy[1]), _zmap[_dcolor]]), IDENT
            )
            _dprim.set_linear_velocity(np.zeros(3))
            _dprim.set_angular_velocity(np.zeros(3))
            ACTIVE.add(SHAPE_DEFS[_dcolor][1])
        _g["GR_SNUG"] = SHAPE_DEFS[_col][3]
        _g["_IC_SHAPE_LAST_SCENE"] = {
            "target": _col,
            "band": _band,
            "seed": _seed,
            "target_xyz": [float(_value) for _value in _sp],
            "distractors_xy": _distractors,
            "capture_protocol": _protocol,
        }
        print("IC_SHAPE_SPAWN %s snug=%.3f" % (
            _g["_IC_SHAPE_LAST_SCENE"], _g["GR_SNUG"]), flush=True)

    def _shape_start(cmd):
        _g["_IC_SHAPE_ORIG"]["start"](cmd)
        _col = _g.get("_IC_SHAPE_ACTIVE")
        if (cmd.get("action") == "move" and _col and cmd.get("color") == _col
                and S.get("pick") is not None):
            _off = SHAPE_DEFS[_col][2]
            if abs(float(_off[0])) > 1e-9 or abs(float(_off[1])) > 1e-9:
                S["pick"] = np.array(S["pick"], float)
                S["pick"][0] += float(_off[0]); S["pick"][1] += float(_off[1])
                print("IC_SHAPE_GRASP_OFF col=%s pick=%s" % (
                    _col, [round(float(v), 3) for v in S["pick"]]), flush=True)

    _g["spawn_scene"] = _shape_spawn_scene
    _g["start"] = _shape_start
    _g.setdefault("_IC_SHAPE_ACTIVE", "blue")
    _g["_IC_SHAPE_MODE_READY"] = True
    print("IC_SHAPE_MODE_ON active=%s (set _IC_SHAPE_ACTIVE to switch)" % _g["_IC_SHAPE_ACTIVE"], flush=True)
except Exception:
    _g["_IC_SHAPE_MODE_READY"] = False
    print("IC_SHAPE_MODE_ERR:\n" + traceback.format_exc(), flush=True)
    raise
