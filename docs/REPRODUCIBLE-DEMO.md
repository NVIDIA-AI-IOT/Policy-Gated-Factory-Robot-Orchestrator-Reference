# Reproduce the Policy-Gated Factory Robot Orchestrator Reference demo

This guide installs IC Spine, IC Console, the Isaac Sim reference cell, the
perception VLM, and the shared-model GR00T action path. It targets the validated
two-host configuration in [`SUPPORT.md`](SUPPORT.md); it is not a generic GPU
driver or container-runtime installer.

The learned-motion path uses one fine-tuned checkpoint loaded by two serving
processes, one for each Franka arm. Both processes load the same model. The
shipped profile defaults to six proof-gated serial moves; after baseline
acceptance, an operator may explicitly enable bounded two-arm pairs and the
three pair transactions remain sequenced before the AMR hauls the totes.

Model, dataset, container, runtime, and port identities are pinned in
[`../deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml) and
[`../reference/policy-gated-factory-robot-orchestrator-reference/groot/models/manifest.yaml`](../reference/policy-gated-factory-robot-orchestrator-reference/groot/models/manifest.yaml).

> **Publication boundary:** the 2026-09-08 acceptance used the base revision
> plus uncommitted reproducibility fixes. Until the complete tree is published
> at one immutable commit or tag, a clean clone of the base revision is not the
> accepted system. Treat this as the release-candidate runbook and use its Git
> clone steps for independent reproduction only after publication; see
> [`SUPPORT.md`](SUPPORT.md#measured-acceptance-cohort).

## Deployment layout

| Host | Components |
|---|---|
| Brain host | IC Spine, IC Console, IC Chat/OpenClaw, Nemotron perception VLM, two GR00T policy processes, and two relays |
| Simulation host | Isaac Sim, ROS 2 cell node, cameras, executors, and the fail-closed two-host GR00T bridge |
| Operator host | IC Console through loopback/SSH, or read-only direct LAN access when explicitly firewalled; Isaac Sim through local X11 or a separately secured viewer |

Each long-running component has one owner. Installation prepares files while
the corresponding services are idle; it never silently stops or replaces a
running stack.

Use the repository name as the checkout directory on both machines:
`~/Policy-Gated-Factory-Robot-Orchestrator-Reference`. Full-form package and
filesystem names use `policy-gated-factory-robot-orchestrator-reference` (or
its Python-safe underscore form). Existing abbreviated service names,
environment variables, ROS topics, and schemas keep their `ic-*`, `IC_*`,
`/ic/*`, and `ic_*` compatibility identifiers.

## 1. Prepare the brain host

The reference brain host is an aarch64 NVIDIA Jetson AGX Thor running Ubuntu
24.04 with Python 3.12, user systemd, CUDA, ROS 2 Jazzy, Docker, and NVIDIA
Container Runtime. Install Docker and the NVIDIA runtime using the supported
Jetson platform procedure before continuing; the project does not replace GPU
drivers or the container runtime.

For a brand-new device, complete NVIDIA's
[Jetson AGX Thor quick start](https://docs.nvidia.com/jetson/agx-thor-devkit/user-guide/latest/quick_start.html),
[JetPack setup](https://docs.nvidia.com/jetson/agx-thor-devkit/user-guide/latest/setup_jetpack.html),
and [Docker/NVIDIA Container Toolkit setup](https://docs.nvidia.com/jetson/agx-thor-devkit/user-guide/latest/setup_docker.html)
first. Confirm the expected platform before running the repository installer:

```bash
uname -m                         # aarch64
. /etc/os-release
test "$VERSION_ID" = 24.04
cat /etc/nv_tegra_release
nvidia-smi
python3 --version                # Python 3.12.x
```

If Docker installation added the operator to the `docker` group, end the old
login session and log in again before installing user services. Verify Docker
access from both the interactive shell and a user-systemd unit; the second
check catches a user manager that still has the old supplementary groups:

```bash
docker version --format '{{.Server.Version}}'
systemd-run --user --wait --pipe --collect \
  /usr/bin/docker version --format '{{.Server.Version}}'
docker run --rm --runtime=nvidia --gpus all \
  nvcr.io/nvidia/cuda:13.0.0-devel-ubuntu24.04 \
  nvidia-smi -L
```

The final command is the Thor-specific GPU-container smoke test. It must report
`GPU 0: NVIDIA Thor`; do not reuse the workstation's CUDA 12.8 test image here.

Clone the repository, install the measured host prerequisites, prepare the
pinned GR00T source and environment, and then install the control plane:

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

Use the raw Git URL shown above, not Markdown link syntax. If `ls-remote` or
`clone` returns HTTP 403, fix GitHub organization/SSO authorization first.
Cloning requires repository Contents read access, not write access; use an
organization-authorized SSH key or a fine-grained/read-only credential that
complies with the organization's token-lifetime policy. Never place a token in
the command line or repository URL. Replace `VALIDATED_COMMIT` with the exact
published 40-character commit ID from the release record; never substitute a
moving branch name or `HEAD`. The fail-fast block validates the placeholder
before cloning or mutating the host, so the unpublished release candidate
cannot be mistaken for a release.

The prerequisite installer pins Node and uv and installs the measured ROS and
CUDA host packages. GR00T runtime preparation checks out the pinned NVIDIA
Isaac-GR00T revision, applies the versioned Policy-Gated Factory Robot Orchestrator Reference patch, and builds
its locked Thor environment. The bootstrap uses repository lockfiles and
refuses to replace files beneath active IC services.

Review the generated files under `~/.config/ic-spine/`. The seeded services
bind to loopback. Keep that default and use an SSH tunnel, or set an exact
Console origin and nonempty Chat/Workflows tokens before intentionally binding
write-capable services to another interface.

Before starting IC Chat, replace `replace-with-your-model-id` in
`~/.config/ic-spine/chat.env` and select one coherent endpoint, credential, and
model tuple. IC Chat sends `IC_CHAT_API_KEY` unchanged as a Bearer credential;
it does not infer the endpoint from the key prefix. Set `IC_CHAT_MODEL_URL` to
the service root without `/v1`, because the adapter appends `/v1/models` and
`/v1/chat/completions`.

The public NVIDIA API Catalog profile is:

```dotenv
IC_CHAT_BACKEND=openai
IC_CHAT_MODEL_URL=https://integrate.api.nvidia.com
IC_CHAT_MODEL=nvidia/nemotron-3-ultra-550b-a55b
```

NVIDIA-internal users whose account has access to the OpenAI-compatible
inference service may instead use the internal profile. The following tuple was
validated during the 2026-09-08 acceptance run:

```dotenv
IC_CHAT_BACKEND=openai
IC_CHAT_MODEL_URL=https://inference-api.nvidia.com
IC_CHAT_MODEL=azure/openai/gpt-5.6-sol
```

The internal model is an environment choice, not a repository-wide pin. Query
the authenticated `/v1/models` catalog and validate tool calling before
selecting a different ID. Keep the public profile as the external default;
access to the internal endpoint and its `sk-...` credentials is organization
specific.

Use a model ID available to the deployed NVIDIA account; the example is not a
promise that every account has access. Obtain a hosted-endpoint key using
NVIDIA's [API Catalog quickstart](https://docs.api.nvidia.com/nim/re/docs/api-quickstart).
Keep credentials out of the repository and shell history. The bootstrap creates
the secrets file and a persistent
`OPENCLAW_GATEWAY_TOKEN`; edit that same file without removing the generated
token:

```bash
install -d -m 0700 "$HOME/.openclaw"
touch "$HOME/.openclaw/secrets.env"
chmod 0600 "$HOME/.openclaw/secrets.env"
${EDITOR:-vi} "$HOME/.openclaw/secrets.env"
```

For traditional IC Chat, add the credential issued for the selected endpoint:

```dotenv
IC_CHAT_API_KEY=YOUR_SELECTED_ENDPOINT_KEY
```

For the public NVIDIA profile, the same `nvapi-...` value may also be stored as
`NVIDIA_API_KEY` for OpenClaw's built-in NVIDIA provider. An internal
`sk-...` value belongs only to the internal endpoint and must not be paired
with `integrate.api.nvidia.com`. The hosted-endpoint credential is distinct
from the Hugging Face token used for model downloads and from a registry-only
NGC credential.

Seed the repository's complete OpenClaw configuration once before using its
configuration CLI. This preserves the MCP server and policy settings from
`ops/openclaw.template.json`; invoking `openclaw models set` against a missing
config would create an incomplete replacement. Start only the loopback Gateway,
verify that its config exists, and stop it again:

```bash
systemctl --user start ic-openclaw.service
test -s "$HOME/.policy-gated-factory-robot-orchestrator-reference/openclaw/openclaw.json"
systemctl --user stop ic-openclaw.service ic-seam.service
```

When using the public NVIDIA profile, configure OpenClaw's primary model while
its Gateway is stopped:

```bash
set -a
. "$HOME/.config/ic-spine/openclaw.env"
. "$HOME/.openclaw/secrets.env"
set +a
./node_modules/.bin/openclaw models set \
  nvidia/nemotron-3-ultra-550b-a55b
unset NVIDIA_API_KEY IC_CHAT_API_KEY OPENCLAW_GATEWAY_TOKEN
```

This command configures OpenClaw's built-in public NVIDIA provider. Traditional
IC Chat uses the internal profile independently. Do not assume that changing
`IC_CHAT_MODEL_URL` also changes OpenClaw; an internal OpenClaw deployment
requires a separately reviewed custom-provider configuration.

Test one actual completion before starting the stack. A successful
`/v1/models` response alone does not prove that the API key is authorized:

```bash
(
set -euo pipefail
set -a
. "$HOME/.config/ic-spine/chat.env"
set +a
: "${IC_CHAT_MODEL_URL:?set IC_CHAT_MODEL_URL in ~/.config/ic-spine/chat.env}"
: "${IC_CHAT_MODEL:?set IC_CHAT_MODEL in ~/.config/ic-spine/chat.env}"
MODEL_URL="${IC_CHAT_MODEL_URL%/}"
case "$MODEL_URL" in
  */v1) echo 'IC_CHAT_MODEL_URL must exclude /v1' >&2; exit 1 ;;
