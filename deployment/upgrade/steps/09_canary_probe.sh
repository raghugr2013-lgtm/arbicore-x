#!/usr/bin/env bash
# 09_canary_probe.sh — short-window post-cutover canary. READ-ONLY.
# Runs a ~60s probe loop against the NEW backend immediately after 06_cutover.sh.
# Triggers the existing auto-rollback (calls steps/99_rollback.sh) if the failure
# threshold is exceeded. NEVER writes to MongoDB. NEVER changes config or scanner state.
#
# Tuning (env-overridable, all optional):
#   CANARY_DURATION_SECS   total probe window      (default: 60)
#   CANARY_INTERVAL_SECS   probe interval          (default: 2)
#   CANARY_MAX_CONSEC_FAIL abort after N back-to-back failures (default: 3)
#   CANARY_MAX_FAIL_PCT    abort if failure rate > this percentage over the window (default: 20)
#   CANARY_AUTO_ROLLBACK   "yes" (default) | "no"  -- "no" exits non-zero without invoking rollback
#   ARBICORE_TOKEN         optional bearer to also exercise /api/arbicore/health
#
# Endpoints probed (all GET, read-only):
#   /api/                                                    (liveness)
#   /openapi.json                                            (must still expose /api/arbicore/*)
#   /api/arbicore/health                  (only if ARBICORE_TOKEN is set)
#
# Exit codes:
#   0 = canary PASS (within threshold)
#   1 = canary FAIL, rollback triggered (or skipped if CANARY_AUTO_ROLLBACK=no)
#
# B3 NOTE: the probe loop runs inside a `{ ... } | tee` brace group, which is a
# pipeline component and therefore executes in a SUBSHELL. Variables set inside
# the brace group do not propagate to the parent shell. We export the abort
# state via a sentinel FILE (read by the parent after the pipeline ends).
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
load_env
need_cmd curl

DURATION="${CANARY_DURATION_SECS:-60}"
INTERVAL="${CANARY_INTERVAL_SECS:-2}"
MAX_CONSEC="${CANARY_MAX_CONSEC_FAIL:-3}"
MAX_PCT="${CANARY_MAX_FAIL_PCT:-20}"
AUTO_RB="${CANARY_AUTO_ROLLBACK:-yes}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${LOG_DIR}/canary_${TS}.log"
ABORT_FILE="${LOG_DIR}/.canary_abort_${TS}"
mkdir -p "$LOG_DIR"
: > "$ABORT_FILE"

log "Canary starting: ${DURATION}s window, probe every ${INTERVAL}s (consec_fail<=${MAX_CONSEC}, fail_pct<=${MAX_PCT}%)"
log "Log: $OUT"

END_TS=$(( $(date +%s) + DURATION ))

probe_once() {
  # All probes are read-only. Returns 0 = green, 1 = any check failed this iteration.
  local fail=0 detail="" code

  # Allow tests / dry-runs to short-circuit. PROBE_FORCE_FAIL=1 means "this probe is failing".
  if [ "${PROBE_FORCE_FAIL:-0}" = "1" ]; then
    echo "[$(date -u +%H:%M:%SZ)] BAD (forced) total=${TOTAL} fails=${FAILS} consec=${CONSEC}"
    return 1
  fi
  # PROBE_FORCE_PASS=1 means "this probe is passing"; intended for dry-run verification only.
  if [ "${PROBE_FORCE_PASS:-0}" = "1" ]; then
    echo "[$(date -u +%H:%M:%SZ)] OK  (forced) total=${TOTAL} fails=${FAILS} consec=${CONSEC}"
    return 0
  fi

  # (1) /api/ liveness
  code="$(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/api/ 2>/dev/null || echo "000")"
  if [ "$code" != "200" ]; then
    fail=1; detail="${detail} api=${code}"
  fi

  # (2) /api/arbicore/* still in OpenAPI (catches accidental wrong-image deploys)
  if ! curl -s -m 4 -fs http://127.0.0.1:8001/openapi.json 2>/dev/null \
       | grep -q "/api/arbicore/scanners/cex_arb/config"; then
    fail=1; detail="${detail} arbicore_api=missing"
  fi

  # (3) authed /api/arbicore/health -- only if a token is provided (purely read-only)
  if [ -n "${ARBICORE_TOKEN:-}" ]; then
    code="$(curl -s -m 4 -o /dev/null -w '%{http_code}' \
              -H "Authorization: Bearer ${ARBICORE_TOKEN}" \
              http://127.0.0.1:8001/api/arbicore/health 2>/dev/null || echo "000")"
    if [ "$code" != "200" ]; then
      fail=1; detail="${detail} arbicore_health=${code}"
    fi
  fi

  if [ "$fail" -eq 0 ]; then
    echo "[$(date -u +%H:%M:%SZ)] OK  total=${TOTAL} fails=${FAILS} consec=${CONSEC}"
  else
    echo "[$(date -u +%H:%M:%SZ)] BAD total=${TOTAL} fails=${FAILS} consec=${CONSEC} ${detail}"
  fi
  return "$fail"
}

