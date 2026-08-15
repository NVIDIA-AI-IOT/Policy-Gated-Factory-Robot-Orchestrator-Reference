# IC Spine user services

These files are templates, not files to copy directly: `__IC_REPO__` and
`__IC_HOME__` are rendered by `../bootstrap-brain.sh --install`.

The six units are the only supported owners of ports 8766, 18790, 8620, 8610,
8601, and 8600. Environment files are seeded once and preserved on later installs.
No unit starts or restarts Isaac Sim or a model container.

The `groot/` templates load the published Order744-cont24 checkpoint in two
independent B=1 policy processes, one per arm. Each process has its own
loopback relay and service-state record. They are installed by
`bootstrap-brain.sh`, but are not started by the brain/viewer target. Start
`ic-groot-shared-stack.target` only after model verification succeeds.

The `simulation-host/` unit is separate. It runs no model and no relay; it
creates validated loopback-only forwards to a Thor-owned shared stack and
publishes only derived local readiness records. Its installer performs a
daemon reload but never enables or starts it.

## Manual and appliance operation

Installation is manual-start by design. `WantedBy` records dependency
relationships but does not enable a unit. This is the default for development,
evaluation, and any cell where an operator must review state before actuation.

An operator may opt into reboot persistence only after reviewing the cell's
startup, network, and safety behavior. On the brain host, enable the exact
reviewed owners rather than a wildcard:

```bash
systemctl --user enable ic-perception-vlm.service \
  ic-seam.service ic-openclaw.service ic-chat.service \
  ic-workflows.service ic-gpu-exporter.service ic-console.service
systemctl --user enable ic-groot-shared-stack.target
loginctl enable-linger "$USER"
```

On the simulation host, persistence of the bridge is a separate decision:

```bash
systemctl --user enable ic-groot-two-host-bridge.service
```

`enable` changes future startup only; it does not start or restart a running
service. To remove persistence without stopping active work, use the matching
`systemctl --user disable ...` commands and, if appropriate,
`loginctl disable-linger "$USER"`. Starting or stopping remains an explicit
operator action.
