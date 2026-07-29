# ArbiCore X — Phase 1: Deployment Architecture Understanding

**Phase:** 1 (Exploration & Understanding) · **Status:** COMPLETE · **Next:** Phase 1 checkpoint (your approval) → Phase 2 (Design)
**Scope:** read-only exploration of `ArbiCoreX-V01`, `arbicore-x-vps-bundle`, and `_rc2_2_prep.tar.gz` overlay.
**No writes performed.** No repository modified.

---

## 0. Sources actually reviewed (with provenance)

| Source | Location on disk | HEAD / Version | Trust level for this phase |
|---|---|---|---|
| Application repo | `/app/audit_sources/app_repo/` | commit `f64f7bf` "Auto-generated changes", 1 commit in history (shallow clone) | Ground truth for **application code** |
| VPS Bundle repo | `/app/audit_sources/vps_bundle_repo/` | HEAD `90a296d` on `main`; tags `v0.1.0-rc1`, `v0.1.0-rc2`, `v0.1.0-rc2.2` (no `rc2.1` tag despite release notes existing); bundle-root at `arbicore-x-vps-bundle/`, `VERSION = arbicore-x-vps-bundle-0.1.0-rc2.2` | Ground truth for **deployment infrastructure** |
| RC2.2 overlay | `/app/audit_sources/uploaded_bundle/_rc2_2_prep/` | patch package (12 entries) | Supplemental only — describes intent, not canonical |

Both GitHub repos are now public and successfully cloned anonymously.

---

## 1. Application architecture (from `ArbiCoreX-V01@f64f7bf`)

### 1.1 Tech stack
- **Backend**: Python 3.11 · FastAPI 0.110.1 · Motor 3.3.1 · pymongo 4.6.3 · httpx 0.28.1 · uvicorn 0.25.0 · bcrypt 4.1.3 · cryptography 48.0.0
- **Data store**: MongoDB (compose-pinned default `mongo:4.4`; overridable to 6.0/7.0 on AVX-capable hosts via `MONGO_IMAGE`)
- **Frontend (operator UI)**: React 19 · CRACO · Tailwind · shadcn/ui (`components.json` present) · **package manager: yarn 1.22.22** (declared in `package.json`)
- **Opportunity Center (analytics UI)**: Vite · React · Tailwind (separate SPA)
- **Tests**: pytest, ~200 test files, D-1 → D-6 scanner families + Wave-1 → Wave-5 endpoints

### 1.2 Backend module tree (top level under `backend/`)
`arbicore/` (core scanner engine — data + intel + intelligence + learning + models + routes + runtime + scanner + scanners + shadow), `connectors/` (bitmart, coinstore, evm_wallet, gate, mexc, xt, sim, stubs), `core/`, `diagnostics/`, `engines/`, `routes/` (alerts, auth, execution, observation, portal, portfolio, vault, venues), `services/` (auth, balances, capability, collector, db, discovery, exchange_private, execution/, health_analytics, holdprob, key_health, observation, portal_price, seed, telegram_alerts, vault, venue_monitor, ws_manager), `scripts/`, `tests/`, `server.py` (FastAPI entry), `requirements.txt`, `reset_admin.py`, `conftest.py`.

### 1.3 Frontend
CRACO-based CRA app; API base URL from `REACT_APP_BACKEND_URL` **baked at build time** into the JS bundle (standard CRA behavior). `craco.config.js`, `tailwind.config.js`, `components.json`, `plugins/health-check/`.

**Reproducibility gap in app repo:** `frontend/yarn.lock` and `frontend/.npmrc` are **missing** from `ArbiCoreX-V01@f64f7bf`. They exist in the VPS bundle repo (RC2.2 additions), but Step 1 of the RC2.2 two-step workflow (commit to app repo) was never completed. On a clean `docker compose build`, the frontend build falls through to `npm ci`/`npm install`, which hits `npm ERESOLVE` on `react-day-picker@8.10.1` (peer-requires `date-fns@^2||^3`) vs installed `date-fns@4.1.0`.

### 1.4 Opportunity Center
Vite SPA, small (~10 files). Simple `App.jsx`, pages (Home, Analytics, Opportunities, WalletIntelligence, SystemHealth, Login), `lib/api.js`, standard Vite/Tailwind config.

