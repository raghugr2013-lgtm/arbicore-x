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

# --- greenfield: Caddy/proxy network attachment guard ---
# When the peer stack's vqb-network is present on the host, the services the
# peer Caddy reverse-proxy must reach (backend, frontend, opportunity_center)
# MUST be attached to it — otherwise Caddy cannot resolve them by container
# name and returns HTTP 502. This assertion turns the old manual
# `docker network connect vqb-network arbicore-x-frontend` step into an
# automated, fail-loud check. It is skipped on hosts without vqb-network.
if [ "$PROFILE" = "greenfield" ] && command -v docker >/dev/null; then
  if docker network inspect vqb-network >/dev/null 2>&1; then
    for c in arbicore-x-backend arbicore-x-frontend arbicore-x-opportunity-center; do
      nets=$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$c" 2>/dev/null || echo "")
      if printf '%s' "$nets" | grep -qw vqb-network; then
        ok "container $c attached to vqb-network (Caddy-reachable)"
      else
        ng "container $c NOT on vqb-network — peer Caddy will 502 (fix: canonical compose now dual-homes it; run 'docker compose up -d --force-recreate $c')"
      fi
    done
  else
    printf "  note  vqb-network absent on host — skipping Caddy attachment check (standalone/greenfield-nginx mode)\n"
  fi
fi

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
    # -------------------------------------------------------------------------
    # Shared profile HTTP probe (audited 2026-06).
    #
    # Design fact: in shared/co-tenant mode the backend is fronted by the PEER
    # Caddy reverse proxy, which reaches it over the shared Docker network BY
    # CONTAINER NAME. Per docs/DEPLOYMENT_ARCHITECTURE_FROZEN.md the backend does
    # NOT publish a host port on this VPS (the canonical shared compose maps
    # only 127.0.0.1:8101, and the production VPS publishes none at all). The
    # previous probe assumed 127.0.0.1:8101 and therefore always returned 000.
    #
    # Correct, architecture-preserving probes (no host port required, no VPS
    # change, all READ-ONLY — SHADOW governance untouched):
    #   1. AUTHORITATIVE: curl /api/ from INSIDE the backend container (same
    #      liveness check the compose healthcheck uses; Docker-network direct).
    #   2. END-TO-END: probe https://$DOMAIN/api/ THROUGH Caddy when a public
    #      DOMAIN is configured (validates the real operator/browser path).
    #   3. OPTIONAL: loopback host-port probe, ONLY if a port is actually
    #      published — never a failure when it is not (the default here).
    # See docs/HEALTHCHECK_SHARED_PROFILE.md.
    # -------------------------------------------------------------------------
    BACKEND_CID="${BACKEND_CONTAINER_NAME:-arbicore-x-backend}"

    # 1. Authoritative in-container liveness.
    if command -v docker >/dev/null \
       && docker exec "$BACKEND_CID" curl -fs -m 5 http://127.0.0.1:8001/api/ >/dev/null 2>&1; then
      ok "backend /api/ (in-container 127.0.0.1:8001) -> 200"
    else
      ng "backend /api/ (in-container 127.0.0.1:8001) unreachable in $BACKEND_CID"
    fi

    # 2. End-to-end through the peer Caddy proxy (only when DOMAIN is set).
    if [ -n "${DOMAIN:-}" ]; then
      DHOST="${DOMAIN#https://}"; DHOST="${DHOST#http://}"; DHOST="${DHOST%/}"
      CODE=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "https://${DHOST}/api/" 2>/dev/null || echo 000)
      [ "$CODE" = "200" ] \
        && ok "backend via Caddy https://${DHOST}/api/ -> 200" \
        || ng "backend via Caddy https://${DHOST}/api/ -> $CODE"
    else
      printf "  note  DOMAIN not set in env — skipping public Caddy end-to-end probe\n"
    fi

    # 3. Optional loopback host-port probe — ONLY when actually published.
    if command -v docker >/dev/null \
       && [ -n "$(docker port "$BACKEND_CID" 8001/tcp 2>/dev/null)" ]; then
      BPORT="${BACKEND_HOST_PORT:-8101}"; BBIND="${BACKEND_HOST_BIND:-127.0.0.1}"
      CODE=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://${BBIND}:${BPORT}/api/" 2>/dev/null || echo 000)
      [ "$CODE" = "200" ] \
        && ok "backend host-port http://${BBIND}:${BPORT}/api/ -> 200" \
        || ng "backend host-port http://${BBIND}:${BPORT}/api/ -> $CODE (published but not answering)"
    else
      printf "  note  backend publishes no host port (by design on this VPS) — skipping loopback host-port probe\n"
    fi
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
