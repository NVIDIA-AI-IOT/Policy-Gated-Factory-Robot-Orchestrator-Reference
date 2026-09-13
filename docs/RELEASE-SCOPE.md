# Public release scope

This release provides the orchestration source, the Isaac Sim reference cell,
and tools and instructions for creating demonstrations and fine-tuning GR00T.
It does not distribute a project fine-tuned checkpoint or a recorded training
dataset, and installation does not depend on developer-hosted artifacts.

The supplied factory cell is a reference implementation you can adapt to your
own Isaac Sim environment, robots, and tasks. You can collect a custom dataset
and fine-tune GR00T for that environment. Follow the
[adaptation guidance](../README.md#adapt-the-reference-to-your-own-scene) to update
the capture pipeline, model inputs/outputs, and scene integration together.
The provided commands and acceptance criteria target the documented reference
configuration; a custom setup requires its own validation.

## Runtime delivery

This is a source-and-instructions release. It does not publish a project-built
Isaac Sim image, a Thor inference image, or a snapshot of the development hosts.
Users pull the pinned Isaac Sim image directly from NVIDIA, accept its terms,
and mount the project's source and generated configuration from the RTX host.
GR00T is installed into the documented native Thor environment from pinned
upstream source, the checked-in lock, and the checksum-verified platform wheel.
The perception VLM and diagnostic tools retain their documented upstream image
pulls; those images are not repackaged by this project.

Dataset capture, conversion, and fine-tuning remain separate local procedures.
The Thor installer requests the versioned FFmpeg 6 decoder libraries needed by
the pinned TorchCodec wheel; it does not request the unversioned FFmpeg command.
The conversion guide selects and checks its own encoder executable.

The Apache source license does not relicense Isaac Sim's Kit components, assets,
models, or other upstream dependencies. Obtain those components under their
applicable terms. See [Isaac Sim licensing](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/common/licenses-isaac-sim.html)
and the [third-party inventory](../THIRD-PARTY-NOTICES.md). Keeping upstream
binaries out of this delivery avoids republishing the observed nonfree FFmpeg
build; it does not establish that the previous internal use violated a license,
or remove the remaining source, asset, dependency, and codec review obligations.

Do not include installed virtual environments, package caches, container
exports, downloaded assets, weights, or recordings in the public artifacts.
Any future redistribution of those binaries is a separate release-scope change.

## User workflow

1. Set up the documented Isaac Sim capture environment.
2. [Create demonstrations](../reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/DATASET_CREATION.md)
   for the selected arms, objects, and scene layout; convert them to native
   DROID and compute and validate the training statistics.
3. [Fine-tune GR00T](../reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md)
   from the pinned NVIDIA base using those local datasets.
4. [Export and verify the local checkpoint](../reference/policy-gated-factory-robot-orchestrator-reference/groot/models/README.md),
   transfer it to Thor, and install both arm profiles against that checkpoint.
5. Run the [deployment acceptance checks](VALIDATION.md) for the new model.

The scripted Isaac Sim baseline in [Installation](../INSTALL.md) is available
without training GR00T. The learned-motion path requires the user's checkpoint.
The AMR tote transport remains scripted in both cases.

## Upstream prerequisites

Official upstream source, base-model identities, model cards, and license/access
instructions remain documented. Users obtain NVIDIA GR00T-N1.7-DROID, the
Cosmos runtime backbone, and the perception VLM under their applicable terms;
the cloud orchestrator uses a user-configured endpoint and credential. This is
fine-tuning an existing model, not training those foundation models from scratch.

The small recorded arm-alignment JSON files under `groot/capture_context` are
runtime reference inputs. Their provenance and the scene's asset terms remain
part of release review. Changing
scene geometry or capture alignment requires new measured context and validation.
Existing source attribution, copyright notices, and applicable upstream licenses
are retained.

## Evidence and limits

Historical mission results describe the development experiment. They do not
establish the accuracy or task success of a user-trained checkpoint. A successful export/checksum check establishes artifact integrity;
acceptance also requires inference, physical rollout, and visual verification.
Dataset creation and training must be qualified on the documented hardware before
claiming a complete fresh-machine reproduction. Training duration and GPU memory
requirements must be measured rather than inferred from serving memory.

This scope document is not a release approval. Source, asset, dependency, and any
future container distribution remain subject to the project's release review.
