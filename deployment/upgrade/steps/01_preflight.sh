#!/usr/bin/env bash
# 01_preflight.sh — verify the auto-detected environment is sane.
# Mongo reachable, network exists, audited backend source present, no name collision,
# old backend currently healthy on :8001. Read-only. Fails fast on any anomaly.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
load_env
need_cmd docker
need_cmd curl

log "Confirming detected old backend is still running ..."
docker inspect -f '{{.State.Running}}' "$BACKEND_OLD" 2>/dev/null | grep -q true \
  || die "old backend '$BACKEND_OLD' is not running — refusing to proceed"
ok "old backend running: $BACKEND_OLD"

log "Confirming detected Mongo is running ..."
docker inspect -f '{{.State.Running}}' "$MONGO_CONTAINER" 2>/dev/null | grep -q true \
  || die "mongo container '$MONGO_CONTAINER' is not running"
ok "mongo running: $MONGO_CONTAINER"

log "Confirming Docker network '$NETWORK_NAME' exists ..."
docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 \
  || die "docker network '$NETWORK_NAME' not found"
ok "network exists: $NETWORK_NAME"

log "Pinging Mongo from inside the network (admin.ping) ..."
PING_OUT="$(mongo_eval "$MONGO_CONTAINER" admin 'db.runCommand({ping:1}).ok' 2>&1)" \
  || die "mongo ping failed: $PING_OUT"
echo "$PING_OUT" | grep -q '1' || die "mongo ping returned non-1: $PING_OUT"
ok "mongo ping OK"

log "Confirming target DB '$DB_NAME' exists and is non-empty ..."
COLLS="$(mongo_eval "$MONGO_CONTAINER" "$DB_NAME" 'db.getCollectionNames().filter(function(c){return c.indexOf("arbicore_")==0;}).length')"
echo "$COLLS" | grep -Eq '^[0-9]+$' || die "could not list collections in $DB_NAME"
[ "$COLLS" -gt 0 ] || die "DB $DB_NAME has zero arbicore_* collections — wrong DB?"
ok "DB $DB_NAME has $COLLS arbicore_* collections"

log "Checking for backend name collision (new vs old) ..."
if [ "$BACKEND_NEW" = "$BACKEND_OLD" ]; then
  die "BACKEND_NEW == BACKEND_OLD ($BACKEND_NEW) — name collision; re-run 00_detect_env.sh"
fi
if docker ps -a --format '{{.Names}}' | grep -qx "$BACKEND_NEW"; then
  die "container named '$BACKEND_NEW' already exists — remove it or change BACKEND_NEW in deploy.env"
fi
ok "no name collision: new=$BACKEND_NEW  old=$BACKEND_OLD"

log "Probing the OLD backend on :8001 (sanity baseline) ..."
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/api/ || true)"
[ "$HTTP_CODE" = "200" ] || c_red "  WARN  old backend /api/ returned HTTP $HTTP_CODE (continuing — rollback still possible)"
[ "$HTTP_CODE" = "200" ] && ok "old backend /api/ -> 200"

log "Confirming audited backend source is staged at ./backend/ ..."
[ -f "${ROOT_DIR}/backend/server.py" ] || die "missing ${ROOT_DIR}/backend/server.py — copy the audited backend/ into the bundle"
[ -f "${ROOT_DIR}/backend/Dockerfile" ] || die "missing ${ROOT_DIR}/backend/Dockerfile (template ships in this bundle)"
[ -f "${ROOT_DIR}/backend/requirements.txt" ] || die "missing ${ROOT_DIR}/backend/requirements.txt"
[ -f "${ROOT_DIR}/backend/.env" ] || die "missing ${ROOT_DIR}/backend/.env — should have been baked by 00_detect_env.sh"
# arbicore module presence (audited build)
[ -d "${ROOT_DIR}/backend/arbicore" ] || c_red "  WARN  ${ROOT_DIR}/backend/arbicore not found — confirm you copied the FULL audited backend/"
# B1: labels.json is bind-mounted by compose/docker-compose.prod.yml L27.
# If missing, Docker silently creates an empty DIRECTORY at the mount target,
# breaking the audited launch-arb subsystem. Hard-fail here, not at cutover.
LABELS="${ROOT_DIR}/backend/arbicore/intel/launch/labels.json"
[ -f "$LABELS" ] || die "missing $LABELS — required by compose bind mount; copy the FULL audited backend/"
ok "backend source staged (incl. arbicore/intel/launch/labels.json)"

log "Confirming compose env was generated ..."
[ -f "$COMPOSE_ENV" ] || die "missing $COMPOSE_ENV — run 00_detect_env.sh"
[ -f "$COMPOSE_FILE" ] || die "missing $COMPOSE_FILE — this bundle is incomplete"
ok "compose files present"

log "Backup target directory ..."
mkdir -p "$BACKUP_DIR" "$LOG_DIR"
ok "backup dir: $BACKUP_DIR    log dir: $LOG_DIR"

c_green "PREFLIGHT GREEN — safe to run 02_backup.sh"
