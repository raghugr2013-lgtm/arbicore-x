#!/usr/bin/env bash
# 99_rollback.sh — restore the OLD backend. Mongo is never touched -> data intact.
# This is the SAFE rollback: it relies on the fact that 06_cutover.sh only stopped (never
# removed) the OLD container, so we just start it again and tear down the NEW.
#
# It does NOT restore from the mongodump archive — that would be destructive and is only
# needed if Mongo itself is corrupted (manual procedure documented in §8 of the readiness
# report). The realignment is schema-additive: the OLD build simply ignores the new seed
# docs in arbicore_scanner_config/arbicore_scanner_state, so functional rollback is enough.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
load_env
need_cmd docker
need_cmd curl

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  die "docker compose not installed"
fi

log "Stopping NEW backend ($BACKEND_NEW) via compose down ..."
( cd "$ROOT_DIR" && $DC --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" down ) || true
ok "NEW backend stopped"

log "Confirming OLD backend exists ($BACKEND_OLD) ..."
docker inspect "$BACKEND_OLD" >/dev/null 2>&1 \
  || die "OLD container '$BACKEND_OLD' not found — cannot auto-rollback. See readiness report §8 for manual restore."

log "Starting OLD backend ($BACKEND_OLD) ..."
docker start "$BACKEND_OLD" >/dev/null
ok "OLD backend started"

log "Waiting up to 60s for OLD /api/ to return 200 ..."
ATTEMPTS=0
until [ "$ATTEMPTS" -ge 30 ]; do
  CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/api/ || true)"
  [ "$CODE" = "200" ] && break
  ATTEMPTS=$((ATTEMPTS+1))
  sleep 2
done
[ "$CODE" = "200" ] || c_red "  WARN  OLD /api/ never returned 200 (last=$CODE) — inspect 'docker logs $BACKEND_OLD'"
[ "$CODE" = "200" ] && ok "OLD /api/ -> 200"

cat <<'NOTE'

[rollback] Functional rollback complete.
  - Mongo was never touched -> all 320 opportunities + history are intact.
  - The new build's seeded arbicore_scanner_config / arbicore_scanner_state docs are
    harmless to the OLD build (it ignores them).
  - If you need an "exact pre-state" reset of those seed docs, do so manually using the
    procedure in /audit/13_production_readiness_report.md §8 — NOT included here so no
    destructive command can ever be executed by accident.
NOTE
c_green "ROLLBACK DONE — production is on the OLD backend again."
