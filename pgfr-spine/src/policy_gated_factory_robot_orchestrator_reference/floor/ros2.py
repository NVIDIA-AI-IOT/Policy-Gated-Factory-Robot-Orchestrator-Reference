# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ROS 2 floor backend — drives the Isaac Sim cell over ROS 2 (the HIL body).

Sense:   ``/pgfr/floor_state`` (world JSON) + ``/<cam>/image_raw`` (3 cameras).
Command: publish ``/pgfr/command`` (JSON action) → await matching ``/pgfr/result``.
Motion runs *inside* Isaac (high-level seam); this backend only sends actions and
reads results/state. ``rclpy`` is imported lazily so this module (and the mock/CI
path) imports fine on a host without ROS; it is required only once a method runs.
The contract is documented in docs/floor-ros2-contract.md.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

from policy_gated_factory_robot_orchestrator_reference.action_endpoints.base import (
    ActionEndpoint,
    ActionResult,
)
from policy_gated_factory_robot_orchestrator_reference.floor.scene import Scene
from policy_gated_factory_robot_orchestrator_reference.input_sources.base import InputSource
from policy_gated_factory_robot_orchestrator_reference.types import Capability, EndpointState

# Logical coverage region -> camera topic prefix. The agent's inspect/perceive
# target selects the viewpoint.  Keep the native-DROID 320x180 inspect stream
# for conveyor checks; tote verification uses a separate 640x360 publisher from
# the same pinned RackCam_B pose so it cannot alter the policy visual domain.
_CAMERA_FOR_REGION = {
    "conveyor_1": "inspect_cam",  # RackCam_B: closer top-down — cubes resolve better than table_cam
    "table_1": "table_cam",
    "rack_1": "rack_cam",
    "tote": "inspect_vlm_cam",
    "conveyor_2": "outside_right_cam",  # right workcell (franka_right zone)
    "tote_r": "outside_right_cam",
}

# Region crops (fractions of the frame): a 5cm cube is ~30px full-frame — below
# the quantized 8B VLM's reliable resolution. Cropping to the region ~5x's the
# object before the VLM sees it. Boxes calibrated on the contract-view framing.
_CROP_FOR_REGION: dict[str, tuple[float, float, float, float]] = {
    "conveyor_1": (0.20, 0.50, 0.98, 0.95),
    "tote":       (0.08, 0.00, 0.55, 0.30),
    "conveyor_2": (0.20, 0.50, 0.98, 0.95),
    "tote_r":     (0.08, 0.00, 0.55, 0.30),
    "rack_1":     (0.22, 0.00, 1.00, 1.00),  # full right edge: the far shelf spot sits there edge-on
}
_TOTE_SLOTS = ("red", "blue", "green")
_LAST_FRAME: bytes | None = None


def take_last_frame() -> bytes | None:
    """Pop the most recent VLM input frame (journal evidence). None if no camera read."""
    global _LAST_FRAME
    f = _LAST_FRAME
    _LAST_FRAME = None
    return f


@dataclass
class _ImageSnapshot:
    """An image source's snapshot; PerceptionAgent reads ``.image_bytes``."""

    image_bytes: bytes


def _image_to_jpeg(msg: Any, crop: tuple[float, float, float, float] | None = None) -> bytes:
    """sensor_msgs/Image -> JPEG bytes (numpy + Pillow; only on the live ROS path).
    ``crop`` is a fractional (x0, y0, x1, y1) box applied before encoding."""
    import numpy as np
    from PIL import Image as PILImage

    h, w = int(msg.height), int(msg.width)
    arr = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    ch = arr.size // (h * w) if h and w else 3
    arr = arr.reshape(h, w, ch)
    if crop is not None:
        x0, y0, x1, y1 = crop
        arr = arr[int(y0 * h):max(int(y1 * h), int(y0 * h) + 8),
                  int(x0 * w):max(int(x1 * w), int(x0 * w) + 8)]
        # normalize to ViT-patch-friendly dims (mult of 28, upscaled ~2x): odd
        # crop sizes hit a vLLM vision-token edge case (500s); regular dims dodge it
        ch2, cw2 = arr.shape[0], arr.shape[1]
        scale = max(1.0, min(2.0, 560.0 / max(1, min(ch2, cw2))))
        nh = max(28, int(round(ch2 * scale / 28.0)) * 28)
        nw = max(28, int(round(cw2 * scale / 28.0)) * 28)
        img = PILImage.fromarray(arr[..., :3])
        arr = np.asarray(img.resize((nw, nh), PILImage.BILINEAR))
    if (msg.encoding or "rgb8").lower().startswith("bgr"):
        arr = arr[:, :, ::-1]
    buf = io.BytesIO()
    if ch >= 3:
        PILImage.fromarray(arr[:, :, :3], "RGB").save(buf, format="JPEG", quality=85)
    else:
        PILImage.fromarray(arr.reshape(h, w), "L").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


