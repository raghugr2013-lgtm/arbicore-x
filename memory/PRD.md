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

Documented spec drift (deferred): `/api/arbicore/opportunities*` remain
public (never were auth-gated). User to decide whether to add
`Depends(get_current_user)` in a follow-up.

### Slice 2 — Scanner / Discovery activation (P1 — next)
Replace `_V2_DISCOVERY` (7 preview candidates in `server.py:818`) with
live `LiveMarketScanner` / `ContinuousDiscovery` engine output.

### Slice 3 — Market Intelligence live endpoints (P1)
Live fees, gas oracle, liquidity snapshots.

### Slice 4 — Execution Planning / Readiness (P2)
### Slice 5 — Dashboard Summary — replace hardcoded pulse/deck (P2)
### Slice 6 — Portfolio activation (P2)
### Slice 7 — Operations activation (P3)

