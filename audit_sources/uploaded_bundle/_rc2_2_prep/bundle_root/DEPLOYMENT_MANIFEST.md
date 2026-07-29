# ArbiCore X — DEPLOYMENT_MANIFEST.md

**The authoritative deployment record.** Regenerated on every bundle rebuild.

---

## 1. Bundle identity

| Field | Value |
|---|---|
| Bundle version         | `arbicore-x-vps-bundle-0.1.0-rc2.2` |
| Build date (UTC)       | `2026-07-28T15:00:00Z` (RC2.2 dependency-resolution patch) |
| Total files            | 864 (RC2.1 862 + 2 new files under app/frontend/: yarn.lock + .npmrc) |
| Total size (excl `.git`) | ~ 8.75 MB |
| Assembly method        | Merge: GitHub HEAD (`app/`) + audited tarball (`infrastructure/realignment/`) + new authoring (compose, nginx, certbot, docs) + **RC2 additions: env templates + shared-infrastructure profile** + **RC2.1 additions: packaging fix (Dockerfiles + .dockerignore + compose build blocks)** + **RC2.2 additions: frontend reproducibility (yarn.lock + .npmrc)** |
| Assembled by           | Emergent E1 audit + build session |

## 2. Application source provenance (`app/`)

| Field | Value |
|---|---|
| Source repository       | https://github.com/raghugr2013-lgtm/ArbiCoreX-V01 |
| Branch                  | `main` (default) |
| Commit SHA (full)       | `__APP_SOURCE_SHA_RC2_2__` (RC2.2 candidate: adds `frontend/yarn.lock` + `frontend/.npmrc`; APPLY.sh fills this in) |
| Commit SHA (short)      | `__APP_SOURCE_SHA_RC2_2_SHORT__` |
| Byte-identity vs source | **IDENTICAL** (per-file `diff -qr` empty) |
| Subtree hash (SHA-256)  | *(recomputed on rebuild — RC2.2 subtree differs from RC1/RC2/RC2.1 by exactly 2 new files under app/frontend/)* |
| Change vs RC2.1         | **+2 files** — `app/frontend/yarn.lock` (canonical yarn 1 resolution; 12,739 lines) and `app/frontend/.npmrc` (`legacy-peer-deps=true`). No package.json, no source, no config change. |

Verify locally:

```bash
diff -qr /path/to/ArbiCoreX-V01/backend  app/backend
diff -qr /path/to/ArbiCoreX-V01/frontend app/frontend
diff -qr /path/to/ArbiCoreX-V01/opportunity_center app/opportunity_center
# All should be empty.
```

## 3. Operations toolkit provenance (`infrastructure/realignment/arbicore-x-deploy/`)

| Field | Value |
|---|---|
| Original artifact       | `arbicore-x-deploy.tar.gz` (uploaded 2026-07-24) |
| Original tarball SHA-256| `33ce217a74354df347d42bd6e3701f0810732f82244453a98732f5f49e8fbbf3` |
| Byte-identity vs source | **IDENTICAL** (per-file `diff -qr` empty) |
| Subtree hash (SHA-256)  | `ac00fb1d787646c44324e8ca514e5fe034b21e81b714b044a7783fe0e97e7067` |
| Reviewer sign-off       | `docs/audit/legacy/15_bundle_technical_review.md` (7-area PASS, 11/11 static checks green) |
| Change vs RC1           | **None** — realignment toolkit byte-identical to RC1 |

## 4. Docker image versions (built by greenfield compose)

| Image | Tag (default) | Base | Non-root? | Labels |
|---|---|---|---|---|
| Backend             | `arbicore-x-backend:0.1.0`             | `python:3.11-slim` | Yes (uid 1001) | `arbicore.gitsha`, `arbicore.schema=v1`, `arbicore.role=backend` |
| Frontend            | `arbicore-x-frontend:0.1.0`            | `nginx:1.25-alpine` (stage-2) from `node:20-alpine` build | Yes (uid 101 nginx) | `arbicore.gitsha`, `arbicore.role=frontend` |
| Opportunity Center  | `arbicore-x-opportunity-center:0.1.0`  | `nginx:1.25-alpine` (stage-2) from `node:20-alpine` build | Yes (uid 101 nginx) | `arbicore.gitsha`, `arbicore.role=opportunity_center` |
| Nginx (reverse)     | `nginx:1.25-alpine`                    | Alpine 3.19 | uid 101 nginx | `arbicore.role=nginx` |
| Mongo               | `${MONGO_IMAGE:-mongo:4.4}` (`mongo:4.4` default, `mongo:6.0`/`7.0` supported) | Debian/Alpine | uid 999 mongodb | `arbicore.role=mongo` |
| Certbot             | `certbot/certbot:latest`               | Alpine | root (safe: only writes /etc/letsencrypt) | `arbicore.role=certbot` |

