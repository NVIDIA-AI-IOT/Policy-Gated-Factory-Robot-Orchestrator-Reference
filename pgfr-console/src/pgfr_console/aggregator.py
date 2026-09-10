# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read-only pollers that turn the declared topology into measured status.

Sources (all existing endpoints — the console adds zero instrumentation):
- seam ``GET /v1/health``  -> seam/floor/cell status (ros_ok, backend,
  floor_state_age_s, camera_age_s) and journal freshness
- seam ``POST /v1/floor-state`` -> current endpoints and world state
- seam ``GET /v1/missions`` -> recent mission summaries
- VLM ``GET /v1/models``    -> model endpoint liveness
- Chat ``GET /api/health`` -> process liveness and configured assistants/tools
- floor-state ``groot_serving`` -> existing passive relay-listener observations
"""

from __future__ import annotations

import asyncio
import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlsplit

import httpx

from .topology import Edge, NodeStatus, blank_topology, resolve


class Settings:
    def __init__(self) -> None:
        self.seam_url = os.environ.get("PGFR_FLOOR_SERVICE", "http://127.0.0.1:8766").rstrip("/")
        self.vlm_url = os.environ.get("PGFR_VLM_URL", "").rstrip("/")
        self.gym_url = os.environ.get("PGFR_GYM_URL", "").rstrip("/")
        self.chat_url = os.environ.get("PGFR_CHAT_URL", "http://127.0.0.1:8620").rstrip("/")
        # GPU exporter on the serving host (ops/pgfr_gpu_exporter.py); unset -> pane
        # renders "unknown", per the measured-not-asserted rule.
        self.gpu_url = os.environ.get("PGFR_GPU_URL", "").rstrip("/")
        # Same exporter on the Thor brain box (tegra probe); unset -> the pane
        # simply has no Thor card. Thor's IP is DHCP — env, never hardcoded.
        self.gpu_url_thor = os.environ.get("PGFR_GPU_URL_THOR", "").rstrip("/")
        self.timeout_s = float(os.environ.get("PGFR_CONSOLE_TIMEOUT_S", "3.0"))
        self.poll_interval_s = float(os.environ.get("PGFR_CONSOLE_POLL_S", "2.0"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite_age(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def _public_detail(body: Dict[str, Any]) -> Dict[str, Any]:
    """Keep reported diagnostics JSON-safe, including unknown numeric readings."""
    def clean(value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if not key.startswith("_")}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return {key: clean(value) for key, value in body.items() if not key.startswith("_")}


def _configured_host(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


# Assurance claims. Each carries an honest `basis`:
#  - "live"   : backed by a figure measured from the audit store (attached in the UI)
#  - "design" : a design-time / test-enforced property with a concrete `proof`
#               citation — NOT a runtime measurement, and shown as such so it
#               never masquerades as measured evidence (GSN evidence fidelity).
_ASSURANCE_CLAIMS = [
    {"name": "Physics-verified, stop on uncertainty", "basis": "live",
     "how": "A dispatch is done only when the cell re-measured the world (verified=true); "
            "aggregation reports FAIL when data is missing or corrupt — a false PASS is "
            "unreachable."},
    {"name": "Operator actions blocked from agents", "basis": "live",
     "how": "reset/spawn/cancel refused at author time, at resolved-runtime, and by the seam "
            "policy gate — an agent/workflow/chat can never actuate them."},
    {"name": "Journal records expose attributable evidence", "basis": "live",
     "how": "successful journal writes preserve the operation, request context, and exact "
            "camera frame used by the VLM; missing records cannot be inferred as complete."},
    {"name": "One action, no auto-retry", "basis": "design",
     "proof": "pgfr-workflows runner: dispatch max_attempts=1",
     "how": "Physical dispatch is one call, always verified-gated, and never auto-retried "
            "(an unverified move may already have actuated)."},
    {"name": "CSRF on every write path", "basis": "design",
     "proof": "custom header + exact-Origin guard (pgfr-workflows / pgfr-chat)",
     "how": "workflows/chat/schedule require a custom header + exact Origin check — a random "
            "web page in the operator's browser cannot move the arm."},
    {"name": "Read-only observability plane", "basis": "design",
     "proof": "test_api_surface_is_read_only (GET-only)",
     "how": "the console API is GET-only (test-enforced) and crash-isolated from the control "
            "path — it can lag or die without touching production."},
]


class Aggregator:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or Settings()
        self._snapshot: Dict[str, Any] = {"nodes": [], "edges": [], "generated_at": _now()}
        self._lock = asyncio.Lock()
        # Discovery persists across a transient outage; missing measurements
        # become unknown instead of removing previously reported equipment.
        self._reported_cameras: Optional[set[str]] = None
        self._groot_seen = False

    # ------------------------------------------------------------- polling
    async def _get_json(self, client: httpx.AsyncClient, url: str) -> Optional[Dict[str, Any]]:
        try:
            resp = await client.get(url)
            body = resp.json() if resp.content else {}
            if not isinstance(body, dict):
                return None
            body["_http_status"] = resp.status_code
            return body
        except Exception:
            return None

    async def _post_json(self, client: httpx.AsyncClient, url: str) -> Optional[Dict[str, Any]]:
        try:
            resp = await client.post(url, json={})
            body = resp.json() if resp.content else {}
            if not isinstance(body, dict):
                return None
            body["_http_status"] = resp.status_code
            return body
        except Exception:
            return None

    async def poll_once(self) -> Dict[str, Any]:
        topo = blank_topology()
        nodes: Dict[str, NodeStatus] = topo["nodes"]  # type: ignore[assignment]
        edges: Dict[str, Edge] = topo["edges"]  # type: ignore[assignment]
        s = self.settings
        for nid, url in (("brain", s.chat_url), ("seam", s.seam_url),
                         ("vlm", s.vlm_url), ("gym", s.gym_url)):
            nodes[nid].host = _configured_host(url)
        if not s.vlm_url:
            nodes.pop("vlm")
        if not s.gym_url:
            nodes.pop("gym")

        async with httpx.AsyncClient(timeout=s.timeout_s) as client:
            async def optional(url: str) -> Optional[Dict[str, Any]]:
                return await self._get_json(client, url) if url else None

            health, vlm, gym, chat = await asyncio.gather(
                optional(f"{s.seam_url}/v1/health"),
                optional(f"{s.vlm_url}/v1/models" if s.vlm_url else ""),
                optional(f"{s.gym_url}/" if s.gym_url else ""),
                optional(f"{s.chat_url}/api/health" if s.chat_url else ""),
            )

        # Robot API health reports on the policy gate and attached simulator.
        if health is None:
            nodes["seam"].status = "down"
            nodes["seam"].detail = {"error": "unreachable", "url": s.seam_url}
        else:
            code = health.get("_http_status")
            nodes["seam"].status = "ok" if code == 200 else "degraded" if code == 503 else "down"
            nodes["seam"].detail = _public_detail(health)
            nodes["seam"].detail["status_basis"] = "Robot API health"
            backend = str(health.get("backend", ""))
            ros_ok = health.get("ros_ok")
            nodes["floor"].status = nodes["seam"].status
            nodes["floor"].detail = {"backend": backend, "status_basis": "Robot API health"}
            if backend == "mock":
                nodes["cell"].detail = {"note": "Mock backend; no simulator attached"}
            elif code in (200, 503) and isinstance(ros_ok, bool):
                age = _finite_age(health.get("floor_state_age_s"))
                nodes["cell"].status = (
                    "down" if not ros_ok else "unknown" if age is None
                    else "degraded" if age > 10 else "ok"
                )
                nodes["cell"].detail = {
                    "ros_ok": ros_ok, "floor_state_age_s": age,
                    "status_basis": "Robot API simulator heartbeat",
                }
            nodes["journal"].status = nodes["seam"].status
            nodes["journal"].detail = {
                "status_basis": "Robot API health; history storage is not probed separately",
            }

        if s.chat_url:
            nodes["brain"].status = (
                "ok" if chat is not None and chat.get("_http_status") == 200 else "down"
            )
            nodes["brain"].detail = _public_detail(chat or {})
            nodes["brain"].detail.update({
                "url": s.chat_url,
                "status_basis": "Chat process health; model readiness is not checked",
            })
        if s.vlm_url:
            nodes["vlm"].status = (
                "ok" if vlm is not None and vlm.get("_http_status") == 200 else "down"
            )
            models = (vlm or {}).get("data")
            nodes["vlm"].detail = {
                "url": s.vlm_url, "status_basis": "Vision model listing endpoint",
                "model_ids": [model["id"] for model in models
                              if isinstance(model, dict) and isinstance(model.get("id"), str)]
                if nodes["vlm"].status == "ok" and isinstance(models, list) else [],
            }
        if s.gym_url:
            nodes["gym"].status = (
                "ok" if gym is not None and gym.get("_http_status") == 200 else "down"
            )
            nodes["gym"].detail = {"url": s.gym_url, "status_basis": "Configured Gym endpoint"}

        # These are logical capabilities, not independently probed services.
        for tid in ("t_floor_state", "t_perceive", "t_dispatch", "t_verify", "mcp"):
            nodes[tid].status = nodes["seam"].status
            nodes[tid].detail = {"status_basis": "Robot API health"}
        if chat is not None and chat.get("_http_status") == 200:
            nodes["mcp"].detail["tools"] = chat.get("tools", [])

        cell_status = nodes["cell"].status
        fs = None
        if health is not None and health.get("_http_status") in (200, 503):
            async with httpx.AsyncClient(timeout=s.timeout_s) as client:
                fs = await self._post_json(client, f"{s.seam_url}/v1/floor-state")
        floor_state = fs if isinstance(fs, dict) and fs.get("_http_status") == 200 else {}
        live_eps = {}
        if isinstance(floor_state.get("endpoints"), list):
            for ep in floor_state["endpoints"]:
                if isinstance(ep, dict) and isinstance(ep.get("id"), str):
                    live_eps[ep["id"]] = ep
        for eid in ("franka_left", "franka_right", "mobilebot"):
            nodes[eid].status = "unknown"
            nodes[eid].detail = {"status_basis": "Reported endpoint and simulator heartbeat"}
            # Do not match both Franka arms to the first ID containing 'franka'.
            ep = live_eps.get(eid)
            if ep:
                nodes[eid].status = cell_status
                nodes[eid].detail.update({key: ep[key] for key in
                                         ("status", "battery", "location", "kind") if key in ep})

        cam_age = (health or {}).get("camera_age_s")
        if isinstance(cam_age, dict) and (health or {}).get("_http_status") in (200, 503):
            if self._reported_cameras is None:
                self._reported_cameras = set()
            self._reported_cameras.update(
                cid for cid in cam_age if isinstance(cid, str) and cid
                and (cid not in nodes or nodes[cid].kind == "camera")
            )
        if self._reported_cameras is not None:
            # A per-camera report supersedes the legacy declared camera list.
            for nid in [nid for nid, node in nodes.items() if node.kind == "camera"]:
                nodes.pop(nid)
            camera_labels = {
                "inspect_vlm_cam": "Inspection view", "outside_right_cam": "Overview camera",
                "inspect_cam": "Inspection camera", "rack_cam": "Rack camera",
                "table_cam": "Table camera",
            }
            for cid in sorted(self._reported_cameras):
                label = camera_labels.get(cid, cid.replace("_", " ").replace("-", " ").capitalize())
                nodes[cid] = NodeStatus(id=cid, label=label, kind="camera", layer=6)
                edges[f"cell-{cid}"] = Edge(id=f"cell-{cid}", source="cell", target=cid)
                edges[f"{cid}-vlm"] = Edge(id=f"{cid}-vlm", source=cid, target="vlm", label="feed")
        for cid, node in nodes.items():
            if node.kind != "camera":
                continue
            raw_age = cam_age.get(cid) if isinstance(cam_age, dict) else (
                cam_age if self._reported_cameras is None else None
            )
            age = _finite_age(raw_age)
            node.status = (
                "unknown" if age is None else "down" if age > 30
                else "degraded" if age > 5 else cell_status
            )
            node.detail = {"camera_id": cid, "camera_age_s": age,
                           "status_basis": "Reported camera freshness"}

        # Use existing passive observations. Never open a GR00T relay socket:
        # native DROID relays reserve a single long-lived simulator client.
        serving = floor_state.get("groot_serving")
        if isinstance(serving, dict):
            self._groot_seen = True
        if not self._groot_seen:
            nodes.pop("groot")
        else:
            nodes["groot"].detail = {
                "status_basis": "Relay transport only; inference health is not measured",
                "note": "Listener availability does not verify model inference",
            }
            if isinstance(serving, dict):
                nodes["groot"].detail.update(_public_detail(serving))
                observed = _finite_age(serving.get("observed_at_epoch_s"))
                age = _finite_age(datetime.now(timezone.utc).timestamp() - observed) if observed else None
                nodes["groot"].detail["observed_age_s"] = age
                services = serving.get("services")
                total, opened = serving.get("ports_total"), serving.get("ports_open")
                valid_counts = (isinstance(total, int) and not isinstance(total, bool) and total > 0
                                and isinstance(opened, int) and not isinstance(opened, bool)
                                and 0 <= opened <= total)
                if age is not None and age <= 180 and valid_counts and isinstance(services, dict):
                    listeners_ok = all(isinstance(services.get(arm), dict)
                                       and services[arm].get("listening") is True
                                       for arm in ("franka_left", "franka_right"))
                    ready = opened == total and serving.get("degraded") is False and listeners_ok
                    nodes["groot"].status = (
                        "unknown" if cell_status == "unknown" else "down" if cell_status == "down"
                        else "degraded" if not ready or age > 60 or cell_status == "degraded" else "ok"
                    )

        snapshot = resolve(nodes, edges)
        snapshot["generated_at"] = _now()
        async with self._lock:
            self._snapshot = snapshot
        return snapshot

    async def assurance(self) -> Dict[str, Any]:
        """Verification and auditability, proven from the audit store — not asserted.

        Reads the recent operations and derives the live evidence for each
        assurance claim: the dispatch-policy/physics-verification flow, verification rate, audit
        coverage (journaled + evidence-framed), and placement accuracy vs the
        success tolerance.
        """
        AGENT_ACTIONS = {"move", "pick_and_place"}
        feed = await self.inspect(limit=100)
        ops = feed.get("operations", [])
        # A physical dispatch is ONLY op=="dispatch". perceive/verify ops also
        # carry an `action` field (it holds the target/predicate, not a dispatch
        # verb) — keying on `action` would wrongly count them as dispatches and
        # poison the verified-rate denominator.
        dispatches = [o for o in ops if o.get("op") == "dispatch"]
        operator_refused = 0
        agent_ok = 0
        for o in dispatches:
            act = (o.get("request") or {}).get("action") or o.get("action")
            if act in AGENT_ACTIONS:
                agent_ok += 1
            elif act:
                # an op=="dispatch" whose action is NOT agent-class means an
                # operator verb reached the actuation record — the thing the
                # policy gate exists to prevent (expected count: 0).
                operator_refused += 1
        verified = sum(1 for o in dispatches if o.get("verified") is True)
        unverified = sum(1 for o in dispatches if o.get("verified") is False)
        with_frame = sum(1 for o in ops if o.get("frame"))
        with_verdict = sum(1 for o in dispatches if o.get("verified") is not None)
        # Records-integrity coverage — MEASURED, not asserted. Attribution and
        # timing are counted from fields the seam actually wrote (request_id +
        # request payload; ts + duration_s), never a hardcoded 100%. mission_id
        # is deliberately NOT used for attribution: inspect() back-fills it, so
        # it would be self-fulfilling rather than proof from the record.
        with_request = sum(1 for o in ops if o.get("request_id") and o.get("request"))
        with_timing = sum(
            1 for o in ops if o.get("ts") and o.get("duration_s") is not None
        )

        placement = []
        for o in dispatches:
            m = (o.get("result") or {}).get("measured") or {}
            g = (o.get("result") or {}).get("gate") or {}
            off = m.get("placement_offset_m")
            tol = g.get("placement_tolerance_m")
            if off is not None and tol is not None:
                placement.append({
                    "mission": o.get("mission_id"),
                    "color": (o.get("request") or {}).get("color"),
                    "offset_m": off, "tolerance_m": tol,
                    "pass": o.get("verified") is True,
                })

        return {
            "gate": {
                "dispatches": len(dispatches),
                "agent_class_ok": agent_ok,
                "operator_refused": operator_refused,
                "physics_verified": verified,
                "unverified": unverified,
                "verified_rate": round(verified / len(dispatches), 3) if dispatches else None,
            },
            "coverage": {
                "ops": len(ops),
                "journaled": len(ops),   # every op is journaled by construction
                "with_frame": with_frame,
                "frame_rate": round(with_frame / len(ops), 3) if ops else None,
                "with_request": with_request,   # attributable: request_id + payload
                "with_timing": with_timing,     # timestamped: ts + duration_s
                "dispatches": len(dispatches),
                "with_verdict": with_verdict,
            },
            "placement": placement,
            "assurance_claims": _ASSURANCE_CLAIMS,
        }

    async def gpu_series(
        self,
        minutes: int = 60,
        t_from: Optional[str] = None,
        t_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Per-model GPU load time series, proxied read-only from the exporters.

        With from/to (epoch seconds or ISO) the exporter serves the window from
        its JSONL day files — that's what makes sessions reviewable after the
        fact; otherwise it serves the live ring. When PGFR_GPU_URL_THOR is set,
        the same window is fetched concurrently from the Thor (Jetson) exporter
        and attached under "thor" — one clock, two hosts.
        """
        s = self.settings

        def _series_url(base: str) -> str:
            if t_from and t_to:
                return f"{base}/v1/gpu/series?from={quote(t_from)}&to={quote(t_to)}"
            capped = max(1, min(int(minutes), 24 * 60))
            return f"{base}/v1/gpu/series?minutes={capped}"

        async with httpx.AsyncClient(timeout=s.timeout_s) as client:
            tasks = []
            if s.gpu_url:
                tasks.append(self._get_json(client, _series_url(s.gpu_url)))
            if s.gpu_url_thor:
                tasks.append(self._get_json(client, _series_url(s.gpu_url_thor)))
            results = list(await asyncio.gather(*tasks)) if tasks else []
        body: Optional[Dict[str, Any]] = None
        if s.gpu_url:
            body = results.pop(0) if results else None
        if body is None:
            body = {"samples": [], "error": (
                "GPU telemetry is not configured" if not s.gpu_url else "gpu exporter unreachable"
            )}
        if s.gpu_url_thor:
            thor = results.pop(0) if results else None
            body["thor"] = thor if thor is not None else {
                "samples": [], "error": "thor gpu exporter unreachable"}
        return body

    async def gpu_for_mission(self, mission_id: str) -> Dict[str, Any]:
        """GPU load during one mission: journal window -> exporter file slice.

        The seam journal stays the single source of session truth — the window
        is derived from the mission's first/last op timestamps (padded 30 s
        each side, plus the last op's duration), never stored twice.
        """
        detail = await self.mission_detail(mission_id, limit=500)
        ops = detail.get("operations") or []
        stamps = sorted(str(o.get("ts")) for o in ops if o.get("ts"))
        telemetry_basis = "seam-mission"
        chat_session: Optional[Dict[str, Any]] = None
        if not stamps:
            chat_session = await self.chat_session_for_mission(mission_id)
            if not chat_session:
                return {"samples": [], "mission_id": mission_id,
                        "error": detail.get("error") or "mission has no timestamped ops"}
            telemetry_basis = "chat-session"

        def _parse(ts: Any) -> Optional[datetime]:
            if isinstance(ts, (int, float)):
                try:
                    return datetime.fromtimestamp(float(ts), timezone.utc)
                except (OSError, OverflowError, ValueError):
                    return None
            try:
                parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                return None

        if chat_session is not None:
            start = _parse(chat_session.get("created"))
            end = (
                datetime.now(timezone.utc)
                if chat_session.get("active") is True
                else _parse(chat_session.get("updated"))
            )
        else:
            start = _parse(stamps[0])
            end = _parse(stamps[-1])
        if start is None or end is None:
            return {"samples": [], "mission_id": mission_id, "error": "bad op timestamps"}
        last_duration = 0.0
        if stamps:
            for o in ops:
                if str(o.get("ts")) == stamps[-1]:
                    try:
                        last_duration = max(last_duration, float(o.get("duration_s") or 0))
                    except (TypeError, ValueError):
                        pass
        start -= timedelta(seconds=30)
        end += timedelta(seconds=last_duration + 30)
        body = await self.gpu_series(t_from=start.isoformat(), t_to=end.isoformat())
        body["mission_id"] = mission_id
        body["telemetry_basis"] = telemetry_basis
        body["window"] = {"from": start.isoformat(), "to": end.isoformat()}
        return body

    async def chat_sessions(self) -> Dict[str, Any]:
        """Read-only proxy for the session identities shown by PGFR Chat."""
        if not self.settings.chat_url:
            return {"sessions": [], "error": "PGFR_CHAT_URL not set"}
        async with httpx.AsyncClient(timeout=self.settings.timeout_s) as client:
            body = await self._get_json(client, f"{self.settings.chat_url}/api/sessions")
        return body if body is not None else {"sessions": [], "error": "PGFR Chat unreachable"}

    async def chat_session_for_mission(self, mission_id: str) -> Optional[Dict[str, Any]]:
        """Resolve a ``chat-*`` mission to its persisted PGFR Chat session."""
        if not self.settings.chat_url or not mission_id.startswith("chat-"):
            return None
        session_id = mission_id[5:]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
            return None
        url = f"{self.settings.chat_url}/api/sessions/{quote(session_id, safe='')}"
        async with httpx.AsyncClient(timeout=self.settings.timeout_s) as client:
            body = await self._get_json(client, url)
        if not isinstance(body, dict) or body.get("mission_id") != mission_id:
            return None
        return body

    async def snapshot(self) -> Dict[str, Any]:
        async with self._lock:
            return self._snapshot

    # ------------------------------------------------------------- missions
    async def missions(self, limit: int = 20) -> Dict[str, Any]:
        s = self.settings
        limit = max(1, min(int(limit), 200))
        async with httpx.AsyncClient(timeout=s.timeout_s) as client:
            body = await self._get_json(client, f"{s.seam_url}/v1/missions?limit={limit}")
        return body if body is not None else {"missions": [], "error": "seam unreachable"}

    async def mission_detail(self, mission_id: str, limit: int = 200) -> Dict[str, Any]:
        s = self.settings
        limit = max(1, min(int(limit), 500))
        # Encode the id — it is client-controlled and must not inject query
        # params into the internal seam read endpoint.
        mid = quote(mission_id, safe="")
        async with httpx.AsyncClient(timeout=s.timeout_s) as client:
            body = await self._get_json(client, f"{s.seam_url}/v1/missions/{mid}?limit={limit}")
        return body if body is not None else {"operations": [], "error": "seam unreachable"}

    async def inspect(self, limit: int = 30) -> Dict[str, Any]:
        """Flat, newest-first audit feed across ALL missions, with full detail.

        The seam's /v1/missions/{id} returns full-detail operations (request,
        result, verified, frame, timing); we flatten the most recent missions
        into one feed so the Inspector shows the whole chain per op.
        """
        s = self.settings
        limit = max(1, min(int(limit), 100))
        summaries = (await self.missions(limit=25)).get("missions", [])
        ops: List[Dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=s.timeout_s) as client:
            for m in summaries:
                mid = m.get("mission_id")
                if not mid:
                    continue
                body = await self._get_json(
                    client, f"{s.seam_url}/v1/missions/{quote(str(mid), safe='')}?limit=100"
                )
                for op in (body or {}).get("operations", []):
                    op.setdefault("mission_id", mid)
                    ops.append(op)
        ops.sort(key=lambda o: str(o.get("ts", "")), reverse=True)
        ops = ops[:limit]
        total = len(ops)
        dispatches = [o for o in ops if o.get("op") == "dispatch" or o.get("action")]
        verified = sum(1 for o in dispatches if o.get("verified") is True)
        return {
            "operations": ops,
            "summary": {
                "shown": total,
                "missions": len(summaries),
                "dispatches": len(dispatches),
                "verified_dispatches": verified,
                "with_frame": sum(1 for o in ops if o.get("frame")),
            },
        }
