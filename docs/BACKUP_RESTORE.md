# ArbiCore X — BACKUP_RESTORE.md

**Non-destructive by default.** Destructive restore is explicitly documented and gated.

## 1. What gets backed up

- MongoDB database `${DB_NAME}` (default `arbicore_x_prod`) via `mongodump --archive --gzip`.
- Everything: durable collections (opportunities, outcomes, audit, wallet metrics, entities, sequences), operational (scanner_config, scanner_state), and transient (discovery_candidates).
- Backup archive is a single self-contained `.archive.gz` file.

## 2. What does NOT need backup (regenerable)

- Docker images (rebuild from `app/` + `deployment/compose/`)
- Compose stacks (from the bundle)
- TLS certificates (Let's Encrypt re-issues them free)
- Bundle files (from git or the packaged tarball)

## 3. Manual backup (one-off)

```bash
cd /opt/arbicore-x
./deployment/backups/backup.sh
# → writes to ./backups/arbicore-x_YYYYMMDD_HHMMSS.archive.gz
```


- Runs `mongodump --archive --gzip` inside the `arbicore-x-mongo` container.
- Writes to `${BACKUP_DIR:-./backups}`.
- Rotates to keep last 14 daily archives (older ones removed).

## 4. Automated backup (recommended)

Add to root crontab:

```cron
# ArbiCore X — nightly Mongo backup at 03:00 UTC
0 3 * * * root /opt/arbicore-x/deployment/backups/backup-cron.sh >>/var/log/arbicore-x/backup.log 2>&1
```

`backup-cron.sh` wraps `backup.sh` with:

- Retention control via `BACKUP_RETENTION_DAYS` in `.env` (default 14).
- Optional off-host push via `rclone` (set `BACKUP_RCLONE_REMOTE=remote:bucket/path`).
- Timestamped log lines.

## 5. Off-host backup (highly recommended)

On-host backups don't protect you from disk failure. Push each archive off-host:

### 5a. Via `rclone` (S3 / GCS / Backblaze / etc.)

```bash
apt-get install -y rclone
rclone config    # follow the interactive setup for your remote
# Then in .env:
BACKUP_RCLONE_REMOTE=s3remote:arbicore-x/backups/
```

### 5b. Via `scp` cron

```cron
5 3 * * * scp /opt/arbicore-x/backups/arbicore-x_$(date -u +\%Y\%m\%d)*.archive.gz backup@backups.example.com:/vault/arbicore-x/
```

## 6. Testing a backup (do this regularly)

**A backup you have never restored is not a backup.** Test quarterly:

```bash
# Spin up an ephemeral Mongo, restore the archive into it, run a smoke query.
docker run -d --name arbicore-x-restore-test -v /tmp/restore-data:/data/db mongo:4.4
sleep 10
gunzip -c /opt/arbicore-x/backups/arbicore-x_LATEST.archive.gz \
  | docker exec -i arbicore-x-restore-test mongorestore --archive --gzip

docker exec arbicore-x-restore-test mongosh --quiet --eval '
  db = db.getSiblingDB("arbicore_x_prod");
  print("opportunities:", db.arbicore_opportunities.countDocuments());
  print("outcomes:",      db.arbicore_outcomes.countDocuments());
  print("audit:",         db.arbicore_audit_log.countDocuments());
'

# Tear down when done
docker rm -f arbicore-x-restore-test
rm -rf /tmp/restore-data
```

## 7. Restore in production (⚠ DESTRUCTIVE)

**Only for disaster recovery when Mongo data is lost or corrupted.**

```bash
cd /opt/arbicore-x

# 1. Stop the backend (Mongo stays running)
docker compose -f deployment/compose/docker-compose.yml stop backend

# 2. Restore (--drop replaces matching collections; ALL writes since backup are lost)
./deployment/backups/restore.sh /path/to/arbicore-x_YYYYMMDD_HHMMSS.archive.gz
# → prompts [y/N]. Type 'y' after confirming this is what you want.

# 3. Restart the backend
docker compose -f deployment/compose/docker-compose.yml start backend

# 4. Verify
./scripts/healthcheck.sh
```

⚠ The upgrade path (`docs/UPGRADE.md`) does **NOT** use this script. `docs/ROLLBACK.md` §1 shows the non-destructive rollback.

## 8. Retention policy (recommended)

| Tier | Location | Retention | Purpose |
|---|---|---|---|
| Hot | `${BACKUP_DIR}` on VPS | 14 days rolling | Instant restore |
| Warm | Off-host bucket (rclone) | 30 days rolling | Disk-failure recovery |
| Cold | Off-host bucket (rclone monthly copy) | 12 months | Long-term compliance |

Configure warm + cold at the object-storage layer (S3 lifecycle rules, GCS retention).

## 9. Encryption at rest (recommended for hot + warm)

The archive is gzip-compressed but **not encrypted**. For sensitive deployments:

```bash
# Encrypt each archive with age (https://age-encryption.org)
apt-get install -y age
age -R /etc/arbicore-x/backup-recipients.txt \
    -o backup.archive.gz.age \
    < backup.archive.gz
rm backup.archive.gz   # only after successful encryption
```

Store the `age` key off-host (never on the VPS itself).

## 10. Reference

- `deployment/backups/backup.sh`, `backup-cron.sh`, `restore.sh`
