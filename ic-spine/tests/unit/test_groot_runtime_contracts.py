# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free behavior contracts for the direct GR00T Isaac runtime."""

from __future__ import annotations

import ast
import math
import pickle
import struct
import time
from pathlib import Path

REFERENCE_ROOT = (
    Path(__file__).resolve().parents[3] / "reference" / "policy-gated-factory-robot-orchestrator-reference"
)
GROOT_ROOT = REFERENCE_ROOT / "groot"
RUNTIME_ROOT = GROOT_ROOT / "runtime" / "native_droid_work"
DEPLOYMENT = RUNTIME_ROOT / "ic_groot_certified_deployment_v36.py"
CONCURRENT = RUNTIME_ROOT / "ic_groot_dual_concurrent_mixed.py"
EXECUTOR = (
    RUNTIME_ROOT
    / "executors"
    / "follow_groot_home_convergence_v36.py"
)
TELEMETRY = RUNTIME_ROOT / "ic_sync_capture_cell.py"
ISAAC_DEPLOYMENT = REFERENCE_ROOT / "isaac-cell" / "deployment"


def _assignment_value(module: ast.Module, name: str) -> ast.expr:
    return next(
        node.value
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        )
    )


def test_independent_b1_source_never_builds_a_paired_policy_request() -> None:
    source = CONCURRENT.read_text(encoding="utf-8")
    assert "_deploy_install_shared_serial_transport" in source
    assert "_IC_GROOT_BLOCKING_QUERY" in source
    assert '_CONCURRENT_POLICY_MODE = "independent-b1-per-arm-v1"' in source
    assert "servers=2 batch_size_per_server=1" in source
    assert "IC_GROOT_INDEPENDENT_B1_QUERY" in source
    assert "IC_GROOT_TERMINAL_B1_QUERY" in source
    assert "max_workers=2" in source
    assert "infer_pair_v1" not in source
    assert "exchange_pair" not in source
    assert "build_terminal_pair_observations" not in source


def test_concurrent_executor_accepts_independent_mixed_child_colors() -> None:
    module = ast.parse(CONCURRENT.read_text(encoding="utf-8"))
    validate_node = next(
        node
        for parent in ast.walk(module)
        for node in getattr(parent, "body", [])
        if isinstance(node, ast.FunctionDef)
        and node.name == "_concurrent_validate_pair"
    )
    namespace: dict[str, object] = {
        "_CONCURRENT_ENDPOINTS": ("franka_left", "franka_right")
    }
    exec(
        compile(
            ast.Module(body=[validate_node], type_ignores=[]),
            str(CONCURRENT),
            "exec",
        ),
        namespace,
    )
    validate = namespace["_concurrent_validate_pair"]
    by_endpoint, colors = validate(
        {
            "moves": [
                {
                    "action": "move",
                    "backend": "groot",
                    "endpoint": "franka_left",
                    "color": "green",
                },
                {
                    "action": "move",
                    "backend": "groot",
                    "endpoint": "franka_right",
                    "color": "red",
                },
            ]
        }
    )

    assert set(by_endpoint) == {"franka_left", "franka_right"}
    assert colors == {"franka_left": "green", "franka_right": "red"}


