# PGFR connector SDK

`pgfr-connector-sdk` defines the Python interface for wrapping an external data
system as a typed, read-mostly connector.

## Install

From the repository root:

```bash
python3 -m venv packages/connector-sdk/.venv
packages/connector-sdk/.venv/bin/pip install -e packages/connector-sdk
```

Python 3.10 or later is required. The package has no runtime dependencies.

## Interface

| API | Requirement |
|---|---|
| `CapabilitySpec` | Names a capability and defines its object JSON Schema. Capabilities are read-only by default. |
| `Connector.health()` | Returns a mapping containing an `ok` Boolean. |
| `Connector.capabilities()` | Returns one or more documented `CapabilitySpec` values. |
| `Connector.call()` | Executes a named capability and raises `KeyError` for an unknown name. |
| `assert_connector_compliant()` | Checks the structural requirements above. |

Start from [`connectors/TEMPLATE`](../../connectors/TEMPLATE/README.md), which
contains an implementation and tests.

## Test a connector

Include the compliance assertion in the connector's test suite:

```python
from pgfr_connector_sdk import assert_connector_compliant

from my_connector.connector import MyConnector


def test_sdk_compliance():
    assert_connector_compliant(MyConnector())
```

The compliance assertion calls `health()`, `capabilities()`, and an unknown
capability; those methods may contact the wrapped system. It checks response
structure, not successful capability results or their provenance.

The SDK provides no transport, discovery, authentication, retries, secret
management, or hosting process. Implement and test those in the connector.
