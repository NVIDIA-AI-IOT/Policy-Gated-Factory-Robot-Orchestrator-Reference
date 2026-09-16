# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Prepare shared Order744-cont24 GR00T moves for the Policy-Gated Factory Robot Orchestrator Reference cell.

The adapter binds the direct V36 two-arm executor to the fixed layout-3 scene,
validates the configured one-model relay and service state, enriches each move
with the proven physical-friction and measured-home contract, and fails closed
before motion when any route, camera, scene, or task condition is invalid.
"""

import json as _deploy_json
import os as _deploy_os
import pickle as _deploy_pickle
import re as _deploy_re
import socket as _deploy_socket
import struct as _deploy_struct
import time as _deploy_time
import traceback as _deploy_traceback

import numpy as _deploy_np


_deploy_g = globals()
_deploy_g["_PGFR_GROOT_DEPLOYMENT_READY"] = False

_DEPLOY_SHARED_EXECUTOR_PATH = (
    "/scripts/native_droid_work/executors/"
    "follow_groot_home_convergence_v36.py"
)
_DEPLOY_DATA_ROOT = "/scripts/groot_capture_context"
_DEPLOY_LANGUAGE = {
    "red": "pick the red cube and place it on the red pad",
    "blue": "pick the blue cylinder and place it on the blue pad",
    "green": "pick the green brick and place it on the green pad",
}
_DEPLOY_DUAL_SEQUENTIAL_LAYOUT = 3
_DEPLOY_DUAL_SEQUENTIAL_SEED = 31302
_DEPLOY_RAW_JOINT_LIMIT_REPLAN_MARGIN = 0.040
_DEPLOY_RAW_JOINT_LIMIT_REPLAN_LIMIT = 6
_DEPLOY_HOME_CONVERGENCE_TOLERANCE = 0.030
_DEPLOY_HOME_MIN_TICKS = 120
_DEPLOY_HOME_SETTLE_TICKS = 12
_DEPLOY_HOME_TIMEOUT_TICKS = 600
_DEPLOY_SHARED_POLICY_ALLOWED_KEYS = {
    "schema_version",
    "routing",
    "model_label",
    "checkpoint",
    "checkpoint_fingerprint",
    "relay_host",
    "relay_port",
    "relay_contract",
    "service_state_path",
}
_DEPLOY_SHARED_POLICY_OPTIONAL_KEYS = {"server_port"}
_DEPLOY_SHARED_POLICY_RELAY_CONTRACTS = {
    "single_frame_[0]",
    "batch2_single_frame_[0]",
    "explicit_pair_v1_single_frame_[0]",
}
_DEPLOY_SHARED_TARGET_CLOSE_CASE = ("blue", "franka_left", 3)
_DEPLOY_SHARED_TARGET_CLOSE_ADMISSION_RADIUS = 0.045
_DEPLOY_SHARED_TARGET_ALIGNMENT_RADIUS = 0.055
_DEPLOY_SHARED_SERIAL_MAX_MESSAGE_BYTES = 32 * 1024 * 1024
_DEPLOY_SHARED_SERIAL_TIMEOUT_S = 120.0


def _deploy_shared_color_canary():
    _raw = _deploy_g.get("_PGFR_GROOT_SHARED_COLOR_CANARY")
    if _raw is None:
        return None
    _required = {
        "schema_version",
        "mode",
        "layout",
        "seed",
        "arm",
        "color",
        "used",
    }
    if not isinstance(_raw, dict) or set(_raw) != _required:
        raise RuntimeError("invalid shared color canary record: %s" % _raw)
    _record = dict(_raw)
    if (
        _record["schema_version"] != 1
        or _record["mode"] != "color-slot-canary-v1"
        or int(_record["layout"]) not in range(6)
        or int(_record["layout"]) == _DEPLOY_DUAL_SEQUENTIAL_LAYOUT
        or int(_record["seed"]) != _DEPLOY_DUAL_SEQUENTIAL_SEED
        or _record["arm"] not in ("franka_left", "franka_right")
        or _record["color"] not in _DEPLOY_LANGUAGE
        or not isinstance(_record["used"], bool)
    ):
        raise RuntimeError("invalid shared color canary values: %s" % _record)
    return _record
# Seed 31302 is the certified left-blue layout-3 scene.  It places the left
# cylinder at [3.729061, -7.002156], exactly matching the successful blue
# evaluation, and its continued RNG stream places the right cylinder within
# 3 mm of the successful right-blue layout-3 scene.  The former generic seed
# 50100 shifted the left cylinder 7.5 mm from that pose; the recorded
# pre-close alignment then contacted its side and displaced it before grasp.
# Live sequential compositions reached left red to 0.0641 m and left green to
# 0.0576 m with an open gripper, just outside v25's certified 0.055 m
# demonstration-alignment gate.  In both cases the next policy chunk closed
# without a confirmed grasp and moved away.  Admit only those two shapes into
# the wider bounded alignment for the six-object sequential composition.
#
# Blue is intentionally different.  Both complete green->red->blue six-pick
# recordings used the demonstrated frame-133 anchors with a 0.045 m admission
# radius and a 1,200-tick far-case ceiling.  Substituting the earlier open
# frame-110 anchor made right-blue stop 0.062-0.066 m from the pad, suppress
# every physical open command at the 0.060 m release gate, and sweep the prior
# right-tote cargo out before timing out.  Keep the exact recorded anchors.
_DEPLOY_DUAL_SEQUENTIAL_ALIGNMENT_RADIUS = {
    ("red", "franka_left", 3): 0.070,
    ("red", "franka_right", 3): 0.070,
    ("blue", "franka_left", 3): 0.045,
    ("blue", "franka_right", 3): 0.045,
    ("green", "franka_left", 3): 0.070,
    ("green", "franka_right", 3): 0.070,
}
# In the first v3 red-last trace, the bounded alignment moved toward the
# demonstration pose but its certified 300-tick case budget expired while
# coupled joints were still settling.  Blue's unchanged bounded alignment
# required 1,067 ticks in the same sequential scene.  Reuse the established
# 1,200-tick far-case ceiling for sequential red and the recorded blue anchors;
# certified single-case budgets remain unchanged.
_DEPLOY_DUAL_SEQUENTIAL_ALIGNMENT_TICK_LIMIT = {
    ("red", "franka_left", 3): 1200,
    ("red", "franka_right", 3): 1200,
    ("blue", "franka_left", 3): 1200,
    ("blue", "franka_right", 3): 1200,
}
_DEPLOY_OBJECT_INDEX = {
    ("franka_left", "red"): 0,
    ("franka_right", "red"): 1,
    ("franka_left", "blue"): 2,
    ("franka_right", "blue"): 3,
    ("franka_left", "green"): 4,
    ("franka_right", "green"): 5,
}


def _deploy_case(
    _seed,
    _inference_seed,
    _alignment_pose=None,
    _alignment_source=None,
    _alignment_tick_limit=240,
    _release_xy_radius=0.06,
    _release_max_height=0.20,
    _release_fallback_ticks=45,
):
    return {
        "seed": int(_seed),
        "inference_seed": int(_inference_seed),
        "alignment_pose": _alignment_pose,
        "alignment_source": _alignment_source,
        "alignment_tick_limit": int(_alignment_tick_limit),
        "release_xy_radius": float(_release_xy_radius),
        "release_max_height": float(_release_max_height),
        "release_fallback_ticks": int(_release_fallback_ticks),
    }


_DEPLOY_CASES = {
    ("red", "franka_left", 1): _deploy_case(30100, 0),
    ("red", "franka_left", 3): _deploy_case(
        30301,
        1,
        [-0.042420, -1.060858, 1.835658, -2.469476, 1.420573, 2.123052, 1.526801],
        "left/red/raw96/ep_060/states.json:frame133",
        300,
    ),
    ("red", "franka_left", 5): _deploy_case(
        30502,
        2,
        [-0.243280, -0.629022, 1.858959, -2.732733, 1.277573, 2.512135, 1.245490],
        "left/red/raw96/ep_093/states.json:frame133",
        720,
    ),
    ("red", "franka_right", 1): _deploy_case(40100, 0),
    ("red", "franka_right", 3): _deploy_case(
        40301,
        1,
        [-0.030903, -1.0660583, 1.8342627, -2.4674656, 1.4226438, 2.1182168, 1.5382564],
        "right/red/raw96/ep_058/states.json:frame133",
        300,
    ),
    ("red", "franka_right", 5): _deploy_case(
        40502,
        2,
        [
            -0.2622172,
            -0.6215308,
            1.8662610,
            -2.7284567,
            1.2690320,
            2.5193665,
            1.2417092,
        ],
        "right/red/raw96/ep_091/states.json:frame133",
        720,
    ),
    ("blue", "franka_left", 2): _deploy_case(31200, 0),
    ("blue", "franka_left", 0): _deploy_case(
        31001,
        1,
        [
            -0.0234614,
            -1.0675987,
            1.8334268,
            -2.4695253,
            1.4245696,
            2.1169078,
            1.5425454,
        ],
        "left/blue/layout_0/ep_011:frame133",
        420,
    ),
    ("blue", "franka_left", 3): _deploy_case(
        31302,
        2,
        [
            -0.2744372,
            -0.6246895,
            1.8709174,
            -2.7200687,
            1.2648864,
            2.5163217,
            1.2413369,
        ],
        "left/blue/layout_3/ep_010:frame133",
        1200,
    ),
    ("blue", "franka_right", 2): _deploy_case(41200, 0),
    ("blue", "franka_right", 0): _deploy_case(
        41001,
        1,
        [
            -0.0364950,
            -1.0597422,
            1.8343267,
            -2.4725571,
            1.4205616,
            2.1234708,
            1.5294747,
        ],
        "right/blue/layout_0/ep_005:frame133",
        420,
    ),
    ("blue", "franka_right", 3): _deploy_case(
        41302,
        2,
        [
            -0.2447477,
            -0.6208526,
            1.8590802,
            -2.7367785,
            1.2739518,
            2.5195570,
            1.2447063,
        ],
        "right/blue/layout_3/ep_002:frame133",
        1200,
    ),
    ("green", "franka_left", 3): _deploy_case(
        32300,
        0,
        [0.4867226, -1.1363325, 1.7773260, -2.6412718, 1.5255871, 2.0475738, 1.8285493],
        "left/green/layout_3/ep_009:frame133",
        420,
    ),
    ("green", "franka_left", 1): _deploy_case(
        32101,
        1,
        [
            -0.0298147,
            -1.0623341,
            1.8336047,
            -2.4721057,
            1.4219030,
            2.1211231,
            1.5354884,
        ],
        "left/green/layout_1/ep_011:frame133",
        420,
    ),
    ("green", "franka_left", 0): _deploy_case(
        32002,
        2,
        [
            -0.2989769,
            -0.6065437,
            1.8802391,
            -2.7189803,
            1.2489419,
            2.5329876,
            1.2378176,
        ],
        "left/green/layout_0/ep_003:frame133",
        1200,
    ),
    ("green", "franka_right", 3): _deploy_case(
        42300,
        0,
        [0.4960229, -1.1385096, 1.7762460, -2.6438348, 1.5272639, 2.0453115, 1.8343527],
        "right/green/layout_3/ep_006:frame133",
        420,
    ),
    ("green", "franka_right", 1): _deploy_case(
        42101,
        0,
        [
            -0.0372570,
            -1.0580771,
            1.8345280,
            -2.4747810,
            1.4207101,
            2.1251070,
            1.5268588,
        ],
        "right/green/layout_1/ep_006:frame133",
        420,
        0.10,
        0.16,
        1,
    ),
    ("green", "franka_right", 0): _deploy_case(
        42002,
        2,
        [
            -0.2783510,
            -0.5910422,
            1.8711398,
            -2.7365477,
            1.2479094,
            2.5463557,
            1.2422034,
        ],
        "right/green/layout_0/ep_008:frame133",
        1200,
        0.10,
        0.16,
        1,
    ),
}


def _deploy_validate_shared_policy_contract():
    """Validate the required one-model route and live relay identity."""

    _raw = _deploy_g.get("_PGFR_GROOT_SHARED_POLICY_CONTRACT")
    if _raw is None:
        return None
    if not isinstance(_raw, dict) or set(_raw) not in (
        _DEPLOY_SHARED_POLICY_ALLOWED_KEYS,
        _DEPLOY_SHARED_POLICY_ALLOWED_KEYS
        | _DEPLOY_SHARED_POLICY_OPTIONAL_KEYS,
    ):
        raise RuntimeError("invalid shared-policy routing keys: %s" % _raw)
    _contract = dict(_raw)
    _model_label = str(_contract.get("model_label", ""))
    _checkpoint = str(_contract.get("checkpoint", ""))
    _fingerprint = str(_contract.get("checkpoint_fingerprint", ""))
    _state_path = str(_contract.get("service_state_path", ""))
    _server_port = _contract.get("server_port", 5571)
    if (
        _contract.get("schema_version") != 1
        or _contract.get("routing") != "shared-fixed-layout3-evaluation"
        or not _deploy_re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", _model_label)
        or not _deploy_os.path.isabs(_checkpoint)
        or _checkpoint == "/"
        or not _deploy_re.fullmatch(r"[0-9a-f]{64}", _fingerprint)
        or _contract.get("relay_host") != "127.0.0.1"
        or not isinstance(_server_port, int)
        or not 1024 <= int(_server_port) <= 65535
        or not isinstance(_contract.get("relay_port"), int)
        or not 1024 <= int(_contract["relay_port"]) <= 65535
        or _contract.get("relay_contract")
        not in _DEPLOY_SHARED_POLICY_RELAY_CONTRACTS
        or not _deploy_os.path.isabs(_state_path)
        or not _deploy_os.path.isfile(_state_path)
    ):
        raise RuntimeError("invalid shared-policy routing contract: %s" % _contract)
    with open(_state_path, encoding="utf-8") as _state_stream:
        _state = _deploy_json.load(_state_stream)
    _expected_state = {
        "schema_version": 1,
        "status": "ready",
        "model_label": _model_label,
        "checkpoint": _checkpoint,
        "server_host": "127.0.0.1",
        "server_port": int(_server_port),
        "relay_host": "127.0.0.1",
        "relay_port": int(_contract["relay_port"]),
        "relay_contract": _contract["relay_contract"],
        "preserve_until_explicit_stop": True,
    }
    _actual_state = {_key: _state.get(_key) for _key in _expected_state}
    if _actual_state != _expected_state:
        raise RuntimeError(
            "shared-policy service identity mismatch expected=%s actual=%s"
            % (_expected_state, _actual_state)
        )
    return _contract


def _deploy_shared_serial_receive_exact(_connection, _count):
    _chunks = bytearray()
    while len(_chunks) < _count:
        _chunk = _connection.recv(_count - len(_chunks))
        if not _chunk:
            raise ConnectionError("shared GR00T relay closed the connection")
        _chunks.extend(_chunk)
    return bytes(_chunks)


def _deploy_shared_serial_query(_context, _request):
    """Perform one bounded request on a fresh loopback connection.

    The inherited executor transport keeps a socket in its private namespace.
    Those namespaces are rebuilt across scene resets, making retained socket
    identity difficult to prove.  Shared serial evaluation instead uses one
    connection per policy chunk, matching the explicit pair transport's
    stop-on-uncertainty framing without changing the relay or policy protocol.
    """

    _host = str(_context.get("_GROOT_RELAY_HOST", "127.0.0.1"))
    _port = int(_context.get("_GROOT_RELAY_PORT", 0))
    if _host != "127.0.0.1" or not 1024 <= _port <= 65535:
        raise RuntimeError(
            "invalid shared serial GR00T relay endpoint %s:%s" % (_host, _port)
        )
    _payload = _deploy_pickle.dumps(_request, protocol=4)
    if not 0 < len(_payload) <= _DEPLOY_SHARED_SERIAL_MAX_MESSAGE_BYTES:
        raise ValueError(
            "invalid shared serial GR00T request size: %d" % len(_payload)
        )
    _started = _deploy_time.perf_counter()
    print(
        "PGFR_GROOT_SHARED_SERIAL_QUERY "
        "arm=%s seed=%s relay=%s:%d request_bytes=%d connection=fresh"
        % (
            _request.get("client_id"),
            _request.get("inference_seed"),
            _host,
            _port,
            len(_payload),
        ),
        flush=True,
    )
    with _deploy_socket.create_connection(
        (_host, _port), timeout=_DEPLOY_SHARED_SERIAL_TIMEOUT_S
    ) as _connection:
        _connection.settimeout(_DEPLOY_SHARED_SERIAL_TIMEOUT_S)
        _connection.sendall(
            _deploy_struct.pack(">I", len(_payload)) + _payload
        )
        _response_size = _deploy_struct.unpack(
            ">I", _deploy_shared_serial_receive_exact(_connection, 4)
        )[0]
        if not 0 < _response_size <= _DEPLOY_SHARED_SERIAL_MAX_MESSAGE_BYTES:
            raise ValueError(
                "invalid shared serial GR00T response size: %d"
                % _response_size
            )
        _response = _deploy_pickle.loads(
            _deploy_shared_serial_receive_exact(_connection, _response_size)
        )
    print(
        "PGFR_GROOT_SHARED_SERIAL_RESULT "
        "arm=%s seed=%s response_bytes=%d elapsed=%.3fs"
        % (
            _request.get("client_id"),
            _request.get("inference_seed"),
            _response_size,
            _deploy_time.perf_counter() - _started,
        ),
        flush=True,
    )
    return _response


def _deploy_shared_serial_exchange(_arm, _transport, _observation):
    """Add and verify the arm identity required by the batch-two relay.

    The concurrent adapter already supplies ``client_id`` in its explicit-pair
    envelope. Serial execution reaches the same relay through a fresh bounded
    exchange, so it must supply the identity here as well. Keep this wrapper
    The wrapper is scoped to the shared route and preserves the relay protocol.
    """

    if _arm not in ("franka_left", "franka_right"):
        raise ValueError("invalid shared serial GR00T arm: %s" % _arm)
    if not isinstance(_observation, dict):
        raise TypeError("shared serial GR00T observation must be a dictionary")
    _request = dict(_observation)
    _supplied_client = _request.get("client_id")
    if _supplied_client not in (None, _arm):
        raise RuntimeError(
            "shared serial GR00T client identity mismatch expected=%s actual=%s"
            % (_arm, _supplied_client)
        )
    _request["client_id"] = _arm
    _result = _transport(_request)
    _metadata = _result.get("_batch") if isinstance(_result, dict) else None
    _expected_seed = _request.get("inference_seed")
    if (
        not isinstance(_metadata, dict)
        or _metadata.get("schema_version") != 1
        or _metadata.get("client_id") != _arm
        or _metadata.get("batch_size") != 1
        or _metadata.get("protocol") != "timed_batch_v1"
        or _metadata.get("inference_seed") != _expected_seed
        or not isinstance(_metadata.get("batch_index"), int)
        or isinstance(_metadata.get("batch_index"), bool)
    ):
        raise RuntimeError(
            "shared serial GR00T relay identity mismatch arm=%s metadata=%s"
            % (_arm, _metadata)
        )
    return _result


def _deploy_install_shared_serial_transport(_contexts):
    for _arm in ("franka_left", "franka_right"):
        _context = _contexts[_arm]
        if not callable(_context.get("_grquery")):
            raise RuntimeError(
                "shared serial GR00T query function is missing for %s" % _arm
            )
        # Retire the first transport iteration's retained base-query pointer.
        # It must not be reused across a scene-reset context rebuild.
        _context.pop("_PGFR_GROOT_SHARED_SERIAL_BASE_QUERY", None)

        def _query(_observation, _arm=_arm, _context=_context):
            return _deploy_shared_serial_exchange(
                _arm,
                lambda _request: _deploy_shared_serial_query(
                    _context,
                    _request,
                ),
                _observation,
            )

        _context["_grquery"] = _query


def _deploy_camera_record(_message, _label):
    if _message is None:
        raise RuntimeError("%s camera has no post-reset frame" % _label)
    _height = int(_message.height)
    _width = int(_message.width)
    _raw = _deploy_np.frombuffer(bytes(_message.data), dtype=_deploy_np.uint8)
    _pixels = _height * _width
    if (_height, _width) != (180, 320) or _pixels <= 0 or _raw.size % _pixels:
        raise RuntimeError(
            "%s camera violates native-DROID 320x180 contract: "
            "actual=%dx%d" % (_label, _width, _height)
        )
    _channels = _raw.size // _pixels
    if _channels != 3:
        raise RuntimeError(
            "%s camera violates native-DROID RGB contract: channels=%d"
            % (_label, _channels)
        )
    _sample = _raw[:: max(1, _raw.size // 4096)]
    _dynamic_range = int(_sample.max()) - int(_sample.min())
    _standard_deviation = float(_deploy_np.std(_sample))
    if _dynamic_range < 16 or _standard_deviation < 2.0:
        raise RuntimeError(
            "%s camera is blank/constant range=%d std=%.3f"
            % (_label, _dynamic_range, _standard_deviation)
        )
    return {
        "shape": [_height, _width, _channels],
        "dynamic_range": _dynamic_range,
        "std": round(_standard_deviation, 3),
        "sample": bytes(_sample),
    }


def _deploy_camera_audit(_contexts):
    _records = {}
    for _arm in ("franka_left", "franka_right"):
        _frames = _contexts[_arm].get("_GRF") or {}
        for _view in ("wrist", "outside"):
            _label = "%s_%s" % (_arm, _view)
            _records[_label] = _deploy_camera_record(
                _frames.get(_view),
                _label,
            )
    if (
        _records["franka_left_wrist"]["sample"]
        == _records["franka_right_wrist"]["sample"]
        or _records["franka_left_outside"]["sample"]
        == _records["franka_right_outside"]["sample"]
    ):
        raise RuntimeError("left/right GR00T camera buffers are duplicate")
    return {
        _label: {_key: _value for _key, _value in _record.items() if _key != "sample"}
        for _label, _record in _records.items()
    }


def _deploy_home_state(_color, _arm, _layout):
    _side = "right" if _arm == "franka_right" else "left"
    _states_path = "%s/%s/%s/layout_%d/ep_000/states.json" % (
        _DEPLOY_DATA_ROOT,
        _side,
        _color,
        _layout,
    )
    if not _deploy_os.path.isfile(_states_path):
        raise FileNotFoundError(_states_path)
    with open(_states_path, encoding="utf-8") as _stream:
        _states = _deploy_json.load(_stream)
    _home = _deploy_np.asarray(_states[0]["fl_joints"], dtype=float)
    if _home.shape == (8,):
        _home = _deploy_np.concatenate(
            (_home, _deploy_np.asarray([_home[7]], dtype=float))
        )
    if _home.shape != (9,) or not _deploy_np.isfinite(_home).all():
        raise RuntimeError("invalid recorded DROID home state: " + _states_path)
    return _home, _states_path


def _deploy_scene_audit(_color, _arm, _case):
    _scene = dict(_deploy_g.get("_PGFR_SHAPE_LAST_SCENE") or {})
    _protocol = dict(_scene.get("capture_protocol") or {})
    _dual = _protocol.get("mode") == "shape_dual_triple"
    if _dual:
        _color_canary = _deploy_shared_color_canary()
        _admitted_layout = (
            int(_color_canary["layout"])
            if _color_canary is not None
            else _DEPLOY_DUAL_SEQUENTIAL_LAYOUT
        )
        _layouts = dict(_scene.get("layouts") or {})
        _layout = int(_layouts.get(_arm, -1))
        if (
            _protocol.get("arm") != "both"
            or _layouts
            != {
                "franka_left": _admitted_layout,
                "franka_right": _admitted_layout,
            }
            or int(_scene.get("seed", -1)) != _DEPLOY_DUAL_SEQUENTIAL_SEED
            or set(ACTIVE) != set(range(6))
        ):
            raise RuntimeError(
                "GR00T dual sequence requires the pinned six-object reset; "
                "scene=%s active=%s" % (_scene, sorted(ACTIVE))
            )
        _staged_by_arm = dict(_scene.get("positions_xyz") or {})
        _states = {}
        _positions = []
        for _item_arm in ("franka_left", "franka_right"):
            _arm_staged = dict(_staged_by_arm.get(_item_arm) or {})
            _tote_prim = tp_r if _item_arm == "franka_right" else tp
            for _item_color in ("red", "blue", "green"):
                _index = _DEPLOY_OBJECT_INDEX[(_item_arm, _item_color)]
                _position = _deploy_np.asarray(
                    wrp[_index].get_world_pose()[0],
                    dtype=float,
                )
                _expected = _deploy_np.asarray(
                    _arm_staged.get(_item_color, []),
                    dtype=float,
                )
                _staged = bool(
                    _position.shape == (3,)
                    and _expected.shape == (3,)
                    and _deploy_np.isfinite(_position).all()
                    and float(_deploy_np.linalg.norm(_position[:2] - _expected[:2]))
                    <= 0.012
                    and 0.70 <= float(_position[2]) <= 0.77
                )
                _center = _deploy_np.asarray(
                    comp_world(_item_color, _tote_prim),
                    dtype=float,
                )
                _in_matching_tote = bool(
                    _position.shape == (3,)
                    and _deploy_np.isfinite(_position).all()
                    and float(_deploy_np.linalg.norm(_position[:2] - _center[:2]))
                    < 0.12
                    and float(_position[2]) > 0.66
                )
                _is_target = _item_arm == _arm and _item_color == _color
                if (_is_target and not _staged) or (
                    not _is_target and not (_staged or _in_matching_tote)
                ):
                    raise RuntimeError(
                        "six-object sequence state invalid arm=%s color=%s "
                        "actual=%s expected=%s staged=%s "
                        "in_matching_tote=%s"
                        % (
                            _item_arm,
                            _item_color,
                            _position.tolist(),
                            _expected.tolist(),
                            _staged,
                            _in_matching_tote,
                        )
                    )
                _states["%s|%s" % (_item_arm, _item_color)] = (
                    "staged" if _staged else "matching_tote"
                )
                if _staged:
                    _positions.append(_position)
        _contract = (
            "shared-color-slot-canary-v1"
            if _color_canary is not None
            else "fixed-layout3-dual-sequential-physical-friction-v8"
        )
    else:
        _layouts = dict(_scene.get("layouts") or {})
        _layout = int(_layouts.get(_arm, _scene.get("layout", -1)))
        if (
            _protocol.get("mode") != "shape_triple"
            or _protocol.get("arm") != _arm
            or _scene.get("target") != _color
            or int(_scene.get("seed", -1)) != int(_case["seed"])
            or set(ACTIVE) != {0, 2, 4}
        ):
            raise RuntimeError(
                "GR00T task requires an exact single-arm certified reset; "
                "scene=%s active=%s" % (_scene, sorted(ACTIVE))
            )
        _staged = dict(_scene.get("positions_xyz") or {})
        _actual = {}
        for _item_color, _index in (
            ("red", 0),
            ("blue", 2),
            ("green", 4),
        ):
            _position = _deploy_np.asarray(
                wrp[_index].get_world_pose()[0],
                dtype=float,
            )
            _expected = _deploy_np.asarray(
                _staged.get(_item_color, []),
                dtype=float,
            )
            if (
                _position.shape != (3,)
                or _expected.shape != (3,)
                or not _deploy_np.isfinite(_position).all()
                or float(_deploy_np.linalg.norm(_position[:2] - _expected[:2])) > 0.012
                or not 0.70 <= float(_position[2]) <= 0.77
            ):
                raise RuntimeError(
                    "staged %s moved before rollout: actual=%s expected=%s"
                    % (
                        _item_color,
                        _position.tolist(),
                        _expected.tolist(),
                    )
                )
            _actual[_item_color] = _position
        _positions = list(_actual.values())
        _states = {"%s|%s" % (_arm, _item_color): "staged" for _item_color in _actual}
        _contract = "fixed-18-case-physical-friction-v1"
    _minimum_separation = (
        min(
            float(
                _deploy_np.linalg.norm(_positions[_left][:2] - _positions[_right][:2])
            )
            for _left in range(len(_positions))
            for _right in range(_left + 1, len(_positions))
        )
        if len(_positions) > 1
        else float(_scene.get("minimum_separation_m", 1.0))
    )
    if _minimum_separation < 0.13:
        raise RuntimeError(
            "certified scene separation is below the required minimum: %.6f" % _minimum_separation
        )
    return _layout, _minimum_separation, _contract, _states


try:
    _deploy_task = S.get("task") or {}
    if _deploy_task and _deploy_task.get("action") != "reset_scene":
        raise RuntimeError("refusing GR00T deployment install during an active task")
    if not _deploy_g.get("_PGFR_SHAPE_MODE_READY", False):
        raise RuntimeError("GR00T deployment requires hardened shape mode")
    _deploy_policy_route = str(_deploy_g.get("_PGFR_GROOT_POLICY_ROUTE", "shared"))
    if _deploy_policy_route != "shared":
        raise RuntimeError(
            "the public V36 deployment requires PGFR_GROOT_POLICY_ROUTE=shared"
        )
    _deploy_shared_policy_contract = _deploy_validate_shared_policy_contract()
    if _deploy_shared_policy_contract is None:
        raise RuntimeError("the shared GR00T policy contract is required")
    _deploy_executor_revision = "v36h"
    _deploy_executor_path = _DEPLOY_SHARED_EXECUTOR_PATH
    _deploy_executor_context_key = "_PGFR_DUAL_GROOT_V36H_CONTEXTS"
    _deploy_runtime_revision = "home_convergence_v36_direct"
    _deploy_contexts = _deploy_g.get(_deploy_executor_context_key)
    if not _deploy_contexts or set(_deploy_contexts) != {"franka_left", "franka_right"}:
        raise RuntimeError("V36 dual executor is not installed")
    for _deploy_arm, _deploy_context in _deploy_contexts.items():
        if (
            _deploy_context.get("_PGFR_GROOT_EXECUTION_REVISION")
            != _deploy_runtime_revision
        ):
            raise RuntimeError(
                "V36 executor identity mismatch in %s" % _deploy_arm
            )
    _deploy_install_shared_serial_transport(_deploy_contexts)
    print(
        "PGFR_GROOT_SHARED_SERIAL_TRANSPORT_READY "
        "arms=franka_left,franka_right protocol=timed_batch_v1 "
        "client_identity=required",
        flush=True,
    )
    _deploy_original_start = _deploy_g["start"]
    _deploy_g["_PGFR_GROOT_DEPLOYMENT_ORIGINAL_START"] = _deploy_original_start

    def _pgfr_groot_certified_start(_command, *, _return_enriched=False):
        if _command.get("action") != "move" or _command.get("backend") != "groot":
            if _return_enriched:
                raise ValueError(
                    "certified preparation accepts only GR00T move commands"
                )
            # A cargo manifest belongs to exactly one haul.  The underlying
            # certified executor keeps state across commands, so discard the
            # prior tote's indices before it snapshots the next tote.
            if _command.get("action") in ("pick_and_place", "haul"):
                S.pop("cargo_manifest", None)
            return _deploy_original_start(_command)
        if not _deploy_g.get("_PGFR_FULL_SCENE_READY", False):
            raise RuntimeError("scene is not ready for GR00T deployment")

        _color = str(_command.get("color", "")).strip().lower()
        _arm = str(_command.get("endpoint") or "franka_left").strip().lower()
        if _color not in _DEPLOY_LANGUAGE:
            raise ValueError("unsupported GR00T deployment color: %s" % _color)
        if _arm not in ("franka_left", "franka_right"):
            raise ValueError("unsupported GR00T deployment arm: %s" % _arm)
        _destination = str(_command.get("destination") or _color).replace("tote_", "")
        if _destination != _color:
            raise ValueError(
                "certified GR00T task must use the matching %s pad" % _color
            )

        _scene = dict(_deploy_g.get("_PGFR_SHAPE_LAST_SCENE") or {})
        _layouts = dict(_scene.get("layouts") or {})
        _layout = int(_layouts.get(_arm, _scene.get("layout", -1)))
        _case_key = (_color, _arm, _layout)
        _case = _DEPLOY_CASES.get(_case_key)
        if _case is None:
            raise RuntimeError(
                "no physically certified GR00T case for %s" % (_case_key,)
            )
        _color_canary = _deploy_shared_color_canary()
        if _color_canary is not None:
            if _deploy_shared_policy_contract is None:
                raise RuntimeError(
                    "shared color canary requires the shared policy route"
                )
            if _color_canary["used"]:
                raise RuntimeError("shared color canary is single-use")
            if (
                _arm != _color_canary["arm"]
                or _color != _color_canary["color"]
                or _layout != int(_color_canary["layout"])
            ):
                raise RuntimeError(
                    "shared color canary command mismatch: command=%s record=%s"
                    % ((_arm, _color, _layout), _color_canary)
                )
        (
            _layout,
            _minimum_separation,
            _scene_contract,
            _scene_states,
        ) = _deploy_scene_audit(_color, _arm, _case)
        _camera_audit = _deploy_camera_audit(_deploy_contexts)
        _home, _states_path = _deploy_home_state(_color, _arm, _layout)
        _alignment_radius = 0.055
        _alignment_tick_limit = int(_case["alignment_tick_limit"])
        if _scene_contract == ("fixed-layout3-dual-sequential-physical-friction-v8"):
            _alignment_radius = float(
                _DEPLOY_DUAL_SEQUENTIAL_ALIGNMENT_RADIUS.get(
                    _case_key,
                    _alignment_radius,
                )
            )
            _alignment_tick_limit = int(
                _DEPLOY_DUAL_SEQUENTIAL_ALIGNMENT_TICK_LIMIT.get(
                    _case_key,
                    _alignment_tick_limit,
                )
            )
        _target_close_gate = bool(
            _deploy_shared_policy_contract is not None
            and _case_key == _DEPLOY_SHARED_TARGET_CLOSE_CASE
            and _scene_contract
            == "fixed-layout3-dual-sequential-physical-friction-v8"
        )
        if _target_close_gate:
            _alignment_radius = _DEPLOY_SHARED_TARGET_ALIGNMENT_RADIUS

        _context = _deploy_contexts[_arm]
        _executor_active_indices = sorted(
            int(_index) for _index in _deploy_g.get("ACTIVE", set())
        )
        if _arm == "franka_right":
            # The right executor is a private namespace.  Single-arm right
            # scenes alias their local shapes onto canonical indices 0/2/4,
            # while the six-object scene uses distinct right indices 1/3/5.
            # Bind this explicitly at every task boundary so the private
            # context cannot retain the prior reset profile's index set.
            _executor_active_indices = (
                [1, 3, 5]
                if _scene_contract
                in (
                    "fixed-layout3-dual-sequential-physical-friction-v8",
                    "shared-color-slot-canary-v1",
                )
                else [0, 2, 4]
            )
            _context["ACTIVE"] = set(_executor_active_indices)
            _context["wrp"] = _deploy_g["wrp"]
            _context["POOL_COL"] = _deploy_g["POOL_COL"]
        if (
            _scene_contract
            not in (
                "fixed-layout3-dual-sequential-physical-friction-v8",
                "shared-color-slot-canary-v1",
            )
        ):
            raise RuntimeError(
                "shared policy requires the pinned layout-3 scene or the "
                "operator-only color-slot canary"
            )
        _model_label = _deploy_shared_policy_contract["model_label"]
        _port = int(_deploy_shared_policy_contract["relay_port"])
        _policy_routing = _deploy_shared_policy_contract["routing"]
        _checkpoint_fingerprint = _deploy_shared_policy_contract[
            "checkpoint_fingerprint"
        ]
        _relay_identity = _deploy_shared_policy_contract["relay_contract"]
        _alignment_pose = _case["alignment_pose"]
        _alignment_source = _case["alignment_source"]
        if _scene_contract == "shared-color-slot-canary-v1":
            _alignment_pose = None
            _alignment_source = "disabled:color-slot-canary-v1"
        _context["_GROOT_RELAY_HOST"] = "127.0.0.1"
        _context["_GROOT_RELAY_PORT"] = _port
        _context["_GEXEC_OVERRIDE"] = 15
        _context["_GEXEC"] = 15
        _context["_GHOLD"] = 4
        _context["_GROOT_NATIVE_CONTROL_HZ"] = 15.0
        _context["_GROOT_PHYSICS_HZ"] = 60.0
        _context["_GN_LIMIT"] = 7000
        _context["_GROOT_SETTLE_FRAMES"] = 30
        _context["_GROOT_MAX_TARGET_STATE_ERROR"] = 0.12
        _context["_PGFR_GRASP_TH"] = 0.033
        _context["_PGFR_REL_TH"] = 0.036
        _context["_PGFR_LOCK_R"] = 0.06

        _closed = []
        for _context_arm, _arm_context in _deploy_contexts.items():
            _old_socket = _arm_context.get("_GRSOCK")
            if _old_socket is not None:
                try:
                    _old_socket.close()
                except Exception:
                    pass
                _closed.append(_context_arm)
            _arm_context["_GRSOCK"] = None

        _enriched = dict(_command)
        _enriched.update(
            {
                "action": "move",
                "color": _color,
                "endpoint": _arm,
                "backend": "groot",
                "physical_friction": True,
                "physical_release_gate": True,
                "physical_release_xy_radius": _case["release_xy_radius"],
                "physical_release_min_height": -0.01,
                "physical_release_max_height": _case["release_max_height"],
                "physical_release_confirm_actions": 2,
                "physical_release_on_zone": False,
                "physical_release_fallback_stall_ticks": _case[
                    "release_fallback_ticks"
                ],
                "physical_grip_hold_target": 0.016,
                "physical_grasp_confirm_lift": 0.004,
                "physical_grasp_confirm_drift": 0.012,
                "physical_grasp_confirm_ticks": 3,
                "native_droid": True,
                "native_direct": True,
                "tracking_gated_progress": True,
                "tracking_rate_limit_enabled": True,
                "transport_tracking_rate_limit_enabled": True,
                "tracking_progress_tolerance": 0.03,
                "tracking_progress_hold_limit": 45,
                "tracking_replan_limit": 8,
                "raw_joint_limit_replan_margin": (
                    _DEPLOY_RAW_JOINT_LIMIT_REPLAN_MARGIN
                ),
                "raw_joint_limit_replan_limit": (_DEPLOY_RAW_JOINT_LIMIT_REPLAN_LIMIT),
                "groot_home_convergence_tolerance": _DEPLOY_HOME_CONVERGENCE_TOLERANCE,
                "groot_home_min_ticks": _DEPLOY_HOME_MIN_TICKS,
                "groot_home_settle_ticks": _DEPLOY_HOME_SETTLE_TICKS,
                "groot_home_timeout_ticks": _DEPLOY_HOME_TIMEOUT_TICKS,
                "tracking_command_velocity_fraction": 1.0,
                "tracking_guard_enabled": True,
                "auto_recovery": False,
                "groot_retrying_home": True,
                "groot_home_target": _home.tolist(),
                "inference_seed_base": _case["inference_seed"],
                "language_instruction": _DEPLOY_LANGUAGE[_color],
                "model_label": _model_label,
                "execution_horizon": 15,
                "transport_execution_horizon": 15,
                "post_success_ticks": 120,
                "rollout_layout": _layout,
                "pregrasp_alignment_pose": _alignment_pose,
                "pregrasp_alignment_source": _alignment_source,
                "pregrasp_alignment_radius": _alignment_radius,
                "pregrasp_alignment_tolerance": 0.020,
                "pregrasp_alignment_velocity_fraction": 0.20,
                "pregrasp_alignment_tick_limit": _alignment_tick_limit,
                "target_aware_pregrasp_close_gate": _target_close_gate,
                "target_close_admission_radius": (
                    _DEPLOY_SHARED_TARGET_CLOSE_ADMISSION_RADIUS
                ),
                "pgfr_groot_deployment": {
                    "contract": _scene_contract,
                    "relay_port": _port,
                    "model_label": _model_label,
                    "scene_seed": int(_scene.get("seed", -1)),
                    "validation_case_seed": _case["seed"],
                    "states_path": _states_path,
                    "executor_revision": _deploy_executor_revision,
                    "raw_joint_limit_replan_margin": (
                        _DEPLOY_RAW_JOINT_LIMIT_REPLAN_MARGIN
                    ),
                    "raw_joint_limit_replan_limit": (
                        _DEPLOY_RAW_JOINT_LIMIT_REPLAN_LIMIT
                    ),
                    "groot_home_convergence_tolerance": _DEPLOY_HOME_CONVERGENCE_TOLERANCE,
                    "groot_home_min_ticks": _DEPLOY_HOME_MIN_TICKS,
                    "groot_home_settle_ticks": _DEPLOY_HOME_SETTLE_TICKS,
                    "groot_home_timeout_ticks": _DEPLOY_HOME_TIMEOUT_TICKS,
                    "pregrasp_alignment_radius": _alignment_radius,
                    "pregrasp_alignment_tick_limit": _alignment_tick_limit,
                    "pregrasp_alignment_enabled": _alignment_pose is not None,
                    "shared_color_canary": (
                        _scene_contract == "shared-color-slot-canary-v1"
                    ),
                    "target_aware_pregrasp_close_gate": _target_close_gate,
                    "target_close_admission_radius": (
                        _DEPLOY_SHARED_TARGET_CLOSE_ADMISSION_RADIUS
                    ),
                    "minimum_separation_m": _minimum_separation,
                    "executor_active_indices": _executor_active_indices,
                    "scene_states": _scene_states,
                    "camera_audit": _camera_audit,
                    "closed_policy_sockets": sorted(_closed),
                    "policy_routing": _policy_routing,
                    "checkpoint_fingerprint": _checkpoint_fingerprint,
                    "relay_contract": _relay_identity,
                },
            }
        )
        print(
            "PGFR_GROOT_CERTIFIED_PREFLIGHT "
            + _deploy_json.dumps(
                {
                    "arm": _arm,
                    "color": _color,
                    "layout": _layout,
                    "scene_seed": int(_scene.get("seed", -1)),
                    "validation_case_seed": _case["seed"],
                    "contract": _scene_contract,
                    "inference_seed": _case["inference_seed"],
                    "relay": "127.0.0.1:%d" % _port,
                    "executor_revision": _deploy_executor_revision,
                    "raw_joint_limit_replan_margin": (
                        _DEPLOY_RAW_JOINT_LIMIT_REPLAN_MARGIN
                    ),
                    "raw_joint_limit_replan_limit": (
                        _DEPLOY_RAW_JOINT_LIMIT_REPLAN_LIMIT
                    ),
                    "groot_home_convergence_tolerance": _DEPLOY_HOME_CONVERGENCE_TOLERANCE,
                    "groot_home_min_ticks": _DEPLOY_HOME_MIN_TICKS,
                    "groot_home_settle_ticks": _DEPLOY_HOME_SETTLE_TICKS,
                    "groot_home_timeout_ticks": _DEPLOY_HOME_TIMEOUT_TICKS,
                    "pregrasp_alignment_radius": _alignment_radius,
                    "pregrasp_alignment_tick_limit": _alignment_tick_limit,
                    "target_aware_pregrasp_close_gate": _target_close_gate,
                    "target_close_admission_radius": (
                        _DEPLOY_SHARED_TARGET_CLOSE_ADMISSION_RADIUS
                    ),
                    "minimum_separation_m": round(_minimum_separation, 6),
                    "executor_active_indices": _executor_active_indices,
                    "policy_routing": _policy_routing,
                    "model_label": _model_label,
                    "checkpoint_fingerprint": _checkpoint_fingerprint,
                    "relay_contract": _relay_identity,
                    "cameras": _camera_audit,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if _scene_contract == "shared-color-slot-canary-v1":
            _deploy_g["_PGFR_GROOT_SHARED_COLOR_CANARY"]["used"] = True
        if _return_enriched:
            return _enriched
        return _deploy_original_start(_enriched)

    _deploy_g["start"] = _pgfr_groot_certified_start
    _deploy_g["_PGFR_GROOT_CERTIFIED_PREPARE"] = (
        lambda _command: _pgfr_groot_certified_start(
            _command,
            _return_enriched=True,
        )
    )
    _deploy_g["_PGFR_GROOT_CERTIFIED_CASES"] = {
        "%s|%s|%d" % _key: dict(_value) for _key, _value in _DEPLOY_CASES.items()
    }
    _deploy_g["_PGFR_GROOT_SHARED_POLICY_DEPLOYMENT"] = (
        dict(_deploy_shared_policy_contract)
        if _deploy_shared_policy_contract is not None
        else None
    )
    _deploy_g["_PGFR_GROOT_DEPLOYMENT_EXECUTOR_CONTRACT"] = {
        "revision": _deploy_executor_revision,
        "runtime_revision": _deploy_runtime_revision,
        "path": _deploy_executor_path,
        "contexts_key": _deploy_executor_context_key,
    }
    _deploy_g["_PGFR_GROOT_DEPLOYMENT_READY"] = True
    print(
        "PGFR_GROOT_CERTIFIED_DEPLOYMENT_READY "
        "cases=%d colors=red,blue,green arms=franka_left,franka_right "
        "executor_revision=%s shared_policy=%s"
        % (
            len(_DEPLOY_CASES),
            _deploy_runtime_revision,
            _deploy_g["_PGFR_GROOT_SHARED_POLICY_DEPLOYMENT"],
        ),
        flush=True,
    )
except Exception:
    _deploy_g["_PGFR_GROOT_DEPLOYMENT_READY"] = False
    print(
        "PGFR_GROOT_CERTIFIED_DEPLOYMENT_ERROR:\n" + _deploy_traceback.format_exc(),
        flush=True,
    )
    raise
