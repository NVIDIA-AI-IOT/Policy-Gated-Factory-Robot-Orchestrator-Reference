# Connector template

This template implements the minimal `pgfr-connector-sdk` interface for an
external data system. It is intended for read-mostly context and evidence. It
does not provide a path around PGFR Spine for dispatching robot actions.

## Requirements

- Python 3.10 or later
- The repository checkout, which supplies `pgfr-connector-sdk` through the local
  package reference in `pyproject.toml`

## Create a connector

1. Copy this directory to `connectors/<system-name>/`.
2. Rename the `my-connector` project and `src/my_connector` package in
   `pyproject.toml`.
3. Implement the `Connector` methods in `src/my_connector/connector.py`:

   - `health()` returns a mapping with an `ok` Boolean and useful freshness
     information.
   - `capabilities()` returns at least one `CapabilitySpec` with an object JSON
     Schema.
   - `call()` returns provenance-bearing results and raises `KeyError` for an
     unknown capability.

4. Read endpoints and credentials from the environment or a deployment secret
   store. Do not commit credentials.
5. Add domain-specific tests in addition to the SDK compliance check.

## Install and test

From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ../../packages/connector-sdk
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest
```

The included test calls `assert_connector_compliant(MyConnector())` and checks
that a successful result carries `source` and `ts` fields.

## Limitations

`assert_connector_compliant` checks the connector shape, health response,
capability schemas, and unknown-capability behavior. It does not verify an
external system, authenticate requests, evaluate data quality, or confirm that
all successful results contain provenance. Cover those requirements in the
connector's own integration tests.

The repository does not include a connector registry or hosting process. Add
the connector explicitly to the service that will expose its capabilities.
