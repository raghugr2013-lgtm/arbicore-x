# Canonical Certification — ArbiCore X v2.0.2 (Production Entry Experience)

**Certification date:** 2026-08-02
**Tag:** `v2.0.2`
**Scope:** frontend routing refinement — Login → Initialization → Dashboard

## Verdict (v2.0.2)

> ✅ **CERTIFIED for deployment to VPS in SHADOW mode.**

The "Preview Pod" landing page is retired.  The application now opens
into the production entry experience: unauthenticated users see the
Login page, authenticated users transition through a professional
Initialization screen that hits real backend health endpoints, then
land on the Dashboard as the application's home.

## Delta from v2.0.1

- **New pages:** `LoginPage.jsx` + `InitializationPage.jsx` (+ tokenised CSS)
- **New context:** `AuthContext.jsx` (localStorage-backed session; drop-in
  replaceable when backend `/api/auth/login` is activated in Sprint 1B)
- **New routing:**
  - `/`               → routes based on auth+init state
  - `/login`          → LoginPage (unauthenticated only)
  - `/initialization` → InitializationPage (authenticated, uninitialized)
  - `/dashboard/*`    → AppShell (formerly `/v2/*`) — protected
  - `/v2/*`           → legacy alias, redirects to `/dashboard`
- **Initialization steps** (each hits a real backend endpoint):
  - "Connecting to Market…"                       → `GET /api/`
  - "Loading Intelligence…"                       → `GET /api/system/status`
  - "Synchronizing Market Intelligence Database…" → `GET /api/arbicore/mid/status`
  - "Preparing Opportunity Engine…"               → `GET /api/arbicore/opportunities/summary`
- **Design language:** obsidian + amber consistent with UI v2 tokens; no
  new dependencies added.

## Verified

Frontend automated browser suite:
- `/` redirect to `/login` — pass
- Login validation (empty fields, short passphrase) — pass
- Login → `/initialization` — pass
- Initialization sequential steps (4/4 respond) — pass
- Initialization → `/dashboard` — pass
- `/dashboard` mounts the AppShell (`v2-root` + `v2-content` present) — pass
- `/v2` deep-link redirects to `/dashboard` — pass
- Session persistence across reload — pass
- "Preview Pod" text no longer exists anywhere on the page — pass

## Backend regression

Untouched — 1469 tests still pass (no backend business logic changed).

---

# Canonical Certification — ArbiCore X v2.0.1 (Sprint 1A · MID)

**Certification date:** 2026-08-02
**Tag:** `v2.0.1`
**Scope:** Market Intelligence Database (MID) foundation

## Verdict (v2.0.1)

> ✅ **CERTIFIED for deployment to VPS in SHADOW mode.**

Sprint 1A shipped the platform-wide persistent intelligence foundation per operator directive. Every observation the platform produces will be permanently recorded through the MID façade from the first tick after deployment.

### Delta from v2.0.0

- **New module:** `arbicore/data/mid/` (5 files: `__init__`, `enums`, `schemas`, `writers`, `readers`, `indexes`)
- **New collections:** 11 (10 domain + `mid_enum_warnings`)
- **New REST endpoints:** 3 (`/api/arbicore/mid/status`, `/api/arbicore/mid/query/{domain}`, `/api/arbicore/mid/enums`)
- **New tests:** 27 (`tests/test_mid_sprint1a.py`)
- **Regression:** 1442 → **1469 passed**, 76 skipped, 0 failed (delta: +27, all MID)

### Design invariants enforced