esac
REQUEST_BODY="$(python3 -c '
import json, sys
print(json.dumps({
    "model": sys.argv[1],
    "messages": [{"role": "user", "content": "Reply with READY."}],
}))
' "$IC_CHAT_MODEL")"
AUTH_HEADER="$(mktemp)"
trap 'rm -f "$AUTH_HEADER"' EXIT
chmod 0600 "$AUTH_HEADER"
set -a
. "$HOME/.openclaw/secrets.env"
set +a
: "${IC_CHAT_API_KEY:?set IC_CHAT_API_KEY in ~/.openclaw/secrets.env}"
printf 'Authorization: Bearer %s\n' "$IC_CHAT_API_KEY" > "$AUTH_HEADER"
unset NVIDIA_API_KEY IC_CHAT_API_KEY OPENCLAW_GATEWAY_TOKEN
curl --fail-with-body --silent --show-error \
  "$MODEL_URL/v1/chat/completions" \
  -H "@$AUTH_HEADER" \
  -H 'Content-Type: application/json' \
  -d "$REQUEST_BODY"
)
```

The mode-`0600` temporary header file keeps the key out of `curl`'s process
arguments. The sourced secrets are removed from its environment before launch,
and the file is removed when the subshell exits.

The perception VLM on port 8001 remains a separate, pinned service and is not
an implicit replacement for this reasoning model.

## 2. Authenticate and fetch the brain-host artifacts

Accept the terms for the gated runtime backbone
[`nvidia/Cosmos-Reason2-2B`](https://huggingface.co/nvidia/Cosmos-Reason2-2B)
on Hugging Face. Use the `hf` CLI supplied by the
locked GR00T environment rather than installing a second host copy:

```bash
export IC_HF_BIN="$HOME/groot_shadow/Isaac-GR00T/.venv/bin/hf"
export HF_HOME="$HOME/policy-gated-factory-robot-orchestrator-reference-models/hf-home"
export HF_TOKEN_PATH="$HF_HOME/token"
mkdir -p "$HF_HOME"
"$IC_HF_BIN" auth login
"$IC_HF_BIN" auth whoami

