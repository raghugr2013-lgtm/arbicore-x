#!/usr/bin/env bash
# R3-APPLY rollback — restore pre-switch ArbiCore .env and recreate backend only.
# Does not drop arbicore_app (harmless residual) unless operator separately authorises.
set -euo pipefail
BACKUP_ENV="${1:-/home/raghu/arbicore_backups/r3_mongo_leastpriv_20261010T105128Z/backend.env.pre-r3}"
# fallback to create-time backup
if [[ ! -f "$BACKUP_ENV" ]]; then
  BACKUP_ENV=/home/raghu/arbicore_backups/r3_mongo_leastpriv_20261010T102900Z/backend.env.pre-r3
fi
ENVF=/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env
EXPECTED=sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313
test -f "$BACKUP_ENV"
cp -a "$BACKUP_ENV" "$ENVF"
chmod 600 "$ENVF"
cd /home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose
docker compose -f docker-compose.prod.yml -f /tmp/arbicore-s2a-rpc-redact-override.yml \
  up -d --no-deps --force-recreate --pull never backend
test "$(docker inspect arbicore-x-backend-new --format '{{.Image}}')" = "$EXPECTED"
echo "rollback complete; verify username=root and health=healthy manually (do not print URI)"