1. **Single write path** — every producer routes through `MidWriter`
2. **Additive-only Mongo schema** — new `mid_*` collections; no existing collections modified
3. **Per-domain TTL** — configurable, sensible defaults (permanent: routes/opportunities/decisions/outcomes)
4. **No parallel storage systems**
5. **Zero new external dependencies**
6. **Strategy-agnostic** — every row carries `{strategy_type, opportunity_type, capital_source, chain, protocol, execution_mode, market_regime, tags[]}` metadata (v2.0.1 populates flash-loan values; future strategy families require zero migration)
7. **Replay-ready** — every row carries a `replay_context` block (`block_number`, `block_timestamp`, `quote_snapshot_id`, `liquidity_snapshot_id`, `gas_snapshot_id`, `route_snapshot_id`, `decision_snapshot_id`, `market_snapshot_id`)
8. **Stable canonical identifiers** — `mid_id` (row UUID), `event_id`, `route_id`, `provider_id`, `market_snapshot_id`. Downstream analytics reference by ID.

### What Sprint 1A does NOT include (deferred to Sprint 1B onward, per operator directive)

- Wiring dormant intelligence producers (Confidence, ROI, Route Ranking, Economics, Regime, Entity Scoring) to write into the MID — the API is present; the producers get wired in Sprint 1B on the deployed VPS
- Scanner activation (dex_arbitrage, flash_loan_arbitrage) — Sprint 1B
- Opportunity Lifetime Intelligence (P1-β) — Sprint 2
- Historical Market Intelligence (P1-γ) — Sprint 3
- Replay & Outcome Intelligence + Stablecoin Depeg gate — Sprint 4

### Deployment instructions

See [`V2_MIGRATION_GUIDE.md`](V2_MIGRATION_GUIDE.md). No new required env vars; the MID starts in bootstrap mode with default per-domain TTL policies. Operator can adjust TTLs from Settings → Market Intelligence Database once the UI card ships in Sprint 1B.

---

# Canonical Certification — ArbiCore X v2.0.0

**Certification date:** 2026-08-02
**Repository HEAD:** (initial v2.0.0 commit — see `git log`)
**Tag:** `v2.0.0`
**Certifier:** merged canonical consolidation session
**Runtime validation scope:** deferred to target VPS (see `docs/V2_MIGRATION_GUIDE.md`)

---

## Verdict (v2.0.0)

> ✅ **CERTIFIED as the canonical production baseline for ArbiCore X, subject to runtime validation on target VPS.**

This release is the merged canonical consolidation of:
- `arbicore-x` v1.0.2 — the previous deployment-complete canonical
- `Arbicorex-ui-v2-slice-02` — the UI v2 + Wave 6 + Phase 7–10 development slice

Both source repositories were treated as equal sources of truth. Each subsystem was audited independently; the strongest verified implementation was retained. See `docs/V2_CONSOLIDATION_AUDIT.md` for the full subsystem-by-subsystem decision matrix.

### Static acceptance criteria (v2.0.0)

| # | Criterion | Status |
|---|---|:-:|
| 1 | Self-contained (no dependency on either legacy repo) | ✅ Pass |
| 2 | Production-ready deployment tree preserved from v1.0.2 | ✅ Pass |
| 3 | UI v2 + Wave 6 + Phase 7–10 code fully absorbed from ui-v2-slice | ✅ Pass |
| 4 | Clone-and-build capable from a clean checkout | ✅ Pass |
| 5 | No parallel architectures (one server, one arbicore package, one frontend, one opportunity_center, one deployment tree) | ✅ Pass |
| 6 | Dormant modules preserved in-tree, not wired into `server.py` (per directive 4b) | ✅ Pass |
| 7 | Merged regression suite green, all remaining tests pass | ✅ Pass |

### Regression evidence

```
$ cd app/backend && pytest tests/ -n 2 --dist loadscope

1442 passed, 76 skipped, 0 failed in 13.60s
```

**Test-suite composition:**
- 46 tests from the ui-v2-slice repository — 100 % green (599 assertions, 2 skipped)
- 72 tests from arbicore-x v1.0.2 that pass against the merged server — 100 % green (843 assertions, 74 skipped)
- 45 tests from arbicore-x v1.0.2 that exercise dormant modules — moved to `tests/_pending_scanner_activation/` (excluded from default regression per user directive 5c; re-included when the corresponding module cluster is activated in a future validation wave)

