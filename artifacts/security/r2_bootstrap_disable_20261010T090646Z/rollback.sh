#!/bin/bash
# R2-DISABLE rollback — restores pre-disable .env and recreates backend on S2-A image.
set -euo pipefail
BACKUP=/home/raghu/arbicore_backups/r2_bootstrap_disable_20261010T090646Z/backend.env.pre-disable
ENVF=/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env
EXPECTED=sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313
cp -a "$BACKUP" "$ENVF"
chmod 600 "$ENVF"
cd /home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose
docker compose -f docker-compose.prod.yml -f /tmp/arbicore-s2a-rpc-redact-override.yml \
  up -d --no-deps --force-recreate --pull never backend
DIGEST=$(docker inspect arbicore-x-backend-new --format '{{.Image}}')
test "$DIGEST" = "$EXPECTED"
echo "rollback_ok digest=$DIGEST"
