# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free tests for the simulation-host GR00T bridge."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[4]
BRIDGE_PATH = ROOT / "ops" / "groot-two-host-bridge.py"
INSTALLER_PATH = ROOT / "ops" / "install-groot-two-host-bridge.sh"
THOR_INSTALLER_PATH = ROOT / "ops" / "install-groot-thor-shared-profiles.sh"
UNIT_PATH = (
    ROOT
    / "ops"
    / "systemd"
    / "simulation-host"
    / "pgfr-groot-two-host-bridge.service"
)

SPEC = importlib.util.spec_from_file_location("groot_two_host_bridge", BRIDGE_PATH)
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)


def write_checkpoint(root: Path, *, include_weights: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "config.json": b'{"architectures": ["Gr00tN1d7"]}\n',
        "embodiment_id.json": b'{"OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT": 0}\n',
        "processor_config.json": b'{"processor_class": "Gr00tProcessor"}\n',
        "statistics.json": b'{"state": {"mean": [0.0]}}\n',
        "model.safetensors": b"fixture model weights\n",
    }
    metadata = {
        "schema_version": 1,
        "model_label": "user_trained_fixture_v1",
        "embodiment_tag": "OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT",
        "provenance": {
            "kind": "user_trained",
            "checkpoint": "/training/checkpoint-1000",
            "dataset": "/datasets/my-demonstrations",
        },
        "inference_files": sorted(artifacts),
    }
    artifacts["pgfr_checkpoint.json"] = (json.dumps(metadata, sort_keys=True) + "\n").encode()
    for name, payload in artifacts.items():
        if include_weights or name == "pgfr_checkpoint.json":
            (root / name).write_bytes(payload)
    (root / "SHA256SUMS").write_text(
        "".join(f"{hashlib.sha256(payload).hexdigest()}  {name}\n" for name, payload in sorted(artifacts.items())),
        encoding="ascii",
    )
    return root / "pgfr_checkpoint.json"


class TwoHostBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.metadata_path = write_checkpoint(self.root / "identity", include_weights=False)
        self.environment = {
            "PGFR_GROOT_THOR_SSH": "jetson@thor.example",
            "PGFR_GROOT_REMOTE_CHECKPOINT": "/models/my-trained-policy",
            "PGFR_GROOT_CHECKPOINT_METADATA": str(self.metadata_path),
            "PGFR_GROOT_REMOTE_STATE_ROOT": "/home/jetson/.local/share/pgfr-spine/groot",
            "PGFR_GROOT_LOCAL_STATE_ROOT": str(self.root),
            "PGFR_GROOT_REMOTE_LEFT_POLICY_PORT": "5592",
            "PGFR_GROOT_REMOTE_RIGHT_POLICY_PORT": "5593",
            "PGFR_GROOT_REMOTE_LEFT_RELAY_PORT": "5641",
            "PGFR_GROOT_REMOTE_RIGHT_RELAY_PORT": "5642",
            "PGFR_GROOT_LOCAL_LEFT_POLICY_PORT": "5792",
            "PGFR_GROOT_LOCAL_RIGHT_POLICY_PORT": "5793",
            "PGFR_GROOT_LOCAL_LEFT_RELAY_PORT": "5741",
            "PGFR_GROOT_LOCAL_RIGHT_RELAY_PORT": "5742",
            "PGFR_GROOT_BRIDGE_POLL_SECONDS": "5",
        }
        self.config = bridge.load_config(self.environment)

    def remote_state(self, arm) -> dict[str, object]:
        return {
            "schema_version": 1,
            "status": "ready",
            "model_label": self.config.model_label,
            "checkpoint": self.config.remote_checkpoint,
            "checkpoint_fingerprint": self.config.checkpoint_fingerprint,
            "server_host": "127.0.0.1",
            "server_port": arm.remote_policy_port,
            "relay_host": "127.0.0.1",
            "relay_port": arm.remote_relay_port,
            "relay_contract": bridge.RELAY_CONTRACT,
            "relay_pid": 1234,
            "preserve_until_explicit_stop": True,
        }

    def probe(self) -> dict[str, object]:
        return {
            "active": {unit: True for unit in bridge.REMOTE_UNITS},
            "listeners": {
                str(port): True
                for arm in self.config.arms
                for port in (arm.remote_policy_port, arm.remote_relay_port)
            },
            "states": {
                arm.state_name: self.remote_state(arm) for arm in self.config.arms
            },
        }

    def test_metadata_only_identity_defines_the_remote_contract(self) -> None:
        self.assertEqual(self.config.model_label, "user_trained_fixture_v1")
        self.assertEqual(
            self.config.checkpoint_fingerprint,
            hashlib.sha256((self.metadata_path.parent / "SHA256SUMS").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            sorted(path.name for path in self.metadata_path.parent.iterdir()),
            ["SHA256SUMS", "pgfr_checkpoint.json"],
        )

    def test_metadata_is_required_and_tampering_is_rejected(self) -> None:
        environment = dict(self.environment)
        del environment["PGFR_GROOT_CHECKPOINT_METADATA"]
        with self.assertRaisesRegex(bridge.BridgeError, "CHECKPOINT_METADATA.*required"):
            bridge.load_config(environment)
        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        metadata["model_label"] = "changed-after-export"
        self.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        with self.assertRaisesRegex(bridge.BridgeError, "checksum mismatch"):
            bridge.load_config(self.environment)

    def test_missing_manifest_is_rejected(self) -> None:
        (self.metadata_path.parent / "SHA256SUMS").unlink()
        with self.assertRaisesRegex(bridge.BridgeError, "SHA256SUMS"):
            bridge.load_config(self.environment)

    def test_failed_identity_loading_invalidates_stale_readiness(self) -> None:
        for name in bridge.STATE_NAMES:
            (self.root / name).write_text('{"status": "ready"}', encoding="utf-8")
        self.metadata_path.unlink()
        with mock.patch.dict(os.environ, self.environment, clear=True):
            with mock.patch.object(sys, "argv", [str(BRIDGE_PATH)]):
                self.assertEqual(bridge.main(), 1)
        self.assertFalse(any((self.root / name).exists() for name in bridge.STATE_NAMES))

    def test_stop_cleanup_works_without_checkpoint_identity(self) -> None:
        for name in bridge.STATE_NAMES:
            (self.root / name).write_text('{"status": "ready"}', encoding="utf-8")
        with mock.patch.dict(
            os.environ, {"PGFR_GROOT_LOCAL_STATE_ROOT": str(self.root)}, clear=True
        ):
            with mock.patch.object(sys, "argv", [str(BRIDGE_PATH), "--invalidate-states"]):
                self.assertEqual(bridge.main(), 0)
        self.assertFalse(any((self.root / name).exists() for name in bridge.STATE_NAMES))

    def test_tunnel_has_exact_loopback_forwards(self) -> None:
        command = bridge.tunnel_command(self.config)
        self.assertEqual(command[0:3], ["/usr/bin/ssh", "-N", "-T"])
        self.assertEqual(command[-1], "jetson@thor.example")
        forwards = [
            command[index + 1]
            for index, value in enumerate(command)
            if value == "-L"
        ]
        self.assertEqual(
            forwards,
            [
                "127.0.0.1:5792:127.0.0.1:5592",
                "127.0.0.1:5741:127.0.0.1:5641",
                "127.0.0.1:5793:127.0.0.1:5593",
                "127.0.0.1:5742:127.0.0.1:5642",
            ],
        )
        for required in (
            "BatchMode=yes",
            "ExitOnForwardFailure=yes",
            "ControlMaster=no",
        ):
            self.assertIn(required, command)

    def test_valid_probe_rewrites_only_local_endpoints(self) -> None:
        validated = bridge.validate_probe(self.probe(), self.config)
        rewritten = bridge.rewrite_states(validated, self.config)
        for arm in self.config.arms:
            state = rewritten[arm.state_name]
            self.assertEqual(state["checkpoint"], self.config.remote_checkpoint)
            self.assertEqual(
                state["checkpoint_fingerprint"], self.config.checkpoint_fingerprint
            )
            self.assertEqual(state["server_port"], arm.local_policy_port)
            self.assertEqual(state["relay_port"], arm.local_relay_port)
            self.assertEqual(
                state["bridge_remote_server_port"], arm.remote_policy_port
            )
            self.assertEqual(
                state["bridge_remote_relay_port"], arm.remote_relay_port
            )

    def test_wrong_fingerprint_fails_closed(self) -> None:
        probe = self.probe()
        probe["states"]["shared-right.json"]["checkpoint_fingerprint"] = "0" * 64
        with self.assertRaisesRegex(bridge.BridgeError, "fingerprint"):
            bridge.validate_probe(probe, self.config)

    def test_wrong_label_and_path_still_fail_closed(self) -> None:
        for key, value in (("model_label", "unselected-policy"), ("checkpoint", "/models/other")):
            with self.subTest(key=key):
                probe = self.probe()
                probe["states"]["shared-left.json"][key] = value
                with self.assertRaisesRegex(bridge.BridgeError, key):
                    bridge.validate_probe(probe, self.config)

    def test_publish_pair_and_invalidate_pair(self) -> None:
        validated = bridge.validate_probe(self.probe(), self.config)
        states = bridge.rewrite_states(validated, self.config)
        bridge.publish_states(states, self.config)
        for name in bridge.STATE_NAMES:
            path = self.root / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), states[name])
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
        self.assertEqual(list(self.root.glob("*.tmp")), [])
        bridge.invalidate_states(self.config)
        self.assertFalse(any((self.root / name).exists() for name in bridge.STATE_NAMES))

    def test_partial_replace_failure_invalidates_pair(self) -> None:
        validated = bridge.validate_probe(self.probe(), self.config)
        states = bridge.rewrite_states(validated, self.config)
        real_replace = bridge.os.replace

        def fail_right(source, destination):
            if Path(destination).name == "shared-right.json":
                raise OSError("simulated replacement failure")
            return real_replace(source, destination)

        with mock.patch.object(bridge.os, "replace", side_effect=fail_right):
            with self.assertRaisesRegex(OSError, "replacement failure"):
                bridge.publish_states(states, self.config)
        self.assertFalse(any((self.root / name).exists() for name in bridge.STATE_NAMES))
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_config_rejects_local_port_collision(self) -> None:
        environment = dict(self.environment)
        environment["PGFR_GROOT_LOCAL_RIGHT_POLICY_PORT"] = "5792"
        with self.assertRaisesRegex(bridge.BridgeError, "local.*distinct"):
            bridge.load_config(environment)

    def test_installer_and_unit_are_idle_only_and_hardened(self) -> None:
        installer = INSTALLER_PATH.read_text(encoding="utf-8")
        executable_lines = [
            line.strip()
            for line in installer.splitlines()
            if line.strip()
            and not line.lstrip().startswith(("#", "echo"))
        ]
        self.assertFalse(
            any(
                line.startswith(("systemctl --user start", "systemctl --user enable"))
                for line in executable_lines
            )
        )
        self.assertIn("systemctl --user daemon-reload", installer)
        self.assertIn("is-active --quiet", installer)
        unit = UNIT_PATH.read_text(encoding="utf-8")
        for contract in (
            "Restart=on-failure",
            "ExecStopPost=%h/.local/lib/policy-gated-factory-robot-orchestrator-reference/groot-two-host-bridge.py --invalidate-states",
            "TimeoutStopSec=30",
            "NoNewPrivileges=yes",
            "ProtectSystem=strict",
            "ProtectHome=read-only",
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
            "ReadWritePaths=%h/.local/share/pgfr-spine/groot/remote-thor-v36",
        ):
            self.assertIn(contract, unit)
        for unsupported_user_capability_contract in (
            "PrivateDevices=yes",
            "ProtectKernelModules=yes",
        ):
            self.assertNotIn(unsupported_user_capability_contract, unit)

    def test_bridge_installer_snapshots_verified_metadata_without_connecting(self) -> None:
        home = self.root / "bridge-home"
        home.mkdir()
        fake_bin = self.root / "bridge-bin"
        fake_bin.mkdir()
        for name, body in {
            "systemctl": (
                'case "$*" in\n'
                '  *list-units*|*daemon-reload*) exit 0 ;;\n'
                '  *is-active*) exit 3 ;;\n'
                '  *) exit 99 ;;\n'
                'esac\n'
            ),
            "ssh": "exit 99\n",
            "python3": (
                'if [ "$1" = "-" ] && [ "$2" = "5792" ]; then\n'
                "  cat >/dev/null\n"
                "else\n"
                f'  exec "{sys.executable}" "$@"\n'
                "fi\n"
            ),
        }.items():
            command = fake_bin / name
            command.write_text("#!/bin/sh\n" + body, encoding="utf-8")
            command.chmod(0o755)
        environment = {**os.environ, "HOME": str(home), "PATH": f"{fake_bin}:{os.environ['PATH']}"}
        command = [
            "bash", str(INSTALLER_PATH),
            "--thor-ssh", "jetson@thor.example",
            "--remote-checkpoint", "/models/my-trained-policy",
            "--checkpoint-metadata", str(self.metadata_path),
            "--remote-state-root", "/home/jetson/.local/share/pgfr-spine/groot",
        ]
        for _ in range(2):
            result = subprocess.run(command, env=environment, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
        config_root = home / ".config" / "pgfr-spine"
        identity_root = config_root / "groot-bridge-checkpoint"
        for name in ("pgfr_checkpoint.json", "SHA256SUMS"):
            self.assertEqual((identity_root / name).read_bytes(), (self.metadata_path.parent / name).read_bytes())
            self.assertEqual((identity_root / name).stat().st_mode & 0o777, 0o600)
        environment.update(
            line.split("=", 1)
            for line in (config_root / "groot-two-host-bridge.env").read_text(encoding="utf-8").splitlines()
        )
        installed = home / ".local/lib/policy-gated-factory-robot-orchestrator-reference"
        shutil.rmtree(self.metadata_path.parent)
        result = subprocess.run(
            [sys.executable, str(installed / "groot-two-host-bridge.py"), "--check-config"],
            env=environment, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("jetson@thor.example", result.stdout)
        self.assertFalse(any((home / ".local/share/pgfr-spine/groot/remote-thor-v36" / name).exists() for name in bridge.STATE_NAMES))

    def test_cell_installer_uses_metadata_for_remote_checkpoint(self) -> None:
        mount = self.root / "scripts"
        mount.mkdir()
        fake_bin = self.root / "cell-bin"
        fake_bin.mkdir()
        docker = fake_bin / "docker"
        docker.write_text(
            '#!/bin/sh\nif [ "$1" = "ps" ]; then exit 0; fi\nexit 99\n',
            encoding="utf-8",
        )
        docker.chmod(0o755)
        environment = {**os.environ, "HOME": str(self.root), "PATH": f"{fake_bin}:{os.environ['PATH']}"}
        result = subprocess.run(
            [
                "bash", str(ROOT / "ops/install-groot-cell.sh"),
                "--mount", str(mount),
                "--checkpoint-path", self.config.remote_checkpoint,
                "--checkpoint-metadata", str(self.metadata_path),
                "--left-service-state", "/groot-state/shared-left.json",
                "--right-service-state", "/groot-state/shared-right.json",
                "--left-policy-port", "5792", "--right-policy-port", "5793",
                "--left-relay-port", "5741", "--right-relay-port", "5742",
            ],
            env=environment, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("groot_shared_policy_contract.json", "groot_shared_concurrent_policy_contract.json"):
            contract = json.loads((mount / name).read_text(encoding="utf-8"))
            self.assertEqual(contract["checkpoint"], self.config.remote_checkpoint)
            self.assertEqual(contract["model_label"], self.config.model_label)
            self.assertEqual(contract["checkpoint_fingerprint"], self.config.checkpoint_fingerprint)
        concurrent = json.loads((mount / "groot_shared_concurrent_policy_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(concurrent["relays"]["franka_left"]["server_port"], 5792)
        self.assertEqual(concurrent["relays"]["franka_right"]["relay_port"], 5742)

    def test_thor_shared_installer_is_narrow_and_idle_only(self) -> None:
        subprocess.run(("bash", "-n", str(THOR_INSTALLER_PATH)), check=True)
        subprocess.run(
            ("bash", str(THOR_INSTALLER_PATH), "--help"),
            check=True,
            capture_output=True,
            text=True,
        )
        installer = THOR_INSTALLER_PATH.read_text(encoding="utf-8")
        executable_lines = [
            line.strip()
            for line in installer.splitlines()
            if line.strip()
            and not line.lstrip().startswith(("#", "echo"))
        ]
        self.assertFalse(
            any(
                line.startswith(("systemctl --user start", "systemctl --user enable"))
                for line in executable_lines
            )
        )
        self.assertEqual(installer.count('install_missing "$STAGE/'), 3)
        for required in (
            "verify-groot-models.sh",
            "pgfr-groot-policy@.service",
            "pgfr-groot-relay@.service",
            "pgfr-groot-shared-stack.target",
            "shared-left.env",
            "shared-right.env",
            "SHARED_PORTS=(5592 5593 5641 5642)",
            "systemctl --user daemon-reload",
            "existing shared-profile file differs",
        ):
            self.assertIn(required, installer)
        self.assertNotIn("bootstrap-brain", installer)

    def test_thor_shared_installer_operates_only_in_fake_home(self) -> None:
        home = self.root / "home"
        config = home / ".config"
        systemd = config / "systemd" / "user"
        systemd.mkdir(parents=True)
        policy_unit = systemd / "pgfr-groot-policy@.service"
        relay_unit = systemd / "pgfr-groot-relay@.service"
        policy_source = (
            "[Service]\n"
            f"WorkingDirectory={home}/groot_shadow/Isaac-GR00T\n"
            f"EnvironmentFile={home}/.config/pgfr-spine/groot/%i.env\n"
            f"ExecStartPre={ROOT}/ops/verify-groot-models.sh "
            "${MODEL_PATH} ${PGFR_CHECKPOINT_FINGERPRINT}\n"
            f"ExecStart={home}/groot_shadow/Isaac-GR00T/.venv/bin/python "
            "gr00t/eval/run_gr00t_server.py --host 127.0.0.1 "
            "--port ${POLICY_PORT} --model-path ${MODEL_PATH}\n"
            "Restart=on-failure\n"
        )
        relay_source = (
            "[Service]\n"
            f"WorkingDirectory={home}/groot_shadow/Isaac-GR00T\n"
            f"EnvironmentFile={home}/.config/pgfr-spine/groot/%i.env\n"
            "Environment=PGFR_RELAY_HOST=127.0.0.1\n"
            "Environment=PGFR_POLICY_HOST=127.0.0.1\n"
            f"ExecStart={home}/groot_shadow/Isaac-GR00T/.venv/bin/python "
            "${RELAY_SCRIPT}\n"
            "Restart=on-failure\n"
        )
        policy_unit.write_text(policy_source, encoding="utf-8")
        relay_unit.write_text(relay_source, encoding="utf-8")

        model = home / "models" / "my-trained-policy"
        write_checkpoint(model)

        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        systemctl_log = self.root / "systemctl.log"
        fake_systemctl = fake_bin / "systemctl"
        fake_systemctl.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >>\"$FAKE_SYSTEMCTL_LOG\"\n"
            "case \"$*\" in\n"
            "  *list-units*) exit 0 ;;\n"
            "  *is-active*) exit 3 ;;\n"
            "  *daemon-reload*) exit 0 ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_systemctl.chmod(0o755)
        port_probe_log = self.root / "port-probe.log"
        fake_python = fake_bin / "python3"
        fake_python.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "-" ] && [ "$2" = "5592" ]; then\n'
            "  cat >/dev/null\n"
            "  printf '%s\\n' \"$*\" >>\"$FAKE_PORT_PROBE_LOG\"\n"
            "else\n"
            f'  exec "{sys.executable}" "$@"\n'
            "fi\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o755)
        environment = dict(os.environ)
        environment.update(
            {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(config),
                "FAKE_SYSTEMCTL_LOG": str(systemctl_log),
                "FAKE_PORT_PROBE_LOG": str(port_probe_log),
                "PATH": f"{fake_bin}:{environment['PATH']}",
            }
        )
        for _ in range(2):
            subprocess.run(
                ("bash", str(THOR_INSTALLER_PATH), "--checkpoint-path", str(model)),
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )

        self.assertEqual(policy_unit.read_text(encoding="utf-8"), policy_source)
        self.assertEqual(relay_unit.read_text(encoding="utf-8"), relay_source)
        self.assertEqual(
            sorted(path.name for path in systemd.iterdir()),
            [
                "pgfr-groot-policy@.service",
                "pgfr-groot-relay@.service",
                "pgfr-groot-shared-stack.target",
            ],
        )
        groot_env = config / "pgfr-spine" / "groot"
        self.assertEqual(
            sorted(path.name for path in groot_env.iterdir()),
            ["shared-left.env", "shared-right.env"],
        )
        self.assertEqual(
            (systemd / "pgfr-groot-shared-stack.target").stat().st_mode & 0o777,
            0o644,
        )
        for name in ("shared-left.env", "shared-right.env"):
            self.assertEqual((groot_env / name).stat().st_mode & 0o777, 0o600)
        calls = systemctl_log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(calls)
        self.assertTrue(all(" start " not in f" {call} " for call in calls))
        self.assertTrue(all(" enable " not in f" {call} " for call in calls))
        self.assertEqual(sum("list-units" in call for call in calls), 2)
        self.assertEqual(calls.count("--user daemon-reload"), 2)
        self.assertEqual(
            port_probe_log.read_text(encoding="utf-8").splitlines(),
            ["- 5592 5593 5641 5642", "- 5592 5593 5641 5642"],
        )


if __name__ == "__main__":
    unittest.main()
