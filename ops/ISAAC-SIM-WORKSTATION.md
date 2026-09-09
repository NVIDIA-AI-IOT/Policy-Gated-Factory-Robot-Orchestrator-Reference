# Scripted Isaac Sim workstation

isaac-sim-workstation.sh prepares and launches the scripted, learned-policy-free
baseline on the validated x86_64 Linux RTX simulation host. It uses the
packaged ic_cell, ic_boot.py, and our_factory.usda; it does not install
or start GR00T, a Thor bridge, IC Spine, or an agent.

The deterministic host root is:

    ~/.local/share/policy-gated-factory-robot-orchestrator-reference/isaac-sim

Its scripts child is mounted read-only at /scripts. Cache, configuration,
data, and log leaves are writable by the image's unprivileged isaac-sim
user, but their parent remains private to the host user.

## Host prerequisites

The repository validates the simulation host but does not install or replace
its NVIDIA driver, Docker Engine, or NVIDIA Container Toolkit. On a fresh
Ubuntu x86_64 RTX workstation, install those components using NVIDIA's
[Isaac Sim container setup](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_container.html)
and [technical requirements](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html),
then install the X11 helpers used by the launch scripts:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends xauth x11-xserver-utils
```

If Docker group membership was added during installation, log out and back in.
Run these checks without `sudo` from the local desktop account that will own
Isaac Sim:

```bash
uname -m                                      # x86_64
nvidia-smi                                    # RTX GPU and driver are visible
docker version --format '{{.Server.Version}}'
docker run --rm --gpus all \
  nvcr.io/nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi
command -v xauth xhost
printf 'DISPLAY=%s\n' "${DISPLAY:?run from the local X11 desktop}"
```

Do not continue until the GPU container smoke test succeeds. The pinned Isaac
image is much larger and will not repair a broken host driver/runtime setup.

## Prepare and validate

Pull the manifest-pinned image only after reviewing and accepting NVIDIA's
[Isaac Sim license](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/common/NVIDIA_Omniverse_License_Agreement.html):

    docker pull nvcr.io/nvidia/isaac-sim:6.0.0-dev2@sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9

Then stage the baseline and run the read-only check from the local X11 desktop
that will own the Isaac Sim window:

```bash
(
  set -euo pipefail
  ops/isaac-sim-workstation.sh --prepare
  : "${DISPLAY:?run from the local X11 desktop}"
  ops/isaac-sim-workstation.sh --check
)
```

Preparation never pulls an image or starts, stops, removes, or replaces a
container. It is idempotent when the staged files exactly match the checkout.
It refuses a partial, modified, or stale bundle; use a new --mount instead of
silently mixing packages.

## Launch

The launcher uses the caller's actual `DISPLAY` and `XAUTHORITY`. GDM commonly
stores the cookie under the user's runtime directory; a non-GDM desktop must set
its own readable cookie path:

```bash
(
  set -euo pipefail
  : "${DISPLAY:?run from the local X11 desktop}"
  export XAUTHORITY="${XAUTHORITY:-/run/user/$(id -u)/gdm/Xauthority}"
  test -r "$XAUTHORITY"
  xauth -f "$XAUTHORITY" nlist "$DISPLAY" | grep -q .
  ops/isaac-sim-workstation.sh --run --accept-eula
)
```

The measured GDM workstation used `DISPLAY=:1`; that is an observation, not a
portable default. Do not copy it over the value in the local desktop session.

Privacy telemetry is off by default. The launcher explicitly disables anonymous
data, the telemetry endpoint, crash reporting, and the usage, performance, and
personalization consent settings; merely omitting `PRIVACY_CONSENT` is not
sufficient for the pinned development image. Add `--privacy-consent` only to
opt in.
The command waits up to 900 seconds by default. A successful launch emits:

    IC_ISAAC_BASELINE_STARTING container=ic-isaac-sim-baseline ...
    IC_ISAAC_BASELINE_READY container=ic-isaac-sim-baseline marker=IC_CELL_UP

Follow the underlying application output with:

    docker logs -f ic-isaac-sim-baseline

The authoritative application marker is IC_CELL_UP markers=all, emitted only
after the deferred scene reset and clean physics ticks. The launcher checks
bootstrap/step errors before accepting that marker and observes a short
post-ready stability window. A launch that reports IC_CELL_BOOT_ERR or
IC_STEP_ERR, exits early, or times out fails and leaves the container intact
for inspection. The launcher never stops or removes it.

## Remote viewing and NVIDIA alignment

The current launch helper starts the pinned Isaac Sim windowed application on
a real local X11 display. It does not start a WebRTC signaling server or a
browser viewer.

| Access mode | Status in this repository | Client or endpoint | Inbound ports |
|---|---|---|---|
| Local X11 | Validated compatibility path | Workstation display selected by `DISPLAY` | None added by Isaac Sim |
| RealVNC desktop mirror | Optional external operator setup; not provisioned by this repository | RealVNC Viewer to `<sim-host-ip>:5900`; this is not an HTTP URL | Normally `5900/tcp`, restricted to the operator address |
| NVIDIA Isaac Sim WebRTC Streaming Client | NVIDIA-recommended remote path; not yet automated or validated here | Native client to `<sim-host-ip>` | `49100/tcp` and `47998/udp` |
| NVIDIA browser viewer | NVIDIA Docker Compose path; not included in this repository | Chromium at `http://<sim-host-ip>:8210` | `8210/tcp`, `49100/tcp`, and `47998/udp` |

