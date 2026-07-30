# ArbiCore X — Canonical Repository (PRD)

## Original problem statement
Audit two legacy repositories (`ArbiCoreX-V01`, `arbicore-x-vps-bundle`) and
consolidate them into a single, clean, production-ready canonical repository
that serves as the sole source of truth for both application code and
deployment infrastructure. Deploy target: Contabo VPS running the
shared-infrastructure profile (co-tenant alongside "Strategy Factory").

## Repository
- Path: `/app/canonical_repo/`
- Current version: **v1.0.2**
- Distribution: manual (tarball / zip / git bundle) — user pushes to their
  own remote. Platform GitHub integration explicitly NOT used (it targeted
  the workspace repo, not the user's).

## Architecture (unchanged from v1.0.0)
```
canonical_repo/
├── app/{backend, frontend, opportunity_center}/
├── deployment/{compose, docker, nginx, ssl, monitoring, upgrade, backups}/
├── docs/{ARCHITECTURE.md, INSTALL.md, ROADMAP.md, releases/}
├── scripts/{install.sh, upgrade.sh, healthcheck.sh, backup.sh, restore.sh}
├── Makefile, README.md, VERSION, CONTRIBUTING.md, LICENSE
└── .dockerignore, .gitignore, .gitattributes
```

Two deployment profiles:
- **Greenfield** (`docker-compose.yml`): 6 services — mongo, backend,
  frontend, opportunity_center, nginx, certbot.
- **Shared infrastructure** (`docker-compose.shared.yml`): 3 services —
  backend, frontend, opportunity_center. External mongo + network +
  reverse proxy owned by peer stack (Strategy Factory).

## Current phase (Feb 2026): UI v2 Architecture

**Goal:** transform ArbiCore X from a BDAG-oriented terminal UI into a Universal Arbitrage Intelligence Platform cockpit. Backend remains stable (v1.0.2 in production); only additive UI-facing endpoints permitted.

**Deliverables** (`docs/ui_v2/`, versioned, committed @ `f0658ac`):
- `01_BACKEND_CAPABILITY_AUDIT.md` (389 lines) — 6-layer backend audit, 245 canonical endpoints
- `02_UI_EXPOSURE_MATRIX.md` (299 lines) — 38% current coverage, 152 uncovered endpoints mapped to target workflow
- `03_INFORMATION_ARCHITECTURE.md` (427 lines) — 7-section workflow-first IA (Home / Discovery / Opportunities / Portfolio / Intelligence / Operations / Settings), progressive-disclosure grammar
- `04_UI_V2_MASTER_SPEC.md` (542 lines) — page hierarchy, 6 workflows, 30 widgets, endpoint bindings, states, keyboard, 11 acceptance criteria
- `design_language.md` (199 lines, by design agent) — colours, typography (JetBrains Mono + IBM Plex Sans), 4px grid, motion, signature elements, anti-patterns
- `appendix/endpoints.tsv` — machine-readable per-endpoint UI coverage
- `appendix/panels.tsv` — 66-panel disposition: Keep 6 / Reposition 29 / Consolidate 16 / Rebuild 10 / Retire 5

**Binding principles:**
- Decision velocity, not information density
- Cockpit, not engine room (backend logic invisible unless surfacing changes an operator decision)
- Progressive disclosure L1 (what) → L2 (why) → L3 (receipts)
- Zero BDAG identity — BDAG is one market, one dataset, one learning source
- Universal opportunity card across all 8 scanner families

**Backend deltas (locked, additive only):**
- `GET /api/arbicore/dashboard/pulse` (Home Pulse band composition)
- `GET /api/arbicore/dashboard/deck` (Home Priorities band composition)
- `GET /api/arbicore/opportunities/summary` (Opportunities header)
- `GET /api/arbicore/roi-probability?route_id=…` (surface existing internal engine)

## Release history

### v1.0.0 (2026-01, initial canonical release)
- Consolidated app + infra into single repo.
- Documentation: ARCHITECTURE, ROADMAP, REPOSITORY_PHILOSOPHY,
  CANONICAL_CERTIFICATION, MIGRATION_SUMMARY.

### v1.0.1 (2026-01, first VPS deploy patch)
- Mongo auth doc fixes (auth-enabled peer mongo).
- Nginx `USER 101` chown permissions.
- `emergentintegrations` dependency swap.
- Docker compose healthcheck overrides.

### v1.0.2 (2026-02-05, current — frontend black-screen fix + verification harness)
- **Root cause**: `frontend/Dockerfile` never declared
  `ARG REACT_APP_BACKEND_URL` → compose `build.args` silently ignored →
  `yarn build` ran with undefined env var → Webpack emitted
  `"".concat(void 0,"/api")` (26 refs) → nginx SPA fallback + axios
  interpretation cascade → black screen.
- **Fix**: three-layer guard (compose `${VAR:?err}`, Dockerfile pre-build
  `[ -z "$VAR" ] && exit 1`, Dockerfile post-build grep against
  `void 0/undefined` in compiled output).
- Same treatment applied to Opportunity Center (`VITE_BACKEND_URL`).
- `docker-compose.shared.yml` gained `build:` blocks (was previously
  image-only, requiring images be built elsewhere).
- Greenfield changed `${REACT_APP_BACKEND_URL:-https://localhost}` soft
  default → `${REACT_APP_BACKEND_URL:?...}` hard requirement.
- `.env.shared.example` documents new required variable.
- **NEW: 8-category deployment verification harness**
  (`scripts/verify-deployment.sh`, `scripts/verify-browser.mjs`, `make
  verify`). Covers backend health, frontend + OC HTTP, bundle
  fingerprint (v1.0.1 regression guard), browser runtime, API
  connectivity, login flow, dashboard render. Playwright browser
  checks auto-skip if not installed. Standard release checklist for
  every future deployment.
- Empirically validated: 8/8 pre-deploy verification cases passed
  (positive AND negative reproduced).

## New required environment variable (v1.0.2)
- **`REACT_APP_BACKEND_URL`** — public URL where the operator UI is
  served (e.g., `https://arbicore.example.com`). Set in `.env.shared`
  (shared profile) or repo-root `.env` (greenfield). Baked into JS
  bundle at BUILD time. No trailing slash, no path suffix.

## Distribution artifacts (v1.0.2, at `/app/`)
- `arbicore-x-v1.0.2.tar.gz` (1.2 MB, source, no `.git`)
- `arbicore-x-v1.0.2.zip` (1.6 MB, source, no `.git`)
- `arbicore-x-v1.0.2.bundle` (1.4 MB, full git history + tags)
- `arbicore-x-v1.0.2.sha256` (checksums)

## Deployment status
- v1.0.1 deployed to Contabo VPS — containers healthy, frontend black.
- v1.0.2 ready for user to pull + rebuild + redeploy. Full instructions
  in `docs/releases/v1.0.2.md`.

## Roadmap / Backlog
- **P0** — UI v2: awaiting sign-off on Master Spec (Phase 4 complete). Phase 5 (Implementation Roadmap) is the next architectural deliverable, then a sliced implementation begins.
- **UI v2 backend delta**: 4 additive composed endpoints (`dashboard/pulse`, `dashboard/deck`, `opportunities/summary`, `roi-probability`). Small PR, no logic changes.
- **ENH-001 (post-v1.0.2, target v1.1.0)** — continuous verification metrics: `scripts/verify-metrics.sh` Prometheus text-format exporter, cron template, Grafana dashboard JSON, `docs/OBSERVABILITY.md`. Filed in `docs/ROADMAP.md` §9a. Deferred until v1.0.2 is stable in production (currently satisfied).
- **P2**: end-to-end smoke test that runs against a live VPS deployment (largely superseded by v1.0.2's `make verify` harness).
- **P2**: CI pipeline (GitHub Actions) that runs the compose validation + Dockerfile guard tests on every PR.
- **P2**: registry publishing workflow (push tagged images to registry.example.com).

## Non-goals (explicitly out of scope)
- Automated GitHub push from the platform (user handles pushes manually).
- Multi-region / HA — single-VPS deployment is the design target.

## Testing
- Static YAML validation (docker-compose v5.3.1 CLI installed in sandbox
  for validation runs).
- Empirical bundle inspection (`yarn build` in-sandbox, then grep
  compiled JS for both positive and negative cases).
- Full end-to-end (login page renders, auth against backend, no
  regression to Strategy Factory) is USER-side on the Contabo VPS,
  per the v1.0.2 upgrade instructions.
