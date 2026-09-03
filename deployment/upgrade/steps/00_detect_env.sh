#!/usr/bin/env bash
# 00_detect_env.sh — AUTO-DETECT the production environment on the VPS and bake it in.
# Writes deploy.env (+ compose/.env + backend/.env from the live container).
# Non-destructive. Stops if detection is ambiguous (never guesses silently).
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
need_cmd docker

log "Detecting production backend container..."

# Do NOT identify the backend by image name or port.
# Disposable validator/livehunt containers intentionally reuse the same
# arbicore-x-backend image and may expose/use port 8001.
BACKEND_CANDIDATES="$(detect_backend_candidates)"

# Preserve an operator-provided backend selection if one exists in the
# environment or in the previously generated deploy.env.
EXPLICIT_BACKEND="${BACKEND_OLD:-}"
if [ -z "$EXPLICIT_BACKEND" ] && [ -f "$DEPLOY_ENV" ]; then
  EXPLICIT_BACKEND="$(
    (
      set -a
      source "$DEPLOY_ENV"
      printf '%s' "${BACKEND_OLD:-}"
    )
  )"
fi

set +e
BACKEND_OLD="$(select_backend_container "$BACKEND_CANDIDATES" "$EXPLICIT_BACKEND")"
_sel_backend_rc=$?
set -e

BACKEND_ONE_LINE="$(printf '%s' "$BACKEND_CANDIDATES" | tr '\n' ' ')"

case "$_sel_backend_rc" in
  0)
    ;;
  2)
    die "configured BACKEND_OLD='$EXPLICIT_BACKEND' not found among authoritative backend candidates: [$BACKEND_ONE_LINE]
  -> correct BACKEND_OLD or remove the stale override and re-run."
    ;;
  *)
    die "expected exactly one authoritative production backend; found [$BACKEND_ONE_LINE]
  -> candidates are selected only by the canonical production container name.
  -> set BACKEND_OLD=<name> in deploy.env or environment only when operator-authoritative."
    ;;
esac

ok "backend container: $BACKEND_OLD (authoritative candidate selection)"

log "Detecting production Mongo container..."

# Production Mongo authority:
#
# 1. Explicit MONGO_CONTAINER is operator-authoritative.
# 2. Otherwise derive Mongo from the LIVE production backend's MONGO_URL.
#    This preserves the actual production topology even when multiple Mongo
#    containers exist on the VPS.
# 3. Only fall back to the historical candidate/default selector when the
#    running backend has no usable MONGO_URL.
#
# IMPORTANT:
# Do not blindly prefer ARBICORE_DEFAULT_MONGO. On this VPS the historical
# arbicore-x-mongo container exists but is NOT the Mongo used by production.

OLD_ENV="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$BACKEND_OLD" 2>/dev/null || true)"
get_old(){ printf '%s\n' "$OLD_ENV" | grep -E "^$1=" | head -n1 | cut -d= -f2-; }

EXPLICIT_MONGO="${MONGO_CONTAINER:-}"

# If the operator explicitly exported MONGO_CONTAINER, honor it.
if [ -n "$EXPLICIT_MONGO" ]; then
  MONGO_CONTAINER="$EXPLICIT_MONGO"
  ok "mongo container: $MONGO_CONTAINER (explicit environment configuration)"
