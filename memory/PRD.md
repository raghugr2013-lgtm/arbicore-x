# ArbiCore X — PRD (Program Reference Document)

## Original problem statement (v2.9.1 maintenance)

Continue ArbiCore X — v2.9.1 Maintenance Release.

The previous workspace was interrupted mid-flight while preparing a
v2.9.1 maintenance release; it had identified three deployment blockers
but had not implemented them. Ship a clean v2.9.1 that:

1. Renames `app/backend/arbicore/providers/aux.py` (Windows reserves AUX;
   blocks git checkout on Windows dev machines).
2. Promotes `REACT_APP_BACKEND_URL` to REQUIRED in the .env contract so
   fresh Docker builds don't fail on the empty variable.
3. Removes runtime `pip install` from `arbictl` (Ubuntu 24 / PEP 668).
4. Verifies deployment end-to-end (compose, backend, frontend, OCE,
   arbictl, env loading, Windows clone, Ubuntu VPS).
5. No new features, scanners, providers, UI work, execution logic, APIs
   or behavioural changes.
6. Produces v2.9.1 bundle + SHASUMS + release notes; updated OPS_GUIDE
   and DEPLOYMENT_CHECKLIST; git tag v2.9.1; commit and tag pushed to
   the connected GitHub repository from the workspace.

## Architecture summary

FastAPI backend on :8001, CRA operator UI + Vite Opportunity Center
served by nginx-alpine, MongoDB persistence. Docker compose (greenfield
+ shared-infra profiles). `arbictl` = single-file Python CLI for
operations (deploy, preflight, dashboard, snapshot, evidence-pack,
validate-start, upgrade, rollback).

## User personas

- **VPS operator** — runs `scripts/install.sh` on a fresh Ubuntu 24 host
  and expects a clean bring-up without manual pip installs.
- **Windows developer** — clones the repo on Windows for local review;
  `AUX`-collision must not block checkout.
- **Ops on-call** — uses `arbictl` for deploy / rollback / snapshot on a
  running validation run.

## What's been implemented (v2.9.1 — 2026-08-04)

- ✅ Windows-safe module rename: `aux.py` → `aux_providers.py`.
- ✅ Single internal import updated in `providers/bootstrap.py`; no other
     references to the old name in code.
- ✅ `.env.example` promotes `REACT_APP_BACKEND_URL` to REQUIRED with a
     compile-time-baking explanation.
- ✅ `scripts/install.sh` pre-flight now gates on
     `REACT_APP_BACKEND_URL` (fails fast before Docker build).
- ✅ `ops/arbictl` (bash wrapper) rewritten: discovers a Python that has
     `httpx` (via `ARBICTL_PYTHON`, `ARBICTL_VENV`, `.venv/`, `venv/`,
     `/app/venv/`, `python3`). Never runs pip. Exits 3 with actionable
     four-path provisioning message when none available.
- ✅ `ops/arbictl.py` ImportError branch mirrors the wrapper guidance.
- ✅ `docs/OPERATIONS_GUIDE.md` — new "httpx runtime dependency" section.
- ✅ `docs/DEPLOYMENT_CHECKLIST.md` — rewritten for v2.9.1 (Windows
     clone note, PEP-668 step, REQUIRED env var, `arbictl deploy`).
- ✅ `docs/RELEASE_NOTES_v2.9.1.md`.
- ✅ Release artifacts in `releases/v2.9.1/`:
     `arbicore-x-v2.9.1.tar.gz`, `arbicore-x-v2.9.1.SHASUMS`,
     `arbicore-x-v2.9.1.MANIFEST.sha256`, `RELEASE_NOTES_v2.9.1.md`.
- ✅ Commit + annotated tag `v2.9.1` pushed to
     `raghugr2013-lgtm/arbicore-x` on GitHub main.

## Deployment gates verified

