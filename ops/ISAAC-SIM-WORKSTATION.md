# Scripted Isaac Sim workstation

`isaac-sim-workstation.sh` prepares, validates, and launches the scripted
baseline on an x86_64 Linux RTX workstation. It uses no learned policy.
The supported default is NVIDIA Isaac Sim 6.0.1 in NVIDIA's official NGC
container, running headless with the native WebRTC streaming service. The
repository does not build a custom Isaac Sim image.

This path loads `pgfr_cell`, `pgfr_boot.py`, and `our_factory.usda` through a
read-only mount. It does not install or start GR00T, a Thor bridge, PGFR Spine, or
an agent. The GR00T launcher remains a separate, explicitly pinned
6.0.0-dev2/X11 compatibility path.

The default external host state is:

    ~/.local/share/policy-gated-factory-robot-orchestrator-reference/isaac-sim

Its `scripts` child is mounted read-only. Writable cache, configuration, data,
and log directories serve the image's documented `1234:1234` user; their parent is
mode `0700` and private to the host account.

## Host prerequisites

The repository validates but does not install or replace the NVIDIA driver,
Docker Engine, or NVIDIA Container Toolkit. Follow NVIDIA's
[Isaac Sim container setup](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/install_container.html)
and
[technical requirements](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/requirements.html).

The host preflight requires:

- Ubuntu 22.04 or 24.04 (runtime validation used 24.04);
- at least 4 available CPU cores and 32 GB RAM;
- at least 50 GB total capacity on the filesystem holding the state cache;
- an RTX GPU with at least 16 GiB VRAM;
- NVIDIA Linux driver 595.58.03 or newer, the baseline enforced by this
  project's preflight;
- Docker with the NVIDIA runtime; and
- `python3`, `ip`, and `ss` on the host.

These checks cover the repository's x86_64 profile; see the
[support matrix](../docs/SUPPORT.md) for measured configurations and limits.
The default headless profile needs no X11, `xhost`, `DISPLAY`, or Xauthority.

Verify the unprivileged host account before pulling the large Isaac image:

```bash
uname -m
. /etc/os-release
printf 'OS=%s %s\n' "$ID" "$VERSION_ID"
nproc
awk '/^MemTotal:/ {printf "RAM: %.1f GiB\n", $2/1024/1024}' /proc/meminfo
df -h "$HOME"
nvidia-smi
docker version --format '{{.Server.Version}}'
docker info --format '{{json .Runtimes}}'
command -v python3 ip ss
```

If Docker group membership was added during installation, log out and back in.
Do not continue until Docker and `nvidia-smi` work without `sudo`.
The checker enforces the 50,000,000,000-byte capacity baseline on
`STATE_ROOT/cache` and reports its currently available bytes separately. It
does not require 50 GB to be free.

## Pull, prepare, and validate

Review and accept NVIDIA's
[Isaac Sim Additional Software and Materials License](https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/),
then pull the qualified immutable amd64 image:

```bash
docker pull --platform linux/amd64 \
  nvcr.io/nvidia/isaac-sim:6.0.1@sha256:b1c542b2ecc549b3d1ebb78c25664aa3bacba1709e6ad8e0a68e09426d57dedb
ops/isaac-sim-workstation.sh --prepare
ops/isaac-sim-workstation.sh --check --accept-eula
```

`--accept-eula` is an explicit operator choice for each check or launch. The
helper does not infer acceptance from an environment variable. Keep NVIDIA's
runtime and asset notices; the project's source license does not replace them.

Preparation never pulls an image or starts, stops, removes, or replaces a
container. It builds and validates the complete bundle in a sibling directory,
then publishes it with one same-filesystem directory rename. Consumers cannot
observe a partially copied set of entrypoints. An existing complete bundle is
verified byte-for-byte and reused; a modified, stale, or partially populated
mount is rejected rather than overwritten.

`--check` first runs the repository host preflight, then starts only a
transient `--rm` container at the same image digest to run NVIDIA's bundled
`isaac-sim.compatibility_check.sh`. It requires the official result and emits:

    System checking result: PASSED
    PGFR_ISAAC_NVIDIA_CHECK_OK image=... result=PASSED
    PGFR_ISAAC_BASELINE_CHECK_OK mount=... image=... profile=headless

