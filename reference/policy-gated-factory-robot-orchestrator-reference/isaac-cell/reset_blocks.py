# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# reset_blocks.py — surgical reset: put the 3 sort cubes back on the conveyor and the
# tote back on the table, reusing ic_node_v2's live prim wrappers. Does NOT touch the
# step callback (_IC_SUB) or the rclpy command node, so /ic/command keeps working.
import numpy as np
IDENT = np.array([1.0, 0, 0, 0])
START = {"red": 3.50, "blue": 3.72, "green": 3.94}
for col, x in START.items():
    wr[col].set_world_pose(np.array([x, -6.95, 0.74]), IDENT)
    wr[col].set_linear_velocity(np.zeros(3)); wr[col].set_angular_velocity(np.zeros(3))
tote.set_world_pose(np.array([4.126, -7.701, 0.665]), IDENT)
tote.set_linear_velocity(np.zeros(3)); tote.set_angular_velocity(np.zeros(3))
print("IC_RESET_BLOCKS done", flush=True)
