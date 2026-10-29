# Configure model providers

Configure Chat reasoning separately from perception:

| Service | Purpose | Configuration |
|---|---|---|
| PGFR Chat | Reasoning and tool selection | `~/.config/pgfr-spine/chat.env` and `~/.openclaw/secrets.env` |
| Perception VLM | Camera evidence on port `8001` | Pinned container and model in [`../deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml) |

PGFR Chat accepts an OpenAI-compatible endpoint. The endpoint URL, credential,
and model ID must match; the application does not infer the
endpoint from the API-key prefix.

## Contents

- [Select a PGFR Chat endpoint](#select-a-pgfr-chat-endpoint)
- [Store credentials](#store-credentials)
- [Configure OpenClaw](#configure-openclaw)
- [Test a completion](#test-a-completion)
- [Perception VLM boundary](#perception-vlm-boundary)

## Select a PGFR Chat endpoint

Before starting PGFR Chat, replace `replace-with-your-model-id` in
`~/.config/pgfr-spine/chat.env`. Set `PGFR_CHAT_MODEL_URL` to the service root
without `/v1`; the adapter appends `/v1/models` and `/v1/chat/completions`.

### NVIDIA API Catalog

Use this profile for the public NVIDIA API Catalog:

```dotenv
PGFR_CHAT_BACKEND=openai
PGFR_CHAT_MODEL_URL=https://integrate.api.nvidia.com
PGFR_CHAT_MODEL=nvidia/nemotron-3-ultra-550b-a55b
```

Use a model ID available to the deployed NVIDIA account. The example does not
guarantee access for every account. Obtain a hosted-endpoint key using the
[NVIDIA API Catalog quickstart](https://docs.api.nvidia.com/nim/re/docs/api-quickstart).

### Other OpenAI-compatible services

For another provider or a self-hosted model, replace the example hostname and
model ID with the values for your service:

```dotenv
PGFR_CHAT_BACKEND=openai
PGFR_CHAT_MODEL_URL=https://inference.example.test
PGFR_CHAT_MODEL=your-tool-calling-model
```

Query the authenticated `/v1/models` catalog and validate tool calling before
selecting a model ID.

## Store credentials

Keep credentials out of the repository and shell history. The bootstrap
creates the secrets file and a persistent `OPENCLAW_GATEWAY_TOKEN`; edit that
same file without removing the generated token:

```bash
install -d -m 0700 "$HOME/.openclaw"
touch "$HOME/.openclaw/secrets.env"
chmod 0600 "$HOME/.openclaw/secrets.env"
${EDITOR:-vi} "$HOME/.openclaw/secrets.env"
```

For traditional PGFR Chat, add the credential issued for the selected endpoint:

```dotenv
PGFR_CHAT_API_KEY=YOUR_SELECTED_ENDPOINT_KEY
```

PGFR Chat sends `PGFR_CHAT_API_KEY` unchanged as a Bearer credential. Use the
credential issued for the configured endpoint; key prefixes do not select a
provider.

For the public NVIDIA profile, the same `nvapi-...` value may also be stored as
`NVIDIA_API_KEY` for OpenClaw's built-in NVIDIA provider. The hosted-endpoint
credential is distinct from the Hugging Face token used for model downloads
and from a registry-only NGC credential.

## Configure OpenClaw

Seed the repository's complete OpenClaw configuration before using its
configuration CLI. Running `openclaw models set` against a missing config
creates an incomplete replacement without the repository's MCP server and
policy settings. Start the loopback Gateway once, verify its config, and stop
it again:

```bash
systemctl --user start pgfr-openclaw.service
test -s "$HOME/.policy-gated-factory-robot-orchestrator-reference/openclaw/openclaw.json"
systemctl --user stop pgfr-openclaw.service pgfr-seam.service
```

For the public NVIDIA profile, configure OpenClaw's primary model while its
Gateway is stopped:

```bash
set -a
. "$HOME/.config/pgfr-spine/openclaw.env"
. "$HOME/.openclaw/secrets.env"
set +a
./node_modules/.bin/openclaw models set \
  nvidia/nemotron-3-ultra-550b-a55b
unset NVIDIA_API_KEY PGFR_CHAT_API_KEY OPENCLAW_GATEWAY_TOKEN
```

This command configures OpenClaw's built-in public NVIDIA provider.
PGFR Chat and OpenClaw configure providers independently. Changing
`PGFR_CHAT_MODEL_URL` does not change OpenClaw. Configure other OpenClaw
providers in the Gateway's own configuration.

## Test a completion

Test one real completion before starting the stack. A successful `/v1/models`
response does not prove that the API key is authorized for inference:

```bash
(
set -euo pipefail
set -a
. "$HOME/.config/pgfr-spine/chat.env"
set +a
: "${PGFR_CHAT_MODEL_URL:?set PGFR_CHAT_MODEL_URL in ~/.config/pgfr-spine/chat.env}"
: "${PGFR_CHAT_MODEL:?set PGFR_CHAT_MODEL in ~/.config/pgfr-spine/chat.env}"
MODEL_URL="${PGFR_CHAT_MODEL_URL%/}"
case "$MODEL_URL" in
  */v1) echo 'PGFR_CHAT_MODEL_URL must exclude /v1' >&2; exit 1 ;;
esac
REQUEST_BODY="$(python3 -c '
import json, sys
print(json.dumps({
    "model": sys.argv[1],
    "messages": [{"role": "user", "content": "Reply with READY."}],
}))
' "$PGFR_CHAT_MODEL")"
AUTH_HEADER="$(mktemp)"
trap 'rm -f "$AUTH_HEADER"' EXIT
chmod 0600 "$AUTH_HEADER"
set -a
. "$HOME/.openclaw/secrets.env"
set +a
: "${PGFR_CHAT_API_KEY:?set PGFR_CHAT_API_KEY in ~/.openclaw/secrets.env}"
printf 'Authorization: Bearer %s\n' "$PGFR_CHAT_API_KEY" > "$AUTH_HEADER"
unset NVIDIA_API_KEY PGFR_CHAT_API_KEY OPENCLAW_GATEWAY_TOKEN
curl --fail-with-body --silent --show-error \
  "$MODEL_URL/v1/chat/completions" \
  -H "@$AUTH_HEADER" \
  -H 'Content-Type: application/json' \
  -d "$REQUEST_BODY"
)
```

The mode-`0600` temporary header file keeps the key out of `curl`'s process
arguments. The shown API-key and gateway-token variables are unset before `curl` starts,
and the file is removed when the subshell exits.

## Perception VLM boundary

The perception VLM on port `8001` is a separate, pinned service. It provides
camera evidence and is not an implicit replacement for the PGFR Chat reasoning
model. Pull its exact image during the control-host artifact step in the
[two-host deployment guide](REPRODUCIBLE-DEMO.md#2-fetch-control-host-artifacts).
