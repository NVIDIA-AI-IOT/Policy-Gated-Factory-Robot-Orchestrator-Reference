# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Swappable model backends — the deliberation host is a connector, not the product.

A backend takes (messages, tools) and returns one assistant turn: text plus any
tool calls. That is the whole contract, so any host that speaks it plugs in:

- ``openai``   — any OpenAI-compatible /v1/chat/completions endpoint: the Cosmos
                 VLM on Thor, a local vLLM/NIM, or a hosted API. Covers most.
- ``anthropic`` — Anthropic Messages API: the same brain the OpenClaw gateway
                 runs (Claude via the NVIDIA NIM provider), in the console's own chat.
- ``echo``     — a deterministic no-network backend for tests/demos: it emits a
                 tool call parsed from a ``/tool`` directive, else echoes.

NemoClaw or Claude slot in as another adapter (NIM endpoints are OpenAI-shaped,
so they use the openai backend directly).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol

import httpx

from .openclaw_gateway import OpenClawGatewayClient


class ChatBackend(Protocol):
    name: str

    async def respond(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Return {"content": str, "tool_calls": [{"id","name","arguments"}]}."""
        ...


class OpenAIBackend:
    name = "openai"

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: float = 120.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("IC_CHAT_MODEL_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("IC_CHAT_API_KEY", "")
        self.model = model or os.environ.get("IC_CHAT_MODEL", "cosmos-reason")
        self.timeout_s = timeout_s
        self.configured = bool(
            self.base_url
            and self.model
            and self.model != "replace-with-your-model-id"
        )

    async def readiness(self) -> Dict[str, Any]:
        """Prove that the configured OpenAI endpoint advertises this model."""
        if not self.configured:
            return {
                "ready": False,
                "backend": self.name,
                "reason": "set a non-placeholder IC_CHAT_MODEL_URL and IC_CHAT_MODEL",
            }
        headers = {}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout_s, 15.0)) as client:
                response = await client.get(f"{self.base_url}/v1/models", headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return {
                "ready": False,
                "backend": self.name,
                "model": self.model,
                "reason": f"model endpoint probe failed: {type(exc).__name__}",
            }
        models = {
            str(item.get("id"))
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        } if isinstance(payload, dict) else set()
        if self.model not in models:
            return {
                "ready": False,
                "backend": self.name,
                "model": self.model,
                "reason": "configured model is not advertised by the endpoint",
                "advertised_models": sorted(models),
            }
        return {"ready": True, "backend": self.name, "model": self.model}

    async def respond(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not self.base_url:
            raise RuntimeError("IC_CHAT_MODEL_URL is not set")
        payload: Dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise RuntimeError(f"model returned no choices: {str(data)[:200]}")
        msg = choices[0].get("message", {})
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", "{}")
            try:
                parsed = json.loads(args) if isinstance(args, str) else args
            except Exception:
                parsed = {}
            calls.append({"id": tc.get("id", ""), "name": fn.get("name", ""), "arguments": parsed})
        return {"content": msg.get("content") or "", "tool_calls": calls}


class OpenClawBackend(OpenAIBackend):
    """Headless OpenClaw adapter with a compatibility HTTP responder.

    Normal IC Chat operation uses OpenClaw's typed Gateway protocol: OpenClaw
    owns its namespaced MCP tools and this class streams native tool lifecycle
    events back to the console.  ``respond`` remains available for explicit
    compatibility/testing of the OpenAI-shaped HTTP endpoint.
    """

    name = "openclaw"

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: Optional[float] = None,
        config_path: Optional[str] = None,
        native_gateway: Optional[bool] = None,
    ) -> None:
        resolved_timeout_s = float(
            timeout_s
            if timeout_s is not None
            else os.environ.get("IC_OPENCLAW_TIMEOUT_S", "900")
        )
        self.config_path = Path(
            config_path
            or os.environ.get(
                "IC_OPENCLAW_CONFIG",
                str(Path.home() / ".industrial-claw" / "openclaw" / "openclaw.json"),
            )
        ).expanduser()
        config: Dict[str, Any] = {}
        try:
            config = json.loads(self.config_path.read_text())
        except (OSError, ValueError, TypeError):
            pass
        gateway = config.get("gateway") if isinstance(config, dict) else {}
        gateway = gateway if isinstance(gateway, dict) else {}
        auth = gateway.get("auth") if isinstance(gateway.get("auth"), dict) else {}
        endpoint = gateway.get("http") if isinstance(gateway.get("http"), dict) else {}
        endpoint = endpoint.get("endpoints") if isinstance(endpoint.get("endpoints"), dict) else {}
        chat_endpoint = (
            endpoint.get("chatCompletions")
            if isinstance(endpoint.get("chatCompletions"), dict)
            else {}
        )
        token = api_key or os.environ.get("IC_OPENCLAW_TOKEN", "") or auth.get("token", "")
        url = base_url or os.environ.get("IC_OPENCLAW_URL", "http://127.0.0.1:18790")
        target = model or os.environ.get("IC_OPENCLAW_AGENT_MODEL", "openclaw/ic-console")
        super().__init__(
            base_url=url,
            api_key=str(token),
            model=target,
            timeout_s=resolved_timeout_s,
        )
        if native_gateway is None:
            native_gateway = os.environ.get("IC_OPENCLAW_NATIVE_GATEWAY", "1") != "0"
        self.native_tool_owner = bool(native_gateway)
        ws_url = os.environ.get("IC_OPENCLAW_WS_URL", "")
        if not ws_url:
            ws_url = self.base_url
            if ws_url.startswith("https://"):
                ws_url = "wss://" + ws_url[len("https://"):]
            elif ws_url.startswith("http://"):
                ws_url = "ws://" + ws_url[len("http://"):]
        self.gateway = OpenClawGatewayClient(
            ws_url=ws_url,
            token=self.api_key,
            agent_id=os.environ.get("IC_OPENCLAW_AGENT_ID", "ic-console"),
            timeout_s=resolved_timeout_s,
        )
        # Native mode needs only the Gateway socket/config.  HTTP compatibility
        # additionally requires chatCompletions to be enabled.
        self.configured = bool(
            self.base_url
            and (
                base_url is not None
                or api_key is not None
                or os.environ.get("IC_OPENCLAW_TOKEN")
                or (self.native_tool_owner and self.config_path.exists())
                or chat_endpoint.get("enabled") is True
            )
        )

    async def run_native_stream(
        self, messages: List[Dict[str, Any]], mission_id: str
    ) -> AsyncIterator[Dict[str, Any]]:
        if not self.native_tool_owner:
            raise RuntimeError("OpenClaw native Gateway mode is disabled")
        last_user = next(
            (str(m.get("content") or "") for m in reversed(messages)
             if m.get("role") == "user"),
            "",
        )
        if not last_user:
            raise RuntimeError("OpenClaw turn has no user message")
        async for event in self.gateway.run_stream(last_user, mission_id):
            yield event

    async def request_stop(self, mission_id: str) -> Dict[str, Any]:
        return await self.gateway.request_stop(mission_id)


class AnthropicBackend:
    """Anthropic Messages API — the host the OpenClaw gateway itself runs on.

    Same deliberation brain as the gateway (Claude via the NVIDIA NIM provider
    declared in openclaw.json), reached through the documented adapter seam
    instead of embedding the gateway's own UI: the console keeps its CSP, the
    gateway keeps X-Frame-Options, and the conversation renders in the console's
    chat surface with the usual tool cards + evidence frames.

    Env: IC_CHAT_MODEL_URL (e.g. https://inference-api.nvidia.com),
    IC_CHAT_API_KEY (NVIDIA_NIM_API_KEY), IC_CHAT_MODEL (e.g.
    aws/anthropic/bedrock-claude-opus-4-8).
    """

    name = "anthropic"

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: float = 300.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("IC_CHAT_MODEL_URL", "")).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("IC_CHAT_API_KEY", "")
            or os.environ.get("NVIDIA_NIM_API_KEY", "")
        )
        self.model = model or os.environ.get("IC_CHAT_MODEL", "")
        self.max_tokens = int(os.environ.get("IC_CHAT_MAX_TOKENS", "4096"))
        self.timeout_s = timeout_s
        self.configured = bool(
            self.base_url
            and self.model
            and self.api_key
            and self.model != "replace-with-your-model-id"
        )

    async def readiness(self) -> Dict[str, Any]:
        # The Messages API has no side-effect-free model-list contract. Refuse
        # incomplete configuration without spending tokens on a probe turn.
        return {
            "ready": self.configured,
            "backend": self.name,
            "model": self.model,
            "probe": "configuration-only",
            **({} if self.configured else {
                "reason": "IC_CHAT_MODEL_URL, IC_CHAT_MODEL, and API key are required"
            }),
        }

    @staticmethod
    def _to_anthropic(messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
        """Split the loop's message list into (system, messages) Anthropic-side.

        The tool loop speaks the OpenAI shape (role=tool with tool_call_id);
        translate those to Anthropic tool_result blocks so a tool turn round-trips.
        """
        system = ""
        out: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                system = str(m.get("content") or "")
            elif role == "tool":
                out.append({"role": "user", "content": [{
                    "type": "tool_result",
                    "tool_use_id": str(m.get("tool_call_id") or ""),
                    "content": str(m.get("content") or ""),
                }]})
            elif role == "assistant":
                blocks: List[Dict[str, Any]] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": str(m["content"])})
                for tc in m.get("tool_calls") or []:
                    # The loop stores assistant tool calls in the OpenAI shape
                    # (function.name + JSON-string arguments) once they have
                    # been executed, and in the flat shape as emitted. Accept
                    # both: a tool_use block with an empty name is a 400.
                    fn = tc.get("function") or {}
                    name = tc.get("name") or fn.get("name") or ""
                    raw = tc.get("arguments")
                    if raw is None:
                        raw = fn.get("arguments")
                    if isinstance(raw, str):
                        try:
                            raw = json.loads(raw or "{}")
                        except Exception:
                            raw = {}
                    if not name:
                        continue  # never emit a nameless tool_use
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": name,
                        "input": raw if isinstance(raw, dict) else {},
                    })
                if blocks:
                    out.append({"role": "assistant", "content": blocks})
            elif role == "user" and m.get("content"):
                out.append({"role": "user", "content": str(m["content"])})
        return system, out

    async def respond(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not self.base_url or not self.model:
            raise RuntimeError("IC_CHAT_MODEL_URL and IC_CHAT_MODEL must be set")
        system, msgs = self._to_anthropic(messages)
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": msgs,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [{
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("parameters") or {"type": "object", "properties": {}},
            } for t in tools]
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
            headers["authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(f"{self.base_url}/v1/messages", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        text_parts: List[str] = []
        calls: List[Dict[str, Any]] = []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append({
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "arguments": block.get("input") or {},
                })
        return {"content": "".join(text_parts), "tool_calls": calls}


class EchoBackend:
    """No-network backend. A user line 'tool <name> {json}' becomes a tool call."""

    name = "echo"
    configured = True

    async def respond(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        # If the most recent message is a tool result, the action already ran —
        # summarize and stop (a real model does the same). This prevents the
        # demo backend from re-firing the same directive every loop turn.
        if messages and messages[-1].get("role") == "tool":
            return {"content": "done (tool result received)", "tool_calls": []}
        last = next(
            (m for m in reversed(messages) if m.get("role") == "user"), {"content": ""}
        )
        text = str(last.get("content", "")).strip()
        if text.startswith("tool "):
            rest = text[len("tool ") :].strip()
            name, _, arg_str = rest.partition(" ")
            try:
                args = json.loads(arg_str) if arg_str else {}
            except Exception:
                args = {}
            return {"content": "", "tool_calls": [{"id": "echo-0", "name": name, "arguments": args}]}
        return {"content": f"echo: {text}", "tool_calls": []}


def make_backend(kind: Optional[str] = None) -> ChatBackend:
    kind = kind or os.environ.get("IC_CHAT_BACKEND", "openai")
    if kind == "openai":
        return OpenAIBackend()
    if kind == "anthropic":
        return AnthropicBackend()
    if kind == "openclaw":
        return OpenClawBackend()
    if kind == "echo":
        return EchoBackend()
    raise ValueError(f"unknown chat backend: {kind!r}")
