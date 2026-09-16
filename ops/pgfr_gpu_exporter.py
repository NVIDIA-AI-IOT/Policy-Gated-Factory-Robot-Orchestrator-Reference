#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PGFR GPU exporter — per-model GPU attribution over time, stdlib only.

Runs on the GPU host beside the serving stacks. Samples nvidia-smi every
SAMPLE_S seconds, attributes each compute process to an orchestration role
(model ports, router, Isaac Sim, training, other), and serves the series
over read-only HTTP for the pgfr-console GPU pane.

Persistence is JSONL day files (the same idiom as the seam journal): every
sample is appended to PGFR_GPU_LOG_DIR/gpu-YYYYMMDD.jsonl, so sessions remain
reviewable after restarts; files older than PGFR_GPU_RETENTION_DAYS are
dropped at rotation. The in-memory ring is warmed from today's file on
startup so the live view survives exporter restarts too.

    GET /healthz                        -> {"ok": true, "samples": N}
    GET /v1/gpu/now                     -> latest sample
    GET /v1/gpu/series?minutes=60       -> live window from the ring
    GET /v1/gpu/series?from=..&to=..    -> historical window from day files
                                           (epoch seconds or ISO-8601)

Responses are downsampled to <= MAX_POINTS samples (stride sampling) so a
24 h window stays plot-sized. Sample shape:
    {"ts": "2026-07-23T18:04:11+00:00", "host": "5cebaec-lcedt",
     "gpu_util_pct": 34, "mem_used_mib": 41210, "mem_total_mib": 97240,
     "per_process_sm_available": true,
     "ram_used_mib": 58320, "ram_total_mib": 128000,
     "procs": {"groot-red-left": {"mem_mib": 6920, "sm_pct": 3, "pid": 1234}}}

The same file runs on Jetson (Thor). There nvidia-smi reports utilization
but no memory ("[N/A]"), so a Tegra probe is auto-detected at startup:
memory comes from /proc/meminfo (unified CPU+GPU pool), GPU power from one
tegrastats sample (VDD_GPU), and per-role attribution from process RSS
(model-specific VLM / GR00T policy / relay / OpenClaw / ROS 2). Tegra samples
add:
    {"unified": true, "gpu_memory_mode": "unified-system-ram",
     "gpu_power_mw": 1972}

