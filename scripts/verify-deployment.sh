#!/usr/bin/env bash
# =============================================================================
#  ArbiCore X — Deployment Verification Script
#  File: scripts/verify-deployment.sh
# =============================================================================
#
#  Purpose
#  -------
#  Post-deployment sanity harness. Runs the 8-category verification matrix
#  agreed as the standard release checklist. Run this after EVERY
#  production deployment or upgrade (greenfield or shared-infrastructure).
#
#  The script is idempotent, read-only against the deployment, and never
#  mutates state. All work happens over docker exec + curl.
#
#  8-category coverage
#  -------------------
#   [1] Backend health          - /api/ returns 200 + JSON
#   [2] Frontend HTTP 200       - operator UI SPA reachable
#   [3] Opportunity Center HTTP - analytics SPA reachable
#   [4] Bundle verification     - configured URL baked in, no `void 0`
#   [5] Browser runtime         - login page renders, no JS exceptions
#   [6] API connectivity        - frontend can reach /api/auth/status
#   [7] Successful login        - POST /api/auth/login returns a session
#   [8] Dashboard render        - authenticated Dashboard mounts cleanly
#
#  Categories 5 and 8 require a headless browser. The script auto-detects
#  Playwright (via `scripts/verify-browser.mjs`) and runs those checks
#  transparently. If Playwright is unavailable, they are marked SKIP with
#  a copy-pasteable manual verification step.
#
#  Usage
#  -----
#    scripts/verify-deployment.sh \
#        --domain https://arbicore.example.com \
#        --profile shared \
#        --admin-user admin \
#        --admin-pass 's3cr3t'
#
#    scripts/verify-deployment.sh --help
#
#  Exit codes
#  ----------
#    0   all checks PASS (SKIP is not a failure)
#    1   one or more checks FAIL
#    2   invalid arguments / preflight failure
# =============================================================================

set -o errexit
set -o pipefail
set -o nounset

# ------------------------------------------------------------ ANSI colors
if [[ -t 1 ]]; then
  C_RED=$'\e[31m'; C_GREEN=$'\e[32m'; C_YELLOW=$'\e[33m'
  C_BLUE=$'\e[34m'; C_BOLD=$'\e[1m'; C_DIM=$'\e[2m'; C_RESET=$'\e[0m'
else
  C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_DIM=""; C_RESET=""
fi

# ------------------------------------------------------------ Result counters
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
FAILED_CHECKS=()

# ------------------------------------------------------------ Defaults
DOMAIN=""
PROFILE=""
ADMIN_USER=""
ADMIN_PASS=""
SKIP_BROWSER=0
BACKEND_CONTAINER=""
FRONTEND_CONTAINER=""
OC_CONTAINER=""
COMPOSE_FILE=""
ENV_FILE=""
JSON_OUT=""

