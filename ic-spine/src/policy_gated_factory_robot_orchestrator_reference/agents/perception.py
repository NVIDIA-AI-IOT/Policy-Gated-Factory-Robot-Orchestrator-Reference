# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PerceptionAgent — selects the best InputSource for a query, calls the VLM, returns structured answers."""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from policy_gated_factory_robot_orchestrator_reference.clients.vlm.base import VLMClient
from policy_gated_factory_robot_orchestrator_reference.input_sources.base import InputSource


class PerceptionAgent:
    def __init__(self, sources: Sequence[InputSource], vlm: VLMClient) -> None:
        self._sources = sources
        self._vlm = vlm

    def list_input_sources(
        self,
        modality_filter: str | None = None,
        region_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            s.metadata()
            for s in self._sources
            if (modality_filter is None or s.modality == modality_filter)
            and (region_filter is None or s.coverage_region == region_filter)
        ]

    async def check_predicate(
        self, predicate: str, target_region_id: str | None = None
    ) -> dict[str, Any]:
        src = self._pick_image_source(target_region_id)
        if src is None:
            return {"answer": "unknown", "evidence": "no input source available", "source_used": ""}
        snap = await src.snapshot()
        prompt = _predicate_prompt(predicate, target_region_id)
        resp = await self._vlm.query(image_bytes=snap.image_bytes, prompt=prompt)
        answer = self._normalize_yes_no(resp.answer)
        return {"answer": answer, "evidence": resp.evidence or resp.answer, "source_used": src.id}

    async def observe_visual(self, region_id: str | None = None) -> dict[str, Any]:
        """Vision-only structured observation of a region from its camera — the "eyes".

        Returns what the VLM actually SEES (which colored cubes and where, whether a tote
        sits on the rack) as structured data. It is deliberately a raw perception: the
        caller fuses this against the symbolic floor state and, on any conflict, flags the
        mismatch and trusts ground truth (vision-first, but symbolic wins ties). ``parse_ok``
        is False when the VLM didn't return usable JSON — treat the result as low-confidence.
        """
        src = self._pick_image_source(region_id)
        if src is None:
            return {
                "region": region_id,
                "source_used": "",
                "cubes_visible": [],
                "tote_on_rack": None,
                "summary": "no input source available",
                "parse_ok": False,
                "raw": "",
            }
        snap = await src.snapshot()
        resp = await self._vlm.query(
            image_bytes=snap.image_bytes,
            prompt=_visual_observe_prompt(region_id),
        )
        parsed = _scope_observation(_parse_observation(resp.answer), region_id)
        return {
            "region": region_id,
            "source_used": src.id,
            "cubes_visible": parsed["cubes_visible"],
            "tote_on_rack": parsed["tote_on_rack"],
            "summary": parsed["summary"],
            "parse_ok": parsed["parse_ok"],
            "raw": resp.answer,
        }

    async def describe(self, region_id: str | None = None) -> dict[str, Any]:
        src = self._pick_image_source(region_id)
        if src is None:
            return {"description": "no input source available", "source_used": ""}
        snap = await src.snapshot()
        resp = await self._vlm.query(
            image_bytes=snap.image_bytes,
            prompt="Describe what you see in 1-3 sentences focused on object identities and locations.",
        )
        return {"description": resp.answer, "source_used": src.id}

    def _pick_image_source(self, region_id: str | None) -> InputSource | None:
        image_sources = [s for s in self._sources if s.modality == "image"]
        if not image_sources:
            return None
        if region_id is None:
            return image_sources[0]
        matched = [s for s in image_sources if s.coverage_region == region_id]
        return matched[0] if matched else image_sources[0]

    @staticmethod
    def _normalize_yes_no(text: str) -> str:
        lowered = text.strip().lower()
        if lowered.startswith("yes"):
            return "yes"
        if lowered.startswith("no"):
            return "no"
        tagged = re.search(
            r"<answer>\s*(yes|no|unknown)\b",
            lowered,
        )
        if tagged:
            return tagged.group(1)
        return "unknown"