export IC_GROOT_HF_REPO=mmallick/industrial-claw-groot-order744-cont24
export IC_GROOT_HF_REVISION=9307ac9cba3a27c9a57ed2d90393ceefb28367e1
ops/fetch-groot-models.sh
ops/install-groot-thor-shared-profiles.sh
```

Pull the exact perception image recorded in the deployment manifest. The
systemd service later starts it by digest and refuses a tag-only substitute:

```bash
docker pull vllm/vllm-openai:v0.20.0-ubuntu2404@sha256:aff65d7198dd284c37dd0a18a606544cc5e92bfb0d5eb608b77e8b8f1c6b8b0d
```

The profile installer creates two GR00T profiles and one shared target. It does
not start or enable them.

## 3. Prepare the simulation host

The validated simulation host is an x86_64 Linux workstation with an NVIDIA
RTX GPU, Docker, NVIDIA Container Runtime, X11, `xauth`, and the pinned Isaac
Sim image. Clone the same repository commit on this host and accept NVIDIA's
[Isaac Sim license](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/common/NVIDIA_Omniverse_License_Agreement.html)
before pulling the image by digest:

Complete the fresh-host installation and GPU-container smoke test in the
[Isaac Sim workstation runbook](../ops/ISAAC-SIM-WORKSTATION.md#host-prerequisites)
first. The repository checks these dependencies but does not install or replace
the host's NVIDIA driver, Docker Engine, or NVIDIA Container Toolkit.

Record the brain-host, simulation-host, and operator addresses before opening
any firewall rule. From the simulation host, establish non-interactive SSH to
Thor because the GR00T bridge owns persistent loopback forwards:

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
docker pull nvcr.io/nvidia/isaac-sim:6.0.0-dev2@sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9
export IC_GROOT_ISAAC_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/policy-gated-factory-robot-orchestrator-reference/isaac-sim-groot"
export IC_GROOT_ISAAC_MOUNT="$IC_GROOT_ISAAC_ROOT/scripts"
ops/isaac-sim-workstation.sh --prepare \
  --root "$IC_GROOT_ISAAC_ROOT" \
  --container isaac-sim
ops/check-sim-host.sh --mount "$IC_GROOT_ISAAC_MOUNT"
)
```