class _Bridge:
    """One rclpy node: publishes /pgfr/command, caches latest /pgfr/result + /pgfr/floor_state.

    Spun on a daemon executor thread so the cache fills while the caller blocks in
    ``send``. One process-lived instance per backend (created lazily on first use).
    """

    def __init__(self) -> None:
        import rclpy  # lazy: ROS only needed when the backend actually runs
        from std_msgs.msg import String

        self._rclpy = rclpy
        self._String = String
        if not rclpy.ok():
            rclpy.init(args=None)
        self.node = rclpy.create_node("pgfr_floor_backend")
        self._cmd_pub = self.node.create_publisher(String, "/pgfr/command", 10)
        self._lock = threading.Lock()
        self._last_result: dict[str, Any] | None = None
        self._results: dict[str, dict[str, Any]] = {}
        self._pending: dict[str, dict] = {}
        self._state: dict[str, Any] = {}
        self._images: dict[str, Any] = {}
        self._img_subs: dict[str, Any] = {}
        self.node.create_subscription(String, "/pgfr/result", self._on_result, 10)
        self.node.create_subscription(String, "/pgfr/floor_state", self._on_state, 10)
        self._exec = rclpy.executors.SingleThreadedExecutor()
        self._exec.add_node(self.node)
        threading.Thread(target=self._exec.spin, daemon=True).start()

    def _on_result(self, msg: Any) -> None:
        try:
            r = json.loads(msg.data)
        except Exception:
            r = {"raw": msg.data}
        with self._lock:
            # the cell echoes goal_id nested under args; accept both shapes
            gid = (r.get("goal_id") or (r.get("args") or {}).get("goal_id")) if isinstance(r, dict) else None
            if gid:
                self._results[gid] = r
            else:
                self._last_result = r

    def _on_state(self, msg: Any) -> None:
        try:
            self._state = json.loads(msg.data)
            self._state_ts = time.time()
        except Exception:
            pass

    def health(self) -> dict[str, Any]:
        """Liveness of the ROS side: context validity + signal freshness (seconds)."""
        import rclpy

        now = time.time()
        state_ts = getattr(self, "_state_ts", None)
        return {
            "ros_ok": bool(rclpy.ok()),
            "floor_state_age_s": round(now - state_ts, 2) if state_ts else None,
            "camera_age_s": {
                t.strip("/").split("/")[0]: round(now - ts, 2)
                for t, ts in getattr(self, "_image_ts", {}).items()
            },
        }

    def floor_state(self, timeout: float = 5.0) -> dict[str, Any]:
        """Latest world-state JSON, waiting briefly for the first frame after connect."""
        end = time.time() + timeout
        while not self._state and time.time() < end:
            time.sleep(0.05)
        return dict(self._state)

    def latest_image_jpeg(self, topic: str, timeout: float = 15.0, crop: tuple | None = None) -> bytes:
        """Latest frame on an image topic as JPEG. Lazy-subscribes — image streams are
        heavy, so the deterministic floor path never pays for them; live/ROS only.
        The FIRST call on a topic is cold: cross-host DDS discovery + first frame can take
        ~6-8s, so the timeout must exceed that or the first verify/perceive on a camera
        errors with 'no image within Ns' (it would then warm up and work on the retry)."""
        from sensor_msgs.msg import Image  # lazy: ROS only

        with self._lock:
            if topic not in self._img_subs:
                if not hasattr(self, "_image_ts"):
                    self._image_ts = {}

                def _store(m: Any, t: str = topic) -> None:
                    self._images[t] = m
                    self._image_ts[t] = time.time()

                self._img_subs[topic] = self.node.create_subscription(Image, topic, _store, 10)
            # Freshness contract: a perceive/verify must describe the scene NOW.
            # Drop the cached frame and wait for one that arrives after this call —
            # a dead stream then raises loudly instead of silently serving the past.
            self._images.pop(topic, None)
        end = time.time() + timeout
        while time.time() < end:
            with self._lock:
                msg = self._images.get(topic)
            if msg is not None:
                return _image_to_jpeg(msg, crop)
            time.sleep(0.05)
        raise RuntimeError(f"no image on {topic} within {timeout}s")

    def send(self, cmd: dict[str, Any], timeout: float = 180.0) -> dict[str, Any]:
        """Publish one command; block until the matching /pgfr/result arrives (or timeout).

        180s covers the slowest action (the AMR haul's multi-phase drive)."""
        # Wait for the cell to discover our publisher first: a one-shot command
        # published before the subscription matches is silently dropped — and we must
        # not resend (a duplicate move would re-sort). 5s covers DDS discovery.
        disc = time.time() + 5.0
        while self._cmd_pub.get_subscription_count() < 1 and time.time() < disc:
            time.sleep(0.05)
        # Action-protocol semantics over the JSON transport (T4): every command
        # carries a goal_id and the cell echoes it in the result, so results are
        # matched exactly. NOTE: the cell does NOT dedupe on goal_id — never
        # republish a command assuming idempotency.
        goal_id = uuid.uuid4().hex[:12]
        cmd = dict(cmd)
        cmd["goal_id"] = goal_id
        with self._lock:
            self._last_result = None
            self._results.pop(goal_id, None)
        self._cmd_pub.publish(self._String(data=json.dumps(cmd)))
        end = time.time() + timeout
        while time.time() < end:
            with self._lock:
                r = self._results.pop(goal_id, None)
                legacy = self._last_result
            if r is not None:
                return r   # exact goal_id match — the only fully trusted path
            if legacy is not None:
                # legacy node without goal_id echo: match the action name (old guard)
                res_action = legacy.get("action") or (legacy.get("args") or {}).get("action")
                if res_action == cmd.get("action"):  # no None wildcard: an anonymous
                    # result (e.g. inspect without goal echo) must never satisfy a move
                    with self._lock:
                        self._last_result = None
                    return legacy
            time.sleep(0.05)
        return {"success": False, "verified": False, "reason": "timeout waiting for /pgfr/result"}

    _ASYNC_TTL_S = 3600.0  # completed goals swept after an hour

    def _sweep_async(self) -> None:
        """Drop completed async goals older than the TTL (holds self._lock)."""
        cutoff = time.time() - self._ASYNC_TTL_S
        for gid in [g for g, meta in self._pending.items()
                    if g in self._results and meta["ts"] < cutoff]:
            self._pending.pop(gid, None)
            self._results.pop(gid, None)

    def pending_goals(self) -> list[str]:
        """Async goals dispatched but not yet resolved (queue-depth gauge)."""
        with self._lock:
            return [g for g in self._pending if g not in self._results]

    def send_async(self, cmd: dict, queue: bool = False) -> dict:
        """Publish one command and return its goal_id immediately. Refuses when
        another async goal is still in flight unless ``queue=True`` — the cell
        executes strictly one task at a time, so silent stacking means surprise
        sequential motions. Returns {"goal_id"} or {"refused": reason}."""
        with self._lock:
            self._sweep_async()
            inflight = [g for g in self._pending if g not in self._results]
        if inflight and not queue:
                return {"refused": f"busy: goal {inflight[0]} still in flight — pass "
                                   "queue=true to stack intentionally",
                        "busy_goal": inflight[0]}
        disc = time.time() + 5.0
        while self._cmd_pub.get_subscription_count() < 1 and time.time() < disc:
            time.sleep(0.05)
        if self._cmd_pub.get_subscription_count() < 1:
            return {"refused": "cell not reachable (no /pgfr/command subscriber) — "
                               "command NOT sent"}
        goal_id = uuid.uuid4().hex[:12]
        cmd = dict(cmd)
        cmd["goal_id"] = goal_id
        with self._lock:
            self._results.pop(goal_id, None)
            self._pending[goal_id] = {"cmd": cmd, "ts": time.time()}
        self._cmd_pub.publish(self._String(data=json.dumps(cmd)))
        return {"goal_id": goal_id}

    def poll_result(self, goal_id: str) -> dict | None:
        """Non-destructive read of an async goal's result; None while running.
        Unknown goal ids raise KeyError so a typo can't read as 'still running'."""
        with self._lock:
            self._sweep_async()
            if goal_id in self._results:
                return self._results[goal_id]
            if goal_id not in self._pending:
                raise KeyError(goal_id)
            return None

    def pending_age_s(self, goal_id: str) -> float | None:
        with self._lock:
            meta = self._pending.get(goal_id)
            return None if meta is None else max(0.0, time.time() - meta["ts"])