# ------------------------------------------------------------ Helpers
usage() {
  cat <<EOF
${C_BOLD}ArbiCore X — Deployment Verification${C_RESET}

Usage:
  $(basename "$0") --domain <URL> --profile <shared|greenfield>
                   [--admin-user <user>] [--admin-pass <pass>]
                   [--backend-container <name>] [--frontend-container <name>]
                   [--oc-container <name>] [--skip-browser] [--json <file>]

Required:
  --domain URL          Public URL of the deployment (e.g. https://arbicore.example.com).
                        Must include protocol. No trailing slash.
  --profile P           "shared" or "greenfield".

Optional:
  --admin-user U        Admin username for auth verification (cat. 7 + 8).
                        If omitted, those checks are SKIP.
  --admin-pass P        Admin password. May also be supplied via
                        \$ARBICORE_ADMIN_PASS env var.
  --backend-container   Override backend container name.
                        Defaults: shared -> \$BACKEND_CONTAINER_NAME from
                        .env.shared, greenfield -> arbicore-x-backend.
  --frontend-container  Override frontend container name.
                        Defaults: arbicore-x-frontend.
  --oc-container        Override Opportunity Center container name.
                        Defaults: arbicore-x-opportunity-center.
  --skip-browser        Skip categories 5 and 8 (mark as SKIP).
  --json PATH           Also write machine-readable results to PATH.
  -h, --help            This message.

Environment fallbacks:
  ARBICORE_ADMIN_PASS   Alternative to --admin-pass (recommended for CI).

Exit codes:
  0  all checks PASS
  1  one or more checks FAIL (SKIP does NOT fail the run)
  2  invalid arguments / preflight failure

Examples:
  # Shared-profile deploy, full 8-category check:
  $(basename "$0") --domain https://arbicore.example.com \\
                   --profile shared \\
                   --admin-user admin \\
                   --admin-pass "\$ADMIN_PASS"

  # Skip browser (fast, CI without Playwright):
  $(basename "$0") --domain https://arbicore.example.com \\
                   --profile shared --skip-browser
EOF
}

die() { echo "${C_RED}error:${C_RESET} $*" >&2; exit 2; }

section() {
  echo
  echo "${C_BOLD}${C_BLUE}━━━ $* ━━━${C_RESET}"
}

pass() {
  echo "  ${C_GREEN}✓${C_RESET} $*"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "  ${C_RED}✗ $*${C_RESET}"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILED_CHECKS+=("$*")
}

skip() {
  echo "  ${C_YELLOW}○ SKIP${C_RESET} $*"
  SKIP_COUNT=$((SKIP_COUNT + 1))
}

info() { echo "  ${C_DIM}$*${C_RESET}"; }

# ------------------------------------------------------------ Arg parsing
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --admin-user) ADMIN_USER="$2"; shift 2 ;;
    --admin-pass) ADMIN_PASS="$2"; shift 2 ;;
    --backend-container) BACKEND_CONTAINER="$2"; shift 2 ;;
    --frontend-container) FRONTEND_CONTAINER="$2"; shift 2 ;;
    --oc-container) OC_CONTAINER="$2"; shift 2 ;;
    --skip-browser) SKIP_BROWSER=1; shift ;;
    --json) JSON_OUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

# ------------------------------------------------------------ Preflight
[[ -n "$DOMAIN"  ]] || die "--domain is required"
[[ -n "$PROFILE" ]] || die "--profile is required (shared|greenfield)"
[[ "$PROFILE" == "shared" || "$PROFILE" == "greenfield" ]] \
  || die "--profile must be 'shared' or 'greenfield', got: $PROFILE"

# Strip any trailing slash from --domain (bundles bake without it)
DOMAIN="${DOMAIN%/}"

# Prefer env-var admin pass if flag not given
ADMIN_PASS="${ADMIN_PASS:-${ARBICORE_ADMIN_PASS:-}}"

# Resolve compose file + env file from profile
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_DIR="$REPO_ROOT/deployment/compose"

if [[ "$PROFILE" == "shared" ]]; then
  COMPOSE_FILE="$COMPOSE_DIR/docker-compose.shared.yml"
  ENV_FILE="$COMPOSE_DIR/.env.shared"
else
  COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml"
  ENV_FILE="$REPO_ROOT/.env"
fi

# Container names (with env-file fallbacks for shared profile)
if [[ -z "$BACKEND_CONTAINER" ]]; then
  if [[ "$PROFILE" == "shared" && -f "$ENV_FILE" ]]; then
    BACKEND_CONTAINER="$(grep -E '^BACKEND_CONTAINER_NAME=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)"
  fi
  BACKEND_CONTAINER="${BACKEND_CONTAINER:-arbicore-x-backend}"
fi
if [[ -z "$FRONTEND_CONTAINER" ]]; then
  if [[ "$PROFILE" == "shared" && -f "$ENV_FILE" ]]; then
    FRONTEND_CONTAINER="$(grep -E '^FRONTEND_CONTAINER_NAME=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)"
  fi
  FRONTEND_CONTAINER="${FRONTEND_CONTAINER:-arbicore-x-frontend}"
