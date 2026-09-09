# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Compute stock Franka panda_link8 FK for a native-DROID request.

Run inside the already-bootstrapped Isaac Sim process after
``build_native_droid_dataset.py export``.  This keeps FK on NVIDIA's stock Lula
Franka description and does not define a joint map or kinematics model.
"""

import json
import traceback

import numpy as np
from isaacsim.robot_motion.motion_generation import LulaKinematicsSolver


_g = globals()

try:
    _request_path = _g.pop(
        "_PGFR_NATIVE_DROID_FK_REQUEST",
        "/scripts/native_droid_work/shape_pair_smoke16_fk_request.json",
    )
    _output_path = _g.pop(
        "_PGFR_NATIVE_DROID_FK_OUTPUT",
        "/scripts/native_droid_work/shape_pair_smoke16_fk_lula.json",
    )
    with open(_request_path, encoding="utf-8") as _stream:
        _request = json.load(_stream)
    if _request.get("frame") != "panda_link8":
        raise ValueError("FK request frame must be panda_link8")

    _solver = LulaKinematicsSolver(
        robot_description_path=(
            "/isaac-sim/exts/isaacsim.robot_motion.motion_generation/"
            "motion_policy_configs/franka/rmpflow/robot_descriptor.yaml"
        ),
        urdf_path=(
            "/isaac-sim/exts/isaacsim.robot_motion.motion_generation/"
            "motion_policy_configs/franka/lula_franka_gen.urdf"
        ),
    )

    def _compute(_joint_rows):
        _positions = []
        _rotations = []
        for _row in _joint_rows:
            _joints = np.asarray(_row, dtype=float)
            if _joints.shape != (7,) or not np.isfinite(_joints).all():
                raise ValueError("FK input must be a finite seven-joint vector")
            _position, _rotation = _solver.compute_forward_kinematics(
                "panda_link8", _joints
            )
            _positions.append(np.asarray(_position, dtype=float).tolist())
            _rotations.append(np.asarray(_rotation, dtype=float).tolist())
        return {"position": _positions, "rotation": _rotations}

    _episodes = []
    _frames = 0
    for _expected_index, _episode in enumerate(_request.get("episodes", [])):
        if int(_episode.get("episode_index", -1)) != _expected_index:
            raise ValueError("FK request episodes are not contiguous")
        _state_rows = _episode["state_joint_position"]
        _action_rows = _episode["action_joint_position"]
        if len(_state_rows) != len(_action_rows) or not _state_rows:
            raise ValueError("FK state/action frame count mismatch")
        _episodes.append(
            {
                "episode_index": _expected_index,
                "source_file": _episode["source_file"],
                "source_sha256": _episode["source_sha256"],
                "state": _compute(_state_rows),
                "action": _compute(_action_rows),
            }
        )
        _frames += len(_state_rows)

    _result = {
        "schema_version": 1,
        "kinematics": "Isaac Sim LulaKinematicsSolver(Franka)",
        "frame": "panda_link8",
        "episodes": _episodes,
    }
    with open(_output_path, "w", encoding="utf-8") as _stream:
        json.dump(_result, _stream)
    print(
        "PGFR_NATIVE_DROID_FK_DONE episodes=%d frames=%d output=%s"
        % (len(_episodes), _frames, _output_path),
        flush=True,
    )
except Exception:
    print("PGFR_NATIVE_DROID_FK_ERR:\n" + traceback.format_exc(), flush=True)
