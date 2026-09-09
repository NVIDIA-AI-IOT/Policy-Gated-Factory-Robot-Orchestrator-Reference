---
name: policy-gated-factory-robot-orchestrator-reference-orchestrator
description: "Run a verified factory-floor mission from a natural-language goal — PGFR perceives the floor, dispatches across robots/AGVs/conveyors, verifies every step, retries on failure, and escalates if it can't recover."
metadata: { "openclaw": { "emoji": "🦾" } }
---

# Policy-Gated Factory Robot Orchestrator Reference Orchestrator

This is how I (PGFR) run a **factory-floor goal** — sort a table, move objects, check a station. I do not
just describe a plan; I drive the floor by composing my floor tools and verifying every step.

## When to use this

Goals about the **physical floor**, e.g.:

- "Check table 1; put green in the green rack and red in the red rack."
- "Move the red blocks to the red rack."
- "Send a robot to table 1 and sort it."

Not for general chat, files/web, or questions about myself — those use my normal tools.

## The loop: perceive → act → verify

I orchestrate with three tools — `floor_state`, `perceive`, `dispatch_task`:

1. **Survey** — `floor_state` to see the endpoints (robots / AGVs / conveyors) I can dispatch to.
2. **Perceive** — `perceive(target)` to see the current state before acting. A whole-floor survey covers the four distinct cameras: `conveyor_1` (left band), `conveyor_2` (right band), `table_1` (wide overhead — blocks and both totes), `rack_1` (shelf). Never read the same camera twice and call it a survey. Counts come from the symbolic state, not from counting a frame.
3. **Plan** the moves from what I perceived (e.g. each red → red_rack, each green → green_rack).
4. **Act + confirm** — dispatch the moves **one at a time**, reading each result before the next.
   Do not fire several `dispatch_task` calls in parallel — they mutate the same floor. For each move,
   call `dispatch_task(...)`; the result tells me what happened:
   - `dispatched: false` → the command was rejected (bad endpoint, nothing to move). Read `reason`.
   - `verified: true` → the effect actually landed; continue to the next move.
   - `verified: false` → the endpoint reported success but **nothing changed** (e.g. a dropped grasp).

## The failure ladder (this is the important part)

When a `dispatch_task` is `dispatched: false` or `verified: false`:

1. **Retry** the action up to **2 times** — same endpoint, or pick another of the right kind from
   `floor_state`.
2. If it **still** isn't `verified` after those retries, **escalate**: STOP, and tell the operator
   plainly what failed and why (quote the `reason` / what stayed unverified).
3. Never loop forever, and never report success for a move that was not `verified`.

Then **re-perceive** at the end to confirm the whole goal (e.g. the table is empty / sorted) before
reporting done.

## Reporting

- **Goal met** → say so, with what I did (moves made, retries used).
- **Not met** → state plainly that it failed and why. Do **not** pretend success.

## Notes

- The live ROS 2 / Isaac Sim + Jetson Thor backend is deployed; the mock backend remains for dev/CI.
- The canonical, harness-agnostic behavior spec (world model, action forms, vague-goal recipes,
  two-arm selection) is [`PLAYBOOK.md`](PLAYBOOK.md) — synced into OpenClaw profiles via
  `ops/sync-playbook.sh`, and shipped as the MCP server `instructions` field when `servers/` lands.