For this validated GUI-container path, use RealVNC only to mirror an
already-working real local desktop. It must not provide the virtual display on
which Isaac Sim starts: NVIDIA warns that container GUI mode needs a real local
display and can fail to create its Vulkan swapchain on VNC and other virtual
displays. Before installing or enabling
[RealVNC Server](https://help.realvnc.com/hc/en-us/articles/360002253198-Installing-and-Removing-RealVNC-Connect-Advanced-users),
establish an exact source-address firewall rule. For a host that already uses
UFW, first confirm that it is active, has default-deny inbound policy, and has
no broader rule for port 5900; then add and review the operator rule:

```bash
SIM_IF=YOUR_SIMULATION_INTERFACE
OPERATOR_IP=YOUR_OPERATOR_IP
sudo ufw status verbose
sudo ufw status numbered
sudo ufw allow in on "$SIM_IF" proto tcp \
  from "$OPERATOR_IP" to any port 5900 \
  comment 'RealVNC from Isaac Sim operator'
sudo ufw status numbered
```

If UFW is not installed, establish the site's equivalent host or upstream
control before continuing; do not install or reconfigure a firewall blindly on
a remotely administered workstation. If VNC is already listening without that
control, use the local desktop to stop or restrict it first. Then install,
license, authenticate, encrypt, and enable RealVNC separately and verify it:

```bash
systemctl is-active vncserver-x11-serviced.service
ss -ltn | grep ':5900 '
```

Open RealVNC Viewer on the operator machine and connect to
`<sim-host-ip>:5900`. A browser cannot open that VNC endpoint. RealVNC mirrors
the entire workstation desktop, not only Isaac Sim, so retain normal VNC
authentication and never expose it to the public Internet.

For NVIDIA's documented remote presentation path, follow the
[Livestream Clients](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/manual_livestream_clients.html)
guide and implement a separate tested headless profile. WebRTC requires
`--network=host` and `ISAACSIM_HOST=<sim-host-ip>`; Docker bridge networking
and `-p` publication are not supported. The native and browser streaming
endpoints have no built-in authentication or encryption, so keep them on a
private/trusted network and restrict every inbound port to the operator IP.
NVIDIA Isaac Sim livestreaming requires an NVIDIA GPU with NVENC support and a
compatible driver. Each Isaac Sim instance can use only one livestreaming
method and accept only one streaming client at a time.
Port `8210` exists only when NVIDIA's browser-viewer Compose service is running;
it is not available from this repository's current launcher.

## Network and asset caveats

Docker host networking is required for the containerized ROS 2 seam. The
launcher gives Isaac a bounded, 2 GiB, shareable IPC namespace because Fast DDS
uses shared memory for same-host payloads; fully isolated IPC namespaces can
discover publishers over UDP while silently receiving no samples. This is not
host IPC: only a deliberately joined container shares it. The baseline also
sets ROS_LOCALHOST_ONLY=1 and ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST, so DDS
discovery remains loopback-only unless an operator deliberately uses another
launcher. No Docker ports are published.

An external ROS 2 Jazzy container must select the same RMW and join Isaac's IPC
namespace as the image's UID/GID (`1234:1234`). Matching ownership is required
because Fast DDS creates per-participant shared-memory files with owner-write
permissions. For example, after pulling the official ROS image, list topics with:

    docker run --rm --network host \
      --ipc=container:ic-isaac-sim-baseline \
      --user 1234:1234 \
      -e HOME=/tmp \
      -e ROS_DOMAIN_ID=0 \
      -e ROS_LOCALHOST_ONLY=1 \
      -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
      -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
      ros@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4 \
      ros2 topic list --no-daemon --spin-time 5 -t

The scene references NVIDIA's Isaac 6.0 cloud assets. First launch therefore
needs outbound HTTPS access to
omniverse-content-production.s3-us-west-2.amazonaws.com; later launches use
the persistent cache. This reference path requires a local X11 display. It is
not the repository's headless or learned-policy deployment path.

Before a deliberate retry, inspect the retained container and its logs. Stop
it explicitly if it is still running, then remove the stopped container:

    docker inspect ic-isaac-sim-baseline
    docker logs ic-isaac-sim-baseline
    docker stop ic-isaac-sim-baseline
    docker rm ic-isaac-sim-baseline