def test_shared_serial_transport_supplies_and_validates_arm_identity() -> None:
    module = ast.parse(DEPLOYMENT.read_text(encoding="utf-8"))
    functions = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name
        in {
            "_deploy_shared_serial_exchange",
            "_deploy_install_shared_serial_transport",
        }
    ]
    namespace: dict[str, object] = {}
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), str(DEPLOYMENT), "exec"),
        namespace,
    )
    install = namespace["_deploy_install_shared_serial_transport"]
    exchange = namespace["_deploy_shared_serial_exchange"]
    requests: list[dict[str, object]] = []

    def base_query(request):
        requests.append(dict(request))
        return {
            "_batch": {
                "schema_version": 1,
                "client_id": request["client_id"],
                "batch_index": 7,
                "batch_size": 1,
                "protocol": "timed_batch_v1",
                "inference_seed": request["inference_seed"],
            }
        }

    contexts = {
        "franka_left": {"_grquery": base_query},
        "franka_right": {"_grquery": base_query},
    }
    namespace["_deploy_shared_serial_query"] = (
        lambda _context, request: base_query(request)
    )
    install(contexts)
    install(contexts)
    result = contexts["franka_right"]["_grquery"]({"inference_seed": 11})

    assert requests == [{"inference_seed": 11, "client_id": "franka_right"}]
    assert result["_batch"]["client_id"] == "franka_right"

    def wrong_identity(_request):
        return {
            "_batch": {
                "schema_version": 1,
                "client_id": "franka_left",
                "batch_index": 8,
                "batch_size": 1,
                "protocol": "timed_batch_v1",
                "inference_seed": 12,
            }
        }

    try:
        exchange("franka_right", wrong_identity, {"inference_seed": 12})
    except RuntimeError as exc:
        assert "relay identity mismatch" in str(exc)
    else:
        raise AssertionError("shared serial transport accepted the wrong arm identity")

    source = DEPLOYMENT.read_text(encoding="utf-8")
    assert "with _deploy_socket.create_connection(" in source
    assert '_context.pop("_IC_GROOT_SHARED_SERIAL_BASE_QUERY", None)' in source
    assert "_deploy_install_shared_serial_transport(_deploy_contexts)" in source


def test_shared_serial_transport_uses_fresh_bounded_framing() -> None:
    module = ast.parse(DEPLOYMENT.read_text(encoding="utf-8"))
    functions = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name
        in {
            "_deploy_shared_serial_receive_exact",
            "_deploy_shared_serial_query",
        }
    ]
    response_payload = pickle.dumps({"result": "ok"}, protocol=4)

    class FakeConnection:
        def __init__(self) -> None:
            self.reply = bytearray(struct.pack(">I", len(response_payload)))
            self.reply.extend(response_payload)
            self.sent = b""
            self.timeout = None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def settimeout(self, value) -> None:
            self.timeout = value

        def sendall(self, value) -> None:
            self.sent += value

        def recv(self, count):
            value = bytes(self.reply[:count])
            del self.reply[:count]
            return value

    connection = FakeConnection()
    calls = []

    class FakeSocket:
        @staticmethod
        def create_connection(endpoint, timeout):
            calls.append((endpoint, timeout))
            return connection

    namespace = {
        "_deploy_pickle": pickle,
        "_deploy_socket": FakeSocket,
        "_deploy_struct": struct,
        "_deploy_time": time,
        "_DEPLOY_SHARED_SERIAL_MAX_MESSAGE_BYTES": 32 * 1024 * 1024,
        "_DEPLOY_SHARED_SERIAL_TIMEOUT_S": 120.0,
    }
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), str(DEPLOYMENT), "exec"),
        namespace,
    )
    query = namespace["_deploy_shared_serial_query"]
    request = {"client_id": "franka_right", "inference_seed": 0}
    result = query(
        {"_GROOT_RELAY_HOST": "127.0.0.1", "_GROOT_RELAY_PORT": 5611},
        request,
    )

    assert result == {"result": "ok"}
    assert calls == [(('127.0.0.1', 5611), 120.0)]
    assert connection.timeout == 120.0
    request_size = struct.unpack(">I", connection.sent[:4])[0]
    assert request_size == len(connection.sent) - 4
    assert pickle.loads(connection.sent[4:]) == request


def test_certified_deployment_starts_each_haul_with_a_fresh_manifest() -> None:
    source = DEPLOYMENT.read_text(encoding="utf-8")
    non_groot_branch = source.split("def _ic_groot_certified_start(", 1)[1].split(
        "if not _deploy_g.get", 1
    )[0]
    assert '_command.get("action") in ("pick_and_place", "haul")' in non_groot_branch
    assert 'S.pop("cargo_manifest", None)' in non_groot_branch


