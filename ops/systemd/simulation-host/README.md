# Simulation-host GR00T bridge

This unit connects an Isaac simulation host to the two GR00T policy/relay
pairs owned by Thor. It does not run a model or relay locally.

The bridge creates four loopback-only SSH forwards and derives two local
service-state files only after the exact Thor units, listeners, checkpoint,
fingerprint, and relay contract pass validation. Both derived states are
removed if the tunnel or either remote service becomes invalid.

Install while the bridge is idle:

```bash
ops/install-groot-two-host-bridge.sh \
  --thor-ssh user@thor-host \
  --remote-checkpoint /absolute/path/to/order744-cont24 \
  --remote-state-root /absolute/thor/state/root
```

The installer performs a daemon reload but never enables or starts the unit.
Review the generated environment file and run the helper's `--check-config`
preflight before explicitly starting it. Starting, stopping, or replacing an
active bridge remains an operator decision.
