// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Floor dispatch policy enforced as a before_tool_call hook: PGFR composes the floor
// primitives freely, but every dispatch_task is gated here BEFORE it reaches the
// floor. Pure + side-effect free so it is exhaustively unit-testable; the hook in
// index.ts wires it to the gateway and traces each decision.

export type DispatchPolicyDecision = { allow: true } | { allow: false; reason: string };

/** Verbs the floor is allowed to execute. Anything else is refused up front. */
const ALLOWED_ACTIONS = new Set(["move", "pick_and_place"]);

/** Parameters each allowed action must carry before it may be dispatched. */
const REQUIRED_PARAMS: Record<string, readonly string[]> = {
  move: ["endpoint", "color", "from", "destination"],
  pick_and_place: ["endpoint", "object_id", "target_id"],
};

/** Destinations a block must never be placed on (people, walkways, the bare floor). */
const PROHIBITED_DESTINATIONS = new Set([
  "human",
  "person",
  "operator",
  "worker",
  "floor",
  "aisle",
  "walkway",
]);

function asTrimmed(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Decide whether a dispatch_task call may proceed.
 *
 * Order: action allowlist → required-parameter preconditions → prohibited-destination
 * denylist. Returns the first failing rule's reason, or `{ allow: true }`.
 */
export function evaluateDispatchPolicy(params: Record<string, unknown>): DispatchPolicyDecision {
  const action = asTrimmed(params.action).toLowerCase();
  if (!ALLOWED_ACTIONS.has(action)) {
    return {
      allow: false,
      reason: `action '${asTrimmed(params.action) || "(none)"}' is not permitted; allowed: ${[
        ...ALLOWED_ACTIONS,
      ].join(", ")}`,
    };
  }

  const required = REQUIRED_PARAMS[action] ?? [];
  const missing = required.filter((key) => asTrimmed(params[key]) === "");
  if (missing.length > 0) {
    return {
      allow: false,
      reason: `${action} requires ${required.join(", ")}; missing: ${missing.join(", ")}`,
    };
  }

  // A move names its landing spot in `destination`; a pick_and_place in `target_id`.
  const landing = asTrimmed(params.destination) || asTrimmed(params.target_id);
  if (PROHIBITED_DESTINATIONS.has(landing.toLowerCase())) {
    return {
      allow: false,
      reason: `refusing to place onto prohibited destination '${landing}'`,
    };
  }

  return { allow: true };
}
