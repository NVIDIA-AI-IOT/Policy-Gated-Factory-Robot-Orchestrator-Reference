#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Verify an explicitly supplied local inference export before serving it.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_ROOT="${1:-${PGFR_GROOT_MODEL_ROOT:-}}"
[ "$#" -le 2 ] || { echo 'usage: ops/verify-groot-models.sh CHECKPOINT_DIRECTORY [EXPECTED_FINGERPRINT]' >&2; exit 2; }
[ -n "$MODEL_ROOT" ] || { echo 'verify-groot-models: ERROR: supply your local checkpoint export path (ops/export-groot-checkpoint.py)' >&2; exit 2; }
python3 - "$REPO/ops" "$MODEL_ROOT" "${2:-}" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from pgfr_checkpoint import verify_checkpoint
try:
    identity = verify_checkpoint(Path(sys.argv[2]))
    if sys.argv[3] and identity["checkpoint_fingerprint"] != sys.argv[3]:
        raise ValueError("checkpoint fingerprint differs from the installed serving identity")
except (OSError, ValueError) as exc:
    raise SystemExit(f"verify-groot-models: ERROR: {exc}") from exc
print(f"PGFR_GROOT_MODEL_VERIFIED model_root={sys.argv[2]} model_label={identity['model_label']} checkpoint_fingerprint={identity['checkpoint_fingerprint']}")
PY