No secrets, no writes outside the log dir, GET-only by construction.
"""

from __future__ import annotations

import collections
import json
import os
import re
import socket
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SAMPLE_S = 5
WINDOW_S = 24 * 3600
PORT = int(os.environ.get("PGFR_GPU_PORT", "8601"))
LOG_DIR = Path(os.environ.get("PGFR_GPU_LOG_DIR", "~/pgfr_gpu_telemetry")).expanduser()
RETENTION_DAYS = int(os.environ.get("PGFR_GPU_RETENTION_DAYS", "14"))
MAX_POINTS = 1500
HOST = os.environ.get("PGFR_GPU_HOST", socket.gethostname().split(".")[0])

PORT_ROLES = {
    5592: "groot-shared-left",
    5593: "groot-shared-right",
}

# Tegra (Thor) has no per-process GPU accounting; attribution falls back to
# RSS of the roles that matter on the brain box, matched against cmdline.
# Caveat: CUDA unified-memory pools don't appear in RSS, so per-process
# numbers are indicative; the whole-pool used/total is the ground truth.
TEGRA_ROLE_PATTERNS = [
    ("nemotron-vlm", ("nemotron",)),
    ("cosmos-edge-vlm", ("cosmos3-edge", "cosmos3_edge")),
    ("cosmos-reason-vlm", ("cosmos-reason", "cosmos_reason")),
    ("vllm-server", ("vllm",)),
    ("openclaw-gateway", ("dist/index.js", "openclaw")),
    ("ros2", ("ros2", "rmw_", "fastrtps")),
]
# The shared checkpoint is loaded in two independent B=1 processes, one per
# arm. Tegra cannot report per-process SM utilization, but these fixed ports
# make process memory attribution stable.
TEGRA_GROOT_PORT_ROLES = {
    "5571": "groot-shared-right",
    "5572": "groot-shared-left",
    "5581": "groot-specialists",
    "5582": "groot-specialists",
    "5583": "groot-specialists",
    "5584": "groot-specialists",
    "5585": "groot-specialists",
    "5592": "groot-shared-left",
    "5593": "groot-shared-right",
}
TEGRA_MIN_RSS_MIB = 64  # ignore trivia; unified RAM makes tiny procs noise

_samples: collections.deque = collections.deque(maxlen=WINDOW_S // SAMPLE_S)
_lock = threading.Lock()


# ----------------------------------------------------------- persistence
def _day_file(day: datetime) -> Path:
    return LOG_DIR / ("gpu-%s.jsonl" % day.strftime("%Y%m%d"))


def _append_sample(entry: dict) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_day_file(datetime.now(timezone.utc)), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # persistence is best-effort; the live ring keeps serving


def _prune_old_files() -> None:
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        for path in LOG_DIR.glob("gpu-*.jsonl"):
            match = re.fullmatch(r"gpu-(\d{8})\.jsonl", path.name)
            if match and match.group(1) < cutoff.strftime("%Y%m%d"):
                path.unlink(missing_ok=True)
    except Exception:
        pass


def _warm_ring_from_today() -> int:
    """Reload today's samples on startup so a restart doesn't blank the view."""
    count = 0
    try:
        with open(_day_file(datetime.now(timezone.utc)), encoding="utf-8") as f:
            for line in f:
                try:
                    _samples.append(json.loads(line))
                    count += 1
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return count


def _parse_when(raw: str) -> float | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return float(raw)  # epoch seconds
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _entry_epoch(entry: dict) -> float:
    try:
        return datetime.fromisoformat(str(entry.get("ts"))).timestamp()
    except Exception:
        return 0.0


def _read_window(t_from: float, t_to: float) -> list[dict]:
    """Time-range slice from the day files overlapping [t_from, t_to]."""
    out: list[dict] = []
    day = datetime.fromtimestamp(t_from, timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_day = datetime.fromtimestamp(t_to, timezone.utc)
    while day <= end_day:
        try:
            with open(_day_file(day), encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    ts = _entry_epoch(entry)
                    if t_from <= ts <= t_to:
                        out.append(entry)
        except FileNotFoundError:
            pass
        except Exception:
            pass
        day += timedelta(days=1)
    return out


def _downsample(entries: list[dict]) -> list[dict]:
    if len(entries) <= MAX_POINTS:
        return entries
    stride = -(-len(entries) // MAX_POINTS)  # ceil division
    kept = entries[::stride]
    if kept and entries and kept[-1] is not entries[-1]:
        kept.append(entries[-1])
    return kept


# ----------------------------------------------------------- sampling
def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return ""


def _pid_roles() -> dict[int, str]:
    roles: dict[int, str] = {}
    for line in _run(["ss", "-ltnp"]).splitlines():
        match = re.search(r":(\d+)\s.*pid=(\d+)", line)
        if not match:
            continue
        port, pid = int(match.group(1)), int(match.group(2))
        if port in PORT_ROLES:
            roles.setdefault(pid, PORT_ROLES[port])
    return roles


def _cmdline(pid: int) -> str:
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            return handle.read().replace(b"\x00", b" ").decode(errors="replace")
    except Exception:
        return ""


def _fallback_role(pid: int) -> str:
    cmd = _cmdline(pid)
    if "isaac-sim" in cmd or "/isaac-sim/" in cmd or "omni." in cmd:
        return "isaac-sim"
    if any(k in cmd for k in ("finetune", "deepspeed", "launch_finetune", "train")):
        return "training"
    if "gr00t" in cmd.lower() or "run_gr00t_server" in cmd:
        return "groot-server"
    base = (cmd.split() or ["unknown"])[0].rsplit("/", 1)[-1][:24]
    return "other:%s" % (base or "unknown")


def _sample() -> dict | None:
    top = _run(
        [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ]
    ).strip()
    if not top:
        return None
    try:
        util, mem_used, mem_total = [int(float(v)) for v in top.split(",")[:3]]
    except Exception:
        return None

    mem_by_pid: dict[int, int] = {}
    for line in _run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ]
    ).splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2 and parts[0].isdigit():
            mem_by_pid[int(parts[0])] = int(float(parts[1] or 0))

    sm_by_pid: dict[int, int] = {}
    for line in _run(["nvidia-smi", "pmon", "-c", "1", "-s", "u"]).splitlines():
        if line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[1].isdigit():
            try:
                sm_by_pid[int(parts[1])] = int(parts[3])
            except ValueError:
                pass  # '-' when idle

    roles = _pid_roles()
    procs: dict[str, dict] = {}
    for pid, mem in mem_by_pid.items():
        role = roles.get(pid) or _fallback_role(pid)
        entry = procs.setdefault(role, {"mem_mib": 0, "sm_pct": 0, "pid": pid})
        entry["mem_mib"] += mem
        entry["sm_pct"] += sm_by_pid.get(pid, 0)

    ram_used, ram_total = _meminfo_mib()
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": HOST,
        "gpu_memory_mode": "dedicated",
        "per_process_sm_available": True,
        "gpu_util_pct": util,
        "mem_used_mib": mem_used,
        "mem_total_mib": mem_total,
        "ram_used_mib": ram_used,
        "ram_total_mib": ram_total,
        "procs": procs,
    }


# --------------------------------------------------- tegra (Jetson) probe
def _is_tegra() -> bool:
    """Thor's nvidia-smi answers utilization but reports memory as [N/A]."""
    out = _run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader"])
    return "N/A" in out if out.strip() else Path("/etc/nv_tegra_release").exists()


