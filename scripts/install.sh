#!/usr/bin/env bash
# =============================================================================
# install.sh — ArbiCore X profile-aware installer (v2.9.2+).
#
# Reads ARBICORE_DEPLOY_PROFILE from .env (or --profile flag) and dispatches
# to the correct compose file. Two supported profiles:
#
#   greenfield  — ArbiCore X owns Mongo, network, nginx, TLS.
#                 Fresh Ubuntu VPS scenario. Uses deployment/compose/docker-compose.yml.
#                 Consumes repo-root .env only.
#
#   shared      — ArbiCore X is a co-tenant of an existing peer stack that
#                 owns Mongo (e.g. "factory-mongo") and the reverse proxy.
#                 Uses deployment/compose/docker-compose.shared.yml.
#                 Consumes repo-root .env AND deployment/compose/.env.shared.
#
# Fingerprint-based consistency check refuses to run the greenfield profile
# when the .env carries a shared-topology MONGO_URL — this is the exact
# failure mode that produced "getaddrinfo ENOTFOUND factory-mongo" in v2.9.1.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
c_blue(){  printf "\033[34m%s\033[0m\n" "$*"; }
c_green(){ printf "\033[32m%s\033[0m\n" "$*"; }
c_yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
c_red(){   printf "\033[31m%s\033[0m\n" "$*" >&2; }
log(){  c_blue "[$(date +%H:%M:%S)] $*"; }
ok(){   c_green "  OK    $*"; }
warn(){ c_yellow "  WARN  $*"; }
die(){  c_red   "  FAIL  $*"; c_red "INSTALL ABORTED."; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }

# ---------------------------------------------------------------------------
# CLI flag parsing (--profile greenfield|shared)
# ---------------------------------------------------------------------------
PROFILE_FLAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE_FLAG="$2"; shift 2 ;;
    --profile=*) PROFILE_FLAG="${1#*=}"; shift ;;
    -h|--help)
      cat <<'EOF'
usage: install.sh [--profile greenfield|shared]

Profile selection (highest precedence first):
  1) --profile CLI flag
  2) ARBICORE_DEPLOY_PROFILE in .env
  3) default: greenfield

Shared profile also requires deployment/compose/.env.shared to be present
(copy from deployment/compose/.env.shared.example).
EOF
      exit 0 ;;
    *) die "unknown argument: $1 (see --help)" ;;
  esac
done

# ---------------------------------------------------------------------------
# 1) preflight
# ---------------------------------------------------------------------------
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

[ -f "$ENV_FILE" ] || die "$ENV_FILE not found — copy .env.example or .env.production.example first"
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

# ---------------------------------------------------------------------------
# 1b) profile selection + consistency guard (v2.9.2)
# ---------------------------------------------------------------------------
PROFILE="${PROFILE_FLAG:-${ARBICORE_DEPLOY_PROFILE:-greenfield}}"
case "$PROFILE" in
  greenfield|shared) : ;;
  *) die "invalid profile '$PROFILE' — must be 'greenfield' or 'shared'" ;;
esac

# Fingerprint-based consistency check. If .env's MONGO_URL points at a host
# that is NOT the greenfield in-network name 'mongo', the operator is on the
# shared profile — refuse to run greenfield to avoid the v2.9.1 misdeploy.
MONGO_HOST_IN_URL="$(printf '%s' "${MONGO_URL:-}" | \
  sed -nE 's|^mongodb(\+srv)?://([^@]*@)?([^:/,?]+).*|\3|p')"
if [ "$PROFILE" = "greenfield" ] && [ -n "$MONGO_HOST_IN_URL" ] \
    && [ "$MONGO_HOST_IN_URL" != "mongo" ] \
    && [ "$MONGO_HOST_IN_URL" != "localhost" ] \
    && [ "$MONGO_HOST_IN_URL" != "127.0.0.1" ]; then
  die "profile mismatch:
    --profile greenfield was selected, but .env's MONGO_URL points at
    host '$MONGO_HOST_IN_URL' (not the greenfield-internal 'mongo' host).

    Your .env is configured for the SHARED profile. Re-run as:
        ./scripts/install.sh --profile shared
    or set:
        ARBICORE_DEPLOY_PROFILE=shared
    in your .env, then re-run.

    See docs/DEPLOYMENT_CHECKLIST.md § 'Choose your profile'."
