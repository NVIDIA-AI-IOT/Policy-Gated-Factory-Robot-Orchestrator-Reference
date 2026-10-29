# Deploy the two-host reference system

This guide installs and starts the learned-motion reference deployment across
a Jetson control host and an RTX simulation host. It covers PGFR Spine, PGFR
Console, PGFR Chat/OpenClaw, the perception VLM, two GR00T policy processes, and
the Isaac Sim reference cell.

The launchers run NVIDIA's official Isaac Sim image and mount the prepared
PGFR code read-only at `/scripts`. Writable simulator state uses separate host
directories. The project does not build or publish an Isaac Sim image.

Review the [platform requirements](../INSTALL.md#platform-requirements) and
[validation status](VALIDATION.md#validation-status). Upstream model,
container, runtime, and port identities are recorded in
[`../deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml) and the
[GR00T model manifest](../reference/groot/models/manifest.yaml).
Your fine-tuned checkpoint and generated data are local inputs. Follow
[dataset creation](../reference/groot/groot_n1_7_pgfr_pipeline/docs/DATASET_CREATION.md),
[fine-tuning](../reference/groot/groot_n1_7_pgfr_pipeline/docs/FINETUNING_RECIPE.md),
and [checkpoint export](../reference/groot/models/README.md)
before this learned-motion installation. No project weights or recorded
training dataset are supplied.

Use the same Git commit on both hosts and run the [deployment checks](VALIDATION.md)
with your checkpoint. See [validation coverage](VALIDATION.md#validation-status)
for tested configurations and known limitations. Existing PGFR installations
with saved paths from an earlier source layout should follow the
[relay-path update](#update-an-existing-pgfr-relay-path).

## Requirements

Complete the [hardware and software prerequisites](../INSTALL.md) on both
hosts before running these commands. You also need:

- Read access to the repository and the same published 40-character commit ID
  on both hosts.
- A locally trained and exported GR00T checkpoint, with access to its gated
  runtime backbone and the pinned perception model.
- Credentials for the selected Chat endpoint, Hugging Face, and registry where
  required; see [model providers](MODEL-PROVIDERS.md).
- Passwordless SSH from RTX to Thor and peer-scoped Fast DDS UDP access.

## Contents

1. [Prepare the Jetson control host](#1-prepare-the-jetson-control-host)
2. [Prepare the local checkpoint and upstream backbone](#2-prepare-the-local-checkpoint-and-upstream-backbone)
3. [Prepare the RTX simulation host](#3-prepare-the-rtx-simulation-host)
4. [Install the bridge and GR00T cell](#4-install-the-bridge-and-gr00t-cell)
5. [Start the deployment](#5-start-the-deployment)
6. [Open and validate the system](#6-open-and-validate-the-system)

Related procedures:

- [Model providers and credentials](MODEL-PROVIDERS.md)
- [Remote operator access](REMOTE-ACCESS.md)
- [Deployment and mission validation](VALIDATION.md)
- [Standalone Isaac Sim workstation](../ops/ISAAC-SIM-WORKSTATION.md)
- [Update an existing PGFR relay path](#update-an-existing-pgfr-relay-path)

## Deployment layout

| Host | Components |
|---|---|
| Jetson control host | PGFR Spine, PGFR Console, PGFR Chat/OpenClaw, perception VLM, two GR00T policy processes, and two relays |
| RTX simulation host | Isaac Sim, ROS 2 cell node, cameras, executors, and the stop-on-uncertainty two-host GR00T bridge |
| Operator machine | PGFR Console through SSH or a deliberately firewalled LAN profile; optional workstation viewing |

The learned-motion path runs one user-trained checkpoint in two serving
processes, one per Franka arm. Both processes load the same model. The shipped
profile executes six proof-gated moves in series. Mixed-color pairs are an
optional profile enabled after serial acceptance; all three pairs must finish before the
AMR hauls the totes.

Each long-running component has one owner. Installation prepares files while
the corresponding services are stopped; it does not silently replace a
running stack.

Use `~/Policy-Gated-Factory-Robot-Orchestrator-Reference` as the checkout on
both hosts. Full-form package and filesystem names use
`policy-gated-factory-robot-orchestrator-reference`, or its Python-safe
underscore form. Project-owned abbreviated service names, environment
variables, ROS topics, and schemas use `pgfr-*`, `PGFR_*`, `/pgfr/*`, and `pgfr_*`.

<a id="1-prepare-the-brain-host"></a>

## 1. Prepare the Jetson control host

For a new device, complete NVIDIA's
[Jetson AGX Thor quick start](https://docs.nvidia.com/jetson/agx-thor-devkit/user-guide/latest/quick_start.html),
[JetPack setup](https://docs.nvidia.com/jetson/agx-thor-devkit/user-guide/latest/setup_jetpack.html),
and [Docker/NVIDIA Container Toolkit setup](https://docs.nvidia.com/jetson/agx-thor-devkit/user-guide/latest/setup_docker.html).
Confirm the expected platform:

```bash
uname -m                         # aarch64
. /etc/os-release
test "$VERSION_ID" = 24.04
cat /etc/nv_tegra_release
nvidia-smi
python3 --version                # Python 3.12.x
```

If Docker installation added the operator to the `docker` group, end the old
login session and log in again. Verify Docker from the interactive shell and a
user-systemd unit; the second check detects a user manager with stale
supplementary groups:

```bash
docker version --format '{{.Server.Version}}'
systemd-run --user --wait --pipe --collect \
  /usr/bin/docker version --format '{{.Server.Version}}'
docker run --rm --platform linux/arm64 --runtime=nvidia --gpus all \
  docker.io/nvidia/cuda:13.0.0-devel-ubuntu24.04@sha256:1e8ac7a54c184a1af8ef2167f28fa98281892a835c981ebcddb1fad04bdd452d \
  nvidia-smi -L
```

The final command is specific to Thor and must report `GPU 0: NVIDIA Thor`. Do
not use the RTX workstation's CUDA 12.8 smoke-test image for this check.

The qualified GR00T policy and relay processes run bare metal from the pinned
uv environment under `~/groot_shadow/Isaac-GR00T/`, owned by user systemd.
Docker is still required for the upstream perception VLM and for dependency
qualification. GR00T runtime preparation installs the pinned source and Python
environment locally on Thor; it does not build a project container. A CUDA
container smoke test is not policy-inference or full-mission evidence.

Clone the repository, install host prerequisites, prepare the pinned GR00T
source and environment, and install the control plane:

```bash
(
set -euo pipefail
cd ~
VALIDATED_COMMIT=REPLACE_WITH_PUBLISHED_COMMIT
[[ "$VALIDATED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo 'replace VALIDATED_COMMIT with the published 40-character commit ID' >&2
  exit 1
}
git ls-remote \
  https://github.com/NVIDIA-AI-IOT/Policy-Gated-Factory-Robot-Orchestrator-Reference.git \
  HEAD
git clone https://github.com/NVIDIA-AI-IOT/Policy-Gated-Factory-Robot-Orchestrator-Reference.git
cd ~/Policy-Gated-Factory-Robot-Orchestrator-Reference
git checkout --detach "$VALIDATED_COMMIT"
test "$(git rev-parse HEAD)" = "$VALIDATED_COMMIT"
test -z "$(git status --porcelain=v1 --untracked-files=all)"
ops/install-brain-host-prereqs.sh
ops/prepare-groot-runtime.sh --install
ops/bootstrap-brain.sh --check
ops/bootstrap-brain.sh --install
)
```

Cloning requires read access. If GitHub returns HTTP 403, check repository
permissions and any organization or SSO restrictions. Use an approved SSH key
or read-only credential; never put a token in the command line or repository
URL.

Replace `VALIDATED_COMMIT` with the exact published 40-character release
commit. Do not substitute a moving branch name or `HEAD`. The fail-fast block
rejects the placeholder before it clones or mutates the host.

The prerequisite installer pins Node and uv and installs the measured ROS and
CUDA packages. Runtime preparation checks out the pinned NVIDIA Isaac-GR00T
revision, applies the versioned project patch, and builds the frozen Thor uv
environment. The exact TorchCodec `0.10.0a0` LFS wheel is installed after the
frozen sync as a separately checksum-attested platform overlay; it is not a
registry package resolved by the uv lock. The bootstrap uses repository
lockfiles and refuses to replace files beneath active PGFR services.

The bootstrap preserves operator environment files. If a saved relay path no
longer exists in the updated checkout, follow the
[relay-path update](#update-an-existing-pgfr-relay-path) before starting services.

Review the generated files under `~/.config/pgfr-spine/`. The default services
bind to loopback. Keep that default unless the access profile in
[`REMOTE-ACCESS.md`](REMOTE-ACCESS.md) explicitly calls for another bind
address.

Configure and test the reasoning endpoint before starting PGFR Chat. Follow
[`MODEL-PROVIDERS.md`](MODEL-PROVIDERS.md) for endpoint selection, credential
storage, OpenClaw setup, and the required completion smoke test.

<a id="2-authenticate-and-fetch-the-brain-host-artifacts"></a>

<a id="2-fetch-control-host-artifacts"></a>

## 2. Prepare the local checkpoint and upstream backbone

Export on the training host using the [model export procedure](../reference/groot/models/README.md).
Copy the complete exported directory to Thor, including `pgfr_checkpoint.json`
and `SHA256SUMS`. The example below uses `my-checkpoint`; use your actual
export directory consistently in the Thor profiles, bridge, and Isaac contracts.
The export records artifact identity and provenance. Task success requires
separate rollout validation.

Accept the terms for the gated runtime backbone
[`nvidia/Cosmos-Reason2-2B`](https://huggingface.co/nvidia/Cosmos-Reason2-2B)
on Hugging Face. Use the `hf` CLI supplied by the locked GR00T environment:

```bash
export PGFR_HF_BIN="$HOME/groot_shadow/Isaac-GR00T/.venv/bin/hf"
export HF_HOME="$HOME/policy-gated-factory-robot-orchestrator-reference-models/hf-home"
export HF_TOKEN_PATH="$HF_HOME/token"
mkdir -p "$HF_HOME"
"$PGFR_HF_BIN" auth login
"$PGFR_HF_BIN" auth whoami

export PGFR_GROOT_MODEL_ROOT="$HOME/policy-gated-factory-robot-orchestrator-reference-models/my-checkpoint"
ops/verify-groot-models.sh "$PGFR_GROOT_MODEL_ROOT"
ops/fetch-groot-models.sh "$PGFR_GROOT_MODEL_ROOT"
ops/install-groot-thor-shared-profiles.sh --checkpoint-path "$PGFR_GROOT_MODEL_ROOT"
```

`fetch-groot-models.sh` verifies the local checkpoint and downloads only the
pinned official Cosmos backbone. It does not download a fine-tuned project model
or a training dataset.

Pull the exact perception image recorded in the deployment manifest. The
systemd service starts it by digest and refuses a tag-only substitute:

```bash
docker pull vllm/vllm-openai:v0.20.0-ubuntu2404@sha256:aff65d7198dd284c37dd0a18a606544cc5e92bfb0d5eb608b77e8b8f1c6b8b0d
```

The profile installer creates two GR00T profiles and one shared target. It does
not start or enable them.

<a id="3-prepare-the-simulation-host"></a>

## 3. Prepare the RTX simulation host

The historical two-host GR00T deployment used the pinned Isaac Sim
6.0.0-dev2 image with local X11. It is separate from the standalone scripted
baseline, which uses stable Isaac Sim 6.0.1 and headless WebRTC. Learned motion
on 6.0.1 has not been qualified.

Accept the
[Isaac Sim Additional Software and Materials License](https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/)
and complete the fresh-host installation and GPU-container smoke test in the
[workstation runbook](../ops/ISAAC-SIM-WORKSTATION.md#host-prerequisites).

Record the Jetson control-host, RTX simulation-host, and operator addresses.
The bridge owns persistent loopback forwards, so establish non-interactive SSH
from the RTX host to the Jetson host:

```bash
(
set -euo pipefail
cd ~
VALIDATED_COMMIT=REPLACE_WITH_PUBLISHED_COMMIT
[[ "$VALIDATED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo 'replace VALIDATED_COMMIT with the published 40-character commit ID' >&2
  exit 1
}
git clone https://github.com/NVIDIA-AI-IOT/Policy-Gated-Factory-Robot-Orchestrator-Reference.git
cd ~/Policy-Gated-Factory-Robot-Orchestrator-Reference
git checkout --detach "$VALIDATED_COMMIT"
test "$(git rev-parse HEAD)" = "$VALIDATED_COMMIT"
test -z "$(git status --porcelain=v1 --untracked-files=all)"
THOR_SSH=YOUR_THOR_USER@YOUR_THOR_IP
install -d -m 0700 "$HOME/.ssh"
if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
  ssh-keygen -t ed25519 -N '' -f "$HOME/.ssh/id_ed25519" \
    -C 'Policy-Gated Factory Robot Orchestrator Reference simulation-to-Thor bridge'
fi
ssh "$THOR_SSH" true                    # review the host key out of band
ssh-copy-id -i "$HOME/.ssh/id_ed25519.pub" "$THOR_SSH"
ssh -o BatchMode=yes "$THOR_SSH" true   # must succeed without a prompt
systemd-run --user --wait --pipe --collect \
  /usr/bin/ssh -o BatchMode=yes "$THOR_SSH" true
LOCAL_COMMIT="$(git rev-parse HEAD)"
REMOTE_COMMIT="$(ssh "$THOR_SSH" \
  'git -C ~/Policy-Gated-Factory-Robot-Orchestrator-Reference rev-parse HEAD')"
test "$LOCAL_COMMIT" = "$REMOTE_COMMIT"
REMOTE_DIRTY="$(ssh "$THOR_SSH" \
  'git -C ~/Policy-Gated-Factory-Robot-Orchestrator-Reference status --porcelain=v1 --untracked-files=all')"
test -z "$REMOTE_DIRTY"
: "${DISPLAY:?run from the workstation X11 owner session}"
docker pull --platform linux/amd64 nvcr.io/nvidia/isaac-sim:6.0.0-dev2@sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9
export PGFR_GROOT_ISAAC_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/policy-gated-factory-robot-orchestrator-reference/isaac-sim-groot"
export PGFR_GROOT_ISAAC_MOUNT="$PGFR_GROOT_ISAAC_ROOT/scripts"
ops/isaac-sim-workstation.sh --prepare \
  --root "$PGFR_GROOT_ISAAC_ROOT" \
  --container isaac-sim
PGFR_ISAAC_IMAGE=nvcr.io/nvidia/isaac-sim:6.0.0-dev2 \
PGFR_ISAAC_IMAGE_DIGEST=sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9 \
ops/check-sim-host.sh --profile x11 --mount "$PGFR_GROOT_ISAAC_MOUNT" \
  --state-root "$PGFR_GROOT_ISAAC_ROOT"
)
```

The bridge always uses SSH `BatchMode=yes`; a password prompt cannot work from
its user service. The example creates an unencrypted default key only when one
does not exist. Protect it as a service credential, or use a site-managed SSH
key or agent. Verify the Jetson host-key fingerprint through a trusted channel.
The `systemd-run` check proves the user manager can authenticate.

The dev2 digest records the historical GR00T compatibility environment. Its
continued availability from NVIDIA has not been verified by a fresh pull. If
that exact digest is unavailable, stop and qualify a replacement before
changing the pin. Any upgrade requires cell, ROS, camera, GR00T, and rendering
acceptance. The separate
[standalone helper](../ops/ISAAC-SIM-WORKSTATION.md) prepares stable Isaac Sim
6.0.1, checks 15 streams and one exactly-once scripted move, and resets the
scene. That result is not Thor or GR00T evidence.

With the GR00T overrides above, the host checker validates Linux/x86_64,
Docker access, NVIDIA runtime and GPU visibility, X11, the exact dev2 image
digest, the scripts mount, and at least 50,000,000,000 bytes of total
filesystem capacity at the state cache. It reports available bytes but does
not impose a free-space threshold. The standalone helper additionally runs
NVIDIA's bundled compatibility checker under the stable image identity.

`PGFR_GROOT_ISAAC_MOUNT` is the host directory mounted at `/scripts`, not the
Isaac Sim installation directory.

Use a separate scripts mount for the GR00T deployment; do not reuse the
standalone baseline's live mount. Preparation
builds the packaged cell in a sibling temporary directory and publishes it
with one same-filesystem `mv -T`. It rejects a divergent target rather than
merging or overwriting it.

The launcher mounts
[`../ops/fastdds-multi-host.xml`](../ops/fastdds-multi-host.xml) read-only and
uses the same Fast DDS profile, ROS domain, and RMW as the Jetson PGFR Spine
service.
If either host has a default-deny firewall, allow peer-scoped UDP traffic. For
the pinned ROS domain `0`, participant IDs `0` through `99` use `7400:7609`.

On the RTX simulation host:

```bash
SIM_IF=YOUR_SIMULATION_INTERFACE
THOR_IP=YOUR_THOR_IP
sudo ufw allow in on "$SIM_IF" proto udp \
  from "$THOR_IP" to any port 7400:7609 \
  comment 'ROS 2 Fast DDS from Jetson Thor'
```

On the Jetson control host, only when its host firewall is active:

```bash
THOR_IF=YOUR_THOR_NETWORK_INTERFACE
SIM_IP=YOUR_SIMULATION_HOST_IP
sudo ufw allow in on "$THOR_IF" proto udp \
  from "$SIM_IP" to any port 7400:7609 \
  comment 'ROS 2 Fast DDS from Isaac simulation host'
```

Use the actual interfaces and fixed peer addresses. If UFW is not the host
firewall, apply the equivalent site rule; do not install or reconfigure a
firewall blindly. Do not disable either firewall or open this range to
arbitrary sources. This Fast DDS profile is not authenticated or encrypted;
use a trusted isolated network, VPN, or DDS Security in production.

<a id="4-install-the-bridge-and-groot-cell-while-isaac-is-idle"></a>

## 4. Install the bridge and GR00T cell

Keep Isaac Sim stopped throughout this section. The bridge and cell need a
local copy of the export metadata and checksum manifest to attest the remote
model identity; the simulation host does not need another copy of the weights.
On the RTX simulation host, copy those two files from the verified Thor export
and install the two-host bridge:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
THOR_USER=YOUR_THOR_USER
THOR_HOST=YOUR_THOR_IP
THOR_SSH="$THOR_USER@$THOR_HOST"
THOR_HOME="/home/$THOR_USER"
THOR_MODEL_ROOT="$THOR_HOME/policy-gated-factory-robot-orchestrator-reference-models/my-checkpoint"
THOR_STATE_ROOT="$THOR_HOME/.local/share/pgfr-spine/groot"
CHECKPOINT_METADATA_DIR="$HOME/.local/share/pgfr-spine/checkpoints/my-checkpoint"
mkdir -p "$CHECKPOINT_METADATA_DIR"
scp "$THOR_SSH:$THOR_MODEL_ROOT/pgfr_checkpoint.json" "$CHECKPOINT_METADATA_DIR/"
scp "$THOR_SSH:$THOR_MODEL_ROOT/SHA256SUMS" "$CHECKPOINT_METADATA_DIR/"
ops/install-groot-two-host-bridge.sh \
  --thor-ssh "$THOR_SSH" \
  --remote-checkpoint "$THOR_MODEL_ROOT" \
  --checkpoint-metadata "$CHECKPOINT_METADATA_DIR/pgfr_checkpoint.json" \
  --remote-state-root "$THOR_STATE_ROOT"
```

Install the GR00T cell bundle using the bridge-owned local ports and readiness
files:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
THOR_USER=YOUR_THOR_USER
THOR_MODEL_ROOT="/home/$THOR_USER/policy-gated-factory-robot-orchestrator-reference-models/my-checkpoint"
CHECKPOINT_METADATA_DIR="$HOME/.local/share/pgfr-spine/checkpoints/my-checkpoint"
PGFR_GROOT_ISAAC_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/policy-gated-factory-robot-orchestrator-reference/isaac-sim-groot"
PGFR_GROOT_ISAAC_MOUNT="$PGFR_GROOT_ISAAC_ROOT/scripts"
export PGFR_GROOT_STATE_ROOT="$HOME/.local/share/pgfr-spine/groot/remote-thor-v36"
ops/install-groot-cell.sh \
  --mount "$PGFR_GROOT_ISAAC_MOUNT" \
  --checkpoint-path "$THOR_MODEL_ROOT" \
  --checkpoint-metadata "$CHECKPOINT_METADATA_DIR/pgfr_checkpoint.json" \
  --left-service-state /groot-state/shared-left.json \
  --right-service-state /groot-state/shared-right.json \
  --left-policy-port 5792 \
  --right-policy-port 5793 \
  --left-relay-port 5741 \
  --right-relay-port 5742
```

The bridge installer refuses to replace an active bridge. The cell installer
checks every active container and refuses to replace a scripts mount in use.
The launcher also refuses to start while a container using the pinned Isaac
image is active. Complete installation before starting the simulator; these
commands do not stop an existing instance.

<a id="5-start-and-validate"></a>

## 5. Start the deployment

On the Jetson control host, start the GR00T and perception model owners:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
systemctl --user start pgfr-groot-shared-stack.target
systemctl --user start pgfr-perception-vlm.service
ops/launch-perception-vlm.sh --check
```

On the RTX simulation host, start the bridge and the pinned Isaac runtime only
after the standalone baseline has been explicitly stopped:

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

The measured GDM desktop used `DISPLAY=:1`; use the display owned by the local
workstation session. On another desktop, set `XAUTHORITY` to its readable
cookie file. Do not substitute a VNC or virtual display for this qualified GUI
container path.

`--accept-eula` confirms the operator's acceptance for this launch and is
required before host checks or state changes. The launcher uses only the
already-pulled image (`--pull never`) and mounts project code read-only. It
sets `OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1` and preserves a failed container
for diagnosis. It returns successfully only after both
`PGFR_GROOT_RUNTIME_READY` and `STARTUP_DONE full_scene+runner` remain healthy.

Then start the remaining services on the Jetson control host:

```bash
ops/thor-deploy.sh --start all
ops/thor-deploy.sh --check
```

`thor-deploy.sh` requires the configured Chat backend to pass `/api/ready`. A
placeholder model or endpoint that does not advertise the configured model
fails readiness. Catalog access does not establish permission to run inference;
also run the completion test in
[`MODEL-PROVIDERS.md`](MODEL-PROVIDERS.md#test-a-completion).

## 6. Open and validate the system

Follow [`REMOTE-ACCESS.md`](REMOTE-ACCESS.md) to open Console and view Isaac
Sim. The recommended profile tunnels Console and Chat over SSH; the Workflows
API can be forwarded separately when needed.
Direct trusted-LAN Chat makes network reachability equivalent to actuation
authority and must not be enabled on an untrusted network.

Follow [`VALIDATION.md`](VALIDATION.md) in order. It checks the live ROS graph,
runs both conformance suites, resets the scene, executes the serial reference
mission, and verifies the authoritative state, journal, and current Isaac Sim
log. The serial mission is the first acceptance. Physical workflow dispatches
are not automatically retried; reconcile an uncertain result before another
action.

The optional mixed-color mode is enabled only after serial acceptance. Its
fixed sequence is left blue/right green, left green/right red, then left
red/right blue, with proof after every pair. Enabling it requires both
capability flags in PGFR Spine and Workflows and the additional certified-order
flag in the MCP child.

<a id="operator-access-from-another-machine"></a>
<a id="opt-in-shared-trusted-lan-chat-automatic-access"></a>
<a id="remote-operator-access"></a>
<a id="6-run-the-physical-acceptance-workflow"></a>
<a id="physical-acceptance-workflow"></a>
<a id="openclaw-acceptance-boundary"></a>
<a id="optional-mixed-color-concurrent-revalidation"></a>
<a id="validation-checklist"></a>

Detailed procedures: [remote access](REMOTE-ACCESS.md),
[serial acceptance](VALIDATION.md#run-the-serial-reference-mission),
[OpenClaw acceptance](VALIDATION.md#openclaw-acceptance-boundary),
[optional mixed-color revalidation](VALIDATION.md#optional-mixed-color-concurrent-revalidation),
and the [acceptance checklist](VALIDATION.md#acceptance-checklist).
A deterministic workflow pass does not certify OpenClaw; acceptance requires
measured state, journal, camera, and current-run simulator evidence.

## Persistence and safeguards

The installers do not enable services. Configure automatic startup separately
after reviewing the site's requirements. See
[`../ops/systemd/README.md`](../ops/systemd/README.md) for manual and
appliance-mode procedures.

These are user services. Enabling a unit does not guarantee unattended startup:
the user manager must start and may stop after the final logout. Appliance
persistence also requires an administrator-approved
`loginctl enable-linger <user>`, when permitted by site policy. Apply the same
decision separately to the RTX bridge.

- A configuration change does not authorize replacing an active process.
- Start, stop, restart, and cancel operations require an explicit target.
- Do not identify or terminate processes only by port number.
- Keep policy and relay listeners loopback-only; use the qualified bridge for
  the two-host path.
- Preserve the local checkpoint checksum manifest, dataset provenance, upstream model revisions, image digests, and source revision when comparing results.

## Update an existing PGFR relay path

Use this procedure when an existing PGFR deployment's saved `RELAY_SCRIPT`
points to a source path that moved. On Thor, confirm that no mission, reset,
or model request is in flight. Back up
`~/.config/pgfr-spine/groot/shared-{left,right}.env`, then stop both relays and
open their configuration:

```bash
systemctl --user stop \
  pgfr-groot-relay@shared-left.service pgfr-groot-relay@shared-right.service
${EDITOR:-vi} \
  "$HOME/.config/pgfr-spine/groot/shared-left.env" \
  "$HOME/.config/pgfr-spine/groot/shared-right.env"
```

Set each affected `RELAY_SCRIPT` to the existing file
`<checkout>/reference/groot/relay/native_droid_relay_batch2.py`. Preserve the
checkout prefix, quoting, and other settings; leave valid custom relay paths
unchanged. The profile installer refuses differing existing files, so rerunning
it does not migrate saved paths.

After checking both paths, restart the two relay units, run
`ops/thor-deploy.sh --check`, and repeat the [deployment checks](VALIDATION.md)
before resuming missions. Model/cache paths, persistent state, and existing
copied Isaac mounts do not need to move for this relay-path update.
