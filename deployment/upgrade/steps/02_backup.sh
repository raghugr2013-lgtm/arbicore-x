#!/usr/bin/env bash
# 02_backup.sh — mandatory pre-cutover backup. NON-DESTRUCTIVE.
# Produces: gzipped mongodump archive + pre-cutover collection counts + OpenAPI snapshot.
# Aborts on a suspiciously small archive (rollback would be unsafe without it).
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
load_env
need_cmd docker
need_cmd curl

TS="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="${BACKUP_DIR}/preupgrade_${DB_NAME}_${TS}.archive.gz"
COUNTS="${BACKUP_DIR}/counts_pre_${TS}.tsv"
OPENAPI="${BACKUP_DIR}/openapi_pre_${TS}.json"
mkdir -p "$BACKUP_DIR"

log "mongodump $DB_NAME from $MONGO_CONTAINER -> $ARCHIVE ..."
# stream archive out of the container to host (avoids 'docker cp' double-copy)
docker exec "$MONGO_CONTAINER" sh -c \
  "mongodump --db='$DB_NAME' --archive --gzip" > "$ARCHIVE"

SIZE="$(stat -c%s "$ARCHIVE" 2>/dev/null || stat -f%z "$ARCHIVE")"
log "archive size = ${SIZE} bytes"
[ "${SIZE:-0}" -gt 100000 ] || die "archive suspiciously small (${SIZE}B) — refusing to continue"
ok "archive written: $ARCHIVE"

log "Recording pre-cutover arbicore_* counts -> $COUNTS ..."
# build a tiny JS that prints "<coll>\t<count>"; works with both mongo and mongosh
JS='var L=db.getCollectionNames().filter(function(c){return c.indexOf("arbicore_")==0;}).sort();L.forEach(function(c){print(c+"\t"+db.getCollection(c).count());});'
mongo_eval "$MONGO_CONTAINER" "$DB_NAME" "$JS" > "$COUNTS" 2>/dev/null \
  || die "failed to capture pre-cutover counts"
ok "wrote $(grep -c . "$COUNTS") collection counts"

log "Snapshotting current OpenAPI spec -> $OPENAPI ..."
if curl -fs -o "$OPENAPI" http://127.0.0.1:8001/openapi.json; then
  ok "OpenAPI captured ($(stat -c%s "$OPENAPI" 2>/dev/null || stat -f%z "$OPENAPI") bytes)"
else
  c_red "  WARN  could not capture OpenAPI from old backend (continuing)"
fi

# Persist the backup pointer for the rollback step
cat > "${ROOT_DIR}/.last_backup" <<EOF
ARCHIVE=${ARCHIVE}
COUNTS=${COUNTS}
OPENAPI=${OPENAPI}
TS=${TS}
EOF
ok "rollback anchor recorded: ${ROOT_DIR}/.last_backup"

c_green "BACKUP COMPLETE — keep ${ARCHIVE} as the rollback anchor."