fi

if [ "$PROFILE" = "shared" ]; then
  SHARED_ENV_FILE="${REPO_ROOT}/deployment/compose/.env.shared"
  [ -f "$SHARED_ENV_FILE" ] || die "shared profile selected but $SHARED_ENV_FILE not found.
    Copy deployment/compose/.env.shared.example to that path and edit it first."
  # shellcheck disable=SC1090
  set -a; source "$SHARED_ENV_FILE"; set +a
  COMPOSE_FILE="${REPO_ROOT}/deployment/compose/docker-compose.shared.yml"
  COMPOSE_ENV_FILE="$SHARED_ENV_FILE"
else
  COMPOSE_FILE="${REPO_ROOT}/deployment/compose/docker-compose.yml"
  COMPOSE_ENV_FILE=""   # greenfield uses only interpolation from environment
fi
ok "profile: $PROFILE  ($(basename "$COMPOSE_FILE"))"

# Common REQUIRED variables (both profiles).
: "${JWT_SECRET:?JWT_SECRET missing in .env}"
: "${VAULT_KEY:?VAULT_KEY missing in .env}"
: "${REACT_APP_BACKEND_URL:?REACT_APP_BACKEND_URL missing in .env (required: CRA bakes it into the JS bundle at build time; empty value produces a black-screen operator UI)}"
[ "${#JWT_SECRET}" -ge 32 ] || die "JWT_SECRET must be >= 32 chars"
[ "${#VAULT_KEY}"  -ge 32 ] || die "VAULT_KEY must be >= 32 chars"

# Profile-specific REQUIRED variables.
if [ "$PROFILE" = "greenfield" ]; then
  : "${DOMAIN:?DOMAIN missing in .env}"
  : "${LETSENCRYPT_EMAIL:?LETSENCRYPT_EMAIL missing in .env}"
  # Ports 80/443 must be free (nginx + certbot bind them).
  for p in 80 443; do
    if ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":$p\$"; then
      die "port $p already in use — free it or stop the conflicting service"
    fi
  done
  ok "ports 80 + 443 are free"
  ok ".env validated (profile=greenfield, DOMAIN=${DOMAIN}, cert mode=${LETSENCRYPT_MODE:-staging})"
else
  # Shared profile REQUIREDs come from .env.shared.
  : "${NETWORK_NAME:?NETWORK_NAME missing in .env.shared}"
  : "${MONGO_HOST:?MONGO_HOST missing in .env.shared}"
  : "${MONGO_URL:?MONGO_URL missing in .env (must include credentials if peer Mongo has auth)}"
  : "${DB_NAME:?DB_NAME missing in .env.shared}"
  # Peer network must already exist.
  if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    die "shared network '$NETWORK_NAME' does not exist.
    Ask the peer-stack owner to create it, or:
        docker network create --driver bridge $NETWORK_NAME"
  fi
  ok "shared network '$NETWORK_NAME' present"
  # Peer Mongo must be reachable at MONGO_HOST on the shared network.
  if ! docker ps --format '{{.Names}}' | grep -qx "$MONGO_HOST"; then
    warn "container '$MONGO_HOST' not visible via 'docker ps' — check the peer stack is up."
  else
    ok "peer Mongo container '$MONGO_HOST' present"
  fi
  ok ".env validated (profile=shared, MONGO_HOST=${MONGO_HOST}, DB_NAME=${DB_NAME})"
fi

