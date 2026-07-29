# ArbiCore X — Shared-Infrastructure Deployment Guide

**Bundle version:** post-RC1 hardening (Phase 2)
**Profile:** `shared`
**Compose file:** `deployment/compose/docker-compose.shared.yml`
**Wiring template:** `deployment/compose/.env.shared.example`
**Companion documents:** `docs/INSTALL.md` (greenfield), `docs/UPGRADE.md`, `docs/ROLLBACK.md`, `docs/TROUBLESHOOTING.md`

---

## 1. When to use this profile

Use the **shared-infrastructure** profile when the target VPS already runs a peer stack (Strategy Factory, or any other Docker-Compose-based application) that owns:

- an existing Docker bridge network,
- an existing MongoDB instance,
- an existing reverse proxy (Caddy is the canonical peer choice; nginx also supported).

ArbiCore X plugs in as a co-tenant: three containers (backend + operator UI + Opportunity Center) attach to the peer network, connect to peer Mongo, and expose loopback host ports that the peer Caddy proxies through TLS.

Use the **greenfield** profile (default `docker-compose.yml`) if you want ArbiCore X to own the entire stack (network, Mongo, TLS). Use the **upgrade toolkit** (`deployment/upgrade/`) to upgrade an existing greenfield install in-place.

---

## 2. Architecture diagram

