# ArbiCore X — Deployment Checklist (v2.9.1)

v2.9.1 is a **maintenance release**: Windows compatibility, Ubuntu-24 /
PEP 668 compliance, and deployment-safety hardening. **No runtime
behaviour changed.** v2.5–v2.9.0 data and configs are forward-compatible.

## Pre-deploy

- [ ] Confirm VPS has: Python 3.11+, Node 18+, MongoDB 6+, supervisor,
      Docker + docker-compose v2, `sha256sum`.
- [ ] Ubuntu 24.04 hosts: install `python3-httpx` (or provision a project
      venv with httpx) — **v2.9.1 no longer pip-installs at runtime**. See
      `docs/OPERATIONS_GUIDE.md` § "httpx runtime dependency".
- [ ] Pull `v2.9.1` (git tag) or extract `arbicore-x-v2.9.1.tar.gz`.
- [ ] Verify checksums against `arbicore-x-v2.9.1.SHASUMS`:
      ```bash
      sha256sum -c arbicore-x-v2.9.1.SHASUMS
      ```
- [ ] Copy the environment template and edit it:
      ```bash
      cp .env.example .env
      chmod 600 .env
      $EDITOR .env
      ```
- [ ] Set every **REQUIRED** env var (install.sh will refuse to run until
      each of these is set):
      - `DOMAIN`
      - `LETSENCRYPT_EMAIL`
      - `JWT_SECRET`   (≥ 32 chars, `openssl rand -hex 32`)
      - `VAULT_KEY`    (≥ 32 chars, `openssl rand -hex 32`)
      - `ARBICORE_ADMIN_USER`
      - `ARBICORE_ADMIN_PASS`
      - `REACT_APP_BACKEND_URL`   ← **REQUIRED in v2.9.1** (was OPTIONAL
        in v2.9.0). Both docker-compose files and the frontend Dockerfile
        hard-fail if empty; empty produces a black-screen operator UI.
      - `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`
- [ ] Confirm safety defaults remain **explicit**:
      ```
      ARBICORE_SAFETY_KILL_DEFAULT=true
      ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED=false
      ```

### Windows clone/checkout note

v2.9.1 renames `app/backend/arbicore/providers/aux.py` →
`app/backend/arbicore/providers/aux_providers.py`. Windows reserves the
filename `AUX` and would refuse to check the repo out on Windows hosts.
No source references to the old name remain. Re-clone (or `git pull`) on
Windows dev machines after this release.

## Deploy — Docker compose (recommended)

```bash
cd /app/canonical_repo
./scripts/install.sh
```

`install.sh` now validates `REACT_APP_BACKEND_URL` in the .env preflight;
the frontend build will otherwise fail loudly with the actionable message
baked into `deployment/docker/frontend/Dockerfile`.

## Deploy — bare-metal (legacy)

- [ ] `pip install -r app/backend/requirements.txt`
- [ ] `yarn --cwd app/frontend install --frozen-lockfile`
- [ ] `REACT_APP_BACKEND_URL=... yarn --cwd app/frontend build`
- [ ] `sudo supervisorctl restart backend`
- [ ] `sudo supervisorctl restart frontend`
- [ ] Wait 15 seconds for the live scanner autostart.

## Post-deploy — arbictl one-liner

```bash
arbictl deploy --tag v2.9.1 \
  --checksum /app/releases/v2.9.1/arbicore-x-v2.9.1.SHASUMS
```

`deploy` runs checksum verify → backup marker → `git checkout` →
supervisor restart → wait → **preflight**. Any non-zero exit means the
deploy did NOT reach a healthy state.

## Post-deploy — gate on preflight

- [ ] `arbictl preflight` — expect **11/11 PASS**.
- [ ] Equivalent HTTP check:
      `curl -s $BASE_URL/api/arbicore/preflight | jq .ok` → `true`.

## Post-deploy — smoke tests

- [ ] `curl -s $BASE_URL/api/arbicore/providers/status | jq .provider_count`
  → expect **≥ 30**.
- [ ] `curl -s $BASE_URL/api/arbicore/live/status | jq '.stats.iterations'`
  → **> 0** within 30 s.
- [ ] `curl -s $BASE_URL/api/arbicore/live/prices | jq '.prices | keys'`
  → lists `BTC/USDT` and `ETH/USDT`.
- [ ] `curl -s $BASE_URL/api/arbicore/scanners/cross/status | jq`
  → both `cex_dex` and `dex_dex` show `running=true`.
- [ ] `curl -s $BASE_URL/api/arbicore/safety/status | jq '.kill.engaged'`
  → **must be `true`**.
- [ ] `curl -s $BASE_URL/api/arbicore/validation/daily_status | jq`
  → shows `run_id`, `running=true`, `last_summary_at != null`.

## Post-deploy — UI

- [ ] Open `$BASE_URL/login`, log in with admin credentials.
- [ ] Land on `/dashboard` — Ops Center renders within 6 seconds.
- [ ] Verify:
  - KPI row shows 30+ providers and > 0 iterations.
  - Live prices show at least 3 CEX venues per symbol.
  - Safety chip shows `ENGAGED`, `PAPER-ONLY`.

## Rollback

If preflight fails or the Ops Center is empty after 60 seconds:

1. `arbictl rollback`   (rolls back to `LAST_KNOWN_GOOD` marker)
2. Alternatively: `git checkout v2.9.0 && sudo supervisorctl restart backend`
3. Tail `/var/log/supervisor/backend.err.log` for the first exception.

v2.9.1 is fully backward-compatible with v2.5–v2.9.0 data in MID.
