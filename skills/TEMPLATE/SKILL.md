# Skill template

Use this template to define how an agent combines approved tools for one class
of goal. The instruction file describes the procedure; `manifest.yaml` defines
the required tools, allowed actions, and observable completion criteria.

Review the reference
[orchestration playbook](../policy-gated-factory-robot-orchestrator-reference-orchestrator/PLAYBOOK.md)
before creating a new skill.

## Create a skill

1. Copy this directory to `skills/<skill-name>/`.
2. Replace every placeholder in `manifest.yaml` and this file.
3. Define exact tool parameters, verification steps, stop conditions, and
   operator escalation behavior.
4. Validate the manifest:

   ```bash
   pgfr-conformance skill --manifest manifest.yaml
   ```

5. Test the procedure in its intended deployment.
6. Publish it through the selected MCP server or agent-runtime configuration.

## Required instruction content

- **Scope and vocabulary:** name every object, region, endpoint, and tool used
  by the procedure.
- **Execution sequence:** state when to observe, act, verify, stop, and request
  operator input.
- **Action parameters:** provide the complete parameter set and at least one
  valid example for each allowed action.
- **Failure handling:** distinguish read-only retries from physical actions and
  define when an uncertain result requires state reconciliation.
- **Completion criteria:** identify the authoritative state and evidence needed
  to report success.
- **Prohibited behavior:** list unsupported actions, unsupported assumptions, and
  conditions that require refusal.

Write the procedure so it can be followed using only this file and the exposed
tool contracts. A validated manifest checks structure; it does not establish
model quality or physical mission success.
