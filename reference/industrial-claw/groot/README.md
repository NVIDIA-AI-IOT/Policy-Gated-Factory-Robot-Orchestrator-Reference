# GR00T integration for action execution

Industrial Claw's primary learned-motion demo uses one fine-tuned GR00T
checkpoint for all three object types and both Franka arms. The same checkpoint
is loaded by two policy-server processes: one serves the left arm and one
serves the right arm. These are two serving instances of one model, not two
different models or per-color experts.

## How concurrency works

```text
IC Spine mission
  -> choose one left/right object pair
  -> capture one observation for each arm
  -> query the two instances of the same GR00T model concurrently
  -> apply both validated action streams in one paired cell transaction
  -> verify both physical placements and both camera regions
  -> continue to the next pair
```

The two arms move concurrently within a pair. The three pairs are intentionally
sequenced because every completed placement changes the scene seen by the next
pair. Unrelated floor operations remain serialized by IC Spine.

The executor verifies arm identity, observation identity, physical tracking,
grasp, release, settling, and the resulting floor state. A policy response is
not treated as success merely because inference returned normally.

## Demo command

Run the demo with this order:

> Reset and inspect the simulated cell. Pick left blue and right green
> together, then left green and right red together, then left red and right
> blue together. Verify both totes after each pair. Finally, haul both totes to
> the rack and verify completion.

This maps to three concurrent pairs executed sequentially:

1. left blue + right green;
2. left green + right red;
3. left red + right blue.

The demonstrated result placed all six objects using the shared model, then
hauled both loaded totes to the rack with visual and authoritative floor-state
verification.

## What is preserved here

The installable action runtime lives in [`runtime/`](runtime/). It contains
ordinary Python source for measured home-state convergence, two-arm routing,
shared-model deployment, mixed-color pair execution, and scene reset. Reset
restores the complete action runtime automatically; no separate staging
command is needed.

Install it into an idle Isaac scripts mount with the checkpoint path and the
two relay service-state paths:

```bash
export IC_GROOT_MODEL_ROOT="$HOME/industrial-claw-models/order744-cont24"

ops/install-groot-cell.sh \
  --mount /path/to/isaac-scripts \
  --checkpoint-path "$IC_GROOT_MODEL_ROOT" \
  --left-service-state /groot-state/shared-left.json \
  --right-service-state /groot-state/shared-right.json

systemctl --user start ic-groot-shared-stack.target
ops/launch-groot-isaac.sh /path/to/isaac-scripts
```

The installer assigns one policy port and one relay port per arm. If those
defaults are already occupied, select alternatives with
`--left-policy-port`, `--right-policy-port`, `--left-relay-port`, and
`--right-relay-port`. Generated policy-to-relay connections remain
loopback-only on the serving host.

The installer refuses to modify an active Isaac container. The launcher starts
the shared-model route and waits for the GR00T runtime and cell startup ready
markers.

### Separate Thor serving

When Thor and Isaac run on different hosts, Thor remains the sole owner of the
two policy servers, two relays, and their authoritative service-state files.
First fetch and verify the pinned shared checkpoint on Thor, then install only
its two shared profiles and target:

```bash
export IC_GROOT_HF_REPO=mmallick/industrial-claw-groot-order744-cont24
export IC_GROOT_HF_REVISION=9307ac9cba3a27c9a57ed2d90393ceefb28367e1
ops/fetch-groot-models.sh
ops/install-groot-thor-shared-profiles.sh
```

The Thor profile installer verifies the existing generic policy/relay unit
contract and the model checksum. It refuses active shared units, occupied
ports, stale readiness files, or differing existing profiles. It installs only
`shared-left.env`, `shared-right.env`, and
`ic-groot-shared-stack.target`; it never enables or starts them and does not
replace the generic templates used by other profiles.

The simulation host then installs the dedicated bridge:

```bash
ops/install-groot-two-host-bridge.sh \
  --thor-ssh user@thor-host \
  --remote-checkpoint /absolute/path/to/order744-cont24 \
  --remote-state-root /absolute/thor/state/root
```

The installer does not enable or start the bridge. After an operator reviews
both host configurations and explicitly starts the Thor shared target and the
simulation-host bridge, the bridge opens four loopback-only SSH forwards.
It publishes a separate local state pair only while both remote units,
listeners, checkpoint identities, fingerprints, and relay contracts are
valid. Tunnel or identity failure removes both local readiness records.

The Isaac installer then consumes the derived left/right state paths and the
bridge's local policy/relay ports. It does not need network-facing GR00T
listeners, and the existing executor and relay protocol remain unchanged.
For the bridge defaults, render the cell contracts with policy ports
5792/5793, relay ports 5741/5742, and service-state paths beneath
`/groot-state`. Launch with:

```bash
export IC_GROOT_STATE_ROOT="$HOME/.local/share/ic-spine/groot/remote-thor-v36"
ops/launch-groot-isaac.sh /path/to/isaac-scripts
```

The development lineage remains in
[`groot_n1_7_ic_pipeline/`](groot_n1_7_ic_pipeline/). It includes:

- synchronized simulation capture and native-DROID conversion;
- the official NVIDIA fine-tuning entry point and single-frame modality;
- the isolated Order744-cont24 continuation recipe;
- the dataset and model validation contract.

The direct executor lives in [`runtime/`](runtime/), and the serving bridge
lives in [`relay/`](relay/). Earlier development iterations remain available
through Git history. The public installer does not checksum normal source
files: Git versions and behavioral tests cover source, while the model
artifact checksum validates the downloaded weights at the serving boundary.

## Reproduction status

The one-model action runtime and its successful evidence are packaged. Thor
supplies the Order744-cont24 checkpoint and authoritative state manifests
produced by its two serving instances; a separate simulation host consumes
validated derived manifests from the bridge. The public model and dataset
revisions are pinned in [`models/manifest.yaml`](models/manifest.yaml) and can be
downloaded without repository-specific access. The fetch path still requires
Hugging Face authentication for its separately gated Cosmos-Reason2-2B runtime
backbone. Persistent local service templates load the same checkpoint in two
independent B=1 processes and publish one service-state record per arm. A
fresh-machine full-cell validation remains a release input.

See [`../../../docs/REPRODUCIBLE-DEMO.md`](../../../docs/REPRODUCIBLE-DEMO.md)
for the two-host setup and the remaining release gates.
