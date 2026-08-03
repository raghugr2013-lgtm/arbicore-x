# ArbiCore X v2.1.0 — VPS Deployment Checklist

**Target:** production Contabo VPS (Ubuntu 22.04) currently on v2.0.5
**Codename:** Intelligence Activation
**Migration risk:** LOW  (no schema change, no data migration,
    backward-compatible endpoints, runtime `.env` preserved)

Estimated wall time: 20-25 min from preflight snapshot to green health.
Rollback path: `git checkout v2.0.5 && docker compose up -d --build backend` (< 5 min).

---

## Pre-deployment (on canonical host / dev workstation)

- [ ] Verify canonical `VERSION` reads `2.1.0`:
      `cat /opt/arbicore-canonical/VERSION` → `2.1.0`
- [ ] Regression suite green:
      `cd app/backend && REACT_APP_BACKEND_URL=<preview> pytest -q` →
      `1494 passed, 76 skipped, 0 failures`
- [ ] Bundle produced:
      `git bundle create arbicore-x-v2.1.0.bundle --all` +
      `sha256sum arbicore-x-v2.1.0.bundle > arbicore-x-v2.1.0.SHASUMS`
- [ ] Bundle integrity verified locally:
      `sha256sum -c arbicore-x-v2.1.0.SHASUMS`
- [ ] Release notes reviewed: `docs/RELEASE_NOTES_v2.1.0.md`

---

## On the VPS

### 1. Preflight snapshot (5 min)

- [ ] `cd /opt/arbicore-x && make backup`
      (writes `backups/arbicore-x_YYYYMMDD_HHMMSS.archive.gz`)
- [ ] `cp .env .env.pre-v2.1.0.backup`
- [ ] `docker volume inspect arbicore-x-mongo-data > ~/mongo-volume.info.json`
- [ ] Snapshot current auth state
      (verifies the v2.0.7 fix will be tested against real data):
      ```bash
      docker compose exec mongo mongosh --quiet arbicore \
        --eval 'db.auth_users.find({}, {_id:0, username:1, role:1, active:1}).toArray()'
      ```
- [ ] `docker compose ps` — record which images are currently running

### 2. Bring the stack down (preserving volumes)

- [ ] `docker compose -f deployment/compose/docker-compose.yml down`
- [ ] Verify volumes preserved: `docker volume ls | grep arbicore-x`
- [ ] Expected volumes intact: `arbicore-x-mongo-data`, `arbicore-x-certbot-etc`, `arbicore-x-certbot-var`

### 3. Swap in v2.1.0

- [ ] `sudo mv /opt/arbicore-x /opt/arbicore-x-v2.0.5`
- [ ] Upload `arbicore-x-v2.1.0.bundle` + `.SHASUMS` to the VPS
- [ ] Verify SHAs: `sha256sum -c arbicore-x-v2.1.0.SHASUMS`
- [ ] `cd /opt && sudo git clone /path/to/arbicore-x-v2.1.0.bundle arbicore-x && \
       cd arbicore-x && sudo git checkout v2.1.0`
- [ ] `sudo chown -R $USER:$USER /opt/arbicore-x`
- [ ] `cat VERSION` → **must** show `2.1.0`

### 4. Migrate runtime configuration

- [ ] `cp /opt/arbicore-x-v2.0.5/.env .env`
- [ ] `chmod 600 .env`
- [ ] Diff against reference: `diff .env .env.production.example`
      → resolve any missing variables (no new env vars in v2.1.0)
- [ ] Existing `ARBICORE_JWT_SECRET`, `ARBICORE_ADMIN_PASSWORD`,
      `ARBICORE_OPERATOR_PASSWORD` remain **unchanged** — this
      release preserves auth session validity.

### 5. Build + bring up v2.1.0

- [ ] `SKIP_VOLUME_GUARD=1 docker compose \
        -f deployment/compose/docker-compose.yml build backend`
      (frontend + OC images unchanged; only backend needs rebuild)
- [ ] `docker compose -f deployment/compose/docker-compose.yml up -d`
- [ ] `make healthcheck` (or `docker compose ps`) — all four services
      report healthy

### 6. Post-deploy verification

- [ ] Basic HTTPS + root API:
      ```
      curl -sI https://${DOMAIN}/                    → HTTP/2 200
      curl -s  https://${DOMAIN}/api/                → {"message":"Hello World"}
      ```

- [ ] **Startup log — auth seed truthful (v2.0.6):**
      ```
      docker compose logs backend | grep 'auth: '
      ```
      Expected pattern (idempotent restart of existing DB):
      ```
      auth: all 2 default user(s) already exist in arbicore.auth_users [admin, operator] — no seed needed
      auth: post-seed verification OK — admin=True, operator=True present in arbicore.auth_users
      auth: startup seed summary — db=arbicore coll=auth_users
          inserted=[] existed_before=['admin', 'operator']
          skipped_existing=['admin', 'operator']
          verified={'admin': True, 'operator': True} ok=True
      ```

