# ic-workflows — build skills from tool verbs, in the browser

The write-path sibling of [`ic-console`](../ic-console/): the console's
**Workflows tab** talks to this service. Compose the certified MCP tool verbs
(`floor_state` · `perceive` · `dispatch_task` · `check_predicate`) into a
linear, gated, retryable workflow; save it as reviewable YAML; dry-run it;
run it through the seam's policy gate; publish it as a skill manifest.

```
pip install -e servers/ic-workflows
IC_FLOOR_SERVICE=http://127.0.0.1:8766 ic-workflows   # -> :8610 (API only)
```
Open the console (`ic-console`, :8600) → Workflows tab.

## The loop

1. **Compose** — palette from `/api/tools` (the MCP toolset); args take
   literals, `${params.name}`, or `${steps.N.field}` (backward refs only).
2. **Save** — validated spec → `workflows/<name>.yaml` (git-versioned;
   operator actions like `reset` are refused at save time, not just at run time).
3. **Dry-run** — resolves every template, touches nothing.
4. **Run** — each step is one seam call under a per-run mission id
   (`wf-<name>-<hex>`), so the journal and console replay cover workflow runs
   for free. Gated steps (dispatch: physics-`verified`; predicate: `yes`)
   stop the run after their bounded retries.
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
`IC_WORKFLOWS_CORS` (default allows the console origin :8600).

## Tests

`pytest servers/ic-workflows/tests` — 12 hardware-free tests (scripted seam),
including the published-manifest-passes-the-conformance-kit bar.
