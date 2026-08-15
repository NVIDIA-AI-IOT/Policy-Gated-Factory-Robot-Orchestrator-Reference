# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pluggable action-endpoint registry. Add an endpoint type by subclassing ActionEndpoint."""
from industrial_claw.action_endpoints.base import ActionEndpoint, ActionResult

__all__ = ["ActionEndpoint", "ActionResult"]
