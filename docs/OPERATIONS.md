# ArbiCore X — OPERATIONS.md

Daily / weekly / monthly runbook. Copy-pasteable commands.

## Daily (≤ 2 min)

### 1. Health probe

```bash
cd /opt/arbicore-x && ./scripts/healthcheck.sh
```

Expect: `Summary: N OK / 0 FAIL`. If any FAIL → `docs/TROUBLESHOOTING.md`.

### 2. Snapshot (observability)

```bash
./deployment/monitoring/snapshot.sh
# → writes evidence/snapshot_YYYYMMDDTHHMMSSZ.json
```

Records collection counts + scanner state + last 10 outcomes. Diff two snapshots to see drift over time.

### 3. Log spot-check

```bash
docker compose -f deployment/compose/docker-compose.yml logs --tail=200 backend \
  | grep -E "ERROR|Traceback|last_error" | head -20
```

## Weekly (5–10 min)

### 4. Confirm backup succeeded

```bash
ls -lh /opt/arbicore-x/backups/ | tail -10
# The most recent file should be < 24 h old and non-trivial in size.
```

Also check `/var/log/arbicore-x/backup.log` for cron output.

### 5. Check TLS cert expiry

```bash
DOMAIN_VAL=$(grep '^DOMAIN=' /opt/arbicore-x/.env | cut -d= -f2)
echo | openssl s_client -servername "$DOMAIN_VAL" -connect "${DOMAIN_VAL}:443" 2>/dev/null \
  | openssl x509 -noout -enddate
```

Should be > 30 days out. If < 14 days, `renew.sh` cron may have failed — investigate.

### 6. Docker resource review

```bash
docker stats --no-stream
# Watch for containers hitting their resource limit (2 GB backend / 2 GB mongo).
```

### 7. Disk

```bash
df -h /opt/arbicore-x
docker system df
```

If Mongo volume + logs volume + backup dir together exceed 70 % of disk, plan rotation:

- Older backups: rotate to off-host via `rclone` (already automated if `BACKUP_RCLONE_REMOTE` is set)
- Logs: `logrotate` is applied by Docker's `json-file` driver (max 500 MB/service)
- Mongo: consider trimming `arbicore_discovery_candidates` (see UPGRADE.md §3 opt-in cleanup)

## Monthly (15–20 min)

### 8. Restore test (never skip this)

Once a quarter minimum — see `docs/BACKUP_RESTORE.md §6`. If you have never restored a backup, you have no backup.

### 9. Base image refresh

```bash
cd /opt/arbicore-x/deployment/compose
docker compose pull mongo certbot
docker compose build --no-cache backend frontend opportunity_center
```

Then use the realignment path (`docs/UPGRADE.md`) to swap only the backend.

### 10. Host OS patch

```bash
apt-get update && apt-get upgrade -y
# Reboot only if kernel/glibc changed (announced in apt output).
```

If a reboot is needed, plan a maintenance window; the whole stack will come back on `restart: unless-stopped`. Mongo comes back healthy first (compose `depends_on`).

## On-call (something looks wrong)

### 11. Backend not producing scanner activity

```bash
docker exec arbicore-x-mongo mongosh --quiet arbicore_x_prod --eval '
  var w=(new Date()).getTime()/1000 - 300;
  print("recent cex_arb verifications (5m):",
    db.arbicore_discovery_candidates.countDocuments({claimed_by:/^cex_arb:/, verified_at:{$gte:w}}));
  print("scanner_state:");
  db.arbicore_scanner_state.find({}, {_id:1, enabled:1, last_tick_ts:1, last_error:1}).forEach(printjson);
'
```

Expected: > 0 recent verifications; both `cex_arb` and `funding_arb` `enabled: true`; no `last_error`.

### 12. High Mongo IO

```bash
docker stats arbicore-x-mongo --no-stream
docker exec arbicore-x-mongo mongosh --quiet --eval '
  db.currentOp({"active":true, "secs_running":{$gt:5}}).inprog.forEach(printjson);
'
```

If `arbicore_discovery_candidates` is > 3 M rows, run the opt-in cleanup (`docs/UPGRADE.md §3`).

### 13. Emergency shadow abort

If a scanner is producing bad data during a shadow window:

```bash
./deployment/monitoring/shadow_abort.sh <shadow_label>
```

### 14. Container in a restart loop

```bash
docker inspect arbicore-x-<service> -f '{{.State.Status}} {{.State.RestartCount}} {{.State.Error}}'
docker compose logs --tail=200 <service>
```

Common causes: missing env var (fail-fast) → check `.env`; port conflict → check `ss -ltn`; volume mount error → check bind path exists.

## Config change workflow

Any change to `.env`:

```bash
$EDITOR /opt/arbicore-x/.env
chmod 600 /opt/arbicore-x/.env
cd /opt/arbicore-x/deployment/compose
docker compose up -d --force-recreate backend    # or the specific service you affected
./scripts/healthcheck.sh
```

Any change to `nginx/*.conf` or the site template:

```bash
docker compose exec nginx nginx -t     # validate before reload
docker compose exec nginx nginx -s reload
```

## Reference

- `deployment/monitoring/snapshot.sh` — point-in-time snapshot (from GitHub, unchanged)
- `deployment/monitoring/uptime-probe.sh` — external-style probe (new authoring)
- `deployment/upgrade/steps/11_snapshot.sh` — realignment-flavored snapshot