Image tags remain `0.1.0` in RC2 because the underlying `app/` subtree is unchanged from RC1.

## 5. Component versions (pinned)

| Component | Pinned version | Source |
|---|---|---|
| Python                     | 3.11 (slim)              | `infrastructure/greenfield/backend/Dockerfile` |
| Node                       | 20 (alpine)              | frontend + opportunity_center Dockerfiles |
| Nginx                      | 1.25 (alpine)            | frontends + reverse proxy |
| MongoDB                    | 4.4 (default; override via `MONGO_IMAGE`) | greenfield compose |
| FastAPI                    | 0.110.1                  | `requirements.prod.txt` |
| Motor                      | 3.3.1                    | `requirements.prod.txt` |
| pymongo                    | 4.6.3                    | `requirements.prod.txt` |
| bcrypt                     | 4.1.3                    | `requirements.prod.txt` |
| cryptography               | 48.0.0                   | `requirements.prod.txt` |
| httpx                      | 0.28.1                   | `requirements.prod.txt` |
| uvicorn                    | 0.25.0                   | `requirements.prod.txt` |
| pydantic                   | ≥ 2.6.4                  | `requirements.prod.txt` |
| Certbot                    | latest                   | greenfield compose |
| Docker Engine (host)       | ≥ 24.0                   | prerequisites |
| docker compose (host)      | v2                       | prerequisites |
| Bundle Python requirements | `requirements.prod.txt` (120 lines, no `emergentintegrations`, no `litellm`) | verified excluded via grep |

## 6. ArbiCore X schema

| Field | Value |
|---|---|
| Schema version              | `v1` (Phase C / Wave 5)                     |
| Core collections            | 14 (opportunities, outcomes, state_snapshots, audit_log, route_stats, provenance_audit, signal_metrics, wallet_metrics, temporal_sequences, sequence_patterns, regime_snapshots, entities, entity_refs, entity_clusters) |
| Operational collections     | ~6 (scanner_config, scanner_state, discovery_candidates, discovery_source_metrics, venue-capability cache, …) |
| Effective TTL indexes       | 4 (`state_snapshots.captured_at_dt`=30d, `audit_log.ts_dt`=90d, `temporal_sequences.discovered_at_dt`=90d, `regime_snapshots.captured_at_dt`=90d) |
| Non-functional TTL (advisory)| `discovery_candidates.expires_at` (float epoch — see audit doc 13 §4) |
| Full inventory              | `app/backend/arbicore/data/mongo/arbicore_collections.py` + `docs/audit/legacy/13_production_readiness_report.md §3` |

## 7. New authoring inventory (production components not in source)