# --- visual observation: grounded JSON prompt + a defensive parser ----------------
# Cosmos renders the cubes as flat colored squares and, ungrounded, calls them "buttons"
# or "a panel"; the prompt names the scene so the structured read stays trustworthy.
_VISUAL_OBSERVE_PROMPT = (
    "This is one camera frame from a robotic warehouse sorting cell. Depending on the camera "
    "you may see (elevated table view) a tan work table with one or two white Franka arms; "
    "the CONVEYOR is the wide dark-gray HORIZONTAL band across the LOWER half of the frame. "
    "The sortable objects are specifically a RED CUBE, a BLUE CYLINDER, and a GREEN "
    "RECTANGULAR BRICK. There may be one set at each arm, so a color/shape can appear twice; "
    "scan the whole visible band. The TOTE is a gray open bin near an arm; two camera regions "
    "cover two separate totes, one belonging to each arm. Each tote floor has three colored "
    "compartment PADS (red, blue, green) that are PART OF THE TOTE — an empty tote still "
    "shows three colored rectangles. Count an object as 'in the tote' ONLY if the raised red "
    "cube, blue cylinder, or green brick sits ON a pad and has a visible edge/shadow; a bare "
    "pad is flat. Or you may see (wide side view) a warehouse aisle "
    "where the RACK is the WHITE multi-tier shelf near frame center — ignore background "
    "shelving, carts and boxes; either or both totes may rest on separate levels of that rack. "
    "Report ONLY what is visible in THIS frame as a single JSON object and nothing else, "
    "in exactly this shape:\n"
    '{"cubes_visible": [{"color": "red|blue|green", "where": "conveyor|tote|rack|floor|other"}], '
    '"tote_on_rack": true|false|null, "summary": "<one short sentence>"}\n'
    "Set tote_on_rack to null unless the white rack itself is visible in this frame. List "
    "each visible sortable object once in cubes_visible (the field name is retained for API "
    "compatibility); do NOT list bare tote pads as objects. Output only the JSON object."
)

_REGION_GROUNDING = {
    "conveyor_1": (
        "This crop covers only the LEFT conveyor work area. The conveyor may be empty. "
        "Do not infer a tote or rack outside the crop."
    ),
    "conveyor_2": (
        "This crop covers only the RIGHT conveyor work area. The conveyor may be empty. "
        "Do not infer a tote or rack outside the crop."
    ),
    "tote": (
        "This crop covers only the LEFT tote's workcell location. The tote may be absent "
        "because it has already been hauled away. Do not infer where an absent tote went."
    ),
    "tote_r": (
        "This crop covers only the RIGHT tote's workcell location. The tote may be absent "
        "because it has already been hauled away. Do not infer where an absent tote went."
    ),
    "rack_1": (
        "This frame covers the WHITE multi-tier rack. Ignore background shelving, carts, "
        "and boxes. A tote counts as on-rack only when a gray open bin visibly rests on a "
        "shelf of that white rack."
    ),
}

_SORTABLE_OBJECT_GROUNDING = (
    "The only sortable object types are a visibly raised RED CUBE, BLUE CYLINDER, and "
    "GREEN RECTANGULAR BRICK. White robot parts are not sortable objects. A tote's flat "
    "red, blue, and green compartment pads are part of the tote and are not objects. "
    "An object must have a visible raised edge or shadow; never infer an occluded object. "
)

_OBSERVATION_SCHEMA = (
    "Return only one JSON object in exactly this shape:\n"
    '{"cubes_visible": [{"color": "red|blue|green", '
    '"where": "conveyor|tote|rack|floor|other"}], '
    '"tote_on_rack": true|false|null, "summary": "<one short sentence>"}\n'
)


