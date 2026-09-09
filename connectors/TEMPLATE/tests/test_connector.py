# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Template tests — the SDK compliance bar plus your domain specifics."""
from pgfr_connector_sdk import assert_connector_compliant

from my_connector.connector import MyConnector


def test_sdk_compliance():
    assert_connector_compliant(MyConnector())


def test_results_carry_provenance():
    out = MyConnector().call("query_events", {"query": "probe"})
    assert out["source"] and out["ts"], "results are evidence — they need provenance"
