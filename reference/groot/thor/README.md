# GR00T on Jetson AGX Thor

The reference serves GR00T policy and relay processes directly on Thor using
the pinned aarch64, Python 3.12, and CUDA 13 environment. This directory provides
the bare-metal installer, dependency declarations, and lock file. It does not
provide a project GR00T container build. The existing upstream CUDA image used
by the host GPU check remains a separate readiness tool.

Dataset capture, conversion, and fine-tuning belong to the workstation workflow
in the [training recipe](../groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md).
Use your own exported checkpoint; this environment does not supply trained
project weights or a training dataset.

## Prepare and install

Follow the [two-host prerequisites](../../../docs/REPRODUCIBLE-DEMO.md) first.
On Thor, from this repository's root, with the GR00T policy and relay services
inactive and a new destination directory:

```bash
ops/prepare-groot-runtime.sh --install
```

This prepares NVIDIA Isaac-GR00T at upstream commit
`e5749287857afd97b78f1147166137de29746392` in
`$HOME/groot_shadow/Isaac-GR00T`. It verifies the SHA-256 of the
[project patch](../patches/isaac-groot-e574-policy-gated-factory-robot-orchestrator-reference.patch),
checks that it applies cleanly, applies it, and checks the resulting source
diff. It also materializes the checksum-verified TorchCodec wheel and invokes
the Thor installer. `PGFR_GROOT_SOURCE_ROOT` can select another preparation
directory, but the shared-profile installer requires the default path above.
Preparation refuses an existing destination or active known profiles and starts
no policy or relay service.

To inspect the prepared source before installing dependencies, use this
alternative sequence instead:

```bash
ops/prepare-groot-runtime.sh --source-only
# Review the prepared source, then install on the idle Thor host:
"${PGFR_GROOT_SOURCE_ROOT:-$HOME/groot_shadow/Isaac-GR00T}/scripts/deployment/thor/install_deps.sh"
```

Do not run `--install` against the directory already created by `--source-only`;
invoke its prepared installer as shown. The installer consumes the Thor
`pyproject.toml` and `uv.lock` in place, performs a frozen sync into the source
checkout's `.venv`, and installs GR00T editable without changing the upstream
root dependency files. Keep the default `.venv` for the shared-profile
installer; it does not support a different `UV_PROJECT_ENVIRONMENT`.

After dependency installation, continue with checkpoint export/verification,
profile installation, and service startup in the
[two-host guide](../../../docs/REPRODUCIBLE-DEMO.md).

The patch covers configuration, fine-tuning, model, evaluation, policy, and
inference-server changes used by training and serving. Apply it through the
preparation script to retain revision and integrity checks. The
[runtime guide](../runtime/README.md) describes the separate Isaac executor and
serving relay; neither reads the patch during a rollout.

## FFmpeg and TorchCodec dependencies

The pinned TorchCodec wheel links these six FFmpeg 6 library packages:

```text
libavfilter9 libavformat60 libavcodec60 libavutil58 libswresample4 libswscale7
```

The installer requests only those ABI-versioned packages with
`--no-install-recommends`; it does not request the unversioned `ffmpeg` command-
line package. Jetson repositories can select an FFmpeg 8 build for that package,
which does not supply the FFmpeg 6 ABI required by this wheel. Some previously
observed NVIDIA FFmpeg builds report nonfree components. Dataset conversion
uses a separately selected executable in the workstation training workflow.
Normal package dependency resolution still applies; `--no-remove` prevents
package removals.

The measured Ubuntu 24.04 FFmpeg 6 packages are GPL builds. The pinned OpenCV
headless wheel also bundles separate LGPL FFmpeg libraries. Their obligations
remain separate from the TorchCodec wheel's BSD license and the project's
source license; see [third-party notices](../../../THIRD-PARTY-NOTICES.md).
Omitting the command-line package does not remove these library dependencies.

You can inspect the selected package versions and origins without running a
model or decoder:

```bash
dpkg-query -W libavfilter9 libavformat60 libavcodec60 libavutil58 libswresample4 libswscale7
apt-cache policy libavfilter9 libavformat60 libavcodec60 libavutil58 libswresample4 libswscale7
```

Omitting TorchCodec or system FFmpeg requires separate cold-start and inference
validation.

## Pins and limits

| File | Purpose |
| --- | --- |
| [install_deps.sh](install_deps.sh) | Checks platform and wheel integrity, installs CUDA/runtime libraries, performs frozen sync, and installs the pinned TorchCodec wheel. |
| [pyproject.toml](pyproject.toml) | Defines the Thor Python dependency set and package indexes. |
| [uv.lock](uv.lock) | Freezes the Python dependency resolution. |

The TorchCodec artifact is `torchcodec-0.10.0a0-cp312-cp312-linux_aarch64.whl`,
SHA-256 `1421de7e6248cc33398c16b2d7ba5ada4bf5c2a38af7cc44a003f3b0c36eb314`.
The installer rejects a Git LFS pointer, invalid archive, unexpected wheel
inventory, or checksum mismatch before package installation. This identifies
the tested artifact; it does not supply a complete reproducible source/build
recipe for the custom wheel. See
[Validation](../../../docs/VALIDATION.md#validation-status) for artifact and
runtime limitations.
