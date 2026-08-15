# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
from pathlib import Path


_SOURCE = Path(__file__).with_name("ic_gpu_exporter.py")
_SPEC = importlib.util.spec_from_file_location("ic_gpu_exporter", _SOURCE)
assert _SPEC and _SPEC.loader
exporter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(exporter)


def test_tegra_attributes_two_shared_servers(monkeypatch) -> None:
    commands = {
        101: "python gr00t/eval/run_gr00t_server.py --port 5592",
        102: "python gr00t/eval/run_gr00t_server.py --port 5593",
        103: "openclaw gateway --port 18790",
        104: "vllm serve nvidia/Cosmos-Reason2-2B",
    }
    monkeypatch.setattr(exporter.os, "listdir", lambda _path: [str(pid) for pid in commands])
    monkeypatch.setattr(exporter, "_cmdline", lambda pid: commands[pid])
    monkeypatch.setattr(exporter, "_rss_mib", lambda _pid: 100)

    procs = exporter._tegra_procs()

    assert procs["groot-shared-left"]["pids"] == [101]
    assert procs["groot-shared-right"]["pids"] == [102]
    assert "groot-specialists" not in procs
    assert procs["openclaw-gateway"]["pids"] == [103]
    assert procs["cosmos-reason-vlm"]["pids"] == [104]


def test_tegra_separates_vlms_specialists_and_relays(monkeypatch) -> None:
    commands = {
        201: "vllm serve nvidia/Cosmos3-Edge --port 8002",
        202: "VLLM::EngineCore",
        203: "vllm serve nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-NVFP4-QAD",
        204: "VLLM::EngineCore",
        205: "python gr00t/eval/run_gr00t_server.py --port 5581",
        206: "python /opt/groot_shadow/native_droid_relay_v36.py --listen-port 5681",
        207: "vllm serve org/another-model",
    }
    parents = {202: 201, 204: 203}
    monkeypatch.setattr(exporter.os, "listdir", lambda _path: [str(pid) for pid in commands])
    monkeypatch.setattr(exporter, "_cmdline", lambda pid: commands[pid])
    monkeypatch.setattr(exporter, "_ppid", lambda pid: parents.get(pid))
    monkeypatch.setattr(exporter, "_rss_mib", lambda _pid: 100)

    procs = exporter._tegra_procs()

    assert procs["cosmos-edge-vlm"]["pids"] == [201, 202]
    assert procs["nemotron-vlm"]["pids"] == [203, 204]
    assert procs["groot-specialists"]["pids"] == [205]
    assert procs["groot-relays"]["pids"] == [206]
    assert procs["vllm-server"]["pids"] == [207]
    assert "cosmos-vlm" not in procs


def test_tegra_sample_marks_ram_as_the_unified_gpu_pool(monkeypatch) -> None:
    monkeypatch.setattr(exporter, "_run", lambda _cmd: "37")
    monkeypatch.setattr(exporter, "_meminfo_mib", lambda: (96_000, 128_000))
    monkeypatch.setattr(exporter, "_tegrastats_gpu_mw", lambda: 2400)
    monkeypatch.setattr(exporter, "_tegra_procs", lambda: {})

    sample = exporter._sample_tegra()

    assert sample["gpu_util_pct"] == 37
    assert sample["gpu_memory_mode"] == "unified-system-ram"
    assert sample["per_process_sm_available"] is False
    assert sample["ram_used_mib"] == sample["mem_used_mib"] == 96_000
    assert sample["ram_total_mib"] == sample["mem_total_mib"] == 128_000
    assert sample["gpu_power_mw"] == 2400


def test_tegra_process_sm_is_explicitly_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(exporter.os, "listdir", lambda _path: ["101"])
    monkeypatch.setattr(
        exporter, "_cmdline", lambda _pid: "python gr00t/eval/run_gr00t_server.py --port 5592"
    )
    monkeypatch.setattr(exporter, "_rss_mib", lambda _pid: 100)

    assert exporter._tegra_procs()["groot-shared-left"]["sm_pct"] is None
