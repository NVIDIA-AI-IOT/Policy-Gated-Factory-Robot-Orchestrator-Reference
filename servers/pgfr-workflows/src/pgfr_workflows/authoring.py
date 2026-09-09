# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NL → verified artifact. The assistant drafts a workflow or skill manifest
from a plain-language instruction; the draft is validated against the real
schema BEFORE it is returned (retrying with the validation error fed back), so
nothing unschema'd can escape to the user or the store.

New PRIMITIVE tools cannot be authored here — those need floor-engine code. New
COMPOSITE tools are made by authoring a workflow and publishing it as a skill.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .spec import TOOLS, Workflow

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _palette() -> str:
    lines = []
    for name, t in TOOLS.items():
        params = t.get("params", {})
        ex = t.get("example", {})
        parg = ", ".join(f"{k} ({v})" for k, v in params.items()) or "no args"
        lines.append(f"- {name}: {t['description']}  args: {parg}"
                     + (f"  example: {json.dumps(ex)}" if ex else ""))
    return "\n".join(lines)


WORKFLOW_RULES = (
    "Output ONLY a JSON object for a Policy-Gated Factory Robot Orchestrator Reference workflow, no prose, no code fence.\n"
    "Schema: {name: kebab-case string, description: string, params: {name: desc} (optional),\n"
    "  steps: [{tool: one of the tools below, args: {..}, max_retries: 0-3 (optional)}],\n"
    "  done_criteria: string}.\n"
    "Rules: linear steps only; use ONLY the listed tools; dispatch_task.action must be "
    "'move' or 'pick_and_place' (never reset/spawn/cancel); reference a run input as "
    "${params.NAME}; reference an earlier step's output as ${steps.N.field} (N < this step); "
    "keep it minimal and correct.\n\nTools:\n" + _palette()
)

SKILL_RULES = (
    "Output ONLY a JSON object for a Policy-Gated Factory Robot Orchestrator Reference skill manifest, no prose, no fence.\n"
    "Schema: {name: kebab-case string, version: '0.1.0', description: string,\n"
    "  requires_tools: [tool names], allowed_actions: [subset of move|pick_and_place],\n"
    "  done_criteria: string}.\n"
    "allowed_actions MUST be agent-class only (move, pick_and_place) — never operator "
    "actions.\n\nTools:\n" + _palette()
)


def _extract_json(text: str) -> Any:
    m = _FENCE.search(text or "")
    raw = m.group(1) if m else (text or "")
    raw = raw.strip()
    # tolerate leading prose before the object
    start = raw.find("{")
    if start > 0:
        raw = raw[start:]
    return json.loads(raw)


def _validate(kind: str, obj: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if kind == "workflow":
        try:
            wf = Workflow.model_validate(obj)
            return wf.model_dump(exclude_none=True), None
        except Exception as exc:
            return None, str(exc)
    if kind == "skill":
        if not isinstance(obj, dict):
            return None, "skill manifest must be a JSON object"
        try:
            from pgfr_conformance.kit import check_skill_manifest  # type: ignore
        except ImportError:
            check_skill_manifest = None  # type: ignore
        required = ("name", "version", "description", "requires_tools",
                    "allowed_actions", "done_criteria")
        missing = [f for f in required if not obj.get(f)]
        if missing:
            return None, f"missing required fields: {missing}"
        actions = obj.get("allowed_actions")
        if not isinstance(actions, list) or not all(isinstance(a, str) for a in actions):
            return None, "allowed_actions must be a list of strings"
        bad = set(actions) - {"move", "pick_and_place"}
        if bad:
            return None, f"allowed_actions must be agent-class; offending: {sorted(bad)}"
        req_tools = obj.get("requires_tools")
        if not isinstance(req_tools, list) or not all(t in TOOLS for t in req_tools):
            return None, f"requires_tools must be a list of known tools: {sorted(TOOLS)}"
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,48}", str(obj["name"])):
            return None, "name must be kebab-case"
        if check_skill_manifest is not None:
            import tempfile
            import os
            import yaml

            fd, tmp = tempfile.mkstemp(suffix=".yaml")
            try:
                with open(tmp, "w") as f:
                    yaml.safe_dump(obj, f)
                fails = [r.name for r in check_skill_manifest(tmp) if not r.passed]
            finally:
                os.close(fd)
                os.unlink(tmp)
            if fails:
                return None, f"conformance failures: {fails}"
        return obj, None
    return None, f"unknown artifact kind: {kind}"


async def author(
    backend: Any, kind: str, instruction: str, max_attempts: int = 3
) -> Dict[str, Any]:
    """Draft + validate an artifact from NL. Returns {ok, kind, draft, error, attempts}."""
    if kind not in ("workflow", "skill"):
        return {"ok": False, "kind": kind, "error": f"unknown kind: {kind}", "attempts": 0}
    rules = WORKFLOW_RULES if kind == "workflow" else SKILL_RULES
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": rules},
        {"role": "user", "content": instruction},
    ]
    last_error = "no response"
    for attempt in range(1, max_attempts + 1):
        reply = await backend.respond(messages, [])
        content = reply.get("content", "") if isinstance(reply, dict) else str(reply)
        try:
            obj = _extract_json(content)
        except Exception as exc:
            last_error = f"model output was not JSON: {exc}"
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content":
                             f"That was not valid JSON ({exc}). Return ONLY the JSON object."})
            continue
        try:
            draft, err = _validate(kind, obj)
        except Exception as exc:  # any validator surprise -> retry, never crash
            draft, err = None, f"could not validate: {type(exc).__name__}: {exc}"
        if draft is not None:
            return {"ok": True, "kind": kind, "draft": draft, "attempts": attempt}
        last_error = err or "validation failed"
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content":
                         f"That did not pass the schema: {err}. Fix it and return ONLY the JSON."})
    return {"ok": False, "kind": kind, "error": last_error, "attempts": max_attempts}
