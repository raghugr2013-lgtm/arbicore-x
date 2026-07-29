# ArbiCore X — Phase 2: Canonical Repository Design

**Phase:** 2 (Design) · **Status:** COMPLETE · **Next:** Phase 2 checkpoint (your approval) → Phase 3 (Build)
**Reads-only work only.** Nothing has been created, moved, or written into `/app/canonical_repo/` yet.

---

## 0. Design principles applied

Every decision in this document is checked against, in priority order:
1. Simplicity — the shortest correct expression of each concern
2. Clear separation of concerns — application vs deployment
3. Production-readiness — everything an operator needs, nothing they don't
4. Reproducibility — anyone can `git clone` and get to a working install with only `.env` inputs
5. Minimal duplication — one location per file, one file per concept
6. Long-term maintainability — a new engineer can navigate without a tour
7. No dependency on legacy repos or historical bundles

Anything that fails one of the above is dropped or regenerated.

---

## 1. Proposed canonical directory tree

**Repo:** `raghugr2013-lgtm/arbicore-x` (private) · **Version:** `v1.0.0` · **Layout:** flat (no nested `arbicore-x-vps-bundle/` wrapper)

```
arbicore-x/
├── README.md                                # ★ new — real, actionable top-level readme
├── LICENSE                                  # ★ new — Proprietary — All Rights Reserved
├── CONTRIBUTING.md                          # ★ new — folder/naming/docs/deployment/review standards
├── VERSION                                  # ★ new — 1.0.0
├── Makefile                                 # ★ new — install/upgrade/status/backup/logs/test conveniences
├── .gitignore                               # ★ new — clean, minimal
├── .gitattributes                           # ★ new — LF enforcement for shell/py/yaml
├── .dockerignore                            # from VPS bundle root (byte-preserved)
├── .env.example                             # from VPS bundle root (byte-preserved)
├── .env.production.example                  # from VPS bundle root (byte-preserved)
├── .env.development.example                 # from VPS bundle root (byte-preserved)
│
├── app/                                     # ─── APPLICATION SOURCE (fully absorbed) ───
│   ├── README.md                            # ★ new — app-tree orientation
│   ├── backend/                             # from ArbiCoreX-V01/backend/ (byte-identical)
│   │   ├── arbicore/                        #   scanner core (D-1…D-6 families)
│   │   ├── connectors/, core/, engines/, routes/, services/, scripts/
│   │   ├── tests/                           #   pytest suite (~200 files)
│   │   ├── conftest.py, server.py, reset_admin.py, requirements.txt
│   ├── frontend/                            # from ArbiCoreX-V01/frontend/ + RC2.2 fixes
│   │   ├── src/, public/, plugins/
│   │   ├── package.json, craco.config.js, tailwind.config.js, postcss.config.js
│   │   ├── components.json, jsconfig.json, README.md
│   │   ├── yarn.lock                        # from VPS bundle (RC2.2 addition; missing from app repo)
│   │   └── .npmrc                           # from VPS bundle (RC2.2 addition)
│   └── opportunity_center/                  # from ArbiCoreX-V01/opportunity_center/ (byte-identical)
│       ├── src/, index.html, package.json, vite.config.js
│       ├── postcss.config.js, tailwind.config.js, README.md
│
├── deployment/                              # ─── DEPLOYMENT (all infra building blocks) ───
│   ├── README.md                            # ★ new — deployment-tree orientation
│   │
│   ├── docker/                              # Dockerfiles by service (not by profile)
│   │   ├── backend/
│   │   │   ├── Dockerfile                   # from VPS bundle greenfield/backend/Dockerfile
│   │   │   ├── .dockerignore                # from VPS bundle greenfield/backend/.dockerignore
│   │   │   ├── requirements.prod.txt        # from VPS bundle greenfield/backend/requirements.prod.txt
│   │   │   └── requirements.dev.txt         # from VPS bundle greenfield/backend/requirements.dev.txt
│   │   ├── frontend/
│   │   │   ├── Dockerfile                   # from VPS bundle greenfield/frontend/Dockerfile
│   │   │   └── nginx-spa.conf               # from VPS bundle greenfield/frontend/nginx-spa.conf
│   │   └── opportunity_center/
│   │       ├── Dockerfile                   # from VPS bundle greenfield/opportunity_center/Dockerfile
│   │       └── nginx-spa.conf               # from VPS bundle greenfield/opportunity_center/nginx-spa.conf
│   │
│   ├── compose/                             # compose files by profile
│   │   ├── docker-compose.yml               # DEFAULT — greenfield 6-service stack
│   │   │                                    #   (from VPS bundle greenfield/docker-compose.yml,
│   │   │                                    #    paths adjusted to new layout)
│   │   ├── docker-compose.shared.yml        # OPTIONAL — shared-infra (peer-tenant)
│   │   │                                    #   (from VPS bundle shared-infrastructure/)
│   │   ├── .env.shared.example              # from VPS bundle shared-infrastructure/
│   │   └── README.md                        # ★ new — profile selection guide
│   │
│   ├── nginx/                               # reverse-proxy assets (shared across profiles)
│   │   ├── nginx.conf                       # from VPS bundle infrastructure/nginx/
│   │   ├── conf.d/
│   │   │   └── arbicore-x.conf.template     # envsubst-templated site config
│   │   └── snippets/
│   │       ├── security_headers.conf        # HSTS + CSP
│   │       ├── ssl.conf                     # Mozilla Intermediate TLS
│   │       └── gzip.conf
│   │
│   ├── ssl/                                 # Let's Encrypt lifecycle
│   │   ├── init-letsencrypt.sh              # staging-first cert issuance
│   │   ├── renew.sh                         # renewal (also runs inside certbot container loop)
│   │   └── cronjob.example
│   │
│   ├── backups/                             # data safety
│   │   ├── backup.sh                        # mongodump archive+gzip
│   │   ├── backup-cron.sh                   # rotation + optional off-host rclone
│   │   └── restore.sh                       # mongorestore (interactive confirm)
│   │
│   ├── monitoring/                          # observability + probes
│   │   ├── healthcheck.sh                   # internal aggregate — used by scripts/healthcheck.sh
│   │   ├── uptime-probe.sh                  # external-style TLS + HTTP probe
│   │   ├── snapshot.sh                      # point-in-time Mongo census (JSON)
│   │   ├── shadow_start.sh                  # data-collection window start
│   │   └── shadow_abort.sh                  # window abort + final capture
│   │
│   └── upgrade/                             # in-place upgrade toolkit (SHA-locked audited artifact)
│       │                                     # renamed from "infrastructure/realignment/arbicore-x-deploy/"
│       ├── README.md                        # from toolkit's README.md
│       ├── EXECUTION_ORDER.md               # from toolkit's EXECUTION_ORDER.md
│       ├── Makefile                         # from toolkit's Makefile
│       ├── backend/
│       │   ├── Dockerfile
│       │   ├── .dockerignore
│       │   └── README.md
│       ├── compose/
│       │   └── docker-compose.prod.yml
│       ├── lib/
│       │   └── common.sh
│       ├── mongo/
│       │   ├── 01_index_audit.js
│       │   ├── 02_precutover_cleanup.js
│       │   └── 04_validate.js
│       └── steps/
│           ├── 00_detect_env.sh, 01_preflight.sh, 02_backup.sh, 03_index_audit.sh
│           ├── 04_precutover_cleanup.sh, 05_build.sh, 06_cutover.sh
│           ├── 09_canary_probe.sh, 10_validate.sh, 11_snapshot.sh
│           └── 99_rollback.sh
│
├── scripts/                                 # ─── OPERATOR ENTRYPOINTS (top-level) ───
│   ├── install.sh                           # greenfield installer (9-phase, guarded)
│   ├── upgrade.sh                           # thin wrapper → deployment/upgrade/
│   ├── healthcheck.sh                       # aggregate probe (delegates to deployment/monitoring)
│   ├── backup.sh                            # ★ new — thin wrapper → deployment/backups/backup.sh
│   └── restore.sh                           # ★ new — thin wrapper → deployment/backups/restore.sh
│
└── docs/                                    # ─── OPERATIONAL DOCUMENTATION ONLY ───
    ├── README.md                            # ★ new — doc index
    ├── ARCHITECTURE.md                      # ★ new/merged — app + deployment architecture (single source)
    ├── INSTALL.md                           # from VPS bundle docs/INSTALL.md (paths refreshed)
    ├── OPERATIONS.md                        # from VPS bundle docs/OPERATIONS.md
    ├── UPGRADE.md                           # from VPS bundle docs/UPGRADE.md
    ├── ROLLBACK.md                          # from VPS bundle docs/ROLLBACK.md
    ├── BACKUP_RESTORE.md                    # from VPS bundle docs/BACKUP_RESTORE.md
    ├── SSL.md                               # from VPS bundle docs/SSL.md
    ├── SECURITY.md                          # from VPS bundle docs/SECURITY.md
    ├── TROUBLESHOOTING.md                   # from VPS bundle docs/TROUBLESHOOTING.md
    ├── SHARED_INFRASTRUCTURE.md             # from VPS bundle docs/SHARED_INFRASTRUCTURE.md
    ├── REPOSITORY_PHILOSOPHY.md             # ★ new — why the repo is designed this way
    ├── MIGRATION_SUMMARY.md                 # ★ new — provenance & one-time migration record
    ├── CANONICAL_CERTIFICATION.md           # ★ new — Phase 4 certification output
    └── EXCLUSIONS.md                        # ★ new — what was omitted and why
```

