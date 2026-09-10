# PGFR Workflows

PGFR Workflows stores, validates, and executes reviewable YAML workflows through
PGFR Spine. Its HTTP API supports authoring, dry-runs, execution, schedules,
and skill publication.

## Install and run

From the repository root:

```bash
uv sync --frozen --extra dev --project servers/pgfr-workflows
PGFR_FLOOR_SERVICE=http://127.0.0.1:8766 uv run --frozen \
  --project servers/pgfr-workflows pgfr-workflows
```

The service listens on `127.0.0.1:8610` by default. View its API documentation
at [http://127.0.0.1:8610/docs](http://127.0.0.1:8610/docs). For a complete
mission example, follow the
[serial reference mission procedure](../../docs/VALIDATION.md#run-the-serial-reference-mission).

## Workflow lifecycle

| Operation | Behavior |
|---|---|
| Compose | Loads the tool palette from `/api/tools`. Arguments may use literals, `${params.name}`, or backward-only `${steps.N.field}` references. |
| Save | Validates the specification and writes `workflows/<name>.yaml`. Only agent-class `move` and `pick_and_place` actions are accepted. |
| Dry run | Resolves parameters and prior-step references without contacting PGFR Spine. |
| Run | Executes each step through PGFR Spine under one `wf-<name>-<hex>` mission ID. |
| Schedule | Stores an opt-in interval of 30 to 86,400 seconds. Scheduled runs use the same validation, policy, and verification path as manual runs. |
| Publish | Writes a skill manifest below `skills/wf-<name>/` and validates the same agent-action boundary. |

Version 1 workflows are linear and limited to 20 steps. They do not support
branches, loops, or embedded code.

## Execution controls

Physical steps always gate on the PGFR Spine result:

- `dispatch_task` requires `verified=true`;
- `dispatch_parallel` requires `verified=true` and
  `independent_b1_verified=true`; and
- `check_predicate` requires `answer=yes` with complete evidence.

The runner never retries `dispatch_task` or `dispatch_parallel`. A transport
failure or unverified result stops the workflow because the physical outcome
may be uncertain. Read-only operations can use `max_retries` from `0` to `3`.

The default `full-groot-dual-tote` workflow executes all physical actions
serially. The optional `full-groot-dual-tote-concurrent` workflow is refused
before PGFR Spine contact unless `PGFR_GROOT_PARALLEL_ENABLED=1` and
`PGFR_GROOT_FLEXIBLE_ORDER=1` are both set. PGFR Spine independently permits only
the next accepted pair:

1. left blue and right green;
2. left green and right red; and
3. left red and right blue.

Same-color, partial, skipped, repeated, and out-of-order pairs are refused.

## Draft assistant

`POST /api/assist` accepts a `workflow` or `skill` instruction and uses the
configured PGFR Chat model adapter to return a schema-validated draft. It does
not write a workflow or skill. Save and publish remain explicit, separately
validated operations.

New primitive tools require PGFR Spine implementation and policy. The assistant
can compose only the existing tool palette.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PGFR_FLOOR_SERVICE` | `http://127.0.0.1:8766` | PGFR Spine base URL |
| `PGFR_WORKFLOWS_DIR` | `workflows/` | Workflow specification directory |
| `PGFR_SKILLS_DIR` | `skills/` | Published skill directory |
| `PGFR_WORKFLOWS_HOST` | `127.0.0.1` | Bind address |
| `PGFR_WORKFLOWS_PORT` | `8610` | HTTP port |
| `PGFR_WORKFLOWS_CORS` | `http://127.0.0.1:8600` | Allowed browser origins |
| `PGFR_WORKFLOWS_TOKEN` | unset | Optional write-request token |
| `PGFR_WORKFLOWS_TIMEOUT_S` | `300` | PGFR Spine request timeout |
| `PGFR_WORKFLOWS_SCHEDULER` | `1` | Enables the scheduler loop |
| `PGFR_WORKFLOWS_MAX_CONCURRENT` | `2` | Maximum concurrent scheduled runs |
| `PGFR_GROOT_PARALLEL_ENABLED` | `0` | Records parallel-serving readiness |
| `PGFR_GROOT_FLEXIBLE_ORDER` | `0` | Enables the accepted mixed-pair order |

Keep the service on loopback. The direct-IP trusted-LAN profile does not expose
the Workflows API; use the optional Workflows port forwarding in the
[SSH-tunnel profile](../../docs/REMOTE-ACCESS.md#ssh-tunnel) for remote API access.

## Test

```bash
uv run --frozen --project servers/pgfr-workflows \
  pytest -q servers/pgfr-workflows/tests
```

The hardware-free suite covers schema validation, template resolution,
execution gates, scheduling, pair order, browser request guards, and published
skill conformance.

## Related documentation

- [Two-host deployment](../../docs/REPRODUCIBLE-DEMO.md)
- [Deployment validation](../../docs/VALIDATION.md)
- [Architecture](../../docs/ARCHITECTURE.md)
- [Workflow schema](../../schemas/)