fi
if [[ -z "$OC_CONTAINER" ]]; then
  if [[ "$PROFILE" == "shared" && -f "$ENV_FILE" ]]; then
    OC_CONTAINER="$(grep -E '^OPPORTUNITY_CENTER_CONTAINER_NAME=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)"
  fi
  OC_CONTAINER="${OC_CONTAINER:-arbicore-x-opportunity-center}"
fi

# Tool preflight
command -v curl >/dev/null 2>&1 || die "curl is required"
command -v docker >/dev/null 2>&1 || die "docker is required"

# ------------------------------------------------------------ Banner
cat <<EOF

${C_BOLD}ArbiCore X — Deployment Verification${C_RESET}
${C_DIM}$(date -Iseconds)${C_RESET}

  Domain:              ${C_BOLD}$DOMAIN${C_RESET}
  Profile:             $PROFILE
  Backend container:   $BACKEND_CONTAINER
  Frontend container:  $FRONTEND_CONTAINER
  OC container:        $OC_CONTAINER
  Admin auth checks:   $([[ -n "$ADMIN_USER" && -n "$ADMIN_PASS" ]] && echo "enabled" || echo "SKIP (no --admin-user/--admin-pass)")
  Browser checks:      $([[ $SKIP_BROWSER -eq 1 ]] && echo "SKIP (--skip-browser)" || echo "auto-detect Playwright")
EOF

# =============================================================================
#  [1] Backend health
# =============================================================================
section "[1/8] Backend health"

# Check container exists + running
if docker inspect --format '{{.State.Running}}' "$BACKEND_CONTAINER" 2>/dev/null | grep -q true; then
  pass "container $BACKEND_CONTAINER is running"
else
  fail "container $BACKEND_CONTAINER is NOT running (or does not exist)"
fi

# Check docker healthcheck status
HC_STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$BACKEND_CONTAINER" 2>/dev/null || echo missing)"
if [[ "$HC_STATUS" == "healthy" ]]; then
  pass "docker healthcheck status = healthy"
elif [[ "$HC_STATUS" == "none" ]]; then
  info "no docker healthcheck configured — skipping container-level probe"
else
  fail "docker healthcheck status = $HC_STATUS (expected: healthy)"
fi

# Probe /api/ from inside the container (avoids reverse-proxy misconfig noise)
if docker exec "$BACKEND_CONTAINER" curl -fsS --max-time 5 http://127.0.0.1:8001/api/ >/tmp/verify_api_root.txt 2>&1; then
  pass "GET http://127.0.0.1:8001/api/ inside container -> 200"
  info "response: $(tr -d '\n' </tmp/verify_api_root.txt | head -c 120)"
else
  fail "GET /api/ inside backend container failed"
fi

# Probe /api/ via the public domain (validates reverse-proxy path)
API_ROOT_HTTP="$(curl -sS -o /tmp/verify_api_public.txt -w '%{http_code}' --max-time 10 "$DOMAIN/api/" || echo 000)"
if [[ "$API_ROOT_HTTP" == "200" ]]; then
  pass "GET $DOMAIN/api/ -> 200 (reverse proxy reaches backend)"
else
  fail "GET $DOMAIN/api/ -> $API_ROOT_HTTP (expected 200)"
  info "body: $(tr -d '\n' </tmp/verify_api_public.txt | head -c 200)"
fi

# =============================================================================
#  [2] Frontend HTTP 200
# =============================================================================
section "[2/8] Frontend HTTP 200 (operator UI)"

FE_HTTP="$(curl -sS -o /tmp/verify_fe_index.html -w '%{http_code}' --max-time 10 "$DOMAIN/" || echo 000)"
if [[ "$FE_HTTP" == "200" ]]; then
  pass "GET $DOMAIN/ -> 200"
else
  fail "GET $DOMAIN/ -> $FE_HTTP (expected 200)"
fi

