# Policy-Gated Factory Robot Orchestrator Reference documentation

Policy-Gated Factory Robot Orchestrator Reference is organized around two primary software components: IC Spine,
the governed control and assurance service, and IC Console, the operator
interface. The repository also includes an Isaac Sim reference cell and a
fine-tuned GR00T action-execution path.

## Guides

| Topic | Document |
|---|---|
| Project overview and quick start | [`../README.md`](../README.md) |
| Repository structure | [`../STRUCTURE.md`](../STRUCTURE.md) |
| Architecture and execution flow | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Two-host installation and demo | [`REPRODUCIBLE-DEMO.md`](REPRODUCIBLE-DEMO.md) |
| RTX simulation-host prerequisites, launch, and remote viewing | [`../ops/ISAAC-SIM-WORKSTATION.md`](../ops/ISAAC-SIM-WORKSTATION.md) |
| IC Spine floor service | [`../ic-spine/README.md`](../ic-spine/README.md) |
| ROS 2 cell contract | [`floor-ros2-contract.md`](floor-ros2-contract.md) |
| GR00T action execution | [`../reference/policy-gated-factory-robot-orchestrator-reference/groot/README.md`](../reference/policy-gated-factory-robot-orchestrator-reference/groot/README.md) |
| GR00T N1.7 fine-tuning pipeline | [`../reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_ic_pipeline/README.md`](../reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_ic_pipeline/README.md) |
| Add an action endpoint | [`ENDPOINT-INTEGRATION.md`](ENDPOINT-INTEGRATION.md) |
| Security policy | [`../SECURITY.md`](../SECURITY.md) |
| Contributing | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
| Changelog | [`../CHANGELOG.md`](../CHANGELOG.md) |

## Visual references

- [`ic-spine-reference-architecture.png`](ic-spine-reference-architecture.png)
  presents the harness-independent IC Spine architecture.
- [`ic-spine-deployment.svg`](ic-spine-deployment.svg) shows the two-host
  reference deployment.
- [`IC_Demo.mp4`](IC_Demo.mp4) shows the reference mission in Isaac Sim.

Exact runtime versions, model revisions, ports, and service ownership are kept
in [`../deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml) rather
than duplicated across the guides.
