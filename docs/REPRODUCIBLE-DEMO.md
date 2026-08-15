# Reproduce the Industrial Claw demo

This guide installs IC Spine, IC Console, the Isaac Sim reference cell, the
perception VLM, and the shared-model GR00T action path. It targets the validated
two-host configuration in [`SUPPORT.md`](SUPPORT.md); it is not a generic GPU
driver or container-runtime installer.

The learned-motion path uses one fine-tuned checkpoint loaded by two serving
processes, one for each Franka arm. Both processes load the same model. The two
arms execute one object pair concurrently; the three pairs are sequenced and
verified before the AMR hauls the totes.

Model, dataset, container, runtime, and port identities are pinned in
[`../deploy/reproducible-demo.yaml`](../deploy/reproducible-demo.yaml) and
[`../reference/industrial-claw/groot/models/manifest.yaml`](../reference/industrial-claw/groot/models/manifest.yaml).

## Deployment layout

| Host | Components |
|---|---|
| Brain host | IC Spine, IC Console, IC Chat/OpenClaw, Nemotron perception VLM, two GR00T policy processes, and two relays |
| Simulation host | Isaac Sim, ROS 2 cell node, cameras, executors, and the fail-closed two-host GR00T bridge |
| Browser | IC Console through loopback or an SSH tunnel |

Each long-running component has one owner. Installation prepares files while
the corresponding services are idle; it never silently stops or replaces a
running stack.

## 1. Prepare the brain host

The reference brain host is an aarch64 NVIDIA Jetson AGX Thor running Ubuntu
24.04 with Python 3.12, user systemd, CUDA, ROS 2 Jazzy, Docker, and NVIDIA
Container Runtime. Install Docker and the NVIDIA runtime using the supported
Jetson platform procedure before continuing; the project does not replace GPU
drivers or the container runtime.

Clone the repository, install the measured host prerequisites, prepare the
pinned GR00T source and environment, and then install the control plane:

```bash
git clone https://github.com/NVIDIA-AI-IOT/Industrial-Claw.git ~/industrial-claw
cd ~/industrial-claw
ops/install-brain-host-prereqs.sh
ops/prepare-groot-runtime.sh --install
ops/bootstrap-brain.sh --check
ops/bootstrap-brain.sh --install
```

The prerequisite installer pins Node and uv and installs the measured ROS and
CUDA host packages. GR00T runtime preparation checks out the pinned NVIDIA
Isaac-GR00T revision, applies the versioned Industrial Claw patch, and builds
its locked Thor environment. The bootstrap uses repository lockfiles and
refuses to replace files beneath active IC services.

Review the generated files under `~/.config/ic-spine/`. The seeded services
bind to loopback. Keep that default and use an SSH tunnel, or set an exact
Console origin and nonempty Chat/Workflows tokens before intentionally binding
write-capable services to another interface.

Before starting IC Chat, replace `replace-with-your-model-id` in
`~/.config/ic-spine/chat.env` and set its OpenAI-compatible endpoint. Put
`IC_CHAT_API_KEY` in `~/.openclaw/secrets.env` when the endpoint requires
authentication. `thor-deploy.sh` will refuse readiness until the configured
endpoint advertises the exact model. The perception VLM on port 8001 remains a
separate, pinned service and is not an implicit replacement for the reasoning
model.

## 2. Authenticate and fetch the brain-host artifacts

Accept the terms for the gated runtime backbone
`nvidia/Cosmos-Reason2-2B` on Hugging Face. Use the `hf` CLI supplied by the
locked GR00T environment rather than installing a second host copy:

```bash
export IC_HF_BIN="$HOME/groot_shadow/Isaac-GR00T/.venv/bin/hf"
export HF_HOME="$HOME/industrial-claw-models/hf-home"
export HF_TOKEN_PATH="$HF_HOME/token"
mkdir -p "$HF_HOME"
"$IC_HF_BIN" auth login

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
Isaac Sim license before pulling the image by digest:

```bash
git clone https://github.com/NVIDIA-AI-IOT/Industrial-Claw.git ~/industrial-claw
cd ~/industrial-claw
docker pull nvcr.io/nvidia/isaac-sim:6.0.0-dev2@sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9
ops/check-sim-host.sh --mount <isaac-mount>
```

`<isaac-mount>` is the host directory mounted at `/scripts` inside the Isaac
container, not the Isaac Sim installation directory. The checker is read-only:
it validates Linux/x86_64, Docker access, NVIDIA runtime and GPU visibility,
X11, the exact image digest, mount existence, and available disk space.

Copy the packaged cell into that scripts mount while Isaac Sim is stopped:

```bash
cp -r reference/industrial-claw/isaac-cell/ic_cell \
  reference/industrial-claw/isaac-cell/ic_boot.py <isaac-mount>/
```

## 4. Install the bridge and GR00T cell while Isaac is idle

On the simulation host, install the validated two-host bridge:

```bash
ops/install-groot-two-host-bridge.sh \
  --thor-ssh user@brain-host \
  --remote-checkpoint /absolute/path/to/order744-cont24 \
  --remote-state-root /absolute/brain-host/state/root
```

Then install the GR00T cell bundle using the bridge-owned local ports and
readiness files:

```bash
export IC_GROOT_STATE_ROOT="$HOME/.local/share/ic-spine/groot/remote-thor-v36"
ops/install-groot-cell.sh \
  --mount <isaac-mount> \
  --checkpoint-path /absolute/path/on-brain-host/order744-cont24 \
  --left-service-state /groot-state/shared-left.json \
  --right-service-state /groot-state/shared-right.json \
  --left-policy-port 5792 \
  --right-policy-port 5793 \
  --left-relay-port 5741 \
  --right-relay-port 5742
```

Both installers refuse to replace files beneath an active bridge or Isaac
container. No stop transition is hidden in this sequence: installation is
complete before the simulation starts.

## 5. Start and validate

Start the model owners on the brain host:

```bash
systemctl --user start ic-groot-shared-stack.target
systemctl --user start ic-perception-vlm.service
ops/launch-perception-vlm.sh --check
```

Start the bridge and pinned Isaac runtime on the simulation host:

```bash
systemctl --user start ic-groot-two-host-bridge.service
ops/launch-groot-isaac.sh <isaac-mount>
```

Wait for `IC_GROOT_RUNTIME_READY` and `STARTUP_DONE`, then start the remaining
brain-host services:

```bash
ops/thor-deploy.sh --start all
ops/thor-deploy.sh --check
```

`thor-deploy.sh` requires the configured Chat backend to pass `/api/ready`; a
placeholder model or an OpenAI-compatible endpoint that does not advertise the
configured model fails readiness.

Validate ROS streams on the simulation host:

```bash
ros2 topic list | grep -E '^/ic/(floor_state|result|feedback)$|^/(table_cam|inspect_cam|inspect_vlm_cam|rack_cam|outside_cam|outside_right_cam|wrist_cam|wrist_right_cam)/image_raw$'
```

Run the IC Spine and MCP conformance checks before dispatching the mission.
Access IC Console through loopback or an SSH tunnel and confirm that topology,
camera evidence, mission history, and host telemetry are fresh.

## 6. Run the reference mission

Submit this goal through IC Chat or another MCP-compatible harness:

> Reset and inspect the simulated cell. Pick left blue and right green
> together, then left green and right red together, then left red and right
> blue together. Verify both totes after each pair. Finally, haul both totes to
> the rack and verify completion.

The expected control flow is:

1. reset and visually inspect the two work areas;
2. execute and verify three paired-arm placements;
3. haul each loaded tote;
4. visually verify the rack; and
5. retain the complete tool, result, telemetry, and camera-evidence journal.

## Validation checklist

- IC Spine health reports a live ROS context and fresh required signals.
- All required camera topics produce changing frames.
- The VLM returns structured evidence from a fresh recorded frame.
- Both GR00T profiles report the same checkpoint identity.
- Both relays and bridge-derived readiness records are valid.
- Scene reset restores both three-object work areas and the executor home state.
- Every paired placement returns `success:true` and `verified:true` for both
  arms before the next pair begins.
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
