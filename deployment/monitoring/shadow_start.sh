#!/usr/bin/env bash
# ArbiCore X — Shadow window start
# Kicks off the Wave-1 shadow observation window. Read-only operator action.
# Captures a baseline snapshot at T+0 and prints the next checkpoint times.
set -euo pipefail
cd "$(dirname "$0")/.."

WINDOW_HOURS="${1:-24}"
START_TS=$(date -u +%s)
LABEL=$(date -u +'%Y%m%dT%H%M%SZ')
EVIDENCE_DIR="evidence/shadow_${LABEL}"
mkdir -p "$EVIDENCE_DIR"

echo "[shadow] window length: ${WINDOW_HOURS} h"
echo "[shadow] evidence dir: ${EVIDENCE_DIR}"

scripts/snapshot.sh "${EVIDENCE_DIR}/t0_baseline.json"
echo "[shadow] T+0 baseline captured."

cat > "${EVIDENCE_DIR}/window.json" <<JSON
{
  "label": "${LABEL}",
  "start_ts": ${START_TS},
  "window_hours": ${WINDOW_HOURS},
  "checkpoints": {
    "t0":   ${START_TS},
    "t4h":  $((START_TS + 4*3600)),
    "t8h":  $((START_TS + 8*3600)),
    "t12h": $((START_TS + 12*3600)),
    "t24h": $((START_TS + 24*3600))
  }
}
JSON

echo "[shadow] window registered. Run scripts/snapshot.sh evidence/shadow_${LABEL}/tNN.json at each checkpoint."
echo "[shadow] abort with: scripts/shadow_abort.sh ${LABEL}"
