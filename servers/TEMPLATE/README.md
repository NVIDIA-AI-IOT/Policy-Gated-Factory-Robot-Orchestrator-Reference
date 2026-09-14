# MCP server template

This directory is a minimal Python MCP server for exposing a system as typed
tools. It uses standard input/output transport and includes examples of a
read-only tool and an effectful tool.

See the [PGFR floor MCP
server](../policy-gated-factory-robot-orchestrator-reference-mcp/README.md) for
the repository's reference implementation.

## Requirements

- Python 3.10 or later
- The `pgfr-conformance` package for the optional MCP contract check

## Create a server

1. Copy this directory to `servers/<name>-mcp/`.
2. Rename the project, command, and source package entries in `pyproject.toml`.
3. Add `src/<package>/INSTRUCTIONS.md`. This content is sent to each MCP client
   in the server handshake.
4. Replace the example tools in `src/<package>/server.py`.
5. Add tests for transport errors, authorization boundaries, and the system
   behind each tool.
6. Document the completed server in the repository [source map](../../STRUCTURE.md).

Every tool should have a concise docstring and accurate `ToolAnnotations`.
Return structured JSON data. An effectful tool should report whether its result
was verified and must not infer success from request acceptance alone.

## Install and test

From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

The template intentionally omits `INSTRUCTIONS.md`. Add that file and replace
all placeholders before running the tests:

```bash
.venv/bin/python -m pytest
```

## Run the server

```bash
.venv/bin/my-mcp
```

The process communicates over standard input/output. Configure endpoints and
credentials through environment variables or a secret store, and document
every required variable in the completed server README.

## Run the MCP conformance check

Install the [conformance
kit](../../packages/conformance-kit/README.md), then run from this directory:

```bash
../../packages/conformance-kit/.venv/bin/pgfr-conformance mcp \
  --command "$PWD/.venv/bin/my-mcp"
```

The check covers handshake instructions, tool availability, descriptions, and
annotations. It does not validate authorization, the backing system, or the
semantic correctness of tool results.

## Floor-service integration

When a tool proxies PGFR Spine:

- preserve one mission ID for the lifetime of the MCP process;
- use the `agent` role unless the user explicitly invokes an operator control;
- return PGFR Spine results without converting an unverified result into success;
  and
- leave motion policy and physical verification at PGFR Spine.