The check container runs as `1234:1234`, uses host networking, never pulls an
image, and has anonymous telemetry disabled. It leaves no named container.
A headless preflight also confirms that `ISAACSIM_HOST` is a literal address
assigned to a real host interface.

## Launch the supported headless/WebRTC profile

Launch for a local client:

```bash
ops/isaac-sim-workstation.sh --run --accept-eula
```

It advertises `127.0.0.1`, signaling on `49100/tcp` and media on
`47998/udp`. It uses `--network host`, the image's `runheadless.sh -v`
entrypoint, and explicit user `1234:1234`. The launcher repeats the host and
official compatibility gates before starting the named application container.

For a native WebRTC client on another trusted machine, select a literal IP
assigned to the workstation:

```bash
SIM_HOST_IP=REPLACE_WITH_WORKSTATION_INTERFACE_IP
ops/isaac-sim-workstation.sh --run --accept-eula \
  --webrtc-host "$SIM_HOST_IP"
```

Optional port overrides are explicit:

```bash
ops/isaac-sim-workstation.sh --run --accept-eula \
  --webrtc-host "$SIM_HOST_IP" \
  --webrtc-signal-port 49100 \
  --webrtc-stream-port 47998
```

A successful default-profile launch requires the project marker, NVIDIA's
streaming-app marker, a running container after the stability window, and a
listening signaling TCP socket. It emits the advertised address and
ports:

    PGFR_ISAAC_BASELINE_STARTING container=pgfr-isaac-sim-baseline ... profile=headless webrtc_host=... signal_tcp=49100 stream_udp=47998
    PGFR_ISAAC_BASELINE_READY container=pgfr-isaac-sim-baseline profile=headless marker=PGFR_CELL_UP streaming=true webrtc_host=... signal_tcp=49100 stream_udp=47998

The launcher checks `49100/tcp` after readiness. It deliberately does not
require a pre-client `47998/udp` socket because media binding can occur during
client negotiation. Follow startup with:

    docker logs -f pgfr-isaac-sim-baseline

Use NVIDIA's
[Isaac Sim WebRTC Streaming Client](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/manual_livestream_clients.html)
and connect to the advertised host. This native-client endpoint is not an HTTP
URL. The launcher does not include NVIDIA's separate browser-viewer Compose
service, so it does not serve port `8210`.

Isaac Sim livestreaming provides no application authentication and is not a
production access-control boundary. Keep it on a trusted private network and
authorize only the intended operator source. For a host that already uses UFW
with default-deny inbound policy:

```bash
SIM_IF=REPLACE_WITH_WORKSTATION_INTERFACE
OPERATOR_IP=REPLACE_WITH_OPERATOR_SOURCE_IP
sudo ufw status verbose
sudo ufw status numbered
sudo ufw allow in on "$SIM_IF" proto tcp \
  from "$OPERATOR_IP" to any port 49100 \
  comment 'Isaac Sim WebRTC signaling'
sudo ufw allow in on "$SIM_IF" proto udp \
  from "$OPERATOR_IP" to any port 47998 \
  comment 'Isaac Sim WebRTC media'
sudo ufw status numbered
```

If UFW is absent, use the site's equivalent host or upstream controls. Do not
install, disable, or reconfigure a firewall blindly on a remote workstation.

## Run the scripted-baseline acceptance gate

The acceptance command is scene-destructive. It resets the scene, requires
fresh payloads on all 15 camera/state streams, issues exactly one simulated
`franka_left` red-object move, verifies the result, performs a final
deterministic reset, and scans only the current container run for critical
errors. It is the non-Thor scripted-baseline gate; it is not GR00T or Thor
inference evidence.

For the default launcher container:

```bash
docker pull --platform linux/amd64 \
  docker.io/library/ros:jazzy-ros-base-noble@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4
ops/accept-isaac-sim-workstation.sh \
  --container pgfr-isaac-sim-baseline
```

The harness requires the exact pinned image, launcher user/entrypoint/arguments,
read-only `/scripts` bind, and byte-identical checkout payload before it
publishes. It infers `ROS_DOMAIN_ID` from the target container; use
`--ros-domain-id ID` only to confirm the exact target value. A mismatch is
rejected rather than overridden. It never stops or removes the target. Success
ends with:

    PGFR_ISAAC_WORKSTATION_ACCEPTANCE_PASS container=pgfr-isaac-sim-baseline domain=<id> run_id=<id>

