# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""DROID modality contract matching ``nvidia/GR00T-N1.7-DROID``.

The shipped DROID checkpoint was trained with the current frame only.  The
generic N1.7 repository configuration uses two frames ([-15, 0]), so a
second-stage fine-tune from the DROID checkpoint must override that one field
to preserve the checkpoint's processor contract.
"""

from gr00t.configs.data.embodiment_configs import MODALITY_CONFIGS
from gr00t.data.embodiment_tags import EmbodimentTag
from gr00t.data.types import (
    ActionConfig,
    ActionFormat,
    ActionRepresentation,
    ActionType,
    ModalityConfig,
)


TAG = EmbodimentTag.OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT.value

MODALITY_CONFIGS[TAG] = {
    "video": ModalityConfig(
        delta_indices=[0],
        modality_keys=["exterior_image_1_left", "wrist_image_left"],
    ),
    "state": ModalityConfig(
        delta_indices=[0],
        modality_keys=["eef_9d", "gripper_position", "joint_position"],
    ),
    "action": ModalityConfig(
        delta_indices=list(range(40)),
        modality_keys=["eef_9d", "gripper_position", "joint_position"],
        action_configs=[
            ActionConfig(
                rep=ActionRepresentation.RELATIVE,
                type=ActionType.EEF,
                format=ActionFormat.XYZ_ROT6D,
                state_key="eef_9d",
            ),
            ActionConfig(
                rep=ActionRepresentation.ABSOLUTE,
                type=ActionType.NON_EEF,
                format=ActionFormat.DEFAULT,
                state_key="gripper_position",
            ),
            ActionConfig(
                rep=ActionRepresentation.RELATIVE,
                type=ActionType.NON_EEF,
                format=ActionFormat.DEFAULT,
                state_key="joint_position",
            ),
        ],
    ),
    "language": ModalityConfig(
        delta_indices=[0],
        modality_keys=["annotation.language.language_instruction"],
    ),
}
