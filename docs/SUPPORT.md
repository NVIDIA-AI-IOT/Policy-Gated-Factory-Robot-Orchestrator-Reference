# Validated deployment targets

This repository provides an extensible reference architecture. Its release-candidate
reproduction workflow targets one concrete two-host configuration. It becomes
an independently reproducible release only when the exact candidate is
published and then passes the documented clean-clone gate; committing source
alone does not create new hardware evidence. The table below distinguishes
measured evidence from portability that has not been tested.

| Component | Validated target | Other platforms |
|---|---|---|
| Brain host and GR00T serving | NVIDIA Jetson AGX Thor, aarch64, Ubuntu 24.04, Python 3.12, CUDA 13, ROS 2 Jazzy; GR00T policy and relay processes run bare metal from the pinned uv environment | amd64 brain hosts, DGX systems, other Jetson products, and containerized GR00T serving are not validated by the canonical installer |
| Simulation host | x86_64 Ubuntu 24.04 workstation with NVIDIA RTX GPU, Docker, and NVIDIA Container Runtime; standalone scripted baseline qualified on Isaac Sim 6.0.1, while the accepted two-host GR00T cohort remains on its separate dev2 pin | Ubuntu 22.04 is accepted by the published minimum profile but is not in the measured cohort; Windows, WSL2, and other GPUs are not validated |
| Isaac presentation | Standalone launcher defaults to NVIDIA's headless WebRTC service; local X11 remains an explicit compatibility profile and was used for the historical two-host mission | No native WebRTC client session or browser-viewer Compose deployment has been accepted; RealVNC is external desktop administration, not an Isaac streaming dependency |
| Operator host | Browser or MCP-capable client with SSH reach to the brain host | Platform-independent where the browser, SSH, and MCP client are supported |
| Control-plane Python packages | Installed and tested as part of the Thor workflow | Individual packages may run elsewhere, but that does not imply GR00T, ROS 2, or complete-demo support |

Unsupported targets are not accepted by this reference workflow. Existing
guards reject known architecture and OS mismatches in the brain prerequisites,
and architecture, Python, and wheel mismatches in Thor dependency setup. They
do not attest every Jetson AGX Thor, L4T, CUDA, and ROS identity before any
mutation. Run the documented read-only inventory and preflights, and compare
the result with the measured cohort below. Supporting another platform should
begin with an explicit compatibility profile and controlled reproduction
evidence, not by weakening the existing guards.

## Measured acceptance cohort

The complete two-host mission was accepted on 2026-09-08 from base Git revision
`c985be23d56eaae5a2beea2f8893387c120a849f` with the then-current uncommitted
reproducibility fixes applied on both hosts:

| Host | Measured environment |
|---|---|
| Brain | NVIDIA Jetson AGX Thor; aarch64 Ubuntu 24.04; L4T 39.2.1; kernel `6.8.12-1021-tegra`; NVIDIA driver `595.78`; CUDA 13.0 and 13.2 runtime packages; Python 3.12.3; ROS 2 Jazzy; Docker 29.7.2 |
| Simulation | NVIDIA RTX PRO 6000 Blackwell Workstation Edition; x86_64 Ubuntu 24.04; kernel `7.0.0-31-generic`; NVIDIA driver `610.43.02`; Docker 29.8.0; NVIDIA Container Toolkit 1.20.0; local X11 display `:1` |
| Isaac Sim | NVIDIA NGC `6.0.0-dev2` image pinned by digest `sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9` |

The fixes were subsequently committed together with the breaking full-form
product/package rename. The accepted hosts did not run that post-rename tree,
so neither the base revision nor the later source commit is, by itself, a
post-rename clean-clone acceptance record. Publish one immutable release
candidate and repeat both a clean installation and the stopped-service upgrade
in [`FULL-FORM-RENAME-UPGRADE.md`](FULL-FORM-RENAME-UPGRADE.md) before making
that claim. Do not update the deployment manifest's historical `validated_on`
date until a new corresponding live run actually passes.

The physical mission acceptance does not automatically accept every agent and
hosted-model combination. Each harness/provider path must pass a real completion,
the physical mission, and the authoritative state/journal/log checks in the
reproduction guide; a model-catalog or readiness response is not inference proof.

These versions are reproduction evidence, not permission to float dependencies
or a claim that every newer combination is compatible. In particular, the
complete two-host GR00T path still uses the listed early-development Isaac pin;
the standalone stable qualification below does not migrate or accept that
learned-policy path.
RealVNC Server 7.12.1 was active in service mode on port 5900 while the local
X11 desktop contained the live Isaac window. RealVNC remains external
workstation infrastructure rather than a supported Isaac Sim streaming
dependency.

The accepted Thor policy and relay services used the native frozen uv
environment under `~/groot_shadow/Isaac-GR00T/`, followed by the separately
checksum-attested TorchCodec `0.10.0a0` LFS-wheel overlay. The final environment
is therefore not entirely lock-resolved. The Thor Dockerfile qualified a
CUDA/dependency path, while the pinned perception VLM ran in its own container;
neither fact validates containerized GR00T serving. Treat the container path as
non-canonical until it passes its own full inference and two-host mission gate.

## Stable scripted-baseline qualification

A separate local qualification on 2026-09-08 exercised NVIDIA Isaac Sim 6.0.1
at amd64 digest
`sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb`
in isolated container `ic-isaac-sim-601-validation`; the existing dev2
container was not changed. NVIDIA's bundled compatibility checker reported
`PASSED`, the cell emitted `IC_CELL_UP`, all `/ic` topics were discovered, and
the rack camera supplied a real 1280-pixel frame. Scene reset succeeded.

The completed one-command gate reported
`IC_ISAAC_WORKSTATION_ACCEPTANCE_PASS` for run `953020d69491` on ROS domain 42.
It observed all 15 required fresh streams, published exactly three commands
(reset, one left-Franka red move, final reset), verified that move with
`off=0.017`, restored red/blue/green to the conveyor, and found zero critical
current-run log markers.

The hardened candidate tree was separately requalified on 2026-09-09 as run
`d70ed0c3940f` on ROS domain 42. All 15 streams passed exact encoding,
row-stride, and payload-length checks; the single red move verified at
`off=0.001`; both exact resets passed; and exactly three unique command logs
contained no critical marker. Before ROS publication, the wrapper also
attested `ACCEPT_EULA=Y`, the NVIDIA telemetry opt-out, and all seven Kit
privacy, telemetry, and crash-reporting arguments.
These are scripted-baseline results only: they do not test Thor, GR00T, the
full two-host workflow, a clean clone, the rename upgrade, or a connected
WebRTC client. The launcher selects headless/WebRTC by default, but remote
client connection acceptance remains open.

Cold-online and warm-cache cloud-asset behavior passed. The official Isaac Sim
6.0.1 five-part local asset pack is documented as an option in the workstation
runbook, but the repository has not qualified local/offline startup.