### 1.5 App-repo git hygiene issues
- **Only one commit** in history (`f64f7bf` "Auto-generated changes") — no meaningful history.
- **`release_bundle/` is tracked in git but also listed in `.gitignore`** — committed before being ignored. Any subsequent edits to it are silently untracked. `release_bundle/arbicore-x/` inside the app repo is an **older (2026-02-23) 2-service shadow deployment bundle**, entirely superseded by the VPS Bundle repo — see §4.
- `release_bundle/arbicore-x-deployment-bundle.zip` referenced from `backend/arbicore/routes/opportunity_center.py` as a downloadable release artifact — legacy delivery mechanism, superseded by git-based distribution.
- `README.md` = "# Here are your Instructions" (Emergent template — never customized).

---

## 2. Deployment architecture (from `arbicore-x-vps-bundle@main`)

### 2.1 Layout note (important)
The repo is laid out **nested**, not flat: everything production-relevant lives inside `arbicore-x-vps-bundle/`. The repo root itself contains substantial **Emergent-session leakage** that is **not** part of the bundle:

| Path at repo root | Nature |
|---|---|
| `arbicore-x-vps-bundle/` | ✅ The actual bundle — this is the canonical content |
| `audit_output/00_AUDIT_REPORT.md` (28KB), `01_REPO_AUDIT_REPORT.md` (40KB) | ❌ Prior audit-session scratch |
| `audit_workspace/` (`app_bundle/`, `deploy_bundle/`, `frontend_bundle/`, `github/`) | ❌ Prior audit-session scratch |
| `backend/` (stub: `server.py`, `pytest.ini`, `requirements.txt`) | ❌ Stub session-init noise |
| `frontend/` (near-empty CRA scaffold) | ❌ Stub session-init noise |
| `memory/` (only `.gitkeep`), `tests/` (only `__init__.py`), `test_reports/`, `test_result.md`, `.emergent/`, `.gitconfig`, `README.md` = "# Here are your Instructions" | ❌ Emergent session noise |
| `arbicore-x-vps-bundle-0.1.0.SHASUMS`, `-0.1.0-rc2.SHASUMS`, `-0.1.0-rc2.2.SHASUMS` at repo root | Historical release integrity files |

**Implication for Phase 2:** the canonical repo will be **flat**, not nested. The bundle-root subdirectory is a build-time construct; there is no reason to preserve it in the source repository.

### 2.2 Bundle-root contents (`arbicore-x-vps-bundle/`)

```
arbicore-x-vps-bundle/
├── VERSION                              (arbicore-x-vps-bundle-0.1.0-rc2.2)
├── README.md                            (9.6 KB — bundle README)
├── DEPLOYMENT_MANIFEST.md               (14.5 KB — authoritative deployment record)
├── DEPRECATIONS.md                      (what was retired between RCs)
├── PRE_DEPLOYMENT_VALIDATION_CHECKLIST.md (19 KB)
├── RELEASE_NOTES_v0.1.0.md              (RC1 — 18.7 KB)
├── RELEASE_NOTES_v0.1.0-rc2.md          (RC2 — 7.8 KB)
├── RELEASE_NOTES_v0.1.0-rc2.1.md        (RC2.1 — 7.0 KB — no matching git tag)
├── RELEASE_NOTES_v0.1.0-rc2.2.md        (RC2.2 — 6.3 KB)
├── .env.example                         (11 KB, 231 lines — canonical template)
├── .env.production.example              (5.0 KB, 108 lines — prod-locked)
├── .env.development.example             (4.5 KB, 100 lines — dev-permissive)
├── .dockerignore                        (bundle-root — denies node_modules, .git, docs, real .env, etc.)
├── app/                                 (vendored app snapshot; see §2.3)
├── infrastructure/                      (deployment building blocks; see §2.4)
├── scripts/                             (operator entrypoints; see §2.5)
└── docs/                                (9 operator docs + audit archives; see §2.6)
```

### 2.3 Vendored app (`app/`)
Direct snapshot of `ArbiCoreX-V01`. Verified byte-identity via `diff -qr`:

