#!/usr/bin/env bash
# install.sh — greenfield ArbiCore X installer.
# Guarded, idempotent, resumable. Refuses to run if an existing ArbiCore X stack is detected.
#
# What it does (in order):
#   1) Preflight  — Docker present, disk >= 40 GB, ports 80/443 free, .env valid.
#   2) Refuse-if-exists  — aborts if arbicore-x-mongo container OR mongo-data volume exists.
#   3) Bring up mongo  — waits healthy.
#   4) Bring up backend  — waits healthy.
#   5) Bring up frontend + opportunity_center  — waits healthy.
#   6) Bring up nginx on :80 (HTTP only, ACME challenge path served).
#   7) Issue Let's Encrypt cert (staging first unless LETSENCRYPT_MODE=prod).
#   8) Reload nginx to activate :443.
#   9) Run healthcheck.
#
# Non-destructive. If any step fails, the stack is left in place for inspection.
# Never touches Mongo data. No hard-coded domain.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

# --- helpers ---
c_blue(){ printf "\033[34m%s\033[0m\n" "$*"; }
c_green(){ printf "\033[32m%s\033[0m\n" "$*"; }
c_red(){ printf "\033[31m%s\033[0m\n" "$*" >&2; }
log(){  c_blue "[$(date +%H:%M:%S)] $*"; }
ok(){   c_green "  OK    $*"; }
die(){  c_red   "  FAIL  $*"; c_red "INSTALL ABORTED."; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }

# --- 1) preflight ---
log "1/9 preflight ..."
need docker
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  die "docker compose (v2 or v1) not installed"
fi
ok "docker CLI + compose available"

FREE_GB=$(df -BG --output=avail "$REPO_ROOT" | tail -1 | tr -dc '0-9')
[ "${FREE_GB:-0}" -ge 40 ] || die "insufficient disk (need >=40 GB, have ${FREE_GB} GB)"
ok "disk space: ${FREE_GB} GB free"

for p in 80 443; do
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":$p\$"; then
    die "port $p already in use — free it or stop the conflicting service"
  fi
done
ok "ports 80 + 443 are free"

[ -f "$ENV_FILE" ] || die "$ENV_FILE not found — copy .env.example or .env.production.example first"
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

: "${DOMAIN:?DOMAIN missing in .env}"
: "${LETSENCRYPT_EMAIL:?LETSENCRYPT_EMAIL missing in .env}"
: "${JWT_SECRET:?JWT_SECRET missing in .env}"
: "${VAULT_KEY:?VAULT_KEY missing in .env}"
[ "${#JWT_SECRET}" -ge 32 ]   || die "JWT_SECRET must be >= 32 chars"
[ "${#VAULT_KEY}"  -ge 32 ]   || die "VAULT_KEY must be >= 32 chars"
ok ".env validated (DOMAIN=${DOMAIN}, cert mode=${LETSENCRYPT_MODE:-staging})"

# --- 2) refuse-if-exists ---
log "2/9 refuse-if-exists guard ..."
if docker ps -a --format '{{.Names}}' | grep -qx arbicore-x-mongo; then
  die "arbicore-x-mongo container exists — this is not a greenfield install.
    Use scripts/upgrade.sh (delegates to deployment/upgrade/) for backend upgrades instead."
fi
if docker volume ls --format '{{.Name}}' | grep -qx arbicore-x-mongo-data; then
  die "arbicore-x-mongo-data volume exists — refusing to install on top of it.
    If this is intentional, remove the volume manually first (destroys data!)."
fi
ok "no prior stack found — safe to greenfield install"

# --- 3) mongo ---
log "3/9 starting mongo ..."
export GITSHA="${GITSHA:-$(cat "${REPO_ROOT}/.GITSHA_SHORT" 2>/dev/null || echo unknown)}"
cd "${REPO_ROOT}/deployment/compose"
$DC up -d mongo
for i in $(seq 1 30); do
  st=$(docker inspect -f '{{.State.Health.Status}}' arbicore-x-mongo 2>/dev/null || echo starting)
  [ "$st" = "healthy" ] && break
  sleep 2
done
[ "$st" = "healthy" ] || die "mongo not healthy after 60s"
ok "mongo healthy"

# --- 4) backend ---
log "4/9 building + starting backend ..."
# v1.0.1+: the backend Dockerfile now COPYs requirements.prod.txt directly from
# deployment/docker/backend/. No runtime swap of app/backend/requirements.txt
# is needed. Build context is the repo root.
$DC build backend
$DC up -d backend
for i in $(seq 1 30); do
  st=$(docker inspect -f '{{.State.Health.Status}}' arbicore-x-backend 2>/dev/null || echo starting)
  [ "$st" = "healthy" ] && break
  sleep 3
done
[ "$st" = "healthy" ] || die "backend not healthy after 90s — check: $DC logs backend"
ok "backend healthy"

# --- 5) frontends ---
log "5/9 building + starting frontends ..."
$DC build frontend opportunity_center
$DC up -d frontend opportunity_center
for svc in frontend opportunity_center; do
  cid="arbicore-x-${svc//_/-}"
  for i in $(seq 1 30); do
    st=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)
    [ "$st" = "healthy" ] && break
    sleep 2
  done
  [ "$st" = "healthy" ] || die "${svc} not healthy after 60s"
  ok "${svc} healthy"
done

# --- 6) nginx (HTTP only for ACME) ---
log "6/9 starting nginx (HTTP only, awaiting cert) ..."
$DC up -d nginx || {
  c_red "nginx failed to boot (expected on first run — certs not issued yet)."
  c_red "Bootstrap-http will be handled by init-letsencrypt.sh next."
}
ok "nginx container present (may be restarting until certs exist)"

# --- 7) cert issuance ---
log "7/9 requesting Let's Encrypt cert (MODE=${LETSENCRYPT_MODE:-staging}) ..."
"${REPO_ROOT}/deployment/ssl/init-letsencrypt.sh"
ok "cert issued"

# --- 8) nginx reload ---
log "8/9 reloading nginx to activate TLS ..."
$DC restart nginx
sleep 3
$DC exec -T nginx nginx -t
ok "nginx reloaded; TLS active"

# --- 9) healthcheck ---
log "9/9 running healthcheck ..."
"${REPO_ROOT}/scripts/healthcheck.sh" || {
  c_red "healthcheck reported issues — inspect logs. Stack is left running for diagnosis."
  exit 2
}

c_green ""
c_green "  ================================================================="
c_green "  ArbiCore X — INSTALL COMPLETE."
c_green "  URL:            https://${DOMAIN}"
c_green "  Opportunity C.: https://${DOMAIN}/opportunity-center/"
c_green "  API health:     https://${DOMAIN}/api/"
c_green "  Cert mode:      ${LETSENCRYPT_MODE:-staging}"
c_green "  Version:        $(cat "${REPO_ROOT}/VERSION")"
c_green "  ================================================================="
c_green ""
c_green "  Next steps:"
c_green "    1. Verify all pages load in a browser."
c_green "    2. If cert mode was 'staging', re-run with LETSENCRYPT_MODE=prod in .env."
c_green "    3. Add renew cron:  cat deployment/ssl/cronjob.example >> /etc/crontab"
c_green "    4. Add backup cron: 0 3 * * * ${REPO_ROOT}/deployment/backups/backup-cron.sh"
c_green ""