def _meminfo_mib() -> tuple[int, int]:
    total = avail = 0
    with open("/proc/meminfo", encoding="ascii") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                total = int(line.split()[1]) // 1024
            elif line.startswith("MemAvailable:"):
                avail = int(line.split()[1]) // 1024
    return max(0, total - avail), total


def _tegrastats_gpu_mw() -> int | None:
    """One tegrastats line; VDD_GPU current draw is the activity signal
    (Thor's tegrastats has no GR3D_FREQ utilization field)."""
    out = _run(["timeout", "2", "tegrastats", "--interval", "500"])
    match = re.search(r"VDD_GPU (\d+)mW", out)
    return int(match.group(1)) if match else None


def _rss_mib(pid: int) -> int:
    try:
        with open("/proc/%d/statm" % pid, encoding="ascii") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") // (1024 * 1024)
    except Exception:
        return 0


def _ppid(pid: int) -> int | None:
    """Read a process parent without adding psutil to the stdlib exporter."""
    try:
        with open("/proc/%d/status" % pid, encoding="ascii") as handle:
            for line in handle:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except Exception:
        pass
    return None


def _tegra_procs() -> dict[str, dict]:
    procs: dict[str, dict] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        cmd = _cmdline(pid).lower()
        if not cmd:
            continue
        # vLLM's EngineCore child does not retain the model name in its own
        # command. Classify it with the serving parent's immutable cmdline so
        # parent and engine memory stay under the same model identity.
        identity_cmd = cmd
        if "vllm::enginecore" in cmd:
            parent_pid = _ppid(pid)
            if parent_pid:
                identity_cmd = "%s %s" % (cmd, _cmdline(parent_pid).lower())
        role = None
        if "native_droid_relay" in cmd:
            role = "groot-relays"
        elif "run_gr00t_server" in cmd:
            for port, port_role in TEGRA_GROOT_PORT_ROLES.items():
                if re.search(r"(?:--port(?:=|\s+))%s\b" % re.escape(port), cmd):
                    role = port_role
                    break
            role = role or "groot-server"
        elif "gr00t" in cmd:
            role = "groot-server"
        else:
            for candidate, needles in TEGRA_ROLE_PATTERNS:
                if any(n in identity_cmd for n in needles):
                    role = candidate
                    break
        if role is None:
            continue
        rss = _rss_mib(pid)
        if rss >= TEGRA_MIN_RSS_MIB:
            slot = procs.setdefault(
                role,
                {"mem_mib": 0, "sm_pct": None, "pid": pid, "pids": []},
            )
            slot["mem_mib"] += rss
            slot["pids"].append(pid)
    return procs