# Confirm the response looks like an SPA index (has <div id="root">)
if grep -q '<div id="root"' /tmp/verify_fe_index.html 2>/dev/null; then
  pass "response contains <div id=\"root\"> (SPA shell rendered)"
else
  fail "response does NOT contain <div id=\"root\"> — is this the ArbiCore SPA?"
fi

# Check that the response references at least one hashed JS bundle
JS_BUNDLE_PATH="$(grep -oE '/static/js/main\.[a-f0-9]+\.js' /tmp/verify_fe_index.html | head -n1 || true)"
if [[ -n "$JS_BUNDLE_PATH" ]]; then
  pass "index.html references JS bundle: $JS_BUNDLE_PATH"
else
  fail "index.html does not reference a /static/js/main.*.js bundle"
fi

# =============================================================================
#  [3] Opportunity Center HTTP 200
# =============================================================================
section "[3/8] Opportunity Center HTTP 200 (analytics SPA)"

# The OC is typically mounted at /opportunity-center/. We probe both root
# variants — different reverse-proxy layouts route differently.
OC_HTTP_A="$(curl -sS -o /tmp/verify_oc_a.html -w '%{http_code}' --max-time 10 "$DOMAIN/opportunity-center/" || echo 000)"
OC_HTTP_B="$(curl -sS -o /tmp/verify_oc_b.html -w '%{http_code}' --max-time 10 "$DOMAIN/opportunity-center" || echo 000)"

if [[ "$OC_HTTP_A" == "200" ]]; then
  pass "GET $DOMAIN/opportunity-center/ -> 200"
elif [[ "$OC_HTTP_B" == "200" ]]; then
  pass "GET $DOMAIN/opportunity-center  -> 200"
else
  # Fall back to healthz on the container directly
  if docker exec "$OC_CONTAINER" wget -qO- --timeout=5 http://127.0.0.1/healthz >/dev/null 2>&1; then
    pass "container /healthz probe -> OK (public route may not be exposed on this profile)"
    info "public path returned: $OC_HTTP_A (with slash), $OC_HTTP_B (no slash)"
  else
    fail "Opportunity Center unreachable via public route AND container healthz"
    info "$DOMAIN/opportunity-center/ -> $OC_HTTP_A; $DOMAIN/opportunity-center -> $OC_HTTP_B"
  fi
fi

# =============================================================================
#  [4] Bundle verification (configured URL baked in, zero `void 0`)
#      This is the CORE guard against the v1.0.1 black-screen bug.
# =============================================================================
section "[4/8] Bundle verification (v1.0.1 black-screen regression guard)"

# Locate the compiled main.*.js inside the frontend container
BUNDLE_PATH="$(docker exec "$FRONTEND_CONTAINER" sh -c \
  'ls /usr/share/nginx/html/static/js/main.*.js 2>/dev/null | head -n1' \
  2>/dev/null || true)"

if [[ -z "$BUNDLE_PATH" ]]; then
  fail "could not locate /usr/share/nginx/html/static/js/main.*.js inside $FRONTEND_CONTAINER"
