# Isaac Sim cell

This directory contains the scenes, cameras, ROS 2 interface, and action
implementations for the reference factory cell. Two supported deployment paths
share the ROS contract but use separate Isaac Sim profiles and asset bundles.

## Deployment paths

| Path | Runtime | Purpose | Entry point |
|---|---|---|---|
| Scripted baseline | Isaac Sim 6.0.1 | Validate the scene, ROS 2 streams, reset, and scripted actions on one RTX workstation | [`ops/isaac-sim-workstation.sh`](../../../ops/isaac-sim-workstation.sh) |
| GR00T cell | Isaac Sim 6.0.0-dev2 compatibility profile | Run the learned two-arm action path with Jetson AGX Thor serving | [`ops/install-groot-cell.sh`](../../../ops/install-groot-cell.sh) |

### Scripted baseline

Run the supported launcher from the repository root:

```bash
ops/isaac-sim-workstation.sh --prepare
ops/isaac-sim-workstation.sh --check --accept-eula
ops/isaac-sim-workstation.sh --run --accept-eula
```

`--prepare` validates the packaged Python sources and atomically activates a
complete scripts mount containing [`pgfr_cell/`](pgfr_cell/),
[`pgfr_boot.py`](pgfr_boot.py), and [`our_factory.usda`](our_factory.usda). Do not
copy or replace individual files in an active mount. See the
[RTX workstation runbook](../../../ops/ISAAC-SIM-WORKSTATION.md) for container,
streaming, and acceptance instructions.

### GR00T cell

[`deployment/`](deployment/) contains the two-arm, three-object asset bundle.
The repository installer combines it with the GR00T runtime, generated
contracts, and capture context. The installer refuses to modify a scripts
mount used by a running container.

Follow the [two-host deployment guide](../../../docs/REPRODUCIBLE-DEMO.md) for
the complete install command and host-specific paths. Do not merge this bundle
with the scripted baseline files at the root of this directory.

## Source layout

| Path | Description |
|---|---|
| [`pgfr_cell/`](pgfr_cell/) | Modular scripted runtime, cameras, scene dressing, and action registry |
| [`deployment/`](deployment/) | Installer-owned GR00T scene and startup bundle |
| `startup.py`, `pgfr_node_v2.py`, `gr00t_cams.py`, `pub_cam*.py` | Original command-file fallback for an existing cell |

The other root-level scripts are retained as development evidence from the
original cell iteration. They are not loaded by the supported baseline launcher
or GR00T installer.

## Validate the action registry

This check does not require Isaac Sim:

```bash
python3 reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/validate_actions.py
```

The expected action names are `haul`, `inspect`, `move`, `pick_and_place`,
`reset`, and `spawn`.
