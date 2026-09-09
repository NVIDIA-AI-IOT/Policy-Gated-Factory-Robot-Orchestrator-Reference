# PGFR Console

PGFR Console is the operator web interface for topology, inspection, mission
history, Chat, Workflows, and GPU telemetry. Its aggregation API is read-only.
The Chat and Workflows tabs call their corresponding services directly for
write operations.

## Install and run

```bash
uv sync --frozen --extra dev --project pgfr-console
PGFR_FLOOR_SERVICE=http://127.0.0.1:8766 \
  uv run --frozen --project pgfr-console pgfr-console
```

Open [http://127.0.0.1:8600](http://127.0.0.1:8600).

## Behavior

- The aggregation API exposes GET routes only.
- Topology status comes from measured health endpoints. Unavailable signals
  render as `unknown`.
- Mission replay reads the PGFR Spine journal by mission ID.
- The browser calls PGFR Chat and PGFR Workflows directly; Console does not proxy
  their write requests.
- The frontend is a static ES-module application with no build-time toolchain
  or external CDN dependency.

## Configuration

| Var | Default | Meaning |
|---|---|---|
| `PGFR_FLOOR_SERVICE` | `http://127.0.0.1:8766` | PGFR Spine base URL |
| `PGFR_VLM_URL` | unset | VLM liveness check (`/v1/models`) |
| `PGFR_GYM_URL` | unset | NeMo Gym pgfr_cell server liveness |
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
