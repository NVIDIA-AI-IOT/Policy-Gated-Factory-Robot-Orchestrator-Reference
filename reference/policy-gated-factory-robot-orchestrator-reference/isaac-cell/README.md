# Isaac Sim cell

This directory contains the Isaac Sim side of Policy-Gated Factory Robot Orchestrator Reference: the scene,
robots, cameras, ROS 2 floor interface, and action implementations driven by IC
Spine.

## Supported paths

### Packaged scripted baseline

[`ic_cell/`](ic_cell/) is the modular scripted/RMPFlow baseline. Copy the
package, [`ic_boot.py`](ic_boot.py), and the baseline
[`our_factory.usda`](our_factory.usda) into the Isaac scripts mount, then run
`ic_boot.py` in Isaac Sim. It builds the runtime, cameras, and dressing,
registers the action modules, starts the simulation, and emits `IC_CELL_UP`.

Use this path to validate the cell and ROS action contract without a learned
policy. See [`ic_cell/README.md`](ic_cell/README.md).

### GR00T deployment

[`deployment/`](deployment/) contains the current two-arm, three-object cell
assets installed by [`ops/install-groot-cell.sh`](../../../ops/install-groot-cell.sh).
The scene presents a red cube, blue cylinder, and green brick to each arm. The
installer combines these generic Isaac assets with the GR00T runtime,
contracts, and capture context; do not manually merge them with the differing
baseline files at this directory's root.

See [`deployment/README.md`](deployment/README.md).

### Classic fallback

The original `startup.py` + `cmd.py` workflow remains available through these
root sources:

- `startup.py`
- `ic_node_v2.py`
- `gr00t_cams.py`
- `pub_cam.py`
- `pub_cam_extra.py`

It is the manual fallback for an existing cell and depends on the command-file
poller. For new scripted bring-up use `ic_cell/`; for the learned-policy demo
use the installer-owned `deployment/` path.

## Historical root scripts

The remaining 74 root-level files are retained development evidence from the
original cell iteration. They are not supported launchers and are not loaded
by the current package or GR00T installer. They remain in the repository until
a separately reviewed cleanup identifies their evidence and compatibility
requirements.

## Validation

Validate the packaged action registry without starting Isaac Sim:

```bash
python reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/validate_actions.py
```

The expected action names are `haul`, `inspect`, `move`, `pick_and_place`,
`reset`, and `spawn`.
