# MCP server creation workflow

Expose your system (video analytics, QC, fleet data, …) as tools any brain in the
ecosystem can use — one handshake, doctrine included. Reference implementation:
[`../industrial-claw-mcp`](../industrial-claw-mcp/).

## The workflow

1. **Copy** this directory to `servers/<your-name>-mcp/`; rename `my_mcp` (3 spots
   in `pyproject.toml`, the `src/` dir).
2. **Write `src/<pkg>/INSTRUCTIONS.md`** — the operating doctrine for your domain:
   what the tools are for, in what order, what not to do. This ships in the MCP
   handshake; a server without doctrine is a foot-gun with a schema.
3. **Implement tools.** Rules of the house:
   - docstring on every tool (the model reads it) + `ToolAnnotations`
     (title, `readOnlyHint`; `destructiveHint` honestly set),
   - return JSON data, not prose,
   - effectful tools return a `verified` field — never claim unverified success,
   - proxy a certified seam where possible; add no authority of your own.
4. **Test**: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest`
   (the three template tests are the minimum bar — keep them).
5. **Certify**: `ic-conformance mcp --command .venv/bin/<your-cli>` — connects over
   stdio and verifies instructions + annotations + tool hygiene.
6. **Register**: PR adding your server to the catalog table in `servers/README.md`.

## Conventions

- stdio transport by default; config via env vars (document them in your README)
- one mission-id per session if you talk to the floor seam (`x-mission-id` header)
- role header `x-role` only if your users are operators — default to agent