# Probe loop. Lives inside a brace group piped to `tee`, which means it runs in a
# subshell -- so variables set here do NOT leak to the parent. The abort decision
# is exported via the sentinel file $ABORT_FILE, which the parent reads below.
{
  echo "=== canary @ ${TS} ==="
  echo "duration=${DURATION}s interval=${INTERVAL}s max_consec=${MAX_CONSEC} max_pct=${MAX_PCT}%"
  TOTAL=0
  FAILS=0
  CONSEC=0
  while [ "$(date +%s)" -lt "$END_TS" ]; do
    TOTAL=$((TOTAL + 1))
    if probe_once; then
      CONSEC=0
    else
      FAILS=$((FAILS + 1))
      CONSEC=$((CONSEC + 1))
      if [ "$CONSEC" -ge "$MAX_CONSEC" ]; then
        echo "consecutive failures: ${CONSEC} >= ${MAX_CONSEC}" > "$ABORT_FILE"
        break
      fi
    fi
    sleep "$INTERVAL"
  done

  # Final rate check (only relevant if we didn't already abort on consecutive failures)
  if [ ! -s "$ABORT_FILE" ] && [ "$TOTAL" -gt 0 ]; then
    PCT=$(( FAILS * 100 / TOTAL ))
    echo "summary: total=${TOTAL} fails=${FAILS} pct=${PCT}% consec_max=${CONSEC}"
    if [ "$PCT" -gt "$MAX_PCT" ]; then
      echo "failure rate ${PCT}% > threshold ${MAX_PCT}%" > "$ABORT_FILE"
    fi
  fi
} | tee "$OUT"

# Parent-shell read of the sentinel. This is the line that the B3 fix was needed for:
# previously, ABORT_REASON was set inside the subshell and lost.
ABORT_REASON="$(cat "$ABORT_FILE" 2>/dev/null || true)"
rm -f "$ABORT_FILE"

if [ -n "$ABORT_REASON" ]; then
  c_red "CANARY ABORT: ${ABORT_REASON}"
  if [ "$AUTO_RB" = "yes" ]; then
    c_red "Triggering automatic rollback via steps/99_rollback.sh ..."
    # ROLLBACK_CMD lets test harnesses substitute a mock (defaults to the real rollback).
    ROLLBACK_CMD="${ROLLBACK_CMD:-${ROOT_DIR}/steps/99_rollback.sh}"
    if "$ROLLBACK_CMD"; then
      c_red "Rollback complete. Production is on OLD again. See ${OUT} for canary detail."
    else
      die "ROLLBACK ITSELF FAILED — manual intervention required. See ${OUT}."
    fi
  else
    c_red "CANARY_AUTO_ROLLBACK=no — NOT invoking rollback. Operator must run steps/99_rollback.sh."
  fi
  exit 1
fi

c_green "CANARY GREEN — proceed to 10_validate.sh. Log: ${OUT}"
exit 0