Run this gate only while no other operator or workflow is using the scene.

## Telemetry

Anonymous telemetry is off by default. Both the compatibility container and
the application container set NVIDIA's documented
`OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1`. The application also retains
validated Kit-level telemetry, crash-reporting, and privacy settings as defense
in depth.

`--privacy-consent` explicitly opts the application container in by setting
`PRIVACY_CONSENT=Y` and omitting the opt-out environment variable and
Kit-level overrides. The transient compatibility check remains opted out.

## Explicit local-X11 compatibility alternative

Container GUI mode is not the supported default. NVIDIA generally recommends
headless/WebRTC for a remote container and warns that container GUI mode needs
a real local display. Use this profile only from the local desktop, not a
virtual VNC/NoMachine/DCV display:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends xauth
export XAUTHORITY="${XAUTHORITY:-/run/user/$(id -u)/gdm/Xauthority}"
test -r "$XAUTHORITY"
xauth -f "$XAUTHORITY" nlist "${DISPLAY:?run from the local X11 desktop}" |
  grep -q .
ops/isaac-sim-workstation.sh --check --profile x11 --accept-eula
ops/isaac-sim-workstation.sh --run --profile x11 --accept-eula
```

The helper copies only the selected display cookie into its private runtime
state. It does not require or invoke broad `xhost` authorization. A non-GDM
desktop should set its own readable Xauthority path. Never copy an observed
`DISPLAY=:1` value blindly.

RealVNC remains external workstation administration, not the canonical Isaac
stream. It may mirror an already-working real local desktop, but it must not
supply the virtual display on which Isaac starts. Retain VNC authentication and
encryption, restrict `5900/tcp` to intended administrators, and never expose
it to the public Internet.

## ROS 2, networking, and assets

The baseline uses host networking plus a bounded, 2 GiB, shareable IPC namespace
because same-host Fast DDS payload delivery needs shared memory. It is not host
IPC. The baseline uses Jazzy's `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`; it
does not also set the deprecated `ROS_LOCALHOST_ONLY`, which would override the
modern setting. This standalone profile does not open ROS discovery to Thor or
another machine.

A ROS 2 Jazzy sidecar must join the Isaac container's IPC namespace, select the
same RMW, and use the matching `1234:1234` identity. For example:

    docker run --rm --network host \
      --ipc=container:pgfr-isaac-sim-baseline \
      --user 1234:1234 \
      -e HOME=/tmp \
      -e ROS_DOMAIN_ID=0 \
      -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
      -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
      ros@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4 \
      ros2 topic list --no-daemon --spin-time 5 -t

The scene uses NVIDIA's version-matched Isaac 6.0 cloud asset root. A cold first
run needs outbound HTTPS access to
`omniverse-content-production.s3-us-west-2.amazonaws.com`; warm runs use the
persistent cache. The cloud assets themselves are not content-digest pinned.

NVIDIA's Isaac Sim 6.0.1
[Setup Tips](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/install_faq.html)
document a five-part local asset pack. NVIDIA publishes these MD5 values:

| Part | MD5 |
|---|---|
| 001 | `92149a1f50a21c0f04cca6507ab00653` |
| 002 | `9b4b924e2d31bce41712d7637a0d6e42` |
| 003 | `b1c62924beda91251d3f5318ffec2b00` |
| 004 | `6bd7aa4d9b6c4161c2302e4c9418ade7` |
| 005 | `c4a17942014be6b50492ae860496fef7` |

This repository does not download or install that pack, and the local/offline
path has not been qualified here. Only cold-online and warm-cache cloud
behavior has been validated; do not claim offline support until the exact
NVIDIA procedure and scene assets pass the acceptance gate.

## Inspection and deliberate retry

A failure leaves the named application container intact. Inspect it before a
deliberate retry:

```bash
docker inspect pgfr-isaac-sim-baseline
docker logs pgfr-isaac-sim-baseline
docker stop pgfr-isaac-sim-baseline
docker rm pgfr-isaac-sim-baseline
```

The launcher itself never stops, removes, or replaces an application container.
