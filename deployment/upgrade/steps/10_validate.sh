#!/usr/bin/env bash
# 10_validate.sh — post-cutover acceptance checks. READ-ONLY.
# Runs the Mongo-side validation JS + an HTTP healthcheck. Exits 0 = GREEN.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
load_env
need_cmd docker
need_cmd curl

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${LOG_DIR}/validate_${TS}.log"
mkdir -p "$LOG_DIR"
RED=0

log "Mongo-side acceptance checks ..."
JS_FILE="${ROOT_DIR}/mongo/04_validate.js"
SHELL_BIN="$(mongo_shell "$MONGO_CONTAINER")"
docker exec -i "$MONGO_CONTAINER" "$SHELL_BIN" --quiet "$DB_NAME" < "$JS_FILE" | tee "$OUT"
grep -q "FAIL" "$OUT" && { c_red "  one or more Mongo checks FAILED — see $OUT"; RED=1; } || ok "Mongo checks PASS"

log "HTTP healthcheck (liveness + arbicore API surface) ..."
{
  echo "=== backend liveness ==="
  curl -fs http://127.0.0.1:8001/api/ >/dev/null && echo "  /api/ -> 200 OK" || { echo "  /api/ FAIL"; RED=1; }
  echo "=== arbicore API restored ==="
  if curl -fs http://127.0.0.1:8001/openapi.json | grep -q "/api/arbicore/scanners/cex_arb/config"; then
    echo "  /api/arbicore/* present OK"
  else
    echo "  /api/arbicore/* MISSING"; RED=1
  fi
  if [ -n "${ARBICORE_TOKEN:-}" ]; then
    echo "=== arbicore health (authed) ==="
    curl -fs -H "Authorization: Bearer $ARBICORE_TOKEN" http://127.0.0.1:8001/api/arbicore/health >/dev/null \
      && echo "  /api/arbicore/health OK" || { echo "  /api/arbicore/health FAIL"; RED=1; }
  else
    echo "  (set ARBICORE_TOKEN=<bearer> to also exercise authed /api/arbicore/health)"
  fi
  echo "=== mongo census ==="
  mongo_eval "$MONGO_CONTAINER" "$DB_NAME" '
    print("  scanner_config="+db.arbicore_scanner_config.count()
       +" scanner_state="+db.arbicore_scanner_state.count()
       +" opportunities="+db.arbicore_opportunities.count());' 2>/dev/null || echo "  mongo census FAIL"
} | tee -a "$OUT"

# Compare counts vs the pre-cutover baseline if available
if [ -f "${ROOT_DIR}/.last_backup" ]; then
  # shellcheck disable=SC1090
  source "${ROOT_DIR}/.last_backup"
  if [ -f "$COUNTS" ]; then
    echo "" | tee -a "$OUT"
    echo "=== count delta vs pre-cutover ($COUNTS) ===" | tee -a "$OUT"
    JS='var L=db.getCollectionNames().filter(function(c){return c.indexOf("arbicore_")==0;}).sort();L.forEach(function(c){print(c+"\t"+db.getCollection(c).count());});'
    POST="${LOG_DIR}/counts_post_${TS}.tsv"
    mongo_eval "$MONGO_CONTAINER" "$DB_NAME" "$JS" > "$POST" 2>/dev/null
    join -t $'\t' -a1 -a2 -e "MISSING" -o 0,1.2,2.2 \
      <(sort "$COUNTS") <(sort "$POST") \
      | awk -F'\t' 'BEGIN{print "collection\tpre\tpost\tdelta"} {d=($3=="MISSING"||$2=="MISSING")?"?":$3-$2; print $1"\t"$2"\t"$3"\t"d}' \
      | tee -a "$OUT"
  fi
fi

if [ "$RED" -eq 0 ]; then
  c_green "VALIDATION GREEN — log: $OUT"
else
  c_red   "VALIDATION RED — see $OUT. Consider 99_rollback.sh."
fi
exit "$RED"
