#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Inject the canonical floor playbook (skills/industrial-claw-orchestrator/PLAYBOOK.md)
# into an OpenClaw workspace AGENTS.md, between IC-PLAYBOOK markers. Idempotent:
# re-running replaces the marked block; a legacy unmarked copy of the sections is
# removed on first run. Always writes a timestamped .bak next to the target.
#
# Usage (run on the machine that hosts the profile, normally Thor):
#   ops/sync-playbook.sh                                  # Industrial Claw profile (default)
#   ops/sync-playbook.sh ~/.openclaw/workspace/AGENTS.md  # classic profile (opt-in)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO/skills/industrial-claw-orchestrator/PLAYBOOK.md"
TGT="${1:-$HOME/.industrial-claw/openclaw/workspace/AGENTS.md}"
[ -f "$SRC" ] || { echo "missing $SRC" >&2; exit 1; }
[ -f "$TGT" ] || { echo "missing $TGT" >&2; exit 1; }
cp "$TGT" "$TGT.bak.$(date +%Y%m%d-%H%M%S)"
python3 - "$SRC" "$TGT" <<'PY'
import re, sys
src, tgt = sys.argv[1], sys.argv[2]
BEGIN = "<!-- IC-PLAYBOOK-BEGIN (synced from skills/industrial-claw-orchestrator/PLAYBOOK.md - edit there, then rerun ops/sync-playbook.sh) -->"
END = "<!-- IC-PLAYBOOK-END -->"
play = open(src).read()
m = re.search(r"^## ", play, re.M)  # drop the H1 + header comment; keep the sections
play = play[m.start():].strip()
block = f"{BEGIN}\n\n{play}\n\n{END}"
text = open(tgt).read()
if BEGIN in text and END in text:
    text = text.split(BEGIN)[0] + block + text.split(END, 1)[1]
else:
    # first run: strip the legacy unmarked sections, insert the block after the title
    text = re.sub(r"^## Floor operating rule \(Industrial Claw\).*?(?=^## (?!Floor))",
                  "", text, flags=re.S | re.M)
    lines = text.split("\n")
    lines.insert(1, "\n" + block)
    text = "\n".join(lines)
open(tgt, "w").write(text)
print(f"synced playbook -> {tgt}")
PY