| Subtree | Match against `ArbiCoreX-V01@f64f7bf` |
|---|---|
| `app/backend/` | ✅ **Byte-identical** |
| `app/opportunity_center/` | ✅ **Byte-identical** |
| `app/frontend/` | ⚠️ **Identical except for two extras present only in VPS bundle**: `yarn.lock` (581 KB, yarn 1.22.22 canonical resolution) and `.npmrc` (`legacy-peer-deps=true`). These are the RC2.2 additions. |
| `app/docs/`, `app/memory/` | Documentation snapshot |

**Consequence:** the VPS bundle is *ahead* of `ArbiCoreX-V01` by exactly the RC2.2 reproducibility fix. Step 1 of the RC2.2 workflow (commit the same two files to the app repo) was never executed.

### 2.4 Infrastructure (`infrastructure/`)

Four deployment profiles + shared building blocks:

| Path | Role |
|---|---|
| `infrastructure/greenfield/` | **Default profile.** Full 6-service production stack (see §2.7). Contains `backend/Dockerfile`, `backend/.dockerignore`, `backend/requirements.prod.txt` (120 pinned lines, no `emergentintegrations`/`litellm`), `backend/requirements.dev.txt`, `frontend/Dockerfile`, `frontend/nginx-spa.conf`, `opportunity_center/Dockerfile`, `opportunity_center/nginx-spa.conf`, `docker-compose.yml`, `startup.sh`. |
| `infrastructure/realignment/arbicore-x-deploy/` | **Upgrade toolkit** — SHA-locked (`33ce217a…8fbbf3`) audited artifact for **backend-only** in-place upgrades. 11-step `steps/00_detect_env` → `11_snapshot` with `99_rollback`. `Makefile`-driven. Own `compose/docker-compose.prod.yml`, `backend/Dockerfile`, `mongo/*.js` (index audit, precutover cleanup, validate), `lib/common.sh`, `EXECUTION_ORDER.md`. |
| `infrastructure/shared-infrastructure/` | **Optional profile** for multi-tenant VPS. No mongo/nginx/certbot. `docker-compose.shared.yml` attaches by external network name. `.env.shared.example`, `README.md`. |
| `infrastructure/nginx/` | Shared nginx assets: `nginx.conf` (worker + http), `conf.d/arbicore-x.conf.template` (domain-templated HTTPS + HTTP redirect + WS upgrade + `/api` + `/opportunity-center` + rate limits), `snippets/{security_headers,ssl,gzip}.conf` (HSTS + CSP + Mozilla Intermediate TLS). |
| `infrastructure/ssl/` | `init-letsencrypt.sh` (staging-first cert issuance), `renew.sh`, `cronjob.example`. |
| `infrastructure/backups/` | `backup.sh` (mongodump archive+gzip), `backup-cron.sh` (rotation + optional off-host rclone push), `restore.sh` (mongorestore). |
| `infrastructure/monitoring/` | `healthcheck.sh` (aggregate container+HTTP+TLS probe), `uptime-probe.sh` (external TLS+HTTP), `shadow_start.sh`, `shadow_abort.sh`, `snapshot.sh` (point-in-time Mongo census). |

### 2.5 Operator scripts (`scripts/`)

Three top-level entrypoints, all thin wrappers over `infrastructure/`:

- **`scripts/install.sh`** — 9-phase guarded greenfield installer:
  1. Preflight (docker present, ≥40 GB disk free, ports 80/443 free, `.env` present + validated: DOMAIN, LETSENCRYPT_EMAIL, JWT_SECRET ≥32 chars, VAULT_KEY ≥32 chars).
  2. Refuse-if-exists guard (fails if `arbicore-x-mongo` container or `arbicore-x-mongo-data` volume already exists — no destructive install).
  3. Bring up mongo, wait healthy.
  4. Stage `requirements.prod.txt` → build + bring up backend, wait healthy. (Restores original `requirements.txt` on exit via trap.)
  5. Build + bring up frontend + opportunity_center, wait healthy.
  6. Bring up nginx (HTTP-only mode for ACME challenge).
  7. Issue Let's Encrypt cert via `infrastructure/ssl/init-letsencrypt.sh` (staging by default, prod on flip).
  8. Reload nginx to activate TLS.
  9. Run `scripts/healthcheck.sh`.
