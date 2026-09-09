# One-GR00T fixed-layout validation — 2026-08-05

## Model and scope

- Model: `droid15_dual_shared3_layout3_e2e672_droid1f_steps3000_v2`
- Checkpoint fingerprint: `9da9e40ca8abac3fbdecde740d4b5b3143705dff95e6afbf0282bb8fdad66e32`
- Training: 3,000 steps over 672 fixed-layout demonstrations.
- Scope: layout `3/3`, seed `31302`, fixed green-red-blue order, both Franka arms, physical friction, three distractor shapes visible.
- Executor: unchanged v29, SHA256 `a8e72c73017cfd9d76f874d0eb83c15be8c004735d9a7ee7e2abbe38aa0d4f40`.

## Serial result

All six actions passed through IC Spine with physics-verified release and settle:

| Action | Offset from compartment center |
|---|---:|
| right green | 0.047 m |
| left green | 0.042 m |
| right red | 0.026 m |
| left red | 0.022 m |
| right blue | 0.066 m |
| left blue | 0.021 m |

Final state: empty conveyor; red, blue, and green present in both totes.

## Concurrent result

Concurrency used two independent instances of the same checkpoint, each receiving only B=1 inference:

- left: policy `5572`, relay `5612`
- right: policy `5571`, relay `5613`
- contract: `independent-b1-per-arm-v1`

All three atomic color pairs passed:

| Pair | Left result | Right result | Policy batches |
|---|---:|---:|---|
| green | 0.045 m | 0.042 m | left 18x B=1, right 18x B=1, 0x B=2 |
| red | 0.027 m | 0.030 m | left 17x B=1, right 17x B=1, 0x B=2 |
| blue | 0.005 m | 0.023 m | left 18x B=1, right 19x B=1, 0x B=2 |

The final right-blue query was a terminal B=1 request after the left arm had already completed. Final state again had an empty conveyor and all three shapes in both totes.

## Software verification

- Executor/floor tests: 36 passed.
- MCP proof-gate tests: 15 passed.
- OpenAPI JSON: valid.
- Executor bundle: all SHA256 entries verified.

The three specialist models remain the protected fallback. This validation does not claim arbitrary spawn positions, different object orders, or recovery from a deliberately dropped object.
