# Python packages

The repository includes two reusable Python packages:

| Package | Python | Purpose |
|---|---:|---|
| [`pgfr-conformance`](conformance-kit/README.md) | 3.10+ | Runs black-box checks against a PGFR Spine HTTP endpoint, MCP server, or skill manifest. |
| [`pgfr-connector-sdk`](connector-sdk/README.md) | 3.10+ | Defines the interface and structural compliance check for external-system connectors. |

PGFR Spine and PGFR Console are applications and remain in their top-level
directories. Each package is installed independently; this repository does not
publish a combined Python distribution.