- **`scripts/upgrade.sh`** — thin wrapper delegating to `infrastructure/realignment/arbicore-x-deploy/`. Modes: `safe` (detect→preflight→backup→index-audit, then stops), `full` (all through snapshot), `rollback`.
- **`scripts/healthcheck.sh`** — aggregate probe (5 container healthchecks + nginx hairpin HTTP + delegates to `infrastructure/monitoring/uptime-probe.sh` when `$DOMAIN` set).

### 2.6 Operator documentation (`docs/`)

Nine primary operator guides + an audit archive:
`INSTALL.md`, `UPGRADE.md`, `ROLLBACK.md`, `BACKUP_RESTORE.md`, `SSL.md`, `SECURITY.md`, `OPERATIONS.md`, `TROUBLESHOOTING.md`, `SHARED_INFRASTRUCTURE.md`.

Plus `docs/audit/` with **one current** review (`16_vps_bundle_technical_review.md`) and **18 legacy audit docs** under `docs/audit/legacy/` (STAGE1/STAGE2 runbooks, 01_executive_summary through 15_bundle_technical_review, plus patches subdir).

### 2.7 Runtime topology (from `infrastructure/greenfield/docker-compose.yml`)

Six services on a single bridge network `arbicore-x-net`. All non-root. Every service has healthcheck, resource limits, and json-file log driver capped at 100 MB × 5 files.

| Service | Image | Bind | Port(s) exposed to host | Healthcheck | Deps |
|---|---|---|---|---|---|
| `mongo` | `${MONGO_IMAGE:-mongo:4.4}` | uid 999 | none (internal) | `mongosh ping` w/ `mongo` shell fallback | — |
| `backend` | `arbicore-x-backend:0.1.0` (built), Python 3.11-slim, uid 1001 | env_file `.env` | none (internal) | `curl /api/` | mongo healthy |
| `frontend` | `arbicore-x-frontend:0.1.0` (built), node:20 → nginx:1.25-alpine, uid 101 | build-time `REACT_APP_BACKEND_URL` baked | none (internal) | `wget /healthz` | — |
| `opportunity_center` | `arbicore-x-opportunity-center:0.1.0` (built), node:20 → nginx:1.25-alpine, uid 101 | build-time `VITE_BACKEND_URL` baked | none (internal) | `wget /healthz` | — |
| `nginx` | `nginx:1.25-alpine` | envsubst-templated `${DOMAIN}` at boot | **`80`, `443`** (public) | `wget /nginx-health` | backend + frontend + opportunity_center healthy |
| `certbot` | `certbot/certbot:latest` | shared certs + webroot volumes | none | 12h renew loop | — |

Persistent named volumes: `arbicore-x-mongo-data`, `arbicore-x-logs`, `arbicore-x-certbot-etc`, `arbicore-x-certbot-www`.

**Data anchor invariant:** Mongo binds a *named volume*, never a host path. Volume outlives any container rebuild. The installer refuses to overwrite an existing volume — protects data.

### 2.8 Env template surface
`.env.example` (231 lines, canonical) references every variable the compose stack consumes. `.env.production.example` (108 lines, tight defaults) and `.env.development.example` (100 lines, permissive) are complete-form templates. Required-at-install (validated by `install.sh`): `DOMAIN`, `LETSENCRYPT_EMAIL`, `JWT_SECRET` (≥32 chars), `VAULT_KEY` (≥32 chars). Optional overrides: `MONGO_IMAGE`, `LETSENCRYPT_MODE`, `GITSHA`, image tags, plus every scanner/API-key toggle documented in the DEPLOYMENT_MANIFEST §5.

### 2.9 Hardening properties observed
- All service processes run non-root (uid 1001 backend, uid 101 nginx-alpine, uid 999 mongo).
- No secrets in images — `.env` mounted at runtime via compose `env_file`.
- Build-time provenance labels (`arbicore.gitsha`, `arbicore.schema`, `arbicore.role`, `arbicore.profile`).
- Backend hardcoded to `--workers 1` (correct for the scanner runtime; multi-worker would double-tick scanners).
- No hard-coded domain, FQDN, IP — everything domain-scoped goes through `${DOMAIN}` and `envsubst` at nginx boot.
- Scanners dormant by default (`ARBICORE_SCANNER_*_ARB=false` in every template) — operator opts in.
- `requirements.prod.txt` grep-verified to exclude `emergentintegrations`, `litellm`, and dev tools (black, pytest, ruff, mypy, isort, flake8, ipython, bandit).
- HSTS, CSP, gzip, Mozilla Intermediate TLS applied via nginx snippets.

