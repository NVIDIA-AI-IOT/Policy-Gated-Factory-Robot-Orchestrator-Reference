# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free tests for the simulation-host GR00T bridge."""

from __future__ import annotations

import importlib.util
import json
import os
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
    / "ic-groot-two-host-bridge.service"
)

SPEC = importlib.util.spec_from_file_location("groot_two_host_bridge", BRIDGE_PATH)
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)


class TwoHostBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = {
            "IC_GROOT_THOR_SSH": "jetson@thor.example",
            "IC_GROOT_REMOTE_CHECKPOINT": "/models/order744-cont24",
            "IC_GROOT_REMOTE_STATE_ROOT": "/home/jetson/.local/share/ic-spine/groot",
            "IC_GROOT_LOCAL_STATE_ROOT": str(self.root),
            "IC_GROOT_REMOTE_LEFT_POLICY_PORT": "5592",
            "IC_GROOT_REMOTE_RIGHT_POLICY_PORT": "5593",
            "IC_GROOT_REMOTE_LEFT_RELAY_PORT": "5641",
            "IC_GROOT_REMOTE_RIGHT_RELAY_PORT": "5642",
            "IC_GROOT_LOCAL_LEFT_POLICY_PORT": "5792",
            "IC_GROOT_LOCAL_RIGHT_POLICY_PORT": "5793",
            "IC_GROOT_LOCAL_LEFT_RELAY_PORT": "5741",
            "IC_GROOT_LOCAL_RIGHT_RELAY_PORT": "5742",
            "IC_GROOT_BRIDGE_POLL_SECONDS": "5",
        }
        self.config = bridge.load_config(self.environment)

    def remote_state(self, arm) -> dict[str, object]:
        return {
            "schema_version": 1,
            "status": "ready",
            "model_label": bridge.MODEL_LABEL,
            "checkpoint": self.config.remote_checkpoint,
            "checkpoint_fingerprint": bridge.CHECKPOINT_FINGERPRINT,
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
                state["checkpoint_fingerprint"], bridge.CHECKPOINT_FINGERPRINT
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
        environment["IC_GROOT_LOCAL_RIGHT_POLICY_PORT"] = "5792"
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
            "ReadWritePaths=%h/.local/share/ic-spine/groot/remote-thor-v36",
        ):
            self.assertIn(contract, unit)
        for unsupported_user_capability_contract in (
            "PrivateDevices=yes",
            "ProtectKernelModules=yes",
        ):
            self.assertNotIn(unsupported_user_capability_contract, unit)

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
            "ic-groot-policy@.service",
            "ic-groot-relay@.service",
            "ic-groot-shared-stack.target",
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
        policy_unit = systemd / "ic-groot-policy@.service"
        relay_unit = systemd / "ic-groot-relay@.service"
        policy_source = (
            "[Service]\n"
            f"WorkingDirectory={home}/groot_shadow/Isaac-GR00T\n"
            f"EnvironmentFile={home}/.config/ic-spine/groot/%i.env\n"
            f"ExecStart={home}/groot_shadow/Isaac-GR00T/.venv/bin/python "
            "gr00t/eval/run_gr00t_server.py --host 127.0.0.1 "
            "--port ${POLICY_PORT} --model-path ${MODEL_PATH}\n"
            "Restart=on-failure\n"
        )
        relay_source = (
            "[Service]\n"
            f"WorkingDirectory={home}/groot_shadow/Isaac-GR00T\n"
            f"EnvironmentFile={home}/.config/ic-spine/groot/%i.env\n"
            "Environment=IC_RELAY_HOST=127.0.0.1\n"
            "Environment=IC_POLICY_HOST=127.0.0.1\n"
            f"ExecStart={home}/groot_shadow/Isaac-GR00T/.venv/bin/python "
            "${RELAY_SCRIPT}\n"
            "Restart=on-failure\n"
        )
        policy_unit.write_text(policy_source, encoding="utf-8")
        relay_unit.write_text(relay_source, encoding="utf-8")

        model = home / "policy-gated-factory-robot-orchestrator-reference-models" / "order744-cont24"
        model.mkdir(parents=True)
        model_files = (
            "config.json",
            "embodiment_id.json",
            "model-00001-of-00003.safetensors",
            "model-00002-of-00003.safetensors",
            "model-00003-of-00003.safetensors",
            "model.safetensors.index.json",
            "processor_config.json",
            "statistics.json",
        )
        empty_sha256 = (
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        )
        for name in model_files:
            (model / name).write_bytes(b"")
        (model / "SHA256SUMS").write_text(
            "".join(f"{empty_sha256}  {name}\n" for name in model_files),
            encoding="utf-8",
        )

        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        systemctl_log = self.root / "systemctl.log"
        fake_systemctl = fake_bin / "systemctl"
        fake_systemctl.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >>\"$FAKE_SYSTEMCTL_LOG\"\n"
            "case \"$*\" in\n"
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
            "cat >/dev/null\n"
            "printf '%s\\n' \"$*\" >>\"$FAKE_PORT_PROBE_LOG\"\n",
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
                ("bash", str(THOR_INSTALLER_PATH)),
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
                "ic-groot-policy@.service",
                "ic-groot-relay@.service",
                "ic-groot-shared-stack.target",
            ],
        )
        groot_env = config / "ic-spine" / "groot"
        self.assertEqual(
            sorted(path.name for path in groot_env.iterdir()),
            ["shared-left.env", "shared-right.env"],
        )
        self.assertEqual(
            (systemd / "ic-groot-shared-stack.target").stat().st_mode & 0o777,
            0o644,
        )
        for name in ("shared-left.env", "shared-right.env"):
            self.assertEqual((groot_env / name).stat().st_mode & 0o777, 0o600)
        calls = systemctl_log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(calls)
        self.assertTrue(all(" start " not in f" {call} " for call in calls))
        self.assertTrue(all(" enable " not in f" {call} " for call in calls))
        self.assertEqual(calls.count("--user daemon-reload"), 2)
        self.assertEqual(
            port_probe_log.read_text(encoding="utf-8").splitlines(),
            ["- 5592 5593 5641 5642", "- 5592 5593 5641 5642"],
        )


if __name__ == "__main__":
    unittest.main()
