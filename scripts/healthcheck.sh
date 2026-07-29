#!/usr/bin/env bash
# healthcheck.sh — read-only aggregate health probe.
# Combines:
#   1) container-level health (mongo, backend, frontend, opportunity_center, nginx)
#   2) HTTP-level probe (/api/, openapi.json, /nginx-health)
#   3) TLS cert expiry warning (via deployment/monitoring/uptime-probe.sh)
# Exits 0 GREEN, 1 RED.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

PASS=0; FAIL=0
ok(){ printf "  OK    %s\n" "$*"; PASS=$((PASS+1)); }
ng(){ printf "  FAIL  %s\n" "$*" >&2; FAIL=$((FAIL+1)); }

# --- container healthchecks ---
for c in arbicore-x-mongo arbicore-x-backend arbicore-x-frontend \
         arbicore-x-opportunity-center arbicore-x-nginx; do
  st=$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo "missing")
  case "$st" in
    healthy) ok "container $c healthy" ;;
    starting) ng "container $c still starting" ;;
    unhealthy) ng "container $c UNHEALTHY" ;;
    missing) ng "container $c MISSING" ;;
    *) ng "container $c status=$st" ;;
  esac
done

# --- internal-network HTTP checks (via nginx :80 hairpin) ---
if command -v curl >/dev/null; then
  CODE=$(curl -sk -o /dev/null -m 5 -w '%{http_code}' "http://localhost/nginx-health" 2>/dev/null || echo 000)
  [ "$CODE" = "200" ] && ok "nginx /nginx-health -> 200" || ng "nginx /nginx-health -> $CODE"
fi

# --- delegate to uptime-probe.sh if DOMAIN is set ---
if [ -n "${DOMAIN:-}" ] && [ -x "${REPO_ROOT}/deployment/monitoring/uptime-probe.sh" ]; then
  printf "\n  --- external probe (via https://%s) ---\n" "$DOMAIN"
  "${REPO_ROOT}/deployment/monitoring/uptime-probe.sh" || FAIL=$((FAIL+1))
fi

printf "\nSummary: %d OK / %d FAIL\n" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
