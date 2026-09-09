# Order744-cont24 validation

## Model

The Policy-Gated Factory Robot Orchestrator Reference demo uses one Order744-cont24 checkpoint for both Franka
arms. Order744 contains 744 episodes. The cont24 continuation adds 12
left-blue and 12 right-red accumulated-scene episodes, for 768 training
episodes in the continuation run.

The same final checkpoint is loaded by two policy processes. The model is not
split by arm, color, or shape.

## Integrated executor

The installed runtime restores the complete action executor after every
successful scene reset. Before each policy query it:

```text
commands the recorded task home for at least 120 physics ticks
requires all seven arm joints within 0.030 rad
requires 12 consecutive converged ticks
fails closed after 600 ticks without querying the policy
```

The same runtime enforces canonical Franka limits, bounded policy requery,
tracking, physical-friction grasp and release, settling, and floor-state
verification.

## Demonstrated sequence

The shared model completed this mixed-color two-arm order:

1. left blue with right green;
2. left green with right red; and
3. left red with right blue.

All six placements returned verified physical results. PGFR Chat then hauled the
two loaded totes to the rack and verified both tote contents and final rack
state.

## Validation scope

The result covers the Policy-Gated Factory Robot Orchestrator Reference Isaac Sim cell, the published fixed
three-object layout, the DROID relative-action embodiment, and the included
runtime contract. It is a simulation action-validation result, not a
functional-safety certification for physical equipment.
