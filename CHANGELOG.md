# Changelog

All notable changes to Policy-Gated Factory Robot Orchestrator Reference are
documented here. Components retain their own package metadata, but no
calendar-versioned repository release has been published yet. A future release
entry must identify the exact Git commit and validated artifact digests rather
than inferring a release from component version strings.

## Unreleased

### Added

- An architecture diagram, a scene guide with Isaac Sim screenshots, and a project video.
- A source-and-training release path: users capture demonstrations, compute
  native-DROID statistics, fine-tune GR00T, and export a local checkpoint.
- Local checkpoint metadata and checksum validation shared by Thor profiles,
  the two-host bridge, and Isaac contracts. The simulation host can attest the
  selected checkpoint using metadata without copying its weights.
- Reproducible RTX workstation preparation, host preflight, immutable NVIDIA
  Isaac Sim image launch, exact read-only cell staging, lifecycle checks, and
  hardware-free contract tests.
- A two-host RTX/Jetson AGX Thor reference path for Fast DDS, SSH-forwarded
  GR00T policy/relay connections, local checkpoint identity and pinned upstream VLM retrieval,
  user-systemd service ownership, conformance checks, and a deterministic
  serial acceptance procedure.
- PGFR Console, PGFR Chat, workflow authoring/execution, OpenClaw gateway support,
  persistent mission evidence, and a documented operator-access boundary.
- A stopped-service
  [upgrade guide](docs/FULL-FORM-RENAME-UPGRADE.md) for the breaking product and
  project-prefix rename, including state migration and clean/upgrade validation.

### Changed

- Shortened the simulation and GR00T source paths to `reference/isaac-cell/`
  and `reference/groot/`, with matching installer, CI, and documentation paths.
  Removed unused scene variants and their standalone preview/debug helpers.
- Consolidated platform requirements into `INSTALL.md`, distribution scope into
  `THIRD-PARTY-NOTICES.md`, and validation history into `docs/VALIDATION.md`.

- Reproduction uses directly pulled NVIDIA Isaac Sim images with explicit
  license acceptance and mounted project files; GR00T remains native on Thor.
  Removed the unused project Thor Dockerfile. The native installer no longer
  requests the unversioned FFmpeg executable; dataset conversion has a separate
  encoder selection and preflight.

- Renamed the product from Industrial Claw to Policy-Gated Factory Robot
  Orchestrator Reference and changed the primary Python distribution, import,
  and executable from `industrial_claw` to
  `policy_gated_factory_robot_orchestrator_reference`.
- Renamed full-form reference, MCP-server, skill, OpenClaw-state, model, and
  simulation-bridge paths.
- Replaced the former project prefix across the public surface: `IC_*` became
  `PGFR_*`, `ic-*` became `pgfr-*`, `ic_*` became `pgfr_*`, and `/ic/*` became
  `/pgfr/*`. This includes Python distributions and imports, command-line tools,
  user services, containers, readiness markers, HTTP headers, OpenClaw IDs,
  persistent paths, JSON Schema IDs, and ROS 2 topics.
- Replaced project-owned certification-adjacent terminology with operational
  assurance and dispatch-policy language. The Console endpoint is now
  `/api/assurance`, and the UI, implementation names, runtime messages, and
  documentation use Assurance Claims, Policy Gates, Decision Gates,
  Prohibited Destinations, and Tracking/State Guards. Explicit statements that
  this reference is not a certified functional-safety system remain unchanged.
- PGFR Chat accepts explicitly configured OpenAI-compatible NVIDIA public or
  authorized internal endpoint/model/key tuples without routing by key prefix.
  OpenClaw remains a separately configured provider path.
- Parallel workflow dispatch now requires both physics verification and
  independent-B=1 verification. Physical dispatch remains non-retryable, while
  bundled read-only VLM proof steps use one explicitly bounded retry.