### File census (v2.0.0)

- Total tracked files: **793**  (~+160 over v1.0.2 as UI v2 pages, execution/evidence/notification/secret modules, phase 10 docs, and ui_v2 architecture docs are added)
- Backend Python files: **484** (v1.0.2 had 377; +107 = Wave 6 + Phase 7–10 additions)
- Backend test files (active): **118**
- Backend test files (pending activation): **45**
- Frontend v2 pages: **12**
- Deployment: unchanged (matches v1.0.2 static validation)

---

## Deferred runtime validation (v2.0.0)

Runtime bring-up (`docker compose build` + service start + full UI walkthrough + first flash-loan preflight) is deferred to the target VPS. Operators should follow `docs/V2_MIGRATION_GUIDE.md` § 2 (upgrade path) or § 3 (fresh install). Once the following pass on the VPS, this file will be amended with a "Runtime certified on ${DOMAIN} on YYYY-MM-DD" section:

- `make install` completes all 9 phases green
- `make healthcheck` reports all containers healthy
- `/api/system/status` reports `features.ui_v2=true`
- Legacy UI at `/` renders with feature flag OFF
- UI v2 at `/v2/*` renders with feature flag ON
- Flash Loan Operator page (`/v2/flash-loan`) loads and preflight-reverts against Base mainnet as expected
- Journey page (`/v2/journey`) reflects stage progression
- Certbot renewal loop is healthy

---

## Governance

From v2.0.0 forward:

1. This repository is the **single source of truth** for both application code AND deployment infrastructure.
2. The two legacy source repositories (`arbicore-x` v1.0.2 and `Arbicorex-ui-v2-slice-02`) are frozen and read-only.
3. All future releases originate from this repository. All future deployments deploy from this repository.
4. Dormant module activation is a per-cluster follow-up wave (tag as `v2.1.0`, `v2.2.0`, etc.). Activation moves the associated test file(s) back from `tests/_pending_scanner_activation/` to `tests/` and requires the merged regression to remain green.

---


# Canonical Certification — ArbiCore X v1.0.0

**Certification date:** 2026-07-29
**Repository HEAD:** `d934f11` (main)
**Tag:** `v1.0.0`
**Certifier:** Phase 4 static validation suite
**Runtime validation scope:** deferred to Contabo VPS (Phase 5 post-approval)

---

## Verdict

> ✅ **CERTIFIED as the canonical production baseline for ArbiCore X, subject to runtime validation on target VPS.**

Every static acceptance criterion passes. Two remediation cycles were performed during Phase 4 (documented in §4) to eliminate all real findings surfaced by the validation suite. No Critical, Major, or Minor issues remain open. One Informational note is retained for transparency.

Runtime bring-up (`docker compose build` + service start + healthcheck) is not verifiable inside the Kubernetes preview environment (no docker CLI available). This is by design — final runtime certification happens on the Contabo VPS after Phase 5 review, using the exact commands documented in `docs/INSTALL.md`.

---

## 1. Acceptance criteria — evidence