else
  # The running production backend is the source of truth for the
  # currently deployed database topology.
  OLD_MONGO_URL="$(get_old MONGO_URL)"
  OLD_HOST="$(mongo_url_host "$OLD_MONGO_URL")"

  if [ -n "$OLD_HOST" ] && docker inspect "$OLD_HOST" >/dev/null 2>&1; then
    MONGO_CONTAINER="$OLD_HOST"
    ok "mongo container: $MONGO_CONTAINER (derived from live backend MONGO_URL)"
  else
    # Only use deploy.env as a fallback when the live backend cannot
    # identify its Mongo container.
    EXPLICIT_MONGO="$(
      if [ -f "$DEPLOY_ENV" ]; then
        (
          set -a
          source "$DEPLOY_ENV"
          printf '%s' "${MONGO_CONTAINER:-}"
        )
      fi
    )"

    if [ -n "$EXPLICIT_MONGO" ]; then
      MONGO_CONTAINER="$EXPLICIT_MONGO"
      ok "mongo container: $MONGO_CONTAINER (deploy.env fallback)"
    else
      log "Live backend MONGO_URL did not resolve and deploy.env has no Mongo override; using candidate/default fallback..."

      MONGO_CANDIDATES="$(detect_one 'mongo')"
      MONGO_COUNT="$(printf '%s\n' "$MONGO_CANDIDATES" | grep -c . || true)"
      [ "$MONGO_COUNT" -ge 1 ] ||
        die "no Mongo container found — is the production Mongo running?"

      set +e
      MONGO_CONTAINER="$(choose_mongo_container \
        "$MONGO_CANDIDATES" \
        "" \
        "$ARBICORE_DEFAULT_MONGO")"
      _sel_rc=$?
      set -e

      CAND_ONE_LINE="$(printf '%s' "$MONGO_CANDIDATES" | tr '\n' ' ')"

      case "$_sel_rc" in
        0)
          ok "mongo container: $MONGO_CONTAINER (fallback authoritative selection)"
          ;;
        *)
          die "multiple Mongo containers found and live backend MONGO_URL could not identify one: [$CAND_ONE_LINE]
-> set MONGO_CONTAINER=<name> (environment or deploy.env), or fix the live backend MONGO_URL and re-run."
          ;;
      esac
    fi
  fi
fi

validate_mongo_container "$MONGO_CONTAINER" \
  || die "selected Mongo container '$MONGO_CONTAINER' is not running or is unhealthy — refusing to proceed."

MONGO_CANDIDATES="$(detect_one 'mongo' || true)"
CAND_ONE_LINE="$(printf '%s' "$MONGO_CANDIDATES" | tr '\n' ' ')"

log "Detecting Docker network (shared with Mongo)..."

log "Detecting Docker network (shared with Mongo)..."
NETWORK_NAME="$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' "$MONGO_CONTAINER" | grep -v '^$' | head -n1)"
[ -n "$NETWORK_NAME" ] || die "could not determine Mongo network"
ok "network: $NETWORK_NAME"

log "Recording Mongo volume / bind-mount (for preservation confirmation)..."
MONGO_MOUNTS="$(docker inspect -f '{{range .Mounts}}{{.Type}}:{{.Source}}->{{.Destination}}; {{end}}' "$MONGO_CONTAINER")"
ok "mongo mounts: ${MONGO_MOUNTS:-<none/anonymous>}"

log "Resolving Mongo hostname on the network (for new backend MONGO_URL)..."
# Prefer the existing backend's MONGO_URL; fall back to the mongo container name.
OLD_ENV="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$BACKEND_OLD" 2>/dev/null || true)"
get_old(){ printf '%s\n' "$OLD_ENV" | grep -E "^$1=" | head -n1 | cut -d= -f2-; }

MONGO_URL="mongodb://${MONGO_CONTAINER}:27017"
OLD_MONGO_URL="$(get_old MONGO_URL)"
if [ -n "${ARBICORE_MONGO_URL:-}" ]; then
  # Operator-authoritative full override.
  MONGO_URL="$ARBICORE_MONGO_URL"
  ok "MONGO_URL: operator override via ARBICORE_MONGO_URL"
elif [ -n "$OLD_MONGO_URL" ]; then
  OLD_HOST="$(mongo_url_host "$OLD_MONGO_URL")"
  if [ "$OLD_HOST" = "$MONGO_CONTAINER" ]; then
    MONGO_URL="$OLD_MONGO_URL"   # already consistent with the selected container
  else
    # Reconcile the host to the authoritative container the preflight selected,
    # preserving credentials / authSource / query / path. Loudly reported —
    # never silently trusts a stale host.
    MONGO_URL="$(rewrite_mongo_host "$OLD_MONGO_URL" "$MONGO_CONTAINER")"
    c_red "  WARN - old backend MONGO_URL host '$OLD_HOST' != selected authoritative Mongo '$MONGO_CONTAINER'."
    c_red "         Reconciled host -> '$MONGO_CONTAINER' (credentials/authSource/DB preserved)."
    c_red "         If '$OLD_HOST' is in fact authoritative, set MONGO_CONTAINER=$OLD_HOST"
    c_red "         (or ARBICORE_MONGO_URL=<full-url>) and re-run 00_detect_env.sh."
  fi
