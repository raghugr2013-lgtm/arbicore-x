#!/usr/bin/env bash
# 11_snapshot.sh — point-in-time counts + scanner state snapshot. READ-ONLY.
# Idempotent. Safe to run repeatedly post-cutover for observability.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
load_env
need_cmd docker

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${1:-${LOG_DIR}/snapshot_${TS}.txt}"
mkdir -p "$(dirname "$OUT")"

JS='
print("=== ArbiCore X snapshot " + new Date().toISOString() + " ===");
db.getCollectionNames().filter(function(c){return c.indexOf("arbicore_")==0;}).sort().forEach(function(c){
  print(c + "\t" + db.getCollection(c).count());
});
print("--- scanner_state ---");
db.arbicore_scanner_state.find({}, {_id:1, enabled:1}).forEach(function(d){
  print("  " + d._id + " enabled=" + d.enabled);
});
'
mongo_eval "$MONGO_CONTAINER" "$DB_NAME" "$JS" | tee "$OUT"
ok "snapshot -> $OUT"
