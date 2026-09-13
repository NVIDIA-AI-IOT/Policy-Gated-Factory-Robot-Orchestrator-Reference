# GR00T action integration

The learned-action path uses one user-trained NVIDIA Isaac GR00T checkpoint for
all three object types and both Franka arms. Two policy-server processes load
the same checkpoint: one serves the left arm and one serves the right arm.
These are independent serving instances, not separate models or per-color
experts.

Create your own demonstrations and checkpoint using the
[dataset-creation guide](groot_n1_7_pgfr_pipeline/docs/DATASET_CREATION.md),
[training recipe](groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md), and
[local export procedure](models/README.md). No project fine-tuned weights or
recorded training dataset are supplied. Official NVIDIA base models and their
license/access prerequisites remain required.

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

Thor runs the GR00T policy and relay processes directly in the pinned host
Python environment. Follow the [bare-metal Thor setup](thor/README.md); the
project does not provide a Thor GR00T container build. Dataset conversion and
fine-tuning use the separate workstation workflow linked above. The Thor
installer selects the FFmpeg 6 shared libraries required by TorchCodec without
requesting the FFmpeg command-line package.

The installable action runtime lives in [`runtime/`](runtime/). It contains
the home-state convergence, two-arm routing, shared-model deployment,
mixed-color pair execution, and scene-reset implementation. Reset restores the
complete action runtime; no separate runtime staging command is required.

Follow the [two-host installation sequence](../../../docs/REPRODUCIBLE-DEMO.md):
prepare Thor's runtime, export and verify your model, install its profiles, then
install the RTX bridge and cell while services are stopped. The bootstrap does
not select a model or generate the shared profiles. Start services only after
both hosts have matching checkpoint metadata and all installation steps pass.

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
First copy and verify your exported checkpoint on Thor, then install its two
shared profiles and target:

```bash
export PGFR_GROOT_MODEL_ROOT="$HOME/policy-gated-factory-robot-orchestrator-reference-models/my-checkpoint"
ops/fetch-groot-models.sh "$PGFR_GROOT_MODEL_ROOT"
ops/install-groot-thor-shared-profiles.sh --checkpoint-path "$PGFR_GROOT_MODEL_ROOT"
```

The Thor profile installer verifies the existing generic policy/relay unit
contract and the model checksum. It refuses active shared units, occupied
ports, stale readiness files, or differing existing profiles. It installs only
`shared-left.env`, `shared-right.env`, and
`pgfr-groot-shared-stack.target`; it never enables or starts them and does not
replace the generic templates used by other profiles.

Copy `pgfr_checkpoint.json` and `SHA256SUMS` together to a local directory on
the simulation host. It then installs the dedicated bridge:

```bash
ops/install-groot-two-host-bridge.sh \
  --thor-ssh user@thor-host \
  --remote-checkpoint /absolute/thor/path/to/my-checkpoint \
  --checkpoint-metadata /absolute/local/path/to/pgfr_checkpoint.json \
  --remote-state-root /absolute/thor/state/root
```

The installer does not enable or start the bridge. After an operator reviews
both host configurations and explicitly starts the Thor shared target and the
simulation-host bridge, the bridge opens four loopback-only SSH forwards.
It publishes a separate local state pair only while both remote units,
listeners, checkpoint identities, fingerprints, and relay contracts are
valid. Tunnel or identity failure removes both local readiness records.

The Isaac installer then consumes the derived left/right state paths, the
bridge's local policy/relay ports, and the same local `--checkpoint-metadata`
file. Its `--checkpoint-path` is the absolute model path on Thor. It does not need network-facing GR00T
listeners, and the existing executor and relay protocol remain unchanged.
For the bridge defaults, render the cell contracts with policy ports
5792/5793, relay ports 5741/5742, and service-state paths beneath
`/groot-state`. Launch with:

```bash
export PGFR_GROOT_STATE_ROOT="$HOME/.local/share/pgfr-spine/groot/remote-thor-v36"
ops/launch-groot-isaac.sh --accept-eula /path/to/isaac-scripts
```

The development lineage remains in
[`groot_n1_7_pgfr_pipeline/`](groot_n1_7_pgfr_pipeline/). It includes:

- synchronized simulation capture and native-DROID conversion;
- the official NVIDIA fine-tuning entry point and single-frame modality;
- an explicit fine-tuning and optional corrective-continuation recipe;
- the dataset and model validation contract.

The direct executor lives in [`runtime/`](runtime/), and the serving bridge
lives in [`relay/`](relay/). Earlier development iterations remain available
through Git history. The public installer does not checksum normal source
files: Git versions and behavioral tests cover source, while the model
artifact checksum validates the user-exported weights at the serving boundary.

## Reproduction status

The source packages the controller and the observation/action contract used in
the development experiment. Both Thor policy instances must load the same
user-exported checkpoint and publish its recorded identity. The bridge checks
that identity before exposing readiness to Isaac Sim.

The [model manifest](models/manifest.yaml) records upstream base/runtime
prerequisites and the local artifact contract. It does not identify a project
checkpoint or dataset to download. Historical mission evidence does not qualify
a model trained from new demonstrations. Each checkpoint needs rollout and
visual-verification acceptance on the matching scene, cameras, and alignment.

See [the two-host setup](../../../docs/REPRODUCIBLE-DEMO.md) and
[release scope](../../../docs/RELEASE-SCOPE.md).
