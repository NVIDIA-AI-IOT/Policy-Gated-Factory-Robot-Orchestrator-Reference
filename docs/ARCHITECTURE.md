# Policy-Gated Factory Robot Orchestrator Reference architecture

This repository implements governed, closed-loop orchestration of a factory cell.
PGFR Spine separates agent reasoning
from floor execution so the agent harness, perception model, and robot action
backend can be changed without bypassing policy, verification, or audit.

## Primary components

### PGFR Spine

PGFR Spine is the control and assurance service. It owns:

- floor topology and endpoint discovery;
- action-policy validation;
- fresh-camera perception and visual verification;
- serial floor operations and bounded paired-arm execution;
- goal-correlated robot dispatch and results;
- mission journals and evidence frames; and
- health and signal-freshness reporting.

PGFR Spine can use a hardware-free mock backend or the ROS 2 backend used by the
Isaac Sim reference cell.

### PGFR Console

PGFR Console is the operator interface. Its panes expose topology, chat,
inspection, mission history, and host telemetry. It observes the same session
and journal identities used by PGFR Spine; it is not a second control plane.

### Agent interfaces

MCP-capable clients such as OpenClaw, Codex, Claude Code, and Hermes connect
through the MCP server. Its handshake distributes the operating playbook and
exposes nine governed tools:

1. `floor_state`
2. `perceive`
3. `reset_scene`
4. `dispatch_task`
5. `dispatch_parallel`
6. `certified_groot_sequence`
7. `verify`
8. `mission_history`
9. `mission_detail`

Traditional PGFR Chat uses the PGFR Spine HTTP API directly. When OpenClaw is
selected in PGFR Chat, OpenClaw owns the MCP tool loop and reaches PGFR Spine
through the MCP server. Both routes converge at the same policy, dispatch,
verification, and journal boundary.

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
OpenAI-compatible endpoint. PGFR Spine requests a fresh frame, applies the
configured region crop, records the exact VLM input, and returns structured
`yes`, `no`, or `unknown` evidence.

In `vision_only` mode, camera observations provide the model's perception
input. The executor and resulting floor state independently determine action
success; a model response or successful HTTP request does not prove that an
object moved.

## Reference deployment

The Console aggregation API is read-only; the browser sends operator commands through Chat. ROS 2 carries
floor commands and scene evidence. The separate GR00T bridge carries observations
and action chunks between the Isaac executor and Thor policy servers. AMR tote
transport uses scripted control.

The reference two-host arrangement places PGFR Spine, PGFR Console, the agent
services, the VLM, and both GR00T serving processes on the Jetson control host.
Isaac Sim and the robot executor run on the RTX simulation host. The GR00T
bridge exposes validated loopback forwards and derived readiness state to the
simulation host; policy servers remain bound to loopback.

Exact versions, ports, artifact identities, and service ownership are defined
in [`../deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml).

## Closed-loop mission flow

Given a goal such as “inspect the conveyor, sort the objects into the totes,
then shelve both totes,” the system follows this loop:

1. An agent interface receives the goal and its operating instructions.
2. `perceive` obtains fresh camera evidence for the relevant region.
3. The harness selects an endpoint and action.
4. PGFR Spine validates the request against the scene capabilities and policy.
5. The ROS backend publishes one goal-correlated command on `/pgfr/command`.
6. The cell executes the scripted or GR00T action and publishes progress.
7. The cell publishes the matching result on `/pgfr/result`; PGFR Spine rejects a
   timeout, mismatched goal, or unverified physical effect.
8. `verify` checks the resulting scene using a fresh camera frame and VLM.
9. Read-only perception or proof may be retried within its configured bound.
   A physical dispatch is not repeated automatically; an unresolved outcome is
   reconciled from authoritative state and reported to the operator.
10. Every operation, result, duration, mission identity, and VLM evidence frame
    is retained in the mission journal.

## ROS 2 boundary

The reference cell uses a small generic protocol:

- `/pgfr/command` — JSON command envelope;
- `/pgfr/result` — goal-correlated JSON outcome;
- `/pgfr/feedback` — progress for long-running actions;
- `/pgfr/floor_state` — current floor-state JSON; and
- `/<camera>/image_raw` — ROS image streams.

See [`floor-ros2-contract.md`](floor-ros2-contract.md) for the message contract.

## Source map

| Concern | Location |
|---|---|
| PGFR Spine service and floor backends | [`../pgfr-spine/`](../pgfr-spine/) |
| MCP tool surface | [`../servers/policy-gated-factory-robot-orchestrator-reference-mcp/`](../servers/policy-gated-factory-robot-orchestrator-reference-mcp/) |
| PGFR Chat | [`../servers/pgfr-chat/`](../servers/pgfr-chat/) |
| PGFR Console | [`../pgfr-console/`](../pgfr-console/) |
| OpenClaw integration | [`../plugins/openclaw/`](../plugins/openclaw/) |
| Isaac Sim reference cell | [`../reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/`](../reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/) |
| GR00T action execution | [`../reference/policy-gated-factory-robot-orchestrator-reference/groot/`](../reference/policy-gated-factory-robot-orchestrator-reference/groot/) |
| Deployment manifest | [`../deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml) |
| Agent playbook | [`../skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/`](../skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/) |

## Failure behavior

- Policy rejection returns a structured refusal before dispatch.
- Missing ROS subscribers, stale signals, timeouts, and mismatched goal IDs fail
  closed.
- A robot result with `verified:false` is not reported as success.
- VLM `no` or `unknown` is not treated as visual confirmation.
- Read-only perception and proof retries are bounded. Physical dispatch is
  never retried automatically.
- The protocol defines a cancellation action, but the current ROS cell refuses
  mid-flight cancellation because it cannot safely preempt the active command.
  Sites must use their governed abort or emergency-stop mechanism.
