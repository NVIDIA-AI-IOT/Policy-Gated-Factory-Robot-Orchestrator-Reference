# User-systemd services

These templates define the long-running services on the Jetson control host.
Do not copy them directly: `ops/bootstrap-brain.sh --install` replaces
`__PGFR_REPO__` and `__PGFR_HOME__` with installation-specific paths, seeds the
environment files, and reloads the user manager.

## Service ownership

| Unit | Port | Purpose |
|---|---:|---|
| `pgfr-seam.service` | 8766 | PGFR Spine HTTP and ROS 2 floor service |
| `pgfr-openclaw.service` | 18790 | Loopback OpenClaw Gateway API |
| `pgfr-chat.service` | 8620 | PGFR Chat API |
| `pgfr-workflows.service` | 8610 | Workflow API and runner |
| `pgfr-console.service` | 8600 | Operator Console |
| `pgfr-gpu-exporter.service` | 8601 | Jetson GPU telemetry |
| `pgfr-perception-vlm.service` | 8001 | Pinned perception VLM |

The GR00T templates under [`groot/`](groot/) run two independent B=1 policy
processes and two loopback relays. The per-arm units are grouped by
`pgfr-groot-shared-stack.target` and publish separate service-state records.
Installation does not start or enable that target.

The [simulation-host bridge](simulation-host/README.md) is installed and
operated separately on the RTX host. It runs no model or relay.

## Operate the control-host stack

The repository helper is read-only unless an explicit operation and target are
provided:

```bash
ops/thor-deploy.sh --check
ops/thor-deploy.sh --status
ops/thor-deploy.sh --start all
ops/thor-deploy.sh --restart chat
```

Supported operation targets are `vlm`, `seam`, `gateway`, `chat`,
`workflows`, `gpu`, `console`, and `all`. Start the GR00T target separately,
after its model and readiness inputs have been verified:

```bash
systemctl --user start pgfr-groot-shared-stack.target
```

No unit starts or restarts Isaac Sim. Existing environment files under
`~/.config/pgfr-spine/` are preserved by later bootstrap runs and must be
reviewed when deployment settings change.

## Optional startup at boot

Manual start is the default. Enable persistent user services only after the
site has reviewed startup, network, and actuation behavior:

```bash
systemctl --user enable pgfr-perception-vlm.service pgfr-seam.service
systemctl --user enable pgfr-openclaw.service pgfr-chat.service pgfr-workflows.service
systemctl --user enable pgfr-gpu-exporter.service pgfr-console.service
systemctl --user enable pgfr-groot-shared-stack.target
loginctl enable-linger "$USER"
```

The RTX bridge requires a separate decision on the simulation host:

```bash
systemctl --user enable pgfr-groot-two-host-bridge.service
```

`enable` changes future startup behavior; it does not start or restart a
running service. Use the matching `systemctl --user disable` commands to remove
persistence. Disable lingering separately with
`loginctl disable-linger "$USER"` when appropriate.
