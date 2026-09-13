# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Static and contract tests for the runtime and user checkpoint integrity."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import shutil
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest


REPO = Path(__file__).resolve().parents[4]
GROOT = REPO / "reference" / "policy-gated-factory-robot-orchestrator-reference" / "groot"
RUNTIME = GROOT / "runtime"
CAPTURE_CONTEXT = GROOT / "capture_context"
ISAAC_DEPLOYMENT = (
    REPO / "reference" / "policy-gated-factory-robot-orchestrator-reference" / "isaac-cell" / "deployment"
)
RENDERER = REPO / "ops" / "render-groot-cont24-contracts.py"
INSTALLER = REPO / "ops" / "install-groot-cell.sh"
LAUNCHER = REPO / "ops" / "launch-groot-isaac.sh"
GROOT_SYSTEMD = REPO / "ops" / "systemd" / "groot"
DEPLOYMENT_MANIFEST = REPO / "deploy" / "reproducible-demo.yaml"
THOR_INSTALLER = GROOT / "thor" / "install_deps.sh"
THOR_DOCKERFILE = GROOT / "thor" / "Dockerfile"
PREPARE_GROOT_RUNTIME = REPO / "ops" / "prepare-groot-runtime.sh"
SERVING_HEALTH = ISAAC_DEPLOYMENT / "pgfr_serving_health.py"

PYTHON_SOURCES = (
    RUNTIME
    / "native_droid_work"
    / "executors"
    / "follow_groot_home_convergence_v36.py",
    RUNTIME / "native_droid_work" / "follow_groot_dual_physical_v36.py",
    RUNTIME / "native_droid_work" / "pgfr_groot_certified_deployment_v36.py",
    RUNTIME / "native_droid_work" / "pgfr_groot_dual_concurrent_mixed.py",
    RUNTIME / "cell" / "reset_two_arm.py",
    RENDERER,
)


_checkpoint_spec = importlib.util.spec_from_file_location("pgfr_checkpoint_contract_test", REPO / "ops/pgfr_checkpoint.py")
checkpoint_helpers = importlib.util.module_from_spec(_checkpoint_spec)
_checkpoint_spec.loader.exec_module(checkpoint_helpers)


def checkpoint_fixture(root: Path, *, sharded: bool = False) -> Path:
    root.mkdir()
    for name in checkpoint_helpers.REQUIRED_JSON:
        (root / name).write_text('{"fixture": true}\n', encoding="utf-8")
    if sharded:
        index = {"weight_map": {"layer.a": "weights-1.safetensors", "layer.b": "weights-2.safetensors"}}
        (root / checkpoint_helpers.INDEX_NAME).write_text(json.dumps(index), encoding="utf-8")
        for name in index["weight_map"].values():
            (root / name).write_bytes(b"fixture weights")
    else:
        (root / "model.safetensors").write_bytes(b"fixture weights")
    names = checkpoint_helpers.inference_files(root)
    metadata = {
        "schema_version": 1,
        "model_label": "user-trained-test",
        "embodiment_tag": checkpoint_helpers.EMBODIMENT_TAG,
        "provenance": {"kind": "user_trained", "checkpoint": "/training/my-run/checkpoint-4", "dataset": "/my-data"},
        "inference_files": names,
    }
    (root / "pgfr_checkpoint.json").write_text(json.dumps(metadata), encoding="utf-8")
    (root / "SHA256SUMS").write_text("".join(
        f"{checkpoint_helpers.digest_file(root / name)}  {name}\n"
        for name in sorted([*names, "pgfr_checkpoint.json"])
    ), encoding="ascii")
    return root


