# Bring your own GR00T checkpoint

This reference ships source and runtime contracts. To enable the GR00T path,
record your own demonstrations, prepare native-DROID data, and fine-tune the
pinned official `nvidia/GR00T-N1.7-DROID` base model using the
[training pipeline](../groot_n1_7_pgfr_pipeline/README.md).
No fine-tuned checkpoint or demonstration dataset is supplied by this repository.

One exported checkpoint is loaded by two policy processes, one per Franka arm.
Artifact verification checks consistency and binds serving state to those bytes;
it does not establish task success. Evaluate your trained model in the simulator
before relying on it.

## Export on the training host

After training has finished, export the final local `checkpoint-N` directory to
a fresh directory. Run from the repository root on the training RTX host:

```bash
python3 ops/export-groot-checkpoint.py \
  --checkpoint /absolute/training-output/my-run/checkpoint-3000 \
  --output-dir /absolute/model-exports/my-checkpoint \
  --model-label my-checkpoint \
  --dataset-path /absolute/my-native-droid-data
ops/verify-groot-models.sh /absolute/model-exports/my-checkpoint
```

Use the actual checkpoint step and paths from your training run. The checkpoint
and dataset directories must exist when exporting; the dataset path is recorded
as provenance, and its payload is not copied. Exporting does not publish files
or modify the training checkpoint. Existing output directories are refused.

The export contains these required metadata files and either supported weight
layout; shard counts are taken from the trainer's index:

```text
config.json
embodiment_id.json
processor_config.json
statistics.json
model.safetensors                          # unsharded, or:
model.safetensors.index.json + its shards   # sharded
pgfr_checkpoint.json
SHA256SUMS
```

`pgfr_checkpoint.json` records schema version 1, your model label, the DROID
embodiment tag, training checkpoint/dataset provenance, and the complete
inference file list. `SHA256SUMS` covers every inference file and
`pgfr_checkpoint.json`. The serving fingerprint is the SHA-256 digest of the
`SHA256SUMS` bytes; it is derived, never embedded in those metadata files.
The verifier rejects missing files, omitted checksums, changed bytes, unsafe
paths, symlinks, mismatched shard indexes, and extra files in the export.
Checksums are not a signature or evidence of model performance.

## Transfer and install on Thor

Copy the **entire export** to a fresh directory on Thor. Substitute your own
user, host, and destination; this command is illustrative:

```bash
rsync -a /absolute/model-exports/my-checkpoint/ \
  user@thor-host:/home/user/policy-gated-factory-robot-orchestrator-reference-models/my-checkpoint/
```

On Thor, from the repository root:

```bash
export PGFR_GROOT_MODEL_ROOT="$HOME/policy-gated-factory-robot-orchestrator-reference-models/my-checkpoint"
ops/verify-groot-models.sh "$PGFR_GROOT_MODEL_ROOT"
ops/fetch-groot-models.sh "$PGFR_GROOT_MODEL_ROOT"
ops/install-groot-thor-shared-profiles.sh --checkpoint-path "$PGFR_GROOT_MODEL_ROOT"
```

Prepare the Thor runtime and generic service templates first as described in
the [deployment guide](../../../../docs/REPRODUCIBLE-DEMO.md).
`fetch-groot-models.sh` downloads only the pinned official
`nvidia/Cosmos-Reason2-2B` runtime backbone. Accept NVIDIA's applicable model terms
and authenticate the runtime user first. Its cache defaults to `hf-home` beside
the checkpoint directory; set the same `PGFR_HF_HOME` for fetching and profile
installation to use another location. Checkpoint verification and installation
require an explicit local export and stop when it is missing.

The installer writes profiles without enabling or starting services. It refuses
to replace an active stack or differing installed profiles. Every policy start
rechecks artifact bytes against the fingerprint installed in its profile.
Use a new export and explicitly retire the old idle configuration when changing
checkpoints; do not edit an export beneath a running server.

## Identity files for the simulation host

The RTX simulation host needs the exact `pgfr_checkpoint.json` and `SHA256SUMS`
from the export served on Thor. If training happened on that RTX host, retain
the original export there. Otherwise copy only those two files into a local
identity directory, preserving their bytes and names:

```bash
mkdir -p "$HOME/checkpoint-identities/my-checkpoint"
scp user@thor-host:/home/user/policy-gated-factory-robot-orchestrator-reference-models/my-checkpoint/pgfr_checkpoint.json \
  user@thor-host:/home/user/policy-gated-factory-robot-orchestrator-reference-models/my-checkpoint/SHA256SUMS \
  "$HOME/checkpoint-identities/my-checkpoint/"
```

Pass `--checkpoint-metadata "$HOME/checkpoint-identities/my-checkpoint/pgfr_checkpoint.json"`
to the two-host bridge/cell installer and contract renderer. The checkpoint path
in the contract remains the absolute **Thor** export path. Metadata-only checks
verify the metadata checksum and complete declared checksum inventory; Thor
performs full weight verification. The model label and fingerprint must match
across exported metadata, installed profiles, relay state, and simulator
contracts before readiness succeeds.
