#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# pgfr-e2e-cycle — one fix→test→verdict cycle for the chat-driven floor mission.
#
# Phases: preflight → reset+stage check → fire the mission through the console
# chat gateway → poll ground truth → verdict. Everything it asserts comes from
# the seam (physics) or the journal, never from the model's prose.
#
#   ops/pgfr-e2e-cycle.sh                 # full mission (default)
#   PASS_BAR=plumbing ops/pgfr-e2e-cycle.sh   # software chain only, no motion
#
# Verdict lands in /tmp/pgfr_e2e/verdict.json + cycle-<n>.log
set -o pipefail
SEAM="${PGFR_FLOOR_SERVICE:-http://127.0.0.1:8766}"
CHAT="${PGFR_CHAT_URL:-http://127.0.0.1:8620}"
PASS_BAR="${PASS_BAR:-mission}"
OUT=/tmp/pgfr_e2e; mkdir -p "$OUT"
N=$(( $(cat "$OUT/.n" 2>/dev/null || echo 0) + 1 )); echo "$N" > "$OUT/.n"
LOG="$OUT/cycle-$N.log"
say() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
jq_() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)" 2>/dev/null; }

say "== cycle $N (pass bar: $PASS_BAR) =="

# ---- preflight: every hop the mission needs -------------------------------
fail=0
for probe in "seam|$SEAM/v1/health" "chat|$CHAT/api/health"; do
  name="${probe%%|*}"; url="${probe##*|}"
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "$url")
  say "preflight $name: HTTP $code"; [ "$code" = "200" ] || fail=1
done
BACKEND=$(curl -s --max-time 8 "$CHAT/api/health" | jq_ "d.get('backend')")
say "chat backend: $BACKEND"
[ "$BACKEND" = "anthropic" ] || say "WARN: chat backend is '$BACKEND', not the gateway's brain"
CAMS=$(curl -s --max-time 8 "$SEAM/v1/health" | jq_ "len(d.get('camera_age_s') or {})")
say "cameras publishing: $CAMS"
[ "${CAMS:-0}" -ge 4 ] || say "WARN: fewer than 4 cameras (table_cam publisher may be down)"
[ "$fail" = "1" ] && { say "VERDICT: infra_fail (preflight)"; echo '{"cycle":'"$N"',"verdict":"infra_fail"}' > "$OUT/verdict.json"; exit 2; }

# ---- floor_state must carry world truth, not just endpoints ---------------
FS=$(curl -s --max-time 10 -X POST "$SEAM/v1/floor-state" -H 'content-type: application/json' -d '{}')
HAS_WORLD=$(echo "$FS" | jq_ "'yes' if any(k not in ('endpoints','_meta') for k in d) else 'no'")
say "floor_state carries world state: $HAS_WORLD"
[ "$HAS_WORLD" = "yes" ] || say "WARN: floor_state is endpoints-only — the brain will be blind"

if [ "$PASS_BAR" = "plumbing" ]; then
  say "VERDICT: plumbing_ok (backend=$BACKEND cams=$CAMS world=$HAS_WORLD)"
  printf '{"cycle":%s,"verdict":"plumbing_ok","backend":"%s","cameras":%s,"world_state":"%s"}\n' \
    "$N" "$BACKEND" "${CAMS:-0}" "$HAS_WORLD" > "$OUT/verdict.json"; exit 0
fi

# ---- reset + confirm the scene actually staged -----------------------------
# The spine advertises, as a LIVE guarantee: "Operator actions blocked from
# agents — reset/spawn/cancel ... an agent/workflow/chat can never actuate
# them." A harness that resets the scene itself would falsify that claim, so
# the reset stays an operator step. Set PGFR_OPERATOR_RESET=1 in the environment
# to declare "a human operator authorized this reset for this run".
if [ "${PGFR_OPERATOR_RESET:-0}" = "1" ]; then
  say "reset: operator-authorized for this run (PGFR_OPERATOR_RESET=1)"
  ~/bin/pgfr-reset-demo >> "$LOG" 2>&1; say "reset exit: $?"
  sleep 4
else
  say "reset: SKIPPED — operator action (run ~/bin/pgfr-reset-demo yourself, or set PGFR_OPERATOR_RESET=1)"
fi
STAGED=$(curl -s --max-time 60 -X POST "$SEAM/v1/perceive" -H 'content-type: application/json' \
  -d '{"target":"conveyor_1"}' | jq_ "len(d.get('blocks_on_table') or [])")
say "blocks staged on the table: ${STAGED:-0}"
[ "${STAGED:-0}" -ge 1 ] || { say "VERDICT: staging_fail (reset left the table empty)"
  printf '{"cycle":%s,"verdict":"staging_fail","staged":0}\n' "$N" > "$OUT/verdict.json"; exit 3; }

# ---- fire the mission through the console chat -----------------------------
SID="e2e-cycle-$N"
say "firing mission in session $SID"
curl -s --max-time 1800 -X POST "$CHAT/api/chat" -H 'content-type: application/json' -H 'X-PGFR-Chat: 1' \
  -d "{\"session_id\":\"$SID\",\"message\":\"check the table — if there is anything, sort it and shelve both totes\"}" \
  > "$OUT/reply-$N.json"
say "mission returned (transcript: $(wc -c < "$OUT/reply-$N.json") bytes)"

# ---- verdict from PHYSICS, not from the model's prose ----------------------
AFTER=$(curl -s --max-time 60 -X POST "$SEAM/v1/perceive" -H 'content-type: application/json' -d '{"target":"conveyor_1"}')
LEFT=$(echo "$AFTER" | jq_ "len(d.get('blocks_on_table') or [])")
RACK=$(curl -s --max-time 60 -X POST "$SEAM/v1/perceive" -H 'content-type: application/json' -d '{"target":"rack_1"}' | jq_ "(d.get('racks') or {}).get('rack_1', 0)")
say "after mission — blocks left on table: ${LEFT:-?} | totes on rack: ${RACK:-?}"

VERDICT=fail
[ "${LEFT:-9}" = "0" ] && [ "${RACK:-0}" -ge 2 ] && VERDICT=pass
[ "${LEFT:-9}" = "0" ] && [ "${RACK:-0}" = "1" ] && VERDICT=partial_one_tote
say "VERDICT: $VERDICT (staged=$STAGED left=${LEFT:-?} totes_shelved=${RACK:-?})"
printf '{"cycle":%s,"verdict":"%s","staged":%s,"left":%s,"totes_shelved":%s,"backend":"%s","cameras":%s}\n' \
  "$N" "$VERDICT" "${STAGED:-0}" "${LEFT:-9}" "${RACK:-0}" "$BACKEND" "${CAMS:-0}" > "$OUT/verdict.json"
[ "$VERDICT" = "pass" ]
