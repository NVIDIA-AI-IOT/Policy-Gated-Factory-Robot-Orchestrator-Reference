# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed, headless OpenClaw Gateway client used by IC Chat.

OpenClaw owns its MCP tool loop.  IC Chat owns only the browser-facing session
and normalizes Gateway ``chat``/``agent`` events into its existing SSE contract.
The implementation intentionally targets the protocol shipped by the pinned
OpenClaw dependency (protocol v4); a protocol mismatch fails closed during the
connect handshake instead of silently falling back to client-owned tools.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Optional, Tuple
from urllib.parse import urlparse

import aiohttp


OPENCLAW_PROTOCOL_VERSION = 4
_SAFE_KEY_RE = re.compile(r"[^A-Za-z0-9_-]+")
_HISTORY_LIMIT = 100
_HISTORY_MAX_CHARS = 240_000


@dataclass
class _ActiveRun:
    """The owning Gateway connection and abort state for one live chat run."""

    session_key: str
    run_id: str
    ws: aiohttp.ClientWebSocketResponse
    abort_request_id: Optional[str] = None
    abort_result: Optional[asyncio.Future[Dict[str, Any]]] = None


def _message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(message.get("text") or "")
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _decode_json_text(text: str) -> Any:
    """Decode OpenClaw's MCP transcript envelope when one is present.

    Native Gateway tool events intentionally omit result bodies.  The supported
    ``chat.history`` method retains them as a text content block shaped like::

        structuredContent:
        {"result": "{\"answer\":\"yes\", ...}"}

    Keep this decoder deliberately narrow: ordinary model/tool text remains
    ordinary text instead of being interpreted as a control structure.
    """
    stripped = text.strip()
    prefix = "structuredContent:"
    if stripped.startswith(prefix):
        stripped = stripped[len(prefix):].strip()
    try:
        value = json.loads(stripped)
    except (TypeError, ValueError):
        return text
    if isinstance(value, dict) and set(value).issubset({"result", "isError"}):
        inner = value.get("result")
        if isinstance(inner, str):
            try:
                decoded = json.loads(inner)
            except (TypeError, ValueError):
                return {"output": inner}
            return decoded
        if inner is not None:
            return inner
    return value


def _promote_request_id(result: Dict[str, Any]) -> Dict[str, Any]:
    """Expose the journal frame id at the stable IC Chat result boundary."""
    if result.get("request_id"):
        return result
    meta = result.get("_meta")
    request_id = meta.get("request_id") if isinstance(meta, dict) else None
    if isinstance(request_id, str) and request_id:
        result = dict(result)
        result["request_id"] = request_id
    return result


