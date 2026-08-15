# TEMPLATE skill — copy this directory, rename, write the know-how

A skill is versioned *know-how*: it teaches any brain how to compose tool verbs
(from certified MCP servers) into a competent, safe procedure for one class of
goal. The reference skill is
[`../industrial-claw-orchestrator/PLAYBOOK.md`](../industrial-claw-orchestrator/PLAYBOOK.md)
— study its shape.

## The workflow

1. Copy to `skills/<your-skill>/`; fill in `manifest.yaml` (the machine-readable
   contract) and this file (the know-how).
2. Validate: `ic-conformance skill --manifest manifest.yaml`.
3. Deliver: sync into a harness profile (`ops/sync-playbook.sh` pattern) or ship
   as MCP `instructions`/prompts on the relevant server.
4. Measure: run missions; the journal ties `mission_id` -> outcome, giving the
   skill a success rate. A skill without measurements is an opinion.

## What the know-how section must contain

- **World model / vocabulary** — name every object, region, endpoint the skill touches
- **The loop** — when to look, when to act, when to verify, when to stop and escalate
- **Action forms** — exact parameters for each allowed action, with an example
- **Failure ladder** — retries (how many), fallbacks, and the escalation message
- **Done criteria** — how the skill PROVES the goal state (same as the manifest)
- **Never-do list** — the sharp edges of your domain, written in blood

Write for a competent stranger: the model executing this has your words and the
tool contracts — nothing else.
