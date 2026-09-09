# Isaac-GR00T source patch

Policy-Gated Factory Robot Orchestrator Reference prepares NVIDIA Isaac-GR00T from upstream commit
`e5749287857afd97b78f1147166137de29746392` and applies
[`isaac-groot-e574-policy-gated-factory-robot-orchestrator-reference.patch`](isaac-groot-e574-policy-gated-factory-robot-orchestrator-reference.patch).
The patch contains the GR00T configuration, fine-tuning, model, evaluation,
policy, and inference-server changes used by the Policy-Gated Factory Robot Orchestrator Reference training and
serving workflow.

## Prepare the source

Run the repository preparation script from the repository root:

```bash
./ops/prepare-groot-runtime.sh --source-only
```

The script checks the patch SHA-256, clones the exact upstream revision into a
new destination, verifies that the patch applies cleanly, applies it, and
checks the resulting source diff. Set `PGFR_GROOT_SOURCE_ROOT` to select another
destination. Use `--install` to run the pinned Thor dependency installation
after source preparation.

Apply the patch through
[`ops/prepare-groot-runtime.sh`](../../../../ops/prepare-groot-runtime.sh), so
the upstream revision and integrity checks remain part of the operation.

## Runtime boundary

The patch prepares the GR00T source used for fine-tuning and policy serving.
It is not read by the Isaac executor or relay during a rollout. The rollout
implementation lives under [`../runtime/`](../runtime/) and
[`../relay/`](../relay/).
