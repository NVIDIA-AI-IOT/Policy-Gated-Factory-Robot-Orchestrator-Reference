# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hardware-free contracts for the two-host GR00T simulation launcher."""

from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_multi_host_fastdds_profile_is_udp_only_and_default() -> None:
    profile = ROOT / "ops/fastdds-multi-host.xml"
    root = ET.parse(profile).getroot()
    namespace = {"f": "http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles"}

    descriptor = root.find(
        "./f:transport_descriptors/f:transport_descriptor", namespace
    )
    assert descriptor is not None
    assert descriptor.findtext("f:transport_id", namespaces=namespace) == "UdpTransport"
    assert descriptor.findtext("f:type", namespaces=namespace) == "UDPv4"

    participant = root.find("./f:participant", namespace)
    assert participant is not None
    assert participant.attrib["is_default_profile"] == "true"
    assert (
        participant.findtext(
            "./f:rtps/f:userTransports/f:transport_id", namespaces=namespace
        )
        == "UdpTransport"
    )
    assert (
        participant.findtext(
            "./f:rtps/f:useBuiltinTransports", namespaces=namespace
        )
        == "false"
    )


def test_groot_launcher_is_private_fail_closed_and_multi_host_ready() -> None:
    launcher = text("ops/launch-groot-isaac.sh")

    assert "PRIVACY_CONSENT=Y" not in launcher
    assert "OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1" in launcher
    assert "FASTRTPS_DEFAULT_PROFILES_FILE=/etc/policy-gated-factory-robot-orchestrator-reference/fastdds.xml" in launcher
    assert "RMW_IMPLEMENTATION=rmw_fastrtps_cpp" in launcher
    assert 'ROS_DOMAIN_ID="$ROS_DOMAIN_ID_VALUE"' in launcher
    assert '-v "$FAST_DDS_PROFILE:/etc/policy-gated-factory-robot-orchestrator-reference/fastdds.xml:ro"' in launcher
    assert '-v "$MOUNT:/scripts:ro"' in launcher

    assert "docker ps -q" in launcher
    assert "'{{.Image}}'" in launcher
    assert 'eq .Destination "/scripts"' in launcher
    assert "pinned Isaac image is already active" in launcher
    assert "docker run -d --name" in launcher
    assert "docker run -d --rm" not in launcher
    assert "xhost +local:" not in launcher
    assert "no X11 authorization cookie exists" in launcher

    assert "IC_GROOT_READY_TIMEOUT" in launcher
    assert "IC_GROOT_RUNTIME_READY" in launcher
    assert "STARTUP_DONE full_scene+runner" in launcher
    assert "ERROR_MARKER_RE='[A-Z][A-Z0-9_]*_(ERR|ERROR)" in launcher
    assert launcher.count('grep -Eq "$ERROR_MARKER_RE"') == 2
    assert "container was left intact" in launcher


def test_cell_installer_checks_the_actual_scripts_mount() -> None:
    installer = text("ops/install-groot-cell.sh")

    assert "docker ps -q" in installer
    assert 'eq .Destination "/scripts"' in installer
    assert "realpath -m" in installer
    assert "this installer never replaces live files" in installer
    assert 'grep -qx "$CONTAINER_NAME"' not in installer


def test_thor_seam_uses_the_same_fastdds_profile() -> None:
    environment = text("ops/systemd/seam.env")

    assert "ROS_DOMAIN_ID=0" in environment
    assert "RMW_IMPLEMENTATION=rmw_fastrtps_cpp" in environment
    assert (
        "FASTRTPS_DEFAULT_PROFILES_FILE="
        "__IC_REPO__/ops/fastdds-multi-host.xml"
    ) in environment


