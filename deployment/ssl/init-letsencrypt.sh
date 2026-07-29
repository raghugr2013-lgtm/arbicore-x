#!/usr/bin/env bash
# init-letsencrypt.sh — issue first certificate for ${DOMAIN}.
# Runs in TWO phases:
#   1) Nginx up on :80 only (HTTP), certbot HTTP-01 challenge succeeds.
#   2) Real cert written; caller reloads nginx to serve :443.
# By default this uses --staging (rate-limit-safe test certs). Flip to --production
# once the staging issue-and-serve loop is green.
#
# Usage:
#   LETSENCRYPT_MODE=staging ./init-letsencrypt.sh          # first, always
#   LETSENCRYPT_MODE=prod    ./init-letsencrypt.sh          # after staging OK
#
# Reads: DOMAIN, LETSENCRYPT_EMAIL, LETSENCRYPT_MODE from the environment (or .env).
# Never touches Mongo. Idempotent.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

: "${DOMAIN:?DOMAIN must be set (in .env or shell)}"
: "${LETSENCRYPT_EMAIL:?LETSENCRYPT_EMAIL must be set}"
: "${LETSENCRYPT_MODE:=staging}"

MODE_FLAG=""
if [ "$LETSENCRYPT_MODE" = "staging" ]; then
  MODE_FLAG="--staging"
  echo "[init-letsencrypt] MODE=staging (test certs, rate-limit safe). Flip to prod when green."
else
  MODE_FLAG=""
  echo "[init-letsencrypt] MODE=prod (real certs). Rate limits apply — do not loop."
fi

COMPOSE="docker compose"
if ! docker compose version >/dev/null 2>&1; then
  COMPOSE="docker-compose"
fi

cd "${REPO_ROOT}/deployment/compose"

echo "[init-letsencrypt] issuing cert for ${DOMAIN} via HTTP-01 (webroot)..."
$COMPOSE run --rm --entrypoint "certbot" certbot \
  certonly --webroot -w /var/www/certbot \
  ${MODE_FLAG} \
  -d "${DOMAIN}" \
  --email "${LETSENCRYPT_EMAIL}" \
  --rsa-key-size 4096 \
  --agree-tos \
  --no-eff-email \
  --non-interactive \
  || { echo "[init-letsencrypt] FAIL — see certbot output above" >&2; exit 1; }

echo "[init-letsencrypt] cert issued. Reload nginx to activate TLS:"
echo "    $COMPOSE exec nginx nginx -s reload"
