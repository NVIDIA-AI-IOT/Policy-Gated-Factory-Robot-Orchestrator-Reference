# Documentation

## Set up and run

- [Installation](../INSTALL.md) — choose the scripted RTX cell or the full Jetson and RTX deployment.
- [Isaac Sim scene guide](ISAAC-SIM-SCENE.md) — pictures of the robots, conveyor, totes, and rack.
- [RTX workstation runbook](../ops/ISAAC-SIM-WORKSTATION.md) — launch and validate the scripted cell.
- [Two-host deployment](REPRODUCIBLE-DEMO.md) — install and start GR00T, perception, and orchestration.

## Operate and troubleshoot

- [Console](../pgfr-console/README.md) — Chat, topology, inspection, and GPU views.
- [Model providers](MODEL-PROVIDERS.md) — configure Chat endpoints, credentials, and OpenClaw.
- [Remote access](REMOTE-ACCESS.md) — connect to Console, Chat, and Isaac Sim.
- [User services](../ops/systemd/README.md) — service ownership, configuration, and startup.
- [Deployment validation](VALIDATION.md) — check ROS 2, API contracts, complete missions, and validation status.
- [Rename upgrade](FULL-FORM-RENAME-UPGRADE.md) — migrate an existing installation from the former names.

## Create data and train

Use your own demonstrations and checkpoint; this release includes the tools and
instructions. Adapt the camera, state, and action mappings for a custom scene.

1. [Create a dataset](../reference/groot/groot_n1_7_pgfr_pipeline/docs/DATASET_CREATION.md).
2. [Fine-tune GR00T](../reference/groot/groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md).
3. [Prepare your checkpoint for serving](../reference/groot/models/README.md).

The [GR00T integration guide](../reference/groot/README.md)
links the Thor runtime, simulator executor, and pipeline validation instructions.

## Develop and integrate

- [Architecture](ARCHITECTURE.md) — responsibilities, request flow, and failure behavior.
- [Source map](../STRUCTURE.md) — component guides, services, packages, and schemas.
- [ROS 2 contract](floor-ros2-contract.md) — scene commands, results, state, and cameras.
- [Endpoint integration](ENDPOINT-INTEGRATION.md) — add robot actions, models, or agent harnesses.
- [Contributing](../CONTRIBUTING.md) — development setup, tests, and contribution requirements.

## Licensing and security

- [Deployment manifest](../deploy/reproducible-demo.yaml) — pinned runtimes, model identities, and ports.
- [Security](../SECURITY.md) — trust boundaries and reporting.
- [Asset provenance](ASSET-PROVENANCE.md) and [third-party notices](../THIRD-PARTY-NOTICES.md) — attribution and release review.
- [Changelog](../CHANGELOG.md) and [license](../LICENSE).
