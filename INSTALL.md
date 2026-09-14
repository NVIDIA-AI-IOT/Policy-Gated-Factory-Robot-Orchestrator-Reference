# Installation

Choose a deployment for the supplied reference cell. For a custom Isaac Sim
scene, start with [adapting the reference](README.md#adapt-the-reference-to-your-own-scene)
and update the robot, camera, and action mappings before using these installers.

| Deployment | Required systems | Runtime and instructions |
|---|---|---|
| Scripted cell | One x86_64 Linux workstation with an NVIDIA RTX GPU | Isaac Sim 6.0.1; follow the [RTX workstation runbook](ops/ISAAC-SIM-WORKSTATION.md) |
| Learned-motion orchestration | Jetson AGX Thor, an RTX workstation, and an operator browser | Native GR00T serving on Thor and Isaac Sim 6.0.0-dev2 with local X11 on RTX; follow the [two-host guide](docs/REPRODUCIBLE-DEMO.md) |

Review [supported hardware and qualification limits](docs/SUPPORT.md) first.
The installers check prerequisites but do not install the NVIDIA driver, Docker
Engine, or NVIDIA Container Toolkit.

Both paths pull the official Isaac Sim image from NVIDIA and mount project
files. Review the [Isaac Sim licensing overview](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/common/licenses-isaac-sim.html)
and [Additional Software and Materials License](https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/)
before pulling or launching it. Launchers require explicit `--accept-eula`.
See [release scope](docs/RELEASE-SCOPE.md) for runtime and training prerequisites.

## Standalone RTX scripted baseline

Follow the [workstation runbook](ops/ISAAC-SIM-WORKSTATION.md) to prepare the
host, launch Isaac Sim, open its stream, and run the scripted acceptance gate.
This path tests the cell and its ROS 2 interface without Thor or GR00T. It does
not install the operator console or qualify learned motion.

## Full Jetson Thor and RTX GR00T deployment

The release supplies training tools and instructions; provide your own dataset
and fine-tuned checkpoint. Complete these steps in order:

1. [Create demonstrations](reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/DATASET_CREATION.md).
2. [Fine-tune and evaluate GR00T](reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md) in a separate training environment.
3. [Export and transfer your checkpoint](reference/policy-gated-factory-robot-orchestrator-reference/groot/models/README.md) to Thor.
4. [Install and start the two-host system](docs/REPRODUCIBLE-DEMO.md), including its model providers and SSH bridge.
5. [Validate service readiness and complete missions](docs/VALIDATION.md) with your checkpoint.

The learned-motion profile uses a different Isaac Sim version from the scripted
baseline. Follow its pinned configuration and validate your own deployment;
historical development runs do not qualify a newly trained model.

For an existing installation using the former project names, follow the
[rename upgrade procedure](docs/FULL-FORM-RENAME-UPGRADE.md) before installing.

## Open PGFR Console

After the full system is running, use the [remote-access guide](docs/REMOTE-ACCESS.md)
to forward Console and Chat over SSH. Open <http://127.0.0.1:8600>; Chat is the
default view. Start a new conversation and request **Reset the scene**, then
wait for its verified result before starting a mission.
