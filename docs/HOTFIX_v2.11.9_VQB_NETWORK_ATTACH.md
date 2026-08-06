# v2.11.9 Hotfix — Backend Network Attachment (`vqb-network`)

## Summary

Root cause of the DNS resolution failure: the backend container was only on
`arbicore-x-net`, but `MONGO_URL` resolves to `factory-mongo`, which lives
on the peer stack's `vqb-network`. Docker DNS is per-network, so cross-network
lookups fail with `Temporary failure in name resolution`.

**Fix:** attach the backend service to `vqb-network` (declared as `external`).
No application code changes. No data migration. No Mongo container touched.
The local `mongo` service in the standalone compose file remains defined so
the file still works on a greenfield host — but on the shared-tenancy VPS the
backend will now resolve `factory-mongo` via Docker DNS.

## Files changed

`deployment/compose/docker-compose.yml`:
- Added `vqb-network` under the top-level `networks:` block as `external: true, name: vqb-network`.
- Added `- vqb-network` to the `backend.networks` list (keeps the existing `- arbicore-x-net` too).

Everything else in the compose file is untouched. `mongo`, `frontend`,
`opportunity_center`, `nginx`, `certbot` stay on `arbicore-x-net` only.

## Preconditions

The peer stack must already have `vqb-network` created on the VPS. Verify:

```bash
docker network inspect vqb-network >/dev/null && echo OK || \
  docker network create --driver bridge vqb-network
```

The create-if-missing form is safe — Docker `network create` is idempotent-ish
(fails if the network exists; the `&& / ||` guard above handles both cases).

## Redeploy commands (run in order on the VPS)

```bash
# 1. Pull the fix from git.
cd /path/to/arbicore-x-repo
git pull

# 2. Sanity-check that vqb-network exists on the host.
docker network inspect vqb-network >/dev/null && echo "vqb-network OK" || \
  docker network create --driver bridge vqb-network

# 3. Sanity-check MONGO_URL points at factory-mongo (frozen canonical DB).
grep MONGO_URL .env

# 4. Recreate ONLY the backend container so it picks up the new network
#    attachment.  --force-recreate is required because Compose's default
#    "no changes" detection does not always spot network-list additions.
docker compose -f deployment/compose/docker-compose.yml up -d \
  --force-recreate --no-deps backend

# 5. Verify the container is attached to BOTH networks.
docker inspect arbicore-x-backend \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
#    Expected output:  arbicore-x-net vqb-network
```

## Verification steps

### 1. DNS lookup from the backend container

```bash
docker exec arbicore-x-backend getent hosts factory-mongo
```

Expected output: an IP address + `factory-mongo`. Anything else (including
empty output) means the network attach failed — see rollback below.

### 2. Live Mongo ping from the backend container

```bash
docker exec arbicore-x-backend python3 -c "
import os, asyncio
from motor.motor_asyncio import AsyncIOMotorClient
async def main():
    c = AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=3000)
    print(await c.admin.command('ping'))
    c.close()
asyncio.run(main())
"
```

Expected output: `{'ok': 1.0, ...}`.

### 3. HTTP smoke through the backend

```bash
docker exec arbicore-x-backend curl -fs http://127.0.0.1:8001/api/ && echo OK
```

### 4. Log check — no more DNS errors

```bash
docker logs --tail 100 arbicore-x-backend 2>&1 | grep -i "name resolution\|factory-mongo" \
  || echo "no DNS errors after fix"
```

### 5. Container health

```bash
docker inspect arbicore-x-backend \
  --format '{{.State.Health.Status}}'
```
Expected: `healthy`.

## Rollback

If step 5 shows anything other than `healthy`, or step 1 fails:

```bash
# Revert the compose change.
git revert HEAD --no-edit

# Recreate the backend without the second network.
docker compose -f deployment/compose/docker-compose.yml up -d \
  --force-recreate --no-deps backend
```

No data is at risk — the Mongo data volume (`factory-mongo` on the peer stack
or `arbicore-x-mongo-data` locally) is not touched by this fix.

## Notes on future topology

- If the operator moves fully to shared-tenancy, deploy
  `deployment/compose/docker-compose.shared.yml` instead of this file — it's
  purpose-built for the co-tenant case (no local Mongo service, attaches only
  to the shared network). The current fix is deliberately conservative:
  keep the standalone file working, add just enough network access to unblock
  the frozen-canonical-DB setup.
- The `mongo` service in the standalone file still starts on shared-tenancy
  hosts but is unused (MONGO_URL points elsewhere). It is safe to leave
  running or scale to zero via `docker compose stop mongo`. Do NOT `docker
  compose down mongo` on hosts where the local `arbicore-x-mongo-data`
  volume holds data you might want later.
