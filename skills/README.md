# Skills

Skills describe how an agent composes approved tools into a repeatable
procedure. Each skill includes human-readable instructions and a
`manifest.yaml` contract that names required tools, allowed floor actions, and
observable completion criteria.

## Included skills

| Skill | Purpose | Validation |
|---|---|---|
| [`policy-gated-factory-robot-orchestrator-reference-orchestrator`](policy-gated-factory-robot-orchestrator-reference-orchestrator/SKILL.md) | Sorts cubes, moves totes, and verifies the final scene through the governed floor tools. | Manifest included. |
| [`TEMPLATE`](TEMPLATE/SKILL.md) | Starting point for a custom procedure. | Replace all template fields before use. |

## Validate a manifest

Install the [conformance kit](../packages/conformance-kit/README.md), then run
from the repository root:

```bash
packages/conformance-kit/.venv/bin/pgfr-conformance skill \
  --manifest \
  skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/manifest.yaml
```

The validator checks required fields and restricts `allowed_actions` to the
current agent-action allowlist. It does not execute the procedure, evaluate
model behavior, or establish a physical success rate.

## Create a skill

1. Copy [`TEMPLATE`](TEMPLATE/) to `skills/<skill-name>/`.
2. Replace every placeholder in `manifest.yaml` and the instruction file.
3. Define exact tool parameters, stop conditions, failure handling, and
   evidence-based completion criteria.
4. Run the manifest validator.
5. Test the procedure in the intended deployment before granting motion
   authority.

Keep operator-only actions such as scene reset and emergency cancellation out
of `allowed_actions`. Tool policy remains enforced by PGFR Spine regardless of
the skill instructions.