The bridge always uses SSH `BatchMode=yes`; a password prompt cannot work from
its user service. The example creates an unencrypted default key only when one
does not already exist. Protect that key like a service credential, and use a
site-managed SSH key or agent instead when required by local policy. The
`systemd-run` check proves the user manager—not only the interactive shell—can
authenticate. Review the Thor host-key fingerprint through a trusted channel
before accepting it.

The image is an immutable compatibility pin for the validated cell, not
NVIDIA's current stable recommendation. Do not silently replace it with a
floating tag or a newer release; upgrade only after rerunning the cell, ROS,
camera, GR00T, and rendering acceptance tests.

To reproduce only the packaged scripted baseline on this host without the
Thor-hosted learned policy or two-host bridge, use the
[`Isaac Sim workstation helper`](../ops/ISAAC-SIM-WORKSTATION.md). It prepares
the deterministic default mount, validates it, starts the pinned local image,
and waits for `IC_CELL_UP`.

`IC_GROOT_ISAAC_MOUNT` is the host directory mounted at `/scripts` inside the
Isaac container, not the Isaac Sim installation directory. The checker is
read-only: it validates Linux/x86_64, Docker access, NVIDIA runtime and GPU
visibility, X11, the exact image digest, mount existence, and available disk.

Use a separate scripts mount for the GR00T deployment; do not reuse the
standalone baseline's live mount. The two-host launcher mounts
[`ops/fastdds-multi-host.xml`](../ops/fastdds-multi-host.xml) read-only and
sets the same Fast DDS profile, ROS domain, and RMW selected by the brain-host
Seam environment. This enables NVIDIA's documented UDP transport for ROS 2
participants on multiple machines or in containers.

