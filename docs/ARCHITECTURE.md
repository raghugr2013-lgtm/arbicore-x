# ArbiCore X — Architecture

Current-state description of the ArbiCore X platform. Single canonical reference for how the application is built and how it is deployed. Historical design analyses are out of scope for this document; see [`MIGRATION_SUMMARY.md`](MIGRATION_SUMMARY.md) for provenance.

---

## 1. High-level topology

ArbiCore X is a **single-tenant, single-VPS** platform (a shared-infrastructure profile exists for the multi-tenant case). A production install brings up six containers on one Docker bridge network:

```
                          Internet
                              |
                        :80 / :443 (public)
                              |
                    +---------+---------+
                    |    nginx (TLS)    |
                    |  reverse proxy    |
                    +-----+--------+----+
                          |        |        (all internal)
              +-----------+        +----------+---------+
              |                                          |
      +-------+-------+   +----------------+    +--------+---------+
      |    backend    |   |    frontend    |    | opportunity_    |
      |  FastAPI :8001|   | nginx-alpine   |    | center (Vite)    |
      +-------+-------+   +----------------+    +------------------+
              |                    (all serve static assets over :80 in the internal net)
              v
      +-------+-------+
      |     mongo     |
      |  (named vol)  |
      +---------------+

      +---------------+
      |    certbot    |   (renewal loop, no publish)
      +---------------+
```

**Public surface:** ports 80 and 443 on the host, both terminated by nginx. Nothing else is published. Backend, frontends, and mongo are unreachable from the internet directly.

**Data anchor:** Mongo binds a named Docker volume (`arbicore-x-mongo-data`). It survives container rebuilds, upgrades, and restarts. The installer refuses to install on top of an existing volume.

## 2. Application

### Backend — `app/backend/`
- **Runtime:** Python 3.11-slim, FastAPI 0.110.1, uvicorn 0.25 (`--workers 1`), Motor 3.3.1, pymongo 4.6.3, httpx 0.28.1.
- **Entry point:** `server.py` → `uvicorn server:app --host 0.0.0.0 --port 8001`.
- **Structure:**
  - `arbicore/` — the scanner core. Six scanner families (D-1 discovery, D-2 funding, D-3 DEX, D-4 launch, D-5 cross-chain, D-6 flash-loan). Contains `data/` (Mongo repos + provenance registry), `intel/` (wallet enrichment + entity resolver), `intelligence/` (audit log + confidence + scoring + capital validators), `learning/` (calibration + weights + outcomes), `models/` (canonical Pydantic types + enums), `routes/` (`arbicore.py` + `scanners.py`), `runtime/composition.py` (DI root, event bus, regime worker), `scanners/` (per-family source providers + verifier + gates), `shadow/` (mapper + observer).
  - `connectors/` — venue connectors (bitmart, coinstore, gate, mexc, xt, sim, evm_wallet, plus stubs).
  - `core/`, `engines/`, `diagnostics/`, `routes/` (alerts, auth, execution, observation, portal, portfolio, vault, venues), `services/` (auth, balances, capability, collector, db, discovery, exchange_private, execution/, health_analytics, holdprob, key_health, observation, portal_price, seed, telegram_alerts, vault, venue_monitor, ws_manager).
  - `tests/` — ~200 pytest files covering all scanner families, Wave-1 through Wave-5 endpoints, and hotfix regressions.
- **Runtime image:** `arbicore-x-backend:1.0.0`, non-root uid 1001, provenance labels (`arbicore.role=backend`, `arbicore.gitsha`, `arbicore.schema=v1`). Healthcheck: `curl -fs http://localhost:8001/api/`.
- **Env:** consumed at runtime via `env_file: ../../.env`. Never baked into the image.

### Frontend (operator UI) — `app/frontend/`
- **Runtime:** React 19 + CRACO + Tailwind + shadcn/ui.
- **Package manager:** yarn 1.22.22 (declared in `package.json` as `packageManager`). `yarn.lock` is committed and canonical; `.npmrc` sets `legacy-peer-deps=true` as a fallback safety net.
- **Build:** multi-stage — `node:20-alpine` → `nginx:1.25-alpine`. Runtime image serves the CRA `build/` directory on internal :80. `REACT_APP_BACKEND_URL` is baked at build time into the JS bundle.
- **Runtime image:** `arbicore-x-frontend:1.0.0`, non-root uid 101.