```
                                    Internet
                                        │
                                        │ HTTPS :443
                                        ▼
              ┌──────────────────────────────────────────────┐
              │   HOST  (peer VPS — e.g. 151.243.146.115)      │
              │                                                │
              │   ┌───────────────────────┐                     │
              │   │  Caddy  (peer)  │  (host-native or           │
              │   │  TLS termination │   containerized;           │
              │   │  virtual hosts  │   ArbiCore does not deploy) │
              │   └──────┬───────────────┘                     │
              │          │ loopback proxy                       │
              │          │ 127.0.0.1:8101 → backend             │
              │          │ 127.0.0.1:8102 → frontend            │
              │          │ 127.0.0.1:8103 → opportunity_center  │
              │          ▼                                       │
              │  ┌──────────────────── SHARED NETWORK  ────────────┐    │
              │  │  ${NETWORK_NAME}   (e.g. vqb-network)         │    │
              │  │                                              │    │
              │  │    ┌──────────────────────────┐                │    │
              │  │    │  arbicore-x-backend  (:8001)  │  <────────┐   │
              │  │    └─────────────┬───────────────┘        │   │
              │  │                  │ mongo://factory-mongo:27017  │   │
              │  │                  │   /arbicore_x                │   │
              │  │                  ▼                              │   │
              │  │    ┌──────────────────────────┐                │   │
              │  │    │  ${MONGO_HOST}   (peer's Mongo, │           │   │
              │  │    │  e.g. factory-mongo)             │           │   │
              │  │    └───────────────────────────┘            db=arbicore_x  │
              │  │                                            (peer uses db=vqb)│
              │  │    ┌──────────────────────────┐        │   │
              │  │    │  arbicore-x-frontend        (:80) │  <────┤   │
              │  │    └──────────────────────────┘        │   │
              │  │    ┌──────────────────────────┐        │   │
              │  │    │  arbicore-x-opportunity-center     │  <──┘   │
              │  │    └──────────────────────────┘            │
              │  │                                                │
              │  │    (Peer stack containers also live here:      │
              │  │     strategy-factory-backend, factory-mongo,   │
              │  │     factory-redis, factory-worker, ...)        │
              │  └──────────────────────────────────────────────────────────────────┘
              └───────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Network topology

### 3.1 The shared network

One user-defined Docker bridge network is used by both stacks. It is owned by the peer stack; ArbiCore X attaches to it as an `external: true` network.

| Compose network key | Value | Owner |
|---|---|---|
| `networks.shared.name` | `${NETWORK_NAME}` (e.g. `vqb-network`) | Peer stack |
| `networks.shared.external` | `true` | ArbiCore X compose *declares* external; does not create |

Before first deploy, verify the network exists:

```bash
docker network ls | grep -w "$NETWORK_NAME"
docker network inspect "$NETWORK_NAME" --format '{{range .Containers}}{{.Name}} {{end}}'
```

If it does not exist, either:

- (Preferred) let the peer stack create it — run the peer's `docker compose up -d` first, then verify.
- (Fallback) create it manually: `docker network create --driver bridge "$NETWORK_NAME"`

### 3.2 Alias contract

Each ArbiCore container registers a network alias (env-configurable) so peer stack containers can address it by a stable name that is decoupled from `container_name`. Defaults:

| Service | Alias | Env |
|---|---|---|
| backend | `arbicore-backend` | `BACKEND_NETWORK_ALIAS` |
| frontend | `arbicore-frontend` | `FRONTEND_NETWORK_ALIAS` |
| opportunity_center | `arbicore-opportunity-center` | `OPPORTUNITY_CENTER_NETWORK_ALIAS` |

Multi-tenant setups (staging + prod on same host) prefix these: `arbicore-staging-backend`, `arbicore-prod-backend`, etc.

---

## 4. MongoDB reuse

### 4.1 Connection

ArbiCore X reaches the peer's Mongo container via the shared network. Two ways to configure:

**Simple (recommended):** set host + port; the compose builds `MONGO_URL` for you.

```dotenv
# .env.shared
MONGO_HOST=factory-mongo
MONGO_PORT=27017
# MONGO_URL left blank
```

**Explicit (needed when Mongo has auth):**

```dotenv
# .env.shared
MONGO_URL=mongodb://arbicore:<password>@factory-mongo:27017/?authSource=admin
```

The `MONGO_URL` value, if non-empty, wins over `MONGO_HOST/MONGO_PORT`.

### 4.2 Auth setup (if the peer Mongo has auth enabled)

Run this **on the peer** to create an ArbiCore user with read-write-only access to the ArbiCore database:

```bash
docker exec -i factory-mongo mongosh --quiet <<'EOF'
use admin
db.createUser({
  user: "arbicore",
  pwd:  passwordPrompt(),
  roles: [ { role: "readWrite", db: "arbicore_x" } ]
})
EOF
```

The user gets **no privileges on the peer's own database** (typically `vqb` or similar). This is the isolation guarantee — see § 5.

### 4.3 What ArbiCore X will NOT do

- Never create the Mongo container.
- Never mount `/data/db`.
- Never call `mongod --repair`, `dbAdmin`, or `serverStatus` on Mongo itself.
- Never write outside its own `${DB_NAME}` database.

---

## 5. Database isolation

One Mongo instance, N databases:

```
factory-mongo (single mongod process)
├── admin                     (auth + system)
├── vqb            ← peer stack (Strategy Factory) writes here
└── arbicore_x     ← ArbiCore X writes here
```

| Guarantee | Enforcement |
|---|---|
| ArbiCore X never writes into peer's `vqb` DB | `DB_NAME=arbicore_x` in ArbiCore's env; Motor client picks up only that DB |
| Peer never writes into `arbicore_x` DB | Peer's config points at its own DB, `vqb` |
| Cross-DB read is possible only with `admin`-role user | If Mongo auth is on and each service has a scoped role, cross-DB is denied by Mongo itself |
| No collection-name collisions matter | Different DBs = different namespaces; two `outcomes` collections in `vqb` and `arbicore_x` are entirely independent |

**Naming discipline:** the `DB_NAME` must not equal the peer's DB name. Verify before first start:

```bash
docker exec factory-mongo mongosh --quiet --eval \
  'db.adminCommand({listDatabases:1}).databases.map(d=>d.name)'
