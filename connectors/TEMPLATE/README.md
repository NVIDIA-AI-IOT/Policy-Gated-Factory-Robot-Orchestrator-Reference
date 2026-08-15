# Connector creation workflow

Wrap an external system (VSS video pipelines, MES/ERP, quality DBs) so the brain
can reach it — as context and evidence, under the same umbrella as everything else.
Connectors never dispatch floor actions; that authority stays at the seam.

## The workflow

1. **Copy** this directory to `connectors/<your-system>/`; rename `my_connector`
   (pyproject + `src/` dir).
2. **Implement** the three methods on `Connector` (`ic-connector-sdk`):
   - `health()` — honest liveness + data freshness of the wrapped system,
   - `capabilities()` — each with a description and a JSON-schema params contract,
   - `call()` — results are evidence: always include `source` + timestamp;
     raise `KeyError` for unknown capabilities.
3. **Configure via env** (endpoints, credentials) — never in code, never in git.
4. **Test**: `pytest` — `assert_connector_compliant(...)` is the certification bar;
   keep it plus your domain tests.
5. **Register**: PR adding your connector to the catalog; the backbone re-exposes
   your capabilities northbound as MCP tools (read-only annotated), journaled like
   every other operation.

## Rules of the house

- read-mostly: a connector informs decisions; it does not act on the floor
- no hidden authority: if your system must *cause* something, it goes through
  the seam's policy gate like everyone else
- degrade loudly: unreachable system -> `health.ok=false` + errors, never stale
  answers presented as fresh (the floor learned this the hard way)