- [ ] **Auth login (v2.0.7 fix):**
      ```
      curl -sX POST https://${DOMAIN}/api/auth/login \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"admin\",\"password\":\"${ARBICORE_ADMIN_PASSWORD}\"}"
      ```
      Expected: HTTP 200 with `token`, `user.role="admin"`. This must
      succeed for the account whose password was reset last week.

- [ ] **Auth diagnostics (v2.0.7):**
      ```
      TOKEN=$(curl -sX POST https://${DOMAIN}/api/auth/login ...)
      curl -s https://${DOMAIN}/api/auth/diagnostics \
        -H "Authorization: Bearer ${TOKEN}"
      ```
      Expected payload — `admin.exists=true`, `hash_prefix="$2b$"`,
      `hash_len=60`, `active_field` is `true` OR `null` (both accepted).

- [ ] **Intelligence engines (Wave 1B-α):**
      ```
      curl -s https://${DOMAIN}/api/arbicore/intelligence/status
      ```
      Expected: `active_count=6`, `errored=[]`, all six engines listed.

- [ ] **Scanner activation DORMANT boot (Wave 1B-β):**
      ```
      curl -s https://${DOMAIN}/api/arbicore/scanners/status
      ```
      Expected: `scanner_count=2, running=[], mode="shadow"`. Both
      scanners `enabled=false, running=false` at first boot.

- [ ] **Observability endpoint:**
      ```
      curl -s https://${DOMAIN}/api/arbicore/observability
      ```
      Expected — `mid.available=true`, `intelligence.active_count=6`,
      `scanners.scanner_count=2`, `auth.available=true`.

- [ ] **MID unchanged:** `curl -s https://${DOMAIN}/api/arbicore/mid/status`
      — every domain count `>= 0`, no domain regressed to unavailable.

### 7. Operator smoke test (optional — 2 min)

- [ ] Log in via the UI (`Login → Initialization → Dashboard`).
- [ ] Verify the dashboard renders without console errors.
- [ ] From the operator wizard, start the DEX shadow scanner:
      ```
      curl -sX POST https://${DOMAIN}/api/arbicore/scanners/dex_arbitrage/start \
        -H "Authorization: Bearer ${OPERATOR_TOKEN}"
      ```
      Expected: `{"scanner_id":"dex_arbitrage","mode":"shadow","started":true,...}`
- [ ] Wait 20-30 s, then verify emissions in MID:
      ```
      curl -s "https://${DOMAIN}/api/arbicore/mid/query/opportunities?limit=5" | jq
      ```
      Expected: at least one row with
      `event_type="scanner.dex_arbitrage.emit"`, `payload.shadow=true`.
- [ ] Stop the scanner:
      ```
      curl -sX POST https://${DOMAIN}/api/arbicore/scanners/dex_arbitrage/stop \
        -H "Authorization: Bearer ${OPERATOR_TOKEN}"
      ```

### 8. Freeze + retention

- [ ] `docker image prune -f` (removes replaced backend image)
- [ ] `mv /opt/arbicore-x-v2.0.5 /opt/archive/arbicore-x-v2.0.5.$(date +%Y%m%d)`
- [ ] Keep the backup archive from step 1 for 30 days minimum.
- [ ] Record deploy in `docs/DEPLOYMENT_LOG.md`
      (deploy date, git SHA, operator name, health check output).

---

## Rollback (if needed)

```
cd /opt/arbicore-x
git checkout v2.0.5
docker compose -f deployment/compose/docker-compose.yml up -d --build backend
```

Volumes are preserved so no data recovery is required. The rollback
window is unbounded — v2.1.0 does not modify existing collections.

---

## Success criteria (all must be checked)

- [ ] `VERSION` on VPS shows `2.1.0`
- [ ] All four services healthy (`docker compose ps`)
- [ ] Startup log shows truthful v2.0.6 auth seed summary
- [ ] Admin login returns HTTP 200 with a valid JWT
- [ ] `/api/auth/diagnostics` returns admin+operator, both `hash_prefix=$2b$`
- [ ] `/api/arbicore/intelligence/status` shows 6/6 active, no errors
- [ ] `/api/arbicore/scanners/status` shows 2 scanners DORMANT
- [ ] `/api/arbicore/observability` returns all four subsystems available
- [ ] UI login → dashboard renders cleanly with no console errors
- [ ] Optional operator smoke test: shadow scanner start → MID emission → stop

If any checkbox fails, execute the rollback procedure above.