**Legend:** `★ new` = newly authored for the canonical repo. All other files trace to a specific legacy source and are either copied byte-for-byte or regenerated with justification.

**Total top-level entries:** 15 (5 config files, 3 dotfiles/envs, 4 top-level dirs, plus README/LICENSE/CONTRIBUTING/Makefile/VERSION). Clean and legible.

---

## 2. Architectural decisions (with rationale)

### D-1. Flat layout — drop the `arbicore-x-vps-bundle/` wrapper directory
The VPS bundle nests everything inside `arbicore-x-vps-bundle/` inside the repo root. That was a valid convention for a "release bundle" repo whose primary artifact is a tarball. In a canonical source repo, that extra level is pure friction: every path documented in the manifest becomes `arbicore-x-vps-bundle/…`, operators must `cd` before running anything, and the repo root itself becomes noise-only. **Decision:** the canonical repo is flat. If a release tarball is ever needed, it can be generated by `tar -czf arbicore-x-v1.0.0.tar.gz -C .. arbicore-x/` at build time.

### D-2. Two-tree separation: `app/` and `deployment/`
The canonical separation is between "what the software IS" (`app/`) and "how it runs in production" (`deployment/`). This mirrors the responsibility split that already existed between the two legacy repos, but expressed cleanly inside a single repo. Documentation and scripts are cross-cutting and live at the repo root.

