# ArbiCore X v2.9.2 — Deployment Profile Disambiguation

**Release date:** 2026-08-04
**Type:** Maintenance only — deployment tooling.
**Mode:** OBSERVE / PAPER · Kill switch ENGAGED (unchanged).
**Runtime behaviour:** **UNCHANGED** from v2.9.1.

## Why this release exists

A v2.9.1 VPS deployment failed with:

```
calibration worker: MongoServerSelectionError:
  getaddrinfo ENOTFOUND factory-mongo
```

Root cause: **the repository documents two deployment profiles but the
canonical installer only supports one.**

- `deployment/compose/docker-compose.yml` — greenfield (owns Mongo)
- `deployment/compose/docker-compose.shared.yml` — shared (peer Mongo)

`scripts/install.sh` was hard-coded to the greenfield compose. An
operator with a shared-profile `.env` (MONGO_URL pointing at
`factory-mongo` with credentials + `authSource=admin`) who ran
`./scripts/install.sh` got greenfield behaviour — a new
`arbicore-x-mongo` container next to their existing `factory-mongo`,
with the backend still pointing at `factory-mongo` in its env. Since
`factory-mongo` doesn't live on the greenfield `arbicore-x-net`, the
DNS resolution failed.

`scripts/healthcheck.sh` had the same greenfield-only assumption
(hard-coded `arbicore-x-mongo` and `arbicore-x-nginx` container names).

## What changed

### 1. Profile-aware installer (`scripts/install.sh`)

- **New `--profile {greenfield|shared}` CLI flag**, with fallback to
  `ARBICORE_DEPLOY_PROFILE` from `.env`, defaulting to `greenfield`.
- **Dispatches to the correct compose file + env-file combo**:
  - greenfield → `docker-compose.yml`
  - shared → `docker-compose.shared.yml` with
    `--env-file deployment/compose/.env.shared`
- **Fingerprint-based consistency guard** — if the .env's `MONGO_URL`
  points at a hostname other than `mongo` / `localhost` / `127.0.0.1`
  but the greenfield profile was requested, the installer refuses with
  an actionable message telling the operator to re-run with
  `--profile shared`. This is the exact check that would have caught
  the v2.9.1 misdeploy.
- **Profile-aware guards**:
  - greenfield → refuse if `arbicore-x-mongo` container/volume exists,
    check ports 80/443 free.
  - shared → verify peer network exists (`docker network inspect
    $NETWORK_NAME`), warn if peer Mongo container is not visible,
    refuse if any `arbicore-x-*` container already exists.
- **Profile-aware bring-up** — skips Mongo, nginx, and certbot steps in
  the shared profile (peer stack owns them).
- **Profile-aware success banner** — greenfield prints the public
  `https://${DOMAIN}` URL; shared prints the loopback ports and peer
  wiring summary.

### 2. Profile-aware healthcheck (`scripts/healthcheck.sh`)

- **Container-name set** is now chosen per profile. Shared deployments
  no longer report false-negative FAILs for the non-existent
  `arbicore-x-mongo` and `arbicore-x-nginx` containers.
- **Peer-Mongo reachability probe** — shared profile now runs
  `docker exec <backend> python -c 'socket.gethostbyname("$MONGO_HOST")'`
  to catch exactly the v2.9.1 DNS failure at healthcheck time (instead
  of the calibration worker's silent crash).
- **HTTP probe** — greenfield probes `nginx-health`; shared probes the
  backend directly on `${BACKEND_HOST_BIND}:${BACKEND_HOST_PORT}/api/`.
- **TLS probe** — greenfield only.

### 3. .env contract

- New `ARBICORE_DEPLOY_PROFILE` variable added to `.env.example`,
  `.env.production.example`, `.env.development.example` with a full
  description of the two profiles.
- `DOMAIN` and `LETSENCRYPT_EMAIL` now clearly labelled as
  greenfield-only (still shipped for shared profiles that want the
  backend to log a canonical URL).

### 4. Documentation

- `docs/DEPLOYMENT_CHECKLIST.md` — new **"Choose your profile"**
  section with a side-by-side comparison table. Split pre-deploy
  checklists per profile. Documented migration path from a misdeployed
  v2.9.1 → clean v2.9.2 shared deployment.

## What did **not** change

- `arbicore/` runtime code — unchanged.
- `backend/server.py` and every FastAPI route — unchanged.
- Frontend components, styling, routes — unchanged.
- Both compose files themselves — **unchanged**. They were already
  correct; only the installer needed to learn how to pick between them.
- Scanner behaviour, safety defaults, provider registry, MID schema,
  evidence exporter, daily-summary writer — unchanged.

## Regression posture

- `bash -n` clean for `install.sh` and `healthcheck.sh`.
- All three compose YAMLs still parse.
- The greenfield default path is unchanged in behavior — operators who
  never set `ARBICORE_DEPLOY_PROFILE` and had a greenfield `.env` get
  the exact v2.9.1 bring-up sequence.
- Backward compatible with v2.5–v2.9.1 MID data.

## Constraints held

- ✅ No new features
- ✅ No new scanners / providers
- ✅ No UI work
- ✅ No execution-logic changes
- ✅ No new APIs
- ✅ No safety changes
- ✅ Backward compatible with v2.5–v2.9.1 data

## Verification matrix

| Concern | Status |
|---|---|
| `install.sh --profile greenfield` behaves as v2.9.1 | ✅ (identical steps) |
| `install.sh --profile shared` uses `docker-compose.shared.yml` | ✅ |
| Shared profile requires `deployment/compose/.env.shared` | ✅ (refuses if missing) |
| Shared profile verifies peer network exists | ✅ |
| Greenfield profile refuses shared-topology `MONGO_URL` | ✅ (fingerprint check) |
| Healthcheck skips `arbicore-x-mongo` on shared profile | ✅ |
| Healthcheck resolves peer Mongo host from backend on shared | ✅ |
| `.env.example` documents both profiles | ✅ |
| `DEPLOYMENT_CHECKLIST.md` has "Choose your profile" section | ✅ |
| Migration path documented for v2.9.1 misdeploys | ✅ |

## Migration path from v2.9.1

**If you're on greenfield already**, `git pull && git checkout v2.9.2`
and you're done. Nothing to change in your `.env`.

**If you're the reporter of this issue** (v2.9.1 greenfield installer
run against a shared `.env`, producing broken `arbicore-x-mongo`):

```bash
# 1. Tear down the misdeployed greenfield containers.
cd deployment/compose
docker compose -f docker-compose.yml down
docker volume rm arbicore-x-mongo-data   # only if empty / misdeployed
docker network rm arbicore-x-net 2>/dev/null || true

# 2. Declare the profile in .env.
echo 'ARBICORE_DEPLOY_PROFILE=shared' >> /path/to/.env

# 3. Provision the shared wiring file (once).
cp deployment/compose/.env.shared.example deployment/compose/.env.shared
$EDITOR deployment/compose/.env.shared    # NETWORK_NAME, MONGO_HOST, DB_NAME, ports

# 4. Re-run install.
./scripts/install.sh --profile shared
```

## Deliverables

- `arbicore-x-v2.9.2.tar.gz`
- `arbicore-x-v2.9.2.SHASUMS`
- `docs/RELEASE_NOTES_v2.9.2.md` (this file)
- Updated `docs/DEPLOYMENT_CHECKLIST.md`
- Updated `.env.example`, `.env.production.example`,
  `.env.development.example`
- Updated `scripts/install.sh`, `scripts/healthcheck.sh`
- Git tag `v2.9.2`
