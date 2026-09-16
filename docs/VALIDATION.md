# Validate the two-host deployment

Use this guide after installing both hosts and starting their services. Run
the startup checks before the tests that change the simulated scene.

| Validation | Changes the scene | Required result |
|---|---:|---|
| ROS graph and payload | No | Live publisher, subscriber, payload, and camera topics |
| PGFR Spine and MCP conformance | No; policy-refused probes are expected | `CERTIFIED: 9/9` and `CERTIFIED: 11/11` |
| Serial reference mission | Yes | 20 recorded operations, eight verified dispatches, nine visual proofs |
| Mixed-color concurrent mission | Yes | Exact three-pair sequence with proof after each pair |

The shipped profile denies parallel dispatch by default. `PGFR_GROOT_PARALLEL_ENABLED=0` and
`PGFR_GROOT_FLEXIBLE_ORDER=0` keep the first acceptance run serial. No component
automatically redispatches a physical command. The Workflow runner executes a
physical `dispatch_task` once, even when a step declares retries; only its
read-only visual checks may use a separately bounded retry.

PGFR Chat can accept one explicit retry after a failed move only when a fresh
source-camera check and the authoritative floor state both confirm the exact
object at its original source. The MCP server likewise requires its pending
source-region proof gate to clear and limits a certified action to two total
attempts. Neither path invokes the second dispatch itself. A delivery-uncertain
result must be reconciled before an operator or agent requests another action.

## Contents

