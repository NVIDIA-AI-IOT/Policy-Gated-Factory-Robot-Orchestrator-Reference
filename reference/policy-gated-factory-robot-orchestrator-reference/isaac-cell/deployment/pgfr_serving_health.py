# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Add canonical Thor GR00T serving health to ``floor_state``.

The policy/relay pairs run on the single Jetson Thor.  Persistent SSH
forwarding exposes one shared relay listener per arm on workstation loopback.
The exact ports come from the generated concurrent-policy contract so custom
installer port selections remain observable.  Relays accept one persistent
executor client, so a health check must never connect to them: doing so can
occupy or disturb the data path.

This patch reads the kernel TCP listener tables instead.  It is non-invasive,
cached for 30 seconds, and reports the exact deployed arm relays.  Re-exec is
idempotent because the unwrapped floor_state remains in ``_PGFR_FS_ORIG``.
"""

import json as _hjson
import time as _htime

_g = globals()

_PGFR_SERVING_CONTRACT_PATH = _g.get(
    "_PGFR_SERVING_CONTRACT_PATH",
    "/scripts/groot_shared_concurrent_policy_contract.json",
)


def _pgfr_contract_port(_value, _label):
    if isinstance(_value, bool) or not isinstance(_value, int):
        raise RuntimeError("%s must be an integer" % (_label,))
    if not 1 <= _value <= 65535:
        raise RuntimeError("%s must be between 1 and 65535" % (_label,))
    return _value


def _pgfr_load_serving_services():
    try:
        with open(_PGFR_SERVING_CONTRACT_PATH, encoding="utf-8") as _stream:
            _contract = _hjson.load(_stream)
    except (OSError, UnicodeError, _hjson.JSONDecodeError) as _exc:
        raise RuntimeError(
            "failed to load GR00T concurrent contract %s: %s"
            % (_PGFR_SERVING_CONTRACT_PATH, _exc)
        ) from _exc

    _relays = _contract.get("relays") if isinstance(_contract, dict) else None
    if not isinstance(_relays, dict):
        raise RuntimeError("GR00T concurrent contract relays must be an object")

    _services = {}
    for _arm in ("franka_left", "franka_right"):
        _entry = _relays.get(_arm)
        if not isinstance(_entry, dict):
            raise RuntimeError(
                "GR00T concurrent contract relays.%s must be an object" % (_arm,)
            )
        _services[_arm] = _pgfr_contract_port(
            _entry.get("relay_port"), "relays.%s.relay_port" % (_arm,)
        )
    if len(set(_services.values())) != len(_services):
        raise RuntimeError("GR00T concurrent relay ports must be distinct")
    return _services


_PGFR_SERVING_SERVICES = _pgfr_load_serving_services()
_PGFR_SERVING_PORTS = tuple(sorted(_PGFR_SERVING_SERVICES.values()))
_PGFR_SERVING_CACHE_VERSION = "thor-shared-relay-listeners-v4"


def _pgfr_tcp_listeners():
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


def _pgfr_serving_probe():
    _now = _htime.monotonic()
    _cache = _g.get("_PGFR_SERVING_CACHE")
    if (
        isinstance(_cache, tuple)
        and len(_cache) == 3
        and _cache[0] == _PGFR_SERVING_CACHE_VERSION
        and _now - _cache[1] < 30.0
    ):
        return _cache[2]
    _listeners = _pgfr_tcp_listeners()
    _service_status = {
        _name: {
            "port": _port,
            "listening": _port in _listeners,
        }
        for _name, _port in sorted(_PGFR_SERVING_SERVICES.items())
    }
    _open = sum(
        1 for _status in _service_status.values() if _status["listening"]
    )
    _block = {
        "ports_open": _open,
        "ports_total": len(_PGFR_SERVING_PORTS),
        "degraded": _open < len(_PGFR_SERVING_PORTS),
        "transport": "thor-loopback-via-ssh",
        "services": _service_status,
        "observed_at_epoch_s": int(_htime.time()),
    }
    _g["_PGFR_SERVING_CACHE"] = (
        _PGFR_SERVING_CACHE_VERSION,
        _now,
        _block,
    )
    return _block


if "_PGFR_FS_ORIG" not in _g:
    _g["_PGFR_FS_ORIG"] = _g["floor_state"]


def _pgfr_floor_state_with_health():
    _d = _g["_PGFR_FS_ORIG"]()
    try:
        _d["groot_serving"] = _pgfr_serving_probe()
    except Exception:
        pass
    return _d


_g["floor_state"] = _pgfr_floor_state_with_health
print("PGFR_SERVING_HEALTH_PATCHED ports=%s" % (_PGFR_SERVING_PORTS,), flush=True)
