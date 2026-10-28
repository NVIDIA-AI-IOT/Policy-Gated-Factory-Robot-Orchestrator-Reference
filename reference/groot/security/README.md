# GR00T dependency security patches

These patches retain the GR00T dependency API versions used by each platform.
The `+pgfr.security1` suffix identifies the local modifications; it is not an
upstream release or a claim of scanner clearance.

| Profile | Transformers | Accelerate |
| --- | --- | --- |
| Thor serving | 4.57.6+pgfr.security1 | 1.12.0+pgfr.security1 |
| Workstation training | 4.57.3+pgfr.security1 | 1.13.0+pgfr.security1 |

## Changes

| Finding | Change |
| --- | --- |
| CVE-2026-1839 | Require safe Torch loading explicitly when restoring trainer RNG state. |
| CVE-2026-4372 | Reject hidden attention configuration from model files and restrict implicit Hub kernel loading. |
| CVE-2026-5241 | Prevent LightGlue configuration from enabling nested remote-code loading. |
| CVE-2026-9856 | Keep saved chat-template files inside their intended directory. |
| CVE-2025-14921 | Disable deprecated Transformer-XL raw-pickle vocabulary and corpus loading, including explicit opt-in. Plain-text vocabulary and safe Torch cache loading remain supported. |
| CVE-2026-69112 | Validate Accelerate checkpoint shard paths and file types before loading. Standard Hugging Face cache links, including subfolders, remain supported. |

The Transformer-XL restriction and Accelerate shard checks are downstream
changes. The other fixes are adapted from upstream commits recorded in
[the modification notice](notices/transformers.txt). Qwen model code, robot
control, model weights, and CUDA dependencies are unchanged by these patches.

## Dependency removal and release artifacts

The Thor and training locks use W&B 0.30.0, which no longer depends on
GitPython. GitPython, gitdb, and smmap are removed from both environments;
GR00T's experiment logging remains supported. The logging regression exercises
W&B and the Transformers callback in offline mode. Operators using a
self-hosted W&B server need version 0.70.0 or later.

The seven legacy Transformers conversion advisories (six High and one Medium)
are reviewed in
[`legacy-advisories.json`](legacy-advisories.json). Their checkpoint-conversion
scripts are absent from the pinned release wheels. This is an artifact-specific
applicability assessment, not a claim that every Transformers installation is
unaffected. Four advisory-to-script mappings are inferred from upstream source;
the evidence records those limits. Regression tests check that the relevant
scripts and unsafe conversion functions remain absent from the installed packages.

The ROS camera service and dataset recorder select Pillow 13.0.0 explicitly,
so their installation does not rely on an older system copy.

## Torch loading policy

The GR00T policy service and both training launchers set
`TORCH_FORCE_WEIGHTS_ONLY_LOAD=1`. This uses
[Torch's supported loading control](https://docs.pytorch.org/docs/2.10/notes/serialization.html#environment-variables)
to reject unsafe pickle deserialization, including the `.pt2` loading paths
reported in CVE-2026-4538. Tensor checkpoints and the patched Trainer RNG restore
remain supported. Checkpoints that require arbitrary Python objects are rejected.

This is a process-level mitigation; it does not patch Torch or change its CUDA
ABI. Direct upstream commands outside these launchers must set the same variable.
The current Torch runtimes are retained for GR00T/CUDA compatibility. The
[application applicability review](torch-advisories.json) records the separate
quantized-Sigmoid issue (CVE-2025-2149) and native profiler issue (CVE-2025-2148).
Both remain affected library behaviors; their triggers were not identified in
the supported application inputs. This assessment requires release/security
review and does not claim a package fix or scanner clearance.

## Installation and verification

The Thor preparation and installation scripts build the wheels automatically.
Use `ops/sync-groot-training-deps.sh` for the workstation training environment.
Both paths pin the generated wheels in their dependency locks, including
SHA-256 hashes; later frozen syncs retain the patched packages.

To build or verify the Thor artifacts without installing dependencies:

```bash
python3 reference/groot/security/build_security_wheels.py \
  --manifest reference/groot/security/manifest.json \
  --output-dir reference/groot/thor/wheels/security
python3 reference/groot/security/build_security_wheels.py \
  --manifest reference/groot/security/manifest.json \
  --output-dir reference/groot/thor/wheels/security --check
```

For training artifacts, select `manifest-training.json` and a separate output
directory. `--upstream-dir` reads previously downloaded upstream wheels for an
offline build. The builder checks upstream archives, patch bytes, exact source
before and after patching, notices, and final wheel hashes. It retains upstream
licenses and adds modification notices. Generated wheels are not tracked or
published by this repository.

CI exercises malicious inputs, normal checkpoint loading and offloading, and a
tiny Qwen3-VL image/text model on CPU. These checks do not replace full GR00T
checkpoint and GPU qualification. Keep checkpoint/cache directories protected
from concurrent untrusted writes; the path checks are not a filesystem sandbox.
Version-based scanners may require the patch evidence when evaluating these
local versions. The source patches, removed dependencies, and artifact applicability evidence
need to be reflected in the release scan; a passing CI run does not clear a
scanner finding automatically.
