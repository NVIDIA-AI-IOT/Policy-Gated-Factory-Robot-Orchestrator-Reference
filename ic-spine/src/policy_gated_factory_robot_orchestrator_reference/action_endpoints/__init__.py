# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pluggable action-endpoint registry. Add an endpoint type by subclassing ActionEndpoint."""
from policy_gated_factory_robot_orchestrator_reference.action_endpoints.base import (
    ActionEndpoint,
    ActionResult,
)

__all__ = ["ActionEndpoint", "ActionResult"]
