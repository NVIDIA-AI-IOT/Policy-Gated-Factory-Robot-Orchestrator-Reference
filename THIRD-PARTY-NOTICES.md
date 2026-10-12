# Third-party notices

This document inventories third-party software and externally retrieved
artifacts used by this repository's reference implementation. It is a
release-review aid, not a substitute for the license files shipped by each
dependency and not a statement that NVIDIA OSRB or artifact review is
complete.

## Scope and interpretation

- **Repository content** is source or documentation distributed in this Git
  repository.
- **Runtime retrieval** is software, models, containers, system packages, or
  Isaac assets downloaded by an operator. Listing it here does not mean its
  binary payload is redistributed by this repository.
- **Redistributed binaries** require their own license, notice, export, codec,
  and security review. In particular, packaged NumPy/SciPy native libraries
  and FFmpeg native libraries remain explicit review items. The FFmpeg builds
  used or found on the development hosts are identified below; source-only
  distribution does not remove the need to review their use.
- <code>AND</code> and <code>OR</code> retain their normal SPDX meanings.
  Where an upstream lockfile offered a choice and this distribution selected
  one branch, that selection is stated explicitly.

The dependency tables are derived from the committed
<code>package-lock.json</code> and six committed <code>uv.lock</code> files.
Package links are the attribution and license-detail entry points; installed
distributions remain authoritative for complete copyright and license text.

## Distribution scope

Project fine-tuned weights and full recorded training datasets are not supplied
or retrieved by the public installation path. Users create demonstrations and
train their own checkpoints; see `INSTALL.md` in the source repository.

The tracked arm-alignment state files remain reference runtime inputs; their
provenance and applicable scene asset terms remain part of release review.
Their inclusion does not establish new distribution rights.

No container image, OS package, model weight, dataset payload, FFmpeg binary,
or remote Isaac asset binary is embedded in this source-tree inventory unless
a separately listed tracked file says otherwise.

The architecture diagram, screenshots, and project video are listed in
`docs/ASSET-PROVENANCE.md` in the source repository. Other runtime recordings,
installed virtual environments, package caches, and container exports are
excluded from public artifacts. Redistribution of excluded artifacts requires
a separate release review. Source, dependency, asset, and codec review remains
required for release.

## Included upstream licenses

The following full license texts accompany source material copied or modified
in this repository. Paths are relative to the source repository. Package
dependencies retrieved during installation retain the licenses and notices
in their own distributions; the inventory below also lists their terms.

| Source material | Included full license | Attribution and modification records |
|---|---|---|
| Isaac-GR00T integration patches and platform configuration | `reference/groot/LICENSE.NVIDIA-ISAAC-GROOT` (Apache-2.0) | Pinned revision and patch paths in `reference/groot/README.md` and `deploy/reproducible-demo.yaml`; retain upstream file headers when applying patches |
| Hugging Face Transformers patches | `reference/groot/security/licenses/transformers-LICENSE` (Apache-2.0) | `reference/groot/security/notices/transformers.txt` and `transformers-training.txt` |
| Hugging Face Accelerate patches | `reference/groot/security/licenses/accelerate-LICENSE` (Apache-2.0) | `reference/groot/security/notices/accelerate.txt` and `accelerate-training.txt` |

The security wheel builder retains the upstream wheel's license files and
adds the corresponding modification notice. These upstream notices must not
be replaced by a NVIDIA-only copyright header.

## Upstream source and model prerequisites