class _Ros2Endpoint(ActionEndpoint):
    """An Isaac robot exposed as an ActionEndpoint; execute() sends one /pgfr/command."""

    def __init__(self, bridge: _Bridge, ep_id: str, kind: str, battery: float | None,
                 capabilities: list[Capability]) -> None:
        self._bridge = bridge
        self.id = ep_id
        self.type = kind
        self.pose = None
        self.capabilities = capabilities
        self._battery = battery

    async def execute(self, capability_name: str, goal_args: dict[str, Any]) -> ActionResult:
        cmd: dict[str, Any] = {"action": capability_name, "endpoint": self.id}
        cmd.update({k: v for k, v in goal_args.items() if v is not None})
        r = await asyncio.to_thread(self._bridge.send, cmd)
        return ActionResult(
            success=bool(r.get("success")),
            result={"verified": bool(r.get("verified")), "moved": goal_args, **r},
            reason=r.get("reason"),
        )

    def state(self) -> EndpointState:
        return EndpointState(busy=False, battery_pct=100.0 if self._battery is None else self._battery * 100.0)


class _Ros2Camera(InputSource):
    """A camera topic exposed as a perception InputSource (latest RGB frame)."""

    def __init__(self, bridge: _Bridge, source_id: str, region: str | None,
                 crop: tuple[float, float, float, float] | None = None) -> None:
        self._bridge = bridge
        self.id = source_id
        self.modality = "image"
        self.coverage_region = region
        self._crop = crop

    async def snapshot(self) -> _ImageSnapshot:
        # Latest RGB frame from the camera's ROS topic, as JPEG, for the VLM.
        # One retry after a settle: verifies fired right after robot motion hit
        # transient render starvation (GPU load spike) and timed out, then the
        # camera recovered seconds later — observed on rack_cam post-haul.
        try:
            jpeg = await asyncio.to_thread(self._bridge.latest_image_jpeg, f"/{self.id}/image_raw", 15.0, self._crop)
        except RuntimeError:
            await asyncio.sleep(5.0)
            jpeg = await asyncio.to_thread(self._bridge.latest_image_jpeg, f"/{self.id}/image_raw", 15.0, self._crop)
        global _LAST_FRAME
        _LAST_FRAME = jpeg   # journaled as the evidence for this perceive/verify
        return _ImageSnapshot(image_bytes=jpeg)

    def query_kinds(self) -> list[str]:
        return ["scene", "image"]


