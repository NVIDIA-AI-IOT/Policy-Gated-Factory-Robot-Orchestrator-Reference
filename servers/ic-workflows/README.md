# ic-workflows — build skills from tool verbs, in the browser

The write-path sibling of [`ic-console`](../../ic-console/): the console's
**Workflows tab** talks to this service. Compose its governed workflow verbs
(`floor_state` · `perceive` · `dispatch_task` · `dispatch_parallel` ·
`check_predicate`) into a linear, gated, retryable workflow; save it as
reviewable YAML; dry-run it; run it through the seam's policy gate; publish it
as a skill manifest.

```
pip install -e servers/ic-workflows
IC_FLOOR_SERVICE=http://127.0.0.1:8766 ic-workflows   # -> :8610 (API only)
```
Open the console (`ic-console`, :8600) → Workflows tab.

## The loop

1. **Compose** — workflow palette from `/api/tools`; args take
   literals, `${params.name}`, or `${steps.N.field}` (backward refs only).
2. **Save** — validated spec → `workflows/<name>.yaml` (git-versioned;
   operator actions like `reset` are refused at save time, not just at run time).
3. **Dry-run** — resolves every template, touches nothing.
4. **Run** — each step is one seam call under a per-run mission id
   (`wf-<name>-<hex>`), so the journal and console replay cover workflow runs
   for free. Gated steps stop the run unless serial dispatch is
   physics-`verified`, parallel dispatch is both physics-`verified` and
   `independent_b1_verified`, or a predicate returns `yes` with complete
   evidence. Physical dispatch is never retried automatically. Read-only VLM
   predicate steps may use their explicitly bounded retry count.
   Any parallel step fails before contacting the Seam unless both
   `IC_GROOT_PARALLEL_ENABLED=1` and `IC_GROOT_FLEXIBLE_ORDER=1`. Enable them
   only after the documented two-server B=1 readiness checks. Same-color pairs
   are rejected. The Seam admits only the next qualified Order744 pair from
   authoritative state: left blue/right green, left green/right red, then left
   red/right blue. The serial workflow remains the default.
5. **Publish** — writes `skills/wf-<name>/manifest.yaml` in the conformance
   kit's shape (`ic-conformance skill --manifest ...` passes; enforced by a test).

## NL assistant (author from plain words)

`POST /api/assist {kind: "workflow"|"skill", instruction}` drafts an artifact
from natural language using the configured model backend (same one ic-chat
uses — set `IC_CHAT_BACKEND`/`IC_CHAT_MODEL_URL`). The draft is **validated
against the real schema before it is returned** (retrying with the validation
error fed back to the model), so nothing unschema'd reaches you or the store.
It never writes — you review the draft in the console's Assistant box and save
via the normal PUT/publish (which re-validate). CSRF-guarded like the rest of
the write path.

New PRIMITIVE tools can't be authored (they need floor-engine code); new
COMPOSITE tools are made by drafting a workflow and publishing it as a skill.

## Deliberate limits (v1)

Linear steps + verify gates + retry ≤3 — no branches, no loops, no code.
A workflow must stay reviewable YAML. The policy gate remains the authority:
this service adds zero privileged paths.

## Config (env)

`IC_FLOOR_SERVICE` (seam), `IC_WORKFLOWS_DIR` (default `workflows/`),
`IC_SKILLS_DIR` (default `skills/`), `IC_WORKFLOWS_HOST/PORT` (default `:8610`),
`IC_WORKFLOWS_CORS` (default allows the console origin :8600),
`IC_GROOT_PARALLEL_ENABLED` (default `0`), and `IC_GROOT_FLEXIBLE_ORDER`
(default `0`).

## Tests

`pytest servers/ic-workflows/tests` runs the hardware-free scripted-Seam suite,
including the published-manifest-passes-the-conformance-kit bar.
