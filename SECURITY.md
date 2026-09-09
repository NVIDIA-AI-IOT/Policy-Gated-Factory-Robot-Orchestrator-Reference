# Security

## Report a vulnerability

Report potential vulnerabilities through the
[NVIDIA Product Security reporting process](https://www.nvidia.com/en-us/product-security/report-vulnerability/).
Do not open a public issue or pull request that contains an unpatched
vulnerability, exploit path, credential, or security-sensitive proof of
concept.

## Deployment trust model

Policy-Gated Factory Robot Orchestrator Reference is a single-operator
reference deployment for a trusted factory or lab network. It is not a
multi-tenant security boundary or a certified functional-safety system.

The default configuration keeps PGFR Spine, PGFR Chat, Workflows, OpenClaw, and
the model services on loopback. Remote operators connect through SSH
forwarding. The optional trusted-LAN profile exposes Console and Chat without
application authentication or TLS; every client that can reach Chat has
actuation authority. Do not use that profile on an untrusted or mixed-user
network.

## Known limitations

- **PGFR Spine has no client authentication.** The `x-role` and `x-mission-id`
  headers carry policy and journal context; they are not credentials. Any
  process that can reach PGFR Spine can submit floor requests.
- **The default Chat and Workflows headers provide CSRF protection, not user
  authentication.** The trusted-LAN `console` value is visible to the browser
  and can be reproduced by any network client.
- **Sessions and journals have no per-user authorization model.** A trusted
  local client can read another session or mission when it knows the
  identifier.
- **MCP and OpenClaw include effectful tools.** Access to the MCP standard
  input/output channel or OpenClaw configuration can include physical dispatch
  and operator scene reset.
- **The reference Fast DDS profile is not authenticated or encrypted.** Use it
  only on an isolated network, VPN, or a deployment with DDS Security.
- **Mission evidence is not tamper-resistant.** Protect the host, journal, and
  evidence directories according to the site's audit requirements.

Before production remote-write use, add an authenticated TLS ingress,
service-to-service authentication, per-user authorization, rate limits,
credential rotation, a deployment-specific threat review, and a
deployment-specific machinery-safety assessment.

## Recommended deployment controls

- Keep PGFR Spine, OpenClaw, model, GR00T policy, and relay listeners on
  loopback.
- Prefer the documented SSH-tunnel profile for Console, Chat, and Workflows.
- Restrict Isaac Sim streaming, VNC, SSH, and ROS 2 traffic to the required
  operator or peer addresses.
- Store API keys and access tokens only in the documented mode-`0600` secret
  files or an approved secret manager.
- Do not expose ports `8001`, `8600`–`8620`, `8766`, `18790`, or GR00T
  serving ports to the public Internet.

See [Remote access](docs/REMOTE-ACCESS.md) for the supported network profiles
and [Validation](docs/VALIDATION.md) for the action and evidence boundary.

## Scope of useful reports

Reports are most useful when they demonstrate a reproducible boundary bypass
with impact against PGFR Spine or the deployed agent and gateway path. Scanner
output without demonstrated impact, prompt-injection-only behavior, or attacks
that require an already trusted user to share the same local gateway may fall
outside this reference deployment's current threat model.

## Third-party software

Third-party components retain their own security and disclosure processes. See
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) and the package-manager
lockfiles for the exact runtime dependencies.