### D-3. Rename `infrastructure/realignment/` → `deployment/upgrade/`
"Realignment" is a historical audit term with no operational meaning to a new engineer. The tree it contains IS the upgrade toolkit. Renaming is safe — the toolkit's internal scripts (`Makefile`, `steps/*.sh`, `lib/common.sh`) reference "realignment" only in comments, never in path resolution (verified). Also flattens the redundant `arbicore-x-deploy/` inner directory — its contents move directly under `deployment/upgrade/`.

### D-4. Flatten Dockerfiles under `deployment/docker/{service}/` — not `deployment/profiles/{profile}/{service}/`
There is exactly one production Dockerfile per service (backend, frontend, opportunity_center). Profiles differ in how services are composed (which run, where they bind, which env they consume), not in how each service builds. So Dockerfiles live under `deployment/docker/`, indexed by service; compose files live under `deployment/compose/`, indexed by profile. Cross-cutting infra (nginx, ssl, backups, monitoring) lives at `deployment/`.

### D-5. No top-level `docker-compose.yml`
Idiomatic-looking, but creates a second source of truth. Instead, the top-level `Makefile` provides `make install`, `make up`, `make down`, `make logs`, `make status`, `make upgrade`, `make backup`, `make restore`, `make healthcheck` — all delegating into `scripts/` and `deployment/compose/`. Anyone insisting on running compose directly does `cd deployment/compose && docker compose up -d`.

### D-6. Retain `shared-infrastructure` as an optional profile, not as a top-level directory
The user's locked decisions say "Shared Infrastructure retained as optional, not default". Implementation: it becomes exactly one alternate compose file (`deployment/compose/docker-compose.shared.yml`) plus one env template (`deployment/compose/.env.shared.example`) plus one doc (`docs/SHARED_INFRASTRUCTURE.md`). No separate directory tree — that would inflate the repo.

### D-7. No `archive/` directory in the canonical repo
The user's Phase 2 brief says "Where historical material has long-term reference value, place it in a clearly separated archive that is excluded from normal development and deployment workflows." Evaluated: no legacy audit document has ongoing operational value. The two legacy repos (`ArbiCoreX-V01`, `arbicore-x-vps-bundle`) already provide the historical archive with full git history. **Decision:** the canonical repo has no `archive/`; instead `docs/MIGRATION_SUMMARY.md` provides pointers into the legacy repos at specific commit SHAs and tags for anyone needing historical context. This maximally honors the "clone-and-go" and "no fragmentation" principles.

### D-8. `Makefile` at the repo root as the primary operator interface
A single-file, discoverable, tab-complete-friendly menu of the ~10 things an operator ever does. Every target is a one-liner delegating into `scripts/` or `deployment/`. New engineers can `make help` and see the operational surface at a glance.

### D-9. Full app absorption (not submodule, not vendored-with-pin-file)
Locked by user as Option (iii). App code is a first-class part of the canonical repo. No `.gitmodules`, no vendor-pin file, no origin tracking. `ArbiCoreX-V01` becomes a legacy reference repo.

