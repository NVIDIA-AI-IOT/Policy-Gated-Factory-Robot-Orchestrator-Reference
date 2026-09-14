---
name: policy-gated-factory-robot-orchestrator-reference-orchestrator
description: "Sort objects and transport totes through PGFR floor tools, checking each action result and its visual evidence."
metadata: { "openclaw": { "emoji": "🦾" } }
---

# Factory-cell orchestration

Use this skill for floor tasks such as sorting objects into totes, inspecting a
station, or moving totes to the rack. Read the [floor playbook](PLAYBOOK.md)
for endpoint names, action order, camera regions, and recovery rules.

## Procedure

1. Call `floor_state` to identify endpoints and check the scene state.
2. Use `perceive` to inspect the relevant regions. A whole-cell survey covers
   `conveyor_1`, `conveyor_2`, `table_1`, and `rack_1`. Use `tote` and `tote_r`
   for close views of the compartments.
3. Select the actions required by the goal. For the GR00T reference scene,
   follow the plan returned by `certified_groot_sequence` and the playbook's
   arm-selection rules.
4. Dispatch one action at a time and wait for its result. Do not call independent
   `dispatch_task` tools concurrently. An explicitly enabled `dispatch_parallel`
   pair is one transaction with separate verification for each arm.
5. Require `verified:true` and fresh visual evidence through `verify` before
   continuing. Inspect the returned reason and any pending proof requirements.
6. Check the requested final state before reporting completion.

## Unverified results

A response without `verified:true` leaves the physical outcome uncertain; the
robot may already have moved. Do not automatically retry, switch endpoints, or
assume that nothing changed.

Reconcile the result with fresh floor state and visual evidence. The guarded
MCP recovery path described in the playbook can allow one further move attempt
only after the exact object is proven to remain at its source. Otherwise stop
and report the unresolved outcome to the operator.

## Reporting

State which actions completed and what the tools verified. If a result remains
uncertain or the requested goal is incomplete, say what remains unresolved and
include the returned reason. Reset the scene only on an explicit operator request.
