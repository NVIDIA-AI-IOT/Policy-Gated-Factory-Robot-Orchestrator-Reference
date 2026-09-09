# PGFR Chat

PGFR Chat provides persistent operator conversations backed by a selectable
model service. In traditional mode it executes model tool calls through the PGFR
Spine HTTP API. In OpenClaw mode, OpenClaw executes the MCP tool loop. Both
paths use PGFR Spine policy, verification, and mission journaling.

## Install and run

```bash
uv sync --frozen --extra dev --project servers/pgfr-chat

# Deterministic local backend; no model service required.
PGFR_CHAT_BACKEND=echo \
PGFR_FLOOR_SERVICE=http://127.0.0.1:8766 \
  uv run --frozen --project servers/pgfr-chat pgfr-chat
```

The service listens on `127.0.0.1:8620` by default. Open PGFR Console on port
`8600` and select **Chat**.

## Agent backends

The console presents two choices for each new conversation. The choice is
persisted with the session and cannot change mid-conversation:

| Console choice | Talks to |
|---|---|
| **Traditional PGFR Chat** (default) | Adapter selected by `PGFR_CHAT_BACKEND` |
| **OpenClaw** | OpenClaw's typed headless Gateway, targeting the restricted `pgfr-console` agent and its native `pgfr-floor` MCP tools |

Both choices use the same `pgfr-chat` browser API and session store. In OpenClaw
mode, OpenClaw owns the MCP tool loop and PGFR Chat translates native `chat` and
`agent/tool` events into the console's existing SSE/tool-card format. The
operator token stays server-side and the browser never talks directly to port
18790. OpenClaw's shipped frontend is not required; the Gateway runs headlessly.
The supplied config keeps `/v1/chat/completions` enabled only as an explicit
compatibility path (`PGFR_OPENCLAW_NATIVE_GATEWAY=0`).

## Model adapters

| `PGFR_CHAT_BACKEND` | Talks to |
|---|---|
| `openai` (default) | OpenAI-compatible `/v1/chat/completions` endpoint, including NVIDIA API Catalog, NIM, vLLM, and compatible hosted services |
| `anthropic` | Anthropic Messages API, including Claude through NVIDIA NIM |
| `openclaw` | OpenClaw Gateway (native typed protocol by default; normally selected per conversation) |
| `echo` | no network; deterministic; for tests/demos |

Additional protocols are implemented as adapters in `backends.py`.

## Request and action boundary

- `/api/chat` requires the `X-PGFR-Chat` header, an allowed Origin, and the
  optional `PGFR_CHAT_TOKEN`.
- `PGFR_CHAT_MAX_TURNS` limits model tool iterations for one user message.
- Traditional and OpenClaw modes both dispatch through PGFR Spine.
- Physical actions are not resent automatically after a timeout or unverified
  outcome. Reconciliation begins with read-only state or visual evidence.
- All services bind to loopback by default.

### Opt-in shared trusted-LAN access

The supported default remains loopback plus SSH forwarding. For an isolated
shared trusted-operator LAN, the Console can instead reach Chat directly at the
Thor IP when all three settings are applied together:

```dotenv
PGFR_CHAT_HOST=0.0.0.0
PGFR_CHAT_CORS=http://127.0.0.1:8600,http://localhost:8600,http://YOUR_THOR_IP:8600
PGFR_CHAT_TOKEN=console
```

Console must also set
`PGFR_CHAT_PUBLIC_URL=http://YOUR_THOR_IP:8620`, while retaining
`PGFR_CHAT_URL=http://127.0.0.1:8620` for server-side reads. Apply an inbound rule
for `8620/tcp` with exactly the same trusted network scope as Console `8600/tcp`
**before** changing the bind address. Keep Workflows, PGFR Spine, OpenClaw, VLM,
GR00T policy/relay, and telemetry ports private.