The current GR00T and standalone launchers require a real local X11 display.
Their remote-viewing status is explicit in
[the workstation runbook](../ops/ISAAC-SIM-WORKSTATION.md#remote-viewing-and-nvidia-alignment):
RealVNC can mirror an existing desktop but is not the NVIDIA Isaac Sim WebRTC
Streaming Client, and the current scripts do not start WebRTC or the browser
viewer.

The preparation command above creates the external state tree and stages the
packaged cell atomically. Do not replace that step with an unchecked recursive
copy. Keep Isaac Sim stopped while the GR00T bundle is installed below.

Fast DDS traffic is peer-to-peer. If a host has a default-deny inbound
firewall, it needs a peer-scoped UDP rule; when both hosts filter inbound
traffic, add the reciprocal rule on both. For this pinned ROS domain `0`, the
well-known discovery and user-data range for participant IDs `0` through `99`
is `7400:7609`.

On the simulation host:

```bash
SIM_IF=YOUR_SIMULATION_INTERFACE
THOR_IP=YOUR_THOR_IP
sudo ufw allow in on "$SIM_IF" proto udp \
  from "$THOR_IP" to any port 7400:7609 \
  comment 'ROS 2 Fast DDS from Jetson Thor'
```

On Thor, only when its host firewall is active:

```bash
THOR_IF=YOUR_THOR_NETWORK_INTERFACE
SIM_IP=YOUR_SIMULATION_HOST_IP
sudo ufw allow in on "$THOR_IF" proto udp \
  from "$SIM_IP" to any port 7400:7609 \
  comment 'ROS 2 Fast DDS from Isaac simulation host'
```

Use the actual interfaces and fixed peer addresses. If a host does not use UFW,
apply the equivalent site firewall rule; do not install or reconfigure a
firewall blindly on a remotely administered Thor. Do not disable either
firewall or open this range to arbitrary sources. DDS traffic is not
authenticated or encrypted by this profile; use a trusted isolated network,
VPN, or DDS Security for production.

## 4. Install the bridge and GR00T cell while Isaac is idle

On the simulation host, install the validated two-host bridge:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
THOR_USER=YOUR_THOR_USER
THOR_HOST=YOUR_THOR_IP
THOR_SSH="$THOR_USER@$THOR_HOST"
THOR_HOME="/home/$THOR_USER"
THOR_MODEL_ROOT="$THOR_HOME/policy-gated-factory-robot-orchestrator-reference-models/order744-cont24"
THOR_STATE_ROOT="$THOR_HOME/.local/share/ic-spine/groot"
ops/install-groot-two-host-bridge.sh \
  --thor-ssh "$THOR_SSH" \
  --remote-checkpoint "$THOR_MODEL_ROOT" \
  --remote-state-root "$THOR_STATE_ROOT"
```

Then install the GR00T cell bundle using the bridge-owned local ports and
readiness files:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
THOR_USER=YOUR_THOR_USER
THOR_MODEL_ROOT="/home/$THOR_USER/policy-gated-factory-robot-orchestrator-reference-models/order744-cont24"
IC_GROOT_ISAAC_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/policy-gated-factory-robot-orchestrator-reference/isaac-sim-groot"
IC_GROOT_ISAAC_MOUNT="$IC_GROOT_ISAAC_ROOT/scripts"
export IC_GROOT_STATE_ROOT="$HOME/.local/share/ic-spine/groot/remote-thor-v36"
ops/install-groot-cell.sh \
  --mount "$IC_GROOT_ISAAC_MOUNT" \
  --checkpoint-path "$THOR_MODEL_ROOT" \
  --left-service-state /groot-state/shared-left.json \
  --right-service-state /groot-state/shared-right.json \
  --left-policy-port 5792 \
  --right-policy-port 5793 \
  --left-relay-port 5741 \
  --right-relay-port 5742
```

The bridge installer refuses to replace an active bridge. The cell installer
checks every active container and refuses to replace a scripts mount that is
currently in use. The launcher also refuses to start while any container using
the pinned Isaac image is active. No stop transition is hidden in this
sequence: installation is complete before the simulation starts.

## 5. Start and validate

Start the model owners on the brain host:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
systemctl --user start ic-groot-shared-stack.target
systemctl --user start ic-perception-vlm.service
ops/launch-perception-vlm.sh --check
```

Start the bridge and pinned Isaac runtime on the simulation host only after the
standalone baseline has been explicitly stopped:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
IC_GROOT_ISAAC_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/policy-gated-factory-robot-orchestrator-reference/isaac-sim-groot"
IC_GROOT_ISAAC_MOUNT="$IC_GROOT_ISAAC_ROOT/scripts"
export IC_GROOT_STATE_ROOT="$HOME/.local/share/ic-spine/groot/remote-thor-v36"
: "${DISPLAY:?run from the workstation X11 owner session}"
export XAUTHORITY="${XAUTHORITY:-/run/user/$(id -u)/gdm/Xauthority}"
test -r "$XAUTHORITY"
xauth -f "$XAUTHORITY" nlist "$DISPLAY" | grep -q .
systemctl --user start ic-groot-two-host-bridge.service
ops/launch-groot-isaac.sh "$IC_GROOT_ISAAC_MOUNT"
```

The measured GDM desktop used `DISPLAY=:1`; use the actual display for the
local session that owns the Isaac window. On a non-GDM desktop, set
`XAUTHORITY` to its actual readable cookie file. Do not substitute a VNC or
other virtual display for this validated GUI-container path.

The launcher sets `OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1`, preserves a failed
container for diagnosis, and returns successfully only after both
`IC_GROOT_RUNTIME_READY` and `STARTUP_DONE full_scene+runner` remain healthy.
Then start the remaining brain-host services:

```bash
ops/thor-deploy.sh --start all
ops/thor-deploy.sh --check
```

`thor-deploy.sh` requires the configured Chat backend to pass `/api/ready`; a
placeholder model or an endpoint that does not advertise the configured model
fails readiness. That catalog probe does not authenticate an inference
request, so the real completion smoke test in step 1 is also mandatory.

Validate the ROS graph and at least one real payload on the brain host. Disable
the ROS CLI daemon so cached graph names cannot satisfy the check:

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference/ops/fastdds-multi-host.xml"
export ROS2CLI_NO_DAEMON=1
ros2 topic info -v /ic/floor_state  # require Publisher count: 1
ros2 topic info -v /ic/command      # require Subscription count: 1
timeout 15 ros2 topic echo /ic/floor_state std_msgs/msg/String --once
ros2 topic list | grep -E '^/ic/(floor_state|result|feedback)$|^/(table_cam|inspect_cam|inspect_vlm_cam|rack_cam|outside_cam|outside_right_cam|wrist_cam|wrist_right_cam)/image_raw$'
```

Install the conformance kit in its own environment, then run both the live Seam
and MCP handshake checks before dispatching a mission. These checks are
read-only or deliberately policy-refused; they must report `CERTIFIED: 9/9` and
`CERTIFIED: 11/11` respectively:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
python3.12 -m venv packages/conformance-kit/.venv
packages/conformance-kit/.venv/bin/pip install -e \
  'packages/conformance-kit[mcp]'
packages/conformance-kit/.venv/bin/ic-conformance run \
  --target http://127.0.0.1:8766
packages/conformance-kit/.venv/bin/ic-conformance mcp \
  --command \
  "$PWD/servers/policy-gated-factory-robot-orchestrator-reference-mcp/.venv/bin/ic-mcp"
```

### Operator access from another machine

IC Console is the operator dashboard on port `8600`. OpenClaw port `18790` is a
headless Gateway API, not a second dashboard. The default deployment keeps
Console, Chat, and Workflows on Thor loopback. For the complete UI, forward all
three browser-facing ports from the operator machine:

```bash
THOR_SSH=YOUR_THOR_USER@YOUR_THOR_IP
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8600:127.0.0.1:8600 \
  -L 127.0.0.1:8610:127.0.0.1:8610 \
  -L 127.0.0.1:8620:127.0.0.1:8620 \
  "$THOR_SSH"
```

Then browse to `http://127.0.0.1:8600`. Keep the SSH process open while using
the UI.

For direct-IP, read-only observability, establish an exact source-address
firewall rule on Thor or at the network boundary **before** changing Console's
bind address. For a Thor host that already uses UFW, first confirm that it is
active, has default-deny inbound policy, and has no broader rule for port 8600;
then add and review the exact operator rule:

```bash
THOR_IF=YOUR_THOR_NETWORK_INTERFACE
OPERATOR_IP=YOUR_OPERATOR_IP
sudo ufw status verbose
sudo ufw status numbered
sudo ufw allow in on "$THOR_IF" proto tcp \
  from "$OPERATOR_IP" to any port 8600 \
  comment 'IC Console from operator'
sudo ufw status numbered
```

If UFW is not installed, use the site's equivalent host or upstream firewall;
do not install or reconfigure a firewall blindly on a remotely administered
Thor. Confirm that the alternative control is effective before continuing.
Only then edit `~/.config/ic-spine/console.env` on Thor and change:

```dotenv
IC_CONSOLE_HOST=0.0.0.0
```

`0.0.0.0` preserves the repository's loopback readiness probe while accepting
the firewalled LAN connection. Restart and verify only Console:

```bash
systemctl --user restart ic-console.service
systemctl --user is-active ic-console.service
ss -ltn | grep ':8600 '
```

From the operator machine, verify and open:

```bash
THOR_IP=YOUR_THOR_IP
curl --fail "http://$THOR_IP:8600/api/health"
# Browser: http://YOUR_THOR_IP:8600
```

This direct mode exposes only Console's read-only topology, Inspector, Safety,
GPU, camera-evidence, and mission-history views. Keep `8610`, `8620`, `8766`,
`18790`, `8001`, GR00T policy/relay ports, and the GPU exporter private. The
Chat and Workflow write tabs remain on the loopback/SSH path by default.

#### Opt-in shared trusted-LAN Chat (automatic access)

Use this mode only when every principal allowed to reach Console is also
authorized to command the cell. It deliberately has no login, per-user
identity, token expiry, or TLS: the static Console sends the public
`X-IC-Chat: console` CSRF value automatically. Exact-origin CORS prevents a
drive-by web page from using a browser to submit commands, but `console` is not
an authentication secret and a non-browser client on the admitted network can
reproduce the request. **Network reachability is actuation authority.** Keep
the default above for an untrusted network or one shared with non-operators; a
production remote-write deployment needs an authenticated TLS endpoint.

Before changing either bind address, authorize the same isolated trusted-LAN
CIDR for both Console `8600/tcp` and Chat `8620/tcp`. Do not make Chat broader
than Console. With an active, default-deny UFW installation:

```bash
THOR_IF=YOUR_THOR_NETWORK_INTERFACE
TRUSTED_LAN_CIDR=YOUR_TRUSTED_LAN_CIDR
sudo ufw status verbose
sudo ufw status numbered
sudo ufw allow in on "$THOR_IF" proto tcp \
  from "$TRUSTED_LAN_CIDR" to any port 8600 \
  comment 'IC Console from trusted operator LAN'
sudo ufw allow in on "$THOR_IF" proto tcp \
  from "$TRUSTED_LAN_CIDR" to any port 8620 \
  comment 'IC Chat from trusted operator LAN'
sudo ufw status numbered
```

Use the site's equivalent boundary when UFW is not already the host firewall.
Verify the two scopes are identical before continuing. In
`~/.config/ic-spine/console.env`, retain the internal loopback URL and add the
browser-visible URL using the literal Thor address:

```dotenv
IC_CONSOLE_HOST=0.0.0.0
IC_CHAT_URL=http://127.0.0.1:8620
IC_CHAT_PUBLIC_URL=http://YOUR_THOR_IP:8620
```

In `~/.config/ic-spine/chat.env`, bind Chat to the LAN, add the exact direct
Console origin without a trailing slash, and select the static UI's public CSRF
value. Preserve the two loopback origins so SSH-forwarded access still works:

```dotenv
IC_CHAT_HOST=0.0.0.0
IC_CHAT_CORS=http://127.0.0.1:8600,http://localhost:8600,http://YOUR_THOR_IP:8600
IC_CHAT_TOKEN=console
```

Replace every `YOUR_*` placeholder before restarting. Restart only the two
affected services and verify both listeners and health endpoints:

```bash
systemctl --user restart ic-chat.service ic-console.service
systemctl --user is-active ic-chat.service ic-console.service
ss -ltn | grep -E ':(8600|8620) '
THOR_IP=YOUR_THOR_IP
curl --fail "http://$THOR_IP:8600/api/health"
curl --fail "http://$THOR_IP:8620/api/health"
# Browser: http://YOUR_THOR_IP:8600, then select Chat.
```

Chat drives its policy-gated tool loop and the Seam server-side, so direct
Workflow Builder access is not required. Keep `8610`, `8766`, `18790`, `8001`,
GR00T policy/relay ports, and the GPU exporter private. Use the SSH-forwarded
default if Workflow Builder create/edit/run/schedule access is required.

The current Isaac launchers render to the simulation host's real local X11
desktop. Optional RealVNC access is a direct connection from RealVNC Viewer to
`<sim-host-ip>:5900`, not a browser URL, and it mirrors the entire workstation.
It is external to this repository and must be authenticated, encrypted, and
firewalled to the operator IP. NVIDIA's recommended remote path is headless
WebRTC; the current scripts do not start it, and `http://<sim-host-ip>:8210`
exists only after NVIDIA's separate browser-viewer Compose stack is deployed.
See the
[workstation remote-viewing matrix](../ops/ISAAC-SIM-WORKSTATION.md#remote-viewing-and-nvidia-alignment).

## 6. Run the physical acceptance workflow

The shipped OpenClaw profile is deliberately fail-closed:
`IC_GROOT_PARALLEL_ENABLED=0` and `IC_GROOT_FLEXIBLE_ORDER=0`. Its default
certified plan is therefore six serial GR00T moves, each followed by fresh
visual proof. Do not use a mixed-color concurrent prompt as the first physical
acceptance.

The deterministic `full-groot-dual-tote` workflow exercises the Seam, both
GR00T serving paths, the VLM proof gates, both tote hauls, and the journal
without relying on an agent to invent the action order.

Before every new physical run, open **Chat** in IC Console, start a new
conversation, and enter **`Reset the scene`**. The explicit request is required
because scene reset is operator-gated; Chat must wait for the verified result
before any mission action. A successful reset restores the canonical
`groot_three_object` starting layout, including both totes on the work tables in
front of their respective Franka arms. It resets the complete simulated cell,
not only the camera view or tote transforms.

If Console Chat is unavailable, issue the equivalent explicit operator action
locally on Thor:

```bash
curl --fail-with-body --silent --show-error \
  --output /tmp/ic-reset-response.json \
  -X POST http://127.0.0.1:8766/v1/dispatch \
  -H 'Content-Type: application/json' \
  -H 'x-role: operator' \
  -d '{"action":"reset_scene","endpoint":"mobilebot","scene_profile":"groot_three_object","arm":"both","color":"red","layout_left":3,"layout_right":3,"seed":31302}'
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d,indent=2)); sys.exit(0 if d.get("verified") is True else 1)' \
  /tmp/ic-reset-response.json
```

Then run the shipped workflow through its loopback-only guarded endpoint:

```bash
(
set -euo pipefail
WORKFLOWS_TOKEN="$(sed -n 's/^IC_WORKFLOWS_TOKEN=//p' \
  "$HOME/.config/ic-spine/workflows.env" | tail -n 1)"
: "${WORKFLOWS_TOKEN:=console}"
curl --fail-with-body --silent --show-error \
  --output /tmp/ic-reference-mission-response.json \
  -X POST \
  http://127.0.0.1:8610/api/workflows/full-groot-dual-tote/run \
  -H 'Origin: http://127.0.0.1:8600' \
  -H "X-IC-Workflows: $WORKFLOWS_TOKEN" \
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
' /tmp/ic-reference-mission-response.json
)"
printf '%s\n' "$MISSION_ID" > /tmp/ic-reference-mission-id
unset WORKFLOWS_TOKEN
)
```

The command persists the validated mission ID outside the checkout. Verify the
authoritative final state, the journal entries for that exact mission, service
health, and simulator stability:

```bash
(
  set -euo pipefail
  MISSION_ID="$(cat /tmp/ic-reference-mission-id)"
  [[ "$MISSION_ID" =~ ^wf-full-groot-dual-tote-[0-9a-f]{8}$ ]] || {
    echo 'invalid saved mission ID' >&2
    exit 1
  }
curl --fail --silent --show-error \
  --output /tmp/ic-final-floor-state.json \
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
' /tmp/ic-final-floor-state.json
curl --fail --silent --show-error \
  --output /tmp/ic-reference-mission-detail.json \
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
' /tmp/ic-reference-mission-detail.json "$MISSION_ID"
test -s "$HOME/ic-journal/journal.jsonl"
wc -l "$HOME/ic-journal/journal.jsonl"
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
ops/thor-deploy.sh --check
)
```

On the simulation host, assert against the complete log for the current
container. The launcher refuses to reuse an existing `isaac-sim` container, so
its `StartedAt` timestamp scopes this to the current run:

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
  grep -F 'IC_GROOT_RUNTIME_READY' "$ISAAC_LOG"
  grep -F 'STARTUP_DONE full_scene+runner' "$ISAAC_LOG"
  if grep -E '[A-Z][A-Z0-9_]*_(ERR|ERROR)(:|[[:space:]=]|$)' \
    "$ISAAC_LOG"; then
    echo 'Isaac Sim current run contains a project error marker' >&2
    exit 1
  fi
)
```

Require both commands to succeed. The final floor state and camera proof must
show both loaded totes on the rack; model prose alone is not acceptance
evidence.

### OpenClaw acceptance boundary

The NVIDIA provider completion in step 1 validates hosted-model inference, and
the conformance commands in step 5 validate the MCP server independently. The
shipped OpenClaw profile also exposes physical dispatch tools, so prompt wording
is not an authorization boundary and this guide does not label any OpenClaw chat
request as a non-actuating smoke test. Exercise an OpenClaw/model combination
only as a deliberate physical acceptance with an operator watching the cell, or
after a separately reviewed read-only MCP profile is added. A successful
deterministic workflow run does not certify OpenClaw.

### Optional mixed-color concurrent revalidation

The demonstrated mixed-color sequence is an explicit capability mode, not the
shipped default. Attempt it only after the serial physical acceptance above and
both B=1 GR00T servers have passed readiness. Stop OpenClaw, change only its MCP
child environment, validate the config, and start it again:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
systemctl --user stop ic-openclaw.service
set -a
. "$HOME/.config/ic-spine/openclaw.env"
set +a
./node_modules/.bin/openclaw config set \
  mcp.servers.ic-floor.env.IC_GROOT_PARALLEL_ENABLED '"1"' --strict-json
./node_modules/.bin/openclaw config set \
  mcp.servers.ic-floor.env.IC_GROOT_FLEXIBLE_ORDER '"1"' --strict-json
./node_modules/.bin/openclaw config validate
systemctl --user start ic-openclaw.service
ops/thor-deploy.sh --check
```

Then submit this goal through IC Chat with the `openclaw` backend:

> Reset and inspect the simulated cell. Pick left blue and right green
> together, then left green and right red together, then left red and right
> blue together. Verify both totes after each pair. Finally, haul both totes to
> the rack and verify completion.

This is a new end-to-end harness acceptance, not a consequence of the serial
workflow passing. Re-run every authoritative state, journal, and simulator-log
check above before recording it as successful.

The expected default acceptance flow is:

1. reset and visually inspect both work areas;
2. execute six certified serial placements, with fresh proof after each;
3. haul each loaded tote sequentially;
4. visually verify the rack; and
5. retain the complete tool, result, telemetry, and camera-evidence journal.

## Validation checklist

- IC Spine health reports a live ROS context and fresh required signals.
- All required camera topics produce changing frames.
- The VLM returns structured evidence from a fresh recorded frame.
- Both GR00T profiles report the same checkpoint identity.
- Both relays and bridge-derived readiness records are valid.
- Scene reset restores both three-object work areas and the executor home state.
- Every physical transaction returns `success:true` and `verified:true` before
  its required fresh visual proof and the next transaction.
- Both tote hauls complete without displacing their contents.
- Final visual verification confirms the loaded totes on the rack.
- The mission journal contains every action, result, duration, and VLM frame.

## Persistence and safeguards

Installation intentionally leaves all services disabled. This avoids enabling
robot-control software at boot without an operator decision. See
[`../ops/systemd/README.md`](../ops/systemd/README.md) for explicit manual and
appliance-mode procedures.

- A configuration change does not authorize replacing an active process.
- Start, stop, restart, and cancel operations require an explicit target.
- Do not identify or terminate processes only by their port number.
- Keep policy and relay listeners loopback-only; use the validated bridge for
  the two-host path.
- Preserve model, dataset, image, and source revisions when comparing results.
