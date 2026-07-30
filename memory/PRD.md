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

## Current phase (Feb 2026): UI v2 Architecture — Complete, Ready to Implement

**Goal:** transform ArbiCore X from a BDAG-oriented terminal UI into a Universal Arbitrage Intelligence Platform cockpit. Backend remains stable (v1.0.2 in production); only additive UI-facing endpoints permitted.

**All 5 architecture phases complete** (`docs/ui_v2/`, versioned, committed @ `a40740b`):
- `README.md` — reading order + Final Design Principle
- `01_BACKEND_CAPABILITY_AUDIT.md` (389 lines) — 6-layer backend audit, 245 canonical endpoints
- `02_UI_EXPOSURE_MATRIX.md` (299 lines) — 38% current coverage, 152 uncovered endpoints mapped
- `03_INFORMATION_ARCHITECTURE.md` (437 lines) — 7 sections (Home / Discovery / Opportunities / Portfolio / Intelligence / Operations / Settings)
- `04_UI_V2_MASTER_SPEC.md` (576 lines) — page hierarchy, 6 workflows, 30 widgets, 14 acceptance criteria (incl. A/B/C from review)
- `design_language.md` (241 lines) — premium institutional aesthetic; existing ArbiCore brand palette (amber `#ffb224`, obsidian, Plex Mono + Archivo)
- `05_IMPLEMENTATION_ROADMAP.md` (299 lines) — 6-slice sequenced delivery plan
- `appendix/USER_JOURNEYS.md` (332 lines) — 8 canonical operator journeys with time budgets (usability benchmark)
- `appendix/wireframes.md` (450 lines) — ASCII wireframes for 7 primary screens
- `appendix/endpoints.tsv` + `appendix/panels.tsv` — machine-readable coverage + panel disposition

**Binding Final Design Principle:**
> ArbiCore X is an AI-powered Arbitrage Intelligence Platform.
> Backend is the intelligence engine. Frontend is the operator cockpit.
> Complexity belongs inside the engine. Clarity belongs in the cockpit.

**Backend deltas (locked, Slice 0):** 4 additive composed endpoints only.
- `GET /api/arbicore/dashboard/pulse`
- `GET /api/arbicore/dashboard/deck`
- `GET /api/arbicore/opportunities/summary`
- `GET /api/arbicore/roi-probability?route_id=…`

**Implementation plan (6 slices, ~10 dev weeks):**
0. **Backend delta + feature flag + `/v2` sub-app scaffold — SHIPPED 2026-02-06.**
1. Foundations + Home + Opportunities + Opportunity Drawer (~2 wks) — enables J1/J2/J3
2. Discovery + Intelligence: Recommendations + Confidence (~1.5 wks) — enables J4
3. Operations: Scanners + Cycles + Venues + Interlock (~1.5 wks) — enables J6/J7
4. Portfolio + Intelligence: Analytics + Certification (~1.5 wks) — enables J5
5. Intelligence: Market/Learning/Knowledge + Settings + remaining Ops (~1.5 wks) — enables J7/J8
6. Polish, Cutover, Developer Mode, Docs (~1 wk)

## Release history

### Slice 0 — UI v2 backend delta + feature flag + `/v2` shell (2026-02-06)
- **Backend delta** — 4 additive composed endpoints (`app/backend/arbicore/routes/dashboard.py`):
  - `GET /api/arbicore/dashboard/pulse` — regime + opportunity vitals + route-learning + pointer hints to canonical endpoints
  - `GET /api/arbicore/dashboard/deck` — fresh opportunities from `OpportunityRepo.find({})`, plus pointer counts for approvals/attention
  - `GET /api/arbicore/opportunities/summary` — counts by family / chain / status
  - `GET /api/arbicore/roi-probability?route_id=…` — direct surface for `MongoRouteSuccessTracker` per-route stats
  - All endpoints are pure compositions; every downstream failure degrades to `None` / zero rather than 500 (defensive `_safe()` wrapper). No mutation, no new business logic, no changes to existing endpoint shapes.
  - Routers registered in `server.py` (`arbicore_dashboard_router`, `arbicore_opportunities_router`, `arbicore_roi_router`).