This is shared network access, not user authentication. The
`console` value is public in the static UI and acts only as the custom CSRF
header; exact-origin CORS blocks unrelated browser origins, but any non-browser
client with admitted LAN reach can submit the same command. HTTP also provides
no confidentiality. Every client with network access is therefore an operator
with actuation authority. See the
[`firewall-before-bind procedure`](../../docs/REMOTE-ACCESS.md#trusted-lan-console-and-chat).

## Provider selection

The `openai` adapter accepts any OpenAI-compatible Bearer credential, including
public NVIDIA `nvapi-...` keys and organization-specific `sk-...` keys. It does
not route by key prefix: `PGFR_CHAT_MODEL_URL`, `PGFR_CHAT_API_KEY`, and
`PGFR_CHAT_MODEL` must describe the same provider profile. Configure the URL
without `/v1`; PGFR Chat appends the versioned paths.

Examples:

| Profile | `PGFR_CHAT_MODEL_URL` | Example model |
|---|---|---|
| Public NVIDIA API Catalog | `https://integrate.api.nvidia.com` | `nvidia/nemotron-3-ultra-550b-a55b` |
| Authorized NVIDIA internal | `https://inference-api.nvidia.com` | `azure/openai/gpt-5.6-sol` |

The internal profile is available only to authorized NVIDIA accounts. Before
enabling robot tools, verify that the model appears in the authenticated
catalog, returns a real completion, and supports the required tool calls.

## Configuration

| Setting | Purpose |
|---|---|
| `PGFR_CHAT_BACKEND` | Traditional adapter: `openai`, `anthropic`, `openclaw`, or `echo` |
| `PGFR_CHAT_MODEL_URL`, `PGFR_CHAT_API_KEY`, `PGFR_CHAT_MODEL` | Model endpoint, Bearer credential, and model ID |
| `PGFR_FLOOR_SERVICE` | PGFR Spine base URL |
| `PGFR_CHAT_MAX_TURNS` | Maximum tool-loop iterations per message |
| `PGFR_CHAT_CORS`, `PGFR_CHAT_TOKEN` | Allowed browser origins and request guard |
| `PGFR_CHAT_HOST`, `PGFR_CHAT_PORT` | Bind address; default `127.0.0.1:8620` |
| `PGFR_OPENCLAW_URL`, `PGFR_OPENCLAW_WS_URL` | OpenClaw HTTP and WebSocket endpoints |
| `PGFR_OPENCLAW_CONFIG` | OpenClaw configuration path |
| `PGFR_OPENCLAW_TOKEN` or `OPENCLAW_GATEWAY_TOKEN` | OpenClaw Gateway credential |
| `PGFR_OPENCLAW_AGENT_ID` | OpenClaw agent ID; default `pgfr-console` |
| `PGFR_OPENCLAW_NATIVE_GATEWAY` | Native typed Gateway mode; default `1` |
| `PGFR_OPENCLAW_TIMEOUT_S` | Gateway timeout; default `900` seconds |
| `PGFR_OPENCLAW_AGENT_MODEL` | HTTP compatibility model; default `openclaw/pgfr-console` |

## Test

```bash
uv run --frozen --project servers/pgfr-chat pytest -q servers/pgfr-chat/tests
```

The hardware-free suite covers model adapters, Gateway events, PGFR Spine
responses, operator-action refusal, sessions, and browser request guards.

## Chat history (persistent sessions)

Conversations persist to `PGFR_CHAT_SESSIONS_DIR` (default `~/.pgfr_chat_sessions`),
one JSON file per session (id validated, no traversal), auto-titled from the
first user message, capped (`PGFR_CHAT_MAX_SESSIONS`) with the oldest evicted.
Stored display history is capped (`PGFR_CHAT_MAX_HISTORY`, default 200); only the
recent window (`PGFR_CHAT_CONTEXT_WINDOW`, default 24) is sent to the model.

- `GET /api/sessions` — list (id, backend, title, updated, message count)
- `GET /api/sessions/{id}` — full transcript
- `DELETE /api/sessions/{id}` — CSRF-guarded

The Console History view can create, reopen, and delete conversations. The
current session ID is retained in browser local storage.

## Related documentation

- [Model and credential configuration](../../docs/MODEL-PROVIDERS.md)
- [Remote operator access](../../docs/REMOTE-ACCESS.md)
- [Security](../../SECURITY.md)