### D-10. Remove dead `arbicore-x-deployment-bundle.zip` distribution endpoints from `backend/`
The app repo's `backend/arbicore/routes/opportunity_center.py` currently exposes `GET /api/arbicore/release/manifest` and `GET /api/arbicore/release/bundle`, streaming the legacy zip. The zip is dropped in the canonical repo (canonical distribution model is git clone, not authenticated API download). The endpoints would become dead code that returns 404 on a missing file. **Decision:** in Phase 3, apply a minimal, surgical edit to that file to remove those two endpoints (and their tests, if any). This is a code change but justified as **"resolving deployment inconsistency"** per your Phase-2 principle: eliminate obsolete assets and prevent the repo from carrying inert surface area.

### D-11. Regenerate `.gitignore`, `.gitattributes`, `README.md`, `VERSION`
The legacy repos' equivalents contain Emergent-session stubs and cross-contamination (`.gitignore` had `release_bundle/` while also tracking it; `README.md` = "Here are your Instructions"). Fresh, clean, purposeful versions.

### D-12. Frontend reproducibility fix (RC2.2) becomes the day-one baseline
`app/frontend/yarn.lock` and `app/frontend/.npmrc` — the two files that fix `docker compose build` on a clean checkout — are canonical from day one. No RC lineage, no patch overlay, no two-step workflow. This closes the frontend build reproducibility gap permanently.

### D-13. Drop all four legacy release notes; provenance lives in `docs/MIGRATION_SUMMARY.md`
`RELEASE_NOTES_v0.1.0.md`, `RELEASE_NOTES_v0.1.0-rc2.md`, `RELEASE_NOTES_v0.1.0-rc2.1.md`, `RELEASE_NOTES_v0.1.0-rc2.2.md` are historical to the RC-line naming. Canonical starts at `v1.0.0`. A one-time provenance record in MIGRATION_SUMMARY.md preserves the audit trail without cluttering the operational docs.

---

## 3. Complete file migration matrix

Grouped by source. **Action codes:** `Copy` = byte-preserved; `Regen` = regenerated; `Merge` = content extracted into a canonical file; `Drop` = intentionally omitted (recorded in EXCLUSIONS.md); `NewAuth` = new authoring.

### 3.1 From `ArbiCoreX-V01@f64f7bf`

| Source path (in ArbiCoreX-V01) | Destination in canonical repo | Action | Justification |
|---|---|---|---|
| `backend/` (all subtrees, tests included) | `app/backend/` | Copy | Byte-identical to VPS bundle's `app/backend`; app is the source of truth for its own code. |
| `frontend/` (all subtrees) | `app/frontend/` | Copy | Same — application code ground truth. |
| `frontend/` — surgical: add `yarn.lock` + `.npmrc` | `app/frontend/yarn.lock`, `app/frontend/.npmrc` | Merge (from VPS bundle) | Missing from app repo; required for reproducible `docker compose build`. See D-12. |
| `backend/arbicore/routes/opportunity_center.py` — surgical edit | `app/backend/arbicore/routes/opportunity_center.py` | Merge | Remove `/api/arbicore/release/manifest` + `/api/arbicore/release/bundle` endpoints (and any tests referencing them). Justified per D-10. Small, contained edit — no other logic touched. |
| `opportunity_center/` | `app/opportunity_center/` | Copy | Application code. |
| `docs/00…24` (24 numbered architecture/audit docs) | `docs/ARCHITECTURE.md` | Merge (selective) | These are historical design analyses. The current-state summary distilled from them plus the deployment topology becomes the single canonical `docs/ARCHITECTURE.md`. Full historical docs referenced from `docs/MIGRATION_SUMMARY.md` (pointing at the legacy repo) for anyone who needs them. |
| `docs/audit/*` (14 audit subdocs) | — | Drop | Historical audit trail. Reference via `docs/MIGRATION_SUMMARY.md`. |
| `docs/manifest.json` | — | Drop | Legacy delivery-side manifest; canonical repo uses `VERSION` + `docs/ARCHITECTURE.md` instead. |
| `memory/` (12 files: CHANGELOG.md, PRD.md, various *_REPORT.md, IMPORT_LOG.md, KEY_CONFIG_AUDIT.md, etc.) | — | Drop | Agent-session memory, not production documentation. Provenance recorded in MIGRATION_SUMMARY.md. |
| `memory/.gitkeep` | — | Drop | Placeholder for a dropped directory. |
| `release_bundle/arbicore-x/` (embedded 2-service shadow bundle, 2026-02-23) | — | Drop | Fully superseded by the 6-service greenfield stack. Recorded in EXCLUSIONS.md. |
| `release_bundle/arbicore-x-deployment-bundle.zip` | — | Drop | Legacy delivery artifact. Distribution now via `git clone`. |
| `release_bundle/screenshots/`, `release_bundle/api_samples/` | — | Drop | Evidence captures, not production content. |
| `test_reports/`, `test_result.md` | — | Drop | Emergent session artifacts. |
| `tests/` (root-level, empty `__init__.py` only) | — | Drop | Empty. Real tests already live at `app/backend/tests/`. |
| `.emergent/` (session config), `.gitconfig` | — | Drop | Session leakage. |
| `.gitignore` | `.gitignore` | Regen | Legacy version simultaneously tracked and ignored `release_bundle/`. Fresh clean version. |
| `README.md` = "# Here are your Instructions" | `README.md` | Regen | Placeholder. Real, actionable README written for canonical. |
| `test_result.md` | — | Drop | Session artifact. |

