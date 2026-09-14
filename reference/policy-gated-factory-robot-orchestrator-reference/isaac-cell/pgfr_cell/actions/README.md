# Cell action modules

At startup, the runtime discovers modules in this package except `base.py`,
`discovery.py`, and names beginning with `_`. Each discovered module exports a
non-empty `ACTION_HANDLERS` iterable whose handlers implement the shared action
contract from `base.py`.

## Current actions

| Module | Registered action names |
| --- | --- |
| `move.py` | `move` |
| `haul.py` | `pick_and_place`, `haul` |
| `scene.py` | `inspect`, `spawn`, `reset` |

`base.py` defines the handler protocol and validated registry. `discovery.py`
imports the action modules and fails cell startup when a module has no
handlers, a handler lacks `start()` or `step()`, an action name is malformed,
or two handlers register the same name.

## Add an action

Add one module to this package and export one or more handler instances:

```python
class PressButtonAction:
    action_names = ("press_button",)

    def start(self, runtime, command):
        ...

    def step(self, runtime, dt):
        ...


ACTION_HANDLERS = (PressButtonAction(),)
```

Action names must match lowercase `snake_case`. `start()` accepts the runtime
and decoded command; `step()` advances the action from the Isaac physics loop.
The runtime owns ROS transport, command deduplication, task lifecycle, and
result publication.

Run the registry validator after adding a module:

```bash
python reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/validate_actions.py
```
