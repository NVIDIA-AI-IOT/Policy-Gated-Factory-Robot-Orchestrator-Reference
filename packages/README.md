# Packages

Industrial Claw ships two reusable Python packages:

- [`conformance-kit/`](conformance-kit/) checks an IC Spine floor endpoint,
  MCP server, or skill manifest against the public contracts.
- [`connector-sdk/`](connector-sdk/) defines the small interface and compliance
  check used by optional enterprise-system connectors.

The main IC Spine and IC Console applications remain top-level components, not
packages hidden in this directory.
