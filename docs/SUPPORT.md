# Validated deployment targets

Industrial Claw is an extensible reference architecture, but the published
reproduction workflow validates one concrete two-host configuration. The table
below distinguishes that evidence from portability that has not been tested.

| Component | Validated target | Other platforms |
|---|---|---|
| Brain host and GR00T serving | NVIDIA Jetson AGX Thor, aarch64, Ubuntu 24.04, Python 3.12, CUDA 13, ROS 2 Jazzy | amd64 brain hosts, DGX systems, and other Jetson products are not validated by the canonical installer |
| Simulation host | x86_64 Linux workstation with NVIDIA RTX GPU, NVIDIA Container Runtime, X11, and the pinned Isaac Sim container | Windows, WSL2, and headless-only operation are not validated by the reference workflow |
| Operator host | Browser or MCP-capable client with SSH reach to the brain host | Platform-independent where the browser, SSH, and MCP client are supported |
| Control-plane Python packages | Installed and tested as part of the Thor workflow | Individual packages may run elsewhere, but that does not imply GR00T, ROS 2, or complete-demo support |

The host installers fail early outside their validated platforms rather than
silently applying a partially compatible configuration. Supporting another
platform should begin with an explicit compatibility profile and controlled
reproduction evidence, not by weakening those checks.