| File | Purpose |
|---|---|
| `.env.example`, `.env.production.example`, `.env.development.example` | Canonical + prod-locked + dev-permissive env templates (**restored in RC2**; missing from RC1 tarball despite documentation references) |
| `infrastructure/greenfield/backend/Dockerfile` (+ `.dockerignore`) | Hardened backend image (non-root, provenance labels) |
| `infrastructure/greenfield/backend/requirements.prod.txt` | 120-line pinned prod deps (grep-verified: no `emergentintegrations`, no `litellm`, no dev tools) |
| `infrastructure/greenfield/backend/requirements.dev.txt` | Dev superset with pytest, black, flake8, isort, mypy, ruff |
| `infrastructure/greenfield/frontend/Dockerfile` + `nginx-spa.conf` | Multi-stage node → nginx-alpine, SPA fallback. **RC2.1:** rewritten so the build context is the bundle root; COPY paths use `app/frontend/*` + `infrastructure/greenfield/frontend/nginx-spa.conf`. Install step falls through `yarn install --frozen-lockfile` → `npm ci` → `npm install` depending on lockfile presence (`yarn.lock` is optional in a clean checkout). |
| `infrastructure/greenfield/opportunity_center/Dockerfile` + `nginx-spa.conf` | Same pattern, Vite target. **RC2.1:** same packaging fix as frontend (bundle-root context + conditional package-manager selection). |
| **`.dockerignore` (bundle root)** | **RC2.1:** denies `node_modules`, `.git`, `docs`, `screenshots`, coverage/cache dirs, Python bytecode, real `.env` files, and the realignment + shared-infrastructure trees. Keeps the widened greenfield build context lean. |
| `infrastructure/greenfield/docker-compose.yml` | 6-service stack: mongo + backend + 2 frontends + nginx + certbot, resource-limited, log-capped. **RC2.1:** `frontend` and `opportunity_center` `build:` blocks widened — `context: ../..` (bundle root) + `dockerfile: infrastructure/greenfield/*/Dockerfile` — so nginx-spa.conf is reachable from the Docker build context. Backend build block unchanged. Runtime service semantics unchanged. |
| **`infrastructure/shared-infrastructure/docker-compose.shared.yml`** | **RC2:** shared-infrastructure profile — backend + operator UI + opportunity center attached to an external network; no Mongo / nginx / Certbot; loopback ports for peer Caddy proxy |
| **`infrastructure/shared-infrastructure/.env.shared.example`** | **RC2:** wiring template for shared profile (network name, Mongo host / port / URL, DB name, host ports, container names, network aliases, image tags, resource limits, optional Caddy labels) |
| **`infrastructure/shared-infrastructure/README.md`** | **RC2:** short pointer + quick-start |
| `infrastructure/nginx/nginx.conf` | Top-level nginx (worker + http block) |
| `infrastructure/nginx/conf.d/arbicore-x.conf.template` | Domain-templated site config (HTTPS + HTTP redirect + WS + /api + /opportunity-center + rate limits) |
| `infrastructure/nginx/snippets/{security_headers,ssl,gzip}.conf` | HSTS + CSP + Mozilla Intermediate TLS + gzip types |
| `infrastructure/ssl/init-letsencrypt.sh` + `renew.sh` + `cronjob.example` | Cert issuance (staging-first) + auto-renewal |
| `infrastructure/backups/backup-cron.sh` | Rotation + optional off-host push via rclone |
| `infrastructure/monitoring/uptime-probe.sh` | External-style TLS + HTTP probe |
| `scripts/install.sh` | Guarded greenfield installer (refuse-if-exists) |
| `scripts/upgrade.sh` | Thin wrapper → realignment toolkit |
| `scripts/healthcheck.sh` | Aggregate probe (containers + HTTP + delegates to uptime-probe) |
| `docs/INSTALL.md`, `UPGRADE.md`, `ROLLBACK.md`, `BACKUP_RESTORE.md`, `SSL.md`, `SECURITY.md`, `OPERATIONS.md`, `TROUBLESHOOTING.md` | 8 operator guides |
| **`docs/SHARED_INFRASTRUCTURE.md`** | **RC2:** shared-infrastructure profile guide (13 sections: architecture, topology, Mongo reuse, DB isolation, port mapping, Caddy integration, deploy / upgrade / rollback / troubleshooting) |
| `README.md`, `VERSION`, `DEPLOYMENT_MANIFEST.md`, `DEPRECATIONS.md` | Bundle-root entrypoints |
| **`RELEASE_NOTES_v0.1.0-rc2.1.md`** | **RC2.1:** packaging patch release notes (RC2 `RELEASE_NOTES_v0.1.0-rc2.md` and RC1 `RELEASE_NOTES_v0.1.0.md` both preserved as-is for historical record) |
| **`RELEASE_NOTES_v0.1.0-rc2.md`** | **RC2:** release notes for this candidate (RC1 `RELEASE_NOTES_v0.1.0.md` preserved as-is for historical record) |

## 8. Compatibility matrix