def _sample_tegra() -> dict | None:
    util_raw = _run(
        ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"]
    ).strip()
    try:
        util = int(float(util_raw.split("\n")[0]))
    except Exception:
        util = 0
    mem_used, mem_total = _meminfo_mib()
    if not mem_total:
        return None
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": HOST,
        "unified": True,
        "gpu_memory_mode": "unified-system-ram",
        "per_process_sm_available": False,
        "gpu_util_pct": util,
        "mem_used_mib": mem_used,
        "mem_total_mib": mem_total,
        "ram_used_mib": mem_used,
        "ram_total_mib": mem_total,
        "procs": _tegra_procs(),
    }
    power = _tegrastats_gpu_mw()
    if power is not None:
        entry["gpu_power_mw"] = power
    return entry


_PROBE = _sample  # rebound to _sample_tegra in main() when Tegra is detected


def _sampler() -> None:
    last_day = datetime.now(timezone.utc).strftime("%Y%m%d")
    while True:
        entry = _PROBE()
        if entry is not None:
            with _lock:
                _samples.append(entry)
            _append_sample(entry)
            today = datetime.now(timezone.utc).strftime("%Y%m%d")
            if today != last_day:
                last_day = today
                _prune_old_files()
        time.sleep(SAMPLE_S)


# ----------------------------------------------------------- http
class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # quiet
        pass

    def _json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("access-control-allow-origin", "*")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        url = urlparse(self.path)
        query = parse_qs(url.query)
        with _lock:
            snapshot = list(_samples)
        if url.path == "/healthz":
            self._json({"ok": True, "samples": len(snapshot)})
        elif url.path == "/v1/gpu/now":
            self._json(snapshot[-1] if snapshot else {"error": "no samples yet"})
        elif url.path == "/v1/gpu/series":
            t_from = _parse_when(query.get("from", [""])[0])
            t_to = _parse_when(query.get("to", [""])[0])
            if t_from is not None and t_to is not None and t_to > t_from:
                if t_to - t_from > 7 * 24 * 3600:
                    t_from = t_to - 7 * 24 * 3600  # clamp: one week per query
                entries = _downsample(_read_window(t_from, t_to))
                self._json(
                    {"sample_s": SAMPLE_S, "mode": "window", "samples": entries}
                )
                return
            try:
                minutes = min(
                    24 * 60, max(1, int(query.get("minutes", ["60"])[0]))
                )
            except ValueError:
                minutes = 60
            keep = minutes * 60 // SAMPLE_S
            self._json(
                {
                    "sample_s": SAMPLE_S,
                    "mode": "live",
                    "samples": _downsample(snapshot[-keep:]),
                }
            )
        else:
            self._json({"error": "not found"}, status=404)


def main() -> None:
    global _PROBE
    tegra = _is_tegra()
    if tegra:
        _PROBE = _sample_tegra
    warmed = _warm_ring_from_today()
    _prune_old_files()
    threading.Thread(target=_sampler, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), _Handler)
    print(
        "pgfr-gpu-exporter serving :%d (host %s, probe %s, sample %ds, log %s, warmed %d)"
        % (PORT, HOST, "tegra" if tegra else "nvidia-smi", SAMPLE_S, LOG_DIR, warmed),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
