# ArbiCore X — ROLLBACK.md

Rollback playbook. Applies to **both** deployment paths.

---

## 1. Backend realignment (upgrade) rollback

The single, safe, non-destructive rollback:

```bash
cd /opt/arbicore-x/deployment/upgrade
make rollback         # runs 99_rollback.sh
```

What it does:

1. `docker compose -f compose/docker-compose.prod.yml down` — stops the NEW backend.
2. `docker start $BACKEND_OLD` — restarts the preserved OLD container.
3. Waits ≤ 60 s for `/api/` to return 200 on the OLD backend.

**Guarantees:**

- MongoDB is never touched. All 320 opportunities + history + audit + outcomes are intact.
- The NEW build's seeded `arbicore_scanner_config` / `arbicore_scanner_state` documents remain in Mongo but are harmless to the OLD build (it ignores them and uses in-code defaults).
- Recovery time: < 30 s from `make rollback` to OLD serving traffic.

**Do NOT do** any of the following as part of a functional rollback:

- ❌ `docker rm $BACKEND_OLD` (destroys the rollback anchor)
- ❌ `mongorestore --archive --gzip --drop` (destroys production data — only for the corruption scenario in §3 below)
- ❌ Delete Mongo volume `arbicore-x-mongo-data`
- ❌ Delete the pre-cutover backup at `${BACKUP_DIR}/preupgrade_*.archive.gz`

## 2. Auto-rollback (already-configured)

Two automatic rollback paths in the realignment toolkit — no operator action needed for these:

| Trigger | Script | When |
|---|---|---|
| Cutover error trap | `06_cutover.sh` (ERR trap) | Any command between "stop OLD" and "NEW `/api/arbicore/*` visible" fails |
| Canary threshold | `09_canary_probe.sh` | 3 consecutive probe failures OR > 20 % failure rate in a 60 s window |

Both invoke the same `99_rollback.sh` internally.

## 3. Full Mongo restore (LAST RESORT — DESTRUCTIVE)

**Do this only if Mongo data is corrupted or lost.** All writes since the backup are lost.

```bash
cd /opt/arbicore-x

# STOP the backend first
docker compose -f deployment/compose/docker-compose.yml stop backend

# Restore from the pre-cutover archive
LATEST=$(ls -1t backups/arbicore-x_*.archive.gz | head -1)
gunzip -c "$LATEST" | docker exec -i arbicore-x-mongo mongorestore --archive --gzip --drop

# Restart backend
docker compose -f deployment/compose/docker-compose.yml start backend
```

Warnings:

- `--drop` deletes ALL matching collections before restore. All data since the archive timestamp is gone.
- This is different from the realignment rollback (§1) which preserves Mongo.
- Requires the `arbicore-x-mongo` container to be present. If Mongo itself is gone, first `docker compose up -d mongo` and wait healthy.

## 4. Greenfield install rollback (fresh install failed)

If `scripts/install.sh` fails mid-way and you want to undo everything:

```bash
cd /opt/arbicore-x/deployment/compose

# Bring everything down
docker compose down

# ⚠ DESTRUCTIVE: this removes the Mongo volume too. Only do this if you're sure
# there's no data worth keeping (typical for a failed first install).
docker volume rm arbicore-x-mongo-data arbicore-x-logs \
                 arbicore-x-certbot-etc arbicore-x-certbot-www

# Remove images if you want a completely clean slate
docker image rm arbicore-x-backend:0.1.0 arbicore-x-frontend:0.1.0 arbicore-x-opportunity-center:0.1.0
```

Now `scripts/install.sh` will pass the "refuse-if-exists" guard and can be re-run.

## 5. Post-rollback verification

Regardless of path, always verify after any rollback:

```bash
./scripts/healthcheck.sh
```

Expected: GREEN. If not:

1. `docker ps -a` — any container in `Restarting` or `Exited`?
2. `docker compose logs --tail=100 <service>` — errors?
3. Check `docs/TROUBLESHOOTING.md` for the specific failure mode.

## 6. Reference

- `deployment/upgrade/steps/99_rollback.sh` — the actual rollback script (SHA-locked)