fi
DB_NAME="$(get_old DB_NAME)";     [ -n "$DB_NAME" ] || DB_NAME="arbicore_x_prod"
ok "MONGO_URL: $(printf '%s' "$MONGO_URL" | sed -E 's#//[^@]*@#//***@#')   DB_NAME: $DB_NAME"
# Consistency guarantee: the generated URL host MUST equal the selected container.
[ "$(mongo_url_host "$MONGO_URL")" = "$MONGO_CONTAINER" ] || [ -n "${ARBICORE_MONGO_URL:-}" ] \
  || die "internal: MONGO_URL host does not match selected container '$MONGO_CONTAINER'"

# Provenance / image tag
GITSHA="$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "$(date +%Y%m%d)")"
GITTAG="$(git -C "$ROOT_DIR" describe --tags --always --dirty 2>/dev/null || echo "$GITSHA")"
BUILD_TIME="$(date -u +%FT%TZ)"
APP_VERSION="$GITTAG"
# Unambiguous image identity: <repo-semver>-<short-sha> (no static 0.1.0-realign
# prefix that would collide across different commits). VERSION is resolved from
# the REPOSITORY ROOT (REPO_ROOT), NOT the deployment/upgrade dir. Falls back to
# 0.0.0 only if the repo VERSION file is genuinely absent (never hardcoded).
APP_SEMVER="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION" 2>/dev/null || true)"
[ -n "$APP_SEMVER" ] || APP_SEMVER="0.0.0"
IMAGE_TAG="arbicore-x-backend:${APP_SEMVER}-${GITSHA}"
BACKEND_NEW="arbicore-x-backend"
[ "$BACKEND_NEW" = "$BACKEND_OLD" ] && BACKEND_NEW="arbicore-x-backend-new"  # avoid name collision

log "Writing deploy.env ..."
{
  echo "# AUTO-GENERATED by 00_detect_env.sh on $(date -u +%FT%TZ). Do not commit secrets."
  echo "# Values are single-quoted and shell-safe; safe to \`source\`."
  env_kv BACKEND_OLD     "$BACKEND_OLD"
  env_kv BACKEND_NEW     "$BACKEND_NEW"
  env_kv MONGO_CONTAINER "$MONGO_CONTAINER"
  env_kv NETWORK_NAME    "$NETWORK_NAME"
  env_kv IMAGE_TAG       "$IMAGE_TAG"
  env_kv GITSHA          "$GITSHA"
  env_kv DB_NAME         "$DB_NAME"
  env_kv MONGO_MOUNTS    "$MONGO_MOUNTS"
} > "$DEPLOY_ENV"
ok "deploy.env written"

log "Writing compose/.env (for compose interpolation) ..."
cat > "$COMPOSE_ENV" <<EOF
NETWORK_NAME=${NETWORK_NAME}
IMAGE_TAG=${IMAGE_TAG}
BACKEND_NEW=${BACKEND_NEW}
GITSHA=${GITSHA}
GITTAG=${GITTAG}
BUILD_TIME=${BUILD_TIME}
APP_VERSION=${APP_VERSION}
EOF
ok "compose/.env written"

log "Baking backend/.env from the LIVE production container (preserve exact config) ..."
mkdir -p "$(dirname "$BACKEND_ENV")" "$LOG_DIR"
: > "$BACKEND_ENV"; chmod 600 "$BACKEND_ENV"

