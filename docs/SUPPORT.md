# Support and validation

This reference project targets one two-host NVIDIA deployment. A platform can
pass source and hardware-free tests without being accepted for the physical
mission, so the tables below separate supported configuration from measured
runtime evidence.

The public learned-motion path uses user-created data and a locally trained
checkpoint; project fine-tuned weights and full recorded datasets are not
release artifacts. Historical mission evidence below does not qualify a new
checkpoint. See [release scope](RELEASE-SCOPE.md) and the
[training recipe](../reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md).

## Deployment targets

| Component | Reference target | Not validated |
|---|---|---|
| Jetson control host | NVIDIA Jetson AGX Thor; aarch64 Ubuntu 24.04; Python 3.12; CUDA 13; ROS 2 Jazzy; bare-metal GR00T serving from the pinned uv environment | Other Jetson systems, amd64 control hosts, DGX systems, and containerized GR00T serving |
| RTX simulation host | x86_64 Ubuntu 24.04; NVIDIA RTX GPU; Docker; NVIDIA Container Runtime | Windows, WSL2, other GPUs, and Ubuntu 22.04 beyond preflight compatibility |
| Scripted simulator | Official Isaac Sim 6.0.1 container; headless WebRTC by default; X11 compatibility profile available | Local/offline asset startup and a completed WebRTC client acceptance session |
| Learned-action simulator | Isaac Sim 6.0.0-dev2 at the pinned digest; local X11 desktop | Migration of the GR00T path to Isaac Sim 6.0.1 or WebRTC |
| Operator system | Browser or MCP client with SSH access to the Jetson control host | Direct remote-write access outside the trusted-LAN profile |

The host preflight scripts reject known architecture, operating-system,
Python, and wheel mismatches. They are not a substitute for checking the full
Jetson, L4T, CUDA, ROS 2, driver, Docker, and network inventory before
installation.

## Evidence summary

| Date | Scope | Result |
|---|---|---|
| 2026-08-08 | Historical two-host GR00T manifest baseline | Recorded by `validated_on` in [`deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml) |
| 2026-09-08 | Live Jetson AGX Thor and RTX physical mission using the base revision plus then-uncommitted reproducibility fixes | Complete two-host mission accepted |
| 2026-09-08 | Standalone Isaac Sim 6.0.1 scripted baseline | Run `953020d69491` passed |
| 2026-09-09 | Hardened standalone Isaac Sim 6.0.1 candidate | Run `d70ed0c3940f` passed |

These records have different scopes. The manifest date is not evidence for
later dependency updates, the full-form rename, or the standalone Isaac Sim
6.0.1 qualification.

## Two-host mission evidence

The live mission on 2026-09-08 started from Git revision
`c985be23d56eaae5a2beea2f8893387c120a849f` with the then-uncommitted
reproducibility fixes present on both hosts.

| Host | Measured environment |
|---|---|
| Jetson control host | NVIDIA Jetson AGX Thor; aarch64 Ubuntu 24.04; L4T 39.2.1; kernel `6.8.12-1021-tegra`; NVIDIA driver `595.78`; CUDA 13.0 and 13.2 runtime packages; Python 3.12.3; ROS 2 Jazzy; Docker 29.7.2 |
| RTX simulation host | NVIDIA RTX PRO 6000 Blackwell Workstation Edition; x86_64 Ubuntu 24.04; kernel `7.0.0-31-generic`; NVIDIA driver `610.43.02`; Docker 29.8.0; NVIDIA Container Toolkit 1.20.0; local X11 display `:1` |
| Isaac Sim | `nvcr.io/nvidia/isaac-sim:6.0.0-dev2` at digest `sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9` |

The accepted GR00T services ran bare metal on Thor from the frozen uv
environment under `~/groot_shadow/Isaac-GR00T/`, followed by the
checksum-attested TorchCodec `0.10.0a0` LFS-wheel overlay. Because that overlay
is applied after the lock, the final environment is not entirely lock-resolved.
The public reproduction path uses this native Thor environment. The former
project Dockerfile for dependency checks has been removed; this release does
not provide a Thor inference image. Existing upstream VLM and CUDA diagnostic
images remain operator-retrieved prerequisites.

The physical mission validates the deterministic workflow and its recorded
state, journal, simulator logs, and camera evidence. It does not automatically
validate every Chat model, agent client, or provider combination. Validate each
selected model endpoint with a real completion, then run the required mission
and evidence checks.

The accepted hosts did not run the renamed source tree. A post-rename clean
installation and stopped-service upgrade must pass on both hosts before a
release can claim that scope.

## Standalone Isaac Sim qualification

The standalone profile uses the official Isaac Sim 6.0.1 amd64 image at digest
`sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb`.
It was tested before the prefix rename in the isolated
`ic-isaac-sim-601-validation` container without modifying the GR00T container.

Run `953020d69491` on 2026-09-08 passed NVIDIA's compatibility checker,
reported the legacy `IC_CELL_UP` marker, discovered all 15 required legacy
`/ic` ROS 2 streams, received a real 1280-pixel rack-camera frame, completed
one left-Franka red-object move at `off=0.017`, and restored the scene with
exactly three commands and no critical current-run log marker.

The hardened candidate was requalified on 2026-09-09 as run
`d70ed0c3940f`. All 15 streams passed exact encoding, row-stride, and payload
checks; the move verified at `off=0.001`; both resets passed; and exactly three
unique command logs contained no critical marker. The wrapper also attested
`ACCEPT_EULA=Y`, NVIDIA telemetry opt-out, and the seven Kit privacy,
telemetry, and crash-reporting arguments before ROS publication.

These runs cover the scripted baseline only. Their legacy names identify the
recorded evidence; they are not current runtime defaults. They do not validate
Thor, GR00T, the full two-host workflow, the rename upgrade, or a connected
WebRTC client.
Cold-online and warm-cache cloud-asset startup passed; the optional five-part
local Isaac asset pack has not been qualified.

RealVNC Server 7.12.1 was active on the measured RTX workstation and mirrored
the local X11 desktop. RealVNC is external workstation infrastructure, not an
Isaac Sim streaming dependency or a supported repository component.

## Open qualification items

- Repeat a clean two-host installation and the full physical mission from one
  immutable post-rename candidate commit, including explicit Isaac license
  acceptance and the native Thor dependency installation.
- Qualify dataset creation, the selected conversion codec build, and training
  in a fresh local environment; evaluate each user-trained checkpoint. The
  codec preflight checks build identity/features, not legal approval.
- Run the stopped-service rename upgrade and repeat the same acceptance checks.
- Connect and acceptance-test NVIDIA's native Isaac Sim WebRTC Streaming
  Client.
- Qualify the NVIDIA local asset-pack procedure before claiming offline
  startup.
- Resolve the Thor post-lock Python overlay before claiming a fully
  lock-resolved GR00T environment.
- Add separate compatibility profiles and evidence before claiming support for
  another operating system, GPU, Jetson product, or serving topology.

Use [Installation](../INSTALL.md) for deployment selection,
[Validate the two-host deployment](VALIDATION.md) for acceptance steps, and the
[deployment manifest](../deploy/reproducible-demo.yaml) for exact identities.