def test_haul_cargo_gate_uses_tote_local_coordinates_and_stable_validation() -> None:
    source_path = ISAAC_DEPLOYMENT / "fix_amr_haul_joint.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    selected = [
        node
        for node in module.body
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id
                in {
                    "_CARGO_HALF_EXTENTS_XY",
                    "_CARGO_HEIGHT",
                    "_CARGO_VERIFY_STABLE_TICKS",
                    "_CARGO_VERIFY_TIMEOUT_TICKS",
                }
                for target in node.targets
            )
        )
        or (
            isinstance(node, ast.FunctionDef)
            and node.name in {"_tote_local_position", "_cargo_is_inside"}
        )
    ]
    namespace: dict[str, object] = {"math": math}
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(source_path), "exec"),
        namespace,
    )
    inside = namespace["_cargo_is_inside"]

    identity = (1.0, 0.0, 0.0, 0.0)
    assert inside((0.0, 0.0, 0.0), identity, (0.29, 0.17, 0.10))
    assert not inside((0.0, 0.0, 0.0), identity, (0.31, 0.0, 0.10))

    yaw_90 = (math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5))
    tote_position = (-0.26, -7.00, 0.52)
    assert inside(tote_position, yaw_90, (-0.26, -7.24, 0.62))

    source = source_path.read_text(encoding="utf-8")
    assert source.count("_cargo_is_inside(") >= 3
    assert source.index('if "cargo_manifest" not in S:') < source.index(
        'if st == "reach":'
    )
    assert 'S["cargo_manifest_phase"] = "pre_reach"' in source
    assert "_REACH_TICKS = 240" in source
    assert "_GRIP_CLOSE_TICKS = 120" in source
    assert '"cargo displaced before attach indices=%s"' in source
    assert 'setp("validate")' in source
    assert "_CARGO_VERIFY_STABLE_TICKS = 30" in source
    assert "_CARGO_VERIFY_TIMEOUT_TICKS = 300" in source


def test_dual_sequential_blue_uses_recorded_full_six_alignment() -> None:
    module = ast.parse(DEPLOYMENT.read_text(encoding="utf-8"))
    radii = ast.literal_eval(
        _assignment_value(module, "_DEPLOY_DUAL_SEQUENTIAL_ALIGNMENT_RADIUS")
    )
    tick_limits = ast.literal_eval(
        _assignment_value(module, "_DEPLOY_DUAL_SEQUENTIAL_ALIGNMENT_TICK_LIMIT")
    )
    cases = _assignment_value(module, "_DEPLOY_CASES")
    assert isinstance(cases, ast.Dict)

    expected = {
        ("blue", "franka_left", 3): (
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
        ),
        ("blue", "franka_right", 3): (
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
        ),
    }
    observed: dict[tuple[str, str, int], tuple[list[float], str]] = {}
    for key_node, case_node in zip(cases.keys, cases.values, strict=True):
        key = ast.literal_eval(key_node)
        if key not in expected:
            continue
        assert isinstance(case_node, ast.Call)
        observed[key] = (
            ast.literal_eval(case_node.args[2]),
            ast.literal_eval(case_node.args[3]),
        )

    assert observed == expected
    for key in expected:
        assert radii[key] == 0.045
        assert tick_limits[key] == 1200


def test_shared_left_blue_close_gate_precedes_alignment_and_close_wait() -> None:
    source = EXECUTOR.read_text(encoding="utf-8")
    guard = source.index("raw_close_requested =")
    alignment = source.index("alignment_pose_value =")
    close_wait = source.index("close_action_key =")
    apply_gripper = source.index("applied_gripcmd =")
    assert guard < alignment < close_wait < apply_gripper
    assert "close_requested = bool(raw_close_requested and not target_close_guard)" in source
    assert "GR_OPEN\n            if target_close_guard" in source
    assert "0.0 < target_close_admission_radius <= near_limit" in source


def test_capture_contract_accepts_six_core_products_plus_one_vlm_product() -> None:
    module = ast.parse(TELEMETRY.read_text(encoding="utf-8"))
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_capture_render_product_contract"
    )
    namespace: dict[str, object] = {}
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(TELEMETRY), "exec"),
        namespace,
    )
    validate = namespace["_capture_render_product_contract"]
    core = {
        "camera_profile": "capture",
        "render_products": {
            "wrist": "rp0",
            "outside": "rp1",
            "inspect": "rp1",
            "wrist_right": "rp2",
            "outside_right": "rp3",
            "table": "rp4",
            "rack": "rp5",
        },
    }
    vlm = {
        "camera_profile": "capture",
        "render_products": {"inspect_vlm": "rp6"},
        "additional_render_product_count": 1,
    }
    rendered = [f"rp{index}" for index in range(7)]

    assert validate(core, vlm, rendered)
    assert not validate(core, vlm, rendered[:-1])
    assert not validate(core, vlm, rendered + ["unexpected"])
