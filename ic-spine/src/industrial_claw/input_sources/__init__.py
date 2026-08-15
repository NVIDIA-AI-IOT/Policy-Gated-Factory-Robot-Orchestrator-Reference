# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pluggable input-source registry. Add a modality by subclassing InputSource."""
from industrial_claw.input_sources.base import InputSource

__all__ = ["InputSource"]