- [Check the ROS graph](#check-the-ros-graph)
- [Run conformance checks](#run-conformance-checks)
- [Run the serial reference mission](#run-the-serial-reference-mission)
- [Check the final state](#check-the-final-state)
- [Check Isaac Sim](#check-isaac-sim)
- [OpenClaw acceptance boundary](#openclaw-acceptance-boundary)
- [Optional mixed-color concurrent revalidation](#optional-mixed-color-concurrent-revalidation)
- [Acceptance checklist](#acceptance-checklist)
- [Validation status](#validation-status)
- [Historical validation](#historical-validation)

## Check the ROS graph

Run these commands on the Jetson control host. Disable the ROS CLI daemon so a
cached graph cannot satisfy the checks:

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference/ops/fastdds-multi-host.xml"
export ROS2CLI_NO_DAEMON=1
ros2 topic info -v /pgfr/floor_state  # require Publisher count: 1
ros2 topic info -v /pgfr/command      # require Subscription count: 1
timeout 15 ros2 topic echo /pgfr/floor_state std_msgs/msg/String --once
ros2 topic list | grep -E '^/pgfr/(floor_state|result|feedback)$|^/(table_cam|inspect_cam|inspect_vlm_cam|rack_cam|outside_cam|outside_right_cam|wrist_cam|wrist_right_cam)/image_raw$'
```

## Run conformance checks

Install the conformance kit in its own environment. Run both the live PGFR Spine
and MCP handshake checks before dispatching a mission. The checks are read-only
or deliberately policy-refused:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
python3.12 -m venv packages/conformance-kit/.venv
packages/conformance-kit/.venv/bin/pip install -e \
  'packages/conformance-kit[mcp]'
packages/conformance-kit/.venv/bin/pgfr-conformance run \
  --target http://127.0.0.1:8766
packages/conformance-kit/.venv/bin/pgfr-conformance mcp \
  --command \
  "$PWD/servers/policy-gated-factory-robot-orchestrator-reference-mcp/.venv/bin/pgfr-mcp"
```

Require `CERTIFIED: 9/9` from the PGFR Spine check and `CERTIFIED: 11/11` from the
MCP check.

## Run the serial reference mission

The deterministic `full-groot-dual-tote` workflow exercises PGFR Spine, both
GR00T serving paths, the VLM proof gates, both tote hauls, and the journal. It
uses six serial GR00T moves, each followed by fresh visual proof. Do not use a
mixed-color concurrent prompt as the first physical acceptance.

Before every run, open **Chat** in PGFR Console, start a new conversation, and
enter **`Reset the scene`**. Reset is operator-gated; Chat must wait for the
verified result before issuing a mission action. A successful reset restores
the canonical `groot_three_object` layout, with both totes on the work tables
in front of the Franka arms. Reset restores the complete simulated cell.

If Console Chat is unavailable, issue the equivalent explicit operator action
locally on the Jetson control host:

```bash
curl --fail-with-body --silent --show-error \
  --output /tmp/pgfr-reset-response.json \
  -X POST http://127.0.0.1:8766/v1/dispatch \
  -H 'Content-Type: application/json' \
  -H 'x-role: operator' \
  -d '{"action":"reset_scene","endpoint":"mobilebot","scene_profile":"groot_three_object","arm":"both","color":"red","layout_left":3,"layout_right":3,"seed":31302}'
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d,indent=2)); sys.exit(0 if d.get("verified") is True else 1)' \
  /tmp/pgfr-reset-response.json
```

Run the workflow through its loopback-only guarded endpoint:

```bash
(
set -euo pipefail
WORKFLOWS_TOKEN="$(sed -n 's/^PGFR_WORKFLOWS_TOKEN=//p' \
  "$HOME/.config/pgfr-spine/workflows.env" | tail -n 1)"
: "${WORKFLOWS_TOKEN:=console}"
curl --fail-with-body --silent --show-error \
  --output /tmp/pgfr-reference-mission-response.json \
  -X POST \
  http://127.0.0.1:8610/api/workflows/full-groot-dual-tote/run \
  -H 'Origin: http://127.0.0.1:8600' \
  -H "X-PGFR-Workflows: $WORKFLOWS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"params":{}}'
MISSION_ID="$(
  python3 -c '
import json, re, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data.get("ok") is True and data.get("degraded") is False, data
assert data.get("workflow") == "full-groot-dual-tote", data
assert data.get("started_steps") == 20, data
timeline = data.get("timeline")
assert isinstance(timeline, list) and len(timeline) == 20, data
dispatches = [step for step in timeline if step.get("tool") == "dispatch_task"]
proofs = [step for step in timeline if step.get("tool") == "check_predicate"]
assert len(dispatches) == 8, dispatches
assert all(step.get("ok") is True and (step.get("response") or {}).get("verified") is True for step in dispatches), dispatches
assert len(proofs) == 9, proofs
assert all(step.get("ok") is True and (step.get("response") or {}).get("answer") == "yes" for step in proofs), proofs
mission_id = data.get("mission_id")
if not isinstance(mission_id, str) or not re.fullmatch(r"wf-full-groot-dual-tote-[0-9a-f]{8}", mission_id):
    raise SystemExit("workflow returned an invalid mission_id")
print(json.dumps(data, indent=2), file=sys.stderr)
print(mission_id)
' /tmp/pgfr-reference-mission-response.json
)"
printf '%s\n' "$MISSION_ID" > /tmp/pgfr-reference-mission-id
unset WORKFLOWS_TOKEN
)
```

The command stores the validated mission ID outside the checkout.

## Check the final state

On the Jetson control host, verify the authoritative floor state, journal
entries for the exact mission, and service health:

```bash
(
  set -euo pipefail
  MISSION_ID="$(cat /tmp/pgfr-reference-mission-id)"
  [[ "$MISSION_ID" =~ ^wf-full-groot-dual-tote-[0-9a-f]{8}$ ]] || {
    echo 'invalid saved mission ID' >&2
    exit 1
  }
curl --fail --silent --show-error \
  --output /tmp/pgfr-final-floor-state.json \
  -X POST http://127.0.0.1:8766/v1/floor-state \
  -H 'Content-Type: application/json' -d '{}'
  python3 -c '
import json, sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
colors = ("red", "blue", "green")
assert state.get("conveyor_1") == [], state
assert state.get("tote_on_rack") is True, state
assert state.get("tote_r_on_rack") is True, state
for tote_name in ("tote", "tote_r"):
    tote = state.get(tote_name)
    assert isinstance(tote, dict), state
    assert all(tote.get(color) == "in" for color in colors), state
print(json.dumps(state, indent=2))
' /tmp/pgfr-final-floor-state.json
curl --fail --silent --show-error \
  --output /tmp/pgfr-reference-mission-detail.json \
  "http://127.0.0.1:8766/v1/missions/$MISSION_ID?limit=100"
  python3 -c '
import json, sys
detail = json.load(open(sys.argv[1], encoding="utf-8"))
mission_id = sys.argv[2]
assert detail.get("mission_id") == mission_id, detail
operations = detail.get("operations")
assert isinstance(operations, list) and len(operations) == 20, detail
assert all(op.get("mission_id") == mission_id for op in operations), detail
dispatches = [op for op in operations if op.get("op") == "dispatch"]
proofs = [op for op in operations if op.get("op") == "verify"]
assert len(dispatches) == 8, dispatches
assert all(op.get("verified") is True and (op.get("result") or {}).get("verified") is True for op in dispatches), dispatches
assert len(proofs) == 9, proofs
assert all((op.get("result") or {}).get("answer") == "yes" for op in proofs), proofs
assert all(str((op.get("result") or {}).get("evidence") or "").strip() for op in proofs), proofs
assert all(str((op.get("result") or {}).get("source_used") or "").strip() for op in proofs), proofs
assert all(str(op.get("request_id") or "").strip() for op in proofs), proofs
assert all(str(op.get("frame") or "").startswith("frames/") for op in proofs), proofs
assert len({op.get("request_id") for op in operations}) == 20, operations
print(json.dumps({"mission_id": mission_id, "operations": len(operations), "verified_dispatches": len(dispatches), "visual_proofs": len(proofs)}, indent=2))
' /tmp/pgfr-reference-mission-detail.json "$MISSION_ID"
test -s "$HOME/pgfr-journal/journal.jsonl"
wc -l "$HOME/pgfr-journal/journal.jsonl"
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
ops/thor-deploy.sh --check
)
```

## Check Isaac Sim

On the RTX simulation host, check the current container run for startup
markers and project errors. The launcher refuses to reuse an existing
`isaac-sim` container, so its `StartedAt` timestamp scopes the log to this run:

```bash
(
  set -euo pipefail
  test "$(docker inspect isaac-sim \
    --format 'status={{.State.Status}} restarts={{.RestartCount}} oom={{.State.OOMKilled}}')" = \
    'status=running restarts=0 oom=false'
  ISAAC_STARTED_AT="$(docker inspect isaac-sim --format '{{.State.StartedAt}}')"
  ISAAC_LOG="$(mktemp)"
  trap 'rm -f "$ISAAC_LOG"' EXIT
  docker logs --since "$ISAAC_STARTED_AT" isaac-sim >"$ISAAC_LOG" 2>&1
  grep -F 'PGFR_GROOT_RUNTIME_READY' "$ISAAC_LOG"
  grep -F 'STARTUP_DONE full_scene+runner' "$ISAAC_LOG"
  if grep -E '[A-Z][A-Z0-9_]*_(ERR|ERROR)(:|[[:space:]=]|$)' \
    "$ISAAC_LOG"; then
    echo 'Isaac Sim current run contains a project error marker' >&2
    exit 1
  fi
)
```

Require both host checks to succeed. The final floor state and camera proof
must show both loaded totes on the rack; model prose alone is not acceptance
evidence.

## OpenClaw acceptance boundary

The provider completion in [`MODEL-PROVIDERS.md`](MODEL-PROVIDERS.md#test-a-completion)
validates hosted-model inference. The conformance commands above validate the
MCP server independently. The shipped OpenClaw profile exposes physical
dispatch tools, so prompt wording is not an authorization boundary and no
OpenClaw chat request is a non-actuating smoke test.

Exercise an OpenClaw and model combination only as a deliberate physical
acceptance with an operator watching the cell, or after adding a separately
reviewed read-only MCP profile. A successful deterministic workflow run does
not certify OpenClaw.

## Optional mixed-color concurrent revalidation

Mixed-color operation is an explicit capability mode, not the shipped default.
Attempt it only after the serial acceptance above and both B=1 GR00T servers
have passed readiness.

PGFR Spine is the authoritative route guard, Workflows has a separate
pre-dispatch guard, and OpenClaw's MCP child enforces the certified sequence
and visual-proof state. PGFR Spine and Workflows must receive both capability
flags; the MCP child requires those flags plus
`PGFR_CERTIFIED_GROOT_ORDER=1`. Stop the services, update only the preserved
installed environment and configuration copies, validate the OpenClaw
configuration, and restart them together:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
systemctl --user stop \
  pgfr-openclaw.service pgfr-workflows.service pgfr-seam.service
for ENV_FILE in \
  "$HOME/.config/pgfr-spine/seam.env" \
  "$HOME/.config/pgfr-spine/workflows.env"; do
  for FLAG in PGFR_GROOT_PARALLEL_ENABLED PGFR_GROOT_FLEXIBLE_ORDER; do
    if grep -q "^$FLAG=" "$ENV_FILE"; then
      sed -i "s/^$FLAG=.*/$FLAG=1/" "$ENV_FILE"
    else
      printf '%s=1\n' "$FLAG" >>"$ENV_FILE"
    fi
  done
  grep -qx 'PGFR_GROOT_PARALLEL_ENABLED=1' "$ENV_FILE"
  grep -qx 'PGFR_GROOT_FLEXIBLE_ORDER=1' "$ENV_FILE"
done
set -a
. "$HOME/.config/pgfr-spine/openclaw.env"
set +a
./node_modules/.bin/openclaw config set \
  mcp.servers.pgfr-floor.env.PGFR_CERTIFIED_GROOT_ORDER '"1"' --strict-json
./node_modules/.bin/openclaw config set \
  mcp.servers.pgfr-floor.env.PGFR_GROOT_PARALLEL_ENABLED '"1"' --strict-json
./node_modules/.bin/openclaw config set \
  mcp.servers.pgfr-floor.env.PGFR_GROOT_FLEXIBLE_ORDER '"1"' --strict-json
./node_modules/.bin/openclaw config validate
systemctl --user start \
  pgfr-seam.service pgfr-workflows.service pgfr-openclaw.service
systemctl --user is-active \
  pgfr-seam.service pgfr-workflows.service pgfr-openclaw.service
for UNIT in pgfr-seam.service pgfr-workflows.service; do
  PID="$(systemctl --user show --property MainPID --value "$UNIT")"
  test "$PID" -gt 0
  tr '\0' '\n' <"/proc/$PID/environ" | \
    grep -Ex 'PGFR_GROOT_(PARALLEL_ENABLED|FLEXIBLE_ORDER)=1' | \
    sort -u | grep -c '^' | grep -qx '2'
done
curl --fail http://127.0.0.1:8766/v1/health
curl --fail http://127.0.0.1:8610/api/health
ops/thor-deploy.sh --check
```

Do not set only the MCP child flags: PGFR Spine and Workflows will refuse the
route. Changing only the service environment does not authorize the MCP agent
to leave its serial fallback.

The `full-groot-dual-tote-concurrent` workflow accepts only this sequence:

1. left blue with right green;
2. left green with right red; and
3. left red with right blue.

Same-color, partial, skipped, out-of-order, and repeated pairs are refused by
PGFR Spine before ROS contact. Submit this goal through PGFR Chat using the
`openclaw` backend:

> Reset and inspect the simulated cell. Pick left blue and right green
> together, then left green and right red together, then left red and right
> blue together. Verify both totes after each pair. Finally, haul both totes to
> the rack and verify completion.

This is a separate end-to-end harness acceptance. Check the floor state,
journal, and simulator logs for this run, including all three pair results,
their visual proofs, both hauls, and final rack verification. Use this run's
mission ID; the serial workflow's fixed mission-ID and operation-count
assertions above do not apply.

## Acceptance checklist

- PGFR Spine health reports a live ROS context and fresh required signals.
- All required camera topics produce changing frames.
- The VLM returns structured evidence from a fresh recorded frame.
- Both GR00T profiles report the same checkpoint identity.
- Both relays and bridge-derived readiness records are valid.
- Scene reset restores both three-object work areas and the executor home state.
- Every PGFR Spine dispatch returns `dispatched:true` and `verified:true`
  before its required fresh visual proof and the next transaction.
- Both tote hauls complete without displacing their contents.
- Final visual verification confirms the loaded totes on the rack.
- The mission journal contains every action, result, duration, and VLM frame.

The expected serial acceptance flow is reset and visual inspection, six
certified serial placements with proof after each, sequential tote hauls, rack
verification, and retention of the complete journal.

## Validation status

Automated checks cover software contracts and package installation. Live results
apply to the hardware, source revision, simulator profile, and checkpoint used
in each [recorded run](#historical-validation). See [Installation](../INSTALL.md)
for the reference configurations.

| Area | Coverage and limitations |
|---|---|
| Two-host installation and upgrade | A complete mission is recorded for an earlier source snapshot. End-to-end acceptance of a clean RTX/Thor installation and an upgraded installation is not recorded for the current release. Both paths require the checks above against the same Git commit and checkpoint. |
| Dataset capture and training | Fresh capture, conversion, training, and checkpoint evaluation require validation on the target scene. Training time and VRAM requirements have not been benchmarked for the public training path. |
| Isaac Sim profiles | Recorded GR00T runs use 6.0.0-dev2 with X11. The 6.0.1 results cover the scripted baseline; learned motion on 6.0.1 or WebRTC is unvalidated. |
| Streaming and offline assets | Server startup is covered; a connected WebRTC client and local asset-pack startup are not. Recorded asset-loading tests cover online retrieval and a warm cache. |
| Thor environment | The native installer applies an explicit TorchCodec overlay after the frozen dependency sync. The uv lock alone does not describe the complete installed environment; a reproducible source/build recipe for the custom wheel is not supplied. |
| Runtime image availability | A fresh registry pull of the pinned 6.0.0-dev2 image is not covered by the recorded validation. |

Run installation acceptance with explicit Isaac Sim license acceptance and the
native Thor dependency installation. Existing deployments also need the
[stopped-service upgrade checks](FULL-FORM-RENAME-UPGRADE.md). Other operating
systems, GPUs, Jetson products, serving topologies, and Chat or agent/model
combinations require acceptance on their own configuration.

Codec preflight checks build identity and features; it does not grant legal
approval. Checkpoint checksums establish integrity; rollout and visual
verification establish performance on the target scene.

## Historical validation

<a id="two-host-mission-evidence"></a>

<details>
<summary>Recorded runs, hardware, and runtime versions</summary>

| Date | Configuration | Recorded result |
|---|---|---|
| 2026-08-08 | Two-host GR00T manifest baseline | Historical `validated_on` date in the [deployment manifest](../deploy/reproducible-demo.yaml); it does not cover later dependency changes, the rename, or Isaac Sim 6.0.1. |
| 2026-09-08 | Jetson AGX Thor and RTX; learned Isaac Sim 6.0.0-dev2 profile | Complete deterministic two-host mission accepted from `c985be23d56eaae5a2beea2f8893387c120a849f` plus then-uncommitted reproducibility fixes on both hosts. Evidence included floor state, journal, simulator logs, and camera frames. |
| 2026-09-08 | Standalone scripted Isaac Sim 6.0.1 | Run `953020d69491`: compatibility checker, 15 ROS streams, 1280-pixel rack-camera frame, verified pick-and-place (`off=0.017`), reset, and three commands with clean current-run logs. |
| 2026-09-09 | Hardened standalone scripted Isaac Sim 6.0.1 | Run `d70ed0c3940f`: 15 streams with encoding, row-stride, and payload checks; verified move (`off=0.001`), two resets, and three clean command logs. Attested `ACCEPT_EULA=Y`, telemetry opt-out, and seven Kit privacy/telemetry/crash-reporting arguments. |

The standalone runs covered cold-online and warm-cache cloud-asset startup;
they did not qualify the optional five-part local asset pack, a connected
WebRTC client, Thor/GR00T, or the full two-host workflow.

### Recorded hardware and runtime

| Component | Measured environment |
|---|---|
| Jetson control host | NVIDIA Jetson AGX Thor; aarch64 Ubuntu 24.04; L4T 39.2.1; kernel `6.8.12-1021-tegra`; NVIDIA driver `595.78`; CUDA 13.0 and 13.2 runtime packages; Python 3.12.3; ROS 2 Jazzy; Docker 29.7.2 |
| RTX simulation host | NVIDIA RTX PRO 6000 Blackwell Workstation Edition; x86_64 Ubuntu 24.04; kernel `7.0.0-31-generic`; NVIDIA driver `610.43.02`; Docker 29.8.0; NVIDIA Container Toolkit 1.20.0; local X11 display `:1` |
| Learned simulator | `nvcr.io/nvidia/isaac-sim:6.0.0-dev2@sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9` |
| Scripted simulator | Official Isaac Sim 6.0.1 amd64 image at `sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb` |

The accepted GR00T services ran bare metal from the frozen uv environment at
`~/groot_shadow/Isaac-GR00T/`, followed by the checksum-attested TorchCodec
`0.10.0a0` LFS-wheel overlay. This post-lock installation means the final
environment was not entirely lock-resolved.

The standalone runs used the isolated `ic-isaac-sim-601-validation` container
without modifying the GR00T container. Its `IC_CELL_UP` marker and `/ic` topics
are historical evidence identifiers, not current runtime defaults.

</details>
