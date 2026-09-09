# Isaac cell deployment

This directory is the installer-owned Isaac asset bundle for the current
two-arm, three-object Policy-Gated Factory Robot Orchestrator Reference cell. It is not a second standalone cell
package. [`ops/install-groot-cell.sh`](../../../../ops/install-groot-cell.sh)
copies these files into the selected Isaac scripts mount together with the
GR00T runtime and capture context.

The installed scene presents a red cube, blue cylinder, and green brick in
front of each Franka arm. Installed filenames and `/scripts` destinations are
part of the runtime contract.

## Bring-up flow

`startup.py` opens `our_factory.usda`, runs `full_scene_bootstrap.py`, and then
starts the command-slot poller. The bootstrap prepares the right-hand workcell,
ROS floor node, object layout, camera publishers, visual dressing, and health
checks before reporting the cell ready. GR00T reset and action execution are
installed separately by the same installer.

## Files

| File | Responsibility |
| --- | --- |
| `startup.py` | Opens the scene, runs full-cell bootstrap, and starts the command poller. |
| `cmd.py` | Mutable command slot watched by the running Isaac session. |
| `our_factory.usda` | Current two-arm cell scene. |
| `full_scene_bootstrap.py` | Coordinates the complete scene setup and readiness gates. |
| `setup_right_cell.py` | Adds and validates the mirrored right Franka workcell. |
| `pgfr_node_v2.py` | Provides the ROS command, result, floor-state, and reset bridge. |
| `pgfr_cams_rp.py` | Builds camera render products and validates camera publication. |
| `pgfr_shape_mode.py` | Defines the red cube, blue cylinder, green brick, and supported layouts. |
| `production_contract_expected.json` | Records the expected scene and camera calibration contract. |
| `add_tote_colors.py` | Adds the colored tote compartment pads. |
| `matte_scene.py` | Applies the matte scene treatment used by perception. |
| `fix_amr_haul_joint.py` | Implements the AMR tote-haul and recovery behavior. |
| `pgfr_serving_health.py` | Publishes runtime health and readiness state. |

## Installation

Use the repository installer rather than copying individual files:

```bash
ops/install-groot-cell.sh --help
```

The installer refuses an active simulator, stages portable contracts, and
preserves the expected installed filenames. The differing root-level baseline
files in the parent directory are not overwritten or merged in Git.