- Moved the standalone scripted-baseline launcher to NVIDIA Isaac Sim `6.0.1`
  at amd64 digest
  `sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb`.
  It now defaults to the headless WebRTC service, uses explicit user
  `1234:1234`, runs NVIDIA's bundled compatibility checker, and retains X11 as
  an explicit compatibility profile. The separate GR00T launcher keeps its
  accepted `6.0.0-dev2`/X11 pin.
- Added a one-command, scene-destructive scripted-baseline acceptance gate for
  15 fresh ROS payloads, one exactly-once left-Franka red-object move, final
  deterministic reset, and a current-run critical-log scan.
- Updated the repository's exact JavaScript dependency set to OpenClaw
  `2026.9.2` and Vitest `5`, regenerated the lockfile and third-party notice
  inventory, and verified the resulting install with `npm ci`, the plugin test
  suite, and `npm audit` (zero findings).

### Compatibility and validation boundary

- The product and project-prefix rename is a hard cutover with no runtime alias.
  Existing hosts must stop both legacy and PGFR services, back up and move
  persistent state/model paths, rename project environment keys, audit preserved
  files, recreate path-bound virtual environments, and rerender user units.
- Project fine-tuned weights and recorded datasets are not supplied or linked
  as release dependencies. Official upstream base-model and license references
  remain prerequisites. Older installations must explicitly export and select
  their local checkpoint before regenerating profiles and bridge contracts;
  legacy artifact metadata is preserved rather than rewritten in place.
- The public capture/training path requires its own hardware acceptance; prior
  development results do not qualify a user-generated dataset or checkpoint.
- The 2026-09-08 live RTX/Thor acceptance applies to the source snapshot
  recorded in [Validation](docs/VALIDATION.md#historical-validation). Current
  installation coverage and limitations are listed in
  [validation status](docs/VALIDATION.md#validation-status).
- GR00T serving in the accepted topology is bare metal on Thor from the pinned
  uv environment. The former Thor container path was dependency-qualification only,
  not a canonical or mission-accepted serving topology.
- A separate 2026-09-08 stable scripted-baseline qualification used isolated
  container `ic-isaac-sim-601-validation` with Isaac Sim `6.0.1`: NVIDIA's
  checker passed, the legacy `IC_CELL_UP` marker appeared, all legacy `/ic`
  topics were discovered, a real 1280-pixel rack-camera frame arrived, and
  reset succeeded. The final
  one-command gate passed as run `953020d69491` on ROS domain 42 with 15 fresh
  streams, exactly three commands, a verified red move at `off=0.017`,
  deterministic final reset, and zero current-run critical log findings.
- The hardened candidate tree was separately requalified on 2026-09-09 as run
  `d70ed0c3940f` on ROS domain 42: all 15 streams passed exact encoding,
  row-stride, and payload-length checks; the single red move verified at
  `off=0.001`; both exact resets passed; and exactly three unique command logs
  contained no critical marker. Before ROS publication, the wrapper also
  attested `ACCEPT_EULA=Y`, the NVIDIA telemetry opt-out, and all seven Kit
  privacy, telemetry, and crash-reporting arguments.
  These runs cover the standalone scripted profile. They do not cover
  Thor/GR00T or a connected WebRTC client. Recorded names and run IDs identify
  the tested configurations.
- OpenClaw `2026.9.2` was reconciled after the historical deployment record.
  The manifest's `validated_on: 2026-08-08` remains unchanged and is not live
  acceptance evidence for that upgraded OpenClaw version.

### Known limitations

- [Validation](docs/VALIDATION.md#validation-status) records coverage for
  two-host installation and upgrades, WebRTC, and the Thor Python environment.
- Concurrent arm execution requires explicit opt-in and acceptance after the
  serial mission. Software ordering checks alone do not validate a live run.
- Chat and Workflow control outside the documented trusted-LAN exception
  requires deployment-provided authentication, TLS, and per-user access controls.
  See [remote access](docs/REMOTE-ACCESS.md).