| Concern | State |
|---|---|
| Windows checkout (`aux.py` collision) | ✅ resolved |
| Windows-reserved filename scan | ✅ none remain |
| Docker frontend build (`REACT_APP_BACKEND_URL` empty) | ✅ hard-fails with actionable message at three layers (.env, install.sh, compose, Dockerfile) |
| `arbictl` on Ubuntu 24 (PEP 668) | ✅ no runtime pip; interpreter-discovery only |
| `arbictl` on legacy hosts (v2.9.0 compat) | ✅ `python3` remains last-resort candidate |
| YAML parse (3 compose files) | ✅ pass |
| Bash syntax (install / verify / upgrade / healthcheck) | ✅ pass |
| Python import of `aux_providers` + `bootstrap` | ✅ pass (rename accepted) |
| SHASUMS self-verify | ✅ pass |
| GitHub commit push | ✅ `9391f85` on main |
| GitHub tag push | ✅ `v2.9.1` |

## Prioritized backlog (out of scope for v2.9.1)

None — v2.9.1 is maintenance-only. Next milestone is the 7-day VPS
validation run against v2.9.1 to gate Stage 6 go/no-go.

## Non-goals for this release

- No new scanners, providers, UI work, execution logic, or APIs.
- No changes to safety defaults, MID schema, or evidence-writer.
- No refactors beyond the three deployment fixes.

---

## v2.10.0 — Phase 2: Canonical Runtime Activation (in-progress)

Goal: transition each user-facing surface from preview/hardcoded data
to the real canonical engines behind it. No UI or engine redesign. Each
slice is a surgical replacement.

### Slice 1 — Opportunity Pipeline (2026-08-05) — ✅ COMPLETE (GO)
Branch: `hotfix/canonical-slice-1` — commits `3d69bd2`, `a3e06a3`.

- ✅ Removed `_V2_OPPS` (8 hardcoded opps + `_hydrate_opps`) from `server.py`.
- ✅ Rewired GET `/opportunities`, `/opportunities/summary`,
     `/opportunities/{id}` to read exclusively from `_CANONICAL_OPP_REPO`.
     Empty DB → empty responses. Always `source: 'canonical'`.
- ✅ Rewired POST `/opportunities/{id}/approve` and `/reject` to canonical
     FSM (`mark_validated → mark_approved` / `mark_rejected`) + persist via
     `_CANONICAL_OPP_REPO.upsert`.
- ✅ Extended timeline to include `opportunity_journal` per-opp tap.
- ✅ Added `_journal_record_operator_event` bridge: seeds a `record_discovery`
     row when a canonically-seeded opp has no prior journal entry so every
     operator decision produces an audit-trail row.
- ✅ Normalized timeline event `kind` (raw, no `journal:` prefix).
- ✅ Approve/reject exceptions now logged instead of silently returning 404.
- ✅ Zero frontend, engine, or storage-schema changes.
- ✅ Testing verified: iter3 (26/27, 1 HIGH resolved) + iter4 (18/18 PASS).
- 📄 Deliverables: `docs/roadmap_v2.10/SLICE1_DELIVERABLES.md`.

Deployment impact: none (additive; empty DB safe; rollback trivial via
`git revert 3d69bd2 a3e06a3`).

### Slice 1.1 — Opportunity endpoints session auth gate (2026-08-05) — ✅ COMPLETE (GO)
Branch: `hotfix/canonical-slice-1.1` — commit `3b092ec`.

- ✅ Added `_require_operator_ctx()` helper delegating to unified
     `_resolve_current_user` (v2.9.3 cookie + bearer paths).
- ✅ Gated all 6 `/api/arbicore/opportunities*` endpoints (list, summary,
     detail, approve, reject, timeline). Anonymous → 401
     `{"detail":"not_authenticated"}`.
- ✅ Preserved 200 response shapes and query params. Frontend unchanged
     (already sends cookies via `withCredentials`).
- ✅ Testing verified: iter5 (55/55 PASS — 37 auth-matrix + 18 regression).
- 📄 Report: `test_reports/iteration_5.json`.

### Slice 2 — Canonical Discovery View (2026-08-05) — ✅ COMPLETE (GO)
Branch: `hotfix/canonical-slice-2` — commits `c1ca7d0`, `eb6c8a3`.
Merged to main as v2.10.1.

- ✅ Removed `_V2_DISCOVERY` (7 hardcoded narrative candidates) and
     `_hydrate_discovery` from `server.py`.
