#!/usr/bin/env bash
# R4-APPLY rollback — restore pre-r4 .env and recreate backend.
# If change-password already applied, also restore users admin doc from escrow
#   (BK/users_admin_doc.pre-r4.json) via authorised mongosh — not automated here.
set -euo pipefail
BK="/home/raghu/arbicore_backups/r4_admin_jwt_20261010T110918Z"
BACKUP_ENV="${1:-$BK/backend.env.pre-r4}"
ENVF="/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env"
EXPECTED="sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313"
test -f "$BACKUP_ENV"
cp -a "$BACKUP_ENV" "$ENVF"
chmod 600 "$ENVF"
cd "/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose"
docker compose -f docker-compose.prod.yml -f /tmp/arbicore-s2a-rpc-redact-override.yml \
  up -d --no-deps --force-recreate --pull never backend
test "$(docker inspect arbicore-x-backend-new --format '{{.Image}}')" = "$EXPECTED"
echo "env rollback complete; if password was changed, restore users hash from $BK/users_admin_doc.pre-r4.json"
