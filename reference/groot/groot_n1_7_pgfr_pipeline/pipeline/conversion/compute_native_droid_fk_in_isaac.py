#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Compute stock Franka panda_link8 FK in a separate, headless Isaac process.

CLI: /isaac-sim/python.sh this_file.py --request /data/request.json --output /data/fk.json
The legacy embedded batch caller may instead supply the two explicit globals.
No scene is opened, no ROS node is started, and no robot action is applied.
"""
import argparse
import json
from pathlib import Path


def compute(request_path, output_path):
    import numpy as np
    from isaacsim.core.utils.extensions import get_extension_path_from_name
    from isaacsim.robot_motion.motion_generation import LulaKinematicsSolver

    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite FK output: {output_path}")
    request = json.loads(Path(request_path).read_text())
    if request.get("schema_version") != 1 or request.get("frame") != "panda_link8" or not request.get("episodes"):
        raise ValueError("Expected a nonempty schema-1 panda_link8 FK request")
    extension = Path(get_extension_path_from_name("isaacsim.robot_motion.motion_generation"))
    config = extension / "motion_policy_configs/franka"
    solver = LulaKinematicsSolver(
        robot_description_path=str(config / "rmpflow/robot_descriptor.yaml"),
        urdf_path=str(config / "lula_franka_gen.urdf"),
    )

    def poses(rows):
        positions, rotations = [], []
        for row in rows:
            joints = np.asarray(row, dtype=float)
            if joints.shape != (7,) or not np.isfinite(joints).all():
                raise ValueError("FK input must be a finite seven-joint vector")
            position, rotation = solver.compute_forward_kinematics("panda_link8", joints)
            positions.append(np.asarray(position).tolist())
            rotations.append(np.asarray(rotation).tolist())
        return {"position": positions, "rotation": rotations}

    episodes = []
    for index, episode in enumerate(request["episodes"]):
        state, action = episode["state_joint_position"], episode["action_joint_position"]
        if episode.get("episode_index") != index or not state or len(state) != len(action):
            raise ValueError("FK episodes must be contiguous with matching nonempty state/action rows")
        episodes.append({"episode_index": index, "source_file": episode["source_file"],
                         "source_sha256": episode["source_sha256"],
                         "state": poses(state), "action": poses(action)})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"schema_version": 1, "frame": "panda_link8",
                                     "kinematics": "Isaac Sim LulaKinematicsSolver(Franka)",
                                     "episodes": episodes}) + "\n")
    print(f"PGFR_NATIVE_DROID_FK_DONE episodes={len(episodes)} output={output_path}", flush=True)


if "_PGFR_NATIVE_DROID_FK_REQUEST" in globals():
    compute(globals().pop("_PGFR_NATIVE_DROID_FK_REQUEST"), globals().pop("_PGFR_NATIVE_DROID_FK_OUTPUT"))
elif __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from isaacsim import SimulationApp
    simulation = SimulationApp({"headless": True})
    try:
        compute(args.request, args.output)
    finally:
        simulation.close()
