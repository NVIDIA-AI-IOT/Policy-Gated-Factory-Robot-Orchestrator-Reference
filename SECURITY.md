# Security Policy

Report potential security vulnerabilities through the
[NVIDIA Product Security vulnerability reporting process](https://www.nvidia.com/en-us/product-security/report-vulnerability/).
Do not open a public issue or pull request that discloses an unpatched
vulnerability, exploit path, credential, or security-sensitive proof of concept.

## Trust model (current state)

Policy-Gated Factory Robot Orchestrator Reference is **local-first agent infrastructure for trusted factory operators**. It is not
designed today as a shared multi-tenant boundary between adversarial users on
one gateway. Production hardening—such as sandbox and policy enforcement,
NIM-routed inference, tamper-resistant audit records, and operator RBAC—requires
a separate design, threat review, and acceptance record. It is not implemented
or promised by the current reference deployment.

Loopback services plus SSH forwarding are the default remote-access boundary.
The reproduction guide also documents an explicit lab-only shared trusted-LAN
Chat mode. That exception is not authentication or production hardening: every
client with network reach to its Chat listener can reproduce the public CSRF
header and obtain actuation authority, even without opening IC Console. Do not
enable it on an untrusted or mixed-user network.

## Known boundaries (documented, deferred by design)

These are accepted for the current local-first, single-operator posture. They
are hardening requirements before production remote write access; the
documented trusted-LAN lab exception does not satisfy them:

- **Floor seam has no authentication.** `POST /v1/dispatch` (which actuates the
  arm) is gated only by the policy (`x-role: operator` for operator actions) and
  a journaled, unauthenticated `x-mission-id` header. Any process with network
  reach to the seam can command the cell. The console/workflows/chat CSRF guards
  protect the *browser → gateway* hop, but the *gateway → seam* hop — the one
  that moves the arm — is unauthenticated. **Planned fix:** a shared bearer token
  (env `IC_FLOOR_TOKEN`) required by the seam and presented by every client
  (MCP server, ic-workflows runner, ic-chat tool loop, conformance kit), plus
  mutual-auth once remote access lands. Until then: keep the seam bound to
  `127.0.0.1`.
- **Write-path services (ic-workflows, ic-chat) require a header, not a secret,
  by default.** The `X-IC-Workflows` / `X-IC-Chat` guard defeats browser CSRF
  (forces a preflight the origin allowlist blocks), but with `IC_WORKFLOWS_TOKEN`
  / `IC_CHAT_TOKEN` unset any local process can call them. Set those tokens (and
  the future seam authentication) together when a reviewed authenticated
  deployment supports secure credential delivery. The trusted-LAN profile's
  literal `console` value is intentionally browser-visible and is not such a
  secret. A nonempty header alone does not compensate for the unauthenticated
  floor seam or absent TLS/per-user identity.
- **No per-session isolation / RBAC.** Mission journals, workflow specs, and chat
  sessions are readable by id with no ownership model — consistent with the
  single-trusted-operator assumption above.

## Scope of useful reports today

The most useful reports show a **current, reproducible boundary bypass with demonstrated impact**
against the Python orchestration engine (`ic-spine/`) or the gateway runtime that runs Policy-Gated Factory Robot Orchestrator Reference
agents. Scanner output, prompt-injection-only chains against the LLM, or reports that rely on hostile
users sharing one trusted gateway are usually not security vulnerabilities under this model.

## Third-party software

Third-party components retain their own licenses and security processes. See
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) for bundled or adapted code
and the package-manager lockfiles for resolved runtime dependencies.
