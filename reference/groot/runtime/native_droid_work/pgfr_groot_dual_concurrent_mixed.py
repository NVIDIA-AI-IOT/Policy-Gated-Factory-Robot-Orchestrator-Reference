# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run one atomic mixed-color GR00T move across both Franka arms.

Isaac APIs remain on the physics thread.  Only policy socket I/O uses two
workers, one independent B=1 request per arm.  Each response is checked against
its arm and inference seed before either returned action chunk is applied.
"""

from concurrent.futures import ThreadPoolExecutor as _ConcurrentThreadPool
import json as _concurrent_json
import os as _concurrent_os
import traceback as _concurrent_traceback


_CONCURRENT_DEFAULT_POLICY_CONTRACT_PATH = (
    "/scripts/groot_shared_concurrent_policy_contract.json"
)
_CONCURRENT_POLICY_CONTRACT_PATH = globals().get(
    "_PGFR_GROOT_CONCURRENT_POLICY_CONTRACT_PATH",
    _CONCURRENT_DEFAULT_POLICY_CONTRACT_PATH,
)
if not _concurrent_os.path.isabs(_CONCURRENT_POLICY_CONTRACT_PATH):
    raise RuntimeError(
        "concurrent policy contract path must be absolute: %s"
        % _CONCURRENT_POLICY_CONTRACT_PATH
    )
_CONCURRENT_POLICY_MODE = "independent-b1-per-arm-v1"
_CONCURRENT_RELAY_CONTRACT = "explicit_pair_v1_single_frame_[0]"
_CONCURRENT_ENDPOINTS = ("franka_left", "franka_right")
_CONCURRENT_LEFT_BLUE_ALIGNMENT_RADIUS = 0.080
_CONCURRENT_CONTEXT_CONFIG_KEYS = (
    "_GROOT_RELAY_HOST",
    "_GROOT_RELAY_PORT",
    "_GEXEC_OVERRIDE",
    "_GEXEC",
    "_GHOLD",
    "_GROOT_NATIVE_CONTROL_HZ",
    "_GROOT_PHYSICS_HZ",
    "_GN_LIMIT",
    "_GROOT_SETTLE_FRAMES",
    "_GROOT_MAX_TARGET_STATE_ERROR",
    "_PGFR_GRASP_TH",
    "_PGFR_REL_TH",
    "_PGFR_LOCK_R",
    "ACTIVE",
    "wrp",
    "POOL_COL",
)


def _concurrent_state(_tick):
    return {
        "task": None,
        "t": 0,
        "ph": None,
        "locked": False,
        "rel": False,
        "off": None,
        "n": int(_tick),
    }


try:
    _concurrent_g = globals()
    _concurrent_install_task = S.get("task") or {}
    if (
        _concurrent_install_task
        and _concurrent_install_task.get("action") != "reset_scene"
    ):
        raise RuntimeError(
            "refusing concurrent GR00T install during an active task"
        )
    if not _concurrent_g.get("_PGFR_GROOT_DEPLOYMENT_READY", False):
        raise RuntimeError(
            "concurrent GR00T requires the certified deployment adapter"
        )
    _concurrent_prepare = _concurrent_g.get("_PGFR_GROOT_CERTIFIED_PREPARE")
    if not callable(_concurrent_prepare):
        raise RuntimeError("certified GR00T preparation hook is missing")
    _concurrent_executor_contract = dict(
        _concurrent_g.get("_PGFR_GROOT_DEPLOYMENT_EXECUTOR_CONTRACT") or {}
    )
    if set(_concurrent_executor_contract) != {
        "revision",
        "runtime_revision",
        "path",
        "contexts_key",
    }:
        raise RuntimeError(
            "deployment executor contract is missing or malformed"
        )
    _concurrent_executor_path = str(
        _concurrent_executor_contract["path"]
    )
    _concurrent_runtime_revision = str(
        _concurrent_executor_contract["runtime_revision"]
    )
    _concurrent_contexts_key = str(
        _concurrent_executor_contract["contexts_key"]
    )
    _concurrent_base_contexts = (
        _concurrent_g.get(_concurrent_contexts_key) or {}
    )
    if set(_concurrent_base_contexts) != set(_CONCURRENT_ENDPOINTS):
        raise RuntimeError(
            "%s arm contexts are missing"
            % _concurrent_executor_contract["revision"]
        )

    with open(
        _concurrent_executor_path, encoding="utf-8"
    ) as _concurrent_source_stream:
        _concurrent_source = _concurrent_source_stream.read()
    compile(_concurrent_source, _concurrent_executor_path, "exec")

    _concurrent_shared_contract = dict(
        _concurrent_g.get("_PGFR_GROOT_SHARED_POLICY_CONTRACT") or {}
    )
    if not _concurrent_os.path.isfile(_CONCURRENT_POLICY_CONTRACT_PATH):
        raise RuntimeError(
            "missing independent B=1 policy contract: %s"
            % _CONCURRENT_POLICY_CONTRACT_PATH
        )
    with open(
        _CONCURRENT_POLICY_CONTRACT_PATH, encoding="utf-8"
    ) as _concurrent_contract_stream:
        _concurrent_policy_contract = _concurrent_json.load(
            _concurrent_contract_stream
        )
    if (
        not isinstance(_concurrent_policy_contract, dict)
        or set(_concurrent_policy_contract)
        != {
            "schema_version",
            "mode",
            "model_label",
            "checkpoint",
            "checkpoint_fingerprint",
            "relays",
        }
        or _concurrent_policy_contract.get("schema_version") != 1
        or _concurrent_policy_contract.get("mode") != _CONCURRENT_POLICY_MODE
        or _concurrent_policy_contract.get("model_label")
        != _concurrent_shared_contract.get("model_label")
        or _concurrent_policy_contract.get("checkpoint")
        != _concurrent_shared_contract.get("checkpoint")
        or _concurrent_policy_contract.get("checkpoint_fingerprint")
        != _concurrent_shared_contract.get("checkpoint_fingerprint")
    ):
        raise RuntimeError(
            "independent B=1 contract does not match the active shared model"
        )
    _concurrent_relays = _concurrent_policy_contract.get("relays")
    if not isinstance(_concurrent_relays, dict) or set(
        _concurrent_relays
    ) != set(_CONCURRENT_ENDPOINTS):
        raise RuntimeError("independent B=1 contract must name both Frankas")
    _concurrent_relay_ports = {}
    _concurrent_server_ports = set()
    for _concurrent_endpoint in _CONCURRENT_ENDPOINTS:
        _relay = _concurrent_relays[_concurrent_endpoint]
        if not isinstance(_relay, dict) or set(_relay) != {
            "relay_host",
            "relay_port",
            "server_host",
            "server_port",
            "relay_contract",
            "service_state_path",
        }:
            raise RuntimeError(
                "invalid independent relay contract for %s"
                % _concurrent_endpoint
            )
        _state_path = str(_relay.get("service_state_path") or "")
        if (
            _relay.get("relay_host") != "127.0.0.1"
            or _relay.get("server_host") != "127.0.0.1"
            or not isinstance(_relay.get("relay_port"), int)
            or not 1024 <= int(_relay["relay_port"]) <= 65535
            or not isinstance(_relay.get("server_port"), int)
            or not 1024 <= int(_relay["server_port"]) <= 65535
            or _relay.get("relay_contract") != _CONCURRENT_RELAY_CONTRACT
            or not _concurrent_os.path.isabs(_state_path)
            or not _concurrent_os.path.isfile(_state_path)
        ):
            raise RuntimeError(
                "invalid independent relay endpoint for %s"
                % _concurrent_endpoint
            )
        with open(_state_path, encoding="utf-8") as _state_stream:
            _state = _concurrent_json.load(_state_stream)
        _expected_state = {
            "schema_version": 1,
            "status": "ready",
            "model_label": _concurrent_policy_contract["model_label"],
            "checkpoint": _concurrent_policy_contract["checkpoint"],
            "checkpoint_fingerprint": _concurrent_policy_contract[
                "checkpoint_fingerprint"
            ],
            "server_host": "127.0.0.1",
            "server_port": int(_relay["server_port"]),
            "relay_host": "127.0.0.1",
            "relay_port": int(_relay["relay_port"]),
            "relay_contract": _CONCURRENT_RELAY_CONTRACT,
            "preserve_until_explicit_stop": True,
        }
        _actual_state = {
            _key: _state.get(_key) for _key in _expected_state
        }
        if _actual_state != _expected_state:
            raise RuntimeError(
                "independent B=1 service identity mismatch arm=%s "
                "expected=%s actual=%s"
                % (_concurrent_endpoint, _expected_state, _actual_state)
            )
        _concurrent_relay_ports[_concurrent_endpoint] = int(
            _relay["relay_port"]
        )
        _concurrent_server_ports.add(int(_relay["server_port"]))
    if (
        len(set(_concurrent_relay_ports.values())) != 2
        or len(_concurrent_server_ports) != 2
    ):
        raise RuntimeError(
            "independent B=1 concurrency requires two distinct server/relay pairs"
        )

    def _concurrent_select_query_mode(_active_endpoints, _ready_endpoints):
        _active = set(_active_endpoints)
        _ready = set(_ready_endpoints)
        _known = set(_CONCURRENT_ENDPOINTS)
        if not _active <= _known or not _ready <= _active:
            raise ValueError("query scheduler received invalid endpoint sets")
        if _active == _known and len(_ready) == 1:
            _waiting = next(iter(_ready))
            _peer = next(
                _endpoint
                for _endpoint in _CONCURRENT_ENDPOINTS
                if _endpoint != _waiting
            )
            return "advance_peer", _peer
        if _active == _known and _ready == _known:
            return "independent_b1", None
        if len(_active) == 1 and _ready == _active:
            return "terminal_b1", None
        return "advance", None

    _concurrent_serial_start = _concurrent_g["start"]
    _concurrent_serial_run_move = _concurrent_g["run_move"]
    _concurrent_base_finish = _concurrent_g.get("_PGFR_BASE_FINISH")
    if not callable(_concurrent_base_finish):
        raise RuntimeError("canonical cell result finalizer is missing")

    for _concurrent_old_context in (
        _concurrent_g.get("_PGFR_GROOT_CONCURRENT_CONTEXTS") or {}
    ).values():
        _concurrent_old_socket = _concurrent_old_context.get("_GRSOCK")
        if _concurrent_old_socket is not None:
            try:
                _concurrent_old_socket.close()
            except Exception:
                pass

    _concurrent_old_pool = _concurrent_g.get("_PGFR_GROOT_QUERY_POOL")
    if _concurrent_old_pool is not None:
        # The active-task guard above proves no rollout owns these workers.
        _concurrent_old_pool.shutdown(wait=True, cancel_futures=False)
    _concurrent_pool = _ConcurrentThreadPool(
        max_workers=2,
        thread_name_prefix="pgfr-groot-independent-query",
    )
    _concurrent_g["_PGFR_GROOT_QUERY_POOL"] = _concurrent_pool
    _concurrent_group = {
        "active": False,
        "results": {},
        "ran": set(),
        "inside_peer": False,
        "dt": 0.0,
        "query_round": 0,
        "pending_observations": {},
        "pending_results": {},
        "sync_wait_key": None,
    }
    _concurrent_contexts = {}
    _concurrent_runs = {}

    def _concurrent_finish_factory(_endpoint, _context):
        def _finish(_success, _verified, _reason):
            _state = _context["S"]
            _task = _state.get("task")
            if _task is None:
                return
            _stats = dict(
                _context.get("_PGFR_GROOT_BATCH_STATS")
                or {
                    "batch_1": 0,
                    "batch_2": 0,
                    "independent_b1": 0,
                    "terminal_b1": 0,
                }
            )
            _result = {
                "endpoint": _endpoint,
                "action": "move",
                "success": bool(_success),
                "verified": bool(_verified),
                "reason": str(_reason),
                "color": _task.get("color"),
                "model_label": _task.get("model_label"),
                "policy_routing": (
                    (_task.get("pgfr_groot_deployment") or {}).get(
                        "policy_routing"
                    )
                ),
                "batch_stats": _stats,
            }
            _state["task"] = None
            _state["t"] = 0
            _concurrent_group["results"][_endpoint] = _result
            print(
                "PGFR_GROOT_PAIR_CHILD_RESULT "
                + _concurrent_json.dumps(_result, sort_keys=True),
                flush=True,
            )
            if set(_concurrent_group["results"]) != set(
                _CONCURRENT_ENDPOINTS
            ):
                return

            _group_task = S.get("task") or {}
            if _group_task.get("action") != "move_pair":
                raise RuntimeError(
                    "concurrent child completion lost move_pair ownership"
                )
            _ordered = {
                _arm: _concurrent_group["results"][_arm]
                for _arm in _CONCURRENT_ENDPOINTS
            }
            _independent_b1_only = all(
                int(_ordered[_arm]["batch_stats"].get("independent_b1", 0))
                == int(_ordered[_arm]["batch_stats"].get("batch_1", 0))
                and int(_ordered[_arm]["batch_stats"].get("batch_1", 0)) > 0
                and int(_ordered[_arm]["batch_stats"].get("batch_2", 0)) == 0
                for _arm in _CONCURRENT_ENDPOINTS
            )
            _success_all = all(
                _ordered[_arm]["success"] for _arm in _CONCURRENT_ENDPOINTS
            )
            _verified_all = all(
                _ordered[_arm]["verified"] for _arm in _CONCURRENT_ENDPOINTS
            )
            _group_task["parallel_results"] = _ordered
            _group_task["independent_b1_verified"] = _independent_b1_only
            _group_task["per_arm_relay_ports"] = dict(
                _concurrent_relay_ports
            )
            _concurrent_group["active"] = False
            _concurrent_group["pending_observations"] = {}
            _concurrent_group["pending_results"] = {}
            _concurrent_group["sync_wait_key"] = None
            _summary = (
                "parallel GR00T %s; left=%s; right=%s; independent_b1=%s"
                % (
                    str(_group_task.get("color")),
                    _ordered["franka_left"]["reason"],
                    _ordered["franka_right"]["reason"],
                    _independent_b1_only,
                )
            )
            _concurrent_base_finish(
                _success_all and _independent_b1_only,
                _verified_all and _independent_b1_only,
                _summary,
            )

        return _finish

    def _concurrent_right_comp_world(_color, _unused_tote=None):
        return _concurrent_g["comp_world"](
            _color,
            _concurrent_g.get("tp_r"),
        )

    for _concurrent_endpoint in _CONCURRENT_ENDPOINTS:
        _concurrent_base = _concurrent_base_contexts[_concurrent_endpoint]
        _concurrent_context = dict(_concurrent_base)
        _concurrent_context.update(
            {
                "__name__": "_pgfr_groot_concurrent_%s"
                % _concurrent_endpoint,
                "S": _concurrent_state(S.get("n", 0)),
                "_GRSOCK": None,
                "_GRWSUB": object(),
                "_GROSUB": object(),
                "_GROOT_CLIENT_ID": _concurrent_endpoint,
                "_PGFR_GROOT_BATCH_STATS": {
                    "batch_1": 0,
                    "batch_2": 0,
                    "independent_b1": 0,
                    "terminal_b1": 0,
                },
            }
        )
        if _concurrent_endpoint == "franka_left":
            _concurrent_context.update(
                {
                    "frL": _concurrent_g["frL"],
                    "fhand": _concurrent_g["fhand"],
                    "ctrl": _concurrent_g["ctrl"],
                    "_GRF": _concurrent_base_contexts[
                        "franka_left"
                    ].get("_GRF"),
                    "comp_world": _concurrent_g["comp_world"],
                }
            )
        else:
            _concurrent_context.update(
                {
                    "frL": _concurrent_g["frR"],
                    "fhand": _concurrent_g["fhandR"],
                    "ctrl": _concurrent_g["ctrlR"],
                    "_GRF": _concurrent_base_contexts[
                        "franka_right"
                    ].get("_GRF"),
                    "comp_world": _concurrent_right_comp_world,
                }
            )
        _concurrent_context["finish"] = _concurrent_finish_factory(
            _concurrent_endpoint,
            _concurrent_context,
        )
        exec(
            compile(
                _concurrent_source,
                _concurrent_executor_path,
                "exec",
            ),
            _concurrent_context,
        )
        if (
            _concurrent_context.get("_PGFR_GROOT_EXECUTION_REVISION")
            != _concurrent_runtime_revision
            or not callable(_concurrent_context.get("start"))
            or not callable(_concurrent_context.get("run_move"))
            or not callable(_concurrent_context.get("_grquery"))
        ):
            raise RuntimeError(
                "private %s context failed for %s"
                % (
                    _concurrent_executor_contract["revision"],
                    _concurrent_endpoint,
                )
            )
        _concurrent_contexts[_concurrent_endpoint] = _concurrent_context
        _concurrent_runs[_concurrent_endpoint] = _concurrent_context[
            "run_move"
        ]

    _concurrent_install_serial_transport = _concurrent_g.get(
        "_deploy_install_shared_serial_transport"
    )
    if not callable(_concurrent_install_serial_transport):
        raise RuntimeError("shared B=1 transport installer is missing")
    for _concurrent_endpoint, _concurrent_context in (
        _concurrent_contexts.items()
    ):
        _concurrent_context["_GROOT_RELAY_HOST"] = "127.0.0.1"
        _concurrent_context["_GROOT_RELAY_PORT"] = (
            _concurrent_relay_ports[_concurrent_endpoint]
        )
    _concurrent_install_serial_transport(_concurrent_contexts)

    def _concurrent_query_factory(_endpoint, _context):
        _blocking_query = _context["_grquery"]
        _context["_PGFR_GROOT_BLOCKING_QUERY"] = _blocking_query

        def _record_b1(_arm, _result, _terminal=False):
            _metadata = dict((_result or {}).get("_batch") or {})
            if (
                _metadata.get("client_id") != _arm
                or _metadata.get("batch_size") != 1
                or _metadata.get("protocol") != "timed_batch_v1"
            ):
                raise RuntimeError(
                    "independent B=1 response identity mismatch arm=%s "
                    "metadata=%s" % (_arm, _metadata)
                )
            _arm_context = _concurrent_contexts[_arm]
            _stats = _arm_context["_PGFR_GROOT_BATCH_STATS"]
            _stats["batch_1"] += 1
            _stats["independent_b1"] += 1
            if _terminal:
                _stats["terminal_b1"] += 1
            _arm_context["_PGFR_GROOT_LAST_BATCH"] = _metadata
            return _metadata

        def _independent_query(_observation):
            _peer = (
                "franka_right"
                if _endpoint == "franka_left"
                else "franka_left"
            )
            _peer_context = _concurrent_contexts[_peer]
            _request = dict(_observation)
            _request["client_id"] = _endpoint

            if _peer_context["S"].get("task") is None:
                _result = _concurrent_pool.submit(
                    _blocking_query,
                    _request,
                ).result()
                _metadata = _record_b1(_endpoint, _result, _terminal=True)
                print(
                    "PGFR_GROOT_TERMINAL_B1_QUERY "
                    + _concurrent_json.dumps(
                        {
                            "active_endpoint": _endpoint,
                            "relay_port": _concurrent_relay_ports[_endpoint],
                            "batch_index": _metadata["batch_index"],
                            "inference_seed": _metadata["inference_seed"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                return _result

            _pending = _concurrent_group["pending_observations"]
            if _endpoint in _pending:
                raise RuntimeError(
                    "duplicate independent observation for %s" % _endpoint
                )
            _pending[_endpoint] = _request
            if len(_pending) == 2:
                if set(_pending) != set(_CONCURRENT_ENDPOINTS):
                    raise RuntimeError(
                        "independent observations lost arm identity"
                    )
                _round = int(_concurrent_group["query_round"])
                _observations = {
                    _arm: _pending[_arm] for _arm in _CONCURRENT_ENDPOINTS
                }
                _concurrent_group["pending_observations"] = {}
                _futures = {
                    _arm: _concurrent_pool.submit(
                        _concurrent_contexts[_arm][
                            "_PGFR_GROOT_BLOCKING_QUERY"
                        ],
                        _observations[_arm],
                    )
                    for _arm in _CONCURRENT_ENDPOINTS
                }
                _results = {
                    _arm: _futures[_arm].result()
                    for _arm in _CONCURRENT_ENDPOINTS
                }
                _concurrent_group["query_round"] = _round + 1
                _concurrent_group["pending_results"] = dict(_results)
                _metadata = {
                    _arm: _record_b1(_arm, _results[_arm])
                    for _arm in _CONCURRENT_ENDPOINTS
                }
                print(
                    "PGFR_GROOT_INDEPENDENT_B1_QUERY "
                    + _concurrent_json.dumps(
                        {
                            "query_round": _round,
                            "relay_ports": dict(_concurrent_relay_ports),
                            "batch_indices": {
                                _arm: _metadata[_arm]["batch_index"]
                                for _arm in _CONCURRENT_ENDPOINTS
                            },
                            "inference_seeds": {
                                _arm: _metadata[_arm]["inference_seed"]
                                for _arm in _CONCURRENT_ENDPOINTS
                            },
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                return _concurrent_group["pending_results"].pop(_endpoint)

            if _concurrent_group["inside_peer"]:
                _pending.pop(_endpoint, None)
                raise RuntimeError(
                    "peer query did not join independent B=1 dispatch"
                )
            if (
                _peer not in _concurrent_group["ran"]
                and _peer_context["S"].get("task") is not None
            ):
                _concurrent_group["ran"].add(_peer)
                _concurrent_group["inside_peer"] = True
                try:
                    _concurrent_runs[_peer](_concurrent_group["dt"])
                finally:
                    _concurrent_group["inside_peer"] = False
            _result = _concurrent_group["pending_results"].pop(
                _endpoint,
                None,
            )
            if _result is None:
                _concurrent_group["pending_observations"].pop(
                    _endpoint,
                    None,
                )
                raise RuntimeError(
                    "independent B=1 dispatch completed without result for %s"
                    % _endpoint
                )
            return _result

        return _independent_query

    for _concurrent_endpoint, _concurrent_context in (
        _concurrent_contexts.items()
    ):
        _concurrent_context["_grquery"] = _concurrent_query_factory(
            _concurrent_endpoint,
            _concurrent_context,
        )

    def _concurrent_sync_context(_endpoint):
        _source_context = _concurrent_base_contexts[_endpoint]
        _target_context = _concurrent_contexts[_endpoint]
        for _key in _CONCURRENT_CONTEXT_CONFIG_KEYS:
            if _key in _source_context:
                _target_context[_key] = _source_context[_key]
        _target_context["_GROOT_RELAY_HOST"] = "127.0.0.1"
        _target_context["_GROOT_RELAY_PORT"] = _concurrent_relay_ports[
            _endpoint
        ]
        _old_socket = _target_context.get("_GRSOCK")
        if _old_socket is not None:
            try:
                _old_socket.close()
            except Exception:
                pass
        _target_context["_GRSOCK"] = None
        _target_context["_PGFR_GROOT_BATCH_STATS"] = {
            "batch_1": 0,
            "batch_2": 0,
            "independent_b1": 0,
            "terminal_b1": 0,
        }
        _target_context.pop("_PGFR_GROOT_LAST_BATCH", None)

    def _concurrent_validate_pair(_command):
        _moves = _command.get("moves")
        if not isinstance(_moves, list) or len(_moves) != 2:
            raise ValueError("move_pair requires exactly two moves")
        _by_endpoint = {}
        for _move in _moves:
            if not isinstance(_move, dict):
                raise ValueError("every move_pair child must be an object")
            _child = dict(_move)
            _endpoint = str(_child.get("endpoint") or "")
            if _endpoint not in _CONCURRENT_ENDPOINTS:
                raise ValueError(
                    "move_pair endpoints must be franka_left and franka_right"
                )
            if _endpoint in _by_endpoint:
                raise ValueError("move_pair contains a duplicate endpoint")
            if (
                _child.get("action") != "move"
                or _child.get("backend") != "groot"
            ):
                raise ValueError(
                    "move_pair children must be GR00T move actions"
                )
            _by_endpoint[_endpoint] = _child
        if set(_by_endpoint) != set(_CONCURRENT_ENDPOINTS):
            raise ValueError("move_pair must contain one move for each arm")
        _colors = {
            _endpoint: str(_child.get("color") or "").lower()
            for _endpoint, _child in _by_endpoint.items()
        }
        if any(
            _color not in ("red", "blue", "green")
            for _color in _colors.values()
        ):
            raise ValueError(
                "every move_pair child must target a supported color"
            )
        return _by_endpoint, _colors

    def _concurrent_start(_command):
        if _command.get("action") != "move_pair":
            return _concurrent_serial_start(_command)
        if _concurrent_group["active"]:
            raise RuntimeError("a concurrent GR00T pair is already active")
        _by_endpoint, _colors = _concurrent_validate_pair(_command)

        # Validate both children completely before either executor is started.
        _prepared = {
            _endpoint: _concurrent_prepare(_by_endpoint[_endpoint])
            for _endpoint in _CONCURRENT_ENDPOINTS
        }
        if _colors["franka_left"] == "blue":
            # In the explicit B=2 trace, left blue's closest policy approach
            # was 0.0768 m before the policy requested closure.  The v29
            # target-close gate correctly kept the fingers open, but the
            # serial 0.055 m alignment admission never activated.  Admit only
            # this indexed, target-aware layout-3 case into the same recorded
            # pregrasp alignment.  All serial cases and every other concurrent
            # child retain their certified preparation unchanged.
            _left_blue = _prepared["franka_left"]
            _left_blue_deployment = dict(
                _left_blue.get("pgfr_groot_deployment") or {}
            )
            if (
                not _left_blue.get("target_aware_pregrasp_close_gate")
                or int(_left_blue.get("rollout_layout", -1)) != 3
                or float(_left_blue.get("pregrasp_alignment_radius", -1.0))
                != 0.055
                or _left_blue_deployment.get("policy_routing")
                != "shared-fixed-layout3-evaluation"
            ):
                raise RuntimeError(
                    "left-blue concurrent alignment contract mismatched"
                )
            _left_blue["pregrasp_alignment_radius"] = (
                _CONCURRENT_LEFT_BLUE_ALIGNMENT_RADIUS
            )
            _left_blue_deployment["pregrasp_alignment_radius"] = (
                _CONCURRENT_LEFT_BLUE_ALIGNMENT_RADIUS
            )
            _left_blue["pgfr_groot_deployment"] = _left_blue_deployment
            print(
                "PGFR_GROOT_CONCURRENT_LEFT_BLUE_ALIGNMENT "
                "layout=3 radius=%.3f source=%s"
                % (
                    _CONCURRENT_LEFT_BLUE_ALIGNMENT_RADIUS,
                    _left_blue.get("pregrasp_alignment_source"),
                ),
                flush=True,
            )
        for _endpoint in _CONCURRENT_ENDPOINTS:
            _deployment = dict(
                _prepared[_endpoint].get("pgfr_groot_deployment") or {}
            )
            if (
                _deployment.get("model_label")
                != _concurrent_policy_contract["model_label"]
                or _deployment.get("checkpoint_fingerprint")
                != _concurrent_policy_contract["checkpoint_fingerprint"]
            ):
                raise RuntimeError(
                    "prepared child does not identify the active shared model"
                )
            _deployment["relay_port"] = _concurrent_relay_ports[_endpoint]
            _deployment["concurrent_transport"] = _CONCURRENT_POLICY_MODE
            _deployment["concurrent_server_port"] = int(
                _concurrent_relays[_endpoint]["server_port"]
            )
            _prepared[_endpoint]["pgfr_groot_deployment"] = _deployment
        _routing = {
            (_prepared[_endpoint].get("pgfr_groot_deployment") or {}).get(
                "policy_routing"
            )
            for _endpoint in _CONCURRENT_ENDPOINTS
        }
        _ports = {
            (_prepared[_endpoint].get("pgfr_groot_deployment") or {}).get(
                "relay_port"
            )
            for _endpoint in _CONCURRENT_ENDPOINTS
        }
        _seeds_by_endpoint = {
            _endpoint: _prepared[_endpoint].get("inference_seed_base")
            for _endpoint in _CONCURRENT_ENDPOINTS
        }
        if any(
            not isinstance(_seed, int)
            or isinstance(_seed, bool)
            or _seed < 0
            for _seed in _seeds_by_endpoint.values()
        ):
            raise RuntimeError(
                "move_pair children require valid per-arm inference seeds"
            )
        _seed_values = set(_seeds_by_endpoint.values())
        _relay_contracts = {
            (_prepared[_endpoint].get("pgfr_groot_deployment") or {}).get(
                "relay_contract"
            )
            for _endpoint in _CONCURRENT_ENDPOINTS
        }
        if _routing != {"shared-fixed-layout3-evaluation"}:
            raise RuntimeError(
                "move_pair is admitted only for the validated shared policy"
            )
        if _ports != set(_concurrent_relay_ports.values()):
            raise RuntimeError(
                "move_pair children require the two pinned relays"
            )
        if _relay_contracts != {_CONCURRENT_RELAY_CONTRACT}:
            raise RuntimeError(
                "move_pair requires the identity-aware relay contract"
            )

        _concurrent_group["active"] = True
        _concurrent_group["results"] = {}
        _concurrent_group["query_round"] = 0
        _concurrent_group["pending_observations"] = {}
        _concurrent_group["pending_results"] = {}
        _concurrent_group["sync_wait_key"] = None
        _unique_colors = set(_colors.values())
        _command["color"] = (
            next(iter(_unique_colors))
            if len(_unique_colors) == 1
            else "mixed(left=%s,right=%s)"
            % (_colors["franka_left"], _colors["franka_right"])
        )
        _command["colors"] = dict(_colors)
        _command["policy_routing"] = next(iter(_routing))
        _command["relay_ports"] = dict(_concurrent_relay_ports)
        _command["concurrent_transport"] = _CONCURRENT_POLICY_MODE
        _command["inference_seed_by_arm"] = dict(_seeds_by_endpoint)
        if len(_seed_values) == 1:
            _command["inference_seed_base"] = next(iter(_seed_values))
        try:
            for _endpoint in _CONCURRENT_ENDPOINTS:
                _concurrent_sync_context(_endpoint)
                _context = _concurrent_contexts[_endpoint]
                _context["S"] = _concurrent_state(S.get("n", 0))
                _context["finish"] = _concurrent_finish_factory(
                    _endpoint,
                    _context,
                )
                _context["start"](_prepared[_endpoint])
        except Exception:
            _concurrent_group["active"] = False
            _concurrent_group["results"] = {}
            _concurrent_group["pending_observations"] = {}
            _concurrent_group["pending_results"] = {}
            for _context in _concurrent_contexts.values():
                _context["S"]["task"] = None
            raise
        print(
            "PGFR_GROOT_PAIR_START "
            + _concurrent_json.dumps(
                {
                    "colors": dict(_colors),
                    "endpoints": list(_CONCURRENT_ENDPOINTS),
                    "relay_ports": dict(_concurrent_relay_ports),
                    "transport": _CONCURRENT_POLICY_MODE,
                    "inference_seed_by_arm": dict(_seeds_by_endpoint),
                },
                sort_keys=True,
            ),
            flush=True,
        )

    def _concurrent_run_move(_dt):
        _main_task = S.get("task") or {}
        if _main_task.get("action") != "move_pair":
            return _concurrent_serial_run_move(_dt)
        if not _concurrent_group["active"]:
            raise RuntimeError("move_pair task has no active concurrent group")
        _concurrent_group["ran"] = set()
        _concurrent_group["inside_peer"] = False
        _concurrent_group["dt"] = _dt

        # Prefer an arm that currently needs a policy chunk. If both need one,
        # left starts and cooperatively advances right into the same batch.
        def _needs_query(_endpoint):
            _state = _concurrent_contexts[_endpoint]["S"]
            return (
                _state.get("task") is not None
                and not _state.get("groot_retrying_home")
                and (
                    _state.get("gbuf") is None
                    or int(_state.get("gi", 0))
                    >= int(_state.get("gexec", 0))
                )
            )

        _active = [
            _endpoint
            for _endpoint in _CONCURRENT_ENDPOINTS
            if _concurrent_contexts[_endpoint]["S"].get("task") is not None
        ]
        _query_ready = [
            _endpoint for _endpoint in _active if _needs_query(_endpoint)
        ]
        _query_mode, _scheduled_peer = _concurrent_select_query_mode(
            _active,
            _query_ready,
        )
        if _query_mode == "advance_peer":
            _waiting = _query_ready[0]
            _peer = _scheduled_peer
            if _peer not in _CONCURRENT_ENDPOINTS:
                raise RuntimeError("concurrent scheduler returned an invalid peer")
            _wait_key = (
                _waiting,
                int(
                    _concurrent_contexts[_waiting].get(
                        "_GROOT_QUERY_INDEX", 0
                    )
                ),
            )
            if _concurrent_group["sync_wait_key"] != _wait_key:
                _concurrent_group["sync_wait_key"] = _wait_key
                print(
                    "PGFR_GROOT_B1_SYNC_WAIT arm=%s peer=%s query_index=%d"
                    % (_waiting, _peer, _wait_key[1]),
                    flush=True,
                )
            # The peer may be executing a certified deterministic phase such
            # as pre-grasp alignment.  Advance that phase and let its own
            # evidence-bounded timeout decide failure.  A second generic
            # synchronization timeout would race and mask that physical gate.
            _concurrent_group["ran"].add(_peer)
            _concurrent_runs[_peer](_dt)
            return

        _concurrent_group["sync_wait_key"] = None
        _order = sorted(
            _CONCURRENT_ENDPOINTS,
            key=lambda _endpoint: (
                not _needs_query(_endpoint),
                _CONCURRENT_ENDPOINTS.index(_endpoint),
            ),
        )
        for _endpoint in _order:
            if (
                _endpoint in _concurrent_group["ran"]
                or _concurrent_contexts[_endpoint]["S"].get("task") is None
            ):
                continue
            _concurrent_group["ran"].add(_endpoint)
            _concurrent_runs[_endpoint](_dt)

    _concurrent_g["_PGFR_GROOT_CONCURRENT_CONTEXTS"] = _concurrent_contexts
    _concurrent_g["_PGFR_GROOT_CONCURRENT_GROUP"] = _concurrent_group
    _concurrent_g["_PGFR_GROOT_SERIAL_START"] = _concurrent_serial_start
    _concurrent_g["_PGFR_GROOT_SERIAL_RUN_MOVE"] = _concurrent_serial_run_move
    _concurrent_g["start"] = _concurrent_start
    _concurrent_g["run_move"] = _concurrent_run_move
    _concurrent_g["_PGFR_GROOT_CONCURRENT_READY"] = True
    _concurrent_g["_PGFR_GROOT_CONCURRENT_MIXED_READY"] = True
    _concurrent_g["_PGFR_GROOT_CONCURRENT_MIXED_REVISION"] = "per_arm_seed_v1"
    print(
        "PGFR_GROOT_DUAL_CONCURRENT_READY "
        "action=move_pair arms=franka_left,franka_right "
        "policy_protocol=timed_batch_v1 servers=2 batch_size_per_server=1 "
        "terminal_b1=enabled sync_bound=peer_certified_phase_limits "
        "mixed_color=true per_arm_seed=true relay_ports=%s"
        % _concurrent_json.dumps(
            _concurrent_relay_ports,
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )
except Exception:
    globals()["_PGFR_GROOT_CONCURRENT_READY"] = False
    globals()["_PGFR_GROOT_CONCURRENT_MIXED_READY"] = False
    print(
        "PGFR_GROOT_DUAL_CONCURRENT_ERROR:\n"
        + _concurrent_traceback.format_exc(),
        flush=True,
    )
    raise