else
  info "bundle: $BUNDLE_PATH"

  # 4a) Zero occurrences of `"".concat(void 0,"/api")` or `undefined/api`
  UNDEF_COUNT="$(docker exec "$FRONTEND_CONTAINER" sh -c \
    "grep -cE '\"\".concat\\(void 0,\"/api\"\\)|undefined/api' $BUNDLE_PATH" 2>/dev/null || echo -1)"
  if [[ "$UNDEF_COUNT" == "0" ]]; then
    pass "compiled bundle contains zero \`void 0\` / \`undefined/api\` refs"
  else
    fail "compiled bundle contains $UNDEF_COUNT undefined-API refs (v1.0.1 black-screen bug is present)"
    info "REACT_APP_BACKEND_URL was NOT baked at build time. Rebuild with --no-cache."
  fi

  # 4b) Configured backend URL is present in the bundle
  # Strip protocol to make the match tolerant of trailing chars in minified JS
  DOMAIN_HOST="${DOMAIN#https://}"
  DOMAIN_HOST="${DOMAIN_HOST#http://}"
  URL_MATCH_COUNT="$(docker exec "$FRONTEND_CONTAINER" sh -c \
    "grep -c '$DOMAIN_HOST' $BUNDLE_PATH" 2>/dev/null || echo 0)"
  if [[ "$URL_MATCH_COUNT" -gt 0 ]]; then
    pass "compiled bundle contains configured domain '$DOMAIN_HOST' ($URL_MATCH_COUNT refs)"
  else
    fail "compiled bundle does NOT reference configured domain '$DOMAIN_HOST'"
    info "The bundle was likely built with a different REACT_APP_BACKEND_URL."
    info "Sample baked URL from bundle:"
    docker exec "$FRONTEND_CONTAINER" sh -c \
      "grep -oE '\"https?://[^\"]{5,80}\",\"/api\"' $BUNDLE_PATH | sort -u | head -3" 2>/dev/null \
      | sed 's/^/      /' || true
  fi
fi

# =============================================================================
#  [5] Browser runtime (login page renders, no uncaught JS exceptions)
# =============================================================================
section "[5/8] Browser runtime (login renders, no JS exceptions)"

BROWSER_SCRIPT="$SCRIPT_DIR/verify-browser.mjs"

if [[ $SKIP_BROWSER -eq 1 ]]; then
  skip "browser checks disabled via --skip-browser"
  skip "dashboard render will also be skipped (requires browser)"
elif ! command -v node >/dev/null 2>&1; then
  skip "node not installed — cannot run headless browser checks"
  info "manual check: open $DOMAIN/ in a browser, open DevTools console,"
  info "  confirm Login page renders and console has no red errors."
elif [[ ! -f "$BROWSER_SCRIPT" ]]; then
  skip "$BROWSER_SCRIPT not found — cannot run headless browser checks"
