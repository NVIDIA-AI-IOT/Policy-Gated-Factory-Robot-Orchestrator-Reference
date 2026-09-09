# Changelog

All notable changes to Policy-Gated Factory Robot Orchestrator Reference are
documented here. Components retain their own package metadata, but no
calendar-versioned repository release has been published yet. A future release
entry must identify the exact Git commit and validated artifact digests rather
than inferring a release from component version strings.

## Unreleased

### Added

- Reproducible RTX workstation preparation, host preflight, immutable NVIDIA
  Isaac Sim image launch, exact read-only cell staging, lifecycle checks, and
  hardware-free contract tests.
- A two-host RTX/Jetson AGX Thor reference path for Fast DDS, SSH-forwarded
  GR00T policy/relay connections, pinned model and VLM identities and retrieval,
  user-systemd service ownership, conformance checks, and a deterministic
  serial acceptance procedure.
- PGFR Console, PGFR Chat, workflow authoring/execution, OpenClaw gateway support,
  persistent mission evidence, and a documented operator-access boundary.
- A stopped-service
  [upgrade guide](docs/FULL-FORM-RENAME-UPGRADE.md) for the breaking product and
  project-prefix rename, including state migration and clean/upgrade validation.

### Changed

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
- The published Hugging Face model and dataset IDs retain their legacy
  `industrial-claw` slug because they are external immutable identifiers.
- The 2026-09-08 live RTX/Thor acceptance used the pre-rename source snapshot
  (the base revision plus then-uncommitted reproducibility fixes). The renamed
  tree has passed its documented hardware-free checks but has not yet completed
  a post-rename clean-clone and upgrade acceptance on both live hosts. Do not
  treat the historical date as that missing evidence.
- GR00T serving in the accepted topology is bare metal on Thor from the pinned
  uv environment. The Thor container path is dependency-qualification only,
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
  Neither run proves a post-rename clean clone, a Thor/GR00T path, or a
  connected WebRTC client. Those legacy names are retained here only to
  identify the historical evidence accurately.
- OpenClaw `2026.9.2` was reconciled after the historical deployment record.
  The manifest's `validated_on: 2026-08-08` remains unchanged and is not live
  acceptance evidence for that upgraded OpenClaw version.

### Known release work

- Connect and acceptance-test NVIDIA's native WebRTC Streaming Client; current
  evidence covers the headless service, readiness marker, and signaling
  listener, not a completed client session or browser-viewer deployment.
- Repeat the full two-host mixed-mode acceptance against the candidate commit.
  The Seam, workflow, MCP state machine, prompts, and tests now enforce the
  accepted Order744 pair order, but source-level enforcement is not a new live
  mission result and concurrent mode remains an explicit post-serial opt-in.
- Resolve the remaining Thor Python environment metadata conflicts without
  weakening the runtime pins or applying blind upgrades.
- Replace the provenance-tracked legacy architecture PNG through a controlled
  title-only source edit that preserves its technical content. Until such an
  edit is available, the current docs embed the accurate renamed SVG and keep
  the PNG only as a legacy artifact.
- Add authenticated, TLS-protected, per-user remote-write access before using
  Chat or Workflow control outside the explicit trusted-LAN lab exception.