_ARM_CAPS = [
    Capability(name="move", description="Sort a colored block into its tote compartment.",
               goal_schema={"type": "object", "required": ["color", "source", "destination"]},
               result_schema={"type": "object"}),
    Capability(name="pick_and_place", description="Pick an object and place it at a target.",
               goal_schema={"type": "object", "required": ["object_id", "target_id"]},
               result_schema={"type": "object"}),
]
_AMR_CAPS = [
    Capability(name="pick_and_place", description="Haul an object (e.g. the tote) to a target.",
               goal_schema={"type": "object", "required": ["object_id", "target_id"]},
               result_schema={"type": "object"}),
    Capability(name="navigate_to", description="Drive the base to a named location.",
               goal_schema={"type": "object", "required": ["location_id"]},
               result_schema={"type": "object"}),
]


class Ros2FloorBackend:
    """Live floor backed by the Isaac cell over ROS 2 (see module docstring)."""

    def __init__(self, scene: Scene) -> None:
        self._scene = scene
        self._b: _Bridge | None = None

    def _bridge(self) -> _Bridge:
        if self._b is None:
            self._b = _Bridge()
        return self._b

    def endpoints(self) -> list[ActionEndpoint]:
        b = self._bridge()
        return [
            _Ros2Endpoint(
                b,
                e.id,
                e.kind,
                e.battery,
                e.capabilities or (_AMR_CAPS if "base" in e.kind else _ARM_CAPS),
            )
            for e in self._scene.endpoints
        ]

    def health(self) -> dict[str, Any]:
        """Start the bridge on the first health probe and report ROS freshness."""
        return self._bridge().health()

    def sources(self) -> list[InputSource]:
        # one source PER REGION (regions sharing a camera get distinct crops);
        # the bridge dedups the underlying topic subscriptions.
        b = self._bridge()
        return [_Ros2Camera(b, cam, region, _CROP_FOR_REGION.get(region))
                for region, cam in _CAMERA_FOR_REGION.items()]

    def observe(self, target: str) -> dict[str, Any]:
        """Structured observation of ``target`` from /pgfr/floor_state (perceive contract)."""
        st = self._bridge().floor_state()
        conveyor = list(st.get("conveyor_1", []))
        tote = dict(st.get("tote", {}))
        on_rack = bool(st.get("tote_on_rack", False))
        racks = {f"tote_{c}": (1 if c in tote else 0) for c in _TOTE_SLOTS}
        racks["rack_1"] = 1 if on_rack else 0
        if target in ("conveyor_1", "table_1", "table"):
            return {
                "target": target,
                "blocks_on_table": [{"item": "block", "color": c} for c in conveyor],
                "counts": dict(Counter(conveyor)),
                "racks": racks,
                "sorted": len(conveyor) == 0,
                # geometry for optimal-arm selection: pick the endpoint whose base is
                # closest to the cube (arm_positions vs cube_positions), then dispatch to it.
                "arm_positions": st.get("arms") or {},
                "cube_positions": st.get("cube_positions") or {},
            }
        return {"target": target, "tote": tote, "tote_on_rack": on_rack, "racks": racks}


