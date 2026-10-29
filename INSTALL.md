# Installation

Choose a deployment for the supplied reference cell. For a custom Isaac Sim
scene, start with [adapting the reference](README.md#adapt-the-reference-to-your-own-scene)
and update the robot, camera, and action mappings before using these installers.

| Deployment | Required systems | Runtime and instructions |
|---|---|---|
| Scripted cell | One x86_64 Linux workstation with an NVIDIA RTX GPU | Isaac Sim 6.0.1; follow the [RTX workstation runbook](ops/ISAAC-SIM-WORKSTATION.md) |
| Learned-motion orchestration | Jetson AGX Thor, an RTX workstation, and an operator browser | Native GR00T serving on Thor and Isaac Sim 6.0.0-dev2 with local X11 on RTX; follow the [two-host guide](docs/REPRODUCIBLE-DEMO.md) |

## Platform requirements

| System | Reference configuration |
|---|---|
| RTX simulation host | x86_64 Ubuntu 24.04, NVIDIA RTX GPU, NVIDIA driver, Docker, and NVIDIA Container Toolkit; local X11 and `xauth` for learned motion |
| Jetson control host | Jetson AGX Thor, aarch64 Ubuntu 24.04, CUDA 13, Python 3.12, ROS 2 Jazzy, Docker, NVIDIA Container Runtime, and user systemd |
| Operator system | Browser or MCP client; SSH access to the Jetson host for the full deployment |

The scripted baseline needs no Jetson host. Its preflight also accepts Ubuntu
22.04, but runtime validation used 24.04. Windows, WSL2, other Jetson products,
and other control-host architectures have not been validated. Check the
[workstation requirements](ops/ISAAC-SIM-WORKSTATION.md#host-prerequisites) for CPU,
RAM, VRAM, and driver checks. The installers do not install the NVIDIA driver,
Docker Engine, or NVIDIA Container Toolkit.

The learned-motion profile has not been validated on Isaac Sim 6.0.1 or with
WebRTC. See [Validation](docs/VALIDATION.md#validation-status) for tested
configurations and known limitations.

## Software and model prerequisites

Both paths pull the official Isaac Sim image from NVIDIA and mount project
files. Review the [Isaac Sim licensing overview](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/common/licenses-isaac-sim.html)
and [Additional Software and Materials License](https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/)
before pulling or launching it. Launchers require explicit `--accept-eula`.

The full deployment installs GR00T natively on Thor and retrieves the documented
upstream VLM image. Dataset capture, conversion, and fine-tuning use separate
environments. Obtain the GR00T base model, runtime backbone, and perception VLM
under their applicable terms; configure the orchestration model using the
[provider guide](docs/MODEL-PROVIDERS.md). See [third-party notices](THIRD-PARTY-NOTICES.md)
for the software and model inventory and distribution scope.

## Standalone RTX scripted baseline

Follow the [workstation runbook](ops/ISAAC-SIM-WORKSTATION.md) to prepare the
host, launch Isaac Sim, open its stream, and run the scripted acceptance gate.
This path tests the cell and its ROS 2 interface without Thor or GR00T. It does
not install the operator console or qualify learned motion.

## Full Jetson Thor and RTX GR00T deployment

The release supplies training tools and instructions; provide your own dataset
and fine-tuned checkpoint. Complete these steps in order:

1. [Create demonstrations](reference/groot/groot_n1_7_pgfr_pipeline/docs/DATASET_CREATION.md).
2. [Fine-tune and evaluate GR00T](reference/groot/groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md) in a separate training environment.
3. [Export and transfer your checkpoint](reference/groot/models/README.md) to Thor.
4. [Install and start the two-host system](docs/REPRODUCIBLE-DEMO.md), including its model providers and SSH bridge.
5. [Validate service readiness and complete missions](docs/VALIDATION.md) with your checkpoint.

The learned-motion profile uses a different Isaac Sim version from the scripted
baseline. Follow its pinned configuration and validate your checkpoint on the
matching scene, cameras, and robot configuration.

If an existing PGFR installation has saved relay paths from an earlier source
layout, follow the [relay-path update](docs/REPRODUCIBLE-DEMO.md#update-an-existing-pgfr-relay-path)
before starting the updated deployment.

## Open PGFR Console

After the full system is running, use the [remote-access guide](docs/REMOTE-ACCESS.md)
to forward Console and Chat over SSH. Open <http://127.0.0.1:8600>; Chat is the
default view. Start a new conversation and request **Reset the scene**, then
wait for its verified result before starting a mission.