---

## 3. RC2.2 overlay — role confirmed

The overlay is exactly what it claimed to be: a **patch package**, not a source of truth. Its payload — `yarn.lock` + `.npmrc` + updated VERSION/DEPLOYMENT_MANIFEST/RELEASE_NOTES — has **already been applied** to the VPS bundle repo (visible at HEAD as commits `1f85b7d fix(deps,rc2.2)…` and `d72ae57 prep(rc2.2): SHASUMS…`). The overlay contributes **no additional canonical assets** beyond what the VPS bundle already contains. Retained as historical evidence only.

---

## 4. Duplicate / obsolete assets — inventory

These will be resolved in Phase 2 (design). Listing them here as evidence:

| Asset | Where | Status | Recommended disposition |
|---|---|---|---|
| `release_bundle/arbicore-x/` (embedded 2-service shadow bundle, dated 2026-02-23) | inside `ArbiCoreX-V01` | **Superseded** by the VPS bundle's 6-service greenfield profile | **Drop** — do not migrate |
| `release_bundle/arbicore-x-deployment-bundle.zip` (binary release artifact) | inside `ArbiCoreX-V01`, referenced from `backend/arbicore/routes/opportunity_center.py` | **Legacy delivery mechanism** (download-through-API) — new model is clone-and-go from canonical repo | **Drop** — remove `zip` + remove API endpoint that serves it |
| `release_bundle/screenshots/` (7 PNGs) | inside `ArbiCoreX-V01` | Evidence captures, not runtime assets | **Drop** |
| `release_bundle/api_samples/*.json` | inside `ArbiCoreX-V01` | Evidence captures | **Drop** |
| Repo-root Emergent leakage in VPS bundle repo: `audit_output/`, `audit_workspace/`, `backend/`, `frontend/`, `memory/`, `tests/`, `test_reports/`, `test_result.md`, `.emergent/`, `.gitconfig`, root `README.md = "Here are your Instructions"` | outside `arbicore-x-vps-bundle/` in VPS bundle repo | **Session noise** — never part of the bundle | **Drop** — omit entirely from canonical repo |
| Nested layout (`arbicore-x-vps-bundle/` inside repo root) | VPS bundle repo | Historical build-time construct; unnecessary in a self-contained source repo | **Flatten** — canonical repo will use flat layout, no nested bundle root |
| `RELEASE_NOTES_v0.1.0.md`, `RELEASE_NOTES_v0.1.0-rc2.md`, `RELEASE_NOTES_v0.1.0-rc2.1.md`, `RELEASE_NOTES_v0.1.0-rc2.2.md` | inside `arbicore-x-vps-bundle/` | Historical RC-line release notes; canonical repo starts fresh at `v1.0.0` | **Drop from active docs** — retain excerpted lineage in `MIGRATION_SUMMARY.md` for provenance only |
| `arbicore-x-vps-bundle-0.1.0*.SHASUMS` (3 files) at repo root | VPS bundle repo | Integrity of retired RC tarballs | **Drop** — canonical repo generates its own release integrity on tag |
| `docs/audit/legacy/` (18 files) + `docs/audit/16_vps_bundle_technical_review.md` | inside `arbicore-x-vps-bundle/` | Historical audit trail | **Drop** — retain a one-page provenance note in `MIGRATION_SUMMARY.md` |
| `PRE_DEPLOYMENT_VALIDATION_CHECKLIST.md` (19 KB), `DEPLOYMENT_MANIFEST.md` (14.5 KB), `DEPRECATIONS.md` | inside `arbicore-x-vps-bundle/` | Bundle-format artifacts; canonical repo's docs suite replaces them | **Regenerate** as `docs/ARCHITECTURE.md` + `docs/OPERATIONS.md` content |
| Duplicate bundle README + top-level README | both repos | Two competing READMEs | **Merge into one canonical top-level README** |
| `RC2.2` overlay archive (`_rc2_2_prep.tar.gz`) | supplemental | Already applied to VPS bundle | **Drop** — retain provenance mention only |
| `app/docs/` and `app/memory/` inside VPS bundle | inside `arbicore-x-vps-bundle/` | Application-side documentation is duplicated between app repo and VPS bundle | **Deduplicate** — one canonical `docs/` at repo root |
| `infrastructure/monitoring/shadow_start.sh` + `shadow_abort.sh` + `snapshot.sh` | inside VPS bundle | Wave-1 shadow observation tooling — pre-production experimental flow | **Retain** (still valid operational tooling); reclassify under `deployment/scripts/observation/` |