- **Feature flags** — two independent toggles:
  - Backend: `UI_V2_ENABLED` env var, surfaced on `GET /api/system/status` under `features.ui_v2`.
  - Frontend: `REACT_APP_ENABLE_UI_V2` build-time flag + `?ui_v2=1` / `localStorage.arbicore_ui_v2` runtime override. Legacy UI at `/` unchanged; when disabled, `/v2/*` redirects to `/`.
  - Dockerfile + compose files pass the new frontend arg (soft; defaults to `false`). `.env.example`, `.env.production.example`, `.env.development.example`, and `deployment/compose/.env.shared.example` all document both flags.
- **Frontend shell** — modular sub-app under `app/frontend/src/v2/`, isolated from legacy code:
  - `theme/tokens.css` — CSS variables mirroring `docs/ui_v2/design_language.md` §2 (obsidian surfaces, amber accent, verdict/regime/health/freshness/confidence ramps, Archivo + IBM Plex Mono).
  - `lib/{featureFlag,api,nav}.js` — flag resolver, thin axios wrapper on `REACT_APP_BACKEND_URL`, 7-section nav registry.
  - `components/{AppShell,Header,LeftNavRail,SectionPlaceholder}.jsx` — 48 px header + 64 px icon rail per Binance Desktop conventions.
  - `pages/{Home,Discovery,Opportunities,Portfolio,Intelligence,Operations,Settings}Page.jsx` — Home wires the live Slice 0 endpoints as a preview; the other six render `SectionPlaceholder` citing their scheduled slice.
- **Contract tests** — `app/backend/tests/test_dashboard.py` (12 tests, all green). Composition getters stubbed with `InMemoryOpportunityRepository` + `InMemoryRegimeSnapshotRepository` + a route-tracker stub; no Mongo, no live services. Includes explicit degraded-source tests (`test_pulse_swallows_repo_failures`, `test_summary_swallows_repo_failure`, `test_roi_probability_swallows_tracker_failure`) that prove endpoints return 200 with graceful nulls when downstream repos raise.
- **Build verification** — CRA build succeeds both flag-on and flag-off. Baked bundle contains expected v2 identifiers (`arbicore_ui_v2`, `ui-v2-root`, `v2-header`, `v2-rail`) and the v1.0.2 regression fingerprint (`undefined/api`) is not present.
- **Architecture note** — all v2 code lives in `src/v2/`, `.ui-v2-root`-scoped CSS, and self-contained routing. This preserves the "future extraction into a shared design-system package" path called out in the user brief.

## Older release history

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
- **P0 — Slice 1 (Foundations + Home + Opportunities + Opportunity Drawer, ~2 wks)** — replaces the Slice 0 Home preview with the full Pulse → Priorities → Vitals band, universal opportunity feed + card, opportunity drawer (6 tabs), ⌘K palette, shared component library. Enables journeys J1/J2/J3.
- **P1 — Slice 2** — Discovery + Intelligence: Recommendations + Confidence. Enables J4.
- **P1 — Slice 3** — Operations: Scanners + Cycles + Venues + Interlock. Enables J6/J7 partial.
- **P1 — Slice 4** — Portfolio + Intelligence: Analytics + Certification. Enables J5.
- **P1 — Slice 5** — Intelligence: Market + Learning + Knowledge + Settings + remaining Ops. Enables J7 full + J8.
- **P1 — Slice 6** — Polish, cutover to `/`, Developer Mode, retirement audit, Playwright journey suite, `v1.1.0` cut.
- **ENH-001 (post-UI-v2, target v1.2.0)** — continuous verification metrics: `scripts/verify-metrics.sh` Prometheus text-format exporter, cron template, Grafana dashboard JSON, `docs/OBSERVABILITY.md`. Filed in `docs/ROADMAP.md` §9a. Deferred until UI v2 stable.
- **P2**: CI pipeline (GitHub Actions) that runs the compose validation + Dockerfile guard tests on every PR.
- **P2**: registry publishing workflow (push tagged images to registry.example.com).
- **v1.3 candidate** — Light mode (tokens already CSS variables), i18n, mobile companion view.

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
