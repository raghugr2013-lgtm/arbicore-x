#!/usr/bin/env bash
# 04_precutover_cleanup.sh — OPTIONAL controlled trim of EXPIRED discovery candidates.
# REQUIRES the explicit --confirm flag. Deletes ONLY rows where expires_at < now in
# arbicore_discovery_candidates (a transient queue). Durable collections are never touched.
#
# Usage: steps/04_precutover_cleanup.sh --confirm
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
load_env
need_cmd docker

CONFIRM="${1:-}"
if [ "$CONFIRM" != "--confirm" ]; then
  c_red "REFUSING TO RUN: this step deletes rows. Re-run with --confirm if intended."
  cat <<'EXPLAIN'

What this step does (only with --confirm):
  - Targets ONE collection: arbicore_discovery_candidates
  - Deletes ONLY rows whose expires_at (float epoch) is in the past
  - Bounded batches (50k rows) with 2s pauses to smooth Mongo IO
  - Idempotent / resumable
  - NEVER touches arbicore_opportunities / arbicore_outcomes / arbicore_audit_log /
    arbicore_scanner_state / arbicore_scanner_config (durable data)

Why it's optional now:
  - The realignment itself does NOT require it. The new build will run with the existing
    ~2.9M backlog in place. Trimming is a clean-up to reduce IO load only.
EXPLAIN
  exit 2
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${LOG_DIR}/precutover_cleanup_${TS}.log"
mkdir -p "$LOG_DIR"

JS_FILE="${ROOT_DIR}/mongo/02_precutover_cleanup.js"
[ -f "$JS_FILE" ] || die "missing $JS_FILE"

log "Running CONFIRMED controlled cleanup (target: arbicore_discovery_candidates only) ..."
SHELL_BIN="$(mongo_shell "$MONGO_CONTAINER")"
docker exec -i "$MONGO_CONTAINER" "$SHELL_BIN" --quiet "$DB_NAME" < "$JS_FILE" \
  | tee "$OUT"

ok "cleanup log: $OUT"
c_green "CLEANUP COMPLETE — durable data untouched. Proceed to 05_build.sh."
