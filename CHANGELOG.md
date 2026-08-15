# Changelog

All notable changes to Industrial Claw are documented here. The Python engine and the TypeScript Operator
Gateway evolve together but ship independent version numbers; releases combining both will use calendar
versioning (`YYYY.MM.DD`).

## Unreleased

### Added

- Initial commit — Industrial Claw bootstrap.
- OpenClaw operator gateway integration through a pinned package dependency;
  OpenClaw source is not vendored in this repository.
- Python orchestration engine (`ic-spine/`) — `BrainAgent`, `PerceptionAgent`, `ActionAgent`, pluggable input
  sources and action endpoints, Anthropic LLM + VLM clients, `EndpointState` + `pick_best` selection policy,
  Brain plan validation with retry-with-error-feedback. 38 unit tests passing.
- Foundation plan (T1–T14) under
  the foundation implementation plan (document since removed). T1–T9 complete; T10–T14 next.

### Planned

- Brain orchestration loop with three-tier retry/replan/escalate ladder.
- Run recorder writing `plan.json`, `events.jsonl`, and consulted-frame snapshots per mission.
- Python CLI entry point (`industrial_claw "<goal>"`).
- Integration test suite covering happy path + retry + replan + escalate.
- TypeScript ↔ Python bridge skill so operator messages from the Gateway reach the Python engine.

### Not yet shipped (subsequent plans)

- ROS 2 client + real Isaac Sim integration.
- NVIDIA Jetson Thor deployment with NemoClaw sandboxing.
- Local Cosmos / VILA inference on Thor.
- Multi-station factory floor + multi-Thor cluster.
