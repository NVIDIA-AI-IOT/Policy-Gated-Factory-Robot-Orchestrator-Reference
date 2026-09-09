# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the persistent mock floor that backs the granular floor tools.

The floor file is the single source of truth IC's primitives share across the
stateless CLI invocations: ``dispatch`` mutates it, ``perceive`` / ``floor_state``
read it. ``dispatch`` composes the real ActionAgent over a FloorActionEndpoint,
so the same contract swaps onto ROS 2 / Isaac later.
"""
from __future__ import annotations

from pathlib import Path

from policy_gated_factory_robot_orchestrator_reference.floor import (
    Endpoint,
    FloorState,
    dispatch,
    floor_state,
    perceive,
)


def test_seed_default_matches_the_demo_scene() -> None:
    st = FloorState.seed_default()
    obs = perceive(st, "table_1")
    assert obs["counts"] == {"red": 2, "green": 1}
    assert obs["racks"] == {"red_rack": 0, "green_rack": 0}
    assert obs["sorted"] is False


def test_floor_state_lists_the_three_endpoints() -> None:
    st = FloorState.seed_default()
    fs = floor_state(st)
    assert {e["id"] for e in fs["endpoints"]} == {"amr_franka_1", "amr_franka_2", "conveyor_1"}
    amr = next(e for e in fs["endpoints"] if e["id"] == "amr_franka_1")
    assert amr["kind"] == "arm+base"
    assert amr["battery"] == 0.92


def test_save_load_round_trips_through_json(tmp_path: Path) -> None:
    st = FloorState.seed_default()
    path = tmp_path / "floor_state.json"
    st.save(path)
    reloaded = FloorState.load(path)
    assert perceive(reloaded, "table_1")["counts"] == {"red": 2, "green": 1}


def test_load_or_seed_seeds_then_persists(tmp_path: Path) -> None:
    path = tmp_path / "floor_state.json"
    assert not path.exists()
    st = FloorState.load_or_seed(path)
    assert path.exists()
    assert perceive(st, "table_1")["counts"]["red"] == 2


async def test_dispatch_move_mutates_table_and_rack() -> None:
    st = FloorState.seed_default()
    res = await dispatch(
        st, endpoint="amr_franka_1", action="move", color="red", source="table_1",
        destination="red_rack",
    )
    assert res["dispatched"] is True
    assert res["moved"] == {"color": "red", "from": "table_1", "destination": "red_rack"}
    obs = perceive(st, "table_1")
    assert obs["counts"]["red"] == 1
    assert obs["racks"]["red_rack"] == 1


async def test_dispatch_unknown_endpoint_is_rejected_by_the_action_agent() -> None:
    st = FloorState.seed_default()
    res = await dispatch(
        st, endpoint="nope", action="move", color="red", source="table_1", destination="red_rack",
    )
    assert res["dispatched"] is False
    assert "unknown endpoint" in res["reason"]


async def test_dispatch_missing_block_does_not_mutate() -> None:
    st = FloorState.seed_default()
    res = await dispatch(
        st, endpoint="amr_franka_1", action="move", color="blue", source="table_1",
        destination="blue_rack",
    )
    assert res["dispatched"] is False
    assert "no blue block" in res["reason"]
    assert perceive(st, "table_1")["counts"] == {"red": 2, "green": 1}


def test_from_scene_carries_faulty() -> None:
    from policy_gated_factory_robot_orchestrator_reference.floor.scene import Scene, SceneEndpoint

    st = FloorState.from_scene(
        Scene(
            tables={"table_1": ["red"]},
            racks={"red_rack": 0},
            endpoints=[SceneEndpoint(id="bad_arm", kind="arm+base", faulty=True)],
        )
    )
    assert st.endpoints[0].faulty is True


def test_load_or_seed_seeds_faulty_from_scene(tmp_path: Path) -> None:
    from policy_gated_factory_robot_orchestrator_reference.floor.scene import Scene, SceneEndpoint

    path = tmp_path / "f.json"
    scene = Scene(
        tables={"table_1": ["red"]},
        racks={"red_rack": 0},
        endpoints=[SceneEndpoint(id="bad_arm", kind="arm+base", faulty=True)],
    )
    # File absent → seed from the scene (so faulty survives the per-session reset).
    st = FloorState.load_or_seed(path, scene)
    assert any(e.faulty for e in st.endpoints)


def test_floor_state_hides_the_faulty_flag() -> None:
    # faulty is an internal fault-injection; a real fault is discovered by acting,
    # not advertised — so floor_state must not expose it.
    st = FloorState.seed_default()
    st.endpoints[0].faulty = True
    fs = floor_state(st)
    assert "faulty" not in fs["endpoints"][0]


def test_perceive_unknown_target_returns_empty_observation() -> None:
    st = FloorState.seed_default()
    obs = perceive(st, "table_99")
    assert obs["blocks_on_table"] == []
    assert "note" in obs


async def test_dispatch_confirms_the_effect_via_perception() -> None:
    st = FloorState.seed_default()
    res = await dispatch(
        st, endpoint="amr_franka_1", action="move", color="red", source="table_1",
        destination="red_rack",
    )
    assert res["dispatched"] is True
    assert res["verified"] is True
    assert "red_rack" in res["verification"]


async def test_dispatch_reports_unverified_when_the_effect_does_not_happen() -> None:
    # A faulty endpoint accepts the command but the block never lands (dropped grasp).
    st = FloorState.seed_default()
    st.endpoints.append(Endpoint(id="flaky_arm", kind="arm+base", faulty=True))
    res = await dispatch(
        st, endpoint="flaky_arm", action="move", color="red", source="table_1",
        destination="red_rack",
    )
    assert res["dispatched"] is True
    assert res["verified"] is False
    # The floor is unchanged — the red block is still on the table, rack still empty.
    assert perceive(st, "table_1")["counts"]["red"] == 2
    assert perceive(st, "table_1")["racks"]["red_rack"] == 0
