# Robot-cell reference implementation

This directory contains the working robot-cell example for Policy-Gated Factory Robot Orchestrator Reference.
It combines the repository's two primary software components with an Isaac Sim
warehouse cell and GR00T action execution.

| Component | Role |
|---|---|
| [IC Spine](../../ic-spine/) | Policy, perception, dispatch, verification, mission history, and evidence |
| [IC Console](../../ic-console/) | Topology, chat, inspection, missions, and telemetry UI |
| [Isaac Sim cell](isaac-cell/) | Two Franka arms, an AMR, cameras, conveyors, totes, rack, and deterministic reset |
| [GR00T integration](groot/) | Shared fine-tuned checkpoint, per-arm serving, relay, action execution, and training workflow |

## Demonstrated flow

An operator provides a goal in IC Chat or another connected agent harness.
The harness calls IC Spine tools to inspect the cell, dispatch three
mixed-color left/right pick-and-place pairs, verify both totes after each pair,
haul both totes with the AMR, and verify the rack.

The GR00T path loads one shared checkpoint in two policy processes, one per
arm. Each left/right pair executes concurrently inside the cell while IC Spine
keeps the broader floor operation ordered and auditable.

## Run the example

Follow [the reproducible demo guide](../../docs/REPRODUCIBLE-DEMO.md) for host
preparation, artifact access, Isaac cell installation, IC Spine and IC Console
startup, agent integration, and validation.

The component-specific material is organized here:

- [Isaac Sim cell](isaac-cell/) — packaged baseline and current deployment
  assets;
- [GR00T integration](groot/) — model metadata, capture context, relay,
  runtime, training, and validation; and
- [GR00T N1.7 IC pipeline](groot/groot_n1_7_ic_pipeline/) — the fine-tuning
  and execution workflow used by the example.
