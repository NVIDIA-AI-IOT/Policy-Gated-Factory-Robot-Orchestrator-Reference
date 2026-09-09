# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""VLM client interface and implementations."""
from __future__ import annotations

import os

from policy_gated_factory_robot_orchestrator_reference.clients.vlm.base import (
    VLMClient,
    VLMResponse,
)

__all__ = ["VLMClient", "VLMResponse", "vlm_from_env"]


def vlm_from_env() -> VLMClient | None:
    """Build a VLM client from the ``IC_VLM_*`` env, or None if unconfigured.

    None means "no live VLM wired" — callers fall back to floor-state ground truth.
    ``IC_VLM_URL`` points at an OpenAI-compatible vision endpoint (Cosmos Reason served
    via NIM/vLLM, or any stand-in); ``IC_VLM_MODEL`` and ``IC_VLM_KEY`` are optional.
    """
    url = os.environ.get("IC_VLM_URL")
    if not url:
        return None
    from policy_gated_factory_robot_orchestrator_reference.clients.vlm.cosmos_client import (
        CosmosVLMClient,
    )

    return CosmosVLMClient(
        url=url,
        model=os.environ.get("IC_VLM_MODEL", "cosmos-reason"),
        api_key=os.environ.get("IC_VLM_KEY") or os.environ.get("IC_VLM_API_KEY"),
    )
