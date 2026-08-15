# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Add canonical Thor GR00T serving health to ``floor_state``.

The policy/relay pairs run on the single Jetson Thor.  Persistent SSH
forwarding exposes their four published relay listeners on workstation
loopback ports 5681, 5682, 5683, and 5685.  Relays accept one persistent
executor client, so a health check must never connect to them: doing so can
occupy or disturb the data path.

This patch reads the kernel TCP listener tables instead.  It is non-invasive,
cached for 30 seconds, and reports the exact deployed model roles.  Re-exec is
idempotent because the unwrapped floor_state remains in ``_IC_FS_ORIG``.
"""

import time as _htime

_g = globals()

_IC_SERVING_SERVICES = {
    "red1000": 5681,
    "blue1000": 5682,
    "green1000": 5683,
    "green_corrective200": 5685,
}
_IC_SERVING_PORTS = tuple(sorted(_IC_SERVING_SERVICES.values()))
_IC_SERVING_CACHE_VERSION = "thor-relay-listeners-v3-four-published-experts"


def _ic_tcp_listeners():
    """Return listening TCP ports without creating a network connection."""
    _ports = set()
    for _table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(_table, encoding="ascii") as _stream:
                next(_stream, None)
                for _line in _stream:
                    _fields = _line.split()
                    if len(_fields) < 4 or _fields[3] != "0A":
                        continue
                    _ports.add(int(_fields[1].rsplit(":", 1)[1], 16))
        except (OSError, ValueError):
            continue
    return _ports


def _ic_serving_probe():
    _now = _htime.monotonic()
    _cache = _g.get("_IC_SERVING_CACHE")
    if (
        isinstance(_cache, tuple)
        and len(_cache) == 3
        and _cache[0] == _IC_SERVING_CACHE_VERSION
        and _now - _cache[1] < 30.0
    ):
        return _cache[2]
    _listeners = _ic_tcp_listeners()
    _service_status = {
        _name: {
            "port": _port,
            "listening": _port in _listeners,
        }
        for _name, _port in sorted(_IC_SERVING_SERVICES.items())
    }
    _open = sum(
        1 for _status in _service_status.values() if _status["listening"]
    )
    _block = {
        "ports_open": _open,
        "ports_total": len(_IC_SERVING_PORTS),
        "degraded": _open < len(_IC_SERVING_PORTS),
        "transport": "thor-loopback-via-ssh",
        "services": _service_status,
        "observed_at_epoch_s": int(_htime.time()),
    }
    _g["_IC_SERVING_CACHE"] = (
        _IC_SERVING_CACHE_VERSION,
        _now,
        _block,
    )
    return _block


if "_IC_FS_ORIG" not in _g:
    _g["_IC_FS_ORIG"] = _g["floor_state"]


def _ic_floor_state_with_health():
    _d = _g["_IC_FS_ORIG"]()
    try:
        _d["groot_serving"] = _ic_serving_probe()
    except Exception:
        pass
    return _d


_g["floor_state"] = _ic_floor_state_with_health
print("IC_SERVING_HEALTH_PATCHED ports=%s" % (_IC_SERVING_PORTS,), flush=True)
