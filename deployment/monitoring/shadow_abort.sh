#!/usr/bin/env bash
# ArbiCore X — Shadow window abort (operator panic / regime shift)
# Marks the in-flight window as aborted and captures a final snapshot.
set -euo pipefail
cd "$(dirname "$0")/.."

LABEL="${1:?Usage: shadow_abort.sh <window_label>}"
EVIDENCE_DIR="evidence/shadow_${LABEL}"
[[ -d "$EVIDENCE_DIR" ]] || { echo "[abort] no such window: $EVIDENCE_DIR" >&2; exit 2; }

scripts/snapshot.sh "${EVIDENCE_DIR}/abort_$(date -u +'%Y%m%dT%H%M%SZ').json"
echo "{\"aborted_ts\": $(date -u +%s)}" > "${EVIDENCE_DIR}/aborted.json"
echo "[abort] window ${LABEL} aborted. Final snapshot captured."
