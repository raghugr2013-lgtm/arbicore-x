# ArbiCore X — Deployment Checklist (v2.9.2)

v2.9.2 is a **maintenance release**. It fixes:
- Windows checkout (v2.9.1)
- Ubuntu 24 / PEP 668 arbictl compliance (v2.9.1)
- REACT_APP_BACKEND_URL required contract (v2.9.1)
- **Deployment profile disambiguation (v2.9.2)** — `install.sh` now
  respects `ARBICORE_DEPLOY_PROFILE` and refuses to run the wrong compose
  file when the .env is configured for the other profile.

No runtime behaviour changed. v2.5–v2.9.1 data and configs are
forward-compatible.

---

## Choose your profile

ArbiCore X supports **two canonical deployment profiles**. Pick one
before you touch `.env`.

|  | **greenfield** | **shared** |
|---|---|---|
| Scenario | Fresh Ubuntu VPS, ArbiCore X is the only stack | Existing peer stack (e.g. Strategy Factory) already runs Mongo + reverse proxy |
| Mongo | ArbiCore owns `arbicore-x-mongo` | Connects to peer container (`factory-mongo` by default) |
| Docker network | ArbiCore owns `arbicore-x-net` | Attaches to peer's `vqb-network` |
| TLS | ArbiCore's nginx + certbot | Peer's Caddy |
| Ports | Owns 80 + 443 | Loopback only (8101/8102/8103) |
| Env files | repo-root `.env` | repo-root `.env` **and** `deployment/compose/.env.shared` |
| Compose file | `deployment/compose/docker-compose.yml` | `deployment/compose/docker-compose.shared.yml` |
| MONGO_URL fingerprint | `mongodb://mongo:27017` | `mongodb://root:...@factory-mongo:27017/?authSource=admin` |
| `install.sh` invocation | `./scripts/install.sh` | `./scripts/install.sh --profile shared` |

**The installer refuses to proceed if `.env` is a shared-profile `.env`
(MONGO_URL host ≠ `mongo`/`localhost`) but greenfield was requested.**
That check catches the exact v2.9.1 misdeploy where the greenfield
compose was launched against a shared `.env`, producing a
`factory-mongo:27017` resolution failure inside the calibration worker.

---

## Pre-deploy (common to both profiles)

- [ ] VPS has: Python 3.11+, Node 18+, Docker + docker-compose v2,
      supervisor, `sha256sum`.
- [ ] Ubuntu 24.04 hosts: install `python3-httpx` (or provision a project
      venv with httpx) — `arbictl` never pip-installs at runtime.
      See `docs/OPERATIONS_GUIDE.md` § "httpx runtime dependency".
- [ ] Pull `v2.9.2` (git tag) or extract `arbicore-x-v2.9.2.tar.gz`.
- [ ] Verify checksums:
      ```bash
      sha256sum -c arbicore-x-v2.9.2.SHASUMS
      ```

## Pre-deploy — greenfield profile

- [ ] `cp .env.example .env` and `chmod 600 .env`.
- [ ] Set every **REQUIRED** greenfield env var:
      - `ARBICORE_DEPLOY_PROFILE=greenfield`
      - `DOMAIN`, `LETSENCRYPT_EMAIL`
      - `JWT_SECRET`, `VAULT_KEY` (≥ 32 chars each; `openssl rand -hex 32`)
      - `ARBICORE_ADMIN_USER`, `ARBICORE_ADMIN_PASS`
      - `REACT_APP_BACKEND_URL` (typically `https://${DOMAIN}`)
      - `MONGO_URL=mongodb://mongo:27017`  ← keep this default
      - `DB_NAME=arbicore_prod`, `CORS_ORIGINS=https://${DOMAIN}`
- [ ] Confirm safety defaults:
      ```
      ARBICORE_SAFETY_KILL_DEFAULT=true
      ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED=false
      ```
- [ ] Ports 80 + 443 free on the host (`install.sh` checks this).

## Pre-deploy — shared profile

