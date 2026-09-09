# GR00T Isaac runtime

This directory contains the Isaac-side action runtime for the shared
Order744-cont24 GR00T checkpoint. It turns validated policy responses into
two-arm physical-friction motion, restores that behavior after every scene
reset, and exposes synchronized action telemetry when the cell uses the
capture camera profile.

Model weights and policy inference do not live here. The policy processes run
outside Isaac, and [`../relay/`](../relay/) provides the local serving bridge.

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

Reset validates each ready contract before admitting another action. A reset
therefore restores the complete executor instead of relying on callbacks left
behind by a previous mission.

## Files

| File | Responsibility | Runtime requirement |
| --- | --- | --- |
| [`cell/reset_two_arm.py`](cell/reset_two_arm.py) | Rebuilds the two-arm, three-object scene and restores the complete GR00T route. Cell startup and the PGFR reset endpoint both execute this source. | Required |
| [`native_droid_work/executors/follow_groot_home_convergence_v36.py`](native_droid_work/executors/follow_groot_home_convergence_v36.py) | Queries the relay and applies physical-friction tracking, grasp, release, settling, joint-boundary, and measured home-convergence behavior for one Franka context. | Required |
| [`native_droid_work/follow_groot_dual_physical_v36.py`](native_droid_work/follow_groot_dual_physical_v36.py) | Loads the executor into isolated left and right Franka contexts, binds each arm's cameras and controllers, and routes callbacks by endpoint. | Required |
| [`native_droid_work/pgfr_groot_certified_deployment_v36.py`](native_droid_work/pgfr_groot_certified_deployment_v36.py) | Validates checkpoint and relay service-state identity, scene, cameras, language/object mapping, and action contracts before motion. | Required |
| [`native_droid_work/pgfr_groot_dual_concurrent_mixed.py`](native_droid_work/pgfr_groot_dual_concurrent_mixed.py) | Runs independent per-arm policy requests, validates arm and seed identity, and joins mixed-color left/right results into one paired cell transaction. | Required by the current two-arm demo |
| [`native_droid_work/pgfr_sync_capture_cell.py`](native_droid_work/pgfr_sync_capture_cell.py) | Publishes passive synchronized measured-state and applied-action telemetry for data capture without creating cameras or issuing actions. | Required by the capture profile; inactive in the production profile |

All six sources are part of the supported runtime. The telemetry observer is
profile-conditional, not unused: capture-profile reset installs and verifies
it, while production-profile reset verifies that it is absent.

## Installation and reset lifecycle

[`ops/install-groot-cell.sh`](../../../../ops/install-groot-cell.sh) copies
these sources into an idle Isaac scripts mount together with the generic cell
deployment assets from [`../../isaac-cell/deployment/`](../../isaac-cell/deployment/),
the distilled home states from [`../capture_context/`](../capture_context/),
and the generated policy contracts. Installed paths under `/scripts` are part
of the runtime contract because the reset and loader sources resolve each
other there.

[`ops/launch-groot-isaac.sh`](../../../../ops/launch-groot-isaac.sh) starts the
configured shared-model cell and exposes the two host service-state manifests
inside the container at `/groot-state`. Both startup and later `reset_scene`
operations execute the installed reset source, which reloads the dual-arm
executor, deployment validation, mixed-color concurrency, and
profile-appropriate telemetry before reporting readiness.

The following components remain separate from this directory:

- model and dataset metadata: [`../models/`](../models/);
- policy-server bridge: [`../relay/`](../relay/);
- generated serial and concurrent contracts:
  [`ops/render-groot-cont24-contracts.py`](../../../../ops/render-groot-cont24-contracts.py);
- generic Isaac scene and camera deployment:
  [`../../isaac-cell/deployment/`](../../isaac-cell/deployment/).

## Validation

The hardware-free contract suites compile and inspect the installed source
contracts without launching Isaac:

```bash
python -m pytest -p no:cacheprovider \
  reference/policy-gated-factory-robot-orchestrator-reference/groot/tests/test_cont24_v36_runtime.py
python -m pytest -p no:cacheprovider \
  pgfr-spine/tests/unit/test_groot_runtime_contracts.py
bash -n ops/install-groot-cell.sh
bash -n ops/launch-groot-isaac.sh
```

Renaming or removing a runtime source requires coordinated updates to the
installer, installed `/scripts` paths, reset load sequence, and both contract
suites.