### 3.2 From `arbicore-x-vps-bundle@main` (`arbicore-x-vps-bundle/` subdirectory only)

| Source path (in bundle-root) | Destination in canonical repo | Action | Justification |
|---|---|---|---|
| `VERSION` (= `arbicore-x-vps-bundle-0.1.0-rc2.2`) | `VERSION` | Regen (= `1.0.0`) | Fresh SemVer, drop RC lineage. |
| `README.md` | `README.md` | Merge | Content merged with a fresh top-level README that describes the whole canonical repo. |
| `DEPLOYMENT_MANIFEST.md` (14.5 KB) | `docs/ARCHITECTURE.md` | Merge | Bundle-shape doc; content extracted into the single canonical architecture doc. |
| `DEPRECATIONS.md` | — | Drop | RC-lineage bookkeeping; not applicable to v1.0.0. |
| `PRE_DEPLOYMENT_VALIDATION_CHECKLIST.md` (19 KB) | `docs/INSTALL.md` (checklist section) + `docs/OPERATIONS.md` | Merge | Content that belongs in the operational docs gets folded in; RC-lineage bits dropped. |
| `RELEASE_NOTES_v0.1.0.md`, `-rc2.md`, `-rc2.1.md`, `-rc2.2.md` | — | Drop | Historical RC-line release notes. Provenance chain preserved as a short section in `docs/MIGRATION_SUMMARY.md`. |
| `.env.example` (231 lines) | `.env.example` | Copy | Canonical environment template. |
| `.env.production.example` (108 lines) | `.env.production.example` | Copy | Production-locked template. |
| `.env.development.example` (100 lines) | `.env.development.example` | Copy | Development-permissive template. |
| `.dockerignore` (bundle-root) | `.dockerignore` | Copy | Excludes node_modules, .git, docs, screenshots, real .env, caches, `deployment/upgrade/` (was `realignment/`), etc. Paths adjusted for new layout. |
| `app/backend/`, `app/opportunity_center/` | — | Drop (already in `app/` from ArbiCoreX-V01 side) | Deduplication — byte-identical to the app repo version. |
| `app/frontend/yarn.lock`, `app/frontend/.npmrc` | `app/frontend/yarn.lock`, `.npmrc` | Copy | The RC2.2 fix — canonical from day one. |
| `app/frontend/` (rest) | — | Drop | Deduplication — byte-identical to app repo. |
| `app/docs/`, `app/memory/` | — | Drop | Duplicated app-side docs; single source of truth is `docs/`. |
| `infrastructure/greenfield/docker-compose.yml` | `deployment/compose/docker-compose.yml` | Copy + path adjust | Relative paths `../../` change (see D-4 layout); build contexts remain semantically identical. |
| `infrastructure/greenfield/backend/Dockerfile` | `deployment/docker/backend/Dockerfile` | Copy | No change. |
| `infrastructure/greenfield/backend/.dockerignore` | `deployment/docker/backend/.dockerignore` | Copy | No change. |
| `infrastructure/greenfield/backend/requirements.prod.txt` | `deployment/docker/backend/requirements.prod.txt` | Copy | No change. |
| `infrastructure/greenfield/backend/requirements.dev.txt` | `deployment/docker/backend/requirements.dev.txt` | Copy | No change. |
| `infrastructure/greenfield/frontend/Dockerfile` | `deployment/docker/frontend/Dockerfile` | Copy | No change. |
| `infrastructure/greenfield/frontend/nginx-spa.conf` | `deployment/docker/frontend/nginx-spa.conf` | Copy | No change. |
| `infrastructure/greenfield/opportunity_center/Dockerfile` | `deployment/docker/opportunity_center/Dockerfile` | Copy | No change. |
| `infrastructure/greenfield/opportunity_center/nginx-spa.conf` | `deployment/docker/opportunity_center/nginx-spa.conf` | Copy | No change. |
| `infrastructure/greenfield/startup.sh` | — | Drop | Superseded by `scripts/install.sh` (which does its job and more). |
| `infrastructure/nginx/nginx.conf` | `deployment/nginx/nginx.conf` | Copy | No change. |
| `infrastructure/nginx/conf.d/arbicore-x.conf.template` | `deployment/nginx/conf.d/arbicore-x.conf.template` | Copy | No change. |
| `infrastructure/nginx/snippets/{security_headers,ssl,gzip}.conf` | `deployment/nginx/snippets/…` | Copy | No change. |
| `infrastructure/ssl/{init-letsencrypt.sh, renew.sh, cronjob.example}` | `deployment/ssl/…` | Copy | No change. |
| `infrastructure/backups/{backup.sh, backup-cron.sh, restore.sh}` | `deployment/backups/…` | Copy | No change. |
| `infrastructure/monitoring/{healthcheck.sh, uptime-probe.sh, snapshot.sh, shadow_start.sh, shadow_abort.sh}` | `deployment/monitoring/…` | Copy | No change. |
| `infrastructure/realignment/arbicore-x-deploy/` (entire toolkit) | `deployment/upgrade/` | Copy (rename parent, drop redundant nesting per D-3) | Byte-preserved contents. |
| `infrastructure/shared-infrastructure/docker-compose.shared.yml` | `deployment/compose/docker-compose.shared.yml` | Copy + path adjust | Retained as optional profile. |
| `infrastructure/shared-infrastructure/.env.shared.example` | `deployment/compose/.env.shared.example` | Copy | Retained. |
| `infrastructure/shared-infrastructure/README.md` | Merge into `docs/SHARED_INFRASTRUCTURE.md` | Merge | Deduplication. |
| `scripts/install.sh` | `scripts/install.sh` | Copy + path adjust | Paths change: `BUNDLE_ROOT` → repo root; `infrastructure/…` → `deployment/…`. Logic unchanged. |
| `scripts/upgrade.sh` | `scripts/upgrade.sh` | Copy + path adjust | `infrastructure/realignment/arbicore-x-deploy/` → `deployment/upgrade/`. |
| `scripts/healthcheck.sh` | `scripts/healthcheck.sh` | Copy + path adjust | `infrastructure/monitoring/uptime-probe.sh` → `deployment/monitoring/uptime-probe.sh`. |
| `docs/INSTALL.md` | `docs/INSTALL.md` | Copy + path refresh | Documented paths refreshed to new layout. |
| `docs/UPGRADE.md` | `docs/UPGRADE.md` | Copy + path refresh | Same. |
| `docs/ROLLBACK.md` | `docs/ROLLBACK.md` | Copy + path refresh | Same. |
| `docs/BACKUP_RESTORE.md` | `docs/BACKUP_RESTORE.md` | Copy + path refresh | Same. |
| `docs/SSL.md` | `docs/SSL.md` | Copy + path refresh | Same. |
| `docs/SECURITY.md` | `docs/SECURITY.md` | Copy + path refresh | Same. |
| `docs/OPERATIONS.md` | `docs/OPERATIONS.md` | Copy + path refresh | Same. |
| `docs/TROUBLESHOOTING.md` | `docs/TROUBLESHOOTING.md` | Copy + path refresh | Same. |
| `docs/SHARED_INFRASTRUCTURE.md` | `docs/SHARED_INFRASTRUCTURE.md` | Copy + path refresh | Merged with the profile README (see above). |
| `docs/audit/16_vps_bundle_technical_review.md` | — | Drop | Historical audit. |
| `docs/audit/legacy/` (18 files + patches/) | — | Drop | Historical audits. Reference via MIGRATION_SUMMARY.md. |
| `arbicore-x-vps-bundle-0.1.0*.SHASUMS` (3 files at repo root of VPS bundle) | — | Drop | Historical release integrity. Canonical repo generates its own on tag. |
| Repo-root leakage: `audit_output/`, `audit_workspace/`, stub `backend/`, `frontend/`, `memory/`, `tests/`, `test_reports/`, `test_result.md`, `.emergent/`, `.gitconfig`, root `README.md`, root `.gitignore` | — | Drop | Emergent session noise. Never part of the bundle. Recorded in EXCLUSIONS.md. |