# ---------------------------------------------------------------------------
# 2) refuse-if-exists (profile-aware)
# ---------------------------------------------------------------------------
log "2/9 refuse-if-exists guard ..."
if [ "$PROFILE" = "greenfield" ]; then
  if docker ps -a --format '{{.Names}}' | grep -qx arbicore-x-mongo; then
    die "arbicore-x-mongo container exists — this is not a greenfield install.
    Use scripts/upgrade.sh (deployment/upgrade/) for backend upgrades instead."
  fi
  if docker volume ls --format '{{.Name}}' | grep -qx arbicore-x-mongo-data; then
    die "arbicore-x-mongo-data volume exists — refusing to install on top of it.
    If intentional, remove the volume manually first (destroys data!)."
  fi
  ok "no prior stack found — safe to greenfield install"
else
  # Shared: NEVER touch peer Mongo. Only guard against duplicate arbicore-x-* containers.
  for c in "${BACKEND_CONTAINER_NAME:-arbicore-x-backend}" \
           "${FRONTEND_CONTAINER_NAME:-arbicore-x-frontend}" \
           "${OPPORTUNITY_CENTER_CONTAINER_NAME:-arbicore-x-opportunity-center}"; do
    if docker ps -a --format '{{.Names}}' | grep -qx "$c"; then
      die "container '$c' already exists — remove it or prefix container names in .env.shared"
    fi
  done
  ok "no prior ArbiCore X containers on this host — safe to install"
fi

# Compose command helper (with --env-file for shared).
compose(){
  if [ -n "$COMPOSE_ENV_FILE" ]; then
    (cd "$(dirname "$COMPOSE_FILE")" && \
      $DC --env-file "$COMPOSE_ENV_FILE" -f "$COMPOSE_FILE" "$@")
  else
    (cd "$(dirname "$COMPOSE_FILE")" && $DC -f "$COMPOSE_FILE" "$@")
  fi
}

export GITSHA="${GITSHA:-$(cat "${REPO_ROOT}/.GITSHA_SHORT" 2>/dev/null || echo unknown)}"

# ---------------------------------------------------------------------------
# 3) mongo (greenfield only — shared profile connects to peer Mongo)
# ---------------------------------------------------------------------------
if [ "$PROFILE" = "greenfield" ]; then
  log "3/9 starting mongo ..."
  compose up -d mongo
  for i in $(seq 1 30); do
    st=$(docker inspect -f '{{.State.Health.Status}}' arbicore-x-mongo 2>/dev/null || echo starting)
    [ "$st" = "healthy" ] && break
    sleep 2
  done
  [ "$st" = "healthy" ] || die "mongo not healthy after 60s"
  ok "mongo healthy"
else
  log "3/9 mongo — using peer '$MONGO_HOST' (no-op in shared profile)"
fi

# ---------------------------------------------------------------------------
# 4) backend
# ---------------------------------------------------------------------------
log "4/9 building + starting backend ..."
compose build backend
compose up -d backend
BACKEND_CID="${BACKEND_CONTAINER_NAME:-arbicore-x-backend}"
for i in $(seq 1 30); do
  st=$(docker inspect -f '{{.State.Health.Status}}' "$BACKEND_CID" 2>/dev/null || echo starting)
  [ "$st" = "healthy" ] && break
  sleep 3
done
[ "$st" = "healthy" ] || die "backend not healthy after 90s — check: compose logs backend"
ok "backend healthy ($BACKEND_CID)"

# ---------------------------------------------------------------------------
# 5) frontends
# ---------------------------------------------------------------------------
log "5/9 building + starting frontends ..."
compose build frontend opportunity_center
compose up -d frontend opportunity_center
for var in "${FRONTEND_CONTAINER_NAME:-arbicore-x-frontend}" \
           "${OPPORTUNITY_CENTER_CONTAINER_NAME:-arbicore-x-opportunity-center}"; do
  for i in $(seq 1 30); do
    st=$(docker inspect -f '{{.State.Health.Status}}' "$var" 2>/dev/null || echo starting)
    [ "$st" = "healthy" ] && break
    sleep 2
  done
  [ "$st" = "healthy" ] || die "${var} not healthy after 60s"
  ok "${var} healthy"
