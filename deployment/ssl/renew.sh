#!/usr/bin/env bash
# renew.sh — cron-driven certbot renewal + nginx reload.
# Idempotent. Safe to run daily. Cert renewal only happens within 30d of expiry.
#
# Recommended cron (root):
#   17 3 * * * /opt/arbicore-x/deployment/ssl/renew.sh >>/var/log/arbicore-x/certbot-renew.log 2>&1
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

COMPOSE="docker compose"
if ! docker compose version >/dev/null 2>&1; then
  COMPOSE="docker-compose"
fi

cd "${REPO_ROOT}/deployment/compose"

echo "[$(date -u +%FT%TZ)] certbot renew ..."
$COMPOSE run --rm --entrypoint "certbot" certbot \
  renew --webroot -w /var/www/certbot --quiet

echo "[$(date -u +%FT%TZ)] nginx reload ..."
$COMPOSE exec -T nginx nginx -s reload

echo "[$(date -u +%FT%TZ)] renew complete."
