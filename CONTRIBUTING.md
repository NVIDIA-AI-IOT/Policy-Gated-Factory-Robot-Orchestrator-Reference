# Contributing to Policy-Gated Factory Robot Orchestrator Reference

Thank you for contributing to Policy-Gated Factory Robot Orchestrator
Reference.

## Development environment

CI uses:

- Ubuntu 24.04;
- Python 3.12.3;
- Node.js 22.22.3; and
- uv 0.11.32.

Use the pinned lockfiles. Do not update dependencies as a side effect of an
unrelated change.

## Validation

Run the tests for each changed component. The complete hardware-free CI
workflow is defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

PGFR Spine:

```bash
uv sync --frozen --extra dev --project pgfr-spine
uv run --frozen --project pgfr-spine pytest -q pgfr-spine/tests
```

Chat, Workflows, Console, and MCP:

```bash
uv sync --frozen --extra dev --project servers/pgfr-chat
uv run --frozen --project servers/pgfr-chat pytest -q servers/pgfr-chat/tests

uv sync --frozen --extra dev --project servers/pgfr-workflows
uv run --frozen --project servers/pgfr-workflows pytest -q servers/pgfr-workflows/tests

uv sync --frozen --extra dev --project pgfr-console
uv run --frozen --project pgfr-console pytest -q pgfr-console/tests

uv sync --frozen --extra dev \
  --project servers/policy-gated-factory-robot-orchestrator-reference-mcp
uv run --frozen \
  --project servers/policy-gated-factory-robot-orchestrator-reference-mcp \
  pytest -q servers/policy-gated-factory-robot-orchestrator-reference-mcp/tests
```

OpenClaw plugin:

```bash
npm ci
npm test
npm audit --audit-level=high
```

Validate shell and documentation changes with the relevant contract tests:

```bash
bash -n ops/*.sh
uv run --frozen --project servers/pgfr-workflows pytest -q \
  ops/test_deployment_contracts.py \
  ops/test_groot_sim_host_contract.py \
  ops/test_isaac_sim_acceptance.py \
  ops/test_isaac_sim_workstation.py
git diff --check
```

The release gate also runs the configured Ruff checks for PGFR Spine and skills,
and strict Mypy for all PGFR Spine source and tests:

```bash
uv run --frozen --project pgfr-spine ruff check pgfr-spine skills ops/validate-packages.py
(cd pgfr-spine && uv run --frozen mypy)
```

Build and validate all seven Python distributions with:

```bash
python3 ops/validate-packages.py
```

Use Python 3.12 and the CI-pinned uv. This gate rebuilds wheels from standalone
source archives, checks package assets and license metadata, then installs all
seven wheels into a temporary environment outside the checkout. It checks
imports, entry points, dependency consistency, and Console HTTP assets without
starting host services. Templates and the Thor upstream environment are not
release distributions.

Every Hatchling build-system declaration pins its backend version. Package-local `LICENSE`,
`NOTICE`, and `THIRD-PARTY-NOTICES.md` are regular copies so source archives can
be rebuilt without the monorepo. After changing a canonical root legal file,
refresh the copies with `python3 ops/validate-packages.py --sync-legal`; CI
rejects missing or stale copies.

## Change guidelines

- Keep production behavior, tests, and operator documentation in the same
  change.
- Preserve the deny-by-default action and verification contracts.
- Do not add credentials, generated host state, model weights, or simulator
  caches to the repository.
- Use a Conventional Commits prefix such as `feat:`, `fix:`, `docs:`,
  `test:`, or `chore:`. Add a scope when it improves clarity.
- TypeScript integration work uses the pinned OpenClaw dependency and the
  plugin under [`plugins/openclaw/`](plugins/openclaw/).

## Developer Certificate of Origin

Contributions must be certified under the [Developer Certificate of Origin 1.1](DCO.txt).
Add a `Signed-off-by` line to every commit with:

```bash
git commit -s
```

The sign-off certifies that you have the right to submit the contribution under
the repository's open-source license. It is not a copyright assignment.

By making a contribution to this project, I certify that:

> (a) The contribution was created in whole or in part by me and I have the
> right to submit it under the open source license indicated in the file; or
>
> (b) The contribution is based upon previous work that, to the best of my
> knowledge, is covered under an appropriate open source license and I have the
> right under that license to submit that work with modifications, whether
> created in whole or in part by me, under the same open source license (unless
> I am permitted to submit under a different license), as indicated in the
> file; or
>
> (c) The contribution was provided directly to me by some other person who
> certified (a), (b) or (c) and I have not modified it.
>
> (d) I understand and agree that this project and the contribution are public
> and that a record of the contribution (including all personal information I
> submit with it, including my sign-off) is maintained indefinitely and may be
> redistributed consistent with this project or the open source license(s)
> involved.

## License

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE).
