# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ic-chat gateway API — chat with a swappable model that drives the cell.

Write-path sibling of ic-console/ic-workflows. The console's Chat tab talks to
this service. A chat turn can trigger floor actions (tool calls), so it carries
the SAME CSRF guard as ic-workflows: a message that could move the arm must not
be sent from a random page the operator happens to visit.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .backends import ChatBackend, OpenClawBackend, make_backend
from .sessions import SessionStore
from .toolloop import TOOLS, ToolLoop, ToolLoopSettings

_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _require_write_token(host: str, token: Optional[str], service: str) -> None:
    if host.strip().lower() not in _LOOPBACK_HOSTS and not token:
        raise RuntimeError(
            f"{service} refuses non-loopback host {host!r} without its write token"
        )


class ChatRequest(BaseModel):
    session_id: str = Field(default="")
    message: str = Field(min_length=1, max_length=8000)
    backend: Optional[str] = Field(default=None, max_length=32)


def _csrf_guard(
    request: Request, header: Optional[str], allowed_origins: List[str], token: Optional[str]
) -> None:
    if header is None:
        raise HTTPException(403, "missing X-IC-Chat header (CSRF guard)")
    origin = request.headers.get("origin")
    if origin is not None and origin not in allowed_origins:
        raise HTTPException(403, f"origin {origin!r} not allowed")
    if token and header != token:
        raise HTTPException(403, "bad CSRF token")