| Requirement | Greenfield | Realignment | **Shared (RC2)** |
|---|:-:|:-:|:-:|
| Fresh VPS (nothing else installed) | ✅ | ❌ | ❌ |
| Existing ArbiCore install to upgrade | ❌ | ✅ | ❌ |
| Peer stack already on the VPS | ❌ | ❌ | ✅ |
| Owns Docker network | ✅ | ✅ | ❌ (attaches by name) |
| Owns MongoDB | ✅ | ✅ | ❌ (connects via `MONGO_HOST`) |
| Owns reverse proxy | ✅ (nginx) | ✅ | ❌ (peer Caddy) |
| Owns TLS (Certbot) | ✅ | ✅ | ❌ (peer owns TLS) |
| Publishes public ports 80/443 | ✅ | ✅ | ❌ (loopback only) |
| Compose file | `infrastructure/greenfield/docker-compose.yml` | audited realignment toolkit | `infrastructure/shared-infrastructure/docker-compose.shared.yml` |
| Env templates | bundle-root `.env` (from `.env.production.example`) | toolkit-provided | bundle-root `.env` + `infrastructure/shared-infrastructure/.env.shared` |
| Multi-tenant on one VPS | ❌ | ❌ | ✅ (prefix container names + host ports per tenant) |
| Data-loss risk on install | Low | Guarded (canary + rollback) | None (never touches peer data) |

## 9. Release checksums

| Artifact | SHA-256 | Notes |
|---|---|---|
| `arbicore-x-vps-bundle-0.1.0-rc2.2.tar.gz` | *(pending regeneration by `build_and_tag.sh`)* | Regenerated after this commit lands |
| `arbicore-x-vps-bundle-0.1.0-rc2.2.SHASUMS` | — (checksum file itself, not self-referential) | Contains the SHA-256 above |

The SHASUMS file lives at the repo root, one level above `$BUNDLE_ROOT`, matching the RC1 convention.

**Historical reference:**
- RC1 asset `arbicore-x-vps-bundle-0.1.0.tar.gz` SHA-256 = `90837cb5613ee79d1838a58e0beef62f2c958394caf35eb11e3bed8c6664881f`.
- RC2 asset was superseded by RC2.1 (packaging failure prevented `docker compose build` from succeeding).
- RC2.1 asset was superseded by RC2.2 (npm ERESOLVE on peer-dep conflict prevented the fallback install path from resolving on strict-peer runners).

## 10. Invariants at build time

1. **Byte-identity of `app/` vs `ArbiCoreX-V01@f64f7bf`** — enforced by `diff -qr`.
2. **Byte-identity of `infrastructure/realignment/arbicore-x-deploy/` vs audited tarball** — enforced by SHA-256 match of `arbicore-x-deploy.tar.gz`.
3. **No `emergentintegrations` or `litellm` in `requirements.prod.txt`** — grep-verified 0 hits.
4. **All Docker images use non-root users** — `USER 1001` (backend) or `USER 101` (nginx-alpine) verified in Dockerfiles.
5. **All hard-coded FQDNs/IPs eliminated** — `envsubst` at nginx boot; `.env` interpolation in compose.
6. **Scanners dormant by default** — all four `ARBICORE_SCANNER_*_ARB` env vars ship `false` in every template.
7. **RC2 additive-only** — `diff -qr` between RC2's `app/`, `infrastructure/greenfield/`, `infrastructure/realignment/` and RC1's corresponding trees is empty.
8. **RC2.1 packaging-only** — `diff -qr` between RC2.1's `app/` and RC2's `app/` is empty; only `infrastructure/greenfield/{frontend,opportunity_center}/Dockerfile`, `infrastructure/greenfield/docker-compose.yml` (two build blocks), and the new bundle-root `.dockerignore` differ.
9. **RC2.2 dependency-resolution-only** — `diff -qr` between RC2.2's `app/` and RC2.1's `app/` produces exactly two new files (`app/frontend/yarn.lock` + `app/frontend/.npmrc`) and no other differences. No package.json changes, no source changes, no config changes.

## 11. Future rebuilds

Unchanged from RC1. Re-running the bundle-assembly process against `ArbiCoreX-V01@<newSHA>` regenerates the tarball; RC2's env templates, shared-infrastructure profile, and RC2.1's packaging fixes will carry forward automatically (they are checked into the release repo, not sourced from the dev repo).
