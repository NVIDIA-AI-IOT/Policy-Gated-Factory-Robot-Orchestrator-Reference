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

## Tests

`pytest ic-console/tests` — 10 hardware-free tests (canned seam
responses; the read-only guarantee is itself a test).