# W2: refuse to write a near-empty .env if docker inspect produced nothing useful.
# The OLD container always has at least PATH/HOSTNAME plus a handful of app vars,
# so a capture under 5 lines is a strong indicator of an inspect failure.
OLD_ENV_LINES="$(printf '%s\n' "$OLD_ENV" | grep -c '=' || true)"
[ "$OLD_ENV_LINES" -ge 5 ] || die "OLD container env capture suspiciously empty ($OLD_ENV_LINES lines) — refusing to bake .env"

# B2 (hybrid application-variable copy):
# Inherit ONLY application-specific env vars from OLD; never inherit Docker/runtime/system
# vars (PATH, HOSTNAME, PYTHON_*, LANG, ...). An OLD variable is APPLICATION-LEVEL iff its
# name matches one of:
#   - a prefix in APP_PREFIX_RE      (ARBICORE_, MONGO_, DB_, JWT_, VAULT_, FEATURE_)
#   - a suffix in APP_SUFFIX_RE      (_API_KEY, _SECRET, _RPC_URL, _TOKEN, _WEBHOOK, _WEBHOOK_URL, _DSN)
#   - an explicit name in APP_EXPLICIT_RE (CORS_ORIGINS, LOG_LEVEL, SENTRY_DSN)
APP_PREFIX_RE='^(ARBICORE|MONGO|DB|JWT|VAULT|FEATURE)_'
APP_SUFFIX_RE='_(API_KEY|SECRET|RPC_URL|TOKEN|WEBHOOK|WEBHOOK_URL|DSN)$'
APP_EXPLICIT_RE='^(CORS_ORIGINS|LOG_LEVEL|SENTRY_DSN)$'

PARITY_TS="$(date -u +%Y%m%dT%H%M%SZ)"
PARITY_REPORT="${LOG_DIR}/env_parity_${PARITY_TS}.txt"
OLD_APP_KEYS="${LOG_DIR}/.env_old_app_keys_${PARITY_TS}"
NEW_APP_KEYS="${LOG_DIR}/.env_new_app_keys_${PARITY_TS}"
SKIPPED_LIST="${LOG_DIR}/.env_skipped_${PARITY_TS}"
: > "$OLD_APP_KEYS"; : > "$NEW_APP_KEYS"; : > "$SKIPPED_LIST"

COPIED=0
SKIPPED=0
while IFS= read -r line; do
  [ -z "$line" ] && continue
  case "$line" in *=*) : ;; *) continue ;; esac
  key="${line%%=*}"
  if echo "$key" | grep -Eq "$APP_PREFIX_RE" \
     || echo "$key" | grep -Eq "$APP_SUFFIX_RE" \
     || echo "$key" | grep -Eq "$APP_EXPLICIT_RE"; then
    echo "$line" >> "$BACKEND_ENV"
    echo "$key" >> "$OLD_APP_KEYS"
    COPIED=$((COPIED+1))
  else
    echo "$key" >> "$SKIPPED_LIST"
    SKIPPED=$((SKIPPED+1))
  fi
done <<< "$OLD_ENV"

# Guarantee the connection pivots are present (only added if OLD had nothing).
grep -q '^MONGO_URL=' "$BACKEND_ENV" || echo "MONGO_URL=${MONGO_URL}" >> "$BACKEND_ENV"
grep -q '^DB_NAME='   "$BACKEND_ENV" || echo "DB_NAME=${DB_NAME}"     >> "$BACKEND_ENV"
# Scanner-state preservation: only fall back if OLD set NEITHER flag explicitly.
# If OLD has ARBICORE_SCANNER_CEX_ARB=off, it was already copied above and is preserved.
grep -q '^ARBICORE_SCANNER_CEX_ARB='     "$BACKEND_ENV" || echo "ARBICORE_SCANNER_CEX_ARB=on"     >> "$BACKEND_ENV"
grep -q '^ARBICORE_SCANNER_FUNDING_ARB=' "$BACKEND_ENV" || echo "ARBICORE_SCANNER_FUNDING_ARB=on" >> "$BACKEND_ENV"

