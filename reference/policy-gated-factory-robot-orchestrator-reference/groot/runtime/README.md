# GR00T Isaac runtime

This directory contains the Isaac-side action runtime for a user-trained GR00T
checkpoint shared by both arms. It turns validated policy responses into
simulated arm motion, restores the executor after each scene reset, and
publishes synchronized action telemetry in the capture camera profile.
[Thor](../thor/README.md) runs the policy and relay processes.

## Load flow

```text
Isaac startup or reset_scene
  -> cell/reset_two_arm.py
     -> follow_groot_dual_physical_v36.py
        -> follow_groot_home_convergence_v36.py for the left arm
        -> follow_groot_home_convergence_v36.py for the right arm
     -> pgfr_groot_certified_deployment_v36.py
     -> pgfr_groot_dual_concurrent_mixed.py
     -> pgfr_sync_capture_cell.py when the capture profile is active
```

Reset validates each ready contract before admitting another action.

| File | Responsibility |
|---|---|
| [`cell/reset_two_arm.py`](cell/reset_two_arm.py) | Rebuilds the two-arm, three-object scene and restores the complete GR00T route at startup and reset. |
| [`follow_groot_home_convergence_v36.py`](native_droid_work/executors/follow_groot_home_convergence_v36.py) | Queries the relay and checks physical tracking, grasp, release, settling, joint boundaries, and measured home convergence for one arm. |
| [`follow_groot_dual_physical_v36.py`](native_droid_work/follow_groot_dual_physical_v36.py) | Loads isolated left/right contexts, binds cameras and controllers, and routes callbacks. |
| [`pgfr_groot_certified_deployment_v36.py`](native_droid_work/pgfr_groot_certified_deployment_v36.py) | Validates checkpoint/service identity, scene, cameras, language/object mapping, and action contracts before motion. |
| [`pgfr_groot_dual_concurrent_mixed.py`](native_droid_work/pgfr_groot_dual_concurrent_mixed.py) | Validates arm/seed identity and joins per-arm responses into one paired transaction. Paired execution is opt-in. |
| [`pgfr_sync_capture_cell.py`](native_droid_work/pgfr_sync_capture_cell.py) | Publishes passive measured-state and applied-action telemetry without creating cameras or issuing actions. |

All six sources belong to the supported runtime. Capture-profile reset installs
and verifies the telemetry observer; production-profile reset verifies its absence.

## Installation and reset lifecycle

[`ops/install-groot-cell.sh`](../../../../ops/install-groot-cell.sh) installs
these sources, the [Isaac deployment bundle](../../isaac-cell/README.md#gr00t-cell),
[capture context](#capture-context), and generated policy contracts into an idle
scripts mount. Installed `/scripts` paths are part of the contract because the
reset and loader sources resolve each other there.

[`ops/launch-groot-isaac.sh`](../../../../ops/launch-groot-isaac.sh) exposes the
two host service-state manifests at `/groot-state`. Startup and `reset_scene`
reload and validate the executor before reporting readiness. Follow the
[two-host guide](../../../../docs/REPRODUCIBLE-DEMO.md) for the complete sequence,
[model guide](../models/README.md) for checkpoint identity, and
[contract renderer](../../../../ops/render-groot-cont24-contracts.py) for serial
and concurrent configuration.

## Serving relay

Each arm uses one policy process and one
[`native_droid_relay_batch2.py`](../relay/native_droid_relay_batch2.py) process.
The relay provides the bounded, versioned native-DROID single-frame observation
and action protocol. With `PGFR_SERVICE_STATE_PATH` configured, it atomically
publishes model, checkpoint, fingerprint, policy/relay endpoints, and protocol
identity. The Isaac executor validates this record before dispatch.

Policy and relay listeners must remain on loopback: the executor-facing wire
format uses length-prefixed Python pickle and must not face an untrusted
network. Use the repository's installed service profiles.
[`native_droid_relay_single_frame.py`](../relay/native_droid_relay_single_frame.py)
is retained for earlier specialist profiles and is not used by the current
shared-checkpoint deployment.

## Capture context

The 18 JSON files under [`capture_context/`](../capture_context/) retain the
first recorded DROID joint state for supported arm, color, and layout
combinations:

```text
<left|right>/<red|blue|green>/layout_<id>/ep_000/states.json
```

The installer copies them to `/scripts/groot_capture_context`. The direct
executor selects the matching file and rejects missing or malformed state.
The primary two-arm profile uses layout 3; other entries retain additional
supported layout alignments.

These are deployment alignment inputs. They contain no demonstration images,
full trajectories, or policy actions. Use the
[dataset guide](../groot_n1_7_pgfr_pipeline/docs/DATASET_CREATION.md) for training
data. A changed robot, camera, object layout, or capture protocol requires a
measured replacement and runtime validation; do not hand-edit the recorded
state to accommodate it.

## Validation

Run from the repository root in an environment with `pytest` and NumPy:

```bash
python -m pytest -p no:cacheprovider \
  reference/policy-gated-factory-robot-orchestrator-reference/groot/tests/test_two_host_bridge.py \
  reference/policy-gated-factory-robot-orchestrator-reference/groot/tests/test_cont24_v36_runtime.py \
  reference/policy-gated-factory-robot-orchestrator-reference/groot/tests/test_native_droid_relay_batch2.py \
  pgfr-spine/tests/unit/test_groot_runtime_contracts.py
bash -n ops/install-groot-cell.sh
bash -n ops/launch-groot-isaac.sh
```

| Suite | Coverage |
|---|---|
| [`test_two_host_bridge.py`](../tests/test_two_host_bridge.py) | SSH forwards, endpoint rewriting, model/service identity, paired state invalidation, port collisions, and idle-only installation. |
| [`test_cont24_v36_runtime.py`](../tests/test_cont24_v36_runtime.py) | Runtime compilation, home and mixed-color contracts, reset restoration, rendering, ports, and installer/launcher guards. |
| [`test_native_droid_relay_batch2.py`](../tests/test_native_droid_relay_batch2.py) | Framing, arm/seed identity, paired inference, fallback, and service state; uses the test-only [paired transport fixture](../tests/fixtures/pgfr_groot_pair_transport.py). |
| [`test_groot_runtime_contracts.py`](../../../../pgfr-spine/tests/unit/test_groot_runtime_contracts.py) | Executor, haul, alignment, ordering, cargo, and camera-capture contracts. |

These checks use source inspection and ephemeral loopback sockets without
installing services, launching Isaac, contacting a policy server, or moving an
arm. Renaming a runtime source requires coordinated installer, `/scripts` load
path, reset, and contract-test updates.
