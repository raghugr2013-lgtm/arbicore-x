# ArbiCore X v2.0.3 — VPS Deployment Checklist

**Target:** production Contabo VPS (Ubuntu 22.04)
**Prerequisite:** a prior arbicore-x deploy or a fresh VPS per `docs/V2_MIGRATION_GUIDE.md`

## Pre-deployment (on canonical host / dev workstation)

- [ ] Verify bundle integrity:  
      `sha256sum -c arbicore-x-v2.0.3.SHASUMS`
- [ ] Confirm `arbicore-x-v2.0.3.bundle` clones cleanly:  
      `git clone arbicore-x-v2.0.3.bundle /tmp/verify && cd /tmp/verify && git describe --tags` → should return `v2.0.3`
- [ ] Confirm `VERSION` file inside canonical reads `2.0.3`
- [ ] Confirm 1469-test regression is green on the canonical (last certified run: 2026-08-02)

## On the VPS

### 1. Preflight snapshot (5 min)
- [ ] `cd /opt/arbicore-x && make backup`  (writes `backups/arbicore-x_YYYYMMDD_HHMMSS.archive.gz`)
- [ ] `cp .env .env.pre-v2.0.3.backup`
- [ ] `docker volume inspect arbicore-x-mongo-data > ~/mongo-volume.info.json`
- [ ] `docker volume inspect arbicore-x-certbot-etc > ~/certbot-etc.info.json`

### 2. Bring the stack down (preserving volumes)
- [ ] `docker compose -f deployment/compose/docker-compose.yml down`
- [ ] Verify volumes preserved: `docker volume ls | grep arbicore-x`

### 3. Swap in v2.0.3
- [ ] `sudo mv /opt/arbicore-x /opt/arbicore-x-v2.0.2`
- [ ] Upload `arbicore-x-v2.0.3.bundle` to the VPS
- [ ] `cd /opt && sudo git clone /path/to/arbicore-x-v2.0.3.bundle arbicore-x && cd arbicore-x && sudo git checkout v2.0.3`
- [ ] `sudo chown -R $USER:$USER /opt/arbicore-x`
- [ ] `cat VERSION`  → must show `2.0.3`

### 4. Migrate runtime configuration
- [ ] `cp /opt/arbicore-x-v2.0.2/.env .env`
- [ ] `chmod 600 .env`
- [ ] **Add v2.0.3-specific env vars** (⚠ REQUIRED — do not use dev fallbacks in production):
  ```
  ARBICORE_JWT_SECRET=$(openssl rand -hex 32)
  ARBICORE_ADMIN_PASSWORD=$(openssl rand -base64 24)
  ARBICORE_OPERATOR_PASSWORD=$(openssl rand -base64 24)
  ```
- [ ] Save the generated admin + operator passwords to your operator password manager BEFORE first boot (the seed writes hashes only)
- [ ] `diff .env .env.production.example` — resolve any missing variables

### 5. Bring up v2.0.3
- [ ] `SKIP_VOLUME_GUARD=1 make install`  (existing volumes preserved)
- [ ] Watch for successful phase 3–5 completion (Mongo attach + backend/frontend/OC image rebuild)
- [ ] Phase 7 (Let's Encrypt) should skip — existing certificates re-attached
- [ ] `make healthcheck` — all four services report healthy

### 6. Post-deploy verification
- [ ] `curl -sI https://${DOMAIN}/`  → HTTP/2 200
- [ ] `curl -s https://${DOMAIN}/api/` → `{"message":"Hello World"}`
- [ ] **Auth check:**  
  ```bash
  curl -sX POST https://${DOMAIN}/api/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"admin\",\"password\":\"${ARBICORE_ADMIN_PASSWORD}\"}"
  ```
  → returns `{token, token_type:"bearer", expires_at, user{...}}`
- [ ] **MID check:**  
      `curl -s https://${DOMAIN}/api/arbicore/mid/status | jq '.available, (.domains | length)'`  
      → `true` and `11`
- [ ] **Frontend:** open `https://${DOMAIN}/` in a browser → renders the Login page (not "Preview Pod")
- [ ] **Login flow:** sign in with `admin` + generated password → `/initialization` → 4 steps complete → `/dashboard`
- [ ] **Regression guard:** confirm `/dashboard` renders (not `/v2/*`); confirm `/v2` redirects to `/dashboard`

### 7. Turn on production hardening
- [ ] Verify `ARBICORE_MODE` (or `EXECUTION_MODE_DEFAULT`) is `shadow` for every strategy
- [ ] `curl -s https://${DOMAIN}/api/arbicore/execution/kill-switch` → `engaged=false`
- [ ] Send yourself a Telegram test alert to confirm the notification channel works before entering SHADOW steady-state
- [ ] Enable certbot renewal cron: `docker compose ps certbot-renew` → up

## Rollback trigger (if anything above fails)

- [ ] `docker compose -f deployment/compose/docker-compose.yml down`
- [ ] `sudo mv /opt/arbicore-x /opt/arbicore-x-v2.0.3.failed`
- [ ] `sudo mv /opt/arbicore-x-v2.0.2 /opt/arbicore-x`
- [ ] `cd /opt/arbicore-x && docker compose -f deployment/compose/docker-compose.yml up -d`
- [ ] `make healthcheck` — verify v2.0.2 restored
- [ ] File a bug against v2.0.3 with the specific failure

## Post-deployment monitoring (first 24 h)

- [ ] Every 4 h: check `/api/arbicore/mid/status` → last-write timestamps advancing across all 11 domains
- [ ] Every 4 h: check `/api/arbicore/dashboard/pulse` → workers alive, no red flags
- [ ] Every 4 h: check `docker compose logs backend --since=4h | grep -i "error\|traceback"` → no unexpected errors
- [ ] Every 4 h: `make healthcheck`
- [ ] After 24 h clean: platform is on SHADOW-tier steady-state; begin Sprint 1B in the canonical repo

## Sign-off

- [ ] Deployment executed by: __________
- [ ] Date/time: __________
- [ ] Post-deployment verification signature: __________
- [ ] First-hour steady-state signature: __________
- [ ] 24-hour steady-state signature: __________
