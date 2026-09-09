# Packaged Isaac cell baseline

`ic_cell` is the modular scripted/RMPFlow baseline for the Policy-Gated Factory Robot Orchestrator Reference
Isaac cell. It owns cell bring-up, cameras, scene dressing, ROS transport, and
the action registry without depending on a learned policy.

## Bring-up

Copy this package, `ic_boot.py`, and the baseline `our_factory.usda` into the
Isaac scripts mount. Run the boot entry from Isaac Sim:

```python
exec(open("/scripts/ic_boot.py").read())
```

The default stage is `/scripts/our_factory.usda`; set `IC_STAGE` to select a
different absolute stage path. Successful bring-up emits:

```text
IC_CELL_UP markers=all
```

Re-running bring-up shuts down the previous package runtime and reloads the
stage when required for a clean camera and physics rebuild.

## Modules

| Path | Responsibility |
| --- | --- |
| `boot.py` | Runs stage, runtime, camera, dressing, simulation, and reset setup in order. |
| `runtime.py` | Owns the world, robots, controllers, ROS node, floor state, and FIFO task loop. |
| `cameras.py` | Builds wrist, outside, table, rack, and inspection camera publishers. |
| `dressing.py` | Adds tote pads and matte materials. |
| `actions/` | Discovers and validates action handlers used by the runtime. |

The action package is documented in
[`actions/README.md`](actions/README.md).

## Runtime boundary

This package is the scripted baseline used to validate the cell and action
contract. The GR00T deployment installs its learned-policy executor and
current three-object scene through the sibling
[`deployment/`](../deployment/) bundle.

Validate action discovery without Isaac Sim:

```bash
python reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/validate_actions.py
```