# --- live floor primitives, shared by the CLI ros2 path and the serve HTTP service ---
# A "live" backend (Ros2FloorBackend) exposes observe() + executable endpoints; these
# turn one request into the JSON payloads the CLI prints and the service returns, so
# both transports go through one code path (no per-call duplication).

def is_live_backend(backend: Any) -> bool:
    """True for a backend driven over ROS 2 (observe() + executable endpoints)."""
    return callable(getattr(backend, "observe", None))


def live_floor_state(backend: Any) -> dict[str, Any]:
    """The floor's authoritative world state + its endpoints.

    The route's contract is "world state" (see the service docstring): the cell
    publishes it on /pgfr/floor_state — blocks on the table, tote contents,
    whether each tote is shelved. Returning only the endpoint list left every
    caller (agent, MCP, workflows) blind to the floor it is supposed to reason
    about, so counts and completion checks had nothing authoritative to read.
    Endpoints stay under "endpoints"; a bridge hiccup degrades to endpoints
    only rather than failing the call.
    """
    payload: dict[str, Any] = {}
    try:
        world = backend._bridge().floor_state()
        if isinstance(world, dict):
            payload.update(world)
    except Exception:
        pass
    payload["endpoints"] = [{"id": e.id, "kind": e.type} for e in backend.endpoints()]
    return payload


def _perceive_region(target: str) -> str:
    """Resolve a target to its region-specific visual source.

    ``sources()`` intentionally exposes one source per region because regions
    sharing a physical camera use different crops.  Preserve the requested
    region so, for example, ``tote_r`` cannot silently select
    ``conveyor_2``'s crop merely because both use ``outside_right_cam``.
    """
    return target


def _ground_truth_on_rack(symbolic: dict[str, Any]) -> bool:
    return bool(symbolic.get("tote_on_rack", symbolic.get("racks", {}).get("rack_1", 0)))