def build_app(
    backend: Optional[ChatBackend] = None, loop: Optional[ToolLoop] = None,
    sessions_store: Optional[SessionStore] = None,
    openclaw_backend: Optional[ChatBackend] = None,
) -> FastAPI:
    traditional_backend = backend or make_backend()
    openclaw_backend = openclaw_backend or OpenClawBackend()
    backends: Dict[str, ChatBackend] = {
        "traditional": traditional_backend,
        "openclaw": openclaw_backend,
    }
    loop = loop or ToolLoop(ToolLoopSettings())
    allowed_origins = os.environ.get("IC_CHAT_CORS", "http://127.0.0.1:8600").split(",")
    csrf_token = os.environ.get("IC_CHAT_TOKEN")
    max_sessions = int(os.environ.get("IC_CHAT_MAX_SESSIONS", "200"))
    max_history = int(os.environ.get("IC_CHAT_MAX_HISTORY", "200"))  # stored (display)
    context_window = int(os.environ.get("IC_CHAT_CONTEXT_WINDOW", "24"))  # sent to model
    store = sessions_store or SessionStore(
        os.environ.get("IC_CHAT_SESSIONS_DIR", str(Path.home() / ".ic_chat_sessions")),
        max_sessions=max_sessions, max_history=max_history,
    )
    active_missions: set[str] = set()

    async def backend_events(
        selected_backend: ChatBackend,
        context: List[Dict[str, Any]],
        mission_id: str,
    ):
        native_stream = getattr(selected_backend, "run_native_stream", None)
        if getattr(selected_backend, "native_tool_owner", False) and callable(native_stream):
            async for event in native_stream(context, mission_id):
                yield event
            return
        async for event in loop.run_stream(selected_backend, context, mission_id):
            yield event

    async def run_backend(
        selected_backend: ChatBackend,
        context: List[Dict[str, Any]],
        mission_id: str,
    ) -> Dict[str, Any]:
        transcript: List[Dict[str, Any]] = []
        async for event in backend_events(selected_backend, context, mission_id):
            # The batch API has no placeholder-card concept; retain completed
            # tools and assistant/error events only.
            if event.get("role") in ("assistant", "tool", "error"):
                transcript.append(event)
        final = next(
            (event.get("content", "") for event in reversed(transcript)
             if event.get("role") == "assistant"),
            "",
        )
        return {"transcript": transcript, "final": final}

    def session_backend(state: Dict[str, Any], requested: Optional[str]) -> ChatBackend:
        selected = requested or state.get("backend") or "traditional"
        if selected not in backends:
            raise HTTPException(422, f"unknown chat backend: {selected!r}")
        stored = state.get("backend")
        if stored and requested and requested != stored:
            raise HTTPException(
                409,
                "a conversation stays on one backend; start a new chat to switch",
            )
        chosen = backends[selected]
        if selected == "openclaw" and not getattr(chosen, "configured", True):
            raise HTTPException(
                503,
                "OpenClaw Gateway is not configured; use traditional or configure "
                "IC_OPENCLAW_URL/IC_OPENCLAW_TOKEN",
            )
        if not stored:
            state["backend"] = selected
            store.save(state)
        return chosen

    app = FastAPI(title="IC Chat")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["content-type", "x-ic-chat"],
    )

    @app.get("/api/health")
    async def health() -> dict:
        traditional_available = bool(
            getattr(traditional_backend, "configured", True)
        )
        return {
            "status": "ok",
            # Retain the original fields for older console builds.
            "backend": traditional_backend.name,
            "tools": [t["name"] for t in TOOLS],
            "default_backend": "traditional",
            "backends": {
                "traditional": {
                    "available": traditional_available,
                    "label": f"Traditional IC Chat ({traditional_backend.name})",
                },
                "openclaw": {
                    "available": bool(getattr(openclaw_backend, "configured", True)),
                    "label": "OpenClaw",
                    "transport": (
                        "typed-gateway"
                        if getattr(openclaw_backend, "native_tool_owner", False)
                        else "chat-completions"
                    ),
                    "tool_owner": (
                        "openclaw-mcp"
                        if getattr(openclaw_backend, "native_tool_owner", False)
                        else "ic-chat"
                    ),
                },
            },
        }

    @app.get("/api/ready")
    async def ready() -> dict:
        probe = getattr(traditional_backend, "readiness", None)
        result = await probe() if callable(probe) else {
            "ready": bool(getattr(traditional_backend, "configured", True)),
            "backend": traditional_backend.name,
            "probe": "process-only",
        }
        if not result.get("ready"):
            raise HTTPException(503, detail=result)
        return {"status": "ready", **result}

    @app.get("/api/sessions")
    async def list_sessions() -> dict:
        sessions = store.list()
        for session in sessions:
            session["active"] = session.get("mission_id") in active_missions
        return {"sessions": sessions}

    @app.post("/api/chat")
    async def chat(
        body: ChatRequest, request: Request, x_ic_chat: Optional[str] = Header(default=None)
    ) -> dict:
        _csrf_guard(request, x_ic_chat, allowed_origins, csrf_token)
        if body.session_id and not _SESSION_RE.match(body.session_id):
            raise HTTPException(422, "bad session_id")
        state = store.get_or_create(body.session_id)
        selected_backend = session_backend(state, body.backend)
        state["history"].append({"role": "user", "content": body.message})
        # Send only the recent window to the model (token bound); the model
        # context carries user/assistant text only — tool records in history
        # are for session replay and would be malformed chat messages.
        context = [
            m for m in state["history"] if m.get("role") in ("user", "assistant")
        ][-context_window:]
        try:
            out = await run_backend(selected_backend, context, state["mission_id"])
        except Exception as exc:
            raise HTTPException(502, f"backend error: {type(exc).__name__}: {exc}")
        for entry in out["transcript"]:
            if entry["role"] == "assistant" and entry.get("content"):
                state["history"].append({"role": "assistant", "content": entry["content"]})
            elif entry.get("name"):
                # Persist a compact tool record so opening the session later
                # replays the tool cards and evidence frames, not just prose.
                result = entry.get("result") or {}
                keep = {
                    k: result[k]
                    for k in ("verified", "reason", "error", "dispatched",
                              "moved", "request_id", "answer", "yes",
                              "vision_agrees", "evidence", "source_used",
                              "mode", "status", "goal_id", "proof_gate",
                              "pending_visual_proof", "harness", "harness_tool")
                    if k in result
                }
                vis = result.get("vision") or {}
                if isinstance(vis, dict) and vis:
                    keep["vision"] = {
                        k: vis[k]
                        for k in ("summary", "error", "raw", "parse_ok", "source_used",
                                  "cubes_visible", "tote_on_rack", "region")
                        if k in vis
                    }
                state["history"].append({"role": "tool", "name": entry["name"],
                                         "args": entry.get("args") or {},
                                         "result": keep})
        store.save(state)
        return {
            "session_id": state["id"],
            "mission_id": state["mission_id"],
            "transcript": out["transcript"],
        }

    @app.post("/api/chat/stream")
    async def chat_stream(
        body: ChatRequest, request: Request, x_ic_chat: Optional[str] = Header(default=None)
    ):
        """Same turn as /api/chat, streamed as it happens (SSE).

        The operator watches the mission unfold — each tool call announced when
        it starts, its result (and evidence frame id) the moment the seam
        answers — instead of a wall of text minutes later. Identical loop,
        identical guarantees; the session is persisted exactly as the batch
        route does so replay and live view agree.
        """
        import json as _json

        from fastapi.responses import StreamingResponse

        _csrf_guard(request, x_ic_chat, allowed_origins, csrf_token)
        if body.session_id and not _SESSION_RE.match(body.session_id):
            raise HTTPException(422, "bad session_id")
        state = store.get_or_create(body.session_id)
        selected_backend = session_backend(state, body.backend)
        state["history"].append({"role": "user", "content": body.message})
        context = [
            m for m in state["history"] if m.get("role") in ("user", "assistant")
        ][-context_window:]

        async def events():
            active_missions.add(state["mission_id"])
            yield "data: " + _json.dumps({
                "role": "meta", "session_id": state["id"], "mission_id": state["mission_id"]
            }) + "\n\n"
            try:
                async for ev in backend_events(
                    selected_backend, context, state["mission_id"]
                ):
                    if ev.get("role") == "assistant" and ev.get("content"):
                        state["history"].append({"role": "assistant", "content": ev["content"]})
                    elif ev.get("role") == "tool":
                        result = ev.get("result") or {}
                        keep = {k: result[k] for k in (
                            "verified", "reason", "error", "dispatched", "moved",
                            "request_id", "answer", "yes", "vision_agrees", "evidence",
                            "source_used", "mode", "status", "goal_id", "proof_gate",
                            "pending_visual_proof", "harness", "harness_tool")
                            if k in result}
                        vis = result.get("vision") or {}
                        if isinstance(vis, dict) and vis:
                            keep["vision"] = {
                                k: vis[k]
                                for k in ("summary", "error", "raw", "parse_ok",
                                          "source_used", "cubes_visible",
                                          "tote_on_rack", "region")
                                if k in vis
                            }
                        state["history"].append({"role": "tool", "name": ev.get("name"),
                                                 "args": ev.get("args") or {}, "result": keep})
                    yield "data: " + _json.dumps(ev) + "\n\n"
            except Exception as exc:  # surface, never hang the stream
                yield "data: " + _json.dumps(
                    {"role": "error", "error": f"{type(exc).__name__}: {exc}"}) + "\n\n"
            finally:
                active_missions.discard(state["mission_id"])
                store.save(state)

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"cache-control": "no-store",
                                          "x-accel-buffering": "no"})

    @app.post("/api/sessions/{session_id}/stop")
    async def stop_session(
        session_id: str, request: Request, x_ic_chat: Optional[str] = Header(default=None)
    ) -> dict:
        _csrf_guard(request, x_ic_chat, allowed_origins, csrf_token)
        if not _SESSION_RE.match(session_id):
            raise HTTPException(422, "bad session_id")
        state = store.get(session_id)
        if not state:
            raise HTTPException(404, "no such session")
        mission_id = state["mission_id"]
        if mission_id not in active_missions:
            return {
                "accepted": False,
                "status": "idle",
                "mission_id": mission_id,
                "reason": "this chat session has no running turn",
            }
        selected = backends.get(state.get("backend", "traditional"), traditional_backend)
        native_stop = getattr(selected, "request_stop", None)
        if getattr(selected, "native_tool_owner", False) and callable(native_stop):
            return await native_stop(mission_id)
        return loop.request_stop(mission_id)

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(
        session_id: str, request: Request, x_ic_chat: Optional[str] = Header(default=None)
    ) -> dict:
        _csrf_guard(request, x_ic_chat, allowed_origins, csrf_token)
        if not _SESSION_RE.match(session_id):
            raise HTTPException(422, "bad session_id")
        return {"deleted": store.delete(session_id), "id": session_id}

    @app.get("/api/frame/{request_id}")
    async def frame(request_id: str):
        # Proxy the evidence frame from the seam so the browser talks only to
        # the gateway (one origin for CSP). Read-only; id validated.
        import httpx
        from fastapi.responses import Response

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
            raise HTTPException(422, "bad request_id")
        seam = loop.settings.seam_url
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{seam}/v1/frames/{request_id}")
        except Exception:
            raise HTTPException(502, "seam unreachable")
        if r.status_code != 200:
            raise HTTPException(404, "no frame")
        return Response(content=r.content, media_type="image/jpeg")

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict:
        if not _SESSION_RE.match(session_id):
            raise HTTPException(422, "bad session_id")
        state = store.get(session_id)
        if not state:
            raise HTTPException(404, "no such session")
        return {"id": state["id"], "mission_id": state["mission_id"],
                "backend": state.get("backend", "traditional"),
                "title": state.get("title"),
                "created": state.get("created"), "updated": state.get("updated"),
                "active": state["mission_id"] in active_missions,
                "history": state["history"]}

    return app


def main() -> None:
    import uvicorn

    host = os.environ.get("IC_CHAT_HOST", "127.0.0.1")
    port = int(os.environ.get("IC_CHAT_PORT", "8620"))
    _require_write_token(host, os.environ.get("IC_CHAT_TOKEN"), "IC Chat")
    uvicorn.run(build_app(), host=host, port=port)


if __name__ == "__main__":
    main()