class LocalCheckpointTests(unittest.TestCase):
    def test_export_accepts_trainer_shards_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = checkpoint_fixture(root / "checkpoint-4", sharded=True)
            dataset = root / "data"
            dataset.mkdir()
            output = root / "export"
            result = subprocess.run([
                sys.executable, str(REPO / "ops/export-groot-checkpoint.py"),
                "--checkpoint", str(source), "--output-dir", str(output),
                "--model-label", "my-checkpoint", "--dataset-path", str(dataset),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            identity = checkpoint_helpers.verify_checkpoint(output)
            self.assertEqual(identity["model_label"], "my-checkpoint")
            self.assertEqual(identity["provenance"]["dataset"], str(dataset))
            self.assertEqual(identity["checkpoint_fingerprint"], hashlib.sha256((output / "SHA256SUMS").read_bytes()).hexdigest())
            self.assertEqual(checkpoint_helpers.verify_checkpoint(source)["model_label"], "user-trained-test")

    def test_metadata_transfer_requires_no_weights(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            export = checkpoint_fixture(root / "export")
            identity_dir = root / "identity"
            identity_dir.mkdir()
            for name in ("pgfr_checkpoint.json", "SHA256SUMS"):
                shutil.copyfile(export / name, identity_dir / name)
            self.assertEqual(checkpoint_helpers.read_identity(identity_dir / "pgfr_checkpoint.json"), checkpoint_helpers.verify_checkpoint(export))
            with self.assertRaises(ValueError):
                checkpoint_helpers.verify_checkpoint(identity_dir)

    def test_verifier_rejects_changed_weights_and_metadata(self) -> None:
        for name in ("model.safetensors", "pgfr_checkpoint.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = checkpoint_fixture(Path(directory) / "export")
                if name.endswith(".json"):
                    payload = json.loads((root / name).read_text())
                    payload["model_label"] = "different-checkpoint"
                    (root / name).write_text(json.dumps(payload))
                else:
                    (root / name).write_bytes(b"changed weights")
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    checkpoint_helpers.verify_checkpoint(root)

    def test_verifier_rejects_incomplete_duplicate_and_unsafe_checksums(self) -> None:
        for mutation in ("missing", "duplicate", "traversal"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = checkpoint_fixture(Path(directory) / "export")
                sums = root / "SHA256SUMS"
                lines = sums.read_text().splitlines(keepends=True)
                if mutation == "missing":
                    sums.write_text("".join(lines[1:]))
                elif mutation == "duplicate":
                    sums.write_text("".join([*lines, lines[0]]))
                else:
                    sums.write_text("".join(lines) + "0" * 64 + "  ../outside\n")
                with self.assertRaises(ValueError):
                    checkpoint_helpers.verify_checkpoint(root)

    def test_verifier_rejects_symlink_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = checkpoint_fixture(Path(directory) / "export")
            target = Path(directory) / "weights"
            (root / "model.safetensors").rename(target)
            (root / "model.safetensors").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                checkpoint_helpers.verify_checkpoint(root)

    def test_policy_start_rejects_another_valid_checkpoint_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = checkpoint_fixture(Path(directory) / "export")
            result = subprocess.run(["bash", str(REPO / "ops/verify-groot-models.sh"), str(root), "0" * 64], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("installed serving identity", result.stderr)

    def test_fetch_without_checkpoint_stops_before_network(self) -> None:
        import os
        environment = {**os.environ, "PGFR_GROOT_MODEL_ROOT": "", "PGFR_HF_BIN": "/missing/hf"}
        result = subprocess.run(["bash", str(REPO / "ops/fetch-groot-models.sh")], env=environment, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("supply your local checkpoint export path", result.stderr)


class PublicRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.checkpoint = checkpoint_fixture(Path(temporary.name) / "export")

    def test_deployment_manifest_requires_a_user_checkpoint_for_two_instances(self) -> None:
        manifest = DEPLOYMENT_MANIFEST.read_text(encoding="utf-8")
        for value in (
            "status: user_checkpoint_required",
            "source_revision: e5749287857afd97b78f1147166137de29746392",
            "source: locally_trained_by_user",
            "metadata: pgfr_checkpoint.json",
            "fingerprint: sha256_of_sha256sums_bytes",
            "franka_left:",
            "policy_port: 5592",
            "relay_port: 5641",
            "franka_right:",
            "policy_port: 5593",
            "relay_port: 5642",
            "native_droid_relay_batch2.py",
            "pgfr_groot_certified_deployment_v36.py",
        ):
            self.assertIn(value, manifest)
        self.assertNotIn("canonical_specialists", manifest)
        self.assertNotIn("external-artifacts-not-yet-packaged", manifest)

    def test_python_sources_compile_without_source_wrappers(self) -> None:
        for path in PYTHON_SOURCES:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
            lowered = source.lower()
            if path.is_relative_to(RUNTIME):
                for forbidden in ("sha256", "checksum", "hashlib"):
                    self.assertNotIn(forbidden, lowered, f"{path}: {forbidden}")
            self.assertNotIn("_source.replace", source, str(path))

    def test_thor_installer_freezes_lock_and_requires_pinned_torchcodec(self) -> None:
        source = THOR_INSTALLER.read_text(encoding="utf-8")
        expected = (
            "libavfilter9",
            "libavformat60",
            "libavcodec60",
            "libavutil58",
            "libswresample4",
            "libswscale7",
        )
        package_block = source.split("TORCHCODEC_FFMPEG6_RUNTIME=(", 1)[1].split("\n)", 1)[0]
        configured = tuple(
            line.strip() for line in package_block.splitlines() if line.strip()
        )
        self.assertEqual(configured, expected)
        self.assertIn('--extra dev --frozen', source)
        self.assertIn('"${TORCHCODEC_FFMPEG6_RUNTIME[@]}"', source)
        self.assertNotIn('ffmpeg "${TORCHCODEC_FFMPEG6_RUNTIME[@]}"', source)
        self.assertIn('UV_VERSION="0.11.32"', source)
        self.assertIn(
            'UV_INSTALLER_SHA256="43aff33a967fe40e8c17949d8c85c65bc43f3b5c94742393c957f56ab5ba80f4"',
            source,
        )
        self.assertIn('https://astral.sh/uv/$UV_VERSION/install.sh', source)
        self.assertIn("sha256sum --check --strict", source)
        self.assertIn('"uv $UV_VERSION"*', source)
        self.assertNotIn("https://astral.sh/uv/install.sh | sh", source)
        self.assertIn(
            'TORCHCODEC_WHEEL_SHA256="1421de7e6248cc33398c16b2d7ba5ada4bf5c2a38af7cc44a003f3b0c36eb314"',
            source,
        )
        self.assertIn("zipfile.is_zipfile", source)
        self.assertIn("torchcodec wheel is still a Git LFS pointer", source)
        self.assertIn(
            'TORCHCODEC_WHEEL_NAME="torchcodec-0.10.0a0-cp312-cp312-linux_aarch64.whl"',
            source,
        )
        self.assertIn("exactly one validated Thor torchcodec wheel is required", source)
        self.assertNotIn("DOCKER_CONTAINER", source)
        self.assertNotIn("git clone", source)
        self.assertNotIn("/tmp/torchcodec", source)
        self.assertNotIn("libavdevice-dev", source)
        self.assertIn(
            "Python 3.12 is required for the validated Thor cp312 artifacts",
            source,
        )
        self.assertNotIn("WARNING: Expected Python 3.12", source)
        self.assertLess(
            source.index('if [ "$PYTHON_VERSION" != "3.12" ]'),
            source.index("if ! ldconfig -p"),
        )
        self.assertLess(
            source.index("torchcodec wheel is still a Git LFS pointer"),
            source.index("if ! ldconfig -p"),
        )
        thor_project = (GROOT / "thor" / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        thor_lock = (GROOT / "thor" / "uv.lock").read_text(encoding="utf-8")
        self.assertIn("TorchCodec is intentionally a post-sync overlay", thor_project)
        self.assertNotIn('"torchcodec', thor_project)
        self.assertNotIn('name = "torchcodec"', thor_lock)

    def test_runtime_preparation_materializes_wheel_before_publication(self) -> None:
        source = PREPARE_GROOT_RUNTIME.read_text(encoding="utf-8")

        self.assertIn("git lfs version", source)
        self.assertIn(
            'TORCHCODEC_WHEEL_RELATIVE="scripts/deployment/thor/wheels/'
            'torchcodec-0.10.0a0-cp312-cp312-linux_aarch64.whl"',
            source,
        )
        self.assertIn('lfs pull --include="$TORCHCODEC_WHEEL_RELATIVE"', source)
        self.assertIn("zipfile.is_zipfile", source)
        self.assertIn(
            'TORCHCODEC_WHEEL_SHA256="1421de7e6248cc33398c16b2d7ba5ada4bf5c2a38af7cc44a003f3b0c36eb314"',
            source,
        )
        self.assertLess(source.index("lfs pull"), source.index('mv -T "$tmp" "$DEST"'))
        self.assertIn("flock -n 9", source)
        self.assertIn('mv -T "$tmp" "$DEST"', source)
        self.assertLess(
            source.index("flock -n 9"),
            source.index('[ ! -e "$DEST" ]'),
        )

        self.assertFalse(THOR_DOCKERFILE.exists())
        self.assertIn('rm -f -- "$tmp/scripts/deployment/thor/Dockerfile"', source)
        self.assertIn('for name in install_deps.sh pyproject.toml uv.lock; do', source)

    def test_thor_lock_keeps_binary_runtimes_on_attested_nvidia_wheels(
        self,
    ) -> None:
        lock = tomllib.loads((GROOT / "thor" / "uv.lock").read_text(encoding="utf-8"))
        packages = {package["name"]: package for package in lock["package"]}
        nvidia_packages = (
            "cuda-toolkit",
            "nvidia-cublas",
            "nvidia-cudnn-cu13",
            "nvidia-cudss-cu13",
            "tensorrt",
            "tensorrt-cu13",
            "tensorrt-cu13-bindings",
            "tensorrt-cu13-libs",
        )
        for name in nvidia_packages:
            package = packages[name]
            self.assertEqual(
                package["source"]["registry"],
                "https://pypi.nvidia.com/",
                name,
            )
            artifacts = [*package.get("wheels", [])]
            if "sdist" in package:
                artifacts.append(package["sdist"])
            self.assertTrue(artifacts, name)
            self.assertTrue(
                all(item["url"].startswith("https://pypi.nvidia.com/") for item in artifacts),
                name,
            )

        for name in ("tensorrt-cu13-bindings", "tensorrt-cu13-libs"):
            self.assertNotIn("sdist", packages[name], name)
            self.assertTrue(packages[name].get("wheels"), name)
        tensorrt_libs = packages["tensorrt-cu13-libs"]["wheels"]
        self.assertTrue(
            any(
                "manylinux_2_35_aarch64.whl" in wheel["url"]
                and wheel["hash"]
                == "sha256:f2f6fdaba477ef5536e9932d7f0ce2952ab3c87c5d0fbf93f080388390cba1de"
                for wheel in tensorrt_libs
            )
        )
        self.assertNotIn(
            "sha256:d07fe8b65ce7edb94e805d0b6e9653afe742610b7d5e1b270c918bc9e58a36b1",
            (GROOT / "thor" / "uv.lock").read_text(encoding="utf-8"),
        )

    def test_v36_home_contract(self) -> None:
        source = PYTHON_SOURCES[0].read_text(encoding="utf-8")
        for field, value in (
            ("groot_home_convergence_tolerance", "0.030"),
            ("groot_home_min_ticks", "120"),
            ("groot_home_settle_ticks", "12"),
            ("groot_home_timeout_ticks", "600"),
        ):
            self.assertIn(field, source)
            self.assertIn(value, source)
        self.assertIn("raw_requery_margin_max=0.040", source)
        self.assertIn("raw_requery_limit_max=6", source)
        self.assertIn("GROOT_TARGET_TRACKING_ABORT", source)
        self.assertIn(
            "arm target-state error exceeded the configured limit", source
        )

    def test_two_arm_and_mixed_contracts(self) -> None:
        loader = PYTHON_SOURCES[1].read_text(encoding="utf-8")
        concurrent = PYTHON_SOURCES[3].read_text(encoding="utf-8")
        self.assertEqual(loader.count("compile(_executor_source"), 3)
        self.assertIn("/wrist_right_cam/image_raw", loader)
        self.assertIn("/outside_right_cam/image_raw", loader)
        self.assertEqual(concurrent.count("inference_seed_by_arm"), 2)
        self.assertIn("independent-b1-per-arm-v1", concurrent)
        self.assertIn("_PGFR_GROOT_CONCURRENT_MIXED_READY", concurrent)

    def test_dual_loader_task_gate_allows_only_idle_or_reset(self) -> None:
        loader_path = PYTHON_SOURCES[1]
        loader_source = loader_path.read_text(encoding="utf-8")
        loader_tree = ast.parse(loader_source, filename=str(loader_path))
        helper = next(
            node
            for node in loader_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_pgfr_groot_install_task_allowed"
        )
        helper_module = ast.Module(body=[helper], type_ignores=[])
        ast.fix_missing_locations(helper_module)
        namespace: dict[str, object] = {}
        exec(compile(helper_module, str(loader_path), "exec"), namespace)
        allowed = namespace["_pgfr_groot_install_task_allowed"]

        self.assertTrue(allowed(None))
        self.assertTrue(allowed({"action": "reset_scene"}))
        for task in (
            {},
            {"action": "move"},
            {"action": "move_pair"},
            {"action": "pick_and_place"},
            {"action": "haul"},
            "reset_scene",
        ):
            with self.subTest(task=task):
                self.assertFalse(allowed(task))

    def test_reset_restores_complete_runtime(self) -> None:
        reset = PYTHON_SOURCES[4].read_text(encoding="utf-8")
        for runtime_file in (
            "follow_groot_dual_physical_v36.py",
            "pgfr_groot_certified_deployment_v36.py",
            "pgfr_groot_dual_concurrent_mixed.py",
        ):
            self.assertEqual(reset.count(runtime_file), 1)
        self.assertEqual(reset.count("_shared_executor_requested = True"), 1)
        self.assertIn("PGFR_GROOT_RUNTIME_READY", reset)
        self.assertIn("table-camera contract restore failed", reset)

    def test_renderer_writes_only_two_contracts(self) -> None:
        checkpoint = "/models/my-checkpoint"
        left_state = "/scripts/runtime/gr00t-left.json"
        right_state = "/scripts/runtime/gr00t-right.json"
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(
                (
                    sys.executable,
                    str(RENDERER),
                    "--checkpoint-path",
                    checkpoint,
                    "--checkpoint-metadata",
                    str(self.checkpoint / "pgfr_checkpoint.json"),
                    "--left-service-state",
                    left_state,
                    "--right-service-state",
                    right_state,
                    "--output-dir",
                    directory,
                ),
                check=True,
                capture_output=True,
                text=True,
            )
            output = Path(directory)
            names = sorted(path.name for path in output.iterdir())
            self.assertEqual(
                names,
                [
                    "groot_shared_concurrent_policy_contract.json",
                    "groot_shared_policy_contract.json",
                ],
            )
            serial = json.loads(
                (output / "groot_shared_policy_contract.json").read_text()
            )
            concurrent = json.loads(
                (
                    output / "groot_shared_concurrent_policy_contract.json"
                ).read_text()
            )
            self.assertEqual(serial["checkpoint"], checkpoint)
            identity = checkpoint_helpers.verify_checkpoint(self.checkpoint)
            self.assertEqual(serial["checkpoint_fingerprint"], identity["checkpoint_fingerprint"])
            self.assertEqual(concurrent["model_label"], identity["model_label"])
            self.assertEqual(serial["service_state_path"], left_state)
            self.assertEqual(serial["server_port"], 5592)
            self.assertEqual(serial["relay_port"], 5641)
            self.assertEqual(concurrent["relays"]["franka_left"]["server_port"], 5592)
            self.assertEqual(concurrent["relays"]["franka_left"]["relay_port"], 5641)
            self.assertEqual(concurrent["relays"]["franka_right"]["server_port"], 5593)
            self.assertEqual(concurrent["relays"]["franka_right"]["relay_port"], 5642)
            for path in output.iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_renderer_accepts_custom_ports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(
                (
                    sys.executable,
                    str(RENDERER),
                    "--checkpoint-path",
                    "/models/my-checkpoint",
                    "--checkpoint-metadata",
                    str(self.checkpoint / "pgfr_checkpoint.json"),
                    "--left-service-state",
                    "/scripts/runtime/gr00t-left.json",
                    "--right-service-state",
                    "/scripts/runtime/gr00t-right.json",
                    "--left-policy-port",
                    "6101",
                    "--right-policy-port",
                    "6102",
                    "--left-relay-port",
                    "6201",
                    "--right-relay-port",
                    "6202",
                    "--output-dir",
                    directory,
                ),
                check=True,
                capture_output=True,
                text=True,
            )
            output = Path(directory)
            serial = json.loads(
                (output / "groot_shared_policy_contract.json").read_text()
            )
            concurrent = json.loads(
                (
                    output / "groot_shared_concurrent_policy_contract.json"
                ).read_text()
            )
            self.assertEqual(serial["server_port"], 6101)
            self.assertEqual(serial["relay_port"], 6201)
            self.assertEqual(concurrent["relays"]["franka_left"]["server_port"], 6101)
            self.assertEqual(concurrent["relays"]["franka_left"]["relay_port"], 6201)
            self.assertEqual(concurrent["relays"]["franka_right"]["server_port"], 6102)
            self.assertEqual(concurrent["relays"]["franka_right"]["relay_port"], 6202)

    def test_serving_health_uses_contracted_shared_relay_ports(self) -> None:
        source = SERVING_HEALTH.read_text(encoding="utf-8")
        for legacy in (
            "red1000",
            "blue1000",
            "green1000",
            "green_corrective200",
            "5681",
            "5682",
            "5683",
            "5685",
        ):
            self.assertNotIn(legacy, source)

        with tempfile.TemporaryDirectory() as directory:
            contract = Path(directory) / "concurrent.json"
            contract.write_text(
                json.dumps(
                    {
                        "relays": {
                            "franka_left": {
                                "server_port": 6101,
                                "relay_port": 6201,
                            },
                            "franka_right": {
                                "server_port": 6102,
                                "relay_port": 6202,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            calls = []

            def original_floor_state():
                calls.append(True)
                return {"scene": "ready"}

            legacy_cache = {"legacy": True}
            namespace = {
                "floor_state": original_floor_state,
                "_PGFR_SERVING_CONTRACT_PATH": str(contract),
                "_PGFR_SERVING_CACHE": (
                    "thor-relay-listeners-v3-four-published-experts",
                    float("inf"),
                    legacy_cache,
                ),
            }
            compiled = compile(source, str(SERVING_HEALTH), "exec")
            exec(compiled, namespace)
            self.assertIs(namespace["_PGFR_FS_ORIG"], original_floor_state)
            namespace["_pgfr_tcp_listeners"] = lambda: {6201, 6202}
            healthy = namespace["floor_state"]()["groot_serving"]
            self.assertIsNot(healthy, legacy_cache)
            self.assertEqual(healthy["ports_open"], 2)
            self.assertEqual(healthy["ports_total"], 2)
            self.assertFalse(healthy["degraded"])
            self.assertEqual(healthy["transport"], "thor-loopback-via-ssh")
            self.assertEqual(
                healthy["services"],
                {
                    "franka_left": {"port": 6201, "listening": True},
                    "franka_right": {"port": 6202, "listening": True},
                },
            )

            namespace["_PGFR_SERVING_CACHE"] = None
            namespace["_pgfr_tcp_listeners"] = lambda: {6201}
            degraded = namespace["floor_state"]()["groot_serving"]
            self.assertEqual(degraded["ports_open"], 1)
            self.assertEqual(degraded["ports_total"], 2)
            self.assertTrue(degraded["degraded"])

            exec(compiled, namespace)
            self.assertIs(namespace["_PGFR_FS_ORIG"], original_floor_state)
            calls_before = len(calls)
            self.assertIn("groot_serving", namespace["floor_state"]())
            self.assertEqual(len(calls), calls_before + 1)

    def test_serving_health_rejects_malformed_contracts(self) -> None:
        source = SERVING_HEALTH.read_text(encoding="utf-8")
        compiled = compile(source, str(SERVING_HEALTH), "exec")
        malformed_contracts = (
            {},
            {"relays": {"franka_left": {"relay_port": 6201}}},
            {
                "relays": {
                    "franka_left": {"relay_port": 6201},
                    "franka_right": {"relay_port": 6201},
                }
            },
            {
                "relays": {
                    "franka_left": {"relay_port": True},
                    "franka_right": {"relay_port": 6202},
                }
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            contract = Path(directory) / "concurrent.json"
            for payload in malformed_contracts:
                with self.subTest(payload=payload):
                    contract.write_text(json.dumps(payload), encoding="utf-8")
                    namespace = {
                        "floor_state": lambda: {},
                        "_PGFR_SERVING_CONTRACT_PATH": str(contract),
                    }
                    with self.assertRaises(RuntimeError):
                        exec(compiled, namespace)

            missing = Path(directory) / "missing.json"
            with self.assertRaisesRegex(RuntimeError, "failed to load"):
                exec(
                    compiled,
                    {
                        "floor_state": lambda: {},
                        "_PGFR_SERVING_CONTRACT_PATH": str(missing),
                    },
                )

    def test_renderer_rejects_invalid_and_colliding_ports(self) -> None:
        common = (
            sys.executable,
            str(RENDERER),
            "--checkpoint-path",
            "/models/my-checkpoint",
            "--left-service-state",
            "/scripts/runtime/gr00t-left.json",
            "--right-service-state",
            "/scripts/runtime/gr00t-right.json",
        )
        with tempfile.TemporaryDirectory() as directory:
            invalid = subprocess.run(
                (*common, "--left-policy-port", "0", "--output-dir", directory),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("port must be between 1 and 65535", invalid.stderr)

        with tempfile.TemporaryDirectory() as directory:
            collision = subprocess.run(
                (
                    *common,
                    "--left-policy-port",
                    "6101",
                    "--right-policy-port",
                    "6101",
                    "--left-relay-port",
                    "6201",
                    "--right-relay-port",
                    "6202",
                    "--output-dir",
                    directory,
                ),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(collision.returncode, 0)
            self.assertIn("policy and relay ports must be distinct", collision.stderr)

    def test_installer_and_launcher_are_fail_closed(self) -> None:
        subprocess.run(("bash", "-n", str(INSTALLER)), check=True)
        subprocess.run(("bash", "-n", str(LAUNCHER)), check=True)
        installer = INSTALLER.read_text(encoding="utf-8")
        launcher = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("is active; this installer never replaces", installer)
        self.assertIn("render-groot-cont24-contracts.py", installer)
        for option in (
            "--left-policy-port",
            "--right-policy-port",
            "--left-relay-port",
            "--right-relay-port",
        ):
            self.assertIn(option, installer)
        self.assertIn(
            "reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/deployment", installer
        )
        self.assertIn("reference/policy-gated-factory-robot-orchestrator-reference/groot/capture_context", installer)
        self.assertIn(
            '"$RUNTIME/native_droid_work/pgfr_sync_capture_cell.py"', installer
        )
        self.assertIn("startup.py cmd.py our_factory.usda", installer)
        self.assertIn("pgfr_shape_mode.py production_contract_expected.json", installer)
        self.assertNotIn("isaac_executor", installer)
        shape_mode = (ISAAC_DEPLOYMENT / "pgfr_shape_mode.py").read_text(
            encoding="utf-8"
        )
        bootstrap = (ISAAC_DEPLOYMENT / "full_scene_bootstrap.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('SHAPE_TASK_NOUN = {"red": "cube"', shape_mode)
        self.assertIn('"blue": "cylinder"', shape_mode)
        self.assertIn('"green": "brick"', shape_mode)
        self.assertIn("groot_three_object", bootstrap)
        self.assertEqual(len(tuple(CAPTURE_CONTEXT.rglob("states.json"))), 18)
        self.assertNotIn("sha256sum", installer)
        self.assertIn("PGFR_GROOT_POLICY_ROUTE=shared", launcher)
        self.assertIn('GROOT_STATE_ROOT="${PGFR_GROOT_STATE_ROOT:-', launcher)
        self.assertIn('-v "$GROOT_STATE_ROOT:/groot-state:ro"', launcher)
        self.assertIn("remove it explicitly before launch", launcher)

    def test_persistent_two_instance_service_templates(self) -> None:
        self.assertEqual(
            sorted(path.name for path in GROOT_SYSTEMD.iterdir()),
            [
                "pgfr-groot-policy@.service",
                "pgfr-groot-relay@.service",
                "pgfr-groot-shared-stack.target",
                "shared-left.env",
                "shared-right.env",
            ],
        )
        expected = {
            "shared-left.env": ("5592", "5641", "shared-left.json"),
            "shared-right.env": ("5593", "5642", "shared-right.json"),
        }
        for name, (policy_port, relay_port, state_name) in expected.items():
            environment = (GROOT_SYSTEMD / name).read_text(encoding="utf-8")
            self.assertIn(
                'MODEL_PATH="__PGFR_CHECKPOINT_PATH__"',
                environment,
            )
            self.assertIn(f"POLICY_PORT={policy_port}", environment)
            self.assertIn(f"PGFR_RELAY_PORT={relay_port}", environment)
            self.assertIn("PGFR_BATCH_WINDOW_MS=0", environment)
            self.assertIn(f"PGFR_SERVICE_STATE_PATH=__PGFR_HOME__/.local/share/pgfr-spine/groot/{state_name}", environment)
            self.assertIn("native_droid_relay_batch2.py", environment)
        policy_unit = (GROOT_SYSTEMD / "pgfr-groot-policy@.service").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "HF_HOME=__PGFR_HOME__/policy-gated-factory-robot-orchestrator-reference-models/hf-home", policy_unit
        )
        self.assertIn(
            "HF_TOKEN_PATH=__PGFR_HOME__/policy-gated-factory-robot-orchestrator-reference-models/hf-home/token",
            policy_unit,
        )
        self.assertNotIn("groot_shadow/hf-home", policy_unit)
        target = (GROOT_SYSTEMD / "pgfr-groot-shared-stack.target").read_text(
            encoding="utf-8"
        )
        for instance in ("shared-left", "shared-right"):
            self.assertIn(f"pgfr-groot-policy@{instance}.service", target)
            self.assertIn(f"pgfr-groot-relay@{instance}.service", target)


if __name__ == "__main__":
    unittest.main()
