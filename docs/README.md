# Documentation

Use this index to find the shortest maintained guide for your task. Exact
runtime versions, container digests, model revisions, ports, and acceptance
identities are recorded in
[`deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml); individual
guides link to that manifest rather than redefining it.

## Getting started

| Document | Audience | Description |
|---|---|---|
| [Project overview](../README.md) | Evaluators and new contributors | Introduces the system, primary components, and current validation boundary. |
| [Installation](../INSTALL.md) | Deployers | Chooses between the standalone RTX scripted baseline and the full Thor plus RTX GR00T deployment, with the minimum readiness markers for each. |
| [Reproduce the full demo](REPRODUCIBLE-DEMO.md) | Deployment owners | Installs, starts, validates, and accepts the complete two-host reference deployment. |
| [Scripted Isaac Sim workstation](../ops/ISAAC-SIM-WORKSTATION.md) | RTX workstation operators | Runs the learned-policy-free Isaac Sim 6.0.1 baseline, WebRTC stream, and scripted acceptance gate. |
| [Configure model providers](MODEL-PROVIDERS.md) | Thor deployment owners | Selects a compatible PGFR Chat endpoint, stores credentials, configures OpenClaw, and verifies a real completion. |
| [Validated deployment targets](SUPPORT.md) | Release owners and evaluators | Defines measured hardware, software, and acceptance scope, including claims that remain open. |

## Operations

| Document | Audience | Description |
|---|---|---|
| [PGFR Spine](../pgfr-spine/README.md) | Service operators and developers | Installs and runs the governed floor service with mock or ROS 2 backends. |
| [PGFR Console](../pgfr-console/README.md) | Operators and UI developers | Runs the Chat, topology, mission, inspection, and telemetry interface. |
| [PGFR Chat](../servers/pgfr-chat/README.md) | Operators and backend integrators | Configures the chat gateway, model provider, CORS policy, and health checks. |
| [PGFR Workflows](../servers/pgfr-workflows/README.md) | Workflow authors and operators | Runs deterministic workflows and documents scheduling, tokens, and request contracts. |
| [Remote access](REMOTE-ACCESS.md) | Operators and network administrators | Configures SSH-forwarded access, read-only direct Console access, trusted-LAN Chat, and Isaac Sim viewing. |
| [User services](../ops/systemd/README.md) | Thor administrators | Describes user-systemd service ownership, environment files, and manual or appliance operation. |
| [Simulation-host bridge](../ops/systemd/simulation-host/README.md) | RTX and network administrators | Operates the SSH bridge between the simulation host and Thor-owned GR00T services; the bridge stops on uncertainty. |
| [Conformance kit](../packages/conformance-kit/README.md) | Deployment and release owners | Verifies the live PGFR Spine API and MCP handshake contracts before a mission. |
| [Rename upgrade](FULL-FORM-RENAME-UPGRADE.md) | Existing deployment owners | Migrates stopped installations from the former product name and `IC` project prefix to the current PGFR namespace. |
| [Security policy](../SECURITY.md) | Operators and security reviewers | Defines the current trust model, network boundaries, known limitations, and reporting scope. |

## Architecture and integration

| Document | Audience | Description |
|---|---|---|
| [Architecture](ARCHITECTURE.md) | Architects and integrators | Explains component responsibilities, deployment topology, closed-loop mission flow, and failure behavior. |
| [Repository structure](../STRUCTURE.md) | Contributors | Maps runtime relationships, source directories, and supported entry points. |
| [ROS 2 floor contract](floor-ros2-contract.md) | Robot and ROS developers | Defines command, result, feedback, floor-state, camera, and capability topics. |
| [Endpoint integration](ENDPOINT-INTEGRATION.md) | Robot, model, and agent integrators | Adds robot actions, AI providers, and agent harnesses without moving policy out of PGFR Spine. |
| [Schemas](../schemas/README.md) | API and protocol developers | Indexes the OpenAPI and JSON Schema contracts used across the system. |
| [Connectors](../connectors/README.md) | Integration developers | Describes connector packages and the resource-server boundary. |
| [Connector SDK](../packages/connector-sdk/README.md) | Connector authors | Provides the typed connector interfaces and implementation guidance. |
| [Servers](../servers/README.md) | Service developers | Explains the server boundary and lists Chat, Workflows, and MCP services. |
| [MCP server](../servers/policy-gated-factory-robot-orchestrator-reference-mcp/README.md) | Agent-harness integrators | Exposes the governed floor tools and playbook through MCP. |
| [OpenClaw plugin](../plugins/openclaw/README.md) | OpenClaw operators and developers | Documents the direct plugin tool surface and its verification behavior. |
| [Skills](../skills/README.md) | Agent-harness integrators | Describes the shipped orchestration skill and playbook packaging. |

## GR00T and development

| Document | Audience | Description |
|---|---|---|
| [Robot-cell reference implementation](../reference/policy-gated-factory-robot-orchestrator-reference/README.md) | Simulation and robotics developers | Introduces the Isaac cell and learned-action implementation. |
| [Isaac Sim cell](../reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/README.md) | Simulation developers | Describes the packaged factory scene, startup paths, and cell source layout. |
| [GR00T integration](../reference/policy-gated-factory-robot-orchestrator-reference/groot/README.md) | GR00T deployers and developers | Covers action serving, policy routing, concurrency behavior, and reproduction status. |
| [GR00T N1.7 pipeline](../reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/README.md) | Model developers | Introduces local dataset creation, fine-tuning, and user-checkpoint deployment. |
| [Dataset creation](../reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/DATASET_CREATION.md) | Model trainers | Capture demonstrations, convert them, and compute training statistics. |
| [Fine-tuning recipe](../reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md) | Model trainers | Records the training inputs, command sequence, and artifact outputs. |
| [Release scope](RELEASE-SCOPE.md) | Release owners and users | Defines source-only runtime delivery, separate local training, and upstream image/model prerequisites. |
| [Pipeline validation](../reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/VALIDATION.md) | Model and release engineers | Defines checks for the fine-tuning and serving pipeline. |
| [Thor runtime](../reference/policy-gated-factory-robot-orchestrator-reference/groot/thor/README.md) | Thor deployment engineers | Documents the pinned native runtime, dependency qualification, and smoke checks. |
| [GR00T models](../reference/policy-gated-factory-robot-orchestrator-reference/groot/models/README.md) | Model release owners | Explains model manifests, immutable identifiers, and verification. |
| [GR00T relay](../reference/policy-gated-factory-robot-orchestrator-reference/groot/relay/README.md) | Robotics developers | Describes relay responsibilities and the two-arm serving boundary. |
| [GR00T runtime](../reference/policy-gated-factory-robot-orchestrator-reference/groot/runtime/README.md) | Robotics developers | Documents the simulator-side executor and runtime artifacts. |
| [GR00T tests](../reference/policy-gated-factory-robot-orchestrator-reference/groot/tests/README.md) | Test and release engineers | Runs hardware-free contract tests and identifies hardware-dependent gates. |
| [Capture context](../reference/policy-gated-factory-robot-orchestrator-reference/groot/capture_context/README.md) | Dataset engineers | Records context capture used by the learned-action pipeline. |
| [Training assets](../reference/policy-gated-factory-robot-orchestrator-reference/groot/training/README.md) | Dataset and model engineers | Describes tracked training configuration and data provenance. |
| [Packages](../packages/README.md) | Python developers | Lists reusable SDK and conformance packages. |
| [Contributing](../CONTRIBUTING.md) | Contributors | Defines the development workflow, testing expectations, and contribution terms. |

## Project and reference

| Document | Audience | Description |
|---|---|---|
| [Deployment manifest](../deploy/README.md) | Release and deployment owners | Explains the machine-readable manifest containing pinned runtimes, artifacts, service ownership, and ports. |
| [Asset provenance](ASSET-PROVENANCE.md) | Release and compliance reviewers | Records tracked assets, remote Isaac assets, and the asset-related release gate. |
| [Changelog](../CHANGELOG.md) | Users and release owners | Lists user-visible changes, compatibility notes, and pending release work. |
| [Third-party notices](../THIRD-PARTY-NOTICES.md) | Legal and release reviewers | Records third-party software and artifact notices. |
| [License](../LICENSE) | All users | Apache License 2.0 terms for the repository. |

### Visual references

| Artifact | Description |
|---|---|
| [Dashboard screenshot](images/orchestration-console.png) | Orchestration Console with Chat selected. |