- [ ] `cp .env.example .env` and `chmod 600 .env`.
- [ ] Set the same application secrets in `.env` as for greenfield,
      **but with these differences**:
      - `ARBICORE_DEPLOY_PROFILE=shared`
      - `MONGO_URL=mongodb://<user>:<pw>@<peer-mongo-host>:27017/?authSource=admin`
      - `DOMAIN` / `LETSENCRYPT_EMAIL` — ignored (peer owns TLS); leave
        them set for backend log payloads that reference `DOMAIN`.
- [ ] `cp deployment/compose/.env.shared.example deployment/compose/.env.shared`
      and edit:
      - `NETWORK_NAME` — the peer's Docker network (default `vqb-network`)
      - `MONGO_HOST` — the peer's Mongo container hostname
      - `DB_NAME` — a database name NOT used by the peer
      - Container names, host ports, image tags (multi-tenant hosts)
- [ ] Confirm peer stack is up:
      ```bash
      docker network inspect vqb-network >/dev/null && echo OK
      docker ps --format '{{.Names}}' | grep -qx factory-mongo && echo OK
      ```

## Deploy

Both profiles use the same installer:

```bash
# greenfield (default)
./scripts/install.sh

# shared
./scripts/install.sh --profile shared
```

The `--profile` flag overrides `ARBICORE_DEPLOY_PROFILE` in `.env`. If
neither is set, the installer defaults to `greenfield`. Mismatched
profile + `.env` combos are refused with an actionable error.

## Post-deploy — gate on preflight

```bash
arbictl preflight       # 11-step readiness table
```

Expect **11/11 PASS**. Equivalent HTTP:
`curl -s $BASE_URL/api/arbicore/preflight | jq .ok` → `true`.

## Post-deploy — smoke tests (both profiles)

- [ ] `curl -s $BASE_URL/api/arbicore/providers/status | jq .provider_count`
  → **≥ 30**.
- [ ] `curl -s $BASE_URL/api/arbicore/live/status | jq '.stats.iterations'`
  → **> 0** within 30 s.
- [ ] `curl -s $BASE_URL/api/arbicore/scanners/cross/status | jq`
  → both `cex_dex` and `dex_dex` show `running=true`.
- [ ] `curl -s $BASE_URL/api/arbicore/safety/status | jq '.kill.engaged'`
  → **`true`**.
- [ ] `curl -s $BASE_URL/api/arbicore/validation/daily_status | jq`
  → shows `run_id`, `running=true`.

For **shared profile**, `$BASE_URL` is the peer Caddy hostname (via
`REACT_APP_BACKEND_URL`), and direct backend probes use
`http://${BACKEND_HOST_BIND}:${BACKEND_HOST_PORT}/api/` (default
`http://127.0.0.1:8101/api/`).

## Post-deploy — UI

- [ ] Open `$BASE_URL/login`, log in with admin credentials.
- [ ] Land on `/dashboard`, Ops Center renders within 6 seconds.
- [ ] KPI row shows 30+ providers and > 0 iterations.
- [ ] Safety chip shows `ENGAGED`, `PAPER-ONLY`.

## Rollback

```bash
arbictl rollback                # rolls back to LAST_KNOWN_GOOD
# — or —
git checkout v2.9.1 && sudo supervisorctl restart backend
```

v2.9.2 is fully backward-compatible with v2.5–v2.9.1 data in MID.

## Migrating from v2.9.1 (or earlier) to v2.9.2

If you deployed v2.9.1 with the greenfield installer against a
shared-profile `.env` and got a broken `arbicore-x-mongo` container:

```bash
# 1. Tear down the misdeployed greenfield containers only. Keep peer Mongo.
cd deployment/compose
docker compose -f docker-compose.yml down
docker volume rm arbicore-x-mongo-data   # ← only if it was misdeployed and empty
docker network rm arbicore-x-net 2>/dev/null || true

# 2. Set the profile in .env
sed -i 's/^ARBICORE_DEPLOY_PROFILE=.*/ARBICORE_DEPLOY_PROFILE=shared/' /path/to/.env
grep -q '^ARBICORE_DEPLOY_PROFILE=' /path/to/.env \
  || echo 'ARBICORE_DEPLOY_PROFILE=shared' >> /path/to/.env

# 3. Provision .env.shared (once)
cp deployment/compose/.env.shared.example deployment/compose/.env.shared
$EDITOR deployment/compose/.env.shared

# 4. Re-run install
./scripts/install.sh --profile shared
```