# ── T2 Base searcher (SHADOW) canonical wiring ──────────────────────────────
# The flashloan-live-shadow branch runs the T2 Base searcher in SHADOW mode.
# Wire the activation flag REPRODUCIBLY (defaults ON; an OLD-container value or a
# detect-time override `ARBICORE_T2_SEARCHER_ENABLED=...` is preserved). This
# NEVER enables broadcasting/signing — SHADOW only; Gate 7 $25 + Gate 8
# fail-closed + provenance enforcement are unaffected by this flag.
T2_FLAG="${ARBICORE_T2_SEARCHER_ENABLED:-true}"
grep -q '^ARBICORE_T2_SEARCHER_ENABLED=' "$BACKEND_ENV" \
  || echo "ARBICORE_T2_SEARCHER_ENABLED=${T2_FLAG}" >> "$BACKEND_ENV"

# Base WSS endpoint consumed by the T2 runtime. The code reads
# ARBICORE_WSS_URL_BASE FIRST, then falls back to ARBICORE_RPC_WSS_BASE
# (arbicore/searcher/live_base.py). Inject an operator-supplied value if present
# and not already inherited from the OLD container. NEVER fabricate a URL — if
# T2 is enabled and no WSS is provided, 01_preflight.sh fails closed.
if ! grep -q '^ARBICORE_WSS_URL_BASE=' "$BACKEND_ENV" && [ -n "${ARBICORE_WSS_URL_BASE:-}" ]; then
  echo "ARBICORE_WSS_URL_BASE=${ARBICORE_WSS_URL_BASE}" >> "$BACKEND_ENV"
fi
if ! grep -q '^ARBICORE_RPC_WSS_BASE=' "$BACKEND_ENV" && [ -n "${ARBICORE_RPC_WSS_BASE:-}" ]; then
  echo "ARBICORE_RPC_WSS_BASE=${ARBICORE_RPC_WSS_BASE}" >> "$BACKEND_ENV"
fi

# Build NEW key set from the file we just wrote and emit the parity report.
grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$BACKEND_ENV" | cut -d= -f1 | sort -u > "$NEW_APP_KEYS"
sort -u -o "$OLD_APP_KEYS" "$OLD_APP_KEYS"

OLD_APP_COUNT="$(wc -l < "$OLD_APP_KEYS" | tr -d ' ')"
NEW_APP_COUNT="$(wc -l < "$NEW_APP_KEYS" | tr -d ' ')"
MISSING="$(comm -23 "$OLD_APP_KEYS" "$NEW_APP_KEYS" | tr '\n' ' ')"
ADDED="$(comm -13 "$OLD_APP_KEYS" "$NEW_APP_KEYS"  | tr '\n' ' ')"
SKIPPED_KEYS="$(tr '\n' ' ' < "$SKIPPED_LIST")"

{
  echo "=== ENV PARITY REPORT @ ${PARITY_TS} ==="
  echo "  OLD application var count   : $OLD_APP_COUNT"
  echo "  NEW application var count   : $NEW_APP_COUNT"
  echo "  OLD-only vars (MISSING)     : ${MISSING:-<none>}"
  echo "  NEW-only vars (ADDED)       : ${ADDED:-<none>}"
  echo "  Non-app OLD vars skipped    : $SKIPPED  (system/runtime housekeeping)"
  echo "  Skipped key names           : ${SKIPPED_KEYS:-<none>}"
} | tee "$PARITY_REPORT"

# Defensive invariant: every OLD application var MUST be present in NEW.
if [ -n "$MISSING" ]; then
  die "ENV PARITY FAIL — OLD application vars not copied: $MISSING"
fi

rm -f "$OLD_APP_KEYS" "$NEW_APP_KEYS" "$SKIPPED_LIST"

c_green "ENV PARITY PASS (all $OLD_APP_COUNT OLD application vars preserved)"
ok "backend/.env baked ($NEW_APP_COUNT vars total; $COPIED inherited from OLD; report: $PARITY_REPORT; secrets not printed)"

c_green "DETECTION COMPLETE — no placeholders remain. Review deploy.env, then run steps/01_preflight.sh"
