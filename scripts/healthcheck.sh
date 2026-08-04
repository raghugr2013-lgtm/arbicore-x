#!/usr/bin/env bash
# =============================================================================
# healthcheck.sh — profile-aware aggregate health probe (v2.9.2+).
#
# Combines:
#   1) container-level health checks (profile-aware container name set)
#   2) HTTP-level probes
#   3) TLS cert expiry warning (greenfield only)
#
# Profile is taken from ARBICORE_DEPLOY_PROFILE (env or .env), defaulting to
# greenfield. The check set is chosen per profile — a shared deployment does
# NOT have arbicore-x-mongo or arbicore-x-nginx, so probing them would always
# fail.
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

PROFILE="${ARBICORE_DEPLOY_PROFILE:-greenfield}"
case "$PROFILE" in
  greenfield|shared) : ;;
  *) printf "  FAIL  invalid profile '%s'\n" "$PROFILE" >&2; exit 1 ;;
esac

# Shared profile also needs .env.shared for container-name overrides.
if [ "$PROFILE" = "shared" ]; then
  SHARED_ENV_FILE="${REPO_ROOT}/deployment/compose/.env.shared"
  if [ -f "$SHARED_ENV_FILE" ]; then
    # shellcheck disable=SC1090
    set -a; source "$SHARED_ENV_FILE"; set +a
  fi
fi

PASS=0; FAIL=0
ok(){ printf "  OK    %s\n" "$*"; PASS=$((PASS+1)); }
ng(){ printf "  FAIL  %s\n" "$*" >&2; FAIL=$((FAIL+1)); }

printf "  profile: %s\n\n" "$PROFILE"

# --- container healthchecks ---
if [ "$PROFILE" = "greenfield" ]; then
  CONTAINERS=(
    arbicore-x-mongo
    arbicore-x-backend
    arbicore-x-frontend
    arbicore-x-opportunity-center
    arbicore-x-nginx
  )
else
  # In shared mode, peer stack owns Mongo + reverse proxy.
  # Container names are overridable via .env.shared (multi-tenant hosts).
  CONTAINERS=(
    "${BACKEND_CONTAINER_NAME:-arbicore-x-backend}"
    "${FRONTEND_CONTAINER_NAME:-arbicore-x-frontend}"
    "${OPPORTUNITY_CENTER_CONTAINER_NAME:-arbicore-x-opportunity-center}"
  )
fi

for c in "${CONTAINERS[@]}"; do
  st=$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo "missing")
  case "$st" in
    healthy)   ok "container $c healthy" ;;
    starting)  ng "container $c still starting" ;;
    unhealthy) ng "container $c UNHEALTHY" ;;
    missing)   ng "container $c MISSING" ;;
    *)         ng "container $c status=$st" ;;
  esac
done

# --- shared-profile: verify peer Mongo reachability from the backend ---
if [ "$PROFILE" = "shared" ] && command -v docker >/dev/null; then
  BACKEND_CID="${BACKEND_CONTAINER_NAME:-arbicore-x-backend}"
  MHOST="${MONGO_HOST:-factory-mongo}"
  if docker exec "$BACKEND_CID" python -c \
      "import socket; socket.gethostbyname('$MHOST')" >/dev/null 2>&1; then
    ok "backend can resolve peer Mongo host '$MHOST'"
  else
    ng "backend CANNOT resolve peer Mongo host '$MHOST' — check NETWORK_NAME and .env MONGO_URL"
  fi
fi

# --- HTTP checks ---
if command -v curl >/dev/null; then
  if [ "$PROFILE" = "greenfield" ]; then
    CODE=$(curl -sk -o /dev/null -m 5 -w '%{http_code}' "http://localhost/nginx-health" 2>/dev/null || echo 000)
    [ "$CODE" = "200" ] && ok "nginx /nginx-health -> 200" || ng "nginx /nginx-health -> $CODE"
  else
    # Shared: probe the backend on its loopback host port (default 8101).
    BPORT="${BACKEND_HOST_PORT:-8101}"
    BBIND="${BACKEND_HOST_BIND:-127.0.0.1}"
    CODE=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://${BBIND}:${BPORT}/api/" 2>/dev/null || echo 000)
    [ "$CODE" = "200" ] && ok "backend http://${BBIND}:${BPORT}/api/ -> 200" || ng "backend http://${BBIND}:${BPORT}/api/ -> $CODE"
  fi
fi

# --- greenfield-only: external TLS probe ---
if [ "$PROFILE" = "greenfield" ] && [ -n "${DOMAIN:-}" ] \
    && [ -x "${REPO_ROOT}/deployment/monitoring/uptime-probe.sh" ]; then
  printf "\n  --- external probe (via https://%s) ---\n" "$DOMAIN"
  "${REPO_ROOT}/deployment/monitoring/uptime-probe.sh" || FAIL=$((FAIL+1))
fi

printf "\nSummary: %d OK / %d FAIL\n" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
