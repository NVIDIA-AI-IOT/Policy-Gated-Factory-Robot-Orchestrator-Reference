#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Inject the canonical floor playbook (skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/PLAYBOOK.md)
# into an OpenClaw workspace AGENTS.md, between PGFR-PLAYBOOK markers. Idempotent:
# re-running replaces the marked block; a legacy unmarked copy of the sections is
# removed on first run. Always writes a timestamped .bak next to the target.
#
# Usage (run on the machine that hosts the profile, normally Thor):
#   ops/sync-playbook.sh                                  # Policy-Gated Factory Robot Orchestrator Reference profile (default)
#   ops/sync-playbook.sh ~/.openclaw/workspace/AGENTS.md  # classic profile (opt-in)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO/skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/PLAYBOOK.md"
TGT="${1:-$HOME/.policy-gated-factory-robot-orchestrator-reference/openclaw/workspace/AGENTS.md}"
LEGACY_GUARD="$REPO/ops/pgfr-legacy-guard.sh"
[ -r "$LEGACY_GUARD" ] || { echo "missing $LEGACY_GUARD" >&2; exit 1; }
# shellcheck disable=SC1090
. "$LEGACY_GUARD"
[ -f "$SRC" ] || { echo "missing $SRC" >&2; exit 1; }
[ -f "$TGT" ] || { echo "missing $TGT" >&2; exit 1; }
cp "$TGT" "$TGT.bak.$(date +%Y%m%d-%H%M%S)"
python3 - "$SRC" "$TGT" "$PGFR_LEGACY_PLAYBOOK_MARKER" <<'PY'
import re, sys
src, tgt, legacy_marker = sys.argv[1], sys.argv[2], sys.argv[3]
BEGIN = "<!-- PGFR-PLAYBOOK-BEGIN (synced from skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/PLAYBOOK.md - edit there, then rerun ops/sync-playbook.sh) -->"
END = "<!-- PGFR-PLAYBOOK-END -->"
MARKED_BLOCK = re.compile(r"<!-- PGFR-PLAYBOOK-BEGIN\b.*?<!-- PGFR-PLAYBOOK-END -->", re.S)
LEGACY_MARKED_BLOCK = re.compile(
    rf"<!-- {re.escape(legacy_marker)}-BEGIN\b.*?"
    rf"<!-- {re.escape(legacy_marker)}-END -->",
    re.S,
)
play = open(src).read()
m = re.search(r"^## ", play, re.M)  # drop the H1 + header comment; keep the sections
play = play[m.start():].strip()
block = f"{BEGIN}\n\n{play}\n\n{END}"
text = open(tgt).read()
if MARKED_BLOCK.search(text):
    # Match the stable PGFR marker rather than its embedded source path so an
    # existing profile remains replaceable when the full-form directory moves.
    text = MARKED_BLOCK.sub(block, text, count=1)
elif LEGACY_MARKED_BLOCK.search(text):
    # Replace the pre-rename generated block in place. The old marker spelling
    # is supplied by the central migration guard and is never duplicated here.
    text = LEGACY_MARKED_BLOCK.sub(block, text, count=1)
else:
    # first run: strip the legacy unmarked sections, insert the block after the title
    text = re.sub(r"^## Floor operating rule \([^\n)]*\).*?(?=^## (?!Floor)|\Z)",
                  "", text, flags=re.S | re.M)
    lines = text.split("\n")
    lines.insert(1, "\n" + block)
    text = "\n".join(lines)
open(tgt, "w").write(text)
print(f"synced playbook -> {tgt}")
PY
