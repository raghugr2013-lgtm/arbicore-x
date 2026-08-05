# v2.11.3 Deployment Fix — MongoDB Wiring & Docker Network

**Applies to**: `hotfix/canonical-v2.11` / tags `v2.11`, `v2.11.1`, `v2.11.2` and later
**Severity**: Deployment blocker (backend never reaches `Application startup complete.`)
**Scope**: Deployment configuration only — no application code changes.

---

## TL;DR

The v2.11 backend was configured to talk to `mongodb://factory-mongo:27017` but the backend container was attached to `arbicore-x-net` while `factory-mongo` lives on `vqb-network`. Docker DNS is network-scoped, so the hostname was unresolvable and every Mongo-touching startup handler stalled.

**Recommended fix:** switch the VPS from the `shared` profile to the `greenfield` profile so ArbiCore owns its own Mongo (`arbicore-x-mongo`) on its own network (`arbicore-x-net`). This eliminates the cross-network fragility entirely.

**Alternative fix (only if the ArbiCore data must remain in `factory-mongo`):** align `.env.shared` so `NETWORK_NAME=vqb-network` matches `MONGO_HOST=factory-mongo`.

Both patches are documented below.

---

## Audit Findings

### 1. Two compose profiles in the repo

| Profile | File | Mongo | Network |
|---|---|---|---|
| **Greenfield (self-owned)** | `deployment/compose/docker-compose.yml` | Creates `arbicore-x-mongo` container | Creates `arbicore-x-net` |
| **Shared (co-tenant)** | `deployment/compose/docker-compose.shared.yml` | Uses external `${MONGO_HOST}` (default `factory-mongo`) | Attaches to external `${NETWORK_NAME}` (fallback default `arbicore-x-net`) |

### 2. Which profile is being used on the VPS

The error trail — `Temporary failure in name resolution` for `factory-mongo:27017` — proves the **shared profile** is active AND the backend's `MONGO_URL` resolves to `factory-mongo`.

That happens when `docker-compose.shared.yml` is composed against these environment values:

```
MONGO_URL:  ${MONGO_URL:-mongodb://${MONGO_HOST:-factory-mongo}:${MONGO_PORT:-27017}}
NETWORK_NAME:  ${NETWORK_NAME:-arbicore-x-net}       ← fallback default
```

If `.env.shared` was either **missing** or set `NETWORK_NAME=arbicore-x-net` while leaving `MONGO_HOST` at the `factory-mongo` fallback, the two networks would refer to disjoint sets of containers — and factory-mongo would be unreachable. This matches the symptom exactly.

### 3. Default-mismatch footgun in `docker-compose.shared.yml`

- `NETWORK_NAME` fallback default: **`arbicore-x-net`** (line 63)
- `MONGO_HOST` fallback default: **`factory-mongo`** (line 104)

These two defaults are **incompatible**. If an operator forgets `.env.shared` entirely, compose silently boots a broken deployment. The example file `.env.shared.example` gets the pairing right (`NETWORK_NAME=vqb-network` + `MONGO_HOST=factory-mongo`), but the compose-level fallbacks disagree.

### 4. `MONGO_URL` references in the repo

| File | Value | Notes |
|---|---|---|
| `app/backend/.env` | `mongodb://localhost:27017` | Local dev only. Not shipped to the VPS. |
| `.env.production.example` | `mongodb://mongo:27017` | Greenfield template. `mongo` = service name in `docker-compose.yml` → resolves via Docker DNS to `arbicore-x-mongo`. ✅ correct for greenfield. |
| `.env.example` / `.env.development.example` | `mongodb://mongo:27017` | Same as above. |
| `docker-compose.shared.yml:104` | `${MONGO_URL:-mongodb://${MONGO_HOST:-factory-mongo}:27017}` | Shared-profile override. **This is where `factory-mongo` came from.** |
| `deployment/upgrade/steps/00_detect_env.sh:38` | Auto-detects from existing prod container | Upgrade script, not first-time deploy. |

No hardcoded `factory-mongo` anywhere else in the code path. The reference is exclusively in the shared-profile compose defaults.

---

## Decision: which Mongo should ArbiCore use?

**Recommendation: `arbicore-x-mongo` (greenfield profile).**

