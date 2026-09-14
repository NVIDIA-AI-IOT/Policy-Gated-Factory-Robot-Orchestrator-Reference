# Isaac Sim cell

This directory contains the scenes, cameras, ROS 2 interface, and action
implementations for the reference factory cell. The scripted baseline and
GR00T deployment share the ROS contract but use separate Isaac Sim
profiles and asset bundles. Both use NVIDIA's official image with mounted
project code; no project image is built or published.

See the [scene guide](../../docs/ISAAC-SIM-SCENE.md) for pictures and component
descriptions.

## Deployment paths

| Path | Runtime | Purpose | Entry point |
|---|---|---|---|
| Scripted baseline | Isaac Sim 6.0.1 | Validate the scene, ROS 2 streams, reset, and scripted actions on one RTX workstation | [`ops/isaac-sim-workstation.sh`](../../ops/isaac-sim-workstation.sh) |
| GR00T cell | Isaac Sim 6.0.0-dev2 compatibility profile | Run the learned two-arm action path with Jetson AGX Thor serving | [`ops/install-groot-cell.sh`](../../ops/install-groot-cell.sh) |

### Scripted baseline

Complete the [workstation host prerequisites](../../ops/ISAAC-SIM-WORKSTATION.md#host-prerequisites)
and review NVIDIA's [Isaac Sim Additional Software and Materials License](https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/).
Then pull NVIDIA's image and run the launcher from the repository root:

```bash
docker pull --platform linux/amd64 \
  nvcr.io/nvidia/isaac-sim:6.0.1@sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb
ops/isaac-sim-workstation.sh --prepare
ops/isaac-sim-workstation.sh --check --accept-eula
ops/isaac-sim-workstation.sh --run --accept-eula
```

`--prepare` validates the packaged Python sources and atomically activates a
complete scripts mount containing [`pgfr_cell/`](pgfr_cell/),
[`pgfr_boot.py`](pgfr_boot.py), and [`our_factory.usda`](our_factory.usda). Do not
copy or replace individual files in an active mount. See the
[RTX workstation runbook](../../ops/ISAAC-SIM-WORKSTATION.md) for container,
streaming, and acceptance instructions. The package uses scripted controllers
and RMPflow without loading a learned policy. Successful startup emits
`PGFR_CELL_UP markers=all`.

For development, `PGFR_STAGE` selects a different absolute stage path.
Re-running the boot entry shuts down the previous package runtime before
rebuilding cameras and physics state.

### GR00T cell

[`deployment/`](deployment/) contains the two-arm, three-object asset bundle.
The repository installer combines it with the GR00T runtime, generated
contracts, and capture context. The installer refuses to modify a scripts
mount used by a running container.

Follow the [two-host deployment guide](../../docs/REPRODUCIBLE-DEMO.md) for
the complete install command and host-specific paths. Its launcher requires
explicit `--accept-eula` before starting the pinned NVIDIA runtime. Learned
motion on Isaac Sim 6.0.1 is not qualified. Do not merge this bundle with the
scripted baseline files at the root of this directory.

The installed `startup.py` opens `our_factory.usda`, runs
`full_scene_bootstrap.py`, then starts the command-slot poller. Bootstrap prepares
the right workcell, ROS node, three-object layouts, camera publishers, visual
dressing, and health checks. The same installer supplies the
[GR00T reset and action runtime](../groot/runtime/README.md). Installed filenames
and `/scripts` destinations are part of the runtime contract.

## Source layout

| Path | Description |
|---|---|
| [`pgfr_cell/boot.py`](pgfr_cell/boot.py) | Orders stage, runtime, camera, dressing, simulation, and reset setup |
| [`pgfr_cell/runtime.py`](pgfr_cell/runtime.py) | Owns the world, robots, controllers, ROS node, floor state, and FIFO task loop |
| [`pgfr_cell/cameras.py`](pgfr_cell/cameras.py), [`dressing.py`](pgfr_cell/dressing.py) | Build baseline camera publishers, tote pads, and matte materials |
| [`pgfr_cell/actions/`](pgfr_cell/actions/README.md) | Action discovery, validation, and extension interface |
| [`deployment/startup.py`](deployment/startup.py), [`full_scene_bootstrap.py`](deployment/full_scene_bootstrap.py) | Open the deployed scene, coordinate setup/readiness, and start the command poller |
| [`deployment/our_factory.usda`](deployment/our_factory.usda), [`cmd.py`](deployment/cmd.py) | Learned scene composition and installed mutable command slot |
| [`deployment/setup_right_cell.py`](deployment/setup_right_cell.py), [`pgfr_shape_mode.py`](deployment/pgfr_shape_mode.py) | Set up the right workcell and red cube, blue cylinder, green brick layouts |
| [`deployment/pgfr_node_v2.py`](deployment/pgfr_node_v2.py), [`pgfr_serving_health.py`](deployment/pgfr_serving_health.py) | Publish ROS commands/results/floor state and serving health; handle reset |
| [`deployment/pgfr_cams_rp.py`](deployment/pgfr_cams_rp.py), [`production_contract_expected.json`](deployment/production_contract_expected.json) | Camera render products, publication, and calibration contract |
| [`deployment/add_tote_colors.py`](deployment/add_tote_colors.py), [`matte_scene.py`](deployment/matte_scene.py) | Tote compartment pads and visual dressing for perception |
| [`deployment/fix_amr_haul_joint.py`](deployment/fix_amr_haul_joint.py) | AMR tote-haul and recovery behavior |
| `startup.py`, `pgfr_node_v2.py`, `gr00t_cams.py`, `pub_cam*.py` | Original command-file fallback for an existing cell |

The baseline launcher and GR00T installer do not load the other root-level
scripts.

## Validate the action registry

This check does not require Isaac Sim:

```bash
python3 reference/isaac-cell/validate_actions.py
```

The expected action names are `haul`, `inspect`, `move`, `pick_and_place`,
`reset`, and `spawn`. See [the action interface](pgfr_cell/actions/README.md)
for handler requirements and an extension example.
