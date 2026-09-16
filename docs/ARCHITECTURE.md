# Policy-Gated Factory Robot Orchestrator Reference architecture

PGFR Spine sits between agent clients and the Isaac Sim cell. It checks action
policy, dispatches robot commands, verifies results, and records them. Agent
clients, model providers, and robot controllers connect through these interfaces.

## Primary components

### PGFR Spine

PGFR Spine provides:

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

PGFR Console displays Chat, topology, inspection, mission history, and GPU
telemetry. Its aggregation API is read-only; operator commands go through Chat.

### Agent interfaces

MCP clients connect through the floor MCP server. When run from this checkout,
the server includes the operating playbook in its handshake. It exposes nine
tools:

1. `floor_state`
2. `perceive`
3. `reset_scene`
4. `dispatch_task`
5. `dispatch_parallel`
6. `certified_groot_sequence`
7. `verify`
8. `mission_history`
9. `mission_detail`

The Default Chat backend calls PGFR Spine over HTTP. With the OpenClaw backend,
OpenClaw runs the tool loop through MCP. Both use PGFR Spine for floor actions.

### Isaac Sim reference cell

The reference cell contains two Franka arms, an AMR, a conveyor, two totes, a
rack, and multiple camera views. Its ROS node accepts goal-correlated JSON
commands, advances the appropriate state machine during simulation steps, and
publishes progress, results, floor state, and camera frames.

The cell provides two action-execution paths:

- a scripted/RMPFlow baseline for cell and contract validation; and
- a learned-motion path using one fine-tuned GR00T checkpoint loaded by two
  policy-server processes, one for each arm.

An enabled paired dispatch queries both policy processes and executes the
left and right action streams together. Each pair must finish and pass its
visual checks before the next pair starts.

### Perception and verification

Camera frames are published by the cell and selected by logical region. The
reference deployment serves NVIDIA Nemotron Nano 12B VL through an
OpenAI-compatible endpoint. PGFR Spine requests a fresh frame, applies the
region crop, and records the VLM input. `perceive` returns a scene observation;
`verify` answers a predicate with `yes`, `no`, or `unknown` and supporting text.

In `vision_only` mode, `perceive` omits symbolic object state. Dispatch still
checks the executor result and floor state independently of the VLM response.

## Reference deployment

ROS 2 carries floor commands and scene evidence. The GR00T bridge carries
observations and action chunks between the Isaac executor and Thor policy
servers. AMR tote transport uses scripted control.

The reference two-host arrangement places PGFR Spine, PGFR Console, the agent
services, the VLM, and both GR00T serving processes on the Jetson control host.
Isaac Sim and the robot executor run on the RTX simulation host. The GR00T
bridge uses SSH port forwarding and checks policy/relay readiness on the
simulation host. Policy servers remain bound to loopback.

Exact versions, ports, artifact identities, and service ownership are defined
in [`../deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml).

## Closed-loop mission flow

Given a goal such as “inspect the conveyor, sort the objects into the totes,
then shelve both totes,” the system follows this loop:

1. An agent interface receives the goal and its operating instructions.
2. `perceive` obtains fresh camera evidence for the relevant region.
3. The agent selects an endpoint and action.
4. PGFR Spine validates the request against the scene capabilities and policy.
5. The ROS backend publishes one goal-correlated command on `/pgfr/command`.
6. The cell executes the scripted or GR00T action and publishes progress.
7. The cell publishes the result on `/pgfr/result`, echoing the command's
   `goal_id`. PGFR Spine reads the result and checks the physical effect.
8. `verify` checks the destination using a fresh camera frame and VLM.
9. The mission journal records the calls, results, timing, and evidence frames.

## ROS 2 boundary

The reference cell uses a small generic protocol:

- `/pgfr/command` — JSON command envelope;
- `/pgfr/result` — goal-correlated JSON outcome;
- `/pgfr/feedback` — progress for long-running actions;
- `/pgfr/floor_state` — current floor-state JSON; and
- `/<camera>/image_raw` — ROS image streams.

See the [ROS 2 contract](floor-ros2-contract.md) for message formats and legacy
compatibility, and the [source map](../STRUCTURE.md) for component guides.

## Failure behavior

- Policy rejection returns a structured refusal before dispatch.
- Missing or stale ROS signals can block readiness or cause an unverified
  timeout. The transport does not automatically republish timed-out commands.
- A robot result with `verified:false` is not reported as success.
- VLM `no` or `unknown` is not treated as visual confirmation.
- Read-only perception and verification retries are bounded. An unverified
  dispatch requires state reconciliation before any further motion.
- The protocol defines a cancellation action, but the current ROS cell refuses
  mid-flight cancellation because it cannot safely preempt the active command.
  Use the deployment's operator-controlled stop procedure.