| # | Criterion | Status | Evidence |
|---|---|:-:|---|
| 1 | **Self-contained** | ✅ Pass | 629 files tracked in a single commit; no `.gitmodules`; zero references to legacy repositories in scripts/deployment/app trees (only permitted references are inside `docs/MIGRATION_SUMMARY.md`, `docs/EXCLUSIONS.md`, `docs/REPOSITORY_PHILOSOPHY.md`, `docs/ROADMAP.md`, `CONTRIBUTING.md`, and the retirement-stub docstring — all intentional). |
| 2 | **Production-ready** | ✅ Pass | Compose file: 6 services, all with healthchecks, resource limits, log caps, provenance labels. `.env` templates cover every var referenced by compose+scripts. Non-root uids (999 mongo, 1001 backend, 101 nginx-alpine). No secrets in images. Refuse-if-exists installer guard. Named-volume data anchor. |
| 3 | **Fully reproducible** | ✅ Pass | `app/frontend/yarn.lock` (581 KB, yarn 1.22.22) + `.npmrc` (`legacy-peer-deps=true`) canonical from day one — resolves the `react-day-picker`/`date-fns` peer conflict that broke reproducible frontend builds in the legacy app repo. Backend deps pinned in `deployment/docker/backend/requirements.prod.txt`. Mongo image pinned via `${MONGO_IMAGE:-mongo:4.4}`. All other images pinned to specific versions (`nginx:1.25-alpine`, `node:20-alpine`, `python:3.11-slim`, `certbot/certbot:latest` — see §7 note on certbot). |
| 4 | **Clone-and-run capable** | ✅ Pass | `git clone` → copy `.env.production.example` → `.env` → edit → `make install`. Single-command install after env configuration. `Makefile` at repo root provides `install`, `upgrade`, `up`, `down`, `logs`, `status`, `healthcheck`, `backup`, `restore`, `test-backend`, `build`, `env-check`, `version`. |
| 5 | **Free of obsolete and duplicate assets** | ✅ Pass | 40+ Emergent-session artefacts, historical release notes, SHASUMS files, legacy audit trees, `release_bundle/` tree, `deployment-bundle.zip` all excluded (recorded in `docs/EXCLUSIONS.md`). Zero duplicated compose files. Zero duplicated Dockerfiles. One env template per audience (canonical/prod/dev/shared). |
| 6 | **Independent of all legacy repositories** | ✅ Pass | No submodules, no `origin` remote of any legacy repo, no path references to `ArbiCoreX-V01/…` or `arbicore-x-vps-bundle/…` outside the deliberate MIGRATION_SUMMARY.md provenance section. `grep -r 'arbicore-x-vps-bundle\|ArbiCoreX-V01' app/ deployment/ scripts/` returns only the retirement-stub URL literal to `github.com/raghugr2013-lgtm/arbicore-x` and the historical URL in the retirement-stub docstring comment. |
| 7 | **Independent of historical deployment bundles** | ✅ Pass | Zero references to `arbicore-x-vps-bundle-0.1.0*.tar.gz`, `arbicore-x-deployment-bundle.zip`, SHASUMS files, or bundle-root path conventions outside `MIGRATION_SUMMARY.md`/`EXCLUSIONS.md`. All operator flows start from `git clone`. |

## 2. Static validation results

