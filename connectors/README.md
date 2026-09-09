# Connectors

Connectors provide typed, read-mostly access to external systems such as video
analytics, manufacturing execution systems, and quality databases. They return
context and evidence to an orchestrator; they do not dispatch robot actions.
Physical actions remain subject to PGFR Spine policy and verification.

## Available integrations

| Integration | Interface | Purpose |
|---|---|---|
| [Connector template](TEMPLATE/README.md) | [`pgfr-connector-sdk`](../packages/connector-sdk/README.md) | Starting point for a custom external-system adapter. |
| [NeMo Gym](nemo-gym/README.md) | NeMo Gym resource server | Exposes the reference cell as an environment for evaluation and rollout collection. |

The repository does not provide automatic connector discovery or a connector
runtime. A deployment must instantiate its connectors and expose the required
capabilities through its chosen service boundary.

## Connector contract

An SDK connector implements three methods:

- `health()` reports availability and data freshness.
- `capabilities()` returns named operations with JSON Schema parameter contracts.
- `call()` executes one capability and raises `KeyError` for an unknown name.

Connector results should include a source identifier and timestamp. Store
endpoints and credentials in the deployment environment, never in source files.

See the [connector template](TEMPLATE/README.md) for implementation and test
instructions.
