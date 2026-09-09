# ic-chat — chat gateway: a swappable model drives the cell

The write-path sibling that makes the brain a connector. Chat with any model
through one adapter interface; when the model calls a tool, the gateway runs it
through the SAME seam + policy gate as every other actor, journaled under a
per-conversation mission id — so the console's mission replay covers chat too.

```
pip install -e servers/ic-chat
# echo backend (no model, deterministic — 'tool perceive {"target":"tote"}' fires a call):
IC_CHAT_BACKEND=echo IC_FLOOR_SERVICE=http://127.0.0.1:8766 ic-chat   # -> :8620
# real model (Cosmos VLM / vLLM / NIM / hosted — any OpenAI-compatible endpoint):
IC_CHAT_BACKEND=openai IC_CHAT_MODEL_URL=http://127.0.0.1:8000 IC_CHAT_MODEL=cosmos-reason ic-chat
```
Open the console (:8600) -> Chat tab.

## Console-selectable agent backends

The console presents two choices for each new conversation.  The choice is
persisted with the session and cannot change mid-conversation:

| Console choice | Talks to |
|---|---|
| **Traditional IC Chat** (default) | the backend selected by `IC_CHAT_BACKEND`; this is the proven fallback |
| **OpenClaw** | OpenClaw's typed headless Gateway, targeting the restricted `ic-console` agent and its native `ic-floor` MCP tools |

Both choices use the same `ic-chat` browser API and session store. In OpenClaw
mode, OpenClaw owns the MCP tool loop and IC Chat translates native `chat` and
`agent/tool` events into the console's existing SSE/tool-card format. The
operator token stays server-side and the browser never talks directly to port
18790. OpenClaw's shipped frontend is not required; the Gateway runs headlessly.
The supplied config keeps `/v1/chat/completions` enabled only as an explicit
compatibility path (`IC_OPENCLAW_NATIVE_GATEWAY=0`).

## Traditional model adapters

| `IC_CHAT_BACKEND` | Talks to |
|---|---|
| `openai` (default) | any OpenAI-compatible `/v1/chat/completions`: Cosmos VLM, vLLM, NIM, hosted APIs — **NemoClaw/Claude via NIM slot in here** |
| `anthropic` | Anthropic Messages API, including Claude through NVIDIA NIM |
| `openclaw` | OpenClaw Gateway (native typed protocol by default; normally selected per conversation) |
| `echo` | no network; deterministic; for tests/demos |

A new host that speaks its own protocol = one new adapter in `backends.py`.

## Safety (same posture as ic-workflows)

- **CSRF guard** on `/api/chat` (a message can trigger a floor action): requires
  `X-IC-Chat` header + exact Origin check + optional `IC_CHAT_TOKEN`.
- **One governed tool boundary**: traditional mode uses IC Chat's proof-gated
  loop; OpenClaw mode uses the MCP server's certified order/proof/retry gate.
  Both ultimately dispatch through the same IC Spine Seam and journal.
- **Bounded**: `IC_CHAT_MAX_TURNS` caps tool iterations per user turn.
- Loopback-bound by default; the seam's own auth gap is the standing boundary.

### Opt-in shared trusted-LAN access

The supported default remains loopback plus SSH forwarding. For an isolated
shared trusted-operator LAN, the Console can instead reach Chat directly at the
Thor IP when all three settings are applied together:

```dotenv
IC_CHAT_HOST=0.0.0.0
IC_CHAT_CORS=http://127.0.0.1:8600,http://localhost:8600,http://YOUR_THOR_IP:8600
IC_CHAT_TOKEN=console
```

Console must also set
`IC_CHAT_PUBLIC_URL=http://YOUR_THOR_IP:8620`, while retaining
`IC_CHAT_URL=http://127.0.0.1:8620` for server-side reads. Apply an inbound rule
for `8620/tcp` with exactly the same trusted network scope as Console `8600/tcp`
**before** changing the bind address. Keep Workflows, Seam, OpenClaw, VLM,
GR00T policy/relay, and telemetry ports private.