done

# ---------------------------------------------------------------------------
# 6-8) reverse proxy + TLS (greenfield only)
# ---------------------------------------------------------------------------
if [ "$PROFILE" = "greenfield" ]; then
  log "6/9 starting nginx (HTTP only, awaiting cert) ..."
  compose up -d nginx || {
    c_red "nginx failed to boot (expected on first run — certs not issued yet)."
    c_red "Bootstrap-http will be handled by init-letsencrypt.sh next."
  }
  ok "nginx container present (may be restarting until certs exist)"

  log "7/9 requesting Let's Encrypt cert (MODE=${LETSENCRYPT_MODE:-staging}) ..."
  "${REPO_ROOT}/deployment/ssl/init-letsencrypt.sh"
  ok "cert issued"

  log "8/9 reloading nginx to activate TLS ..."
  compose restart nginx
  sleep 3
  compose exec -T nginx nginx -t
  ok "nginx reloaded; TLS active"
else
  log "6/9 nginx — peer stack owns TLS (no-op in shared profile)"
  log "7/9 certbot — peer stack owns TLS (no-op in shared profile)"
  log "8/9 nginx reload — peer stack owns TLS (no-op in shared profile)"
fi

# ---------------------------------------------------------------------------
# 9) healthcheck (profile-aware)
# ---------------------------------------------------------------------------
log "9/9 running healthcheck ..."
ARBICORE_DEPLOY_PROFILE="$PROFILE" "${REPO_ROOT}/scripts/healthcheck.sh" || {
  c_red "healthcheck reported issues — inspect logs. Stack is left running for diagnosis."
  exit 2
}

# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
c_green ""
c_green "  ================================================================="
c_green "  ArbiCore X — INSTALL COMPLETE ($PROFILE profile)"
c_green "  Version:        $(cat "${REPO_ROOT}/VERSION")"
if [ "$PROFILE" = "greenfield" ]; then
  c_green "  URL:            https://${DOMAIN}"
  c_green "  Opportunity C.: https://${DOMAIN}/opportunity-center/"
  c_green "  API health:     https://${DOMAIN}/api/"
  c_green "  Cert mode:      ${LETSENCRYPT_MODE:-staging}"
else
  c_green "  Backend port:   ${BACKEND_HOST_BIND:-127.0.0.1}:${BACKEND_HOST_PORT:-8101}"
  c_green "  Frontend port:  ${FRONTEND_HOST_BIND:-127.0.0.1}:${FRONTEND_HOST_PORT:-8102}"
  c_green "  Ops Center:     ${OPPORTUNITY_CENTER_HOST_BIND:-127.0.0.1}:${OPPORTUNITY_CENTER_HOST_PORT:-8103}"
  c_green "  Peer Mongo:     ${MONGO_HOST}:${MONGO_PORT:-27017}  db=${DB_NAME}"
  c_green "  Peer network:   ${NETWORK_NAME}"
fi
c_green "  ================================================================="
c_green ""
if [ "$PROFILE" = "greenfield" ]; then
  c_green "  Next steps:"
  c_green "    1. Verify all pages load in a browser."
  c_green "    2. If cert mode was 'staging', re-run with LETSENCRYPT_MODE=prod in .env."
  c_green "    3. Add renew cron:  cat deployment/ssl/cronjob.example >> /etc/crontab"
  c_green "    4. Add backup cron: 0 3 * * * ${REPO_ROOT}/deployment/backups/backup-cron.sh"
else
  c_green "  Next steps:"
  c_green "    1. Wire the peer reverse proxy (Caddy/nginx) to the loopback ports above."
  c_green "    2. Confirm ArbiCore X reads/writes db=${DB_NAME} inside ${MONGO_HOST}."
  c_green "    3. Peer stack owns TLS + certbot renewals — verify their schedule."
fi
c_green ""