- ✅ Rewrote GET `/arbicore/discovery/candidates` to project the canonical
     opportunity population (`arbicore_opportunities`) into the existing
     UI contract via `_canonical_opp_to_discovery`. Filters
     status/kind/min_score/limit preserved. Empty DB → empty items.
- ✅ Rewrote POST `/arbicore/discovery/candidates/{id}/action` to route
     through the canonical FSM (`mark_validated / mark_approved /
     mark_rejected`), journals as `discovery_watch/promote/dismiss`.
     Illegal transitions return `{ok:false, error:<msg>}`.
- ✅ Replaced the hardcoded `{n_samples:214, ...}` calibration block with
     an honest one computed from live canonical rows (decile promotion
     rates; defaults to 0.0 when n<10).
- ✅ Session-cookie auth-gated (Slice 1.1 pattern).
- ✅ Testing verified: iter6 (33/34, 1 MEDIUM fixed) + iter7 (**79/79 PASS**
     — 42 Slice 2 + 37 Slice 1 regression).
- 📄 Deliverables: `docs/roadmap_v2.10/SLICE2_DELIVERABLES.md`,
     `docs/RELEASE_NOTES_v2.10.1.md`.

Status vocabulary map (canonical FSM → UI):
```
CANDIDATE  ↔ NEW
VALIDATED  ↔ WATCHING
APPROVED   ↔ PROMOTED
REJECTED   ↔ DISMISSED
```

Explicitly out of scope per user directive: narrative-intelligence engine,
external integrations (Twitter/CoinGecko/GitHub), new collections. Discovery
is the pre-approval view of the same funnel Slice 1 activated.

### Slice 2 — Canonical Discovery View (2026-08-05) — ✅ COMPLETE (v2.10.1)
Merged to main. See earlier entry above.

---

## v2.11 — Execution Ready (2026-08-05) — ✅ COMPLETE (FULL GO)

**Branch**: `hotfix/canonical-v2.11` (merged to main).
**Commits**: `57fb80f`, `17a41ec`, `133ffdb`.
**Test evidence**: `test_reports/iteration_8.json` — **145 / 145 PASS**.
**Deliverables**: `docs/roadmap_v2.10/V2.11_DELIVERABLES.md`, `docs/RELEASE_NOTES_v2.11.md`.

### Slice 3 — Market Intelligence canonical activation (P0)

- ✅ 6 intelligence endpoints (`recommendations`, `decisions`, `calibration`,
     `models`, `certification`, `entities`) rewired to canonical sources.
- ✅ Empty stores return empty responses; no fabricated fallbacks.
- ✅ Session-cookie auth-gated.

### Slice 4 — Execution Planning readiness (P0)

- ✅ 20 planner routes now session-cookie auth-gated (`/execution/*`).
- ✅ End-to-end pipeline verified (build → simulate → sign → calldata → broadcast(dry)).
- ✅ Bug fixes: swap-hop validation (no more 500 KeyError); orphan `except` removed.

### Phase C — Backend architectural cleanup (P0)

- ✅ Auth pattern consolidated: all 34 protected endpoints in `server.py`
     use `dependencies=[Depends(_require_operator_dep)]`.
- ✅ Manual `await _require_operator_ctx(...)` calls removed from 14
     Slice 1/1.1/2/3 handlers.
- ✅ Auth helpers moved to top-of-file for decorator import-time binding.

### Missing links before Limited Live (documented, deferred)

1. Calldata encoder for `aave_v3` / `uniswap_v3` flash heads (Wave 7C).
2. Executor smart-contract deployment on `base`.
3. 20-cycle shadow certification threshold (operational).
4. Adaptive-weight / calibration fitting scheduler.
5. Kill-switch operator UI wiring.

See `V2.11_DELIVERABLES.md` §8 for the full assessment.

### Slice 5 — Dashboard Summary (P1 — next)
### Slice 6 — Portfolio activation (P2)
### Slice 7 — Operations activation (P3)

### Slice 4 — Execution Planning / Readiness (P2)
### Slice 5 — Dashboard Summary — replace hardcoded pulse/deck (P2)
### Slice 6 — Portfolio activation (P2)
### Slice 7 — Operations activation (P3)

