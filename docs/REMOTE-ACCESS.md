# Access the reference system remotely

The default deployment binds Console, Chat, and Workflows to loopback on the
Jetson control host. Choose an access profile before changing any service bind
address.

| Profile | Operator capability | Exposure |
|---|---|---|
| SSH tunnel | Full Console and Chat access; optional Workflows API access | Recommended; services remain on loopback |
| Direct read-only Console | Topology, Inspector, GPU, camera evidence, mission history, and the Operational Assurance API | Port `8600/tcp`, restricted to an operator address |
| Trusted-LAN Console and Chat | Console plus write-capable Chat orchestration | Ports `8600/tcp` and `8620/tcp`; no application login or TLS |

OpenClaw port `18790` is a headless Gateway API, not a second dashboard.

## Contents

- [SSH tunnel](#ssh-tunnel)
- [Direct read-only Console](#direct-read-only-console)
- [Trusted-LAN Console and Chat](#trusted-lan-console-and-chat)
- [View Isaac Sim](#view-isaac-sim)

## SSH tunnel

For the complete UI, forward the Console and Chat ports from the operator
machine:

```bash
THOR_SSH=YOUR_THOR_USER@YOUR_THOR_IP
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8600:127.0.0.1:8600 \
  -L 127.0.0.1:8620:127.0.0.1:8620 \
  "$THOR_SSH"
```

Open `http://127.0.0.1:8600`; Chat opens by default. Keep the SSH process running
while using the UI.

For remote [Workflows API](../servers/pgfr-workflows/README.md) access, also add
`-L 127.0.0.1:8610:127.0.0.1:8610` to the SSH command. Workflows are managed
through that API; Console has no workflow editor.

## Direct read-only Console

Establish an exact source-address firewall rule on the Jetson control host or
at the network boundary **before** changing Console's bind address. On a host
that already uses UFW, confirm that UFW is active, has default-deny inbound
policy, and has no broader rule for port `8600`. Then add and review the exact
operator rule:

```bash
THOR_IF=YOUR_THOR_NETWORK_INTERFACE
OPERATOR_IP=YOUR_OPERATOR_IP
sudo ufw status verbose
sudo ufw status numbered
sudo ufw allow in on "$THOR_IF" proto tcp \
  from "$OPERATOR_IP" to any port 8600 \
  comment 'PGFR Console from operator'
sudo ufw status numbered
```

If UFW is not installed, use the site's equivalent host or upstream firewall.
Do not install or reconfigure a firewall blindly on a remotely administered
Jetson. Confirm that the alternative control is effective before continuing.

Only then edit `~/.config/pgfr-spine/console.env` and change:

```dotenv
PGFR_CONSOLE_HOST=0.0.0.0
```

`0.0.0.0` preserves the repository's loopback readiness probe while accepting
the firewalled LAN connection. Restart and verify only Console:

```bash
systemctl --user restart pgfr-console.service
systemctl --user is-active pgfr-console.service
ss -ltn | grep ':8600 '
```

From the operator machine, verify the endpoint and open Console:

```bash
THOR_IP=YOUR_THOR_IP
curl --fail "http://$THOR_IP:8600/api/health"
# Browser: http://YOUR_THOR_IP:8600
```

This profile exposes Console's read-only views. Use the SSH-tunnel profile
for Chat and optional Workflows API access. Keep `8610`, `8620`, `8766`,
`18790`, `8001`, GR00T policy and relay ports, and the GPU exporter private.

## Trusted-LAN Console and Chat

Use this profile only when every principal that can reach Console is also
authorized to command the cell. It has no login, per-user identity, token
expiry, or TLS. The static Console sends the public `X-PGFR-Chat: console` CSRF
value automatically. The origin check and required header reject browser
submissions from other origins, but `console` is not an authentication secret.
A non-browser client that can reach the admitted Chat listener can reproduce the
request. **Network reachability is actuation authority.**

Use the SSH-tunnel profile on an untrusted network or one shared with
non-operators. A production remote-write deployment requires an authenticated
TLS endpoint.

Before changing either bind address, authorize the same isolated trusted-LAN
CIDR for Console `8600/tcp` and Chat `8620/tcp`. Do not make Chat broader than
Console. With an active, default-deny UFW installation:

```bash
THOR_IF=YOUR_THOR_NETWORK_INTERFACE
TRUSTED_LAN_CIDR=YOUR_TRUSTED_LAN_CIDR
sudo ufw status verbose
sudo ufw status numbered
sudo ufw allow in on "$THOR_IF" proto tcp \
  from "$TRUSTED_LAN_CIDR" to any port 8600 \
  comment 'PGFR Console from trusted operator LAN'
sudo ufw allow in on "$THOR_IF" proto tcp \
  from "$TRUSTED_LAN_CIDR" to any port 8620 \
  comment 'PGFR Chat from trusted operator LAN'
sudo ufw status numbered
```

Use the site's equivalent boundary when UFW is not already the host firewall.
Verify that the two scopes are identical before continuing.

In `~/.config/pgfr-spine/console.env`, retain the internal loopback URL and add
the browser-visible URL using the literal Jetson control-host address:

```dotenv
PGFR_CONSOLE_HOST=0.0.0.0
PGFR_CHAT_URL=http://127.0.0.1:8620
PGFR_CHAT_PUBLIC_URL=http://YOUR_THOR_IP:8620
```

In `~/.config/pgfr-spine/chat.env`, bind Chat to the LAN, add the exact direct
Console origin without a trailing slash, and select the static UI's public
CSRF value. Preserve the two loopback origins so SSH-forwarded access still
works:

```dotenv
PGFR_CHAT_HOST=0.0.0.0
PGFR_CHAT_CORS=http://127.0.0.1:8600,http://localhost:8600,http://YOUR_THOR_IP:8600
PGFR_CHAT_TOKEN=console
```

Replace every `YOUR_*` placeholder before restarting. Restart only the two
affected services and verify both listeners and health endpoints:

```bash
systemctl --user restart pgfr-chat.service pgfr-console.service
systemctl --user is-active pgfr-chat.service pgfr-console.service
ss -ltn | grep -E ':(8600|8620) '
THOR_IP=YOUR_THOR_IP
curl --fail "http://$THOR_IP:8600/api/health"
curl --fail "http://$THOR_IP:8620/api/health"
# Browser: http://YOUR_THOR_IP:8600 (Chat opens by default).
```

Chat submits its policy-gated tool calls to PGFR Spine. Keep `8610`, `8766`,
`18790`, `8001`, GR00T policy and relay ports, and the GPU exporter private.
Use the optional Workflows API SSH forwarding above when remote workflow
creation, execution, or scheduling is needed.

## View Isaac Sim

The two-host GR00T launcher renders to the RTX simulation host's real local X11
desktop. Optional RealVNC access connects RealVNC Viewer directly to
`<simulation-host-ip>:5900`; it is not a browser URL and it mirrors the entire
workstation. RealVNC is external to this repository and must be authenticated,
encrypted, and firewalled to the operator address.

The separate standalone launcher defaults to NVIDIA's native headless WebRTC
service on `49100/tcp` and `47998/udp`. It does not include the browser-viewer
Compose service or port `8210`. A WebRTC client session has not yet been
acceptance-tested. See the
[workstation WebRTC procedure](../ops/ISAAC-SIM-WORKSTATION.md#launch-the-supported-headlesswebrtc-profile).
