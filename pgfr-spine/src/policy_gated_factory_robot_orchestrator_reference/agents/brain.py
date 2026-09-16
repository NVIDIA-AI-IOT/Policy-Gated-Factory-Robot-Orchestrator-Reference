# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""BrainAgent — orchestrator. Plans, delegates, verifies, retries, replans, escalates."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from policy_gated_factory_robot_orchestrator_reference.agents.action import ActionAgent
from policy_gated_factory_robot_orchestrator_reference.agents.perception import PerceptionAgent
from policy_gated_factory_robot_orchestrator_reference.clients.llm.base import LLMClient
from policy_gated_factory_robot_orchestrator_reference.types import (
    MissionResult,
    Subtask,
    SubtaskKind,
)


class InvalidPlanError(ValueError):
    """Raised when the LLM produces a plan that cannot be parsed or validated."""


@dataclass
class BrainConfig:
    max_subtasks: int = 20
    max_replans: int = 3
    max_mission_seconds: float = 600.0
    default_max_attempts: int = 2


@dataclass
class BrainAgent:
    llm: LLMClient
    perception: PerceptionAgent
    action: ActionAgent
    config: BrainConfig = field(default_factory=BrainConfig)

    async def plan(
        self,
        operator_goal: str,
        context_extra: str = "",
        max_attempts: int = 2,
    ) -> list[Subtask]:
        """Produce a validated plan.

        If the LLM's first response fails validation (malformed JSON, unknown endpoint, etc.),
        retry with the validation error fed back into the user prompt so the LLM can correct
        itself. Bounded by ``max_attempts``; raises ``InvalidPlanError`` if every attempt fails.
        """
        last_error: str | None = None
        for _attempt in range(max_attempts):
            user = self._user_prompt(operator_goal, context_extra)
            if last_error is not None:
                user += (
                    f"\n\nYour previous attempt failed plan validation: {last_error}. "
                    "Respond again with only a single valid JSON object."
                )
            response = await self.llm.complete(system=self._system_prompt(), user=user)
            try:
                return self._parse_plan(response.text)
            except InvalidPlanError as exc:
                last_error = str(exc)
        raise InvalidPlanError(
            f"plan validation failed after {max_attempts} attempts: {last_error}"
        )

    # --- prompt construction ---

    def _system_prompt(self) -> str:
        return (
            "You are the planning brain of Policy-Gated Factory Robot Orchestrator Reference, a factory orchestration agent. "
            "Given an operator goal and the current world context, produce a JSON plan of subtasks. "
            "Each subtask is either:\n"
            "  - {kind: 'action', endpoint_id, capability, args, verify?, max_attempts?}\n"
            "  - {kind: 'perception', query, args, verify?, max_attempts?}\n"
            "Use only endpoint_ids and capabilities listed in the context. "
            "Respond with a single JSON object: {\"plan\": [ ... subtasks ... ]}. "
            "Keep plans short and rely on verification between steps."
        )

    def _user_prompt(self, operator_goal: str, context_extra: str) -> str:
        endpoints = self.action.list_action_endpoints()
        sources = self.perception.list_input_sources()
        ctx = {
            "operator_goal": operator_goal,
            "action_endpoints": endpoints,
            "input_sources": sources,
            "constraints": {
                "max_subtasks": self.config.max_subtasks,
                "default_max_attempts": self.config.default_max_attempts,
            },
        }
        suffix = f"\n\nAdditional context:\n{context_extra}" if context_extra else ""
        return json.dumps(ctx, indent=2) + suffix

    # --- response parsing & validation ---

    _FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

    def _parse_plan(self, raw: str) -> list[Subtask]:
        obj = self._extract_json(raw)
        if not isinstance(obj, dict) or "plan" not in obj or not isinstance(obj["plan"], list):
            raise InvalidPlanError("plan JSON must be {plan: [...]}")
        items = obj["plan"]
        if len(items) > self.config.max_subtasks:
            raise InvalidPlanError(f"plan exceeds max_subtasks={self.config.max_subtasks}")
        subtasks: list[Subtask] = []
        endpoint_caps = {
            e["id"]: {c["name"] for c in e["capabilities"]}
            for e in self.action.list_action_endpoints()
        }
        for item in items:
            try:
                st = Subtask.model_validate(item)
            except ValidationError as exc:
                raise InvalidPlanError(f"subtask schema invalid: {exc}") from exc
            if st.kind.value == "action":
                if st.endpoint_id not in endpoint_caps:
                    raise InvalidPlanError(f"unknown endpoint_id: {st.endpoint_id}")
                if st.capability not in endpoint_caps[st.endpoint_id]:
                    raise InvalidPlanError(
                        f"endpoint {st.endpoint_id} has no capability {st.capability}"
                    )
            subtasks.append(st)
        return subtasks

    def _extract_json(self, raw: str) -> Any:
        m = self._FENCE.search(raw)
        candidate = m.group(1) if m else raw
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise InvalidPlanError(f"plan output is not valid JSON: {exc}") from exc

    # --- orchestration ---

    async def run_mission(self, operator_goal: str) -> MissionResult:
        """Plan a mission from an operator goal, execute each subtask, verify outcomes,
        retry on capability failure, replan on verification failure, escalate when exhausted.
        """
        mission_id = uuid.uuid4().hex[:8]
        start = time.monotonic()
        retries = 0
        replans_used = 0

        try:
            initial = await self.perception.describe()
            context_extra = f"Initial scene: {initial.get('description', '')}"
            plan = await self.plan(operator_goal, context_extra=context_extra)
        except InvalidPlanError as exc:
            return MissionResult(
                mission_id=mission_id, goal_met=False, subtask_count=0,
                retries=0, escalated=True,
                duration_seconds=time.monotonic() - start,
                reason=f"planning failed: {exc}",
            )

        idx = 0
        executed = 0
        while idx < len(plan):
            if time.monotonic() - start > self.config.max_mission_seconds:
                return MissionResult(
                    mission_id=mission_id, goal_met=False, subtask_count=executed,
                    retries=retries, escalated=True,
                    duration_seconds=time.monotonic() - start,
                    reason="max_mission_seconds exceeded",
                )

            subtask = plan[idx]
            outcome = await self._run_subtask_with_retries(subtask)
            retries += outcome.retries_used
            executed += 1

            if not outcome.success:
                # Tier 2: replan this subtask with the failure context.
                if replans_used < self.config.max_replans:
                    replans_used += 1
                    retries += 1  # a replan counts as a retry in the mission summary
                    try:
                        new_plan = await self.plan(
                            operator_goal,
                            context_extra=(
                                f"Subtask {idx} failed (reason: {outcome.reason}). "
                                f"Original plan: {[s.model_dump() for s in plan]}. "
                                "Produce a revised plan starting from the current state."
                            ),
                        )
                    except InvalidPlanError as exc:
                        return MissionResult(
                            mission_id=mission_id, goal_met=False, subtask_count=executed,
                            retries=retries, escalated=True,
                            duration_seconds=time.monotonic() - start,
                            reason=f"replan failed: {exc}",
                        )
                    plan = new_plan
                    idx = 0
                    continue
                # Tier 3: escalate.
                return MissionResult(
                    mission_id=mission_id, goal_met=False, subtask_count=executed,
                    retries=retries, escalated=True,
                    duration_seconds=time.monotonic() - start,
                    reason=f"subtask {idx} failed and replan budget exhausted",
                )

            idx += 1

        return MissionResult(
            mission_id=mission_id, goal_met=True, subtask_count=executed,
            retries=retries, escalated=False,
            duration_seconds=time.monotonic() - start,
        )

    async def _run_subtask_with_retries(self, subtask: Subtask) -> _SubtaskOutcome:
        """Tier 1: run the subtask, optionally verify, retry up to subtask.max_attempts on failure."""
        attempts = max(1, subtask.max_attempts)
        last_reason: str | None = None
        for attempt in range(attempts):
            ok, reason = await self._execute_once(subtask)
            if ok:
                if subtask.verify:
                    verdict = await self.perception.check_predicate(
                        subtask.verify, target_region_id=None
                    )
                    if verdict["answer"] == "yes":
                        return _SubtaskOutcome(success=True, retries_used=attempt)
                    last_reason = f"verify failed: {verdict.get('evidence', '')}"
                else:
                    return _SubtaskOutcome(success=True, retries_used=attempt)
            else:
                last_reason = reason
        return _SubtaskOutcome(
            success=False, retries_used=attempts - 1, reason=last_reason
        )

    async def _execute_once(self, subtask: Subtask) -> tuple[bool, str | None]:
        """Dispatch one subtask: action.execute(...) for action kind, perception.* for perception kind."""
        if subtask.kind is SubtaskKind.ACTION:
            assert subtask.endpoint_id is not None
            assert subtask.capability is not None
            r = await self.action.execute(
                subtask.endpoint_id, subtask.capability, subtask.args
            )
            return bool(r["success"]), r.get("reason")
        # perception subtask
        if subtask.query == "describe_scene":
            await self.perception.describe(region_id=subtask.args.get("region_id"))
            return True, None
        if subtask.query == "check_predicate":
            predicate = subtask.args.get("predicate", "")
            region = subtask.args.get("region_id")
            verdict = await self.perception.check_predicate(predicate, target_region_id=region)
            return verdict["answer"] != "no", verdict.get("evidence")
        return False, f"unknown perception query: {subtask.query}"


@dataclass
class _SubtaskOutcome:
    success: bool
    retries_used: int = 0
    reason: str | None = None