Rationale:
1. **Canonical primary path.** `docker-compose.yml` + `.env.production.example` are the documented primary deployment. The shared profile was an alternative for co-tenancy with the Strategy Factory peer stack.
2. **Paper Validation is about to begin.** v2.11's Slice 4 execution pipeline will accumulate shadow-cycle data via `arbicore_opportunity_journal`, `execution_plans`, and `capital_policy_audit`. Isolated data ownership is safest during a new certification campaign.
3. **No auth complications.** Peer Mongo (`factory-mongo`) commonly runs with `--auth`; the shared profile then requires a fully-baked `MONGO_URL` with credentials. Self-owned Mongo avoids that entire class of failure.
4. **No cross-network fragility.** The recurring root cause of the current outage cannot happen when Mongo lives on the same Docker network as the backend.

Use `factory-mongo` **only if** the ArbiCore data already lives there and migrating out is not desired. In that case the Path B patch below is the fix.

---

## Path A · Switch to `arbicore-x-mongo` (RECOMMENDED)

No repo file changes required for the greenfield profile itself. All changes happen on the VPS.

### A.1 · Stop the currently-broken shared-profile stack

```bash
cd /opt/arbicore-x/deployment/compose            # or wherever the deploy lives
docker compose --env-file .env.shared -f docker-compose.shared.yml down
docker network prune -f                          # cleans up stale attachments
```

### A.2 · Prepare the greenfield `.env`

```bash
cd /opt/arbicore-x                                # repo root on the VPS
[ -f .env ] || cp .env.production.example .env
$EDITOR .env
```