### 3.3 From `_rc2_2_prep.tar.gz` overlay
| Source | Destination | Action | Justification |
|---|---|---|---|
| Everything | — | Drop | Overlay is a one-time patch already applied to the VPS bundle repo. Its payload files (`yarn.lock`, `.npmrc`, updated VERSION/manifest/notes) are all present in the VPS bundle. Retained as historical evidence only; not migrated into the canonical repo. Recorded in MIGRATION_SUMMARY.md. |

### 3.4 New authoring (files with no source in either legacy repo)

| File | Purpose | Provenance |
|---|---|---|
| `README.md` (repo root) | Top-level orientation; what the repo is, how to use it, links to the operational docs | New — synthesized from VPS bundle README + app repo context |
| `LICENSE` | Legal | New — Proprietary — All Rights Reserved (per your locked decision) |
| `CONTRIBUTING.md` | Contributor standards (folder organization, naming, docs, deployment changes, Docker updates, config management, review requirements) | New — per your Phase 2 brief |
| `VERSION` | Machine-readable version identifier | New — `1.0.0` |
| `Makefile` | Operator convenience wrapper: `install`, `upgrade`, `up`, `down`, `logs`, `status`, `healthcheck`, `backup`, `restore`, `test`, `help` | New |
| `.gitignore` | Clean minimal (node_modules, __pycache__, .env, build outputs, IDE files) | New (replaces both legacy versions) |
| `.gitattributes` | LF line endings for shell/py/yaml/md — cross-platform-safe checkouts | New (VPS bundle repo had one; folded in) |
| `app/README.md` | App-tree orientation (backend / frontend / opportunity_center layout) | New |
| `deployment/README.md` | Deployment-tree orientation (docker / compose / nginx / ssl / backups / monitoring / upgrade) | New |
| `deployment/compose/README.md` | Profile selection guide (greenfield vs shared-infrastructure) | New |
| `docs/README.md` | Doc index with 1-line descriptions | New |
| `docs/ARCHITECTURE.md` | Single canonical architecture doc: app stack, deployment topology, data model, invariants | New — synthesized from `DEPLOYMENT_MANIFEST.md` + selected content from `docs/00…24` |
| `docs/REPOSITORY_PHILOSOPHY.md` | Why the repo is laid out this way; app/deployment separation; anti-fragmentation rules | New — per your brief |
| `docs/MIGRATION_SUMMARY.md` | Provenance record: what came from where, what was dropped, references into legacy repos for historical context | New — per your brief |
| `docs/CANONICAL_CERTIFICATION.md` | Phase 4 output: certified/not-certified statement, criterion-by-criterion | New — Phase 4 deliverable |
| `docs/EXCLUSIONS.md` | What was intentionally omitted and why | New — per your brief |
| `scripts/backup.sh` | Thin wrapper → `deployment/backups/backup.sh` (convenience only) | New |
| `scripts/restore.sh` | Thin wrapper → `deployment/backups/restore.sh` (convenience only) | New |

