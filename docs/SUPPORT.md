# Validated deployment targets

This repository provides an extensible reference architecture. Its release-candidate
reproduction workflow targets one concrete two-host configuration and becomes
an independently published workflow only when the accepted tree is committed
and published. The table below distinguishes measured evidence from portability
that has not been tested.

| Component | Validated target | Other platforms |
|---|---|---|
| Brain host and GR00T serving | NVIDIA Jetson AGX Thor, aarch64, Ubuntu 24.04, Python 3.12, CUDA 13, ROS 2 Jazzy | amd64 brain hosts, DGX systems, and other Jetson products are not validated by the canonical installer |
| Simulation host | x86_64 Linux workstation with NVIDIA RTX GPU, NVIDIA Container Runtime, X11, and the pinned Isaac Sim container | Windows, WSL2, and headless-only operation are not validated by the reference workflow |
| Isaac presentation | Real local X11 display using the repository's pinned GUI-container launch | RealVNC may externally mirror that desktop but is not provisioned by the repository; NVIDIA WebRTC and its browser-viewer Compose deployment are not yet validated here |
| Operator host | Browser or MCP-capable client with SSH reach to the brain host | Platform-independent where the browser, SSH, and MCP client are supported |
| Control-plane Python packages | Installed and tested as part of the Thor workflow | Individual packages may run elsewhere, but that does not imply GR00T, ROS 2, or complete-demo support |

The host installers fail early outside their validated platforms rather than
silently applying a partially compatible configuration. Supporting another
platform should begin with an explicit compatibility profile and controlled
reproduction evidence, not by weakening those checks.

## Measured acceptance cohort

The complete two-host mission was accepted on 2026-09-08 from base Git revision
`c985be23d56eaae5a2beea2f8893387c120a849f` with the then-current uncommitted
reproducibility fixes applied on both hosts:

| Host | Measured environment |
|---|---|
| Brain | NVIDIA Jetson AGX Thor; aarch64 Ubuntu 24.04; L4T 39.2.1; kernel `6.8.12-1021-tegra`; NVIDIA driver `595.78`; CUDA 13.0 and 13.2 runtime packages; Python 3.12.3; ROS 2 Jazzy; Docker 29.7.2 |
| Simulation | NVIDIA RTX PRO 6000 Blackwell Workstation Edition; x86_64 Ubuntu 24.04; kernel `7.0.0-31-generic`; NVIDIA driver `610.43.02`; Docker 29.8.0; NVIDIA Container Toolkit 1.20.0; local X11 display `:1` |
| Isaac Sim | NVIDIA NGC `6.0.0-dev2` image pinned by digest `sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9` |

Because the accepted fixes are still uncommitted, that exact tree cannot yet be
reproduced from a clean GitHub clone of the base revision. Publish the complete
tree at one immutable commit or tag before describing this as an independent
clean-clone reproduction. Commit equality alone is not sufficient while tracked
diffs or untracked runtime files remain.

The physical mission acceptance does not automatically accept every agent and
hosted-model combination. Each harness/provider path must pass a real completion,
the physical mission, and the authoritative state/journal/log checks in the
reproduction guide; a model-catalog or readiness response is not inference proof.

These versions are reproduction evidence, not permission to float dependencies
or a claim that every newer combination is compatible. The Isaac image is an
early-development compatibility pin; migration to NVIDIA's current stable
release and headless WebRTC path requires a separate full regression run.
RealVNC Server 7.12.1 was active in service mode on port 5900 while the local
X11 desktop contained the live Isaac window. RealVNC remains external
workstation infrastructure rather than a supported Isaac Sim streaming
dependency.
