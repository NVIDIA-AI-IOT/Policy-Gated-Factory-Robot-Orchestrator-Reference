# Contributing to Industrial Claw

Thank you for your interest in contributing to Industrial Claw.

## If you're working on this repo

- **Python engine work** lives under [`ic-spine/`](ic-spine/).
- **Python tests must stay green** before any commit:
  ```bash
  cd ic-spine
  .venv/bin/ruff check src tests
  .venv/bin/mypy src tests
  .venv/bin/pytest
  ```
- **Commit style:** Conventional Commits prefix (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, etc.) with a scope
  when meaningful (`feat(agents): ...`, `docs(readme): ...`).
- **TypeScript runtime work** uses the pinned OpenClaw package dependency and
  the Industrial Claw plugin under [`plugins/openclaw/`](plugins/openclaw/).

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