---

## 4. Summary table — dispositions by count

| Disposition | Count (approximate) | Where recorded |
|---|---|---|
| **Copy** (byte-preserved from source) | ~200 files (all `app/backend/`, `app/frontend/`, `app/opportunity_center/`, all `deployment/` infra files, `deployment/upgrade/` toolkit) | Section 3 tables |
| **Regen** (fresh new file replacing a legacy one) | 4 (`.gitignore`, `README.md`, `VERSION`, `.gitattributes`) | Section 3 tables |
| **Merge** (extract content, drop container) | ~7 (docs consolidation + surgical route file edit) | Section 3 tables + D-10 |
| **NewAuth** (net-new file, no legacy predecessor) | ~15 (READMEs, LICENSE, CONTRIBUTING, Makefile, philosophy/migration/certification/exclusions docs) | Section 3.4 |
| **Drop** (intentionally omitted) | ~40+ items (all Emergent leakage, all legacy audits, all release notes, all release bundles, all SHASUMS, `memory/`, `test_reports/`, `test_result.md`, empty stub dirs, `startup.sh`, `docs/manifest.json`, `DEPRECATIONS.md`, `arbicore-x-deployment-bundle.zip`, screenshots, api_samples, session dotfiles) | EXCLUSIONS.md |

Exact per-file exclusion list will be enumerated in `docs/EXCLUSIONS.md` during Phase 3.

---

## 5. Recommended improvements beyond the current implementation

Per your explicit engineering-freedom clause. Small, high-leverage additions that improve maintainability without expanding scope:

### R-1. Top-level `Makefile` as the operator interface *(new in canonical)*
Reduces the "which command do I run?" cognitive load to a single tab-complete. Targets: `install`, `upgrade` (safe/full/rollback), `up`, `down`, `restart`, `logs [SERVICE]`, `status`, `healthcheck`, `backup`, `restore ARCHIVE=…`, `test-backend`, `build`, `env-check`, `help`. Every target is a one-liner delegating to the appropriate `scripts/…` or `docker compose …`.