```

---

## 6. Port mapping

All three ArbiCore host ports bind to loopback (`127.0.0.1`) by default. Only the peer's reverse proxy — running on the same host — can reach them.

| Service | Container port | Default host port | Env |
|---|---|---|---|
| backend | 8001 | 8101 | `BACKEND_HOST_PORT` |
| frontend | 80 | 8102 | `FRONTEND_HOST_PORT` |
| opportunity_center | 80 | 8103 | `OPPORTUNITY_CENTER_HOST_PORT` |

Multi-tenant / port-collision resolution: pick a **contiguous block** (e.g. `8101-8103` for tenant A, `8201-8203` for tenant B, `8301-8303` for tenant C) and update `.env.shared` accordingly.

**Do not** set `*_HOST_BIND=0.0.0.0` unless you have a specific reason. That would expose the backend directly on the VPS's public IP, bypassing Caddy and TLS.

---

## 7. Caddy integration

Two canonical integration patterns; choose based on how the peer's Caddy is configured.

### 7.1 Pattern A — Caddyfile (config-file routing)

The peer runs Caddy from a Caddyfile. Add a virtual-host block:

```caddyfile
# /etc/caddy/Caddyfile   (or wherever the peer's Caddy config lives)

arbicore.example.com {
    # API
    reverse_proxy /api/* 127.0.0.1:8101

    # Opportunity Center analytics UI
    handle_path /opportunity-center* {
        reverse_proxy 127.0.0.1:8103
    }

    # Operator UI (default)
    reverse_proxy 127.0.0.1:8102

    # Security hygiene
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Frame-Options            "SAMEORIGIN"
        X-Content-Type-Options     "nosniff"
        Referrer-Policy            "strict-origin-when-cross-origin"
    }

    log {
        output file /var/log/caddy/arbicore.access.log
    }
}
```

Reload Caddy:

```bash
sudo systemctl reload caddy         # if host-native
# or
docker exec peer-caddy caddy reload --config /etc/caddy/Caddyfile
```

### 7.2 Pattern B — caddy-docker-proxy (label-based routing)

The peer runs [`lucaslorentz/caddy-docker-proxy`](https://github.com/lucaslorentz/caddy-docker-proxy). Populate the CADDY_* variables in `.env.shared` and the compose file's `labels:` blocks activate automatically:

```dotenv
# .env.shared
CADDY_BACKEND_HOST=arbicore.example.com
CADDY_FRONTEND_HOST=arbicore.example.com
CADDY_OPPORTUNITY_CENTER_HOST=arbicore.example.com/opportunity-center/*
```

Leave them **blank** if you are not using the plugin — the compose file emits `caddy: ""` which is a safe no-op.

### 7.3 What ArbiCore X will NOT do to your Caddy

- Never write to `/etc/caddy/`.
- Never issue certificates (Certbot / ACME).
- Never open ports 80 or 443.
- Never reload the peer's Caddy.
- Never assume TLS is present — the compose binds loopback only; TLS is the peer's job.

---

## 8. Deployment workflow (first-time)

```bash
# ------- Pre-flight -------
# 1. Confirm peer stack is up and the shared network exists
docker network ls | grep -w vqb-network
docker ps --format '{{.Names}}' | grep factory-

# 2. Confirm peer Mongo is reachable from a scratch container on the shared network
docker run --rm --network vqb-network mongo:4.4 mongosh --host factory-mongo --eval 'db.adminCommand({ping:1})'

# 3. Verify DB_NAME is unused
docker exec factory-mongo mongosh --quiet --eval \
  'db.adminCommand({listDatabases:1}).databases.map(d=>d.name)'
#    → arbicore_x should NOT appear

# ------- Bundle install -------
# 4. Extract the bundle
cd /opt
tar -xzf arbicore-x-v1.0.0.tar.gz
cd /opt/arbicore-x
REPO_ROOT=$(pwd)

# 5. Populate application secrets
cp .env.production.example .env
$EDITOR .env                       # JWT_SECRET, VAULT_KEY, admin creds, scanner toggles
chmod 600 .env

# 6. Populate shared-profile wiring
cd "$REPO_ROOT/deployment/compose"
cp .env.shared.example .env.shared
$EDITOR .env.shared                # NETWORK_NAME, MONGO_HOST, ports, container names
chmod 600 .env.shared

# ------- Image availability -------
# 7. Either (a) build once, then reuse tags, or (b) pull from your registry
#    (a) Build:
cd "$REPO_ROOT/deployment/compose"
docker compose build backend frontend opportunity_center
#        (This step reuses the greenfield Dockerfiles without deploying the
#         greenfield stack. Only images are produced.)
#    (b) Pull:
# docker pull registry.example.com/arbicore-x-backend:0.1.0
# docker pull registry.example.com/arbicore-x-frontend:0.1.0
# docker pull registry.example.com/arbicore-x-opportunity-center:0.1.0

# ------- Boot ArbiCore X co-tenant -------
cd "$REPO_ROOT/deployment/compose"
docker compose --env-file .env.shared -f docker-compose.shared.yml up -d

# ------- Verify -------
docker compose --env-file .env.shared -f docker-compose.shared.yml ps
docker compose --env-file .env.shared -f docker-compose.shared.yml logs --tail=50 backend
curl -fs "http://127.0.0.1:$(grep '^BACKEND_HOST_PORT=' .env.shared | cut -d= -f2)/api/"

# ------- Wire the peer Caddy -------
#     Add the virtual-host block from § 7.1 (Caddyfile) OR set CADDY_* env
#     variables from § 7.2 and `docker compose up -d` again.

# ------- Final smoke test -------
curl -fs "https://arbicore.example.com/api/"
curl -sk "https://arbicore.example.com/" | head -20
curl -sk "https://arbicore.example.com/opportunity-center/" | head -20
```

---

## 9. Upgrade workflow

Upgrading in shared mode is decoupled from the peer stack — you can upgrade ArbiCore X without touching Strategy Factory.

```bash
cd "$REPO_ROOT/deployment/compose"

# 1. Backup the ArbiCore database (does NOT touch peer databases)
DB_NAME_VAL=$(grep '^DB_NAME=' .env.shared | cut -d= -f2)
docker exec factory-mongo mongodump --db="$DB_NAME_VAL" \
  --archive="/tmp/${DB_NAME_VAL}_$(date +%F).archive" --gzip
docker cp "factory-mongo:/tmp/${DB_NAME_VAL}_$(date +%F).archive" /var/backups/arbicore-x/

# 2. Pull or build the new images
docker pull registry.example.com/arbicore-x-backend:0.1.1
# (or rebuild via deployment/compose/)

# 3. Update image tags in .env.shared
sed -i 's/^BACKEND_IMAGE_TAG=.*/BACKEND_IMAGE_TAG=arbicore-x-backend:0.1.1/' .env.shared
sed -i 's/^FRONTEND_IMAGE_TAG=.*/FRONTEND_IMAGE_TAG=arbicore-x-frontend:0.1.1/' .env.shared
sed -i 's/^OPPORTUNITY_CENTER_IMAGE_TAG=.*/OPPORTUNITY_CENTER_IMAGE_TAG=arbicore-x-opportunity-center:0.1.1/' .env.shared

# 4. Recreate containers with the new images (rolling per-service)
docker compose --env-file .env.shared -f docker-compose.shared.yml up -d --no-deps --force-recreate backend
docker compose --env-file .env.shared -f docker-compose.shared.yml up -d --no-deps --force-recreate frontend
docker compose --env-file .env.shared -f docker-compose.shared.yml up -d --no-deps --force-recreate opportunity_center

# 5. Health-check
curl -fs "http://127.0.0.1:$(grep '^BACKEND_HOST_PORT=' .env.shared | cut -d= -f2)/api/"
docker compose --env-file .env.shared -f docker-compose.shared.yml ps

# 6. Caddy needs no changes: the peer's Caddyfile still points at the same host ports.
```

No migration downtime is expected across a patch bump (`0.1.0` → `0.1.1`). For minor bumps that involve schema migrations, follow `docs/UPGRADE.md § 4` on the peer VPS after step 1.

---

## 10. Rollback workflow

```bash
cd "$REPO_ROOT/deployment/compose"

# 1. Restore previous image tags in .env.shared
sed -i 's/^BACKEND_IMAGE_TAG=.*/BACKEND_IMAGE_TAG=arbicore-x-backend:0.1.0/' .env.shared
sed -i 's/^FRONTEND_IMAGE_TAG=.*/FRONTEND_IMAGE_TAG=arbicore-x-frontend:0.1.0/' .env.shared
sed -i 's/^OPPORTUNITY_CENTER_IMAGE_TAG=.*/OPPORTUNITY_CENTER_IMAGE_TAG=arbicore-x-opportunity-center:0.1.0/' .env.shared

# 2. Recreate
docker compose --env-file .env.shared -f docker-compose.shared.yml up -d --force-recreate

# 3. If schema/data corruption is suspected, restore from mongodump
DB_NAME_VAL=$(grep '^DB_NAME=' .env.shared | cut -d= -f2)
docker cp /var/backups/arbicore-x/${DB_NAME_VAL}_YYYY-MM-DD.archive factory-mongo:/tmp/
docker exec factory-mongo mongorestore --archive="/tmp/${DB_NAME_VAL}_YYYY-MM-DD.archive" --gzip --drop

# 4. Verify
curl -fs "http://127.0.0.1:$(grep '^BACKEND_HOST_PORT=' .env.shared | cut -d= -f2)/api/"
```

**What rollback CANNOT touch:** peer Mongo's other databases (e.g. `vqb`). `mongorestore --drop` above uses `--archive=` targeted at a single-DB dump; it only drops collections inside `arbicore_x`. Verify with:

```bash
docker exec factory-mongo mongosh --quiet --eval \
  'db.adminCommand({listDatabases:1}).databases.map(d=>({name:d.name,size:d.sizeOnDisk}))'
```

The peer's DB size should be unchanged before and after the restore.

---

## 11. Troubleshooting

### 11.1 `network vqb-network declared as external, but could not be found`

The peer stack hasn't been started yet, or the network name in `.env.shared` doesn't match the actual network.

```bash
docker network ls
grep '^NETWORK_NAME=' .env.shared
```

Start the peer or correct `NETWORK_NAME`.

### 11.2 Backend `MongoServerSelectionError: getaddrinfo ENOTFOUND factory-mongo`

The container name in `MONGO_HOST` doesn't match a container on the shared network.

```bash
docker network inspect "$NETWORK_NAME" --format '{{range .Containers}}{{.Name}}{{println}}{{end}}'
```

Use the exact name shown, or use its network alias.

### 11.3 Backend logs show `Authentication failed`

Peer Mongo has auth enabled and `MONGO_URL` in `.env.shared` is missing credentials.

```bash
# Set MONGO_URL explicitly
MONGO_URL=mongodb://arbicore:<pw>@factory-mongo:27017/?authSource=admin
```

### 11.4 Caddy returns 502 Bad Gateway

Check loopback ports are actually listening:

```bash
ss -tlnp | grep -E ':8101 |:8102 |:8103 '
# All three should be listening on 127.0.0.1.
```

If they aren't, `docker compose ps` will show a non-`healthy` state; inspect logs:

```bash
docker compose --env-file .env.shared -f docker-compose.shared.yml logs --tail=100 backend
```

### 11.5 Container name collision (`Conflict. The container name is already in use`)

Another deployment (staging, tenant-A) already uses the same container names. Prefix the *_CONTAINER_NAME variables in `.env.shared`:

```dotenv
BACKEND_CONTAINER_NAME=arbicore-x-staging-backend
FRONTEND_CONTAINER_NAME=arbicore-x-staging-frontend
OPPORTUNITY_CENTER_CONTAINER_NAME=arbicore-x-staging-opportunity-center
```

And the host ports so they don't collide either:

```dotenv
BACKEND_HOST_PORT=8201
FRONTEND_HOST_PORT=8202
OPPORTUNITY_CENTER_HOST_PORT=8203
```

### 11.6 Backend can reach Mongo but health check fails

Check that `DB_NAME` doesn't collide with peer's DB (the health endpoint asserts a small write on startup):

```bash
docker exec factory-mongo mongosh --quiet --eval \
  'db.adminCommand({listDatabases:1}).databases.map(d=>d.name)'
```

If `arbicore_x` doesn't appear yet, it will be created on the first successful backend write. If a *different* name appears that you didn't set, another ArbiCore instance is using it — reconcile before proceeding.

### 11.7 `docker compose up` says `services.mongo is not defined`

You are using the *greenfield* compose file, not the shared one. Ensure `-f docker-compose.shared.yml` is passed and you are in the `deployment/compose/` directory.

### 11.8 Peer stack breaks after ArbiCore X boot

Inspect — no ArbiCore action affects the peer directly, so a peer regression *should not* be caused by an ArbiCore boot. Possible indirect causes:

- Host CPU/memory pressure from ArbiCore. Lower `BACKEND_CPU_LIMIT` / `BACKEND_MEM_LIMIT` in `.env.shared`.
- Peer Mongo overloaded by ArbiCore query rate. Check with `mongotop` and consider tuning scanner concurrency in ArbiCore's `.env` (`ARBICORE_SCANNER_*` toggles).
- Peer Caddy misconfigured (a bad new virtual-host block breaks the whole config on reload). Test with `caddy validate --config /etc/caddy/Caddyfile` before reloading.

### 11.9 How to fully remove ArbiCore X without touching the peer

```bash
cd "$REPO_ROOT/deployment/compose"
docker compose --env-file .env.shared -f docker-compose.shared.yml down
# Optional: also remove the log volume
docker volume rm "$(grep '^LOGS_VOLUME_NAME=' .env.shared | cut -d= -f2)"
# Optional: drop the ArbiCore database
docker exec factory-mongo mongosh --eval "use $(grep '^DB_NAME=' .env.shared | cut -d= -f2); db.dropDatabase()"
# Remove the Caddy virtual-host block from the peer Caddyfile and reload.
```

The peer network, peer Mongo, peer Caddy, and all peer data remain untouched.

---

## 12. Compatibility notes

| Item | Shared profile | Greenfield profile | Realignment profile |
|---|---|---|---|
| Owns the Docker network | No | Yes | Yes |
| Owns MongoDB | No | Yes | Yes |
| Owns reverse proxy | No | Yes (nginx) | Yes (nginx) |
| Owns TLS certs | No | Yes (Certbot) | Yes (Certbot) |
| Compatible with peer Caddy | Yes | No (port conflict on 80/443) | No |
| Compose file | `docker-compose.shared.yml` | `docker-compose.yml` | Uses the audited realignment toolkit |
| Env template | `.env.shared` + bundle-root `.env` | bundle-root `.env` only | Uses the toolkit's own env files |

---

## 13. Guarantees

1. **Additive only.** Adopting shared mode does not modify greenfield or realignment profiles.
2. **No side effects on peer.** ArbiCore X never creates the network, Mongo, Caddy, or Certbot; never writes to peer databases; never opens public ports.
3. **Fully env-configurable.** Network name, Mongo host/port/URL, DB name, host ports, host bind addresses, container names, network aliases, image tags, resource limits — all overridable via `.env.shared` without editing the compose file.
4. **Idempotent.** Running `docker compose ... up -d` twice leaves the same state.
5. **Loopback-only ports.** Backend / frontend / opportunity_center bind to `127.0.0.1` by default. Public access is exclusively via the peer's reverse proxy.