else
  # Delegate to the Node/Playwright helper. It writes /tmp/verify_browser.json.
  BROWSER_ARGS=(
    --domain "$DOMAIN"
    --out /tmp/verify_browser.json
  )
  if [[ -n "$ADMIN_USER" && -n "$ADMIN_PASS" ]]; then
    BROWSER_ARGS+=(--admin-user "$ADMIN_USER" --admin-pass "$ADMIN_PASS")
  fi

  if node "$BROWSER_SCRIPT" "${BROWSER_ARGS[@]}" 2>/tmp/verify_browser.stderr; then
    # Parse JSON result
    if command -v jq >/dev/null 2>&1; then
      LOGIN_RENDERED="$(jq -r '.login_page_rendered' /tmp/verify_browser.json 2>/dev/null || echo unknown)"
      JS_EXCEPTIONS="$(jq -r '.js_exceptions | length' /tmp/verify_browser.json 2>/dev/null || echo unknown)"
      DASHBOARD_MOUNTED="$(jq -r '.dashboard_mounted' /tmp/verify_browser.json 2>/dev/null || echo unknown)"
    else
      LOGIN_RENDERED="$(grep -o '"login_page_rendered":[^,}]*' /tmp/verify_browser.json 2>/dev/null | cut -d: -f2 | tr -d ' ')"
      JS_EXCEPTIONS="$(grep -oE '"js_exceptions":\[[^]]*\]' /tmp/verify_browser.json 2>/dev/null | grep -oE '"[^"]+"' | wc -l)"
      JS_EXCEPTIONS=$((JS_EXCEPTIONS / 2))  # rough count of entries
      DASHBOARD_MOUNTED="$(grep -o '"dashboard_mounted":[^,}]*' /tmp/verify_browser.json 2>/dev/null | cut -d: -f2 | tr -d ' ')"
    fi

    if [[ "$LOGIN_RENDERED" == "true" ]]; then
      pass "login page rendered (data-testid=\"login-form\" visible)"
    else
      fail "login page did NOT render — black screen or DOM tree is empty"
    fi

    if [[ "$JS_EXCEPTIONS" == "0" ]]; then
      pass "zero uncaught JavaScript exceptions during initial load"
    else
      fail "$JS_EXCEPTIONS uncaught JavaScript exception(s) during initial load"
      info "see /tmp/verify_browser.json for stack traces"
    fi

    # Category 8 result piggybacks on the same browser run
    CAT8_LOGIN_OK="$(command -v jq >/dev/null 2>&1 \
      && jq -r '.login_succeeded' /tmp/verify_browser.json 2>/dev/null \
      || grep -o '"login_succeeded":[^,}]*' /tmp/verify_browser.json 2>/dev/null | cut -d: -f2 | tr -d ' ')"
  else
    fail "browser verification helper failed to run"
    info "stderr: $(head -c 300 /tmp/verify_browser.stderr 2>/dev/null || echo '(empty)')"
    info "hint: install Playwright with:"
    info "        npm install --prefix $REPO_ROOT/scripts playwright && \\"
    info "        npx --prefix $REPO_ROOT/scripts playwright install chromium"
    LOGIN_RENDERED="unknown"
    DASHBOARD_MOUNTED="unknown"
    CAT8_LOGIN_OK="unknown"
  fi
fi

# =============================================================================
#  [6] API connectivity (frontend can reach /api/auth/status)
# =============================================================================
section "[6/8] API connectivity ( /api/auth/status through public origin )"

STATUS_RES="$(curl -sS --max-time 10 -w '\n%{http_code}\n%{content_type}' \
  "$DOMAIN/api/auth/status" 2>&1 || true)"
STATUS_BODY="$(echo "$STATUS_RES" | head -n -2)"
STATUS_HTTP="$(echo "$STATUS_RES" | tail -n2 | head -n1)"
STATUS_CT="$(echo "$STATUS_RES"   | tail -n1)"

if [[ "$STATUS_HTTP" == "200" ]]; then
  if echo "$STATUS_CT" | grep -qi 'application/json'; then
    pass "GET $DOMAIN/api/auth/status -> 200 application/json"
    info "body: $(echo "$STATUS_BODY" | head -c 200)"
  else
    fail "GET /api/auth/status -> 200 but Content-Type is '$STATUS_CT' (expected JSON)"
    info "This is the exact fingerprint of the v1.0.1 black-screen bug:"
    info "nginx SPA fallback is serving index.html for API routes."
  fi
else
  fail "GET $DOMAIN/api/auth/status -> $STATUS_HTTP (expected 200)"
fi

# =============================================================================
#  [7] Successful login validation (API-level, no browser required)
# =============================================================================
section "[7/8] Successful login (POST /api/auth/login)"

if [[ -z "$ADMIN_USER" || -z "$ADMIN_PASS" ]]; then
  skip "no --admin-user / --admin-pass provided"
  info "to enable: --admin-user admin --admin-pass 'YOUR_PASS'"
  info "or:        ARBICORE_ADMIN_PASS='YOUR_PASS' $(basename "$0") ..."
else
  LOGIN_JSON=$(printf '{"username":"%s","password":"%s"}' \
    "${ADMIN_USER//\"/\\\"}" "${ADMIN_PASS//\"/\\\"}")

  LOGIN_RES="$(curl -sS --max-time 15 \
    -H 'Content-Type: application/json' \
    -c /tmp/verify_cookies.txt \
    -o /tmp/verify_login_body.json \
    -w '%{http_code}' \
    -X POST -d "$LOGIN_JSON" \
    "$DOMAIN/api/auth/login" || echo 000)"

  if [[ "$LOGIN_RES" == "200" ]]; then
    pass "POST /api/auth/login -> 200 for user '$ADMIN_USER'"

    # Verify session cookie or token was issued
    if grep -qE '(session|access_token|arbicore)' /tmp/verify_cookies.txt 2>/dev/null; then
      pass "session cookie issued"
    elif grep -qE '"(access_token|token|session)"' /tmp/verify_login_body.json 2>/dev/null; then
      pass "auth token returned in body"
    else
      fail "login returned 200 but no session cookie or token found"
    fi

    # Verify /api/auth/me now identifies us
    ME_RES="$(curl -sS --max-time 10 -b /tmp/verify_cookies.txt \
      -o /tmp/verify_me.json -w '%{http_code}' \
      "$DOMAIN/api/auth/me" || echo 000)"
    if [[ "$ME_RES" == "200" ]] && grep -q "$ADMIN_USER" /tmp/verify_me.json 2>/dev/null; then
      pass "GET /api/auth/me -> 200 identifies '$ADMIN_USER'"
    else
      fail "GET /api/auth/me after login -> $ME_RES (session not honoured)"
    fi
  else
    fail "POST /api/auth/login -> $LOGIN_RES for user '$ADMIN_USER'"
    info "body: $(head -c 200 /tmp/verify_login_body.json 2>/dev/null)"
  fi
fi

# =============================================================================
#  [8] Dashboard render validation (authenticated navigation to /)
# =============================================================================
section "[8/8] Dashboard render (authenticated)"

if [[ $SKIP_BROWSER -eq 1 ]]; then
  skip "browser checks disabled via --skip-browser"
elif ! command -v node >/dev/null 2>&1 || [[ ! -f "$BROWSER_SCRIPT" ]]; then
  skip "headless browser unavailable"
  info "manual check: sign in and confirm the Terminal dashboard mounts with"
  info "  data-testid='patient-dashboard' or the header 'TERMINAL' visible."
elif [[ -z "$ADMIN_USER" || -z "$ADMIN_PASS" ]]; then
  skip "no admin credentials — cannot perform authenticated navigation"
else
  # Reuse the browser run from category 5 (it already logged in + navigated)
  case "${CAT8_LOGIN_OK:-unknown}" in
    true)
      pass "authenticated navigation succeeded, dashboard mounted"
      ;;
    false)
      fail "authenticated navigation failed — dashboard did not mount"
      info "see /tmp/verify_browser.json for details"
      ;;
    *)
      skip "browser run did not report dashboard state"
      ;;
  esac