def _predicate_prompt(predicate: str, region_id: str | None) -> str:
    """Ground a yes/no check in the camera's actual coverage region."""
    grounding = _REGION_GROUNDING.get(region_id or "")
    if grounding is None:
        # Preserve the broad table-view contract used by the existing demo.
        grounding = (
            "This is an elevated table view with one or two white Franka arms. The "
            "CONVEYOR is the wide dark-gray horizontal band. There can be one object set "
            "at each arm. There are two separate totes: the left tote belongs to the left "
            "arm and the right tote belongs to the right arm. The RACK, when visible, is "
            "the white multi-tier shelf. Both totes can be on different levels of the same rack."
        )
    return (
        "This is one camera frame from a simulated robotic warehouse sorting cell. "
        + grounding
        + " "
        + _SORTABLE_OBJECT_GROUNDING
        + "Judge only visible pixels. If the relevant area is not visible, answer unknown. "
        "Reply with exactly one word on the first line—yes, no, or unknown—then one short "
        "sentence citing visible evidence.\nQuestion: "
        + predicate
    )


def _visual_observe_prompt(region_id: str | None) -> str:
    """Return a compact prompt scoped to the selected source, not the whole factory."""
    grounding = _REGION_GROUNDING.get(region_id or "")
    if grounding is None:
        return _VISUAL_OBSERVE_PROMPT
    location_rule = {
        "conveyor_1": "Every reported object must use where=conveyor. Set tote_on_rack=null.",
        "conveyor_2": "Every reported object must use where=conveyor. Set tote_on_rack=null.",
        "tote": "Every reported object must use where=tote. Set tote_on_rack=null.",
        "tote_r": "Every reported object must use where=tote. Set tote_on_rack=null.",
        "rack_1": "Use where=rack for sortable objects visibly resting on the rack.",
    }[region_id or ""]
    return (
        "This is one camera frame from a simulated robotic warehouse sorting cell. "
        + grounding
        + " "
        + _SORTABLE_OBJECT_GROUNDING
        + location_rule
        + " Judge only visible pixels; an empty or irrelevant crop must produce an empty "
        "cubes_visible list. "
        + _OBSERVATION_SCHEMA
        + "Output only the JSON object."
    )

_CUBE_COLORS = {"red", "blue", "green"}
_CUBE_WHERE = {"conveyor", "tote", "rack", "floor", "other"}


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """First balanced-looking JSON object in ``text`` (tolerates code fences / surrounding prose)."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _coerce_bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    token = str(value).strip().lower()
    if token in ("true", "yes"):
        return True
    if token in ("false", "no"):
        return False
    return None  # "unknown", "null", anything ambiguous -> not visible / not asserted


def _normalize_cubes(raw: Any) -> list[dict[str, str]]:
    cubes: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return cubes
    for item in raw:
        if not isinstance(item, dict):
            continue
        color = str(item.get("color", "")).strip().lower()
        where = str(item.get("where", item.get("location", "")) or "").strip().lower()
        if color in _CUBE_COLORS:
            cubes.append({"color": color, "where": where if where in _CUBE_WHERE else "other"})
    return cubes


def _parse_observation(text: str) -> dict[str, Any]:
    """Structured scene from the VLM's reply; ``parse_ok`` False falls back to the raw text."""
    obj = _extract_json_object(text)
    if obj is None:
        return {
            "cubes_visible": [],
            "tote_on_rack": None,
            "summary": text.strip()[:300],
            "parse_ok": False,
        }
    return {
        "cubes_visible": _normalize_cubes(obj.get("cubes_visible")),
        "tote_on_rack": _coerce_bool_or_none(obj.get("tote_on_rack")),
        "summary": str(obj.get("summary", "")).strip(),
        "parse_ok": True,
    }


def _scope_observation(
    observation: dict[str, Any], region_id: str | None
) -> dict[str, Any]:
    """Enforce only facts that the selected camera can physically establish."""
    scoped = dict(observation)
    allowed_locations = {
        "conveyor_1": {"conveyor"},
        "conveyor_2": {"conveyor"},
        "tote": {"tote"},
        "tote_r": {"tote"},
        "rack_1": {"rack", "tote"},
    }.get(region_id or "")
    if allowed_locations is not None:
        scoped["cubes_visible"] = [
            item
            for item in scoped.get("cubes_visible", [])
            if item.get("where") in allowed_locations
        ]
    if region_id in {"conveyor_1", "conveyor_2", "tote", "tote_r"}:
        scoped["tote_on_rack"] = None
    return scoped
