# Robot-cell reference implementation

This directory contains the Isaac Sim robot cell and NVIDIA Isaac GR00T action
path used by Policy-Gated Factory Robot Orchestrator Reference. PGFR Spine remains
the policy and verification boundary for both scripted and learned actions.

## Components

| Component | Purpose |
|---|---|
| [Isaac Sim cell](isaac-cell/) | Two Franka arms, an AMR, cameras, conveyors, totes, a rack, and deterministic scene reset |
| [GR00T integration](groot/) | Model metadata, per-arm serving, relays, learned-action execution, and training material |
| [PGFR Spine](../../pgfr-spine/) | Policy checks, perception, dispatch, result verification, mission history, and evidence |
| [PGFR Console](../../pgfr-console/) | Operator views for topology, Chat, Workflows, inspection, missions, and telemetry |

## Reference workflow

The supported workflow begins from the default scene created by **Reset the
scene**. It inspects the work areas, moves the red cube, blue cylinder, and
green brick from each conveyor into the corresponding tote compartments, and
then moves both loaded totes to `rack_1`.

[`full-groot-dual-tote`](../../servers/pgfr-workflows/workflows/full-groot-dual-tote.yaml)
is the default acceptance workflow. It executes all six GR00T moves and both
tote transfers serially, with a fresh visual verification step after each
physical action. A failed physical action is not dispatched again
automatically; inspect authoritative state and evidence before deciding whether
another action is permitted.

An optional paired-action profile is available through
[`full-groot-dual-tote-concurrent`](../../servers/pgfr-workflows/workflows/full-groot-dual-tote-concurrent.yaml).
It denies dispatch unless `PGFR_GROOT_PARALLEL_ENABLED=1` and
`PGFR_GROOT_FLEXIBLE_ORDER=1` are both set and the independent two-server B=1
readiness checks pass. The only accepted pair order is:

1. left blue and right green;
2. left green and right red; and
3. left red and right blue.

The paired profile is an explicit qualification mode, not the default
workflow.

## Run the reference deployment

Start with the repository [installation guide](../../INSTALL.md). The complete
Jetson AGX Thor and RTX procedure, including pinned artifacts, host preparation,
service startup, ROS 2 validation, and mission acceptance, is in the
[two-host deployment guide](../../docs/REPRODUCIBLE-DEMO.md).

Component details are available in:

- [Isaac Sim cell](isaac-cell/)
- [GR00T action integration](groot/)
- [GR00T N1.7 training and execution pipeline](groot/groot_n1_7_pgfr_pipeline/)

The standalone Isaac Sim 6.0.1 scripted baseline and the two-host GR00T
deployment use different runtime profiles. Do not combine their assets or
container pins.
