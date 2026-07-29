#!/usr/bin/env bash
# ArbiCore X — Health-check
# Reads-only probe of all critical surfaces. Exits 0 when GREEN, non-zero when RED.
set -uo pipefail
cd "$(dirname "$0")/.."

PASS=0
FAIL=0
note() { printf "[health] %s\n" "$*"; }
ok()   { note "OK    : $*"; PASS=$((PASS+1)); }
ng()   { note "FAIL  : $*"; FAIL=$((FAIL+1)); }

# 1. Mongo container
if [[ "$(docker inspect --format='{{.State.Health.Status}}' arbicore-x-mongo 2>/dev/null)" == "healthy" ]]; then
  ok "mongo container healthy"
else
  ng "mongo container not healthy"
fi

# 2. Backend container
if [[ "$(docker inspect --format='{{.State.Health.Status}}' arbicore-x-backend 2>/dev/null)" == "healthy" ]]; then
  ok "backend container healthy"
else
  ng "backend container not healthy"
fi

# 3. Backend liveness
if curl -fs http://localhost:8001/api/ >/dev/null; then
  ok "backend /api/ liveness 200"
else
  ng "backend /api/ liveness failed"
fi

# 4. Mongo arbicore_* collection census
# Try mongosh first (mongo:5+/6+/7+); fall back to legacy mongo shell (mongo:4.4).
COUNT=$(docker exec arbicore-x-mongo sh -c "
  mongosh --quiet --eval \"db.getSiblingDB(process.env.DB_NAME || 'arbicore_x_prod').getCollectionNames().filter(n=>n.startsWith('arbicore_')).length\" 2>/dev/null \
  || mongo --quiet --eval \"db.getSiblingDB('arbicore_x_prod').getCollectionNames().filter(function(n){return n.indexOf('arbicore_')===0;}).length\"
" 2>/dev/null | tail -1 || echo 0)
if [[ "$COUNT" -ge 1 ]]; then
  ok "mongo arbicore_* collections present: $COUNT"
else
  ng "mongo arbicore_* collections missing (will auto-create on first scanner tick)"
fi

# 5. Curated wallet seed
SEED_BYTES=$(wc -c < backend/arbicore/intel/launch/labels.json 2>/dev/null || echo 0)
if [[ "$SEED_BYTES" -gt 100 ]]; then
  ok "curated labels.json present (${SEED_BYTES} bytes)"
else
  ng "curated labels.json missing or empty"
fi

note "summary: ${PASS} OK / ${FAIL} FAIL"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