def _perceive_discrepancies(symbolic: dict[str, Any], vision: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Where the VLM read disagrees with symbolic ground truth. Only compared when the VLM
    actually asserted a value (parsed, non-null) so a partial camera view doesn't manufacture
    phantom conflicts. Ground truth always stays authoritative; this is the flag, not a vote."""
    if not vision or not vision.get("parse_ok"):
        return []
    disc: list[dict[str, Any]] = []
    # Only the rack camera (region rack_1) actually sees the rack; other regions' cameras
    # can't judge tote_on_rack, so ignore their guess instead of manufacturing a phantom flag.
    if vision.get("region") == "rack_1":
        v_on_rack = vision.get("tote_on_rack")
        if v_on_rack is not None:
            gt = _ground_truth_on_rack(symbolic)
            if bool(v_on_rack) != gt:
                disc.append({"field": "tote_on_rack", "ground_truth": gt, "vision": bool(v_on_rack)})
    if "blocks_on_table" in symbolic:
        gt_conv = sorted(b["color"] for b in symbolic.get("blocks_on_table", []))
        v_conv = sorted(c["color"] for c in vision.get("cubes_visible", []) if c.get("where") == "conveyor")
        if v_conv and v_conv != gt_conv:
            disc.append({"field": "conveyor_colors", "ground_truth": gt_conv, "vision": v_conv})
    return disc


async def _vision_for_target(backend: Any, target: str, vlm: Any) -> dict[str, Any] | None:
    """Best-effort visual read of ``target``'s region; None when no VLM is configured, and a
    parse_ok=False stub on any error — vision must never break the authoritative symbolic read."""
    from policy_gated_factory_robot_orchestrator_reference.agents.perception import PerceptionAgent

    if vlm is None:
        from policy_gated_factory_robot_orchestrator_reference.clients.vlm import vlm_from_env

        vlm = vlm_from_env()
    if vlm is None:
        return None
    try:
        region = _perceive_region(target)
        return await PerceptionAgent(backend.sources(), vlm).observe_visual(region)
    except Exception as exc:  # noqa: BLE001 - vision is advisory; degrade, don't raise
        return {"error": str(exc), "parse_ok": False, "cubes_visible": [], "tote_on_rack": None}


async def live_perceive(backend: Any, target: str, vlm: Any = None) -> dict[str, Any]:
    """Symbolic observation of ``target`` (authoritative) fused with a vision read of the same
    region. On any VLM-vs-ground-truth conflict the symbolic values stay in the payload and the
    disagreement is reported under ``vision_discrepancies`` — vision informs, ground truth decides.
    Degrades to symbolic-only when ``PGFR_VLM_URL`` is unset or the VLM errors."""
    symbolic = backend.observe(target)
    vision = await _vision_for_target(backend, target, vlm)
    if os.environ.get("PGFR_PERCEIVE_MODE", "fused") == "vision_only":
        # Vision stands on its own: no object ground truth in the payload. Robot
        # poses stay (they come from the robots, not the world model); dispatch
        # verification is untouched — this only changes what perceive REPORTS.
        return {
            "target": symbolic.get("target", target),
            "mode": "vision_only",
            "arm_positions": symbolic.get("arm_positions", {}),
            "vision": vision,
        }
    discrepancies = _perceive_discrepancies(symbolic, vision)
    return {
        **symbolic,
        "vision": vision,
        "vision_discrepancies": discrepancies,
        "vision_agrees": bool(vision and vision.get("parse_ok") and not discrepancies),
    }


async def live_dispatch(
    backend: Any, endpoint: str, action: str, goal_args: dict[str, Any]
) -> dict[str, Any]:
    """Send one action to one endpoint; return the act-and-confirm result payload."""
    from policy_gated_factory_robot_orchestrator_reference.agents.action import ActionAgent

    # The guards can use the Isaac ROS bridge's richer symbolic state, but the
    # ActionEndpoint contract does not require that private bridge. Alternate
    # live backends must remain dispatchable instead of crashing here.
    guard_state: dict[str, Any] | None = None
    bridge_factory = getattr(backend, "_bridge", None)
    if callable(bridge_factory):
        state_reader = getattr(bridge_factory(), "floor_state", None)
        if callable(state_reader):
            guard_state = state_reader() or {}

    # State guards run before actuation.  They make independently-planning Chat
    # sessions idempotent: a stale mission cannot pick an object another
    # mission already sorted, nor send an arm after a tote that has left the
    # workcell for the rack.
    if (
        guard_state is not None
        and action == "move"
        and goal_args.get("color")
        and endpoint.startswith("franka")
    ):
        st = guard_state
        tote_flag = (
            "tote_r_on_rack" if endpoint == "franka_right" else "tote_on_rack"
        )
        if bool(st.get(tote_flag)):
            return {
                "dispatched": False,
                "status": "refused",
                "reason": (
                    f"state guard: {tote_flag}=true; the destination tote is "
                    "already on rack_1"
                ),
            }
        arms = {"franka_left": 3.64, "franka_right": 4.965}
        cubes = [c for c in st.get("cubes", []) if c.get("color") == goal_args["color"]
                 and c.get("where") == "conveyor"]
        if not cubes:
            return {
                "dispatched": False,
                "status": "refused",
                "reason": (
                    "state guard: no matching "
                    f"{goal_args['color']} object remains on the conveyor"
                ),
            }
        if cubes and endpoint in arms:
            # Zone guard: a move dispatched to an arm ~1m+ from its cube while
            # another arm sits beside it is a mis-selection (watched live:
            # blue -> franka_left, 47s timeout). Refuse fast with guidance
            # instead of letting it time out.
            # Duplicate colors exist in the two-arm scene.  Resolve the
            # requested arm's nearest matching conveyor object before applying
            # the cross-zone refusal; cubes[0] always selected the left object
            # and made every legitimate right-arm request impossible.
            cube = min(cubes, key=lambda c: abs(float(c["x"]) - arms[endpoint]))
            cx = float(cube["x"])
            chosen_d = abs(cx - arms[endpoint])
            best = min(arms, key=lambda a: abs(cx - arms[a]))
            if chosen_d > 0.8 and best != endpoint:
                return {
                    "dispatched": False,
                    "status": "refused",
                    "reason": (
                        f"zone guard: the {goal_args['color']} cube (x={cx:.2f}) is in "
                        f"{best}'s zone — dispatch to {best}"
                    ),
                }
    elif (
        guard_state is not None
        and action == "pick_and_place"
        and goal_args.get("target_id") == "rack_1"
    ):
        object_id = str(goal_args.get("object_id") or "")
        flag = {
            "tote": "tote_on_rack",
            "tote_r": "tote_r_on_rack",
        }.get(object_id)
        if flag:
            if bool(guard_state.get(flag)):
                return {
                    "dispatched": False,
                    "status": "refused",
                    "reason": (
                        f"state guard: {flag}=true; {object_id} is already on rack_1"
                    ),
                }

    agent = ActionAgent(backend.endpoints())
    r = await agent.execute(endpoint, action, goal_args)
    verified = bool((r.get("result") or {}).get("verified")) if r["success"] else False
    return {
        "dispatched": bool(r["success"]),
        "endpoint": endpoint,
        "action": action,
        "verified": verified,
        "moved": goal_args,
        "reason": r.get("reason"),
    }


async def live_dispatch_parallel(
    backend: Any, moves: list[dict[str, Any]]
) -> dict[str, Any]:
    """Execute one validated left/right GR00T pair as an atomic cell task.

    PGFR Spine retains its single shared-floor lock. The two arm policies run
    concurrently only inside Isaac's move_pair executor, so no unrelated
    command can interleave with the pair.
    """
    if len(moves) != 2:
        raise ValueError("parallel dispatch requires exactly two moves")
    by_endpoint = {str(move.get("endpoint") or ""): dict(move) for move in moves}
    if set(by_endpoint) != {"franka_left", "franka_right"}:
        raise ValueError("parallel dispatch requires one move for each Franka arm")

    bridge = backend._bridge()
    state = bridge.floor_state() or {}
    arm_x = {"franka_left": 3.64, "franka_right": 4.965}
    for endpoint, move in by_endpoint.items():
        color = str(move.get("color") or "").lower()
        tote_flag = "tote_r_on_rack" if endpoint == "franka_right" else "tote_on_rack"
        if bool(state.get(tote_flag)):
            return {
                "dispatched": False,
                "action": "move_pair",
                "verified": False,
                "parallel_results": {},
                "reason": (
                    f"state guard: {tote_flag}=true; the destination tote is "
                    "already on rack_1"
                ),
            }
        cubes = [
            cube
            for cube in state.get("cubes", [])
            if cube.get("color") == color and cube.get("where") == "conveyor"
        ]
        if not cubes:
            return {
                "dispatched": False,
                "action": "move_pair",
                "verified": False,
                "parallel_results": {},
                "reason": f"state guard: no matching {color} object remains on the conveyor",
            }
        cube = min(cubes, key=lambda item: abs(float(item["x"]) - arm_x[endpoint]))
        cube_x = float(cube["x"])
        chosen_distance = abs(cube_x - arm_x[endpoint])
        best_endpoint = min(arm_x, key=lambda arm: abs(cube_x - arm_x[arm]))
        if chosen_distance > 0.8 and best_endpoint != endpoint:
            return {
                "dispatched": False,
                "action": "move_pair",
                "verified": False,
                "parallel_results": {},
                "reason": (
                    f"zone guard: the {color} object (x={cube_x:.2f}) is in "
                    f"{best_endpoint}'s zone — pair not dispatched"
                ),
            }

    ordered_moves = [by_endpoint[arm] for arm in ("franka_left", "franka_right")]
    cmd = {
        "action": "move_pair",
        "endpoint": "franka_pair",
        "moves": [
            {"action": "move", **move, "backend": "groot"}
            for move in ordered_moves
        ],
    }
    result = await asyncio.to_thread(bridge.send, cmd, 240.0)
    result_args = result.get("args") if isinstance(result.get("args"), dict) else {}
    parallel_results = result_args.get("parallel_results") or {}
    independent_b1_verified = (
        result_args.get("independent_b1_verified") is True
    )
    return {
        "dispatched": bool(result.get("success")),
        "endpoint": "franka_pair",
        "action": "move_pair",
        "verified": bool(result.get("verified")),
        "independent_b1_verified": independent_b1_verified,
        "per_arm_relay_ports": result_args.get("per_arm_relay_ports") or {},
        "parallel_results": parallel_results,
        "moved": ordered_moves,
        "reason": result.get("reason"),
    }


async def live_dispatch_async(
    backend: Any, endpoint: str, action: str, goal_args: dict[str, Any]
) -> dict[str, Any]:
    """Fire-and-track: publish the command, return its goal_id immediately.
    Poll with live_task_status. The physics act-and-confirm still happens in
    the cell; only the WAITING moved out of the request."""
    cmd: dict[str, Any] = {"action": action, "endpoint": endpoint}
    queue = bool(goal_args.pop("queue", False))
    cmd.update({k: v for k, v in goal_args.items() if v is not None})
    bridge = backend._bridge()
    r = await asyncio.to_thread(bridge.send_async, cmd, queue)
    if "refused" in r:
        return {"dispatched": False, "status": "refused", "reason": r["refused"],
                "endpoint": endpoint, "action": action, **({"busy_goal": r["busy_goal"]} if "busy_goal" in r else {})}
    return {
        "dispatched": True,
        "goal_id": r["goal_id"],
        "status": "running",
        "endpoint": endpoint,
        "action": action,
        "moved": goal_args,
        "note": "async dispatch: poll /v1/tasks/{goal_id} for the verified result",
    }


async def live_task_status(backend: Any, goal_id: str) -> dict[str, Any]:
    """Status of an async goal: running | done (+ full cell result) | unknown."""
    bridge = backend._bridge()
    try:
        r = bridge.poll_result(goal_id)
    except KeyError:
        return {"goal_id": goal_id, "status": "unknown",
                "reason": "no such goal_id (typo, restart, or sync dispatch)"}
    if r is None:
        age = bridge.pending_age_s(goal_id) or 0.0
        if age > 420.0:  # past any plausible action+queue window
            return {
                "goal_id": goal_id,
                "status": "stale",
                "age_s": round(age, 1),
                "reason": (
                    f"no result after {age:.0f}s — cell may have dropped it; "
                    "verify floor state before any retry"
                ),
            }
        return {"goal_id": goal_id, "status": "running", "age_s": round(age, 1)}
    return {
        "goal_id": goal_id,
        "status": "done",
        "success": bool(r.get("success")),
        "verified": bool(r.get("verified")),
        "reason": r.get("reason"),
    }


async def live_verify(
    backend: Any, predicate: str, region: str | None = None, vlm: Any = None
) -> dict[str, Any]:
    """VLM yes/no check of a predicate from the camera covering ``region`` (the verify loop).

    The agent acts, then asks e.g. "is the blue block in the tote now?"; the VLM looks at
    the chosen camera and answers yes/no/unknown. Falls back to a clear note when no VLM
    is configured (``PGFR_VLM_URL`` unset)."""
    from policy_gated_factory_robot_orchestrator_reference.agents.perception import PerceptionAgent

    if vlm is None:
        from policy_gated_factory_robot_orchestrator_reference.clients.vlm import vlm_from_env

        vlm = vlm_from_env()
    if vlm is None:
        return {"answer": "unknown", "evidence": "no VLM configured (set PGFR_VLM_URL)", "source_used": ""}
    return await PerceptionAgent(backend.sources(), vlm).check_predicate(predicate, region)