---

## 5. Four framing questions — evidence-based answers

### Q1. Does the deployment repository fully support the current application?
**Yes — with one caveat.** The VPS bundle repo's `app/backend` and `app/opportunity_center` are byte-identical to `ArbiCoreX-V01@f64f7bf`. Its `app/frontend/` is byte-identical *plus* two RC2.2 additions (`yarn.lock`, `.npmrc`) that fix a real `docker compose build` failure. So the deployment tree carries a **superset** of the current app, and the extra files are exactly the fix the app *needs* for reproducible builds. Nothing in the app requires a deployment asset the VPS bundle lacks. All 6 services in the compose stack are backed by real Dockerfiles, real nginx config, real SSL scripts, real backup/restore, real monitoring. ✅

**Caveat:** the app repo has fallen behind the VPS bundle by those two files. In the canonical repo (Option iii — full absorption) this stops mattering because the app tree is owned by the canonical repo directly.

### Q2. Are there deployment assets missing from either repository?
- **From the app repo:** yes — everything deployment-related. `release_bundle/arbicore-x/` inside the app repo is an outdated 2-service shadow bundle only, not a production deployment. The app repo has **no** nginx config, no SSL, no reverse proxy, no install/upgrade/rollback scripts, no monitoring, no backups suitable for production. This is by design — the intended separation of concerns is correct.
- **From the VPS bundle repo:** no missing assets for the greenfield profile. All 6 services and all lifecycle concerns (install/upgrade/rollback/backup/restore/SSL/monitoring/health) are covered.

**One small gap either way:** neither repo has a `CONTRIBUTING.md`, and neither has a `LICENSE` file. The canonical repo will add both.

### Q3. Are there obsolete or duplicated deployment components?
**Yes — multiple.** See §4 above for the full inventory. Summary: (a) the embedded `release_bundle/arbicore-x/` in the app repo is fully obsolete; (b) the VPS bundle repo carries substantial repo-root noise from prior Emergent sessions; (c) four historical release-notes files, three RC-tag SHASUMS files, 19 legacy audit docs, and the nested bundle-root layout are all historical artifacts appropriate for a working release repo but **inappropriate** for a clean-slate canonical repo starting at `v1.0.0`.

### Q4. What should the final production deployment contain?
Based on evidence, the canonical repo needs — and only needs — the following:

**A. Application source (fully absorbed):**
- `app/backend/` — from `ArbiCoreX-V01/backend/` (byte-identical), tests included
- `app/frontend/` — from `ArbiCoreX-V01/frontend/` **plus** the RC2.2 `yarn.lock` and `.npmrc` **from the VPS bundle** (both required for reproducible frontend builds)
- `app/opportunity_center/` — from `ArbiCoreX-V01/opportunity_center/` (byte-identical)

**B. Deployment infrastructure (default greenfield + upgrade toolkit + optional shared-infra):**
- `deployment/compose/docker-compose.yml` — greenfield 6-service (from `infrastructure/greenfield/docker-compose.yml`, minor path adjustments after flattening)
- `deployment/docker/backend/Dockerfile` + `.dockerignore` + `requirements.prod.txt` + `requirements.dev.txt`
- `deployment/docker/frontend/Dockerfile` + `nginx-spa.conf`
- `deployment/docker/opportunity_center/Dockerfile` + `nginx-spa.conf`
- `deployment/nginx/nginx.conf` + `conf.d/arbicore-x.conf.template` + `snippets/{security_headers,ssl,gzip}.conf`
- `deployment/ssl/init-letsencrypt.sh` + `renew.sh` + `cronjob.example`
- `deployment/backups/backup.sh` + `backup-cron.sh` + `restore.sh`
- `deployment/monitoring/healthcheck.sh` + `uptime-probe.sh` + `shadow_start.sh` + `shadow_abort.sh` + `snapshot.sh`
- `deployment/scripts/install.sh` + `upgrade.sh` + `healthcheck.sh` (top-level orchestrators)
- `deployment/profiles/upgrade/arbicore-x-deploy/` — the SHA-locked realignment/upgrade toolkit (11-step + Makefile), retained under a clearer path
- `deployment/profiles/shared-infrastructure/docker-compose.shared.yml` + `.env.shared.example` + `README.md` — optional profile