### Opportunity Center — `app/opportunity_center/`
- **Runtime:** Vite + React + Tailwind. Independent SPA.
- **Build:** multi-stage — `node:20-alpine` → `nginx:1.25-alpine`. Runtime image serves the Vite `dist/` on internal :80. `VITE_BACKEND_URL` baked at build time.
- **Runtime image:** `arbicore-x-opportunity-center:1.0.0`, non-root uid 101.

## 3. Deployment

Every non-application component lives in `deployment/`. Nothing under `deployment/` is referenced by application code.

### Docker
- `deployment/docker/backend/Dockerfile` — python:3.11-slim, non-root uid 1001, staged `requirements.prod.txt` install with `build-essential` purged after.
- `deployment/docker/frontend/Dockerfile` — multi-stage node → nginx-alpine, `yarn --frozen-lockfile` (with npm fallback), `USER 101`.
- `deployment/docker/opportunity_center/Dockerfile` — same multi-stage pattern, `dist/` output.

### Compose profiles (`deployment/compose/`)
- `docker-compose.yml` — greenfield 6-service stack. Default.
- `docker-compose.shared.yml` — optional shared-infrastructure profile (peer TLS/mongo).
- `.env.shared.example` — wiring template for the shared profile.

### Reverse proxy (`deployment/nginx/`)
- `nginx.conf` — worker + http block, sensible defaults.
- `conf.d/arbicore-x.conf.template` — the site config. `envsubst` renders `${DOMAIN}` at boot.
- `snippets/security_headers.conf` — HSTS + CSP + X-Frame-Options + X-Content-Type-Options + Referrer-Policy.
- `snippets/ssl.conf` — Mozilla Intermediate TLS profile.
- `snippets/gzip.conf` — gzip types + compression level.

**Route table (nginx → services):**

| Public path | Backend target |
|---|---|
| `/`, `/static/…` | frontend :80 |
| `/opportunity-center/…` | opportunity_center :80 |
| `/api/…` | backend :8001 |
| `/api/ws/…` (WebSocket) | backend :8001 (Upgrade + Connection headers passed) |
| `/nginx-health` | 200 (health hairpin) |
| `/.well-known/acme-challenge/…` | certbot webroot |

### TLS (`deployment/ssl/`)
- `init-letsencrypt.sh` — first-run cert issuance. Staging cert first (unless `LETSENCRYPT_MODE=prod`), then flip to prod once the staging test succeeds.
- `renew.sh` — renewal invocation (also runs inside the `certbot` container as a 12h loop).
- `cronjob.example` — sample host-side cron.

### Backups (`deployment/backups/`)
- `backup.sh` — `mongodump --archive --gzip` from `arbicore-x-mongo`. Writes to `./backups/arbicore-x_YYYYMMDD_HHMMSS.archive.gz`. Retention: last 14 files.
- `backup-cron.sh` — same, plus optional `rclone` push to a remote target.
- `restore.sh` — `mongorestore --archive --gzip --drop` (interactive confirmation).

### Monitoring (`deployment/monitoring/`)
- `healthcheck.sh` — internal aggregate probe (containers + HTTP + TLS).
- `uptime-probe.sh` — external-style probe against `https://${DOMAIN}` (cert expiry, response codes).
- `snapshot.sh` — point-in-time JSON snapshot of `arbicore_*` collections + scanner state + last 10 outcomes.
- `shadow_start.sh` / `shadow_abort.sh` — data-collection window management (Wave-1 heritage; still used for controlled observation windows).

### Upgrade toolkit (`deployment/upgrade/`)
Audit-heritage in-place backend upgrade with canary + rollback. 11 numbered steps + `99_rollback.sh`. `Makefile`-driven (`make detect / preflight / backup / index-audit / build / cutover / canary / validate / snapshot / rollback`). Invoked via top-level `scripts/upgrade.sh`.

### Operator scripts (`scripts/`)
- `install.sh` — 9-phase guarded greenfield installer. See [`INSTALL.md`](INSTALL.md).
- `upgrade.sh` — thin wrapper over `deployment/upgrade/`. See [`UPGRADE.md`](UPGRADE.md).
- `healthcheck.sh` — aggregate probe. Wraps `deployment/monitoring/healthcheck.sh`.
- `backup.sh`, `restore.sh` — thin wrappers over `deployment/backups/`.

