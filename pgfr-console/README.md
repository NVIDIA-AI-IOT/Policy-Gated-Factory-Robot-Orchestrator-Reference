# PGFR Console

PGFR Console serves the Orchestration Console, an operator web interface for
Chat, topology, inspection, mission history, and GPU telemetry. Chat opens by
default. Its aggregation API is read-only; the browser calls PGFR Chat directly
for chat and reset operations.

## Install and run

```bash
uv sync --frozen --extra dev --project pgfr-console
PGFR_FLOOR_SERVICE=http://127.0.0.1:8766 \
  uv run --frozen --project pgfr-console pgfr-console
```

Open [http://127.0.0.1:8600](http://127.0.0.1:8600).

## Behavior

- The aggregation API exposes GET routes only.
- Chat's example prompts fill the input for review; Send submits the request.
- The Chat sidebar provides New chat, History, the agent backend selector, and
  collapsed Session details with the assistant name and a copyable session ID.
- Reset Scene is available from the header in every pane. It requires explicit
  confirmation and calls PGFR Chat's `POST /api/reset-scene` endpoint for a
  deterministic reset through PGFR Spine.
- Topology opens with tools and cameras grouped. Enable **Show tools and cameras**
  to inspect each one; a group retains its least healthy member's status.
- Optional integrations appear when configured or reported. NeMo Gym has an
  optional evaluation connector and appears only when `PGFR_GYM_URL` is set.
- Component details identify the status source. Vision model names come from
  the model endpoint; camera feeds come from simulator health. GR00T connection
  status uses the floor state's passive relay observations, not inference probes.
- Mission replay shows readable task titles and verification results; exact
  session IDs and full results remain available in expandable details.
- GPU opens in Live view. Selecting a historical session changes only the GPU
  view; process memory on Thor uses its shared CPU/GPU RAM measurements.
- The browser calls PGFR Chat directly; Console does not proxy its write
  requests.
- The frontend is a static ES-module application with no build-time toolchain
  or external CDN dependency.

## Configuration

| Var | Default | Meaning |
|---|---|---|
| `PGFR_FLOOR_SERVICE` | `http://127.0.0.1:8766` | PGFR Spine base URL |
| `PGFR_VLM_URL` | unset | VLM liveness check (`/v1/models`) |
| `PGFR_GYM_URL` | unset | Optional NeMo Gym resource server; omitted from the map when unset |
| `PGFR_GPU_URL` | unset | GPU exporter on the serving host (`ops/pgfr_gpu_exporter.py` :8601) |
| `PGFR_GPU_URL_THOR` | unset | GPU exporter on Jetson AGX Thor |
| `PGFR_CONSOLE_HOST/PORT` | `127.0.0.1:8600` | bind address |
| `PGFR_CONSOLE_POLL_S` | `2.0` | topology poll interval |
| `PGFR_CHAT_URL` | `http://127.0.0.1:8620` | server-side Chat URL used for read-only aggregation |
| `PGFR_CHAT_PUBLIC_URL` | `PGFR_CHAT_URL` | browser-visible Chat origin admitted by Console's CSP |

## Remote Chat boundary

The default deployment keeps Console and Chat on loopback; use SSH forwarding
for remote operation. An explicit shared trusted-LAN profile may set
`PGFR_CHAT_PUBLIC_URL=http://<thor-ip>:8620` while Chat is separately bound and
firewalled on `8620`. In that profile, any client with network access to Chat
has actuation authority. It has no per-user identity or TLS and is unsuitable
for an untrusted network.

Follow the firewall-before-bind procedure in
[`docs/REMOTE-ACCESS.md`](../docs/REMOTE-ACCESS.md#trusted-lan-console-and-chat);
do not expose PGFR Spine, OpenClaw, GR00T relay, VLM, or GPU-exporter ports.

## Test

```bash
uv run --frozen --project pgfr-console pytest -q pgfr-console/tests
```

The hardware-free suite uses recorded PGFR Spine responses and verifies that the
aggregation API remains GET-only.

## Related documentation

- [Architecture](../docs/ARCHITECTURE.md)
- [Two-host deployment](../docs/REPRODUCIBLE-DEMO.md)
- [Remote access](../docs/REMOTE-ACCESS.md)
- [Security](../SECURITY.md)
