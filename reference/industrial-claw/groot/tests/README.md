# GR00T tests

These hardware-free tests validate the public GR00T action runtime and serving
bridge without launching Isaac Sim or a policy server.

## Test suites

| File | Coverage |
| --- | --- |
| [`test_two_host_bridge.py`](test_two_host_bridge.py) | Loopback-only SSH forwards, exact remote model/service identity, local endpoint rewriting, paired state publication/invalidation, port-collision refusal, and idle-only unit installation. |
| [`test_cont24_v36_runtime.py`](test_cont24_v36_runtime.py) | Direct runtime compilation, measured-home and mixed-color contracts, scene-reset restoration, contract rendering, configurable ports, and fail-closed installer/launcher behavior. |
| [`test_native_droid_relay_batch2.py`](test_native_droid_relay_batch2.py) | Batch-two relay framing, arm and seed identity, paired inference, fallback behavior, and service-state reporting. |
| [`fixtures/ic_groot_pair_transport.py`](fixtures/ic_groot_pair_transport.py) | Test-only paired-transport client and response validation used by the relay suite. |
| [`../../../../ic-spine/tests/unit/test_groot_runtime_contracts.py`](../../../../ic-spine/tests/unit/test_groot_runtime_contracts.py) | Semantic executor, haul, alignment, target-ordering, cargo, and camera-capture contracts spanning GR00T and the Isaac cell. |

## Run

Use a Python environment containing `pytest`; the relay suite also requires
NumPy:

```bash
python -m pytest -p no:cacheprovider \
  reference/industrial-claw/groot/tests/test_two_host_bridge.py

python -m pytest -p no:cacheprovider \
  reference/industrial-claw/groot/tests/test_cont24_v36_runtime.py

python -m pytest -p no:cacheprovider \
  reference/industrial-claw/groot/tests/test_native_droid_relay_batch2.py

python -m pytest -p no:cacheprovider \
  ic-spine/tests/unit/test_groot_runtime_contracts.py
```

The socket exercised by the relay suite is an ephemeral loopback socket. The
tests do not install the runtime, start containers, contact a model endpoint,
or move either simulated arm.