This is automatic shared access, not strong-token authentication. The
`console` value is public in the static UI and acts only as the custom CSRF
header; exact-origin CORS blocks unrelated browser origins, but any non-browser
client with admitted LAN reach can submit the same command. HTTP also provides
no confidentiality. Every client with network access is therefore an operator
with actuation authority. See the canonical
[`firewall-before-bind procedure`](../../docs/REPRODUCIBLE-DEMO.md#opt-in-shared-trusted-lan-chat-automatic-access).

## Provider selection

The `openai` adapter accepts any OpenAI-compatible Bearer credential, including
public NVIDIA `nvapi-...` keys and organization-specific `sk-...` keys. It does
not route by key prefix: `IC_CHAT_MODEL_URL`, `IC_CHAT_API_KEY`, and
`IC_CHAT_MODEL` must describe the same provider profile. Configure the URL
without `/v1`; IC Chat appends the versioned paths.

Examples:

| Profile | `IC_CHAT_MODEL_URL` | Example model |
|---|---|---|
| Public NVIDIA API Catalog | `https://integrate.api.nvidia.com` | `nvidia/nemotron-3-ultra-550b-a55b` |
| Authorized NVIDIA internal | `https://inference-api.nvidia.com` | `azure/openai/gpt-5.6-sol` |

The internal profile is available only to authorized NVIDIA accounts. Always
verify the model appears in the authenticated catalog and completes a dummy
tool-call probe before enabling robot tools.

## Config (env)

`IC_CHAT_BACKEND`, `IC_CHAT_MODEL_URL`, `IC_CHAT_API_KEY`, `IC_CHAT_MODEL`,
`IC_FLOOR_SERVICE`, `IC_CHAT_MAX_TURNS`, `IC_CHAT_CORS`, `IC_CHAT_TOKEN`,
`IC_CHAT_HOST`/`IC_CHAT_PORT` (default `:8620`), `IC_OPENCLAW_URL` (default
`http://127.0.0.1:18790`), `IC_OPENCLAW_CONFIG` (default
`~/.policy-gated-factory-robot-orchestrator-reference/openclaw/openclaw.json`),
`IC_OPENCLAW_TOKEN` (or OpenClaw's official
`OPENCLAW_GATEWAY_TOKEN`), and
`IC_OPENCLAW_WS_URL`, `IC_OPENCLAW_AGENT_ID` (default `ic-console`),
`IC_OPENCLAW_NATIVE_GATEWAY` (default `1`), `IC_OPENCLAW_TIMEOUT_S` (default
`900` seconds for a complete serial factory mission), and the HTTP-compatibility-only
`IC_OPENCLAW_AGENT_MODEL` (default `openclaw/ic-console`).

## Tests

`pytest servers/ic-chat/tests` — hardware-free scripted/fake-Gateway/fake-Seam
coverage, including native tool events, operator-action refusal, and CSRF.

## Chat history (persistent sessions)

Conversations persist to `IC_CHAT_SESSIONS_DIR` (default `~/.ic_chat_sessions`),
one JSON file per session (id validated, no traversal), auto-titled from the
first user message, capped (`IC_CHAT_MAX_SESSIONS`) with the oldest evicted.
Stored display history is capped (`IC_CHAT_MAX_HISTORY`, default 200); only the
recent window (`IC_CHAT_CONTEXT_WINDOW`, default 24) is sent to the model.

- `GET /api/sessions` — list (id, backend, title, updated, message count)
- `GET /api/sessions/{id}` — full transcript
- `DELETE /api/sessions/{id}` — CSRF-guarded

The console Chat tab has a History sidebar: New chat, past conversations
(click to reopen, ✕ to delete), and the current session persists across refresh
via localStorage.
