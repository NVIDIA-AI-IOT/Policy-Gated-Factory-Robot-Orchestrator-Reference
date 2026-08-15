# Integrating endpoints without changing the Spine

Industrial Claw has three independent endpoint boundaries. Keeping them
separate is what makes the repository modular.

## Robot and machine actions

For a device already connected to the ROS cell bridge, declare its actions in
the scene YAML. Core Python no longer needs a new hard-coded capability list:

```yaml
schema_version: 1
endpoints:
  - id: welder_1
    kind: welder
    location: station_2
    capabilities:
      - name: weld_seam
        description: Weld a named, approved seam.
        goal_schema:
          type: object
          required: [seam_id, recipe_id]
        result_schema:
          type: object
```

Advertisement does not grant authority. Add the action and required arguments
to a reviewed policy file (see
`ic-spine/configs/policy.example.yaml`) and point
`IC_FLOOR_POLICY` to it. The HTTP or MCP dispatch uses a generic `args` envelope:

```json
{"action":"weld_seam","endpoint":"welder_1","args":{"seam_id":"s-12","recipe_id":"r-4"}}
```

The Seam validates the policy, unwraps `args`, and sends the cell one generic
ROS command with flat device parameters. The cell-side endpoint implements the action and must return the normal
goal-correlated result. Add policy rules for privileged parameters, a mock test,
a ROS contract test, and a conformance fixture before calling the integration
supported. Raw HTTP and MCP accept this generic envelope. IC Chat's additional
physical-proof binding is intentionally limited to its certified warehouse
actions; add a verification binding before exposing a new physical action to
that model loop. Existing scene files that omit `capabilities` retain the legacy
arm/AMR defaults.

If the device does not speak the ROS cell protocol, write a transport adapter
behind `ActionEndpoint`; do not add a second Seam or bypass its policy and
journal.

For an action implemented inside the canonical Isaac cell, put the implementation
in a new module beneath `ic_cell/actions/` and export one or more handlers through
`ACTION_HANDLERS`. A handler implements only `start(runtime, command)` and
`step(runtime, dt)` and declares its command names in `action_names`. The cell
discovers and validates these modules at startup, so a contributor does not edit
the shared frame-loop dispatcher. Existing motion code may be called from the
handler while it is being migrated out of `runtime.py`.

Validate discovery without launching Isaac Sim:

```bash
cd reference/industrial-claw/isaac-cell
python validate_actions.py
```

This streamlines registration and protects existing actions; it does not generate
the device-specific Isaac controller. The contributor must still supply and test
that physical/simulated implementation.

## AI/model providers

- Camera verification uses `IC_VLM_URL` and `IC_VLM_MODEL` in `seam.env`.
- Traditional IC Chat uses `IC_CHAT_BACKEND`, `IC_CHAT_MODEL_URL`, and
  `IC_CHAT_MODEL` in `chat.env`.
- OpenClaw is a headless harness using the same MCP tools; its credentials stay
  in the untracked `~/.openclaw/secrets.env`.

An OpenAI-compatible local or hosted model normally needs configuration only.
A provider with a different wire protocol gets one adapter in IC Chat, with
contract tests; it must not change the floor tools.

## Agent harnesses

Harnesses connect through the nine MCP tools and receive the canonical
playbook during the MCP handshake. OpenClaw, Codex, Claude Code, Hermes, or a
future harness can therefore change without changing robot endpoints or the IC
Console. The Console always talks to IC Chat and the read-only status APIs; the
selected harness is session metadata, not a different frontend.
