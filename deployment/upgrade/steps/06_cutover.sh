#!/usr/bin/env bash
# 06_cutover.sh — the only downtime window (seconds). Mongo is NEVER touched.
# Sequence:
#   1. snapshot OLD container state (for rollback)
#   2. docker stop OLD backend (preserved, NOT removed, so rollback = docker start)
#   3. docker compose up -d the NEW backend (attaches to existing Mongo network)
#   4. wait for /api/ health on the NEW backend
#   5. confirm /api/arbicore/* endpoints are now present
# On any failure: auto-rollback (start OLD, stop NEW) and exit non-zero.
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

auto_rollback() {
  c_red "[cutover] FAILURE — initiating auto-rollback ..."
  ( cd "$ROOT_DIR" && $DC --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" down ) || true
  docker start "$BACKEND_OLD" >/dev/null 2>&1 || c_red "  could not restart OLD ($BACKEND_OLD) — manual intervention required"
  sleep 6
  curl -s -o /dev/null -w "  OLD /api/ -> HTTP %{http_code}\n" http://127.0.0.1:8001/api/ || true
  die "auto-rollback complete; production is on OLD again. Investigate before re-attempting cutover."
}
trap 'auto_rollback' ERR

# 1) Pre-cutover snapshot of the OLD container (for forensics)
TS="$(date -u +%Y%m%dT%H%M%SZ)"
SNAP="${LOG_DIR}/old_backend_state_${TS}.json"
mkdir -p "$LOG_DIR"
docker inspect "$BACKEND_OLD" > "$SNAP" 2>/dev/null || true
ok "snapshot of OLD: $SNAP"

# 2) Stop OLD (keep the container — never docker rm — so rollback is instantaneous)
log "Stopping OLD backend: $BACKEND_OLD ..."
docker stop "$BACKEND_OLD" >/dev/null
ok "OLD stopped (container preserved for rollback)"

# 3) Bring up NEW via compose
log "Starting NEW backend: $BACKEND_NEW (image $IMAGE_TAG, network $NETWORK_NAME) ..."
( cd "$ROOT_DIR" && $DC --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" up -d backend )

# 4) Wait for /api/ health (60s budget — same envelope as compose healthcheck)
log "Waiting for NEW /api/ to return 200 (up to 60s) ..."
ATTEMPTS=0
until [ "$ATTEMPTS" -ge 30 ]; do
  CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/api/ || true)"
  [ "$CODE" = "200" ] && break
  ATTEMPTS=$((ATTEMPTS+1))
  sleep 2
done
[ "$CODE" = "200" ] || { c_red "NEW /api/ never returned 200 (last=$CODE)"; false; }
ok "NEW /api/ -> 200"

# 5) Confirm the realigned API surface is actually present
log "Verifying /api/arbicore/* surface is restored ..."
if ! curl -fs http://127.0.0.1:8001/openapi.json | grep -q "/api/arbicore/scanners/cex_arb/config"; then
  c_red "openapi.json is missing /api/arbicore/scanners/cex_arb/config — wrong build?"
  false
fi
ok "/api/arbicore/* present in OpenAPI"

# 6) Tail the first interesting log lines for the operator
log "Recent NEW backend logs:"
docker logs --tail=60 "$BACKEND_NEW" 2>&1 | grep -E "ArbiCore|Application startup|Traceback|ERROR|seed_defaults|ensure_indexes" || true

trap - ERR
c_green "CUTOVER COMPLETE — NEW backend is serving. Run 09_canary_probe.sh next, then 10_validate.sh."
c_green "Rollback (if needed): steps/99_rollback.sh"
