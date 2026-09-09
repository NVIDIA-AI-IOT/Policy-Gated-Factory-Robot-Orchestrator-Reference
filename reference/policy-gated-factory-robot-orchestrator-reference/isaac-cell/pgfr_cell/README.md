# Scripted Isaac cell package

`pgfr_cell` is the modular scripted and RMPFlow runtime for the standalone Isaac
Sim baseline. It owns scene startup, cameras, visual dressing, ROS 2 transport,
the FIFO task loop, and action registration. It does not load a learned policy.

## Install and run

Use the workstation launcher from the repository root:

```bash
ops/isaac-sim-workstation.sh --prepare
ops/isaac-sim-workstation.sh --check --accept-eula
ops/isaac-sim-workstation.sh --run --accept-eula
```

The prepare step validates and atomically installs this package together with
`pgfr_boot.py` and `our_factory.usda`. The launcher mounts that complete bundle at
`/scripts` and starts the boot entry. Successful startup emits:

```text
PGFR_CELL_UP markers=all
```

Set `PGFR_STAGE` only when developing against a different absolute stage path.
Re-running the boot entry shuts down the previous package runtime before it
rebuilds cameras and physics state.

## Package layout

| Path | Responsibility |
|---|---|
| `boot.py` | Runs stage, runtime, camera, dressing, simulation, and reset setup in order |
| `runtime.py` | Owns the world, robots, controllers, ROS node, floor state, and FIFO task loop |
| `cameras.py` | Builds wrist, outside, table, rack, and inspection camera publishers |
| `dressing.py` | Adds tote pads and matte materials |
| `actions/` | Discovers and validates action handlers used by the runtime |

See [`actions/README.md`](actions/README.md) for the action interface. The
sibling [`deployment/`](../deployment/) bundle is the separate GR00T cell and
must not be merged into this scripts mount.

## Validate without Isaac Sim

```bash
python3 reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/validate_actions.py
```

For the complete container and streaming procedure, see the
[RTX workstation runbook](../../../../ops/ISAAC-SIM-WORKSTATION.md).
