# Fine-tune a user-owned native DROID dataset

Fine-tune the NVIDIA base model on your own inputs from
[DATASET_CREATION.md](DATASET_CREATION.md). The one-GPU settings below are
starting values; training VRAM, time, and convergence have not been measured
on an RTX 6000 Pro with this workflow.

The base checkpoint, launcher, and dataset checks here target the supplied
Franka/native-DROID reference example. To fine-tune on data from your own Isaac
Sim scene or robot, follow the
[custom-scene adaptation guidance](DATASET_CREATION.md#adapt-to-your-own-isaac-sim-scene)
so capture, modality configuration, and runtime use matching contracts.

## Prepare the pinned x86 training environment

Follow the [pinned NVIDIA installation instructions](https://github.com/NVIDIA/Isaac-GR00T/blob/e5749287857afd97b78f1147166137de29746392/README.md#installation)
for the workstation CUDA/driver prerequisites. The upstream x86 default uses
Python 3.10 and CUDA 12.8; the separate Jetson Thor Python 3.12 environment is
for serving and must not be substituted for this workstation setup.
Install Git LFS and uv through your normal system provisioning first. Create a
new training checkout/virtual environment; keep it separate from the recorder
and Thor serving environments. Use the pinned source with the dependency
security patches, then select the CPU FFmpeg executable and compatible
TorchCodec libraries described below.

```bash
export REPO=/absolute/path/Policy-Gated-Factory-Robot-Orchestrator-Reference
export PIPELINE="$REPO/reference/groot/groot_n1_7_pgfr_pipeline"
export ISAAC_GROOT_ROOT="$HOME/pgfr-training/Isaac-GR00T"
GIT_LFS_SKIP_SMUDGE=1 git clone --no-checkout https://github.com/NVIDIA/Isaac-GR00T.git "$ISAAC_GROOT_ROOT"
git -C "$ISAAC_GROOT_ROOT" checkout e5749287857afd97b78f1147166137de29746392
git -C "$ISAAC_GROOT_ROOT" submodule update --init --recursive
git -C "$ISAAC_GROOT_ROOT" apply --check "$REPO/reference/groot/patches/isaac-groot-e574-policy-gated-factory-robot-orchestrator-reference.patch"
git -C "$ISAAC_GROOT_ROOT" apply "$REPO/reference/groot/patches/isaac-groot-e574-policy-gated-factory-robot-orchestrator-reference.patch"
cd "$ISAAC_GROOT_ROOT"
"$REPO/ops/sync-groot-training-deps.sh" --groot-root "$ISAAC_GROOT_ROOT"
export GROOT_PYTHON="$ISAAC_GROOT_ROOT/.venv/bin/python"
"$GROOT_PYTHON" -c 'import gr00t, torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))'
```

The dependency setup verifies the original project files, builds the
[security-patched libraries](../../security/README.md), and applies a pinned
training lock update. Transformers 4.57.3, Accelerate 1.13.0, and the existing
Torch/CUDA baseline are retained; supporting libraries with known High findings
are updated. Later frozen syncs continue to use the patched local wheels.
To prepare and inspect the changes without installing dependencies, add
`--prepare-only`; rerun the same command without it to install.

The public capture conversion does not require upstream demo-data LFS blobs.
Do not use `--skip-weight-loading` for actual training. Confirm the NVIDIA GPU
and dependencies are usable before training.

Record the local setup with your training artifacts. For example:

```bash
export TRAIN_PROVENANCE="$HOME/pgfr-training/provenance"
mkdir -p "$TRAIN_PROVENANCE"
git -C "$REPO" rev-parse HEAD > "$TRAIN_PROVENANCE/pgfr-commit.txt"
git -C "$ISAAC_GROOT_ROOT" rev-parse HEAD > "$TRAIN_PROVENANCE/groot-commit.txt"
git -C "$ISAAC_GROOT_ROOT" diff --binary > "$TRAIN_PROVENANCE/groot-local-changes.patch"
sha256sum "$ISAAC_GROOT_ROOT/uv.lock" > "$TRAIN_PROVENANCE/uv-lock.sha256"
sha256sum "$ISAAC_GROOT_ROOT"/.pgfr-security/wheels/*.whl > "$TRAIN_PROVENANCE/security-wheels.sha256"
uv --version > "$TRAIN_PROVENANCE/uv-version.txt"
"$GROOT_PYTHON" --version > "$TRAIN_PROVENANCE/python-version.txt"
uv pip freeze --python "$GROOT_PYTHON" > "$TRAIN_PROVENANCE/python-packages.txt"
nvidia-smi > "$TRAIN_PROVENANCE/nvidia-smi.txt"
```

Keep any local PGFR source changes, the original lockfile, installed wheel
hashes/source references, OS release and native-package versions with these
records. A package list alone does not identify every wheel or native library.
Keep credentials out of provenance records; review local patches and package
URLs before sharing them.

## Select and check the local CPU encoder

Use an FFmpeg build whose package/source and license you have reviewed. A
normal distribution CPU build with GPL/libx264 support can satisfy conversion;
GPL is allowed in this local workflow. The selected reproduction profile
rejects FFmpeg builds reporting `--enable-nonfree` or a nonfree/unredistributable
license. This choice does not assert that private use of such a build is
prohibited. Review [FFmpeg's licensing guidance](https://ffmpeg.org/legal.html)
for any intended redistribution.

On a fresh Ubuntu 24.04 x86 training host, inspect the package candidate first:

```bash
sudo apt-get update
apt-cache policy ffmpeg
```

Proceed with the command below only when the candidate comes from the Ubuntu
repositories. If it points to a Jetson/NVIDIA FFmpeg repository or another
unreviewed source, select a compatible CPU build in a separate local training
environment instead. This is not an instruction to replace the live Thor setup.

```bash
sudo apt-get install --no-remove --no-install-recommends ffmpeg

dpkg-query -W ffmpeg > "$TRAIN_PROVENANCE/ffmpeg-package.txt"
apt-cache policy ffmpeg > "$TRAIN_PROVENANCE/ffmpeg-package-origin.txt"
```

This installs the Ubuntu executable and its shared-library dependencies. Record
the resolved versions; the Python lock does not pin OS packages. Confirm encoding
and TorchCodec decoding with the checks below before using the environment.

Select the exact executable, then run the preflight. `/usr/bin/ffmpeg` below
is an example path, not an assumption that the installed build is suitable:

```bash
export PGFR_FFMPEG_BIN=/usr/bin/ffmpeg
"$GROOT_PYTHON" "$PIPELINE/pipeline/conversion/ffmpeg_contract.py" \
  --ffmpeg "$PGFR_FFMPEG_BIN" > "$TRAIN_PROVENANCE/ffmpeg.json"
"$PGFR_FFMPEG_BIN" -hide_banner -encoders > "$TRAIN_PROVENANCE/ffmpeg-encoders.txt" 2>&1
"$PGFR_FFMPEG_BIN" -hide_banner -decoders > "$TRAIN_PROVENANCE/ffmpeg-decoders.txt" 2>&1
```

The encoder/decoder lists record the capabilities compiled into this exact
executable for codec review. They do not show which codecs a training run used
or describe the separate libraries loaded by TorchCodec.

The check inspects the reported build/license and performs a tiny CPU RGB
scale → libx264/yuv420p → MP4 encode through pipes. It writes no dataset files.
Missing executables, unidentified build/license reports, reported nonfree
builds, and missing encoder/filter/muxer support stop conversion with an error.
The converter accepts `--ffmpeg /absolute/path/to/ffmpeg`; otherwise it uses
`PGFR_FFMPEG_BIN`, then `ffmpeg` from `PATH`, and applies the same checks.
Retain the returned executable SHA-256 and reports; the converter stores them
in `meta/ffmpeg_provenance.json` and the native builder preserves that file.

This executable check is separate from TorchCodec's native-library needs.
Provision shared FFmpeg libraries compatible with the TorchCodec wheel in the
pinned upstream lockfile and record their exact packages/source references.
The exact x86 native-library installation has not been qualified by this
release; the custom Thor wheel's FFmpeg ABI does not establish x86 compatibility.
Run an import check in this environment, then the
[real converted-video decode check](DATASET_CREATION.md#check-decoding-in-the-actual-training-environment)
before statistics or training:

```bash
"$GROOT_PYTHON" -c 'import torchcodec; from torchcodec.decoders import VideoDecoder; print(torchcodec.__version__)'
```

The executable hash does not cover shared `libav*` dependencies. Do not copy
an installed Jetson environment or its custom ARM64 TorchCodec wheel into
this x86 training setup. An import check, a CPU encode check, and a one-frame
decode check each cover a different prerequisite; none measures model quality.

## Obtain official NVIDIA prerequisites

Use a dedicated Hugging Face cache for this pinned training run, then accept
the applicable model terms, including the gated
[NVIDIA Cosmos-Reason2-2B model](https://huggingface.co/nvidia/Cosmos-Reason2-2B),
and authenticate to Hugging Face if required. Keep tokens out of source, shell
scripts, run manifests, and published logs. The base model is
[NVIDIA GR00T-N1.7-DROID](https://huggingface.co/nvidia/GR00T-N1.7-DROID).
Code licensing and the NVIDIA model licenses are separate requirements.

```bash
export HF_HOME="$HOME/pgfr-training/hf-cache"
"$ISAAC_GROOT_ROOT/.venv/bin/hf" auth login
export GROOT_DROID_BASE="$HOME/pgfr-training/models/groot-n1.7-droid"
"$ISAAC_GROOT_ROOT/.venv/bin/hf" download nvidia/GR00T-N1.7-DROID \
  --revision 05e7cc97e40dbd33b0890c35cc0214fcb0547ab5 \
  --local-dir "$GROOT_DROID_BASE"
"$GROOT_PYTHON" - <<'PIN_BACKBONE'
from pathlib import Path
from huggingface_hub import snapshot_download
revision = "9ce19a195e423419c349abfc86fd07178b230561"
snapshot = Path(snapshot_download("nvidia/Cosmos-Reason2-2B", revision=revision))
# Pinned GR00T loads this model ID without a revision argument. Bind its
# offline default ref explicitly; downloading a commit alone does not do so.
ref = snapshot.parent.parent / "refs" / "main"
ref.parent.mkdir(parents=True, exist_ok=True)
ref.write_text(revision)
print("Pinned backbone:", snapshot)
PIN_BACKBONE
```

The backbone remains in this dedicated cache because pinned GR00T loads it by
its official model ID without a revision argument. The snippet binds that
repository's default cache ref to the downloaded commit; a commit-only download
does not create `refs/main` on a clean cache. Keep the same `HF_HOME` and set
`HF_HUB_OFFLINE=1` for training so it cannot replace the pinned ref. Preserve
upstream NVIDIA notices and model attribution in any permitted derived release.

## Check inputs and train

For each native training root, first run the real statistics command in the
[creation guide](DATASET_CREATION.md#generate-real-statistics-before-training).
The launcher rejects missing or non-finite statistics, incorrect dimensions,
missing or empty video/parquet files, and nonempty output directories. It cannot
detect arbitrary placeholder values; compute statistics from your training data.

```bash
export TRAIN_DATA="$HOME/pgfr-user-data/native/left-layout3-green-red-blue-green"
export TRAIN_OUTPUT="$HOME/pgfr-training/outputs/my-policy"
export HF_HUB_OFFLINE=1
"$GROOT_PYTHON" "$PIPELINE/pipeline/training/launch_finetune.py" \
  --groot-root "$ISAAC_GROOT_ROOT" --base-model "$GROOT_DROID_BASE" \
  --dataset "$TRAIN_DATA" --output-dir "$TRAIN_OUTPUT" \
  --max-steps 3000 --learning-rate 1e-4 \
  --batch-size 16 --dry-run
```

Add `--dataset /absolute/path/to/another/native/root` once per additional
training cohort, including both arms, every color and required accumulated
context. The single green cohort above is only a syntax example. Run the same
command without `--dry-run` only when the printed command and dataset inventory
are correct.
The launcher calls `gr00t/experiment/launch_finetune.py` directly with one GPU,
explicit step/batch/LR/checkpoint arguments, and the provided modality config.
It records the command and inputs in `pgfr_training_run.json`.

The example fine-tunes the action model and projector while leaving the LLM and
visual backbone frozen (plus pinned patched defaults for VLLN). It is not a
LoRA recipe or full tuning of every backbone weight. The single-frame DROID
configuration preserves the base checkpoint's `[0]` image history, 40-step
action horizon, relative EEF/joint actions, and absolute gripper actions.

Checkpoint output is `$TRAIN_OUTPUT/checkpoint-3000` for this example. The
launcher leaves the upstream experiment-name option unset, so the output
directory basename supplies the run label without an extra subdirectory.
Check the trainer's actual final step and files before export. Loss alone does
not establish closed-loop grasp/release success.

## Optional continuation on your own corrective data

Collect new, accepted corrective examples in separate roots, preserve held-out
partitions, and compute their statistics. Initialize from **your own** first
training output and use a new output directory:

```bash
"$GROOT_PYTHON" "$PIPELINE/pipeline/training/launch_finetune.py" \
  --groot-root "$ISAAC_GROOT_ROOT" \
  --base-model "$TRAIN_OUTPUT/checkpoint-3000" \
  --dataset "$TRAIN_DATA" \
  --dataset /absolute/path/to/your/corrective/native-root \
  --output-dir "$HOME/pgfr-training/outputs/my-policy-continuation" \
  --max-steps 3000 --learning-rate 1e-5 --batch-size 16 --dry-run
```

Inspect and then remove `--dry-run` to train. Here `--learning-rate 1e-5` is
passed as an actual upstream argument. The pinned upstream
[`examples/finetune.sh`](https://github.com/NVIDIA/Isaac-GR00T/blob/e5749287857afd97b78f1147166137de29746392/examples/finetune.sh)
hardcodes `--learning_rate 1e-4`; setting an environment variable named
`LEARNING_RATE` does not override it. The wrapper also sets checkpoint retention
explicitly.

The launcher saves model-only checkpoints. Continuation initializes new
optimizer/scheduler state from saved weights; it is **not** an exact resume of
optimizer, scheduler, or RNG state. Choose step counts and LR using held-out
validation.

## Export and qualify

Use the [local export procedure](../../models/README.md). From the repo root:

```bash
python3 "$REPO/ops/export-groot-checkpoint.py" \
  --checkpoint "$TRAIN_OUTPUT/checkpoint-3000" \
  --output-dir "$HOME/pgfr-training/export/my-policy" \
  --model-label my-policy --dataset-path "$TRAIN_DATA"
```

Retain the full training inventory and provenance when multiple dataset roots
were used; the export's dataset-path field is a selected local reference, not
a replacement for the run manifest. Export packages the checkpoint config,
processor/statistics, model tensors, metadata and SHA-256 inventory. It does not
upload, deploy, or validate the policy's physical behavior. Complete
[VALIDATION.md](VALIDATION.md) before deployment.