Ensure the following are set (do NOT edit `MONGO_URL` — it's already correct):
```
MONGO_URL=mongodb://mongo:27017                  # ← service name inside arbicore-x-net
DB_NAME=arbicore_prod                            # or your chosen name
REACT_APP_BACKEND_URL=https://<your.public.fqdn>
ARBICORE_BASE_URL=https://<your.public.fqdn>
CORS_ORIGINS=https://<your.public.fqdn>
JWT_SECRET=...                                   # required in production
ADMIN_USERNAME=...
ADMIN_PASSWORD=...
```

### A.3 · Bring up the greenfield stack

```bash
cd /opt/arbicore-x/deployment/compose
docker compose -f docker-compose.yml up -d
```

The greenfield stack creates:
- `arbicore-x-net` (bridge network)
- `arbicore-x-mongo` (Mongo 4.4 by default; override with `MONGO_IMAGE=mongo:7.0` on AVX hosts)
- `arbicore-x-mongo-data` (durable named volume — never a fresh host dir)
- `arbicore-x-backend`, `arbicore-x-opportunity-center`, `arbicore-x-caddy`, ...

### A.4 · Verify

```bash
# Should complete in <2s. Look for BOOT: <name> done lines (from v2.11.2).
docker logs arbicore-x-backend --since 1m | grep -E "BOOT:|Application startup complete"

# Should return 200.
curl -fsS http://127.0.0.1:8001/api/

# Mongo handshake from inside the backend container.
docker exec arbicore-x-backend python -c \
  "from motor.motor_asyncio import AsyncIOMotorClient as C; import asyncio, os; \
   c = C(os.environ['MONGO_URL'], serverSelectionTimeoutMS=5000); \
   print(asyncio.get_event_loop().run_until_complete(c.admin.command('ping')))"
```

### A.5 · If existing data must be migrated out of `factory-mongo`

```bash
# On the VPS, dump the ArbiCore database from the peer Mongo.
docker exec factory-mongo mongodump --db arbicore_x --archive=/tmp/arbicore.dump
docker cp factory-mongo:/tmp/arbicore.dump /tmp/arbicore.dump

# Restore into the new self-owned Mongo.
docker cp /tmp/arbicore.dump arbicore-x-mongo:/tmp/arbicore.dump
docker exec arbicore-x-mongo mongorestore --archive=/tmp/arbicore.dump
```

If migration isn't required (fresh Paper Validation start), skip A.5.

---

## Path B · Keep sharing `factory-mongo` (alternative)

Use this only if ArbiCore data must remain in the Strategy Factory peer Mongo.

### B.1 · Repair `.env.shared` on the VPS

```bash
cd /opt/arbicore-x/deployment/compose
[ -f .env.shared ] || cp .env.shared.example .env.shared
$EDITOR .env.shared
chmod 600 .env.shared
```

Set these three lines EXACTLY (all three matter — the mismatch you had was between `NETWORK_NAME` and `MONGO_HOST`):

```
NETWORK_NAME=vqb-network                                     # ← was arbicore-x-net; must match factory-mongo's network
MONGO_HOST=factory-mongo
# If peer Mongo has auth enabled, uncomment and set MONGO_URL explicitly:
# MONGO_URL=mongodb://<user>:<pass>@factory-mongo:27017/?authSource=admin
DB_NAME=arbicore_x                                           # or whatever your data currently lives in
```

Also ensure `REACT_APP_BACKEND_URL` and other required values are populated per the comments in the example.

### B.2 · Confirm the network exists

```bash
docker network inspect vqb-network >/dev/null 2>&1 && echo OK || echo "MISSING"
docker network inspect vqb-network | grep -A1 factory-mongo
```

If `MISSING`, the Strategy Factory peer stack owns the network; bring it up first, or manually:
```bash
docker network create --driver bridge vqb-network
docker network connect vqb-network factory-mongo
```

### B.3 · Redeploy

```bash
cd /opt/arbicore-x/deployment/compose
docker compose --env-file .env.shared -f docker-compose.shared.yml down
docker compose --env-file .env.shared -f docker-compose.shared.yml up -d
```

### B.4 · Verify

```bash
# DNS resolves inside the backend container.
docker exec arbicore-x-backend getent hosts factory-mongo   # must print an IP

# Boot completes.
docker logs arbicore-x-backend --since 1m | grep -E "BOOT:|Application startup complete"

# Health check.
curl -fsS http://127.0.0.1:${BACKEND_HOST_PORT:-8101}/api/
```

---

## Repo Patch — Prevent the same footgun from re-appearing

The one config change I'm shipping in this fix is a fail-fast guard in `docker-compose.shared.yml` so an operator who forgets `.env.shared` gets a **loud** error instead of a silent broken deploy.

### `deployment/compose/docker-compose.shared.yml`

Change the two fallback defaults so unset values fail-fast instead of producing mismatched networks. The mismatched defaults (`arbicore-x-net` for network, `factory-mongo` for Mongo host) are exactly the pairing that caused the outage.

Before:
```yaml
networks:
  shared:
    name: ${NETWORK_NAME:-arbicore-x-net}
    external: true
...
    environment:
      MONGO_URL: ${MONGO_URL:-mongodb://${MONGO_HOST:-factory-mongo}:${MONGO_PORT:-27017}}
```

After:
```yaml
networks:
  shared:
    name: ${NETWORK_NAME:?NETWORK_NAME must be set in .env.shared — see .env.shared.example}
    external: true
...
    environment:
      MONGO_URL: ${MONGO_URL:-mongodb://${MONGO_HOST:?MONGO_HOST or MONGO_URL must be set in .env.shared — see .env.shared.example}:${MONGO_PORT:-27017}}
```

With these changes, `docker compose up` on the shared profile without a `.env.shared` prints:

```
error while interpreting services.backend.environment.MONGO_URL:
  required variable MONGO_HOST is missing a value: MONGO_HOST or MONGO_URL must be set in .env.shared
```

instead of silently booting into a broken configuration.

---

## Verification Matrix

| Deploy path | Backend on network | Mongo container | `MONGO_URL` resolves to | `getent hosts` inside backend |
|---|---|---|---|---|
| **A. Greenfield** (recommended) | `arbicore-x-net` | `arbicore-x-mongo` | `mongodb://mongo:27017` | `mongo → 172.x.x.x` |
| **B. Shared (fixed)** | `vqb-network` | `factory-mongo` | `mongodb://factory-mongo:27017` | `factory-mongo → 172.x.x.x` |
| ❌ Broken (current state) | `arbicore-x-net` | `factory-mongo` on `vqb-network` | `mongodb://factory-mongo:27017` | **name resolution failure** |

---

## Rollback

- Path A → Path B: `docker compose -f docker-compose.yml down` then follow Path B from B.1.
- Path B → Path A: `docker compose -f docker-compose.shared.yml down` then follow Path A from A.2.
- Data safety: Path A can be applied on top of Path B without touching factory-mongo (it's ignored, not destroyed). Migration is optional (A.5).

---

## What is NOT in this fix

- **No application-code changes.** Zero touches to `server.py`, workers, engines, models, or handlers.
- **No API contract changes.**
- **No frontend changes.**
- **No data migrations required** (unless the operator chooses Path A.5).
- **No storage-schema changes.**

This is a pure configuration + one-line compose-guard patch.
