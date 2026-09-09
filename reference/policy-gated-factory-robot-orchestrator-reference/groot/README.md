# GR00T action integration

The learned-action path uses one fine-tuned NVIDIA Isaac GR00T checkpoint for
all three object types and both Franka arms. Two policy-server processes load
the same checkpoint: one serves the left arm and one serves the right arm.
These are independent serving instances, not separate models or per-color
experts.

## Execution profiles

| Profile | Workflow | Behavior |
|---|---|---|
| Default | `full-groot-dual-tote` | Executes six arm moves and two tote transfers serially |
| Optional paired actions | `full-groot-dual-tote-concurrent` | Queries the two B=1 policy servers concurrently and applies one validated left/right pair as a cell transaction |

The serial workflow is the supported default. It uses this move order:

1. right green;
2. left green;
3. right red;
4. left red;
5. right blue; and
6. left blue.

Each physical action is followed by fresh visual verification. A physical
dispatch is never retried automatically.

The paired-action profile denies dispatch unless
`PGFR_GROOT_PARALLEL_ENABLED=1` and `PGFR_GROOT_FLEXIBLE_ORDER=1` are both set
and the two independent B=1 serving paths pass readiness checks. It accepts
only three mixed-color pairs in this order:

1. left blue and right green;
2. left green and right red; and
3. left red and right blue.

Each completed pair changes the next policy observation, so the pairs remain
sequential even though the two actions within a pair run concurrently.
Unrelated floor operations remain serialized by PGFR Spine.

Both profiles validate policy-server identity, arm and observation identity,
physical tracking, grasp, release, settling, and resulting floor state.
Inference completion alone is not treated as action success.

## Runtime and installation

The installable action runtime lives in [`runtime/`](runtime/). It contains
the home-state convergence, two-arm routing, shared-model deployment,
mixed-color pair execution, and scene-reset implementation. Reset restores the
complete action runtime; no separate runtime staging command is required.

Install it into an idle Isaac scripts mount with the checkpoint path and the
two relay service-state paths:

```bash
export PGFR_GROOT_MODEL_ROOT="$HOME/policy-gated-factory-robot-orchestrator-reference-models/order744-cont24"

ops/install-groot-cell.sh \
  --mount /path/to/isaac-scripts \
  --checkpoint-path "$PGFR_GROOT_MODEL_ROOT" \
  --left-service-state /groot-state/shared-left.json \
  --right-service-state /groot-state/shared-right.json

systemctl --user start pgfr-groot-shared-stack.target
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
export PGFR_GROOT_HF_REPO=mmallick/industrial-claw-groot-order744-cont24
export PGFR_GROOT_HF_REVISION=9307ac9cba3a27c9a57ed2d90393ceefb28367e1
ops/fetch-groot-models.sh
ops/install-groot-thor-shared-profiles.sh
```

The Thor profile installer verifies the existing generic policy/relay unit
contract and the model checksum. It refuses active shared units, occupied
ports, stale readiness files, or differing existing profiles. It installs only
`shared-left.env`, `shared-right.env`, and
`pgfr-groot-shared-stack.target`; it never enables or starts them and does not
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
export PGFR_GROOT_STATE_ROOT="$HOME/.local/share/pgfr-spine/groot/remote-thor-v36"
ops/launch-groot-isaac.sh /path/to/isaac-scripts
```

The development lineage remains in
[`groot_n1_7_pgfr_pipeline/`](groot_n1_7_pgfr_pipeline/). It includes:

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
