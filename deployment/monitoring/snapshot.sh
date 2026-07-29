#!/usr/bin/env bash
# ArbiCore X — point-in-time snapshot
# Captures Mongo collection counts + scanner-state + recent outcomes into a JSON file.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-evidence/snapshot_$(date -u +'%Y%m%dT%H%M%SZ').json}"
mkdir -p "$(dirname "$OUT")"

DB="${DB_NAME:-arbicore_x_prod}"

# mongosh (mongo:5+/6+/7+) with legacy `mongo` shell fallback for mongo:4.4
SHELL_CMD="mongosh --quiet"
if ! docker exec arbicore-x-mongo sh -c "command -v mongosh >/dev/null"; then
  SHELL_CMD="mongo --quiet"
fi

docker exec arbicore-x-mongo $SHELL_CMD --eval "
  var db_handle = db.getSiblingDB('${DB}');
  var cols = db_handle.getCollectionNames().filter(function(n){return n.indexOf('arbicore_')===0;}).sort();
  var counts = {};
  cols.forEach(function(c){ counts[c] = db_handle.getCollection(c).countDocuments(); });
  var scanner_state = db_handle.arbicore_scanner_state.find({}, {scanner_id:1, enabled:1, last_tick_ts:1, _id:0}).toArray();
  var recent_outcomes = db_handle.arbicore_outcomes.find({}, {_id:0, scanner_id:1, decision:1, timestamp:1}).sort({timestamp:-1}).limit(10).toArray();
  printjson({
    captured_at: new Date().toISOString(),
    collections: counts,
    scanner_state: scanner_state,
    recent_outcomes: recent_outcomes
  });
" > "$OUT"

echo "[snapshot] captured to $OUT"
