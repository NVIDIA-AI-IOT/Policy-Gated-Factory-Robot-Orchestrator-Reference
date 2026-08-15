# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Gym resources server for the Industrial Claw cell.

Exposes the IC Spine floor seam (FastAPI v1) as a NeMo Gym environment:

- tools  -> plain POST routes proxying the seam (floor_state, perceive,
            dispatch_task, check_predicate), stamped with a per-rollout
            mission id so every episode is journaled like any other actor;
- reset  -> ``seed_session`` dispatches the operator ``reset`` action;
- reward -> ``verify`` reads the mission journal: reward is 1.0 only when a
            dispatch matching the task's expectation was physics-verified by
            the cell (never trust ``success`` alone), optionally AND-ed with
            a ground-truth predicate check via ``/v1/verify``.

The server has no privileged path: every call goes through the same seam and
policy gate as the production brain. See README.md for the run recipe.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional

import aiohttp
from fastapi import FastAPI, Request
from pydantic import BaseModel, PrivateAttr

from nemo_gym.base_resources_server import (
    BaseResourcesServerConfig,
    BaseRunRequest,
    BaseSeedSessionRequest,
    BaseSeedSessionResponse,
    BaseVerifyRequest,
    BaseVerifyResponse,
    SimpleResourcesServer,
)
from nemo_gym.server_utils import SESSION_ID_KEY


class ICCellResourcesServerConfig(BaseResourcesServerConfig):
    seam_base_url: str = "http://127.0.0.1:8766"
    request_timeout_s: float = 300.0
    reset_between_episodes: bool = True
    reset_endpoint: str = "franka_left"
    # When True, a failed episode reset fails seed_session loudly instead of
    # being recorded and surfaced in verify diagnostics.
    require_reset: bool = False


class FloorStateRequest(BaseModel):
    pass


class PerceiveRequest(BaseModel):
    target: str


class DispatchTaskRequest(BaseModel):
    action: str
    endpoint: str
    color: Optional[str] = None
    source: Optional[str] = None
    destination: Optional[str] = None
    object_id: Optional[str] = None
    target_id: Optional[str] = None


class CheckPredicateRequest(BaseModel):
    predicate: str
    region: Optional[str] = None


class ICCellRunRequest(BaseRunRequest):
    verifier_metadata: Dict[str, Any] = {}


class ICCellVerifyRequest(ICCellRunRequest, BaseVerifyRequest):
    pass


class ICCellVerifyResponse(BaseVerifyResponse):
    mission_id: Optional[str] = None
    dispatches: int = 0
    verified_dispatches: int = 0
    predicate_answer: Optional[str] = None
    reason: str = ""


