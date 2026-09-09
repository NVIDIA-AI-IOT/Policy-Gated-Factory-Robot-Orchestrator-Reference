---
library_name: gr00t
license: other
license_name: nvidia-open-model-license
license_link: https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
base_model: nvidia/GR00T-N1.7-DROID
tags:
  - robotics
  - vision-language-action
  - gr00t
  - droid
---

# Policy-Gated Factory Robot Orchestrator Reference Order744-cont24

This repository publishes the shared GR00T N1.7 DROID checkpoint used by the
Policy-Gated Factory Robot Orchestrator Reference Isaac Sim demonstration. One checkpoint handles the red cube,
blue cylinder, and green brick for both Franka arms.

The checkpoint is loaded by two policy processes, one for each arm. These are
two serving instances of the same model, not separate arm or object experts.

## Artifacts

- [Fine-tuned Order744-cont24 checkpoint](https://huggingface.co/mmallick/industrial-claw-groot-order744-cont24)
- [768-episode native-DROID dataset](https://huggingface.co/datasets/mmallick/industrial-claw-groot-order744-cont24-dataset)

Both repositories are public artifacts and can be downloaded without
repository-specific access. Model weights and dataset payloads are hosted on
Hugging Face; this Git repository contains their manifest, setup, training,
and runtime source. Immutable revisions are recorded in
[`manifest.yaml`](manifest.yaml).

The dataset is licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and publishes its
dataset card, license text, and attribution notice at the immutable revision
recorded in the manifest.

## Training data

Order744 was trained from vanilla `nvidia/GR00T-N1.7-DROID` with 744
Policy-Gated Factory Robot Orchestrator Reference native-DROID episodes. The cont24 continuation adds 24
accumulated-scene episodes. The companion Hugging Face dataset contains both
cohorts and can be used with the public fine-tuning recipe.

## Artifact layout

```text
config.json
embodiment_id.json
model-00001-of-00003.safetensors
model-00002-of-00003.safetensors
model-00003-of-00003.safetensors
model.safetensors.index.json
processor_config.json
statistics.json
SHA256SUMS
```

`SHA256SUMS` covers only the published model artifacts. Source code is pinned
by the Policy-Gated Factory Robot Orchestrator Reference Git revision and tested through the public runtime
suite.

The NVIDIA trainer writes the final local output under `checkpoint-3000`.
That training-directory name is not reproduced in the published model
repository: the inference artifacts are stored directly at its root.

The model uses the DROID relative-action embodiment and the integrated
Policy-Gated Factory Robot Orchestrator Reference measured-home, physical-friction, mixed-color runtime.

This checkpoint is a simulation research/demo artifact. It is not a
functional-safety component and must not directly control physical equipment
without independent, use-case-specific validation and safety controls.