| # | Check | Result | Note |
|---|---|:-:|---|
| 1 | Shell script syntax (`bash -n`) — 27 scripts | ✅ 27/27 | No syntax errors. |
| 2 | Python AST parse — 377 `.py` files in `app/backend/` | ✅ 377/377 | No parse errors. |
| 3 | Compose YAML parse (greenfield) — `deployment/compose/docker-compose.yml` | ✅ Pass | 6 services (mongo, backend, frontend, opportunity_center, nginx, certbot). Every service (except certbot which runs a renewal loop) has healthcheck, deploy.resources.limits, logging. |
| 4 | Compose YAML parse (shared) — `deployment/compose/docker-compose.shared.yml` | ✅ Pass | 3 services (backend, frontend, opportunity_center). Attaches to external network. |
| 5 | `.env` template completeness — greenfield compose ↔ `.env.example` | ✅ Pass | 7 compose vars, 34 template keys, 0 missing. |
| 5 | `.env` template completeness — greenfield compose ↔ `.env.production.example` | ✅ Pass | 7 compose vars, 34 template keys, 0 missing. |
| 5 | `.env` template completeness — shared compose ↔ `.env.shared.example` | ✅ Pass | 32 compose vars, 33 template keys, 0 missing. |
| 6 | Forbidden dependencies in `requirements.prod.txt` — {emergentintegrations, litellm, black, flake8, isort, mypy, pytest, ruff, bandit, ipython} | ✅ Pass | 0 matches on requirement lines. |
| 7 | Hardcoded secrets in Dockerfiles — patterns `password=`, `token=`, `secret=`, `apikey=`, `api_key=` with literal values | ✅ Pass | 0 matches. |
| 8 | Hardcoded public FQDNs in `deployment/` | ✅ Pass | Only allow-listed `example.com` (in `.env.shared.example` comments and `uptime-probe.sh` header example). |
| 8 | Hardcoded public IPs in `deployment/` | 🟡 Informational | `1.1.1.1` and `8.8.8.8` in `deployment/nginx/snippets/ssl.conf:12` — Cloudflare + Google DNS resolvers used for nginx OCSP-stapling. Industry-standard default; not a security or reproducibility concern. Retained. |
| 9 | Path-reference sanity — all critical script/compose paths exist | ✅ 45/45 | Every path referenced by scripts, compose files, and operator docs resolves to a real file. |
| 9 | Legacy path patterns eliminated (except in provenance docs) | ✅ Pass | `infrastructure/*`, `BUNDLE_ROOT`, `arbicore-x-deployment-bundle.zip`, `arbicore-x-vps-bundle-…tar.gz` — all zero occurrences in scripts/deployment/app trees. |
| 10 | Application-tree isolation — `grep -r "deployment/\|scripts/.*\.sh" app/**/*.py` | ✅ Pass | Only occurrence is the retirement-stub comment in `app/backend/arbicore/routes/opportunity_center.py` (documentation reference in a docstring, not executable code). App tree does not import or exec any deployment code. |
| 11 | Docs ↔ implementation path consistency | ✅ Pass | All backtick-quoted paths in operator docs resolve to a real file. Future-direction references in `ROADMAP.md` (`deployment/network/`, `deployment/observability/`, `deployment/secrets/`, `deployment/upgrade/migrations/`) and anti-pattern examples in `CONTRIBUTING.md` are explicitly labeled as hypothetical. |
| 12 | Every var required by `install.sh` is present in `.env.production.example` | ✅ Pass | 100% coverage. |
| 13 | Git hygiene: no real `.env` tracked | ✅ Pass | 0 real `.env` files tracked; only `.example` templates. |
| 14 | Git hygiene: `.gitignore` and `.gitattributes` present and coherent | ✅ Pass | LF enforcement for `.sh`, `.py`, `.yml`, `.md`, `.conf`, and other text; binaries marked. `release_bundle/`, `backups/`, real `.env` all ignored. |
| 15 | Line endings — no CRLF in shell scripts (checked via git attribute) | ✅ Pass | `.gitattributes` sets `*.sh text eol=lf` globally. |
| 16 | Executable bits on shell scripts (git index mode `100755`) | ✅ 27/27 | All shell scripts marked executable in the git index. |

## 3. Runtime checks deferred to Contabo VPS (Phase 5)

The following are out of scope for static Phase 4 validation in this preview environment (no docker CLI available). They are documented for execution on your Contabo VPS after Phase 5:

| # | Check | Where to run |
|---|---|---|
| R-1 | `docker compose config` against `docker-compose.yml` (schema-level validation) | On the target VPS after `cp .env.production.example .env && $EDITOR .env` |
| R-2 | `docker compose build` — all three built images resolve dependencies and complete | On the target VPS |
| R-3 | `docker compose up -d` — every container reaches `healthy` state within its healthcheck window | On the target VPS |
| R-4 | Let's Encrypt staging cert issuance succeeds | On the target VPS |
| R-5 | `curl -fs https://${DOMAIN}/api/` returns 200 | On the target VPS |
| R-6 | `make backup` produces an archive, `make restore` round-trips cleanly | On the target VPS |
| R-7 | Upgrade path from `v1.0.0` to a subsequent tag succeeds without data loss (deferred to first upgrade) | On the target VPS at first upgrade |
| R-8 | Nginx OCSP stapling succeeds against production Let's Encrypt certs | On the target VPS |

