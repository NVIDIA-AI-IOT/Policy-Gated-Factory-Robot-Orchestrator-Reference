# Create and train your own GR00T policy

This directory provides source tools for collecting simulation demonstrations,
converting them to native DROID format, and fine-tuning the official NVIDIA
GR00T N1.7 DROID base. The public project supplies no task fine-tuned checkpoint
or recorded training dataset. Users create and evaluate their own artifacts.

Run conversion and training in a fresh local workstation environment built
from the pinned upstream source/lockfile. Capture and stock forward kinematics
use the official NVIDIA Isaac Sim image directly, with mounted project source
and explicit operator acceptance of NVIDIA runtime terms. This path builds or
publishes no project container and does not copy an installed Thor environment.
The [training recipe](docs/FINETUNING_RECIPE.md#select-and-check-the-local-cpu-encoder)
checks a user-selected CPU FFmpeg build and records its provenance; training
also requires compatible TorchCodec decoding libraries.

The supplied factory scene and native DROID data format are reference examples.
You can bring your own Isaac Sim scene and custom demonstration dataset to
fine-tune GR00T for your task. Follow the
[custom-scene adaptation guidance](docs/DATASET_CREATION.md#adapt-to-your-own-isaac-sim-scene)
to align capture, training, and runtime with your scene and robot.

1. [Create a dataset](docs/DATASET_CREATION.md): isolated RMPflow expert capture,
   synchronized image/action conversion, stock Isaac forward kinematics, and
   real absolute/relative statistics.
2. [Fine-tune](docs/FINETUNING_RECIPE.md): pinned upstream source and official
   model prerequisites, explicit training arguments, optional continuation,
   and local checkpoint export.
3. [Qualify your result](docs/VALIDATION.md): held-out data, single-arm rollouts,
   two-arm order/accumulation, and the complete orchestration path.

The capture profile and training workflow are implementation tooling. Offline
checks do not establish simulator success, training convergence, RTX memory
requirements, elapsed training time, or the behavior of a newly trained policy.
The earlier development episode counts and checkpoint names are not a promised
public reproduction target.

The [runtime](../runtime/) serves the same user checkpoint in two independent
policy processes, one per Franka arm. Checkpoint export checks integrity and
metadata; it does not certify the checkpoint's actions. See the
[local export procedure](../models/README.md).
