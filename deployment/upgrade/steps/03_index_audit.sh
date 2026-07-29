#!/usr/bin/env bash
# 03_index_audit.sh — READ-ONLY. Reports existing indexes on arbicore_* collections so
# the operator can spot IndexOptionsConflict risks before cutover. Does NOT modify anything.
# Output is teed to the log dir for the audit trail.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
load_env
need_cmd docker

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${LOG_DIR}/index_audit_${TS}.log"
mkdir -p "$LOG_DIR"

JS_FILE="${ROOT_DIR}/mongo/01_index_audit.js"
[ -f "$JS_FILE" ] || die "missing $JS_FILE"

log "Running read-only index audit (target DB: $DB_NAME) ..."
SHELL_BIN="$(mongo_shell "$MONGO_CONTAINER")"
# Pipe the JS into the in-container shell. No file mount needed.
docker exec -i "$MONGO_CONTAINER" "$SHELL_BIN" --quiet "$DB_NAME" < "$JS_FILE" \
  | tee "$OUT"

if grep -q "REVIEW" "$OUT"; then
  c_red "  WARN  Unexpected index names detected — review the lines above marked REVIEW."
  c_red "        If any conflicts with an EXPECTED name but a different spec, drop that single index"
  c_red "        (db.<coll>.dropIndex(\"<name>\")) and the new boot will rebuild it correctly."
else
  ok "no unexpected index names found"
fi

ok "audit log: $OUT"
c_green "INDEX AUDIT COMPLETE — review $OUT, then proceed to 05_build.sh."
c_green "(04_precutover_cleanup.sh is OPTIONAL — only run with --confirm if trimming the expired discovery backlog.)"
c_green "Post-cutover sequence is: 06_cutover -> 09_canary_probe -> 10_validate -> 11_snapshot."