def test_two_host_runbook_describes_separate_mount_and_bounded_readiness() -> None:
    guide = text("docs/REPRODUCIBLE-DEMO.md")

    assert "Use a separate scripts mount for the GR00T deployment" in guide
    assert "standalone baseline has been explicitly stopped" in guide
    assert "sets `OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1`" in guide
    assert "returns successfully only after both" in guide
    assert "systemd-run --user --wait --pipe --collect" in guide
    assert "sudo ufw allow in" in guide
    assert "from \"$THOR_IP\" to any port 7400:7609" in guide
    assert "Do not disable either" in guide
    assert "ROS2CLI_NO_DAEMON=1" in guide
    assert "require Publisher count: 1" in guide
    assert "ros2 topic echo /ic/floor_state" in guide


def test_two_host_runbook_preserves_fail_closed_first_run_order() -> None:
    guide = text("docs/REPRODUCIBLE-DEMO.md")

    assert guide.index("systemctl --user start ic-openclaw.service") < guide.index(
        "./node_modules/.bin/openclaw models set"
    )
    assert "nvcr.io/nvidia/cuda:13.0.0-devel-ubuntu24.04" in guide
    assert "/api/workflows/full-groot-dual-tote/run" in guide
    assert "IC_GROOT_PARALLEL_ENABLED=0" in guide
    assert "IC_GROOT_FLEXIBLE_ORDER=0" in guide
    assert 'docker logs --since "$ISAAC_STARTED_AT"' in guide
    assert "[A-Z][A-Z0-9_]*_(ERR|ERROR)(:|[[:space:]=]|$)" in guide
    assert "Isaac Sim current run contains a project error marker" in guide
    assert "/tmp/ic-reference-mission-id" in guide
    assert '"http://127.0.0.1:8766/v1/missions/$MISSION_ID?limit=100"' in guide
    assert 'data.get("started_steps") == 20' in guide
    assert 'len(operations) == 20' in guide
    assert 'assert len(dispatches) == 8' in guide
    assert (
        'op.get("verified") is True and '
        '(op.get("result") or {}).get("verified") is True'
    ) in guide
    assert 'assert len(proofs) == 9' in guide
    assert 'startswith("frames/") for op in proofs' in guide
    assert 'state.get("tote_r_on_rack") is True' in guide
    assert "prompt wording\nis not an authorization boundary" in guide
    assert "/tmp/ic-openclaw-read-smoke.json" not in guide
    assert guide.count('IC_GROOT_ISAAC_MOUNT="$IC_GROOT_ISAAC_ROOT/scripts"') >= 3
    assert 'xauth -f "$XAUTHORITY" nlist "$DISPLAY"' in guide

    direct = guide[guide.index("For direct-IP, read-only observability") :]
    assert direct.index("sudo ufw allow in") < direct.index(
        "IC_CONSOLE_HOST=0.0.0.0"
    )


def test_two_host_runbook_pins_publication_and_runs_both_conformance_checks() -> None:
    guide = text("docs/REPRODUCIBLE-DEMO.md")

    assert "VALIDATED_COMMIT=REPLACE_WITH_PUBLISHED_COMMIT" in guide
    assert guide.count('[[ "$VALIDATED_COMMIT" =~ ^[0-9a-f]{40}$ ]]') == 2
    assert 'git checkout --detach "$VALIDATED_COMMIT"' in guide
    assert 'test "$(git rev-parse HEAD)" = "$VALIDATED_COMMIT"' in guide
    assert "packages/conformance-kit/.venv/bin/ic-conformance run" in guide
    assert "packages/conformance-kit/.venv/bin/ic-conformance mcp" in guide
    assert "CERTIFIED: 9/9" in guide
    assert "CERTIFIED: 11/11" in guide
    assert '-H "Authorization: Bearer $NVIDIA_API_KEY"' not in guide
    assert '-H "@$AUTH_HEADER"' in guide
    assert "keeps the key out of `curl`'s process" in guide
    completion = guide[guide.index("Test one actual completion") :]
    assert completion.index(
        "unset NVIDIA_API_KEY IC_CHAT_API_KEY OPENCLAW_GATEWAY_TOKEN"
    ) < completion.index("curl --fail-with-body")