| Component | Immutable identity | Terms | Distribution role |
|---|---|---|---|
| [NVIDIA Isaac-GR00T](https://github.com/NVIDIA/Isaac-GR00T) | <code>e5749287857afd97b78f1147166137de29746392</code> | Apache-2.0; repository copy: <code>reference/groot/LICENSE.NVIDIA-ISAAC-GROOT</code> | Upstream source patched by this repository |
| [NVIDIA GR00T-N1.7-DROID](https://huggingface.co/nvidia/GR00T-N1.7-DROID) | <code>05e7cc97e40dbd33b0890c35cc0214fcb0547ab5</code> | NVIDIA Open Model License | Base checkpoint lineage |
| [NVIDIA Cosmos-Reason2-2B](https://huggingface.co/nvidia/Cosmos-Reason2-2B) | <code>9ce19a195e423419c349abfc86fd07178b230561</code> | NVIDIA Open Model License | GR00T runtime backbone retrieved at runtime |
| [Qwen3-VL-2B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct) | Upstream identity declared by Cosmos model card | Apache-2.0 | Nested Cosmos base-model attribution |
| [NVIDIA Nemotron Nano 12B VL NVFP4](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-NVFP4-QAD) | <code>312eb94f6d36209f7c6a82eda896e27200d152ee</code> | NVIDIA Open Model License | VLM retrieved at runtime |

The GR00T bundle includes a Policy-Gated Factory Robot Orchestrator Reference patch against the pinned
Isaac-GR00T source. The patch identifies modified upstream files; the
Policy-Gated Factory Robot Orchestrator Reference relay, executor, scene, service, and orchestration code is
separately authored integration code.

## Modified Transformers and Accelerate dependencies

The source patches under `reference/groot/security/` modify Apache-2.0-licensed
Hugging Face Transformers and Accelerate. Their upstream licenses and
modification notices are retained in that directory and in generated wheels.
The builder verifies exact upstream wheel, patch, modified-file, and output
hashes recorded in `manifest.json` and `manifest-training.json`.

Thor uses Transformers `4.57.6+pgfr.security1` and Accelerate
`1.12.0+pgfr.security1`; workstation training uses `4.57.3+pgfr.security1` and
`1.13.0+pgfr.security1`, respectively. These are locally patched distributions,
not upstream releases. Operators build them during setup; this repository and
its CI do not publish the generated wheels. Patch scope and provenance are
recorded in `reference/groot/security/README.md` and the modification notices.
The training setup applies a separate patch to the pinned upstream training
lock; the inventory below lists the six standalone lockfiles in this repository.

## Containers, system packages, codecs, and remote assets

| Runtime item | Pinned or declared identity | Terms / review status |
|---|---|---|
| NVIDIA Isaac Sim container (historical GR00T/X11 path) | <code>nvcr.io/nvidia/isaac-sim:6.0.0-dev2@sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9</code> | NVIDIA Isaac Sim/container terms; runtime retrieval only |
| NVIDIA Isaac Sim container (stable scripted baseline) | <code>nvcr.io/nvidia/isaac-sim:6.0.1@sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb</code> (linux/amd64) | NVIDIA Isaac Sim/container terms; runtime retrieval only |
| ROS 2 Jazzy acceptance sidecar | <code>docker.io/library/ros:jazzy-ros-base-noble@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4</code> (linux/amd64) | ROS 2 and Ubuntu package terms; runtime retrieval only; retain package-provided notices |
| vLLM OpenAI-compatible container | <code>vllm/vllm-openai:v0.20.0-ubuntu2404@sha256:aff65d7198dd284c37dd0a18a606544cc5e92bfb0d5eb608b77e8b8f1c6b8b0d</code> | [Apache-2.0](https://github.com/vllm-project/vllm/blob/main/LICENSE); runtime retrieval only |
| Upstream Thor CUDA GPU-check image | <code>nvidia/cuda:13.0.0-devel-ubuntu24.04@sha256:1e8ac7a54c184a1af8ef2167f28fa98281892a835c981ebcddb1fad04bdd452d</code> (linux/arm64 child <code>sha256:38c2598ded0fd3ed2b0b13351543fde493faba43ae580f81f0a9ab58d76fdd2d</code>) | [NVIDIA CUDA Toolkit EULA](https://docs.nvidia.com/cuda/eula/index.html); operator-retrieved GPU diagnostic only; no project Thor image is built or distributed |
| Brain-host packages | <code>ca-certificates</code>, <code>curl</code>, <code>git-lfs</code>, <code>gnupg</code>, Node.js 22.22.3, ROS 2 Jazzy base/Fast DDS, CUDA 13 CUPTI/math runtimes | Retrieved from Ubuntu, NodeSource, ROS, and NVIDIA package repositories; retain package-provided copyright/license files |
| Thor GR00T system packages | NVPL BLAS/LAPACK, CUDA development/runtime packages, FFmpeg 6 compatibility runtimes, Git LFS | Native host installation from upstream; does not request the unversioned FFmpeg CLI package; retain package-provided copyright/license files and NVIDIA SDK terms where applicable |
| TorchCodec Thor runtime artifact | <code>torchcodec-0.10.0a0-cp312-cp312-linux_aarch64.whl</code>, SHA-256 <code>1421de7e6248cc33398c16b2d7ba5ada4bf5c2a38af7cc44a003f3b0c36eb314</code> | [BSD-3-Clause](https://github.com/meta-pytorch/torchcodec/blob/main/LICENSE); Git LFS path <code>scripts/deployment/thor/wheels/</code> at pinned Isaac-GR00T revision <code>e5749287857afd97b78f1147166137de29746392</code>; installed only as an explicit post-sync overlay |
| Observed Thor FFmpeg executable | NVIDIA APT <code>7:8.0.1-nvidia</code>, arm64; <code>https://repo.download.nvidia.com/jetson/ffmpeg</code>, <code>r39.2/main</code> | FFmpeg 8 with GPL, nonfree, and libx264 enabled; reports nonfree/unredistributable. Installed on the development/test host, not committed to this repository or requested by its current Thor installer. See the build evidence below and [FFmpeg licensing](https://ffmpeg.org/doxygen/trunk/md_LICENSE.html). |
| Thor FFmpeg 6 decoder libraries | Observed Ubuntu <code>7:6.1.1-3ubuntu5</code>: <code>libavcodec60</code>, <code>libavformat60</code>, <code>libavutil58</code>, <code>libavfilter9</code>, <code>libswscale7</code>, <code>libswresample4</code> | Identified as GPL-2.0-or-later; retrieved by the user for the pinned TorchCodec native adapters. Separate from the observed FFmpeg 8 executable. Retain upstream notices; any binary redistribution requires corresponding-source and linkage review. |
| OpenCV bundled video libraries | PyPI <code>opencv-python-headless==4.11.0.86</code>, Linux aarch64 wheel; bundled FFmpeg <code>5.1.6</code> | Bundled FFmpeg reports LGPL-2.1-or-later and is loaded by the observed GR00T policy processes. Headless OpenCV is not FFmpeg-free; preserve [bundled third-party notices](https://github.com/opencv/opencv-python/blob/86/LICENSE-3RD-PARTY.txt). Identifying the license is not complete binary redistribution clearance. |
| Project-video preview preparation tool | PyPI <code>imageio-ffmpeg==0.6.0</code>, Linux x86-64; bundled FFmpeg <code>7.0.2-static</code> | ImageIO wrapper is BSD-2-Clause; this FFmpeg executable reports GPL-3.0-or-later, with no nonfree flag. Used for documentation media preparation, not a project runtime dependency; only the resulting GIF is committed. |
| Dataset conversion and H.264 | User-selected FFmpeg executable with CPU <code>scale</code>, <code>libx264</code>, and MP4 support | Separate local training prerequisite. Preflight rejects a reported nonfree build and checks required encoding behavior; GPL is not rejected. H.264/ARB review remains open for project media and codec use. [FFmpeg legal guidance](https://ffmpeg.org/legal.html) |
| Remotely referenced Isaac 6.0 assets | Seven HTTPS assets referenced by two ASCII USDA compositions | NVIDIA Isaac asset terms; per-path provenance and rights state in the source repository's <code>docs/ASSET-PROVENANCE.md</code>; owner/OSRB confirmation pending |

The release uses official Isaac Sim images pulled directly by the operator,
with project files mounted from the host. GR00T serving remains native on Thor;
the optional project Thor Dockerfile has been removed. The NVIDIA image's Kit,
assets, and other proprietary components retain their own terms; the source
repository's Apache license does not cover every runtime component. See
[Isaac Sim licensing](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/common/licenses-isaac-sim.html).

The codec observations above distinguish installed artifacts from libraries
loaded by a process. They do not qualify a fresh installation, infer executed
codec functions from process maps, or clear a future environment/container
export. Complete source/build provenance of the custom TorchCodec wheel and
any redistributed native bundles remains a separate review item.

## Codec use and build evidence

`docs/codec-inventory.json` in the source repository records the 2026-10-09
read-only inspection: exact build identities, package origins, binary hashes,
configuration and license reports, and complete compiled encoder/decoder name
lists for each inspected FFmpeg build. Those lists are capabilities reported
by the binaries, not a claim that every codec is used or works on the host's
hardware. Changing an executable, OS package, or wheel requires a new inventory.

| Project path | Required media operations | Build or selection |
|---|---|---|
| README project video | Browser/player playback of H.264 Main video and AAC-LC audio from MP4 | The committed MP4 is a data file, not codec software. Its metadata names Clipchamp; the original encoder build is not recorded. Publication rights require owner confirmation. |
| README animated preview | H.264 video decoding, scaling/palette conversion, GIF encoding; no output audio | Retained preparation record identifies ImageIO-FFmpeg 0.6.0 / FFmpeg 7.0.2-static on x86-64. |
| Dataset conversion | Decode captured JPEG frames, scale them, encode H.264 with `libx264` into MP4; no audio input | Operator-selected CPU FFmpeg executable. `ffmpeg_contract.py` checks its configuration/license and rejects reported nonfree builds before creating a dataset. Ubuntu package selection and provenance commands are in `reference/groot/groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md`. |
| Training video loading | Decode the converted H.264 MP4 videos into tensors | TorchCodec and compatible shared FFmpeg libraries in the actual training environment. Selecting the conversion executable does not select these libraries. The x86 training decoder must be checked separately. |
| Thor TorchCodec compatibility libraries | H.264 decoder available; the libraries also expose the other codecs listed in the inventory | Six Ubuntu `7:6.1.1-3ubuntu5` FFmpeg 6 packages from `ports.ubuntu.com/ubuntu-ports`, `noble/universe`; `libavcodec` reports GPL-2.0-or-later. The pinned Thor wheel's native adapter links this ABI. |
| Thor OpenCV dependency | Image processing; bundled video capability includes H.264/AAC decoding and the other codecs in the inventory | OpenCV 4.11.0.86 bundles FFmpeg 5.1.6 (`libavcodec` 59.37.100), reporting LGPL-2.1-or-later. Process maps show these libraries loaded, which does not establish that a video decoder was called. |

The Thor `/usr/bin/ffmpeg` inspected for this review belongs to NVIDIA package
`7:8.0.1-nvidia`, with executable SHA-256
`3e74c1741e7e990aa3ae47f774a74baa2df57e27b08b1e0f3846d0d861e181c7`.
APT identifies the binary package at
`https://repo.download.nvidia.com/jetson/ffmpeg/pool/main/f/ffmpeg/ffmpeg_8.0.1-nvidia_arm64.deb`.
It reports `--enable-gpl --enable-nonfree --enable-libx264` among its build
options and a nonfree/unredistributable license status. These findings identify
the installed binary and its repository; they do not establish who installed
it, the exact modified source/build recipe, or which earlier tests invoked it.
The separate `7:8.0.1-nvidia1` APT candidate was not the installed build.
The public NVIDIA source index listed that newer candidate only; the exact
installed version's source descriptor returned HTTP 404. Candidate source
must not be presented as matching the installed binary.

The Git source tree and the seven project Python distributions contain no
FFmpeg executable or native FFmpeg libraries. CI builds project packages for
validation and does not publish them. The Thor installer requests the six
versioned FFmpeg 6 compatibility libraries, not the unversioned `ffmpeg`
package. The dataset converter rejects the inspected nonfree executable.
These are distribution and implementation facts, not legal approval of the
runtime dependencies or project media. The inventory discloses gaps in the
exact source/build records for the custom TorchCodec wheel and NVIDIA FFmpeg
binary. Those gaps do not themselves establish a license violation or a
requirement to replace the working runtime. OSRB should assess whether further
evidence is needed for this source release; redistribution of either binary
would require a separate assessment of its terms and supporting evidence.
No host runtime was replaced as part of this documentation audit.

## npm dependency inventory (431 identities)

| Ecosystem | Package | Version | Declared or selected license |
|---|---|---:|---|
| npm | [@agentclientprotocol/sdk](https://www.npmjs.com/package/@agentclientprotocol/sdk/v/1.4.0) | <code>1.4.0</code> | Apache-2.0 |
| npm | [@anthropic-ai/sdk](https://www.npmjs.com/package/@anthropic-ai/sdk/v/0.120.0) | <code>0.120.0</code> | MIT |
| npm | [@babel/runtime](https://www.npmjs.com/package/@babel/runtime/v/7.29.7) | <code>7.29.7</code> | MIT |
| npm | [@borewit/text-codec](https://www.npmjs.com/package/@borewit/text-codec/v/0.2.2) | <code>0.2.2</code> | MIT |
| npm | [@clack/core](https://www.npmjs.com/package/@clack/core/v/1.4.3) | <code>1.4.3</code> | MIT |
| npm | [@clack/prompts](https://www.npmjs.com/package/@clack/prompts/v/1.7.0) | <code>1.7.0</code> | MIT |
| npm | [@earendil-works/pi-tui](https://www.npmjs.com/package/@earendil-works/pi-tui/v/0.84.3) | <code>0.84.3</code> | MIT |
| npm | [@google/genai](https://www.npmjs.com/package/@google/genai/v/2.18.0) | <code>2.18.0</code> | Apache-2.0 |
| npm | [@grammyjs/runner](https://www.npmjs.com/package/@grammyjs/runner/v/2.0.3) | <code>2.0.3</code> | MIT |
| npm | [@grammyjs/transformer-throttler](https://www.npmjs.com/package/@grammyjs/transformer-throttler/v/1.2.1) | <code>1.2.1</code> | MIT |
| npm | [@grammyjs/types](https://www.npmjs.com/package/@grammyjs/types/v/5.0.0) | <code>5.0.0</code> | MIT |
| npm | [@homebridge/ciao](https://www.npmjs.com/package/@homebridge/ciao/v/1.3.12) | <code>1.3.12</code> | MIT |
| npm | [@hono/node-server](https://www.npmjs.com/package/@hono/node-server/v/2.1.1) | <code>2.1.1</code> | MIT |
| npm | [@isaacs/fs-minipass](https://www.npmjs.com/package/@isaacs/fs-minipass/v/4.0.1) | <code>4.0.1</code> | ISC |
| npm | [@jridgewell/resolve-uri](https://www.npmjs.com/package/@jridgewell/resolve-uri/v/3.1.2) | <code>3.1.2</code> | MIT |
| npm | [@jridgewell/sourcemap-codec](https://www.npmjs.com/package/@jridgewell/sourcemap-codec/v/1.6.0) | <code>1.6.0</code> | MIT |
| npm | [@jridgewell/trace-mapping](https://www.npmjs.com/package/@jridgewell/trace-mapping/v/0.3.31) | <code>0.3.31</code> | MIT |
| npm | [@koromix/koffi-darwin-arm64](https://www.npmjs.com/package/@koromix/koffi-darwin-arm64/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-darwin-x64](https://www.npmjs.com/package/@koromix/koffi-darwin-x64/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-freebsd-arm64](https://www.npmjs.com/package/@koromix/koffi-freebsd-arm64/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-freebsd-ia32](https://www.npmjs.com/package/@koromix/koffi-freebsd-ia32/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-freebsd-x64](https://www.npmjs.com/package/@koromix/koffi-freebsd-x64/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-linux-arm64](https://www.npmjs.com/package/@koromix/koffi-linux-arm64/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-linux-ia32](https://www.npmjs.com/package/@koromix/koffi-linux-ia32/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-linux-loong64](https://www.npmjs.com/package/@koromix/koffi-linux-loong64/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-linux-riscv64](https://www.npmjs.com/package/@koromix/koffi-linux-riscv64/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-linux-x64](https://www.npmjs.com/package/@koromix/koffi-linux-x64/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-openbsd-ia32](https://www.npmjs.com/package/@koromix/koffi-openbsd-ia32/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-openbsd-x64](https://www.npmjs.com/package/@koromix/koffi-openbsd-x64/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-win32-arm64](https://www.npmjs.com/package/@koromix/koffi-win32-arm64/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-win32-ia32](https://www.npmjs.com/package/@koromix/koffi-win32-ia32/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@koromix/koffi-win32-x64](https://www.npmjs.com/package/@koromix/koffi-win32-x64/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [@lydell/node-pty](https://www.npmjs.com/package/@lydell/node-pty/v/1.2.0-beta.15) | <code>1.2.0-beta.15</code> | MIT |
| npm | [@lydell/node-pty-darwin-arm64](https://www.npmjs.com/package/@lydell/node-pty-darwin-arm64/v/1.2.0-beta.15) | <code>1.2.0-beta.15</code> | MIT |
| npm | [@lydell/node-pty-darwin-x64](https://www.npmjs.com/package/@lydell/node-pty-darwin-x64/v/1.2.0-beta.15) | <code>1.2.0-beta.15</code> | MIT |
| npm | [@lydell/node-pty-linux-arm64](https://www.npmjs.com/package/@lydell/node-pty-linux-arm64/v/1.2.0-beta.15) | <code>1.2.0-beta.15</code> | MIT |
| npm | [@lydell/node-pty-linux-x64](https://www.npmjs.com/package/@lydell/node-pty-linux-x64/v/1.2.0-beta.15) | <code>1.2.0-beta.15</code> | MIT |
| npm | [@lydell/node-pty-win32-arm64](https://www.npmjs.com/package/@lydell/node-pty-win32-arm64/v/1.2.0-beta.15) | <code>1.2.0-beta.15</code> | MIT |
| npm | [@lydell/node-pty-win32-x64](https://www.npmjs.com/package/@lydell/node-pty-win32-x64/v/1.2.0-beta.15) | <code>1.2.0-beta.15</code> | MIT |
| npm | [@mistralai/mistralai](https://www.npmjs.com/package/@mistralai/mistralai/v/2.6.4) | <code>2.6.4</code> | Apache-2.0 |
| npm | [@modelcontextprotocol/sdk](https://www.npmjs.com/package/@modelcontextprotocol/sdk/v/1.30.0) | <code>1.30.0</code> | MIT |
| npm | [@mozilla/readability](https://www.npmjs.com/package/@mozilla/readability/v/0.6.0) | <code>0.6.0</code> | Apache-2.0 |
| npm | [@openclaw/ai](https://www.npmjs.com/package/@openclaw/ai/v/2026.9.2) | <code>2026.9.2</code> | MIT |
| npm | [@openclaw/fs-safe](https://www.npmjs.com/package/@openclaw/fs-safe/v/0.8.1) | <code>0.8.1</code> | MIT |
| npm | [@openclaw/fs-safe-darwin-arm64](https://www.npmjs.com/package/@openclaw/fs-safe-darwin-arm64/v/0.8.1) | <code>0.8.1</code> | MIT |
| npm | [@openclaw/fs-safe-darwin-x64](https://www.npmjs.com/package/@openclaw/fs-safe-darwin-x64/v/0.8.1) | <code>0.8.1</code> | MIT |
| npm | [@openclaw/fs-safe-linux-arm64-gnu](https://www.npmjs.com/package/@openclaw/fs-safe-linux-arm64-gnu/v/0.8.1) | <code>0.8.1</code> | MIT |
| npm | [@openclaw/fs-safe-linux-arm64-musl](https://www.npmjs.com/package/@openclaw/fs-safe-linux-arm64-musl/v/0.8.1) | <code>0.8.1</code> | MIT |
| npm | [@openclaw/fs-safe-linux-x64-gnu](https://www.npmjs.com/package/@openclaw/fs-safe-linux-x64-gnu/v/0.8.1) | <code>0.8.1</code> | MIT |
| npm | [@openclaw/fs-safe-linux-x64-musl](https://www.npmjs.com/package/@openclaw/fs-safe-linux-x64-musl/v/0.8.1) | <code>0.8.1</code> | MIT |
| npm | [@openclaw/fs-safe-win32-x64-msvc](https://www.npmjs.com/package/@openclaw/fs-safe-win32-x64-msvc/v/0.8.1) | <code>0.8.1</code> | MIT |
| npm | [@openclaw/proxyline](https://www.npmjs.com/package/@openclaw/proxyline/v/0.3.7) | <code>0.3.7</code> | MIT |
| npm | [@opentelemetry/semantic-conventions](https://www.npmjs.com/package/@opentelemetry/semantic-conventions/v/1.43.0) | <code>1.43.0</code> | Apache-2.0 |
| npm | [@oxc-project/types](https://www.npmjs.com/package/@oxc-project/types/v/0.148.0) | <code>0.148.0</code> | MIT |
| npm | [@protobufjs/aspromise](https://www.npmjs.com/package/@protobufjs/aspromise/v/1.1.2) | <code>1.1.2</code> | BSD-3-Clause |
| npm | [@protobufjs/base64](https://www.npmjs.com/package/@protobufjs/base64/v/1.1.2) | <code>1.1.2</code> | BSD-3-Clause |
| npm | [@protobufjs/codegen](https://www.npmjs.com/package/@protobufjs/codegen/v/2.0.5) | <code>2.0.5</code> | BSD-3-Clause |
| npm | [@protobufjs/eventemitter](https://www.npmjs.com/package/@protobufjs/eventemitter/v/1.1.1) | <code>1.1.1</code> | BSD-3-Clause |
| npm | [@protobufjs/fetch](https://www.npmjs.com/package/@protobufjs/fetch/v/1.1.1) | <code>1.1.1</code> | BSD-3-Clause |
| npm | [@protobufjs/float](https://www.npmjs.com/package/@protobufjs/float/v/1.0.2) | <code>1.0.2</code> | BSD-3-Clause |
| npm | [@protobufjs/path](https://www.npmjs.com/package/@protobufjs/path/v/1.1.2) | <code>1.1.2</code> | BSD-3-Clause |
| npm | [@protobufjs/pool](https://www.npmjs.com/package/@protobufjs/pool/v/1.1.0) | <code>1.1.0</code> | BSD-3-Clause |
| npm | [@protobufjs/utf8](https://www.npmjs.com/package/@protobufjs/utf8/v/1.1.2) | <code>1.1.2</code> | BSD-3-Clause |
| npm | [@rolldown/binding-android-arm-eabi](https://www.npmjs.com/package/@rolldown/binding-android-arm-eabi/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-android-arm64](https://www.npmjs.com/package/@rolldown/binding-android-arm64/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-darwin-arm64](https://www.npmjs.com/package/@rolldown/binding-darwin-arm64/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-darwin-x64](https://www.npmjs.com/package/@rolldown/binding-darwin-x64/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-freebsd-x64](https://www.npmjs.com/package/@rolldown/binding-freebsd-x64/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-linux-arm-gnueabihf](https://www.npmjs.com/package/@rolldown/binding-linux-arm-gnueabihf/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-linux-arm64-gnu](https://www.npmjs.com/package/@rolldown/binding-linux-arm64-gnu/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-linux-arm64-musl](https://www.npmjs.com/package/@rolldown/binding-linux-arm64-musl/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-linux-ppc64-gnu](https://www.npmjs.com/package/@rolldown/binding-linux-ppc64-gnu/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-linux-s390x-gnu](https://www.npmjs.com/package/@rolldown/binding-linux-s390x-gnu/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-linux-x64-gnu](https://www.npmjs.com/package/@rolldown/binding-linux-x64-gnu/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-linux-x64-musl](https://www.npmjs.com/package/@rolldown/binding-linux-x64-musl/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-openharmony-arm64](https://www.npmjs.com/package/@rolldown/binding-openharmony-arm64/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-win32-arm64-msvc](https://www.npmjs.com/package/@rolldown/binding-win32-arm64-msvc/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/binding-win32-x64-msvc](https://www.npmjs.com/package/@rolldown/binding-win32-x64-msvc/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [@rolldown/pluginutils](https://www.npmjs.com/package/@rolldown/pluginutils/v/1.0.1) | <code>1.0.1</code> | MIT |
| npm | [@sec-ant/readable-stream](https://www.npmjs.com/package/@sec-ant/readable-stream/v/0.4.1) | <code>0.4.1</code> | MIT |
| npm | [@silvia-odwyer/photon-node](https://www.npmjs.com/package/@silvia-odwyer/photon-node/v/0.3.4) | <code>0.3.4</code> | Apache-2.0 |
| npm | [@sindresorhus/merge-streams](https://www.npmjs.com/package/@sindresorhus/merge-streams/v/4.0.0) | <code>4.0.0</code> | MIT |
| npm | [@stablelib/base64](https://www.npmjs.com/package/@stablelib/base64/v/1.0.1) | <code>1.0.1</code> | MIT |
| npm | [@tokenizer/inflate](https://www.npmjs.com/package/@tokenizer/inflate/v/0.4.1) | <code>0.4.1</code> | MIT |
| npm | [@tokenizer/token](https://www.npmjs.com/package/@tokenizer/token/v/0.3.0) | <code>0.3.0</code> | MIT |
| npm | [@trycua/cua-driver](https://www.npmjs.com/package/@trycua/cua-driver/v/0.22.0) | <code>0.22.0</code> | MIT |
| npm | [@trycua/cua-driver-darwin-arm64](https://www.npmjs.com/package/@trycua/cua-driver-darwin-arm64/v/0.22.0) | <code>0.22.0</code> | MIT AND MPL-2.0 |
| npm | [@trycua/cua-driver-darwin-x64](https://www.npmjs.com/package/@trycua/cua-driver-darwin-x64/v/0.22.0) | <code>0.22.0</code> | MIT AND MPL-2.0 |
| npm | [@trycua/cua-driver-linux-arm64-gnu](https://www.npmjs.com/package/@trycua/cua-driver-linux-arm64-gnu/v/0.22.0) | <code>0.22.0</code> | MIT AND MPL-2.0 |
| npm | [@trycua/cua-driver-linux-x64-gnu](https://www.npmjs.com/package/@trycua/cua-driver-linux-x64-gnu/v/0.22.0) | <code>0.22.0</code> | MIT AND MPL-2.0 |
| npm | [@trycua/cua-driver-win32-arm64-msvc](https://www.npmjs.com/package/@trycua/cua-driver-win32-arm64-msvc/v/0.22.0) | <code>0.22.0</code> | MIT AND MPL-2.0 |
| npm | [@trycua/cua-driver-win32-x64-msvc](https://www.npmjs.com/package/@trycua/cua-driver-win32-x64-msvc/v/0.22.0) | <code>0.22.0</code> | MIT AND MPL-2.0 |
| npm | [@types/chai](https://www.npmjs.com/package/@types/chai/v/5.2.3) | <code>5.2.3</code> | MIT |
| npm | [@types/deep-eql](https://www.npmjs.com/package/@types/deep-eql/v/4.0.2) | <code>4.0.2</code> | MIT |
| npm | [@types/estree](https://www.npmjs.com/package/@types/estree/v/1.0.9) | <code>1.0.9</code> | MIT |
| npm | [@types/node](https://www.npmjs.com/package/@types/node/v/26.5.0) | <code>26.5.0</code> | MIT |
| npm | [@types/retry](https://www.npmjs.com/package/@types/retry/v/0.12.0) | <code>0.12.0</code> | MIT |
| npm | [@ubjs/core](https://www.npmjs.com/package/@ubjs/core/v/0.31.0-3) | <code>0.31.0-3</code> | MPL-2.0 |
| npm | [@ubjs/node](https://www.npmjs.com/package/@ubjs/node/v/0.31.0-3) | <code>0.31.0-3</code> | MPL-2.0 |
| npm | [@ubjs/node-darwin-arm64](https://www.npmjs.com/package/@ubjs/node-darwin-arm64/v/0.31.0-3) | <code>0.31.0-3</code> | MPL-2.0 |
| npm | [@ubjs/node-darwin-x64](https://www.npmjs.com/package/@ubjs/node-darwin-x64/v/0.31.0-3) | <code>0.31.0-3</code> | MPL-2.0 |
| npm | [@ubjs/node-linux-arm64-gnu](https://www.npmjs.com/package/@ubjs/node-linux-arm64-gnu/v/0.31.0-3) | <code>0.31.0-3</code> | MPL-2.0 |
| npm | [@ubjs/node-linux-arm64-musl](https://www.npmjs.com/package/@ubjs/node-linux-arm64-musl/v/0.31.0-3) | <code>0.31.0-3</code> | MPL-2.0 |
| npm | [@ubjs/node-linux-x64-gnu](https://www.npmjs.com/package/@ubjs/node-linux-x64-gnu/v/0.31.0-3) | <code>0.31.0-3</code> | MPL-2.0 |
| npm | [@ubjs/node-linux-x64-musl](https://www.npmjs.com/package/@ubjs/node-linux-x64-musl/v/0.31.0-3) | <code>0.31.0-3</code> | MPL-2.0 |
| npm | [@ubjs/node-win32-arm64-msvc](https://www.npmjs.com/package/@ubjs/node-win32-arm64-msvc/v/0.31.0-3) | <code>0.31.0-3</code> | MPL-2.0 |
| npm | [@ubjs/node-win32-x64-msvc](https://www.npmjs.com/package/@ubjs/node-win32-x64-msvc/v/0.31.0-3) | <code>0.31.0-3</code> | MPL-2.0 |
| npm | [@vitest/mocker](https://www.npmjs.com/package/@vitest/mocker/v/5.0.0) | <code>5.0.0</code> | MIT |
| npm | [@vitest/spy](https://www.npmjs.com/package/@vitest/spy/v/5.0.0) | <code>5.0.0</code> | MIT |
| npm | [abort-controller](https://www.npmjs.com/package/abort-controller/v/3.0.0) | <code>3.0.0</code> | MIT |
| npm | [accepts](https://www.npmjs.com/package/accepts/v/2.0.0) | <code>2.0.0</code> | MIT |
| npm | [acorn](https://www.npmjs.com/package/acorn/v/8.18.0) | <code>8.18.0</code> | MIT |
| npm | [agent-base](https://www.npmjs.com/package/agent-base/v/7.1.4) | <code>7.1.4</code> | MIT |
| npm | [ajv](https://www.npmjs.com/package/ajv/v/8.20.0) | <code>8.20.0</code> | MIT |
| npm | [ajv-formats](https://www.npmjs.com/package/ajv-formats/v/3.0.1) | <code>3.0.1</code> | MIT |
| npm | [ansi-regex](https://www.npmjs.com/package/ansi-regex/v/5.0.1) | <code>5.0.1</code> | MIT |
| npm | [ansi-styles](https://www.npmjs.com/package/ansi-styles/v/4.3.0) | <code>4.3.0</code> | MIT |
| npm | [asn1.js](https://www.npmjs.com/package/asn1.js/v/5.4.1) | <code>5.4.1</code> | MIT |
| npm | [assertion-error](https://www.npmjs.com/package/assertion-error/v/2.0.1) | <code>2.0.1</code> | MIT |
| npm | [balanced-match](https://www.npmjs.com/package/balanced-match/v/4.0.4) | <code>4.0.4</code> | MIT |
| npm | [base64-js](https://www.npmjs.com/package/base64-js/v/1.5.1) | <code>1.5.1</code> | MIT |
| npm | [bignumber.js](https://www.npmjs.com/package/bignumber.js/v/9.3.1) | <code>9.3.1</code> | MIT |
| npm | [bn.js](https://www.npmjs.com/package/bn.js/v/4.12.5) | <code>4.12.5</code> | MIT |
| npm | [body-parser](https://www.npmjs.com/package/body-parser/v/2.3.0) | <code>2.3.0</code> | MIT |
| npm | [boolbase](https://www.npmjs.com/package/boolbase/v/2.0.0) | <code>2.0.0</code> | ISC |
| npm | [bottleneck](https://www.npmjs.com/package/bottleneck/v/2.19.5) | <code>2.19.5</code> | MIT |
| npm | [brace-expansion](https://www.npmjs.com/package/brace-expansion/v/5.0.9) | <code>5.0.9</code> | MIT |
| npm | [buffer-equal-constant-time](https://www.npmjs.com/package/buffer-equal-constant-time/v/1.0.1) | <code>1.0.1</code> | BSD-3-Clause |
| npm | [buffer-from](https://www.npmjs.com/package/buffer-from/v/1.1.2) | <code>1.1.2</code> | MIT |
| npm | [bytes](https://www.npmjs.com/package/bytes/v/3.1.2) | <code>3.1.2</code> | MIT |
| npm | [call-bind-apply-helpers](https://www.npmjs.com/package/call-bind-apply-helpers/v/1.0.2) | <code>1.0.2</code> | MIT |
| npm | [call-bound](https://www.npmjs.com/package/call-bound/v/1.0.4) | <code>1.0.4</code> | MIT |
| npm | [camelcase](https://www.npmjs.com/package/camelcase/v/5.3.1) | <code>5.3.1</code> | MIT |
| npm | [chai](https://www.npmjs.com/package/chai/v/6.2.2) | <code>6.2.2</code> | MIT |
| npm | [chalk](https://www.npmjs.com/package/chalk/v/6.0.0) | <code>6.0.0</code> | MIT |
| npm | [chokidar](https://www.npmjs.com/package/chokidar/v/5.0.0) | <code>5.0.0</code> | MIT |
| npm | [chownr](https://www.npmjs.com/package/chownr/v/3.0.0) | <code>3.0.0</code> | BlueOak-1.0.0 |
| npm | [clawpdf](https://www.npmjs.com/package/clawpdf/v/0.3.1) | <code>0.3.1</code> | MIT |
| npm | [cliui](https://www.npmjs.com/package/cliui/v/6.0.0) | <code>6.0.0</code> | ISC |
| npm | [cliui](https://www.npmjs.com/package/cliui/v/8.0.1) | <code>8.0.1</code> | ISC |
| npm | [color-convert](https://www.npmjs.com/package/color-convert/v/2.0.1) | <code>2.0.1</code> | MIT |
| npm | [color-name](https://www.npmjs.com/package/color-name/v/1.1.4) | <code>1.1.4</code> | MIT |
| npm | [commander](https://www.npmjs.com/package/commander/v/15.0.0) | <code>15.0.0</code> | MIT |
| npm | [content-disposition](https://www.npmjs.com/package/content-disposition/v/1.1.0) | <code>1.1.0</code> | MIT |
| npm | [content-type](https://www.npmjs.com/package/content-type/v/1.0.5) | <code>1.0.5</code> | MIT |
| npm | [content-type](https://www.npmjs.com/package/content-type/v/2.1.0) | <code>2.1.0</code> | MIT |
| npm | [cookie](https://www.npmjs.com/package/cookie/v/0.7.2) | <code>0.7.2</code> | MIT |
| npm | [cookie-signature](https://www.npmjs.com/package/cookie-signature/v/1.2.2) | <code>1.2.2</code> | MIT |
| npm | [core-util-is](https://www.npmjs.com/package/core-util-is/v/1.0.3) | <code>1.0.3</code> | MIT |
| npm | [cors](https://www.npmjs.com/package/cors/v/2.8.6) | <code>2.8.6</code> | MIT |
| npm | [croner](https://www.npmjs.com/package/croner/v/10.0.1) | <code>10.0.1</code> | MIT |
| npm | [cross-spawn](https://www.npmjs.com/package/cross-spawn/v/7.0.6) | <code>7.0.6</code> | MIT |
| npm | [css-select](https://www.npmjs.com/package/css-select/v/7.0.0) | <code>7.0.0</code> | BSD-2-Clause |
| npm | [css-what](https://www.npmjs.com/package/css-what/v/8.0.0) | <code>8.0.0</code> | BSD-2-Clause |
| npm | [cssom](https://www.npmjs.com/package/cssom/v/0.5.0) | <code>0.5.0</code> | MIT |
| npm | [data-uri-to-buffer](https://www.npmjs.com/package/data-uri-to-buffer/v/4.0.1) | <code>4.0.1</code> | MIT |
| npm | [debug](https://www.npmjs.com/package/debug/v/4.4.3) | <code>4.4.3</code> | MIT |
| npm | [decamelize](https://www.npmjs.com/package/decamelize/v/1.2.0) | <code>1.2.0</code> | MIT |
| npm | [depd](https://www.npmjs.com/package/depd/v/2.0.0) | <code>2.0.0</code> | MIT |
| npm | [detect-libc](https://www.npmjs.com/package/detect-libc/v/2.1.2) | <code>2.1.2</code> | Apache-2.0 |
| npm | [diff](https://www.npmjs.com/package/diff/v/9.0.0) | <code>9.0.0</code> | BSD-3-Clause |
| npm | [dijkstrajs](https://www.npmjs.com/package/dijkstrajs/v/1.0.3) | <code>1.0.3</code> | MIT |
| npm | [dom-serializer](https://www.npmjs.com/package/dom-serializer/v/2.0.0) | <code>2.0.0</code> | MIT |
| npm | [dom-serializer](https://www.npmjs.com/package/dom-serializer/v/3.1.1) | <code>3.1.1</code> | MIT |
| npm | [domelementtype](https://www.npmjs.com/package/domelementtype/v/2.3.0) | <code>2.3.0</code> | BSD-2-Clause |
| npm | [domelementtype](https://www.npmjs.com/package/domelementtype/v/3.0.0) | <code>3.0.0</code> | BSD-2-Clause |
| npm | [domhandler](https://www.npmjs.com/package/domhandler/v/5.0.3) | <code>5.0.3</code> | BSD-2-Clause |
| npm | [domhandler](https://www.npmjs.com/package/domhandler/v/6.0.1) | <code>6.0.1</code> | BSD-2-Clause |
| npm | [domutils](https://www.npmjs.com/package/domutils/v/3.2.2) | <code>3.2.2</code> | BSD-2-Clause |
| npm | [domutils](https://www.npmjs.com/package/domutils/v/4.0.2) | <code>4.0.2</code> | BSD-2-Clause |
| npm | [dotenv](https://www.npmjs.com/package/dotenv/v/17.4.2) | <code>17.4.2</code> | BSD-2-Clause |
| npm | [dunder-proto](https://www.npmjs.com/package/dunder-proto/v/1.0.1) | <code>1.0.1</code> | MIT |
| npm | [ecdsa-sig-formatter](https://www.npmjs.com/package/ecdsa-sig-formatter/v/1.0.11) | <code>1.0.11</code> | Apache-2.0 |
| npm | [ee-first](https://www.npmjs.com/package/ee-first/v/1.1.1) | <code>1.1.1</code> | MIT |
| npm | [emoji-regex](https://www.npmjs.com/package/emoji-regex/v/8.0.0) | <code>8.0.0</code> | MIT |
| npm | [encodeurl](https://www.npmjs.com/package/encodeurl/v/2.0.0) | <code>2.0.0</code> | MIT |
| npm | [entities](https://www.npmjs.com/package/entities/v/4.5.0) | <code>4.5.0</code> | BSD-2-Clause |
| npm | [entities](https://www.npmjs.com/package/entities/v/7.0.1) | <code>7.0.1</code> | BSD-2-Clause |
| npm | [entities](https://www.npmjs.com/package/entities/v/8.0.0) | <code>8.0.0</code> | BSD-2-Clause |
| npm | [es-define-property](https://www.npmjs.com/package/es-define-property/v/1.0.1) | <code>1.0.1</code> | MIT |
| npm | [es-errors](https://www.npmjs.com/package/es-errors/v/1.3.0) | <code>1.3.0</code> | MIT |
| npm | [es-module-lexer](https://www.npmjs.com/package/es-module-lexer/v/2.3.2) | <code>2.3.2</code> | MIT |
| npm | [es-object-atoms](https://www.npmjs.com/package/es-object-atoms/v/1.1.2) | <code>1.1.2</code> | MIT |
| npm | [escalade](https://www.npmjs.com/package/escalade/v/3.2.0) | <code>3.2.0</code> | MIT |
| npm | [escape-html](https://www.npmjs.com/package/escape-html/v/1.0.3) | <code>1.0.3</code> | MIT |
| npm | [estree-walker](https://www.npmjs.com/package/estree-walker/v/3.0.3) | <code>3.0.3</code> | MIT |
| npm | [etag](https://www.npmjs.com/package/etag/v/1.8.1) | <code>1.8.1</code> | MIT |
| npm | [event-target-shim](https://www.npmjs.com/package/event-target-shim/v/5.0.1) | <code>5.0.1</code> | MIT |
| npm | [eventsource](https://www.npmjs.com/package/eventsource/v/3.0.7) | <code>3.0.7</code> | MIT |
| npm | [eventsource-parser](https://www.npmjs.com/package/eventsource-parser/v/3.1.1) | <code>3.1.1</code> | MIT |
| npm | [execa](https://www.npmjs.com/package/execa/v/10.0.1) | <code>10.0.1</code> | MIT |
| npm | [expect-type](https://www.npmjs.com/package/expect-type/v/1.4.0) | <code>1.4.0</code> | Apache-2.0 |
| npm | [express](https://www.npmjs.com/package/express/v/5.2.1) | <code>5.2.1</code> | MIT |
| npm | [express-rate-limit](https://www.npmjs.com/package/express-rate-limit/v/8.7.0) | <code>8.7.0</code> | MIT |
| npm | [extend](https://www.npmjs.com/package/extend/v/3.0.2) | <code>3.0.2</code> | MIT |
| npm | [fast-deep-equal](https://www.npmjs.com/package/fast-deep-equal/v/3.1.3) | <code>3.1.3</code> | MIT |
| npm | [fast-sha256](https://www.npmjs.com/package/fast-sha256/v/1.3.0) | <code>1.3.0</code> | Unlicense |
| npm | [fast-string-truncated-width](https://www.npmjs.com/package/fast-string-truncated-width/v/3.0.3) | <code>3.0.3</code> | MIT |
| npm | [fast-string-width](https://www.npmjs.com/package/fast-string-width/v/3.0.2) | <code>3.0.2</code> | MIT |
| npm | [fast-uri](https://www.npmjs.com/package/fast-uri/v/3.1.8) | <code>3.1.8</code> | BSD-3-Clause |
| npm | [fast-wrap-ansi](https://www.npmjs.com/package/fast-wrap-ansi/v/0.2.2) | <code>0.2.2</code> | MIT |
| npm | [fdir](https://www.npmjs.com/package/fdir/v/6.5.0) | <code>6.5.0</code> | MIT |
| npm | [fetch-blob](https://www.npmjs.com/package/fetch-blob/v/3.2.0) | <code>3.2.0</code> | MIT |
| npm | [figures](https://www.npmjs.com/package/figures/v/6.1.0) | <code>6.1.0</code> | MIT |
| npm | [file-type](https://www.npmjs.com/package/file-type/v/22.0.2) | <code>22.0.2</code> | MIT |
| npm | [finalhandler](https://www.npmjs.com/package/finalhandler/v/2.1.1) | <code>2.1.1</code> | MIT |
| npm | [find-up](https://www.npmjs.com/package/find-up/v/4.1.0) | <code>4.1.0</code> | MIT |
| npm | [formdata-polyfill](https://www.npmjs.com/package/formdata-polyfill/v/4.0.10) | <code>4.0.10</code> | MIT |
| npm | [forwarded](https://www.npmjs.com/package/forwarded/v/0.2.0) | <code>0.2.0</code> | MIT |
| npm | [fresh](https://www.npmjs.com/package/fresh/v/2.0.0) | <code>2.0.0</code> | MIT |
| npm | [fsevents](https://www.npmjs.com/package/fsevents/v/2.3.3) | <code>2.3.3</code> | MIT |
| npm | [function-bind](https://www.npmjs.com/package/function-bind/v/1.1.2) | <code>1.1.2</code> | MIT |
| npm | [gaxios](https://www.npmjs.com/package/gaxios/v/7.3.1) | <code>7.3.1</code> | Apache-2.0 |
| npm | [gcp-metadata](https://www.npmjs.com/package/gcp-metadata/v/8.1.2) | <code>8.1.2</code> | Apache-2.0 |
| npm | [get-caller-file](https://www.npmjs.com/package/get-caller-file/v/2.0.5) | <code>2.0.5</code> | ISC |
| npm | [get-east-asian-width](https://www.npmjs.com/package/get-east-asian-width/v/1.6.0) | <code>1.6.0</code> | MIT |
| npm | [get-intrinsic](https://www.npmjs.com/package/get-intrinsic/v/1.3.0) | <code>1.3.0</code> | MIT |
| npm | [get-proto](https://www.npmjs.com/package/get-proto/v/1.0.1) | <code>1.0.1</code> | MIT |
| npm | [get-stream](https://www.npmjs.com/package/get-stream/v/9.0.1) | <code>9.0.1</code> | MIT |
| npm | [google-auth-library](https://www.npmjs.com/package/google-auth-library/v/10.9.1) | <code>10.9.1</code> | Apache-2.0 |
| npm | [google-logging-utils](https://www.npmjs.com/package/google-logging-utils/v/1.1.3) | <code>1.1.3</code> | Apache-2.0 |
| npm | [gopd](https://www.npmjs.com/package/gopd/v/1.2.0) | <code>1.2.0</code> | MIT |
| npm | [grammy](https://www.npmjs.com/package/grammy/v/1.46.0) | <code>1.46.0</code> | MIT |
| npm | [has-symbols](https://www.npmjs.com/package/has-symbols/v/1.1.0) | <code>1.1.0</code> | MIT |
| npm | [hasown](https://www.npmjs.com/package/hasown/v/2.0.4) | <code>2.0.4</code> | MIT |
| npm | [highlight.js](https://www.npmjs.com/package/highlight.js/v/11.12.0) | <code>11.12.0</code> | BSD-3-Clause |
| npm | [hono](https://www.npmjs.com/package/hono/v/4.13.7) | <code>4.13.7</code> | MIT |
| npm | [hosted-git-info](https://www.npmjs.com/package/hosted-git-info/v/10.1.1) | <code>10.1.1</code> | ISC |
| npm | [html-escaper](https://www.npmjs.com/package/html-escaper/v/3.0.3) | <code>3.0.3</code> | MIT |
| npm | [htmlparser2](https://www.npmjs.com/package/htmlparser2/v/10.1.0) | <code>10.1.0</code> | MIT |
| npm | [http-errors](https://www.npmjs.com/package/http-errors/v/2.0.1) | <code>2.0.1</code> | MIT |
| npm | [http_ece](https://www.npmjs.com/package/http_ece/v/1.2.0) | <code>1.2.0</code> | MIT |
| npm | [https-proxy-agent](https://www.npmjs.com/package/https-proxy-agent/v/7.0.6) | <code>7.0.6</code> | MIT |
| npm | [human-signals](https://www.npmjs.com/package/human-signals/v/8.0.1) | <code>8.0.1</code> | Apache-2.0 |
| npm | [iconv-lite](https://www.npmjs.com/package/iconv-lite/v/0.7.3) | <code>0.7.3</code> | MIT |
| npm | [ieee754](https://www.npmjs.com/package/ieee754/v/1.2.1) | <code>1.2.1</code> | BSD-3-Clause |
| npm | [ignore](https://www.npmjs.com/package/ignore/v/7.0.6) | <code>7.0.6</code> | MIT |
| npm | [immediate](https://www.npmjs.com/package/immediate/v/3.0.6) | <code>3.0.6</code> | MIT |
| npm | [inherits](https://www.npmjs.com/package/inherits/v/2.0.4) | <code>2.0.4</code> | ISC |
| npm | [ip-address](https://www.npmjs.com/package/ip-address/v/10.7.0) | <code>10.7.0</code> | MIT |
| npm | [ipaddr.js](https://www.npmjs.com/package/ipaddr.js/v/1.9.1) | <code>1.9.1</code> | MIT |
| npm | [is-fullwidth-code-point](https://www.npmjs.com/package/is-fullwidth-code-point/v/3.0.0) | <code>3.0.0</code> | MIT |
| npm | [is-plain-obj](https://www.npmjs.com/package/is-plain-obj/v/4.1.0) | <code>4.1.0</code> | MIT |
| npm | [is-promise](https://www.npmjs.com/package/is-promise/v/4.0.0) | <code>4.0.0</code> | MIT |
| npm | [is-stream](https://www.npmjs.com/package/is-stream/v/4.0.1) | <code>4.0.1</code> | MIT |
| npm | [is-unicode-supported](https://www.npmjs.com/package/is-unicode-supported/v/2.1.0) | <code>2.1.0</code> | MIT |
| npm | [isarray](https://www.npmjs.com/package/isarray/v/1.0.0) | <code>1.0.0</code> | MIT |
| npm | [isexe](https://www.npmjs.com/package/isexe/v/2.0.0) | <code>2.0.0</code> | ISC |
| npm | [jiti](https://www.npmjs.com/package/jiti/v/2.7.0) | <code>2.7.0</code> | MIT |
| npm | [jose](https://www.npmjs.com/package/jose/v/6.2.12) | <code>6.2.12</code> | MIT |
| npm | [json-bigint](https://www.npmjs.com/package/json-bigint/v/1.0.0) | <code>1.0.0</code> | MIT |
| npm | [json-schema-to-ts](https://www.npmjs.com/package/json-schema-to-ts/v/3.1.1) | <code>3.1.1</code> | MIT |
| npm | [json-schema-traverse](https://www.npmjs.com/package/json-schema-traverse/v/1.0.0) | <code>1.0.0</code> | MIT |
| npm | [json-schema-typed](https://www.npmjs.com/package/json-schema-typed/v/8.0.2) | <code>8.0.2</code> | BSD-2-Clause |
| npm | [json5](https://www.npmjs.com/package/json5/v/2.2.3) | <code>2.2.3</code> | MIT |
| npm | [jszip](https://www.npmjs.com/package/jszip/v/3.10.1) | <code>3.10.1</code> | MIT (selected from MIT OR GPL-3.0-or-later) |
| npm | [jwa](https://www.npmjs.com/package/jwa/v/2.0.1) | <code>2.0.1</code> | MIT |
| npm | [jws](https://www.npmjs.com/package/jws/v/4.0.1) | <code>4.0.1</code> | MIT |
| npm | [koffi](https://www.npmjs.com/package/koffi/v/3.1.6) | <code>3.1.6</code> | MIT |
| npm | [kysely](https://www.npmjs.com/package/kysely/v/0.29.5) | <code>0.29.5</code> | MIT |
| npm | [lie](https://www.npmjs.com/package/lie/v/3.3.0) | <code>3.3.0</code> | MIT |
| npm | [lightningcss](https://www.npmjs.com/package/lightningcss/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [lightningcss-android-arm64](https://www.npmjs.com/package/lightningcss-android-arm64/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [lightningcss-darwin-arm64](https://www.npmjs.com/package/lightningcss-darwin-arm64/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [lightningcss-darwin-x64](https://www.npmjs.com/package/lightningcss-darwin-x64/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [lightningcss-freebsd-x64](https://www.npmjs.com/package/lightningcss-freebsd-x64/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [lightningcss-linux-arm-gnueabihf](https://www.npmjs.com/package/lightningcss-linux-arm-gnueabihf/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [lightningcss-linux-arm64-gnu](https://www.npmjs.com/package/lightningcss-linux-arm64-gnu/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [lightningcss-linux-arm64-musl](https://www.npmjs.com/package/lightningcss-linux-arm64-musl/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [lightningcss-linux-x64-gnu](https://www.npmjs.com/package/lightningcss-linux-x64-gnu/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [lightningcss-linux-x64-musl](https://www.npmjs.com/package/lightningcss-linux-x64-musl/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [lightningcss-win32-arm64-msvc](https://www.npmjs.com/package/lightningcss-win32-arm64-msvc/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [lightningcss-win32-x64-msvc](https://www.npmjs.com/package/lightningcss-win32-x64-msvc/v/1.33.0) | <code>1.33.0</code> | MPL-2.0 |
| npm | [linkedom](https://www.npmjs.com/package/linkedom/v/0.18.13) | <code>0.18.13</code> | ISC |
| npm | [locate-path](https://www.npmjs.com/package/locate-path/v/5.0.0) | <code>5.0.0</code> | MIT |
| npm | [long](https://www.npmjs.com/package/long/v/5.3.2) | <code>5.3.2</code> | Apache-2.0 |
| npm | [lru-cache](https://www.npmjs.com/package/lru-cache/v/11.5.2) | <code>11.5.2</code> | BlueOak-1.0.0 |
| npm | [magic-string](https://www.npmjs.com/package/magic-string/v/1.2.3) | <code>1.2.3</code> | MIT |
| npm | [marked](https://www.npmjs.com/package/marked/v/18.0.5) | <code>18.0.5</code> | MIT |
| npm | [math-intrinsics](https://www.npmjs.com/package/math-intrinsics/v/1.1.0) | <code>1.1.0</code> | MIT |
| npm | [media-typer](https://www.npmjs.com/package/media-typer/v/1.1.1) | <code>1.1.1</code> | MIT |
| npm | [merge-descriptors](https://www.npmjs.com/package/merge-descriptors/v/2.0.0) | <code>2.0.0</code> | MIT |
| npm | [mime-db](https://www.npmjs.com/package/mime-db/v/1.54.0) | <code>1.54.0</code> | MIT |
| npm | [mime-types](https://www.npmjs.com/package/mime-types/v/3.0.2) | <code>3.0.2</code> | MIT |
| npm | [minimalistic-assert](https://www.npmjs.com/package/minimalistic-assert/v/1.0.1) | <code>1.0.1</code> | ISC |
| npm | [minimatch](https://www.npmjs.com/package/minimatch/v/10.2.6) | <code>10.2.6</code> | BlueOak-1.0.0 |
| npm | [minimist](https://www.npmjs.com/package/minimist/v/1.2.8) | <code>1.2.8</code> | MIT |
| npm | [minipass](https://www.npmjs.com/package/minipass/v/7.1.3) | <code>7.1.3</code> | BlueOak-1.0.0 |
| npm | [minizlib](https://www.npmjs.com/package/minizlib/v/3.1.0) | <code>3.1.0</code> | MIT |
| npm | [ms](https://www.npmjs.com/package/ms/v/2.1.3) | <code>2.1.3</code> | MIT |
| npm | [nanoid](https://www.npmjs.com/package/nanoid/v/3.3.18) | <code>3.3.18</code> | MIT |
| npm | [negotiator](https://www.npmjs.com/package/negotiator/v/1.1.0) | <code>1.1.0</code> | MIT |
| npm | [node-addon-api](https://www.npmjs.com/package/node-addon-api/v/8.9.2) | <code>8.9.2</code> | MIT |
| npm | [node-domexception](https://www.npmjs.com/package/node-domexception/v/1.0.0) | <code>1.0.0</code> | MIT |
| npm | [node-edge-tts](https://www.npmjs.com/package/node-edge-tts/v/1.2.10) | <code>1.2.10</code> | MIT |
| npm | [node-fetch](https://www.npmjs.com/package/node-fetch/v/2.7.0) | <code>2.7.0</code> | MIT |
| npm | [node-fetch](https://www.npmjs.com/package/node-fetch/v/3.3.2) | <code>3.3.2</code> | MIT |
| npm | [node-gyp-build](https://www.npmjs.com/package/node-gyp-build/v/4.8.4) | <code>4.8.4</code> | MIT |
| npm | [npm-run-path](https://www.npmjs.com/package/npm-run-path/v/6.0.0) | <code>6.0.0</code> | MIT |
| npm | [nth-check](https://www.npmjs.com/package/nth-check/v/3.0.1) | <code>3.0.1</code> | BSD-2-Clause |
| npm | [object-assign](https://www.npmjs.com/package/object-assign/v/4.1.1) | <code>4.1.1</code> | MIT |
| npm | [object-inspect](https://www.npmjs.com/package/object-inspect/v/1.13.4) | <code>1.13.4</code> | MIT |
| npm | [obug](https://www.npmjs.com/package/obug/v/2.2.1) | <code>2.2.1</code> | MIT |
| npm | [on-finished](https://www.npmjs.com/package/on-finished/v/2.4.1) | <code>2.4.1</code> | MIT |
| npm | [once](https://www.npmjs.com/package/once/v/1.4.0) | <code>1.4.0</code> | ISC |
| npm | [openai](https://www.npmjs.com/package/openai/v/7.5.0) | <code>7.5.0</code> | Apache-2.0 |
| npm | [openclaw](https://www.npmjs.com/package/openclaw/v/2026.9.2) | <code>2026.9.2</code> | MIT |
| npm | [p-limit](https://www.npmjs.com/package/p-limit/v/2.3.0) | <code>2.3.0</code> | MIT |
| npm | [p-limit](https://www.npmjs.com/package/p-limit/v/7.3.1) | <code>7.3.1</code> | MIT |
| npm | [p-locate](https://www.npmjs.com/package/p-locate/v/4.1.0) | <code>4.1.0</code> | MIT |
| npm | [p-map](https://www.npmjs.com/package/p-map/v/7.0.6) | <code>7.0.6</code> | MIT |
| npm | [p-retry](https://www.npmjs.com/package/p-retry/v/4.6.2) | <code>4.6.2</code> | MIT |
| npm | [p-try](https://www.npmjs.com/package/p-try/v/2.2.0) | <code>2.2.0</code> | MIT |
| npm | [pako](https://www.npmjs.com/package/pako/v/1.0.11) | <code>1.0.11</code> | (MIT AND Zlib) |
| npm | [parse-ms](https://www.npmjs.com/package/parse-ms/v/4.0.0) | <code>4.0.0</code> | MIT |
| npm | [parseurl](https://www.npmjs.com/package/parseurl/v/1.3.3) | <code>1.3.3</code> | MIT |
| npm | [partial-json](https://www.npmjs.com/package/partial-json/v/0.1.7) | <code>0.1.7</code> | MIT |
| npm | [path-exists](https://www.npmjs.com/package/path-exists/v/4.0.0) | <code>4.0.0</code> | MIT |
| npm | [path-key](https://www.npmjs.com/package/path-key/v/3.1.1) | <code>3.1.1</code> | MIT |
| npm | [path-key](https://www.npmjs.com/package/path-key/v/4.0.0) | <code>4.0.0</code> | MIT |
| npm | [path-to-regexp](https://www.npmjs.com/package/path-to-regexp/v/8.4.2) | <code>8.4.2</code> | MIT |
| npm | [picocolors](https://www.npmjs.com/package/picocolors/v/1.1.1) | <code>1.1.1</code> | ISC |
| npm | [picomatch](https://www.npmjs.com/package/picomatch/v/4.0.7) | <code>4.0.7</code> | MIT |
| npm | [pkce-challenge](https://www.npmjs.com/package/pkce-challenge/v/5.0.1) | <code>5.0.1</code> | MIT |
| npm | [playwright-core](https://www.npmjs.com/package/playwright-core/v/1.62.1) | <code>1.62.1</code> | Apache-2.0 |
| npm | [pngjs](https://www.npmjs.com/package/pngjs/v/5.0.0) | <code>5.0.0</code> | MIT |
| npm | [postcss](https://www.npmjs.com/package/postcss/v/8.5.28) | <code>8.5.28</code> | MIT |
| npm | [pretty-ms](https://www.npmjs.com/package/pretty-ms/v/9.3.0) | <code>9.3.0</code> | MIT |
| npm | [process-nextick-args](https://www.npmjs.com/package/process-nextick-args/v/2.0.1) | <code>2.0.1</code> | MIT |
| npm | [protobufjs](https://www.npmjs.com/package/protobufjs/v/7.6.6) | <code>7.6.6</code> | BSD-3-Clause |
| npm | [proxy-addr](https://www.npmjs.com/package/proxy-addr/v/2.0.8) | <code>2.0.8</code> | MIT |
| npm | [qrcode](https://www.npmjs.com/package/qrcode/v/1.5.4) | <code>1.5.4</code> | MIT |
| npm | [qs](https://www.npmjs.com/package/qs/v/6.16.0) | <code>6.16.0</code> | BSD-3-Clause |
| npm | [quickjs-wasi](https://www.npmjs.com/package/quickjs-wasi/v/3.5.0) | <code>3.5.0</code> | MIT |
| npm | [range-parser](https://www.npmjs.com/package/range-parser/v/1.3.0) | <code>1.3.0</code> | MIT |
| npm | [rastermill](https://www.npmjs.com/package/rastermill/v/0.3.2) | <code>0.3.2</code> | MIT |
| npm | [raw-body](https://www.npmjs.com/package/raw-body/v/3.0.2) | <code>3.0.2</code> | MIT |
| npm | [readable-stream](https://www.npmjs.com/package/readable-stream/v/2.3.8) | <code>2.3.8</code> | MIT |
| npm | [readdirp](https://www.npmjs.com/package/readdirp/v/5.1.1) | <code>5.1.1</code> | MIT |
| npm | [require-directory](https://www.npmjs.com/package/require-directory/v/2.1.1) | <code>2.1.1</code> | MIT |
| npm | [require-from-string](https://www.npmjs.com/package/require-from-string/v/2.0.2) | <code>2.0.2</code> | MIT |
| npm | [require-main-filename](https://www.npmjs.com/package/require-main-filename/v/2.0.0) | <code>2.0.0</code> | ISC |
| npm | [retry](https://www.npmjs.com/package/retry/v/0.13.1) | <code>0.13.1</code> | MIT |
| npm | [rolldown](https://www.npmjs.com/package/rolldown/v/1.2.7) | <code>1.2.7</code> | MIT |
| npm | [router](https://www.npmjs.com/package/router/v/2.2.0) | <code>2.2.0</code> | MIT |
| npm | [safe-buffer](https://www.npmjs.com/package/safe-buffer/v/5.1.2) | <code>5.1.2</code> | MIT |
| npm | [safe-buffer](https://www.npmjs.com/package/safe-buffer/v/5.2.1) | <code>5.2.1</code> | MIT |
| npm | [safer-buffer](https://www.npmjs.com/package/safer-buffer/v/2.1.2) | <code>2.1.2</code> | MIT |
| npm | [semver](https://www.npmjs.com/package/semver/v/7.8.5) | <code>7.8.5</code> | ISC |
| npm | [send](https://www.npmjs.com/package/send/v/1.2.1) | <code>1.2.1</code> | MIT |
| npm | [serve-static](https://www.npmjs.com/package/serve-static/v/2.2.1) | <code>2.2.1</code> | MIT |
| npm | [set-blocking](https://www.npmjs.com/package/set-blocking/v/2.0.0) | <code>2.0.0</code> | ISC |
| npm | [setimmediate](https://www.npmjs.com/package/setimmediate/v/1.0.5) | <code>1.0.5</code> | MIT |
| npm | [setprototypeof](https://www.npmjs.com/package/setprototypeof/v/1.2.0) | <code>1.2.0</code> | ISC |
| npm | [shebang-command](https://www.npmjs.com/package/shebang-command/v/2.0.0) | <code>2.0.0</code> | MIT |
| npm | [shebang-regex](https://www.npmjs.com/package/shebang-regex/v/3.0.0) | <code>3.0.0</code> | MIT |
| npm | [side-channel](https://www.npmjs.com/package/side-channel/v/1.1.1) | <code>1.1.1</code> | MIT |
| npm | [side-channel-list](https://www.npmjs.com/package/side-channel-list/v/1.0.1) | <code>1.0.1</code> | MIT |
| npm | [side-channel-map](https://www.npmjs.com/package/side-channel-map/v/1.0.1) | <code>1.0.1</code> | MIT |
| npm | [side-channel-weakmap](https://www.npmjs.com/package/side-channel-weakmap/v/1.0.2) | <code>1.0.2</code> | MIT |
| npm | [siginfo](https://www.npmjs.com/package/siginfo/v/2.0.0) | <code>2.0.0</code> | ISC |
| npm | [signal-exit](https://www.npmjs.com/package/signal-exit/v/4.1.0) | <code>4.1.0</code> | ISC |
| npm | [sisteransi](https://www.npmjs.com/package/sisteransi/v/1.0.5) | <code>1.0.5</code> | MIT |
| npm | [source-map](https://www.npmjs.com/package/source-map/v/0.6.1) | <code>0.6.1</code> | BSD-3-Clause |
| npm | [source-map-js](https://www.npmjs.com/package/source-map-js/v/1.2.1) | <code>1.2.1</code> | BSD-3-Clause |
| npm | [source-map-support](https://www.npmjs.com/package/source-map-support/v/0.5.21) | <code>0.5.21</code> | MIT |
| npm | [sqlite-vec](https://www.npmjs.com/package/sqlite-vec/v/0.1.9) | <code>0.1.9</code> | MIT OR Apache-2.0 (lockfile: MIT OR Apache) |
| npm | [sqlite-vec-darwin-arm64](https://www.npmjs.com/package/sqlite-vec-darwin-arm64/v/0.1.9) | <code>0.1.9</code> | MIT OR Apache-2.0 (lockfile: MIT OR Apache) |
| npm | [sqlite-vec-darwin-x64](https://www.npmjs.com/package/sqlite-vec-darwin-x64/v/0.1.9) | <code>0.1.9</code> | MIT OR Apache-2.0 (lockfile: MIT OR Apache) |
| npm | [sqlite-vec-linux-arm64](https://www.npmjs.com/package/sqlite-vec-linux-arm64/v/0.1.9) | <code>0.1.9</code> | MIT OR Apache-2.0 (lockfile: MIT OR Apache) |
| npm | [sqlite-vec-linux-x64](https://www.npmjs.com/package/sqlite-vec-linux-x64/v/0.1.9) | <code>0.1.9</code> | MIT OR Apache-2.0 (lockfile: MIT OR Apache) |
| npm | [sqlite-vec-windows-x64](https://www.npmjs.com/package/sqlite-vec-windows-x64/v/0.1.9) | <code>0.1.9</code> | MIT OR Apache-2.0 (lockfile: MIT OR Apache) |
| npm | [stackback](https://www.npmjs.com/package/stackback/v/0.0.2) | <code>0.0.2</code> | MIT |
| npm | [standardwebhooks](https://www.npmjs.com/package/standardwebhooks/v/1.1.1) | <code>1.1.1</code> | MIT |
| npm | [statuses](https://www.npmjs.com/package/statuses/v/2.0.2) | <code>2.0.2</code> | MIT |
| npm | [std-env](https://www.npmjs.com/package/std-env/v/4.2.0) | <code>4.2.0</code> | MIT |
| npm | [string-width](https://www.npmjs.com/package/string-width/v/4.2.3) | <code>4.2.3</code> | MIT |
| npm | [string_decoder](https://www.npmjs.com/package/string_decoder/v/1.1.1) | <code>1.1.1</code> | MIT |
| npm | [strip-ansi](https://www.npmjs.com/package/strip-ansi/v/6.0.1) | <code>6.0.1</code> | MIT |
| npm | [strip-final-newline](https://www.npmjs.com/package/strip-final-newline/v/4.0.0) | <code>4.0.0</code> | MIT |
| npm | [strtok3](https://www.npmjs.com/package/strtok3/v/10.3.5) | <code>10.3.5</code> | MIT |
| npm | [tar](https://www.npmjs.com/package/tar/v/7.5.22) | <code>7.5.22</code> | BlueOak-1.0.0 |
| npm | [tinybench](https://www.npmjs.com/package/tinybench/v/6.1.4) | <code>6.1.4</code> | MIT |
| npm | [tinyexec](https://www.npmjs.com/package/tinyexec/v/1.3.0) | <code>1.3.0</code> | MIT |
| npm | [tinyglobby](https://www.npmjs.com/package/tinyglobby/v/0.2.17) | <code>0.2.17</code> | MIT |
| npm | [toidentifier](https://www.npmjs.com/package/toidentifier/v/1.0.1) | <code>1.0.1</code> | MIT |
| npm | [token-types](https://www.npmjs.com/package/token-types/v/6.1.2) | <code>6.1.2</code> | MIT |
| npm | [tr46](https://www.npmjs.com/package/tr46/v/0.0.3) | <code>0.0.3</code> | MIT |
| npm | [tree-sitter-bash](https://www.npmjs.com/package/tree-sitter-bash/v/0.25.1) | <code>0.25.1</code> | MIT |
| npm | [ts-algebra](https://www.npmjs.com/package/ts-algebra/v/2.0.0) | <code>2.0.0</code> | MIT |
| npm | [tslib](https://www.npmjs.com/package/tslib/v/2.8.1) | <code>2.8.1</code> | 0BSD |
| npm | [tslog](https://www.npmjs.com/package/tslog/v/4.11.0) | <code>4.11.0</code> | MIT |
| npm | [type-is](https://www.npmjs.com/package/type-is/v/2.1.0) | <code>2.1.0</code> | MIT |
| npm | [typebox](https://www.npmjs.com/package/typebox/v/1.1.38) | <code>1.1.38</code> | MIT |
| npm | [typebox](https://www.npmjs.com/package/typebox/v/1.3.18) | <code>1.3.18</code> | MIT |
| npm | [typescript](https://www.npmjs.com/package/typescript/v/6.0.3) | <code>6.0.3</code> | Apache-2.0 |
| npm | [uhyphen](https://www.npmjs.com/package/uhyphen/v/0.2.0) | <code>0.2.0</code> | ISC |
| npm | [uint8array-extras](https://www.npmjs.com/package/uint8array-extras/v/1.5.0) | <code>1.5.0</code> | MIT |
| npm | [undici](https://www.npmjs.com/package/undici/v/8.10.2) | <code>8.10.2</code> | MIT |
| npm | [undici-types](https://www.npmjs.com/package/undici-types/v/8.9.0) | <code>8.9.0</code> | MIT |
| npm | [unicorn-magic](https://www.npmjs.com/package/unicorn-magic/v/0.3.0) | <code>0.3.0</code> | MIT |
| npm | [unpipe](https://www.npmjs.com/package/unpipe/v/1.0.0) | <code>1.0.0</code> | MIT |
| npm | [util-deprecate](https://www.npmjs.com/package/util-deprecate/v/1.0.2) | <code>1.0.2</code> | MIT |
| npm | [vary](https://www.npmjs.com/package/vary/v/1.1.2) | <code>1.1.2</code> | MIT |
| npm | [vite](https://www.npmjs.com/package/vite/v/8.2.2) | <code>8.2.2</code> | MIT |
| npm | [vitest](https://www.npmjs.com/package/vitest/v/5.0.0) | <code>5.0.0</code> | MIT |
| npm | [web-push](https://www.npmjs.com/package/web-push/v/3.6.7) | <code>3.6.7</code> | MPL-2.0 |
| npm | [web-streams-polyfill](https://www.npmjs.com/package/web-streams-polyfill/v/3.3.3) | <code>3.3.3</code> | MIT |
| npm | [web-tree-sitter](https://www.npmjs.com/package/web-tree-sitter/v/0.26.13) | <code>0.26.13</code> | MIT |
| npm | [webidl-conversions](https://www.npmjs.com/package/webidl-conversions/v/3.0.1) | <code>3.0.1</code> | BSD-2-Clause |
| npm | [whatwg-url](https://www.npmjs.com/package/whatwg-url/v/5.0.0) | <code>5.0.0</code> | MIT |
| npm | [which](https://www.npmjs.com/package/which/v/2.0.2) | <code>2.0.2</code> | ISC |
| npm | [which-command](https://www.npmjs.com/package/which-command/v/0.1.0) | <code>0.1.0</code> | MIT |
| npm | [which-module](https://www.npmjs.com/package/which-module/v/2.0.1) | <code>2.0.1</code> | ISC |
| npm | [why-is-node-running](https://www.npmjs.com/package/why-is-node-running/v/2.3.0) | <code>2.3.0</code> | MIT |
| npm | [wrap-ansi](https://www.npmjs.com/package/wrap-ansi/v/6.2.0) | <code>6.2.0</code> | MIT |
| npm | [wrap-ansi](https://www.npmjs.com/package/wrap-ansi/v/7.0.0) | <code>7.0.0</code> | MIT |
| npm | [wrappy](https://www.npmjs.com/package/wrappy/v/1.0.2) | <code>1.0.2</code> | ISC |
| npm | [ws](https://www.npmjs.com/package/ws/v/8.21.3) | <code>8.21.3</code> | MIT |
| npm | [y18n](https://www.npmjs.com/package/y18n/v/4.0.3) | <code>4.0.3</code> | ISC |
| npm | [y18n](https://www.npmjs.com/package/y18n/v/5.0.8) | <code>5.0.8</code> | ISC |
| npm | [yallist](https://www.npmjs.com/package/yallist/v/5.0.0) | <code>5.0.0</code> | BlueOak-1.0.0 |
| npm | [yaml](https://www.npmjs.com/package/yaml/v/2.9.0) | <code>2.9.0</code> | ISC |
| npm | [yargs](https://www.npmjs.com/package/yargs/v/15.4.1) | <code>15.4.1</code> | MIT |
| npm | [yargs](https://www.npmjs.com/package/yargs/v/17.7.3) | <code>17.7.3</code> | MIT |
| npm | [yargs-parser](https://www.npmjs.com/package/yargs-parser/v/18.1.3) | <code>18.1.3</code> | ISC |
| npm | [yargs-parser](https://www.npmjs.com/package/yargs-parser/v/21.1.1) | <code>21.1.1</code> | ISC |
| npm | [yocto-queue](https://www.npmjs.com/package/yocto-queue/v/1.2.2) | <code>1.2.2</code> | MIT |
| npm | [yoctocolors](https://www.npmjs.com/package/yoctocolors/v/2.2.0) | <code>2.2.0</code> | MIT |
| npm | [zod](https://www.npmjs.com/package/zod/v/4.4.3) | <code>4.4.3</code> | MIT |
| npm | [zod-to-json-schema](https://www.npmjs.com/package/zod-to-json-schema/v/3.25.2) | <code>3.25.2</code> | ISC |

## Python dependency inventory (207 external identities)

The six editable projects are not duplicated in this table: five are
first-party Policy-Gated Factory Robot Orchestrator Reference packages, and editable <code>gr00t</code> is
covered by the pinned Isaac-GR00T source notice above.

| Ecosystem | Package | Version | License / terms | Source |
|---|---|---:|---|---|
| python | [accelerate](https://pypi.org/project/accelerate/1.12.0/) | <code>1.12.0+pgfr.security1</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [aiohappyeyeballs](https://pypi.org/project/aiohappyeyeballs/2.6.1/) | <code>2.6.1</code> | PSF-2.0 | [PyPI](https://pypi.org/) |
| python | [aiohappyeyeballs](https://pypi.org/project/aiohappyeyeballs/2.7.1/) | <code>2.7.1</code> | PSF-2.0 | [PyPI](https://pypi.org/) |
| python | [aiohttp](https://pypi.org/project/aiohttp/3.14.3/) | <code>3.14.3</code> | Apache-2.0 AND MIT | [PyPI](https://pypi.org/) |
| python | [aiosignal](https://pypi.org/project/aiosignal/1.4.0/) | <code>1.4.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [albucore](https://pypi.org/project/albucore/0.0.17/) | <code>0.0.17</code> | MIT | [PyPI](https://pypi.org/) |
| python | [albumentations](https://pypi.org/project/albumentations/1.4.18/) | <code>1.4.18</code> | MIT | [PyPI](https://pypi.org/) |
| python | [annotated-doc](https://pypi.org/project/annotated-doc/0.0.4/) | <code>0.0.4</code> | MIT | [PyPI](https://pypi.org/) |
| python | [annotated-types](https://pypi.org/project/annotated-types/0.7.0/) | <code>0.7.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [annotated-types](https://pypi.org/project/annotated-types/0.8.0/) | <code>0.8.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [anthropic](https://pypi.org/project/anthropic/0.116.0/) | <code>0.116.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [antlr4-python3-runtime](https://pypi.org/project/antlr4-python3-runtime/4.9.3/) | <code>4.9.3</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [anyio](https://pypi.org/project/anyio/4.14.1/) | <code>4.14.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [anyio](https://pypi.org/project/anyio/4.14.2/) | <code>4.14.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [asttokens](https://pypi.org/project/asttokens/3.0.1/) | <code>3.0.1</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [async-timeout](https://pypi.org/project/async-timeout/5.0.1/) | <code>5.0.1</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [attrs](https://pypi.org/project/attrs/25.4.0/) | <code>25.4.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [attrs](https://pypi.org/project/attrs/26.1.0/) | <code>26.1.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [backports-asyncio-runner](https://pypi.org/project/backports-asyncio-runner/1.2.0/) | <code>1.2.0</code> | PSF-2.0 | [PyPI](https://pypi.org/) |
| python | [build](https://pypi.org/project/build/1.4.0/) | <code>1.4.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [certifi](https://pypi.org/project/certifi/2026.1.4/) | <code>2026.1.4</code> | MPL-2.0 | [PyPI](https://pypi.org/) |
| python | [certifi](https://pypi.org/project/certifi/2026.6.17/) | <code>2026.6.17</code> | MPL-2.0 | [PyPI](https://pypi.org/) |
| python | [certifi](https://pypi.org/project/certifi/2026.7.22/) | <code>2026.7.22</code> | MPL-2.0 | [PyPI](https://pypi.org/) |
| python | [cffi](https://pypi.org/project/cffi/2.0.0/) | <code>2.0.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [cffi](https://pypi.org/project/cffi/2.1.0/) | <code>2.1.0</code> | MIT-0 | [PyPI](https://pypi.org/) |
| python | [cfgv](https://pypi.org/project/cfgv/3.5.0/) | <code>3.5.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [charset-normalizer](https://pypi.org/project/charset-normalizer/3.4.4/) | <code>3.4.4</code> | MIT | [PyPI](https://pypi.org/) |
| python | [click](https://pypi.org/project/click/8.2.1/) | <code>8.2.1</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [click](https://pypi.org/project/click/8.4.2/) | <code>8.4.2</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [cloudpickle](https://pypi.org/project/cloudpickle/3.1.2/) | <code>3.1.2</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [colorama](https://pypi.org/project/colorama/0.4.6/) | <code>0.4.6</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [contourpy](https://pypi.org/project/contourpy/1.3.2/) | <code>1.3.2</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [cryptography](https://pypi.org/project/cryptography/50.0.0/) | <code>50.0.0</code> | Apache-2.0 OR BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [cuda-toolkit](https://pypi.nvidia.com/) | <code>13.1.1</code> | NVIDIA SDK terms | [NVIDIA Python index](https://pypi.nvidia.com/) |
| python | [cycler](https://pypi.org/project/cycler/0.12.1/) | <code>0.12.1</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [datasets](https://pypi.org/project/datasets/3.6.0/) | <code>3.6.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [decorator](https://pypi.org/project/decorator/5.2.1/) | <code>5.2.1</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [diffusers](https://pypi.jetson-ai-lab.io/sbsa/cu130/+simple/) | <code>0.36.0.dev0</code> | Apache-2.0 | [Jetson AI Lab index](https://pypi.jetson-ai-lab.io/sbsa/cu130/+simple/) |
| python | [dill](https://pypi.org/project/dill/0.3.8/) | <code>0.3.8</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [distlib](https://pypi.org/project/distlib/0.4.0/) | <code>0.4.0</code> | PSF-2.0 | [PyPI](https://pypi.org/) |
| python | [distro](https://pypi.org/project/distro/1.9.0/) | <code>1.9.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [dm-tree](https://pypi.org/project/dm-tree/0.1.8/) | <code>0.1.8</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [docstring-parser](https://pypi.org/project/docstring-parser/0.17.0/) | <code>0.17.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [docstring-parser](https://pypi.org/project/docstring-parser/0.18.0/) | <code>0.18.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [einops](https://pypi.org/project/einops/0.8.1/) | <code>0.8.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [eval-type-backport](https://pypi.org/project/eval-type-backport/0.3.1/) | <code>0.3.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [exceptiongroup](https://pypi.org/project/exceptiongroup/1.3.1/) | <code>1.3.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [executing](https://pypi.org/project/executing/2.2.1/) | <code>2.2.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [farama-notifications](https://pypi.org/project/farama-notifications/0.0.4/) | <code>0.0.4</code> | MIT | [PyPI](https://pypi.org/) |
| python | [fastapi](https://pypi.org/project/fastapi/0.139.0/) | <code>0.139.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [filelock](https://pypi.org/project/filelock/3.21.2/) | <code>3.21.2</code> | Unlicense | [PyPI](https://pypi.org/) |
| python | [flash-attn](https://pypi.jetson-ai-lab.io/sbsa/cu130/+simple/) | <code>2.8.4</code> | BSD-3-Clause | [Jetson AI Lab index](https://pypi.jetson-ai-lab.io/sbsa/cu130/+simple/) |
| python | [fonttools](https://pypi.org/project/fonttools/4.61.1/) | <code>4.61.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [frozenlist](https://pypi.org/project/frozenlist/1.8.0/) | <code>1.8.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [fsspec](https://pypi.org/project/fsspec/2025.3.0/) | <code>2025.3.0</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [googleapis-common-protos](https://pypi.org/project/googleapis-common-protos/1.75.4/) | <code>1.75.4</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [gymnasium](https://pypi.org/project/gymnasium/1.2.2/) | <code>1.2.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [h11](https://pypi.org/project/h11/0.16.0/) | <code>0.16.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [hf-xet](https://pypi.org/project/hf-xet/1.2.0/) | <code>1.2.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [httpcore](https://pypi.org/project/httpcore/1.0.9/) | <code>1.0.9</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [httpx](https://pypi.org/project/httpx/0.28.1/) | <code>0.28.1</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [httpx-sse](https://pypi.org/project/httpx-sse/0.4.3/) | <code>0.4.3</code> | MIT | [PyPI](https://pypi.org/) |
| python | [huggingface-hub](https://pypi.org/project/huggingface-hub/0.36.2/) | <code>0.36.2</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [identify](https://pypi.org/project/identify/2.6.16/) | <code>2.6.16</code> | MIT | [PyPI](https://pypi.org/) |
| python | [idna](https://pypi.org/project/idna/3.18/) | <code>3.18</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [imageio](https://pypi.org/project/imageio/2.37.2/) | <code>2.37.2</code> | BSD-2-Clause | [PyPI](https://pypi.org/) |
| python | [importlib-metadata](https://pypi.org/project/importlib-metadata/8.7.1/) | <code>8.7.1</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [iniconfig](https://pypi.org/project/iniconfig/2.3.0/) | <code>2.3.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [inquirerpy](https://pypi.org/project/inquirerpy/0.3.4/) | <code>0.3.4</code> | MIT | [PyPI](https://pypi.org/) |
| python | [ipython](https://pypi.org/project/ipython/8.38.0/) | <code>8.38.0</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [jedi](https://pypi.org/project/jedi/0.19.2/) | <code>0.19.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [jinja2](https://pypi.org/project/jinja2/3.1.6/) | <code>3.1.6</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [jiter](https://pypi.org/project/jiter/0.16.0/) | <code>0.16.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [jsonlines](https://pypi.org/project/jsonlines/4.0.0/) | <code>4.0.0</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [jsonschema](https://pypi.org/project/jsonschema/4.26.0/) | <code>4.26.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [jsonschema-specifications](https://pypi.org/project/jsonschema-specifications/2025.9.1/) | <code>2025.9.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [kiwisolver](https://pypi.org/project/kiwisolver/1.4.9/) | <code>1.4.9</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [lazy-loader](https://pypi.org/project/lazy-loader/0.4/) | <code>0.4</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [librt](https://pypi.org/project/librt/0.13.0/) | <code>0.13.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [lmdb](https://pypi.org/project/lmdb/1.7.5/) | <code>1.7.5</code> | OLDAP-2.8 | [PyPI](https://pypi.org/) |
| python | [markdown-it-py](https://pypi.org/project/markdown-it-py/4.0.0/) | <code>4.0.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [markupsafe](https://pypi.org/project/markupsafe/3.0.3/) | <code>3.0.3</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [matplotlib](https://pypi.org/project/matplotlib/3.10.1/) | <code>3.10.1</code> | Matplotlib license (PSF-derived) | [PyPI](https://pypi.org/) |
| python | [matplotlib-inline](https://pypi.org/project/matplotlib-inline/0.2.1/) | <code>0.2.1</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [mcp](https://pypi.org/project/mcp/1.29.0/) | <code>1.29.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [mdurl](https://pypi.org/project/mdurl/0.1.2/) | <code>0.1.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [ml-dtypes](https://pypi.org/project/ml-dtypes/0.5.4/) | <code>0.5.4</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [mpmath](https://pypi.org/project/mpmath/1.3.0/) | <code>1.3.0</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [msgpack](https://pypi.org/project/msgpack/1.2.1/) | <code>1.2.1</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [msgpack-numpy](https://pypi.org/project/msgpack-numpy/0.4.8/) | <code>0.4.8</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [multidict](https://pypi.org/project/multidict/6.7.1/) | <code>6.7.1</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [multiprocess](https://pypi.org/project/multiprocess/0.70.16/) | <code>0.70.16</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [mypy](https://pypi.org/project/mypy/1.20.2/) | <code>1.20.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [mypy-extensions](https://pypi.org/project/mypy-extensions/1.1.0/) | <code>1.1.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [networkx](https://pypi.org/project/networkx/3.4.2/) | <code>3.4.2</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [nodeenv](https://pypi.org/project/nodeenv/1.10.0/) | <code>1.10.0</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [numpy](https://pypi.org/project/numpy/1.26.4/) | <code>1.26.4</code> | BSD-3-Clause; bundled components require binary review | [PyPI](https://pypi.org/) |
| python | [nvidia-cublas](https://pypi.nvidia.com/) | <code>13.2.1.1</code> | NVIDIA SDK terms | [NVIDIA Python index](https://pypi.nvidia.com/) |
| python | [nvidia-cudnn-cu13](https://pypi.nvidia.com/) | <code>9.19.1.2</code> | NVIDIA SDK terms | [NVIDIA Python index](https://pypi.nvidia.com/) |
| python | [nvidia-cudss-cu13](https://pypi.nvidia.com/) | <code>0.7.1.6</code> | NVIDIA SDK terms | [NVIDIA Python index](https://pypi.nvidia.com/) |
| python | [omegaconf](https://pypi.org/project/omegaconf/2.3.0/) | <code>2.3.0</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [onnx](https://pypi.org/project/onnx/1.23.0/) | <code>1.23.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [onnx-ir](https://pypi.org/project/onnx-ir/0.2.0/) | <code>0.2.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [onnxscript](https://pypi.org/project/onnxscript/0.6.2/) | <code>0.6.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [opencv-python-headless](https://pypi.org/project/opencv-python-headless/4.11.0.86/) | <code>4.11.0.86</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [opentelemetry-api](https://pypi.org/project/opentelemetry-api/1.43.0/) | <code>1.43.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [opentelemetry-exporter-otlp-proto-common](https://pypi.org/project/opentelemetry-exporter-otlp-proto-common/1.43.0/) | <code>1.43.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [opentelemetry-exporter-otlp-proto-http](https://pypi.org/project/opentelemetry-exporter-otlp-proto-http/1.43.0/) | <code>1.43.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [opentelemetry-proto](https://pypi.org/project/opentelemetry-proto/1.43.0/) | <code>1.43.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [opentelemetry-sdk](https://pypi.org/project/opentelemetry-sdk/1.43.0/) | <code>1.43.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [opentelemetry-semantic-conventions](https://pypi.org/project/opentelemetry-semantic-conventions/0.64b0/) | <code>0.64b0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [packaging](https://pypi.org/project/packaging/26.0/) | <code>26.0</code> | Apache-2.0 OR BSD-2-Clause | [PyPI](https://pypi.org/) |
| python | [packaging](https://pypi.org/project/packaging/26.2/) | <code>26.2</code> | Apache-2.0 OR BSD-2-Clause | [PyPI](https://pypi.org/) |
| python | [pandas](https://pypi.org/project/pandas/2.2.3/) | <code>2.2.3</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [parso](https://pypi.org/project/parso/0.8.6/) | <code>0.8.6</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pathspec](https://pypi.org/project/pathspec/1.1.1/) | <code>1.1.1</code> | MPL-2.0 | [PyPI](https://pypi.org/) |
| python | [peft](https://pypi.org/project/peft/0.17.1/) | <code>0.17.1</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [pexpect](https://pypi.org/project/pexpect/4.9.0/) | <code>4.9.0</code> | ISC | [PyPI](https://pypi.org/) |
| python | [pfzy](https://pypi.org/project/pfzy/0.3.4/) | <code>0.3.4</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pillow](https://pypi.org/project/pillow/12.3.0/) | <code>12.3.0</code> | MIT-CMU | [PyPI](https://pypi.org/) |
| python | [platformdirs](https://pypi.org/project/platformdirs/4.7.0/) | <code>4.7.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pluggy](https://pypi.org/project/pluggy/1.6.0/) | <code>1.6.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pre-commit](https://pypi.org/project/pre-commit/4.5.1/) | <code>4.5.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [prompt-toolkit](https://pypi.org/project/prompt-toolkit/3.0.52/) | <code>3.0.52</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [propcache](https://pypi.org/project/propcache/0.4.1/) | <code>0.4.1</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [propcache](https://pypi.org/project/propcache/0.5.2/) | <code>0.5.2</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [protobuf](https://pypi.org/project/protobuf/6.33.5/) | <code>6.33.5</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [psutil](https://pypi.org/project/psutil/7.2.2/) | <code>7.2.2</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [ptyprocess](https://pypi.org/project/ptyprocess/0.7.0/) | <code>0.7.0</code> | ISC | [PyPI](https://pypi.org/) |
| python | [pure-eval](https://pypi.org/project/pure-eval/0.2.3/) | <code>0.2.3</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pyarrow](https://pypi.org/project/pyarrow/23.0.0/) | <code>23.0.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [pycparser](https://pypi.org/project/pycparser/3.0/) | <code>3.0</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [pydantic](https://pypi.org/project/pydantic/2.12.5/) | <code>2.12.5</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pydantic](https://pypi.org/project/pydantic/2.13.4/) | <code>2.13.4</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pydantic-core](https://pypi.org/project/pydantic-core/2.41.5/) | <code>2.41.5</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pydantic-core](https://pypi.org/project/pydantic-core/2.46.4/) | <code>2.46.4</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pydantic-settings](https://pypi.org/project/pydantic-settings/2.14.2/) | <code>2.14.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pygments](https://pypi.org/project/pygments/2.20.0/) | <code>2.20.0</code> | BSD-2-Clause | [PyPI](https://pypi.org/) |
| python | [pyjwt](https://pypi.org/project/pyjwt/2.13.0/) | <code>2.13.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pyparsing](https://pypi.org/project/pyparsing/3.3.2/) | <code>3.3.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pyproject-hooks](https://pypi.org/project/pyproject-hooks/1.2.0/) | <code>1.2.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pytest](https://pypi.org/project/pytest/8.4.2/) | <code>8.4.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pytest](https://pypi.org/project/pytest/9.0.3/) | <code>9.0.3</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pytest](https://pypi.org/project/pytest/9.1.1/) | <code>9.1.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pytest-aiohttp](https://pypi.org/project/pytest-aiohttp/1.1.1/) | <code>1.1.1</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [pytest-asyncio](https://pypi.org/project/pytest-asyncio/0.26.0/) | <code>0.26.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [pytest-asyncio](https://pypi.org/project/pytest-asyncio/1.4.0/) | <code>1.4.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [pytest-timeout](https://pypi.org/project/pytest-timeout/2.4.0/) | <code>2.4.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [python-dateutil](https://pypi.org/project/python-dateutil/2.9.0.post0/) | <code>2.9.0.post0</code> | BSD-3-Clause OR Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [python-dotenv](https://pypi.org/project/python-dotenv/1.2.2/) | <code>1.2.2</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [python-multipart](https://pypi.org/project/python-multipart/0.0.32/) | <code>0.0.32</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [pytz](https://pypi.org/project/pytz/2025.2/) | <code>2025.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pywin32](https://pypi.org/project/pywin32/312/) | <code>312</code> | PSF-2.0 | [PyPI](https://pypi.org/) |
| python | [pyyaml](https://pypi.org/project/pyyaml/6.0.3/) | <code>6.0.3</code> | MIT | [PyPI](https://pypi.org/) |
| python | [pyzmq](https://pypi.org/project/pyzmq/27.0.1/) | <code>27.0.1</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [referencing](https://pypi.org/project/referencing/0.37.0/) | <code>0.37.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [regex](https://pypi.org/project/regex/2026.1.15/) | <code>2026.1.15</code> | Apache-2.0 AND CNRI-Python | [PyPI](https://pypi.org/) |
| python | [requests](https://pypi.org/project/requests/2.33.0/) | <code>2.33.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [rich](https://pypi.org/project/rich/14.3.2/) | <code>14.3.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [rpds-py](https://pypi.org/project/rpds-py/0.30.0/) | <code>0.30.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [rpds-py](https://pypi.org/project/rpds-py/2026.6.3/) | <code>2026.6.3</code> | MIT | [PyPI](https://pypi.org/) |
| python | [ruff](https://pypi.org/project/ruff/0.15.1/) | <code>0.15.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [ruff](https://pypi.org/project/ruff/0.15.21/) | <code>0.15.21</code> | MIT | [PyPI](https://pypi.org/) |
| python | [safetensors](https://pypi.org/project/safetensors/0.7.0/) | <code>0.7.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [scikit-image](https://pypi.org/project/scikit-image/0.25.2/) | <code>0.25.2</code> | BSD-3-Clause AND bundled BSD/MIT notices | [PyPI](https://pypi.org/) |
| python | [scipy](https://pypi.org/project/scipy/1.15.3/) | <code>1.15.3</code> | BSD-3-Clause; bundled components require binary review | [PyPI](https://pypi.org/) |
| python | [setuptools](https://pypi.org/project/setuptools/83.0.0/) | <code>83.0.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [shtab](https://pypi.org/project/shtab/1.8.0/) | <code>1.8.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [six](https://pypi.org/project/six/1.17.0/) | <code>1.17.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [sniffio](https://pypi.org/project/sniffio/1.3.1/) | <code>1.3.1</code> | Apache-2.0 OR MIT | [PyPI](https://pypi.org/) |
| python | [sse-starlette](https://pypi.org/project/sse-starlette/3.4.6/) | <code>3.4.6</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [stack-data](https://pypi.org/project/stack-data/0.6.3/) | <code>0.6.3</code> | MIT | [PyPI](https://pypi.org/) |
| python | [starlette](https://pypi.org/project/starlette/1.3.1/) | <code>1.3.1</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [structlog](https://pypi.org/project/structlog/24.4.0/) | <code>24.4.0</code> | Apache-2.0 OR MIT | [PyPI](https://pypi.org/) |
| python | [sympy](https://pypi.org/project/sympy/1.14.0/) | <code>1.14.0</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [tensorrt](https://pypi.nvidia.com/) | <code>10.15.1.29</code> | NVIDIA SDK terms | [NVIDIA Python index](https://pypi.nvidia.com/) |
| python | [tensorrt-cu13](https://pypi.nvidia.com/) | <code>10.15.1.29</code> | NVIDIA SDK terms | [NVIDIA Python index](https://pypi.nvidia.com/) |
| python | [tensorrt-cu13-bindings](https://pypi.nvidia.com/) | <code>10.15.1.29</code> | NVIDIA SDK terms | [NVIDIA Python index](https://pypi.nvidia.com/) |
| python | [tensorrt-cu13-libs](https://pypi.nvidia.com/) | <code>10.15.1.29</code> | NVIDIA SDK terms | [NVIDIA Python index](https://pypi.nvidia.com/) |
| python | [termcolor](https://pypi.org/project/termcolor/3.2.0/) | <code>3.2.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [tifffile](https://pypi.org/project/tifffile/2025.5.10/) | <code>2025.5.10</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [tokenizers](https://pypi.org/project/tokenizers/0.22.2/) | <code>0.22.2</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [tomli](https://pypi.org/project/tomli/2.4.1/) | <code>2.4.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [torch](https://pypi.jetson-ai-lab.io/sbsa/cu130/+simple/) | <code>2.10.0</code> | BSD-3-Clause | [Jetson AI Lab index](https://pypi.jetson-ai-lab.io/sbsa/cu130/+simple/) |
| python | [torchvision](https://pypi.jetson-ai-lab.io/sbsa/cu130/+simple/) | <code>0.25.0</code> | BSD-3-Clause | [Jetson AI Lab index](https://pypi.jetson-ai-lab.io/sbsa/cu130/+simple/) |
| python | [tqdm](https://pypi.org/project/tqdm/4.67.3/) | <code>4.67.3</code> | MPL-2.0 AND MIT | [PyPI](https://pypi.org/) |
| python | [traitlets](https://pypi.org/project/traitlets/5.14.3/) | <code>5.14.3</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [transformers](https://pypi.org/project/transformers/4.57.6/) | <code>4.57.6+pgfr.security1</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [triton](https://pypi.jetson-ai-lab.io/sbsa/cu130/+simple/) | <code>3.5.0</code> | MIT | [Jetson AI Lab index](https://pypi.jetson-ai-lab.io/sbsa/cu130/+simple/) |
| python | [typeguard](https://pypi.org/project/typeguard/4.4.4/) | <code>4.4.4</code> | MIT | [PyPI](https://pypi.org/) |
| python | [types-pyyaml](https://pypi.org/project/types-pyyaml/6.0.12.20260518/) | <code>6.0.12.20260518</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [typing-extensions](https://pypi.org/project/typing-extensions/4.15.0/) | <code>4.15.0</code> | PSF-2.0 | [PyPI](https://pypi.org/) |
| python | [typing-extensions](https://pypi.org/project/typing-extensions/4.16.0/) | <code>4.16.0</code> | PSF-2.0 | [PyPI](https://pypi.org/) |
| python | [typing-inspection](https://pypi.org/project/typing-inspection/0.4.2/) | <code>0.4.2</code> | MIT | [PyPI](https://pypi.org/) |
| python | [tyro](https://pypi.org/project/tyro/0.9.17/) | <code>0.9.17</code> | MIT | [PyPI](https://pypi.org/) |
| python | [tzdata](https://pypi.org/project/tzdata/2025.3/) | <code>2025.3</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [urllib3](https://pypi.org/project/urllib3/2.7.0/) | <code>2.7.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [uvicorn](https://pypi.org/project/uvicorn/0.51.0/) | <code>0.51.0</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [uvicorn](https://pypi.org/project/uvicorn/0.52.1/) | <code>0.52.1</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [virtualenv](https://pypi.org/project/virtualenv/20.36.1/) | <code>20.36.1</code> | MIT | [PyPI](https://pypi.org/) |
| python | [wandb](https://pypi.org/project/wandb/0.30.0/) | <code>0.30.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [wcwidth](https://pypi.org/project/wcwidth/0.6.0/) | <code>0.6.0</code> | MIT | [PyPI](https://pypi.org/) |
| python | [xxhash](https://pypi.org/project/xxhash/3.6.0/) | <code>3.6.0</code> | BSD-3-Clause | [PyPI](https://pypi.org/) |
| python | [yarl](https://pypi.org/project/yarl/1.22.0/) | <code>1.22.0</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [yarl](https://pypi.org/project/yarl/1.24.2/) | <code>1.24.2</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [yarl](https://pypi.org/project/yarl/1.24.5/) | <code>1.24.5</code> | Apache-2.0 | [PyPI](https://pypi.org/) |
| python | [zipp](https://pypi.org/project/zipp/3.23.0/) | <code>3.23.0</code> | MIT | [PyPI](https://pypi.org/) |

## Python license-resolution notes

- <code>matplotlib-inline@0.2.1</code> is BSD-3-Clause and
  <code>mypy-extensions@1.1.0</code> is MIT, resolved from their official
  source distributions because the index metadata had no license value.
- <code>matplotlib</code> uses its PSF-derived project license;
  <code>python-dateutil</code> publishes BSD-3-Clause / Apache-2.0
  alternatives; <code>structlog</code> publishes Apache-2.0 / MIT
  alternatives; <code>aiohttp</code> publishes Apache-2.0 and MIT; and
  <code>tqdm</code> carries MPL-2.0 and MIT portions.
- <code>scikit-image</code> contains separately identified BSD/MIT portions.
  NumPy and SciPy source terms are BSD-3-Clause, but redistributed platform
  wheels or container layers can bundle OpenBLAS, LAPACK, GCC runtime,
  libquadmath, or other components. Their exact binary payload still requires
  scanner-level review before redistribution.
- Packages obtained from the NVIDIA Python index are governed by applicable
  NVIDIA SDK terms. Jetson AI Lab wheel rows use the named upstream project
  license; the wheel payload remains subject to binary-content verification.

## Review status

This inventory is complete for the committed npm and Python lock identities,
but formal NVIDIA/nSpect, security, export, asset-rights, codec, and binary
composition review is still pending. Absence of a finding here is not
clearance. If a packaged dependency or retrieved artifact ships its own
<code>LICENSE</code>, <code>NOTICE</code>, or copyright file, preserve that
file with the redistributed artifact.
