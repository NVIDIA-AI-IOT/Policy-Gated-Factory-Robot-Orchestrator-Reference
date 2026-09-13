# Installation

This guide provides two installation paths for the supplied reference factory
cell. Choose the path that matches the system you intend to run; the standalone
Isaac Sim baseline is not the full robot-orchestration deployment.

You can also use your own Isaac Sim scene and fine-tune GR00T on a custom
dataset. Start with [adapting the reference](README.md#adapt-the-reference-to-your-own-scene):
the installation scripts assume the supplied robots, camera mappings, and scene
contracts, which must be adapted and validated for your setup.

## Choose a deployment

| Goal | Required systems | Runtime | Instructions |
|---|---|---|---|
| Run and validate the scripted factory cell | One x86_64 Linux workstation with an NVIDIA RTX GPU | Isaac Sim 6.0.1, headless WebRTC by default; no GR00T or Jetson services | [Scripted Isaac Sim workstation](ops/ISAAC-SIM-WORKSTATION.md) |
| Run the complete policy-gated demonstration | One Jetson AGX Thor control host, one x86_64 RTX simulation host, and an operator machine | PGFR Spine and model services on Thor; Isaac Sim 6.0.0-dev2 with the pinned GR00T X11 compatibility profile on the RTX host | [Two-host GR00T deployment](docs/REPRODUCIBLE-DEMO.md) |

All commands below are run from the repository root. Review the validated
hardware and software boundary in [Support](docs/SUPPORT.md) before installing.
The project scripts validate host prerequisites, but they do not install or
replace the NVIDIA driver, Docker Engine, or NVIDIA Container Toolkit.

Both paths pull the official Isaac Sim image directly from NVIDIA and mount
project files from the RTX host. GR00T serving uses a native Thor environment;
there is no project image to build or publish. Docker remains necessary for
Isaac Sim, the upstream perception VLM, and the documented GPU/ROS checks.
Review the [Isaac Sim licensing overview](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/common/licenses-isaac-sim.html)
and the [Additional Software and Materials License](https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/)
before pulling or launching it. The launchers require explicit `--accept-eula`.

For the learned-motion path, follow this order:

| Stage | Instructions | Required result |
|---|---|---|
| Create demonstrations in the reference scene | [Dataset creation](reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/DATASET_CREATION.md) | Local native-DROID datasets, statistics, and capture provenance |
| Fine-tune on your local data | [Training recipe](reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md) | A checkpoint evaluated with your held-out data |
| Export and transfer the checkpoint | [Model preparation](reference/policy-gated-factory-robot-orchestrator-reference/groot/models/README.md) | Complete export on Thor with verified metadata and checksums |
| Install and start Thor and RTX services | [Two-host guide](docs/REPRODUCIBLE-DEMO.md) | Policy, perception, bridge, simulator, and control-plane readiness checks pass |
| Verify the complete deployment | [Mission acceptance](docs/VALIDATION.md) | Recorded task execution and state/camera verification for your checkpoint |

Training and conversion use a separate local environment. Follow their codec
setup and preflight instead of copying the workstation or Thor environment;
source checks alone do not qualify a new checkpoint or host installation.

If the machine already has an installation made with the former full-form
product or package names, use the [rename upgrade procedure](docs/FULL-FORM-RENAME-UPGRADE.md)
instead of installing over it.

## Standalone RTX scripted baseline

Use this path to bring up the reference cell and test its ROS 2 streams and
scripted actions without Thor or GR00T. The launcher uses the NVIDIA Isaac Sim
6.0.1 container by immutable digest; it does not build a project-specific
Isaac Sim image.

Read and accept the NVIDIA Isaac Sim license, then run:

```bash
docker pull \
  nvcr.io/nvidia/isaac-sim:6.0.1@sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb
ops/isaac-sim-workstation.sh --prepare
ops/isaac-sim-workstation.sh --check --accept-eula
ops/isaac-sim-workstation.sh --run --accept-eula
```

The preflight must report all three results:

```text
System checking result: PASSED
PGFR_ISAAC_NVIDIA_CHECK_OK image=... result=PASSED
PGFR_ISAAC_BASELINE_CHECK_OK mount=... image=... profile=headless
```

The launcher is ready only after it prints:

```text
PGFR_ISAAC_BASELINE_READY container=pgfr-isaac-sim-baseline profile=headless marker=PGFR_CELL_UP streaming=true webrtc_host=... signal_tcp=49100 stream_udp=47998
```

Run the scripted acceptance gate from an idle scene:

```bash
docker pull --platform linux/amd64 \
  docker.io/library/ros:jazzy-ros-base-noble@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4
ops/accept-isaac-sim-workstation.sh \
  --container pgfr-isaac-sim-baseline
```

Success ends with:

```text
PGFR_ISAAC_WORKSTATION_ACCEPTANCE_PASS container=pgfr-isaac-sim-baseline domain=<id> run_id=<id>
```

The acceptance gate resets the scene, moves one object, verifies the result,
and resets again. Do not run it while another operator or workflow is using the
cell. This result qualifies the scripted baseline only; it is not evidence of
Thor or GR00T inference.

The default WebRTC endpoint advertises loopback. For remote viewing, follow
the [WebRTC setup and firewall procedure](ops/ISAAC-SIM-WORKSTATION.md#launch-the-supported-headlesswebrtc-profile)
and connect with NVIDIA's native Isaac Sim Streaming Client. The endpoint is
not an HTTP page. PGFR Console is not installed by this standalone path.

## Full Jetson Thor and RTX GR00T deployment

First [create a local dataset](reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/DATASET_CREATION.md)
and [fine-tune GR00T](reference/policy-gated-factory-robot-orchestrator-reference/groot/groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md).
[Export your checkpoint](reference/policy-gated-factory-robot-orchestrator-reference/groot/models/README.md)
and copy the complete exported directory to Thor. No project fine-tuned weights
or recorded training dataset are supplied. Each new checkpoint must pass the
rollout checks; the historical development demonstration does not qualify it.

Use the [two-host deployment guide](docs/REPRODUCIBLE-DEMO.md) from the first
step. It covers the exact checkout, Thor prerequisites, upstream model access,
your exported checkpoint, user services, ROS 2 discovery, the simulation-host bridge,
and the GR00T cell installation. Do not substitute the standalone 6.0.1
container for this deployment: the current GR00T compatibility path is pinned
separately and requires a real local X11 desktop on the RTX host.
Use [Configure model providers](docs/MODEL-PROVIDERS.md) when selecting the PGFR
Chat endpoint and storing its credential.

After completing installation sections 1 through 4 of that guide, start the
model services on Thor:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
systemctl --user start pgfr-groot-shared-stack.target
systemctl --user start pgfr-perception-vlm.service
ops/launch-perception-vlm.sh --check
```

On the RTX simulation host, start the bridge and Isaac Sim from the local X11
owner session:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
PGFR_GROOT_ISAAC_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/policy-gated-factory-robot-orchestrator-reference/isaac-sim-groot"
PGFR_GROOT_ISAAC_MOUNT="$PGFR_GROOT_ISAAC_ROOT/scripts"
export PGFR_GROOT_STATE_ROOT="$HOME/.local/share/pgfr-spine/groot/remote-thor-v36"
: "${DISPLAY:?run from the workstation X11 owner session}"
export XAUTHORITY="${XAUTHORITY:-/run/user/$(id -u)/gdm/Xauthority}"
test -r "$XAUTHORITY"
xauth -f "$XAUTHORITY" nlist "$DISPLAY" | grep -q .
systemctl --user start pgfr-groot-two-host-bridge.service
ops/launch-groot-isaac.sh --accept-eula "$PGFR_GROOT_ISAAC_MOUNT"
```

The Isaac launcher requires both runtime markers and then prints its readiness
result:

```text
PGFR_GROOT_RUNTIME_READY
STARTUP_DONE full_scene+runner
PGFR_GROOT_ISAAC_READY container=isaac-sim markers=runtime,full_scene
```

Return to Thor and start the control-plane services:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
ops/thor-deploy.sh --start all
ops/thor-deploy.sh --check
```

`ops/thor-deploy.sh --check` must exit successfully and report every configured
service as reachable. Complete the ROS graph and conformance checks in
[Validate the two-host deployment](docs/VALIDATION.md). The
conformance results must be:

```text
CERTIFIED: 9/9
CERTIFIED: 11/11
```

These markers establish service readiness. Full deployment acceptance also
requires the deterministic
[physical workflow and evidence checks](docs/VALIDATION.md#run-the-serial-reference-mission).

## Open PGFR Console

The default deployment keeps the browser-facing services on Thor loopback.
From the operator machine, open one SSH session that forwards Console and Chat:

```bash
THOR_SSH=YOUR_THOR_USER@YOUR_THOR_IP
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8600:127.0.0.1:8600 \
  -L 127.0.0.1:8620:127.0.0.1:8620 \
  "$THOR_SSH"
```

Keep the SSH session open and browse to <http://127.0.0.1:8600>; **Chat** opens
by default. Port `18790` is the headless OpenClaw Gateway API, not an operator
dashboard.

Direct-IP Console and shared trusted-LAN Chat require explicit network policy
and different service bindings. Follow
[Remote access](docs/REMOTE-ACCESS.md)
before exposing either service. The shared LAN mode has no per-user
authentication or TLS; network reachability is its actuation boundary.

Before the first mission, start a new Chat conversation and enter
**`Reset the scene`**. Wait for the verified reset result before running the
[workflow through its API](docs/VALIDATION.md#run-the-serial-reference-mission).

## Next steps

- [Documentation index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Repository structure](STRUCTURE.md)
- [Security model](SECURITY.md)