Exact commands to execute R-1 through R-6 in one continuous script are documented in `docs/INSTALL.md`.

## 4. Phase 4 remediation record

Two remediation cycles were applied during Phase 4 to resolve real findings surfaced by the validation suite. All fixes were made in-place on the Phase 3 tree and the `v1.0.0` tag was moved forward via `git commit --amend + git tag -f` so history remains a single clean commit.

### Cycle 1 — MAJOR: broken script paths after flat-layout rename
Discovered by CHECK 9 (path-reference verification). Three deployment scripts still `cd`-ed into `infrastructure/greenfield/` — a path that no longer exists in the flat canonical layout. These would fail at runtime on first `scripts/install.sh` invocation.

| File | Fix |
|---|---|
| `deployment/ssl/init-letsencrypt.sh` | `BUNDLE_ROOT` → `REPO_ROOT`; `cd $BUNDLE_ROOT/infrastructure/greenfield` → `cd $REPO_ROOT/deployment/compose` |
| `deployment/ssl/renew.sh` | Same rename; also fixed the cron-example path in the header comment (`/opt/arbicore-x/infrastructure/ssl/renew.sh` → `/opt/arbicore-x/deployment/ssl/renew.sh`) |
| `deployment/backups/backup-cron.sh` | Same rename; `BACKUP_DIR` default changed from `$BUNDLE_ROOT/infrastructure/backups/archives` → `$REPO_ROOT/backups`; delegate path corrected to `$REPO_ROOT/deployment/backups/backup.sh` |
| `deployment/ssl/cronjob.example` | Cron path updated to `/opt/arbicore-x/deployment/ssl/renew.sh` |
| `deployment/docker/frontend/Dockerfile`, `.../opportunity_center/Dockerfile` | Header comments updated to describe the current `REPO ROOT` build context (removed RC-lineage "bundle version" comment; removed references to `infrastructure/greenfield/`) |

**Severity:** MAJOR (runtime failure). **Resolution:** fixed and re-verified. `find` shows zero remaining `infrastructure/` references in `scripts/`, `deployment/`, or `app/`.

### Cycle 2 — MINOR: doc drift referencing legacy paths and dead audit docs
Discovered by CHECK 11 (docs ↔ implementation path consistency). Nine operational docs still described the pre-flatten layout (`infrastructure/greenfield/…`, `infrastructure/realignment/arbicore-x-deploy/…`, `infrastructure/shared-infrastructure/…`) and 10 lines pointed at dead audit-doc paths (`docs/audit/legacy/*.md`, `app/release_bundle/…`, `VPS_DEPLOYMENT_AND_SHADOW_RUNBOOK`).

Systematic Python replacement pass across 9 docs performed **69 path replacements** and **10 dead-reference line removals**. Files affected: `INSTALL.md`, `OPERATIONS.md`, `UPGRADE.md`, `ROLLBACK.md`, `BACKUP_RESTORE.md`, `SSL.md`, `SECURITY.md`, `TROUBLESHOOTING.md`, `SHARED_INFRASTRUCTURE.md`. Two additional targeted fixes: (a) one leftover "realignment profile" phrasing in `SHARED_INFRASTRUCTURE.md`, and (b) header comments of `docker-compose.shared.yml` + `.env.shared.example` updated to reference the new path.

**Severity:** MINOR (documentation drift; no runtime impact). **Resolution:** fixed and re-verified. All 22 previously-broken doc-path references resolve to real files.

**Total changes across both cycles:** 16 files edited, 85 insertions, 100 deletions. Amended into the single `v1.0.0` commit — repo history remains one clean commit.

## 5. Findings — final residual list

