# Industrial Claw architecture

Industrial Claw is a reference architecture and implementation for governed,
closed-loop orchestration of a factory cell. IC Spine separates agent reasoning
from floor execution so the agent harness, perception model, and robot action
backend can be changed without bypassing policy, verification, or audit.

## Primary components

### IC Spine

IC Spine is the control and assurance service. It owns:

- floor topology and endpoint discovery;
- action-policy validation;
- fresh-camera perception and visual verification;
- serial floor operations and bounded paired-arm execution;
- goal-correlated robot dispatch and results;
- mission journals and evidence frames; and
- health and signal-freshness reporting.

IC Spine can use a hardware-free mock backend or the ROS 2 backend used by the
Isaac Sim reference cell.

### IC Console

IC Console is the operator interface. Its panes expose topology, chat,
inspection, mission history, and host telemetry. It observes the same session
and journal identities used by IC Spine; it is not a second control plane.

### Agent harnesses and IC Chat

OpenClaw, Codex, Claude Code, Hermes, IC Chat, and other compatible harnesses
connect through the same MCP server. The MCP handshake distributes the
Industrial Claw operating playbook and exposes nine governed tools:

1. `floor_state`
2. `perceive`
3. `reset_scene`
4. `dispatch_task`
5. `dispatch_parallel`
6. `certified_groot_sequence`
7. `verify`
8. `mission_history`
9. `mission_detail`

Harnesses propose and sequence work. IC Spine remains responsible for whether
an action is allowed, dispatched, verified, and journaled.

### Isaac Sim reference cell

The reference cell contains two Franka arms, an AMR, a conveyor, two totes, a
rack, and multiple camera views. Its ROS node accepts goal-correlated JSON
commands, advances the appropriate state machine during simulation steps, and
publishes progress, results, floor state, and camera frames.

The cell provides two action-execution paths:

- a scripted/RMPFlow baseline for cell and contract validation; and
- a learned-motion path using one fine-tuned GR00T checkpoint loaded by two
  policy-server processes, one for each arm.

The two GR00T serving processes load the same model. A paired dispatch queries
both processes and applies the validated left and right action streams in one
cell transaction. Pairs are sequenced because each completed placement changes
the next observation.

### Perception and verification

Camera frames are published by the cell and selected by logical region. The
reference deployment serves NVIDIA Nemotron Nano 12B VL through an
OpenAI-compatible endpoint. IC Spine requests a fresh frame, applies the
configured region crop, records the exact VLM input, and returns structured
`yes`, `no`, or `unknown` evidence.

The agent reasons from camera perception in `vision_only` mode. Action success
is independently checked by the executor and resulting floor state, so a model
response or normal command return is not by itself proof that an object moved.

## Reference deployment

```text
Operator browser
      |
      v
IC Console and selected agent harness
      |
      | MCP tools and playbook
      v
IC Spine -----> perception VLM
      |
      | ROS 2 command/result/state/camera contract
      v
Isaac Sim cell -----> GR00T policy/relay pair per arm
```

The reference two-host arrangement places IC Spine, IC Console, the harness,
the VLM, and both GR00T serving processes on the brain host. Isaac Sim and the
robot executor run on the simulation host. The GR00T bridge exposes validated
loopback forwards and derived readiness state to the simulation host; it does
not make policy servers network-facing.

Exact versions, ports, artifact identities, and service ownership are defined
in [`../deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml).

## Closed-loop mission flow

Given a goal such as “inspect the conveyor, sort the objects into the totes,
then shelve both totes,” the system follows this loop:

1. The harness receives the goal and the MCP operating playbook.
2. `perceive` obtains fresh camera evidence for the relevant region.
3. The harness selects an endpoint and action.
4. IC Spine validates the request against the scene capabilities and policy.
5. The ROS backend publishes one goal-correlated command on `/ic/command`.
6. The cell executes the scripted or GR00T action and publishes progress.
7. The cell publishes the matching result on `/ic/result`; IC Spine rejects a
   timeout, mismatched goal, or unverified physical effect.
8. `verify` checks the resulting scene using a fresh camera frame and VLM.
9. The harness continues, retries within its bounded playbook, or reports the
   unresolved condition.
10. Every operation, result, duration, mission identity, and VLM evidence frame
    is retained in the mission journal.

## ROS 2 boundary

The reference cell uses a small generic protocol:

- `/ic/command` — JSON command envelope;
- `/ic/result` — goal-correlated JSON outcome;
- `/ic/feedback` — progress for long-running actions;
- `/ic/floor_state` — current floor-state JSON; and
- `/<camera>/image_raw` — ROS image streams.

See [`floor-ros2-contract.md`](floor-ros2-contract.md) for the message contract.

## Source map

| Concern | Location |
|---|---|
| IC Spine service and floor backends | [`../ic-spine/`](../ic-spine/) |
| MCP tool surface | [`../servers/industrial-claw-mcp/`](../servers/industrial-claw-mcp/) |
| IC Chat | [`../servers/ic-chat/`](../servers/ic-chat/) |
| IC Console | [`../ic-console/`](../ic-console/) |
| OpenClaw integration | [`../plugins/openclaw/`](../plugins/openclaw/) |
| Isaac Sim reference cell | [`../reference/industrial-claw/isaac-cell/`](../reference/industrial-claw/isaac-cell/) |
| GR00T action execution | [`../reference/industrial-claw/groot/`](../reference/industrial-claw/groot/) |
| Deployment manifest | [`../deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml) |
| Agent playbook | [`../skills/industrial-claw-orchestrator/`](../skills/industrial-claw-orchestrator/) |

## Failure behavior

- Policy rejection returns a structured refusal before dispatch.
- Missing ROS subscribers, stale signals, timeouts, and mismatched goal IDs fail
  closed.
- A robot result with `verified:false` is not reported as success.
- VLM `no` or `unknown` is not treated as visual confirmation.
- Retries are bounded by the operating playbook; unresolved work is surfaced to
  the operator.
- Cancellation is an explicit action and is not inferred from a new request.