def _tool_payload(value: Any, *, is_error: bool = False) -> Dict[str, Any]:
    """Unwrap OpenClaw/MCP content blocks into the JSON the IC UI expects."""
    if isinstance(value, dict) and isinstance(value.get("content"), list):
        texts = [
            block.get("text", "")
            for block in value["content"]
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        text = "\n".join(part for part in texts if part)
        parsed = _decode_json_text(text) if text else {}
        result = parsed if isinstance(parsed, dict) else {"output": parsed}
    elif isinstance(value, dict):
        result = dict(value)
    elif value is None:
        result = {}
    else:
        result = {"output": value}
    if is_error and "error" not in result:
        result["error"] = str(result.get("output") or "OpenClaw tool failed")
    return _promote_request_id(result)


class OpenClawGatewayClient:
    """One-turn Gateway adapter with native tool-event streaming and abort."""

    def __init__(
        self,
        *,
        ws_url: str,
        token: str,
        agent_id: str = "ic-console",
        timeout_s: float = 300.0,
    ) -> None:
        parsed = urlparse(ws_url)
        if parsed.scheme == "ws" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "plaintext OpenClaw ws:// is allowed only on loopback; use wss:// remotely"
            )
        self.ws_url = ws_url
        self.token = token
        self.agent_id = agent_id
        self.timeout_s = timeout_s
        self._active: Dict[str, _ActiveRun] = {}

    def session_key(self, mission_id: str) -> str:
        safe = _SAFE_KEY_RE.sub("-", mission_id).strip("-") or uuid.uuid4().hex
        return f"agent:{self.agent_id}:ic-chat-{safe[:80]}"

    async def _receive_json(self, ws: aiohttp.ClientWebSocketResponse) -> Dict[str, Any]:
        message = await ws.receive()
        if message.type == aiohttp.WSMsgType.TEXT:
            try:
                value = json.loads(message.data)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("OpenClaw Gateway sent invalid JSON") from exc
            if isinstance(value, dict):
                return value
        if message.type == aiohttp.WSMsgType.ERROR:
            raise RuntimeError(f"OpenClaw Gateway WebSocket error: {ws.exception()}")
        raise RuntimeError(f"OpenClaw Gateway closed unexpectedly ({message.type!s})")

    async def _wait_response(
        self, ws: aiohttp.ClientWebSocketResponse, request_id: str
    ) -> Dict[str, Any]:
        while True:
            frame = await self._receive_json(ws)
            if frame.get("type") != "res" or frame.get("id") != request_id:
                continue
            if frame.get("ok") is not True:
                error = frame.get("error") or {}
                raise RuntimeError(str(error.get("message") or "OpenClaw request failed"))
            payload = frame.get("payload")
            return payload if isinstance(payload, dict) else {}

    async def _connect(
        self,
    ) -> Tuple[aiohttp.ClientSession, aiohttp.ClientWebSocketResponse]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_s + 20.0)
        session = aiohttp.ClientSession(timeout=timeout)
        try:
            ws = await session.ws_connect(
                self.ws_url,
                heartbeat=20.0,
                max_msg_size=25 * 1024 * 1024,
            )
            while True:
                challenge = await self._receive_json(ws)
                if challenge.get("type") == "event" and challenge.get("event") == "connect.challenge":
                    break
            connect_id = uuid.uuid4().hex
            params: Dict[str, Any] = {
                "minProtocol": OPENCLAW_PROTOCOL_VERSION,
                "maxProtocol": OPENCLAW_PROTOCOL_VERSION,
                "client": {
                    "id": "gateway-client",
                    "displayName": "industrial-claw-ic-chat",
                    "version": "0.1.0",
                    "platform": "linux",
                    "mode": "backend",
                    "instanceId": uuid.uuid4().hex,
                },
                "caps": ["tool-events"],
                "role": "operator",
                "scopes": ["operator.read", "operator.write"],
            }
            if self.token:
                params["auth"] = {"token": self.token}
            await ws.send_json({
                "type": "req",
                "id": connect_id,
                "method": "connect",
                "params": params,
            })
            hello = await self._wait_response(ws, connect_id)
            if hello.get("type") != "hello-ok":
                raise RuntimeError("OpenClaw Gateway did not return hello-ok")
            if hello.get("protocol") != OPENCLAW_PROTOCOL_VERSION:
                raise RuntimeError(
                    f"OpenClaw protocol mismatch: expected {OPENCLAW_PROTOCOL_VERSION}, "
                    f"got {hello.get('protocol')!r}"
                )
            methods = ((hello.get("features") or {}).get("methods") or [])
            missing = {"chat.send", "chat.abort", "chat.history"}.difference(methods)
            if missing:
                raise RuntimeError(f"OpenClaw Gateway lacks required methods: {sorted(missing)}")
            return session, ws
        except Exception:
            await session.close()
            raise

    async def _history_tool_result(
        self,
        ws: aiohttp.ClientWebSocketResponse,
        session_key: str,
        tool_call_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Recover one redacted live result from official Gateway history.

        A dedicated read connection calls this method, so chat/agent events on
        the run connection can never be consumed while waiting for the history
        response.  The short bounded retry covers the transcript flush that can
        trail the live ``phase=result`` event by a few milliseconds.
        """
        for attempt in range(4):
            if attempt:
                await asyncio.sleep(0.05 * (2 ** (attempt - 1)))
            request_id = uuid.uuid4().hex
            await ws.send_json({
                "type": "req",
                "id": request_id,
                "method": "chat.history",
                "params": {
                    "sessionKey": session_key,
                    "limit": _HISTORY_LIMIT,
                    "maxChars": _HISTORY_MAX_CHARS,
                },
            })
            response = await self._wait_response(ws, request_id)
            messages = response.get("messages") or []
            for message in reversed(messages if isinstance(messages, list) else []):
                if not isinstance(message, dict):
                    continue
                if str(message.get("role") or "").lower() != "toolresult":
                    continue
                if str(message.get("toolCallId") or "") != tool_call_id:
                    continue
                return _tool_payload(
                    message,
                    is_error=bool(message.get("isError")),
                )
        return None

    async def run_stream(
        self, message: str, mission_id: str
    ) -> AsyncIterator[Dict[str, Any]]:
        session_key = self.session_key(mission_id)
        run_id = f"ic-chat-{uuid.uuid4().hex}"
        request_id = uuid.uuid4().hex
        session: Optional[aiohttp.ClientSession] = None
        ws: Optional[aiohttp.ClientWebSocketResponse] = None
        history_session: Optional[aiohttp.ClientSession] = None
        history_ws: Optional[aiohttp.ClientWebSocketResponse] = None
        open_tools: Dict[str, Dict[str, Any]] = {}
        final_text = ""
        final_seen = False
        active: Optional[_ActiveRun] = None
        try:
            session, ws = await self._connect()
            active = _ActiveRun(session_key=session_key, run_id=run_id, ws=ws)
            self._active[mission_id] = active
            await ws.send_json({
                "type": "req",
                "id": request_id,
                "method": "chat.send",
                "params": {
                    "sessionKey": session_key,
                    "message": message,
                    "deliver": False,
                    "timeoutMs": int(self.timeout_s * 1000),
                    "idempotencyKey": run_id,
                },
            })
            deadline = asyncio.get_running_loop().time() + self.timeout_s + 20.0
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError
                frame = await asyncio.wait_for(self._receive_json(ws), timeout=remaining)
                if (
                    frame.get("type") == "res"
                    and active.abort_request_id
                    and frame.get("id") == active.abort_request_id
                ):
                    abort_result = active.abort_result
                    if abort_result is not None and not abort_result.done():
                        if frame.get("ok") is True:
                            payload = frame.get("payload")
                            abort_result.set_result(
                                payload if isinstance(payload, dict) else {}
                            )
                        else:
                            error = frame.get("error") or {}
                            abort_result.set_exception(RuntimeError(
                                str(error.get("message") or "OpenClaw abort failed")
                            ))
                    continue
                if frame.get("type") == "res" and frame.get("id") == request_id:
                    if frame.get("ok") is not True:
                        error = frame.get("error") or {}
                        raise RuntimeError(
                            str(error.get("message") or "OpenClaw chat.send failed")
                        )
                    continue
                if frame.get("type") != "event":
                    continue
                event = frame.get("event")
                payload = frame.get("payload")
                if not isinstance(payload, dict) or payload.get("runId") != run_id:
                    continue
                if event == "agent" and payload.get("stream") == "tool":
                    data = payload.get("data") or {}
                    if not isinstance(data, dict):
                        continue
                    tool_id = str(data.get("toolCallId") or "")
                    phase = data.get("phase")
                    raw_name = str(data.get("name") or "tool")
                    name = raw_name.split("__", 1)[-1]
                    if not tool_id:
                        continue
                    if phase == "start":
                        entry = {
                            "name": name,
                            "raw_name": raw_name,
                            "args": data.get("args") if isinstance(data.get("args"), dict) else {},
                        }
                        open_tools[tool_id] = entry
                        yield {"role": "tool_start", "name": name, "args": entry["args"]}
                    elif phase == "result":
                        entry = open_tools.pop(tool_id, {
                            "name": name,
                            "raw_name": raw_name,
                            "args": {},
                        })
                        raw_result = data.get("result")
                        result = _tool_payload(
                            raw_result, is_error=bool(data.get("isError"))
                        )
                        # Protocol-v4 public tool events may redact the result
                        # body. Recover the exact sanitized MCP transcript through
                        # the Gateway's official read API; never scrape OpenClaw
                        # files or guess-correlate against the floor journal.
                        if raw_result is None or not result:
                            try:
                                if history_ws is None:
                                    history_session, history_ws = await self._connect()
                                recovered = await self._history_tool_result(
                                    history_ws, session_key, tool_id
                                )
                                if recovered is not None:
                                    result = recovered
                            except Exception:
                                # Observability enrichment must not turn a
                                # completed robot tool call into a failed run.
                                pass
                        if bool(data.get("isError")) and "error" not in result:
                            result["error"] = str(
                                data.get("toolErrorSummary") or "OpenClaw tool failed"
                            )
                        result.setdefault("harness", "openclaw")
                        result.setdefault("harness_tool", entry["raw_name"])
                        yield {
                            "role": "tool",
                            "name": entry["name"],
                            "args": entry["args"],
                            "result": result,
                        }
                        if final_seen and not open_tools:
                            break
                elif event == "chat":
                    state = payload.get("state")
                    if state == "delta":
                        delta = str(payload.get("deltaText") or "")
                        if payload.get("replace") is True:
                            final_text = delta
                        else:
                            final_text += delta
                    elif state == "final":
                        final_seen = True
                        text = _message_text(payload.get("message"))
                        if text:
                            final_text = text
                        if not open_tools:
                            break
                    elif state in {"aborted", "error"}:
                        if (
                            state == "aborted"
                            and active.abort_result is not None
                            and not active.abort_result.done()
                        ):
                            # OpenClaw broadcasts the terminal event before the
                            # chat.abort response. The event on this owning
                            # connection is itself an authoritative confirmation.
                            active.abort_result.set_result({
                                "ok": True,
                                "aborted": True,
                                "runIds": [run_id],
                            })
                        error = payload.get("errorMessage") or state
                        yield {"role": "error", "error": f"OpenClaw run {error}"}
                        return
            if final_text:
                yield {"role": "assistant", "content": final_text, "tool_calls": []}
            elif not final_seen:
                yield {"role": "error", "error": "OpenClaw run ended without a final response"}
        except asyncio.TimeoutError:
            yield {"role": "error", "error": "OpenClaw run timed out"}
        finally:
            if active is not None and self._active.get(mission_id) is active:
                self._active.pop(mission_id, None)
            if (
                active is not None
                and active.abort_result is not None
                and not active.abort_result.done()
            ):
                active.abort_result.set_exception(
                    RuntimeError("OpenClaw run ended before abort confirmation")
                )
            if ws is not None:
                await ws.close()
            if session is not None:
                await session.close()
            if history_ws is not None:
                await history_ws.close()
            if history_session is not None:
                await history_session.close()

    async def request_stop(self, mission_id: str) -> Dict[str, Any]:
        active = self._active.get(mission_id)
        if active is None:
            return {
                "accepted": False,
                "status": "idle",
                "mission_id": mission_id,
                "reason": "this OpenClaw session has no running turn",
            }
        if active.abort_result is None:
            loop = asyncio.get_running_loop()
            active.abort_result = loop.create_future()
            active.abort_request_id = uuid.uuid4().hex
            try:
                await active.ws.send_json({
                    "type": "req",
                    "id": active.abort_request_id,
                    "method": "chat.abort",
                    "params": {
                        "sessionKey": active.session_key,
                        "runId": active.run_id,
                    },
                })
            except Exception as exc:
                active.abort_result = None
                active.abort_request_id = None
                return {
                    "accepted": False,
                    "status": "error",
                    "mission_id": mission_id,
                    "reason": f"OpenClaw abort request could not be sent: {exc}",
                }
        try:
            result = await asyncio.wait_for(
                asyncio.shield(active.abort_result), timeout=min(10.0, self.timeout_s)
            )
        except (asyncio.TimeoutError, RuntimeError) as exc:
            return {
                "accepted": False,
                "status": "error",
                "mission_id": mission_id,
                "run_id": active.run_id,
                "reason": f"OpenClaw did not accept the stop request: {exc}",
            }
        else:
            return {
                "accepted": bool(result.get("aborted") or result.get("ok")),
                "status": "stopping",
                "mission_id": mission_id,
                "run_id": active.run_id,
                "reason": (
                    "OpenClaw run abort requested; an in-flight floor action remains "
                    "owned by IC Spine and is not force-terminated"
                ),
            }
