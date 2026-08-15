# Security Policy

Report potential security vulnerabilities through the
[NVIDIA Product Security vulnerability reporting process](https://www.nvidia.com/en-us/product-security/report-vulnerability/).
Do not open a public issue or pull request that discloses an unpatched
vulnerability, exploit path, credential, or security-sensitive proof of concept.

## Trust model (current state)

Industrial Claw is **local-first agent infrastructure for trusted factory operators**. It is not
designed today as a shared multi-tenant boundary between adversarial users on one gateway. Hardening
for production deployment — NVIDIA NemoClaw sandboxing, OpenShell policy enforcement, NIM-routed
inference, audit logs, RBAC for operator accounts — lands in a later plan and will come with an
updated, more detailed security policy.

## Known boundaries (documented, deferred by design)

These are accepted for the current local-first, single-operator posture and are
the next hardening targets before anything binds beyond loopback:

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
  the seam token above) together when hardening for a shared host.
- **No per-session isolation / RBAC.** Mission journals, workflow specs, and chat
  sessions are readable by id with no ownership model — consistent with the
  single-trusted-operator assumption above.

## Scope of useful reports today

The most useful reports show a **current, reproducible boundary bypass with demonstrated impact**
against the Python orchestration engine (`ic-spine/`) or the gateway runtime that runs Industrial Claw
agents. Scanner output, prompt-injection-only chains against the LLM, or reports that rely on hostile
users sharing one trusted gateway are usually not security vulnerabilities under this model.

## Third-party software

Third-party components retain their own licenses and security processes. See
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) for bundled or adapted code
and the package-manager lockfiles for resolved runtime dependencies.