fi

# =============================================================================
#  Summary
# =============================================================================
echo
echo "${C_BOLD}━━━ Summary ━━━${C_RESET}"
printf "  ${C_GREEN}PASS${C_RESET}   %d\n" "$PASS_COUNT"
printf "  ${C_RED}FAIL${C_RESET}   %d\n" "$FAIL_COUNT"
printf "  ${C_YELLOW}SKIP${C_RESET}   %d\n" "$SKIP_COUNT"

if [[ -n "$JSON_OUT" ]]; then
  {
    echo "{"
    echo "  \"timestamp\": \"$(date -Iseconds)\","
    echo "  \"domain\": \"$DOMAIN\","
    echo "  \"profile\": \"$PROFILE\","
    echo "  \"pass\": $PASS_COUNT,"
    echo "  \"fail\": $FAIL_COUNT,"
    echo "  \"skip\": $SKIP_COUNT,"
    echo -n "  \"failed_checks\": ["
    if [[ ${#FAILED_CHECKS[@]} -gt 0 ]]; then
      first=1
      for c in "${FAILED_CHECKS[@]}"; do
        [[ $first -eq 1 ]] || echo -n ","
        first=0
        printf '\n    "%s"' "$(echo "$c" | sed 's/"/\\"/g')"
      done
      echo
      echo "  ]"
    else
      echo "]"
    fi
    echo "}"
  } > "$JSON_OUT"
  info "wrote machine-readable results to $JSON_OUT"
fi

if [[ $FAIL_COUNT -gt 0 ]]; then
  echo
  echo "${C_RED}${C_BOLD}FAILED${C_RESET} — $FAIL_COUNT check(s) did not pass."
  exit 1
fi

echo
echo "${C_GREEN}${C_BOLD}ALL GREEN${C_RESET} — deployment verified."
exit 0
