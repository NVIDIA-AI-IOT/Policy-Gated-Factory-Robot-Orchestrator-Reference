# Connectors

SDK connectors provide typed, read-mostly access to external systems such as video
analytics, manufacturing execution systems, and quality databases. They return
context and evidence to an orchestrator; they do not dispatch robot actions.
Physical actions remain subject to PGFR Spine policy and verification.

## Create a connector

Start with the [connector template](TEMPLATE/README.md), which uses
[`pgfr-connector-sdk`](../packages/connector-sdk/README.md).

Instantiate SDK connectors in the service that exposes their capabilities;
the repository provides no connector discovery or hosting process.

## Connector contract

An SDK connector implements three methods:

- `health()` reports availability and data freshness.
- `capabilities()` returns named operations with JSON Schema parameter contracts.
- `call()` executes one capability and raises `KeyError` for an unknown name.

Connector results should include a source identifier and timestamp. Store
endpoints and credentials in the deployment environment, never in source files.
