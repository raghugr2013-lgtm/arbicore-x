#!/usr/bin/env bash
# uptime-probe.sh — external-style uptime check.
# Runs from ANY host (VPS itself or a monitoring box). Exits 0 GREEN, non-zero on any RED.
# No writes anywhere. Read-only.
#
# Usage:
#   DOMAIN=arbicore.example.com ./uptime-probe.sh
#   ARBICORE_TOKEN=<bearer> DOMAIN=... ./uptime-probe.sh   # also probes authed /api/arbicore/health
set -uo pipefail

: "${DOMAIN:?DOMAIN must be set}"
BASE="https://${DOMAIN}"

PASS=0; FAIL=0
ok(){ printf "  OK    %s\n" "$*"; PASS=$((PASS+1)); }
ng(){ printf "  FAIL  %s\n" "$*" >&2; FAIL=$((FAIL+1)); }

# 1) HTTPS reachable
CODE=$(curl -sk -o /dev/null -m 10 -w '%{http_code}' "${BASE}/") || CODE="000"
[ "$CODE" = "200" ] && ok "GET ${BASE}/ -> 200" || ng "GET ${BASE}/ -> ${CODE}"

# 2) API liveness
CODE=$(curl -sk -o /dev/null -m 10 -w '%{http_code}' "${BASE}/api/") || CODE="000"
[ "$CODE" = "200" ] && ok "GET ${BASE}/api/ -> 200" || ng "GET ${BASE}/api/ -> ${CODE}"

# 3) OpenAPI includes arbicore
if curl -sk -m 10 "${BASE}/openapi.json" | grep -q "/api/arbicore"; then
  ok "openapi.json exposes /api/arbicore/*"
else
  ng "openapi.json missing /api/arbicore/* — wrong build?"
fi

# 4) TLS cert expiry (advisory — warns if <14d)
EXP=$(echo | openssl s_client -servername "${DOMAIN}" -connect "${DOMAIN}:443" 2>/dev/null \
      | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
if [ -n "$EXP" ]; then
  EXP_TS=$(date -d "$EXP" +%s 2>/dev/null || echo 0)
  NOW=$(date +%s)
  DAYS=$(( (EXP_TS - NOW) / 86400 ))
  if [ "$DAYS" -lt 14 ]; then
    ng "TLS cert expires in ${DAYS} days"
  else
    ok "TLS cert expires in ${DAYS} days"
  fi
fi

# 5) Optional authed check
if [ -n "${ARBICORE_TOKEN:-}" ]; then
  CODE=$(curl -sk -o /dev/null -m 10 -w '%{http_code}' -H "Authorization: Bearer ${ARBICORE_TOKEN}" \
         "${BASE}/api/arbicore/health") || CODE="000"
  [ "$CODE" = "200" ] && ok "authed /api/arbicore/health -> 200" || ng "authed /api/arbicore/health -> ${CODE}"
fi

printf "\nSummary: %d OK / %d FAIL\n" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
