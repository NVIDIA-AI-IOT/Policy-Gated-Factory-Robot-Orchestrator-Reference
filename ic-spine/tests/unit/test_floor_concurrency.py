# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Concurrent dispatch must not corrupt the floor file or lose writes.

Reproduces the live bug: IC fired several dispatch_task calls in one turn, the
parallel `policy_gated_factory_robot_orchestrator_reference dispatch` processes raced the shared JSON file, and it
ended corrupted with a lost increment. With locking + atomic writes, N concurrent
moves all land and the file stays valid JSON.
"""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from policy_gated_factory_robot_orchestrator_reference.floor import Block, Endpoint, FloorState

_CLI = Path(sys.executable).parent / "policy_gated_factory_robot_orchestrator_reference"
_N = 8


def test_concurrent_dispatch_keeps_file_valid_and_loses_nothing(tmp_path: Path) -> None:
    state = tmp_path / "floor.json"
    FloorState(
        tables={"table_1": [Block(color="red") for _ in range(_N)]},
        racks={"red_rack": 0},
        endpoints=[Endpoint(id="amr_franka_1", kind="arm+base")],
    ).save(state)

    def one_move(_: int) -> int:
        return subprocess.run(
            [
                str(_CLI), "dispatch", "--endpoint", "amr_franka_1", "--action", "move",
                "--color", "red", "--from", "table_1", "--destination", "red_rack",
                "--state", str(state),
            ],
            capture_output=True,
        ).returncode

    with ThreadPoolExecutor(max_workers=_N) as ex:
        list(ex.map(one_move, range(_N)))

    final = json.loads(state.read_text())  # raises if the file was corrupted
    assert final["racks"]["red_rack"] == _N, f"lost writes: {final['racks']}"
    assert len(final["tables"]["table_1"]) == 0
