# GR00T N1.7 PGFR pipeline

This pipeline produces the shared Policy-Gated Factory Robot Orchestrator Reference pick-and-place model used by
both Franka arms. The demonstrated checkpoint is **Order744-cont24**:

- **Order744** trains from the vanilla GR00T N1.7 DROID checkpoint with 744
  Policy-Gated Factory Robot Orchestrator Reference episodes.
- **cont24** continues from Order744 with 24 accumulated-scene episodes.
- The resulting checkpoint is loaded by two policy processes, one per arm.
- The integrated action runtime lives in [`../runtime/`](../runtime/).

## Run the published model

The Hugging Face model repository and immutable revision are declared in
[`../models/manifest.yaml`](../models/manifest.yaml). The checkpoint is
public. The fetch script also downloads the gated
`nvidia/Cosmos-Reason2-2B` runtime backbone, so accept its NVIDIA terms and
authenticate with Hugging Face before running:

```bash
export PGFR_GROOT_HF_REPO='mmallick/industrial-claw-groot-order744-cont24'
export PGFR_GROOT_HF_REVISION='9307ac9cba3a27c9a57ed2d90393ceefb28367e1'
export PGFR_GROOT_MODEL_ROOT="$HOME/policy-gated-factory-robot-orchestrator-reference-models/order744-cont24"

ops/fetch-groot-models.sh
```

Start one policy process and one relay for each arm, then install the action
runtime into an idle Isaac scripts mount:

```bash
ops/install-groot-cell.sh \
  --mount /path/to/isaac-scripts \
  --checkpoint-path "$PGFR_GROOT_MODEL_ROOT" \
  --left-service-state /groot-state/shared-left.json \
  --right-service-state /groot-state/shared-right.json

systemctl --user start pgfr-groot-shared-stack.target
ops/launch-groot-isaac.sh /path/to/isaac-scripts
```

The installer restores the complete measured-home, physical-friction, mixed-
color, two-arm runtime on every successful scene reset.

## Fine-tune from the published dataset

The public Hugging Face dataset contains all 744 Order744 episodes and the 24
cont24 episodes. Follow
[`docs/FINETUNING_RECIPE.md`](docs/FINETUNING_RECIPE.md) to:

1. download the pinned dataset revision;
2. train Order744 from vanilla `nvidia/GR00T-N1.7-DROID`;
3. continue from Order744 with the accumulated-scene cohort; and
4. retain the final `checkpoint-3000` training output for publication.

The recipe uses NVIDIA's `examples/finetune.sh` and the included single-frame
DROID modality configuration.

## Create or extend a dataset

Downloading the published dataset is sufficient to reproduce fine-tuning.
These tools are provided for contributors who want to capture or add data:

```text
pipeline/capture/record_pgfr_green_red_blue_staged_synced.py
pipeline/conversion/convert_pgfr_to_lerobot.py
pipeline/conversion/build_native_droid_dataset.py
pipeline/conversion/compute_dual_arm_fk_batch_in_isaac.py
pipeline/training/droid_checkpoint_single_frame_config.py
```

The conversion path produces native-DROID state/action arrays and official
dataset statistics expected by GR00T N1.7.

## Serving contract

Run `gr00t/eval/run_gr00t_server.py` twice with the same checkpoint and DROID
embodiment. Pair each policy process with one
[`../relay/native_droid_relay_batch2.py`](../relay/native_droid_relay_batch2.py)
relay. The installer selects
the four local ports and keeps policy-to-relay traffic loopback-only.

## Validation

[`docs/VALIDATION.md`](docs/VALIDATION.md) records the training identity,
integrated executor contract, and end-to-end result used by this public flow.