| Severity | Count | Details |
|---|---:|---|
| Critical | 0 | — |
| Major | 0 | (All Cycle-1 items fixed) |
| Minor | 0 | (All Cycle-2 items fixed) |
| Informational | 1 | `1.1.1.1` and `8.8.8.8` DNS resolvers hard-coded in `deployment/nginx/snippets/ssl.conf` for OCSP stapling. This is nginx's canonical default; alternative (reading `/etc/resolv.conf`) is more fragile in containers. No action recommended. |

## 6. Six mission-contract success questions — answered

1. **What is the canonical production implementation?**
   The repository at `/app/canonical_repo/`, tagged `v1.0.0`, HEAD `d934f11`, 629 files, 6.1 MB working tree.

2. **Which files should be retained?**
   Every file present in the tag `v1.0.0`. Full inventory in `docs/MIGRATION_SUMMARY.md`.

3. **Which files should be removed?**
   None from within the canonical repo. Full list of assets deliberately excluded from the migration is in `docs/EXCLUSIONS.md` (40+ items, grouped by source).

4. **Which files require regeneration?**
   None. All regeneration work required by the migration was completed during Phase 3 (`.gitignore`, `.gitattributes`, `README.md`, `VERSION`, `.dockerignore`, `Makefile`, and the top-level scripts). Cycle-1/Cycle-2 remediation completed the last remaining path corrections.

5. **Is the system production-ready today?**
   ✅ Static readiness confirmed. Runtime readiness is pending validation on the target Contabo VPS per §3.

6. **If not, what exact work remains before the first certified production release?**
   From this repository: nothing. All remaining work is runtime validation on the target VPS (steps R-1 through R-8 in §3), executed by running `make install` on a clean Ubuntu VPS and observing the documented expected outputs. If any R-* step fails, remediation returns here as a targeted PATCH commit under the versioning rules in `docs/ROADMAP.md` §2.

## 7. Notes and known limitations

- **`certbot/certbot:latest` pin** — The greenfield compose pins `certbot/certbot:latest`. Certbot's own release cadence is disciplined, and `:latest` is the tag the Certbot team recommends for this deployment pattern. However, "latest" is technically a floating tag. In a later minor release we may pin to a specific version (e.g., `certbot/certbot:v2.11.0`). Not blocking for `v1.0.0`.
- **RC lineage retired** — Tags `v0.1.0-rc1`, `v0.1.0-rc2`, `v0.1.0-rc2.2` remain in the archived VPS bundle repository. This canonical repository does not carry them. `v1.0.0` is a clean-slate baseline.
- **Deployment on a machine without docker compose v2** — the installer falls back to `docker-compose` (v1) automatically. Both work. `docker compose v2` is the recommended path.
- **First install always uses `LETSENCRYPT_MODE=staging`** — safety default in `install.sh`. Operators flip to `prod` after verifying the staging cert issued successfully. Documented in `docs/INSTALL.md` and `docs/SSL.md`.

## 8. Ongoing governance

Governance framework in `docs/ROADMAP.md` (SemVer + release process + branch strategy + extension rules + anti-fragmentation invariants). Contribution standards in `CONTRIBUTING.md`. Philosophy in `docs/REPOSITORY_PHILOSOPHY.md`. Any change that reintroduces a legacy pattern listed in `EXCLUSIONS.md` requires an ADR in `docs/ARCHITECTURE.md` and repository-owner approval.

---

## Signature block

> This document certifies that the repository at HEAD `d934f11` on branch `main`, tagged `v1.0.0`, satisfies the static acceptance criteria for the canonical production baseline of ArbiCore X. Runtime certification is contingent on successful completion of the Contabo VPS validation steps in §3.

**Certified:** 2026-07-29
**Repository:** intended destination `raghugr2013-lgtm/arbicore-x` (private) — not yet published
**Next step:** Phase 5 review + Save-to-GitHub, then runtime validation on target VPS
