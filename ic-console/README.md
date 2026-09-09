# ic-console — read-only live console for the IC floor

One screen: the system block diagram, alive. Every node shows measured status
(never guessed), clicking a node shows its live detail, and the mission panel
replays any journaled mission as a verified/failed operation timeline.

```
pip install -e ic-console
IC_FLOOR_SERVICE=http://127.0.0.1:8766 ic-console   # -> http://127.0.0.1:8600
```

## Design rules

- **Read-only by construction** — the API exposes only GETs (enforced by a
  test); the console holds no dispatch capability and sits beside the control
  path, never in it. It can crash or lag without touching production.
- **Measured, not asserted** — statuses come from existing endpoints only:
  seam `/v1/health` (drives seam/floor/cell/journal), `/v1/missions` (replay),
  optional `IC_VLM_URL`/`IC_GYM_URL` liveness. Anything unmeasurable renders
  `unknown`, not green.
- **Zero-toolchain frontend** — a no-build, no-CDN ES-module SPA served by the
  aggregator (matches the repo's stdlib-first bias). When the workflow-builder
  phase lands, that page graduates to a proper React Flow app; the API stays.

## Config (env)

| Var | Default | Meaning |
|---|---|---|
| `IC_FLOOR_SERVICE` | `http://127.0.0.1:8766` | seam base URL |
| `IC_VLM_URL` | unset | VLM liveness check (`/v1/models`) |
| `IC_GYM_URL` | unset | NeMo Gym ic_cell server liveness |
| `IC_GPU_URL` | unset | GPU exporter on the serving host (`ops/ic_gpu_exporter.py` :8601) |
| `IC_GPU_URL_THOR` | unset | same exporter on the Thor Jetson (tegra probe) — adds the Thor card |
| `IC_CONSOLE_HOST/PORT` | `127.0.0.1:8600` | bind address |
| `IC_CONSOLE_POLL_S` | `2.0` | topology poll interval |
| `IC_CHAT_URL` | `http://127.0.0.1:8620` | server-side Chat URL used for read-only aggregation |
| `IC_CHAT_PUBLIC_URL` | `IC_CHAT_URL` | browser-visible Chat origin admitted by Console's CSP |

## Remote Chat boundary

Console remains GET-only and never proxies Chat writes. The default deployment
keeps both services on loopback; use SSH forwarding for authenticated remote
operation. An explicit shared trusted-LAN alternative may set
`IC_CHAT_PUBLIC_URL=http://<thor-ip>:8620` while Chat is separately bound and
firewalled on `8620`. In that mode the browser talks directly to Chat, and every
principal allowed to load Console is intentionally granted actuation authority.
It has no per-user identity or TLS and is unsuitable for an untrusted network.

Follow the firewall-before-bind procedure in
[`docs/REPRODUCIBLE-DEMO.md`](../docs/REPRODUCIBLE-DEMO.md#opt-in-shared-trusted-lan-chat-automatic-access);
do not expose the Seam, OpenClaw, GR00T relay, VLM, or GPU-exporter ports.

## Tests

`pytest ic-console/tests` runs the hardware-free suite with canned seam
responses; the read-only guarantee is itself a test.
