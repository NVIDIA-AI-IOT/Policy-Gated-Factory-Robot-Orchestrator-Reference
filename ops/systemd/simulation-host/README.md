# Simulation-host GR00T bridge

This unit connects an Isaac simulation host to the two GR00T policy/relay
pairs owned by Thor. It does not run a model or relay locally.

The bridge creates four loopback-only SSH forwards and derives two local
service-state files only after the exact Thor units, listeners, checkpoint,
fingerprint, and relay contract pass validation. Both derived states are
removed if the tunnel or any policy or relay service becomes invalid.

Install while the bridge is stopped. First copy `pgfr_checkpoint.json` and
its sibling `SHA256SUMS` from the verified export to the simulation host.
Use the model directory on Thor and the local metadata path:

```bash
ops/install-groot-two-host-bridge.sh \
  --thor-ssh user@thor-host \
  --remote-checkpoint /absolute/thor/path/to/my-checkpoint \
  --checkpoint-metadata /absolute/local/path/to/pgfr_checkpoint.json \
  --remote-state-root /absolute/thor/state/root
```

The installer performs a daemon reload but never enables or starts the unit.
Review the generated environment file and run the helper's `--check-config`
preflight before starting it. This checks configuration without opening an
SSH connection; remote readiness is checked while the bridge runs. Start,
stop, and replacement operations require an explicit operator decision.