class ICCellResourcesServer(SimpleResourcesServer):
    config: ICCellResourcesServerConfig

    # session_id -> {"mission_id": str, "reset_error": str | None}
    _sessions: Dict[str, Dict[str, Any]] = PrivateAttr(default_factory=dict)

    # ------------------------------------------------------------------ http
    def setup_webserver(self) -> FastAPI:
        app = super().setup_webserver()
        app.post("/floor_state")(self.floor_state)
        app.post("/perceive")(self.perceive)
        app.post("/dispatch_task")(self.dispatch_task)
        app.post("/check_predicate")(self.check_predicate)
        return app

    # ------------------------------------------------------------------ seam
    async def _seam(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        mission_id: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers: Dict[str, str] = {}
        if mission_id:
            headers["x-mission-id"] = mission_id
        if role:
            headers["x-role"] = role
        url = self.config.seam_base_url.rstrip("/") + path
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, json=json_body, headers=headers) as resp:
                body = await resp.json(content_type=None)
                if isinstance(body, dict):
                    body.setdefault("_http_status", resp.status)
                return body

    def _session_state(self, request: Request) -> Dict[str, Any]:
        session_id = request.session.get(SESSION_ID_KEY, "")
        return self._sessions.setdefault(
            session_id, {"mission_id": f"gym-{uuid.uuid4().hex[:12]}", "reset_error": None}
        )

    # --------------------------------------------------------------- episode
    async def seed_session(
        self, request: Request, body: BaseSeedSessionRequest
    ) -> BaseSeedSessionResponse:
        state = self._session_state(request)
        if self.config.reset_between_episodes:
            try:
                result = await self._seam(
                    "POST",
                    "/v1/dispatch",
                    {"action": "reset", "endpoint": self.config.reset_endpoint},
                    mission_id=state["mission_id"],
                    role="operator",
                )
                if not result.get("dispatched", False):
                    state["reset_error"] = str(result.get("reason", "reset refused"))
            except Exception as exc:  # degrade loudly, but keep the rollout alive
                state["reset_error"] = f"{type(exc).__name__}: {exc}"
            if state["reset_error"] and self.config.require_reset:
                raise RuntimeError(f"episode reset failed: {state['reset_error']}")
        return BaseSeedSessionResponse()

    # ----------------------------------------------------------------- tools
    async def floor_state(self, request: Request, body: FloorStateRequest) -> Dict[str, Any]:
        state = self._session_state(request)
        return await self._seam("POST", "/v1/floor-state", {}, mission_id=state["mission_id"])

    async def perceive(self, request: Request, body: PerceiveRequest) -> Dict[str, Any]:
        state = self._session_state(request)
        return await self._seam(
            "POST", "/v1/perceive", body.model_dump(), mission_id=state["mission_id"]
        )

    async def dispatch_task(self, request: Request, body: DispatchTaskRequest) -> Dict[str, Any]:
        state = self._session_state(request)
        payload = {k: v for k, v in body.model_dump().items() if v is not None}
        return await self._seam(
            "POST", "/v1/dispatch", payload, mission_id=state["mission_id"]
        )

    async def check_predicate(
        self, request: Request, body: CheckPredicateRequest
    ) -> Dict[str, Any]:
        state = self._session_state(request)
        payload = {k: v for k, v in body.model_dump().items() if v is not None}
        return await self._seam(
            "POST", "/v1/verify", payload, mission_id=state["mission_id"]
        )

    # ---------------------------------------------------------------- reward
    async def verify(self, request: Request, body: ICCellVerifyRequest) -> ICCellVerifyResponse:
        meta = body.verifier_metadata or {}
        state = self._session_state(request)
        mission_id = state["mission_id"]

        dispatches = 0
        verified = 0
        matched_verified = 0
        reason_parts = []
        if state.get("reset_error"):
            reason_parts.append(f"reset_error={state['reset_error']}")

        try:
            detail = await self._seam("GET", f"/v1/missions/{mission_id}")
            operations = detail.get("operations", [])
        except Exception as exc:
            operations = []
            reason_parts.append(f"journal_unreachable={type(exc).__name__}")

        expected_action = meta.get("expected_action")
        expected_color = meta.get("expected_color")
        for op in operations:
            action = op.get("action") or (op.get("params") or {}).get("action")
            if action == "reset":
                continue
            if op.get("op") not in (None, "dispatch") and action is None:
                continue
            dispatches += 1
            if not op.get("verified"):
                continue
            verified += 1
            if expected_action and action != expected_action:
                continue
            color = op.get("color") or (op.get("params") or {}).get("color")
            if expected_color and color != expected_color:
                continue
            matched_verified += 1

        journal_ok = matched_verified > 0 if (expected_action or expected_color) else verified > 0

        predicate_answer: Optional[str] = None
        predicate_ok = True
        if meta.get("predicate"):
            try:
                payload: Dict[str, Any] = {"predicate": meta["predicate"]}
                if meta.get("region"):
                    payload["region"] = meta["region"]
                answer = await self._seam(
                    "POST", "/v1/verify", payload, mission_id=mission_id
                )
                predicate_answer = str(answer.get("answer", "unknown"))
                predicate_ok = predicate_answer == "yes"
            except Exception as exc:
                predicate_answer = "unreachable"
                predicate_ok = False
                reason_parts.append(f"predicate_unreachable={type(exc).__name__}")

        reward = 1.0 if (journal_ok and predicate_ok) else 0.0
        reason_parts.append(
            f"journal_ok={journal_ok} predicate_ok={predicate_ok} "
            f"verified={verified}/{dispatches}"
        )

        return ICCellVerifyResponse(
            **body.model_dump(),
            reward=reward,
            mission_id=mission_id,
            dispatches=dispatches,
            verified_dispatches=verified,
            predicate_answer=predicate_answer,
            reason="; ".join(reason_parts),
        )


if __name__ == "__main__":
    ICCellResourcesServer.run_webserver()
