# Public release scope

This release provides the orchestration source, the Isaac Sim reference cell,
and tools and instructions for creating demonstrations and fine-tuning GR00T.
It does not distribute a project fine-tuned checkpoint or a recorded training
dataset, and installation does not depend on developer-hosted artifacts.

For a custom scene, follow the [adaptation guidance](../README.md#adapt-the-reference-to-your-own-scene)
and validate the capture pipeline, model, and scene integration together.

## Runtime delivery

Users pull the pinned Isaac Sim image directly from NVIDIA, accept its terms,
and mount the project's source and generated configuration from the RTX host.
GR00T is installed into the documented native Thor environment from pinned
upstream source, the checked-in lock, and the checksum-verified platform wheel.
The perception VLM and diagnostic tools retain their documented upstream image
pulls. The project does not redistribute these images, build a Thor inference
image, or distribute a snapshot of the development hosts.

Dataset capture, conversion, and fine-tuning remain separate local procedures.
The Thor installer requests the versioned FFmpeg 6 decoder libraries needed by
the pinned TorchCodec wheel; it does not request the unversioned FFmpeg command.
The conversion guide selects and checks its own encoder executable.

The Apache source license does not relicense Isaac Sim's Kit components, assets,
models, or other upstream dependencies. Obtain those components under their
applicable terms. See [Isaac Sim licensing](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/common/licenses-isaac-sim.html)
and the [third-party inventory](../THIRD-PARTY-NOTICES.md). Source, asset,
dependency, and codec review remains required for release.

Do not include installed virtual environments, package caches, container
exports, downloaded assets, weights, or recorded training datasets in the public
artifacts. Documentation screenshots and the demo video/GIF are listed in the
[asset inventory](ASSET-PROVENANCE.md); other runtime recordings are excluded.
Any future redistribution of excluded artifacts is a separate release-scope change.

## User workflow

[Installation](../INSTALL.md) links the dataset-creation, fine-tuning, checkpoint
export, and deployment procedures in order. The scripted baseline requires no
GR00T training; the learned-motion deployment requires your checkpoint. AMR
tote transport is scripted in both profiles.

## Upstream prerequisites

Obtain NVIDIA GR00T-N1.7-DROID, the Cosmos runtime backbone, and the perception
VLM under their applicable terms. Configure the orchestration model endpoint
and credential using the [provider guide](MODEL-PROVIDERS.md). The training
recipe fine-tunes GR00T from the documented upstream base.

The recorded arm-alignment JSON files under
[`groot/capture_context`](../reference/policy-gated-factory-robot-orchestrator-reference/groot/capture_context/)
are runtime inputs. Changing the scene or capture alignment requires new
measured context and validation. Their provenance and the scene asset terms
remain part of release review.

## Evidence and limits

A new checkpoint must pass inference, rollout, and visual verification checks;
export checksums alone do not establish task success. Historical results apply
only to their recorded configuration. Dataset creation and training still need
validation on the documented hardware, including measured training time and
GPU memory use. See [test evidence and open items](SUPPORT.md).

Publication remains subject to the project's release review.