**C. Environments (root-level):**
- `.env.example` (canonical, comprehensive), `.env.production.example`, `.env.development.example`

**D. Docs (regenerated, clean, no RC lineage):**
- `docs/ARCHITECTURE.md` (application + deployment architecture, single doc)
- `docs/INSTALL.md`, `docs/OPERATIONS.md`, `docs/UPGRADE.md`, `docs/ROLLBACK.md`, `docs/BACKUP_RESTORE.md`, `docs/SSL.md`, `docs/SECURITY.md`, `docs/TROUBLESHOOTING.md`
- `docs/SHARED_INFRASTRUCTURE.md` (kept — describes the optional profile)
- `docs/REPOSITORY_PHILOSOPHY.md` — new authoring
- `docs/MIGRATION_SUMMARY.md` — new authoring, tracks provenance from legacy repos
- `docs/CANONICAL_CERTIFICATION.md` — Phase 4 output
- `docs/EXCLUSIONS.md` — records what was omitted and why

**E. Repo-root files:**
- `README.md` (real, not "Here are your Instructions")
- `LICENSE` — Proprietary — All Rights Reserved
- `CONTRIBUTING.md` — new authoring
- `VERSION` — `1.0.0`
- `.gitignore` — clean, minimal
- `.gitattributes` — line-ending enforcement (Linux LF for shell scripts and code)
- `.dockerignore` — repo-root, denies node_modules, .git, docs, screenshots, real .env, caches
- (top-level convenience) `docker-compose.yml` — symlink or copy of the greenfield compose so `docker compose up` works from repo root (evaluate in Phase 2)

**F. Deliberately excluded (see `docs/EXCLUSIONS.md` in Phase 3):**
All items in §4 marked "Drop", plus the RC2.2 overlay, plus the four RC release notes, plus all legacy audit docs, plus all Emergent session noise from the VPS bundle repo root.

---

## 6. Preliminary canonical architecture direction (informative — final in Phase 2)

- **Flat repo layout**, not nested. No `arbicore-x-vps-bundle/` subdirectory inside the source of truth. The tarball for a VPS release is a *build-time artifact*, not a source-tree property.
- **Two top-level trees**: `app/` (application code, fully absorbed) and `deployment/` (all infrastructure). Docs live at repo root under `docs/`.
- **Three deployment profiles**, cleanly separated: `greenfield` (default), `upgrade` (SHA-locked realignment toolkit), `shared-infrastructure` (optional). `scripts/install.sh` defaults to greenfield.
- **No dependence on external release bundles.** Every operator action starts from `git clone`.
- **App integration:** direct absorption (Option iii, per your locked decision). `app/` is a first-class part of the canonical repo, not a snapshot of some other repo. No submodule.
- **Frontend reproducibility:** `app/frontend/yarn.lock` and `app/frontend/.npmrc` are canonical from day one.
- **Version:** `v1.0.0` clean-slate tag. No RC lineage. The three legacy tags (`v0.1.0-rc1`, `v0.1.0-rc2`, `v0.1.0-rc2.2`) stay in the *legacy* VPS-bundle repo as historical references only, never migrated.

---

## 7. Phase 1 checkpoint

Phase 1 is complete. All four framing questions have evidence-based answers. The full deployment topology is understood end-to-end. The disposition of every duplicate/obsolete asset is provisionally identified (§4).

**Your options at this checkpoint:**
- ✅ **Approve** → I proceed to Phase 2 (Design): produce `Canonical_Repository_Design.md` with the exact final tree, per-file migration table, and app-integration model, then stop again for your Phase 2 approval before any code writes.
- 🔁 **Request clarifications / adjustments** → I revise this Phase 1 report and re-present.
- ⏸ **Pause** → I hold state and wait.

I remain fully read-only. No writes to any repository. No new repo. No bundle generation. Standing by.