### R-2. `.gitattributes` LF enforcement *(carried over from VPS bundle root; formalize in canonical)*
Prevents Windows-checkout CRLF from breaking shell scripts. Extends coverage to `.py`, `.yml`, `.yaml`, `.md`, `.conf`, `.sh` explicitly.

### R-3. `deployment/README.md` and `app/README.md` orientation cards *(new)*
A new engineer arrives at the repo root, reads top-level `README.md`, then drills into either `app/` or `deployment/`. A short orientation doc in each tree accelerates onboarding without duplicating content in the operational docs.

### R-4. Doc index at `docs/README.md` *(new)*
Instead of 15 docs with no navigation, one file with a one-line description of each. Prevents the "which doc has X?" problem.

### R-5. Single unified `docs/ARCHITECTURE.md` *(new; supersedes 24 numbered docs + DEPLOYMENT_MANIFEST + PRE_DEPLOYMENT_VALIDATION_CHECKLIST fragments)*
The legacy app repo has 24 numbered analysis docs (00-executive-summary … 24-production-workflow-blueprint), most of which are historical or duplicate. The VPS bundle has DEPLOYMENT_MANIFEST + PRE_DEPLOYMENT_VALIDATION_CHECKLIST + audit legacies. A single, concise, current-state architecture doc replaces all of them for operational purposes. Historical detail remains referenceable in the legacy repos (linked from MIGRATION_SUMMARY.md).

### R-6. `scripts/backup.sh` and `scripts/restore.sh` thin wrappers *(new)*
Symmetric with `scripts/install.sh` / `upgrade.sh` / `healthcheck.sh`. Operators run everything from `scripts/`; `deployment/backups/` is the implementation. Same wrapper pattern already used for upgrade → deployment/upgrade/.

### R-7. Remove dead API endpoints for the discontinued bundle-download flow (D-10)
Small surgical edit to `app/backend/arbicore/routes/opportunity_center.py`. Justified specifically by your Phase 2 principle "Only migrate validated production assets" — dead code is not a validated production asset.

### R-8. Fold `PRE_DEPLOYMENT_VALIDATION_CHECKLIST.md` content into `docs/INSTALL.md` + `docs/OPERATIONS.md`
A pre-deployment checklist IS the front matter of an install doc. Merging keeps operators from having to reconcile two adjacent docs.

Nothing in R-1 through R-8 changes runtime behavior, business logic, or dependencies. They are strictly organizational.

---

## 6. Open items requiring your explicit decision

Two items I want you to confirm before Phase 3, because they involve tradeoffs:

### O-1. Confirm rename: `infrastructure/realignment/arbicore-x-deploy/` → `deployment/upgrade/`
Two options:
- **(a) Preserve nested naming:** `deployment/upgrade/arbicore-x-deploy/{contents}` — zero risk to toolkit internals; slightly awkward path.
- **(b) Flatten (recommended):** `deployment/upgrade/{contents}` — cleaner. I verified the toolkit's internal scripts reference "realignment" only in comments (not paths), so this is safe. **My recommendation:** (b).

### O-2. Confirm removal of legacy release-bundle endpoints (D-10)
Two options:
- **(a) Remove endpoints and file references** — cleaner; small surgical edit.
- **(b) Keep endpoints but return 410 Gone with a message** — preserves URL surface for anything still calling them.

My recommendation: **(a)** — the endpoints were internal-only (admin-gated), and there is no external caller to preserve compatibility for. Adds no code, removes ~50 lines of dead code.

---

## 7. Phase 2 checkpoint

Phase 2 is complete. The design is:
- **Flat, two-tree layout** (`app/` + `deployment/`) with docs + scripts at repo root.
- **13 architectural decisions** (D-1 through D-13), each with rationale.
- **Complete file migration matrix** (§3) covering every source → destination + action + justification.
- **8 recommended improvements** (R-1 through R-8) beyond the legacy implementation, each strictly organizational.
- **2 open items** (O-1, O-2) requesting your explicit go-ahead.

Nothing has been created, moved, edited, or written into `/app/canonical_repo/` yet. All work so far is on paper.

### Your options at this checkpoint

- ✅ **Approve Phase 2** (with your calls on O-1 and O-2) → I proceed to Phase 3: build the canonical repo locally under `/app/canonical_repo/`, initialize git, single clean commit, tag `v1.0.0`, and produce all the deliverable docs. Then stop again for your Phase 3 review before Phase 4 (static validation).
- 🔁 **Request revisions** → tell me what to reconsider, add, or drop.
- ⏸ **Pause** → I hold state.

Read-only rules still in force. No writes. No new repo. No bundle generation.

Standing by.