## 4. Configuration

Every operational value comes from an env variable. Every env variable is documented in `.env.example` (canonical, 231 lines) and mirrored in `.env.production.example` (locked defaults) and `.env.development.example` (permissive defaults).

**Required at install time** (validated by `scripts/install.sh`):

| Var | Purpose |
|---|---|
| `DOMAIN` | Public domain the stack serves |
| `LETSENCRYPT_EMAIL` | Contact for the ACME account |
| `JWT_SECRET` (≥32 chars) | JWT signing key |
| `VAULT_KEY` (≥32 chars) | Vault symmetric key |
| `MONGO_URL` | `mongodb://mongo:27017` (compose service name) |
| `DB_NAME` | Recommended: `arbicore_x_prod` |
| `CORS_ORIGINS` | UI origin |

**Optional overrides:** `MONGO_IMAGE`, `LETSENCRYPT_MODE`, `GITSHA`, `BACKEND_IMAGE_TAG`, `FRONTEND_IMAGE_TAG`, `OPPORTUNITY_CENTER_IMAGE_TAG`, `REACT_APP_BACKEND_URL`, all `ARBICORE_SCANNER_*_ARB` toggles (default `false`; operators enable per family).

## 5. Data model (Mongo)

| Concern | Collections (representative) |
|---|---|
| Core (schema v1) | `arbicore_opportunities`, `arbicore_outcomes`, `arbicore_state_snapshots`, `arbicore_audit_log`, `arbicore_route_stats`, `arbicore_provenance_audit`, `arbicore_signal_metrics`, `arbicore_wallet_metrics`, `arbicore_temporal_sequences`, `arbicore_sequence_patterns`, `arbicore_regime_snapshots`, `arbicore_entities`, `arbicore_entity_refs`, `arbicore_entity_clusters` (14) |
| Operational | `arbicore_scanner_config`, `arbicore_scanner_state`, `arbicore_discovery_candidates`, `arbicore_discovery_source_metrics`, venue-capability cache, … (~6) |
| TTL indexes | `state_snapshots.captured_at_dt` = 30d, `audit_log.ts_dt` = 90d, `temporal_sequences.discovered_at_dt` = 90d, `regime_snapshots.captured_at_dt` = 90d (4 effective TTLs) |
| Advisory TTL | `discovery_candidates.expires_at` (float epoch) |

Schema version is `v1`. Every backend image carries `arbicore.schema=v1` as a label.

## 6. Invariants

Enforced by the installer, the compose file, or the Dockerfiles — not by convention:

1. Mongo data lives in the named volume `arbicore-x-mongo-data`. Installer refuses to overwrite.
2. Every runtime process is non-root.
3. No secrets are baked into any image.
4. No hard-coded domain / FQDN / IP anywhere; all domain-scoped values go through `${DOMAIN}` and `envsubst`.
5. Scanners are dormant by default (`ARBICORE_SCANNER_*_ARB=false`); operators enable per family.
6. `requirements.prod.txt` is grep-clean of `emergentintegrations`, `litellm`, and dev tools.
7. Every image ships provenance labels: `arbicore.role`, `arbicore.schema`, `arbicore.gitsha`.
8. Every service has a healthcheck, resource limits, and capped logs.
9. Backend uses `--workers 1` (single-worker scanner runtime).
10. Frontend and opportunity_center images bake `REACT_APP_BACKEND_URL` / `VITE_BACKEND_URL` at build time — runtime changes to those values require rebuild.

## 7. Retired surfaces

The following legacy endpoints are preserved for backward compatibility but no longer serve their original purpose:

- `GET /api/arbicore/release/manifest`
- `GET /api/arbicore/release/bundle`

Both return `{"status":"retired", "message":"…", "since_version":"1.0.0"}`. The historical bundle download flow has been replaced by direct `git clone` from this canonical repository. See `app/backend/arbicore/routes/opportunity_center.py` for the exact response and [`MIGRATION_SUMMARY.md`](MIGRATION_SUMMARY.md) §5 for rationale.

## 8. Version and release model

- SemVer 2.0 (`vMAJOR.MINOR.PATCH`).
- First canonical baseline: `v1.0.0`.
- Releases produced by `git tag` on `main` + GitHub release. No side-loaded release bundles.
- See [`ROADMAP.md`](ROADMAP.md) for the release process in detail.
