# GR00T capture context

This directory contains the distilled recorded arm states required by the
Policy-Gated Factory Robot Orchestrator Reference GR00T deployment. The installer copies them into the Isaac
scripts mount, and the deployment runtime selects the matching state by arm,
object color, and scene layout before executing a task.

## Layout

```text
<left|right>/<red|blue|green>/layout_<id>/ep_000/states.json
```

Each `states.json` retains the first recorded DROID joint state needed by the
runtime. The repository contains 18 files covering the supported arm, color,
and layout combinations. The primary two-arm demo uses layout 3; the other
entries preserve the additional supported layout alignments.

## Runtime use

[`ops/install-groot-cell.sh`](../../../../ops/install-groot-cell.sh) installs
these files under `/scripts/groot_capture_context`. The direct deployment in
[`../runtime/native_droid_work/pgfr_groot_certified_deployment_v36.py`](../runtime/native_droid_work/pgfr_groot_certified_deployment_v36.py)
loads the selected file and fails closed if it is missing or malformed.

These files are deployment alignment inputs, not a training dataset. The
public release does not supply demonstration images, full trajectories, or
policy actions. Follow the [dataset-creation guide](../groot_n1_7_pgfr_pipeline/docs/DATASET_CREATION.md)
to record your own demonstrations and the [model guide](../models/README.md)
to install the checkpoint trained from them.

Do not hand-edit a state to accommodate a changed scene. A new robot, camera,
object layout, or capture protocol requires a measured replacement followed by
runtime validation.
