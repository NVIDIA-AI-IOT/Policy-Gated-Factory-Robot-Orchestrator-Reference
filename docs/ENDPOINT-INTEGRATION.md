# Integrate robots, models, and agent clients

The project provides three independent extension points. Robot actions connect
behind PGFR Spine, model providers connect through the perception or Chat
adapters, and agent clients connect through MCP. Policy, physical
verification, and journaling remain in PGFR Spine.

## Add a ROS 2 robot or machine action

For a device connected to the cell's ROS 2 protocol, declare the action in the
scene configuration:

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

Capability advertisement does not grant authority. Add the action and its
required arguments to a reviewed policy file based on
[`pgfr-spine/configs/policy.example.yaml`](../pgfr-spine/configs/policy.example.yaml),
then set `PGFR_FLOOR_POLICY` to that file.

HTTP and MCP dispatches carry device-specific fields in the generic `args`
object:

```json
{
  "action": "weld_seam",
  "endpoint": "welder_1",
  "args": {
    "seam_id": "s-12",
    "recipe_id": "r-4"
  }
}
```

PGFR Spine validates policy, forwards the command through ROS 2, and waits for a
goal-correlated result. The cell-side endpoint must implement the action and
return the standard result envelope. Add:

- policy tests for permitted and refused parameters;
- a hardware-free backend test;
- a ROS 2 protocol contract test;
- a conformance fixture; and
- a visual or authoritative-state verification binding before exposing a new
  physical action to PGFR Chat.

Existing scene files without a `capabilities` field retain the legacy arm and
AMR defaults.

### Add an Isaac Sim action handler

Place a new handler below
[`pgfr_cell/actions/`](../reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/pgfr_cell/actions/)
and export it through `ACTION_HANDLERS`. A handler:

- declares its command names in `action_names`;
- implements `start(runtime, command)`; and
- implements `step(runtime, dt)`.

The cell discovers and validates action modules during startup. Validate the
registry without launching Isaac Sim:

```bash
python3 reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/validate_actions.py
```

Registry validation does not create or test the device-specific controller.
Provide simulation or hardware tests for the implementation.

### Add a non-ROS transport

Implement the transport behind PGFR Spine's `ActionEndpoint` boundary. Do not
add a second policy service or allow the adapter to bypass PGFR Spine policy,
verification, or journaling.

## Configure a model provider

The model extension points are:

| Service | Configuration |
|---|---|
| Camera perception and verification | `PGFR_VLM_URL` and `PGFR_VLM_MODEL` in `seam.env` |
| Traditional PGFR Chat | `PGFR_CHAT_BACKEND`, `PGFR_CHAT_MODEL_URL`, and `PGFR_CHAT_MODEL` in `chat.env` |
| OpenClaw | Provider settings in the generated OpenClaw configuration; secrets in `~/.openclaw/secrets.env` |

An OpenAI-compatible local or hosted service usually requires configuration
only. Add a tested PGFR Chat adapter when a provider uses another wire protocol.
Do not change the floor tool contract to accommodate a model provider.

See [Configure model providers](MODEL-PROVIDERS.md) for the supported endpoint
and credential procedure.

## Connect an agent client

OpenClaw and other MCP-capable clients connect through the nine tools exposed
by the [PGFR floor MCP server](../servers/policy-gated-factory-robot-orchestrator-reference-mcp/).
The server supplies the operating playbook during the MCP handshake.

An agent client can change without changing the robot endpoints or Console.
PGFR Console uses the Chat and Workflows services for interactive operations and
its aggregation API for read-only status. The selected agent runtime is
conversation metadata, not a separate user interface.

Run the [MCP conformance check](../packages/conformance-kit/README.md#check-an-mcp-server)
after changing the server, tool descriptions, annotations, or handshake
instructions.
