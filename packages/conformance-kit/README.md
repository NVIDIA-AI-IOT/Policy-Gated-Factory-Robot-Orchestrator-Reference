# PGFR conformance kit

`pgfr-conformance` runs black-box contract checks against three integration
surfaces:

- a PGFR Spine HTTP endpoint;
- an MCP server launched over standard input/output; or
- a skill `manifest.yaml` file.

HTTP checks are read-only or use requests that policy must refuse. A successful
run exits with status `0`; any failed check exits with status `1`.

## Install

From the repository root:

```bash
python3.12 -m venv packages/conformance-kit/.venv
packages/conformance-kit/.venv/bin/pip install -e \
  'packages/conformance-kit[mcp]'
```

The `mcp` extra is required only for MCP server checks.

## Check PGFR Spine

Start PGFR Spine, then run:

```bash
packages/conformance-kit/.venv/bin/pgfr-conformance run \
  --target http://127.0.0.1:8766 \
  --target-region conveyor_1
```

The command checks health, OpenAPI publication, floor-state metadata, request
IDs, policy refusals, validation errors, and perception response shape.

## Check an MCP server

Pass the complete server launch command after `--command`:

```bash
packages/conformance-kit/.venv/bin/pgfr-conformance mcp \
  --command \
  "$PWD/servers/policy-gated-factory-robot-orchestrator-reference-mcp/.venv/bin/pgfr-mcp"
```

This check validates handshake instructions, tool availability, descriptions,
and MCP annotations.

## Check a skill manifest

```bash
packages/conformance-kit/.venv/bin/pgfr-conformance skill \
  --manifest \
  skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/manifest.yaml
```

Manifest validation requires the documented fields and rejects actions outside
the current agent-action allowlist: `move`, `pick_and_place`, `inspect`, and
`navigate_to`.

Python callers can use `pgfr_conformance.kit.check_skill_manifest_data(manifest)`
to validate a parsed dictionary. `check_skill_manifest(path)` provides the same
checks for YAML files.

## Scope

Conformance results describe protocol and schema compatibility. They do not
qualify robot hardware, model quality, network security, timing behavior, or a
physical mission. Complete the applicable deployment acceptance procedure in
[`docs/VALIDATION.md`](../../docs/VALIDATION.md) before enabling motion.
