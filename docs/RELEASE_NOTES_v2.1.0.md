# ArbiCore X — v2.1.0 Canonical Release Notes

**Release date:** 2026-08-03
**Codename:** Intelligence Activation
**Predecessor:** v2.0.5

This is the single production release that consolidates every change
since v2.0.5. It bundles four independently-approved milestones:

1. **v2.0.6** — Auth seed canonicalization (truthful, idempotent, self-verifying).
2. **v2.0.7** — VPS `invalid_credentials` regression fix (tolerant `active` lookup) + admin auth diagnostics.
3. **Sprint 1B-α** — Six intelligence engines wired through `MidEvidenceBridge`.
4. **Sprint 1B-β** — Two shadow scanners registered DORMANT + operator control + observability.
5. **Sprint 1B-γ** — End-to-end pipeline validation + this consolidated release.

Every change is backward-compatible. The regression suite grew from
**1469** (v2.0.5) to **1494** (v2.1.0) with zero failures.

---

## Deployment target

Existing VPS deploys running v2.0.5 (or v2.0.6-if-tagged internally).
This is a **single** in-place upgrade; there is no data migration and
no schema change.  Runtime configuration (`.env`) is preserved.

The migration is:

  * pull v2.1.0 code,
  * `docker compose build backend` (the new backend image includes the
    intelligence + scanner activation),
  * `docker compose up -d` (Mongo volume untouched),
  * confirm health via `/api/arbicore/observability`.

See `docs/DEPLOYMENT_CHECKLIST_v2.1.0.md` for the full procedure.

---

## What changed (by subsystem)

### Authentication (v2.0.6 → v2.0.7)

| Area                                      | Before                                      | After                                                          |
|-------------------------------------------|---------------------------------------------|----------------------------------------------------------------|
| Seed routine                              | Falsely logged "seeded 2 default users"     | Truthful (inserted/existed/verified), idempotent, self-verifying |
| `_auth_seed_startup`                      | Discarded return value                      | Logs the summary; ERROR if verification fails                  |
| `find_user` filter                        | `{"username": u, "active": True}`           | `{"username": u, "active": {"$ne": False}}` (tolerant)         |
| Seed post-verification query              | `{"active": True}`                          | `{"active": {"$ne": False}}` — matches `find_user`             |
| Diagnostics                               | none                                        | `GET /api/auth/diagnostics` (admin-only)                       |

**Root cause of VPS `invalid_credentials`** (v2.0.7): a password-reset
script wrote fresh `password_hash` without preserving the `active` field;
the old `find_user` filter silently rejected those docs. The tolerant
lookup fixes this while still denying explicitly deactivated accounts.

### Intelligence engines (Sprint 1B-α)

Six engines wired through **`MidEvidenceBridge`**:

| Engine ID        | Class                          | Primary MID domain    | Mirror event type                          |
|------------------|--------------------------------|-----------------------|--------------------------------------------|
| `confidence`     | `SignalConfidenceEngine`       | `mid_confidence`      | `intel.confidence.score_written`           |
| `roi`            | `ROIProbabilityEngine`         | `mid_opportunities`   | `intel.roi.probability`                    |
| `route_ranking`  | `ScoringEngine`                | `mid_routes`          | `intel.route_ranking.scored`               |
| `economics`      | `CapitalSizer`                 | `mid_decisions`       | `intel.economics.capital_sizing`           |
| `entity_scoring` | `EntityScorer`                 | `mid_opportunities`   | `intel.entity_scoring.outcome_recorded`    |
| `regime`         | `HeuristicRegimeClassifier`    | `mid_providers`       | `intel.regime.classified`                  |

Endpoints: `GET /api/arbicore/intelligence/status`, `GET /api/arbicore/intelligence/{engine_id}/snapshot`.

### Scanners (Sprint 1B-β)

Two shadow scanners wired via `ShadowScannerAdapter` (real classes
remain dormant to honour Sprint 1B's "no live network I/O" invariant):

| Scanner ID              | Adapter                           | Boot state | Auth        |
|-------------------------|-----------------------------------|------------|-------------|
| `dex_arbitrage`         | `ShadowScannerAdapter` (Wave 1B-β) | DORMANT    | operator/admin |
| `flash_loan_arbitrage`  | `ShadowScannerAdapter` (Wave 1B-β) | DORMANT    | operator/admin |

Endpoints:
* `GET  /api/arbicore/scanners/status`
* `POST /api/arbicore/scanners/{id}/start`
* `POST /api/arbicore/scanners/{id}/stop`
* `GET  /api/arbicore/observability` (one-shot health for MID + intel + scanners + auth)

Every emission is a validated MID row (opportunity_event + route_observation).

### Runtime alignment (mechanical)

The running `/app/backend/` tree previously omitted several modules
that live in the canonical repo (they had never been imported before
Sprint 1B).  Wave 1B-α + β brought in the missing files:

* full `arbicore/intelligence/` and `arbicore/intel/` packages
* `arbicore/data/{metrics_repo, outcome_repo, regime_snapshot_repo,
   scanner_config_repo, state_observer, venue_capability_repo,
   wallet_profile_repo, _inmemory, discovery_source_metrics_repo}.py`
* `arbicore/data/mongo/{arbicore_collections, metrics_repo_mongo,
   outcome_repo_mongo, regime_snapshot_repo_mongo,
   wallet_profile_repo_mongo}.py`
* `arbicore/learning/concrete/regime_classifier.py`
* minimal `services/db.py` shim (re-exports `db` and `client` — the
   only legacy module the mongo repos still reach through)

None of the newly-copied modules are activated by default; they only
resolve transitive imports.

---

## Regression results

**Full suite: 1494 passed, 76 skipped, 0 failures, 6 warnings**

Suite growth relative to v2.0.5 baseline:

| Milestone   | Passing | Skipped | New tests               |
|-------------|---------|---------|-------------------------|
| v2.0.5      | 1469    | 76      | —                       |
| v2.0.6      | 1469    | 76      | + existing coverage     |
| v2.0.7      | 1478    | 76      | +9 (Wave 1B-α)          |
| 1B-β        | 1487    | 76      | +9 (Wave 1B-β)          |
| **1B-γ / v2.1.0** | **1494** | 76 | +7 (Wave 1B-γ)          |

New test files:

* `tests/test_wave1b_alpha.py` (9 tests) — engine construction, bridge writes, registry snapshots.
* `tests/test_wave1b_beta.py` (9 tests) — scanner lifecycle, bridge attribution, auth v2.0.7 unit coverage.
* `tests/test_wave1b_gamma.py` (7 tests) — end-to-end pipeline validation, cross-wave composition, observability payload.

---

## API surface changes (v2.0.5 → v2.1.0)

**Added** (10 endpoints):

* `GET  /api/auth/diagnostics`                              (admin)
* `GET  /api/arbicore/intelligence/status`
* `GET  /api/arbicore/intelligence/{engine_id}/snapshot`
* `GET  /api/arbicore/scanners/status`
* `POST /api/arbicore/scanners/{scanner_id}/start`          (operator/admin)
* `POST /api/arbicore/scanners/{scanner_id}/stop`           (operator/admin)
* `GET  /api/arbicore/observability`

**Modified**: none.

**Removed**: none.

---

## Sprint 1B constraints honoured

* No live blockchain RPC.
* No live DEX or exchange calls.
* No live quote providers.
* No autonomous execution.
* Scanners boot DORMANT, operator-controlled only.
* Every scanner emission is validated MID evidence.
* Intelligence engines consume scanner outputs strictly via MID.

---

## Migration risk

**Low.** No schema change. No data migration. Backward-compatible
endpoints. Runtime configuration preserved. Roll-forward path is a
single `docker compose build backend && up -d`. Rollback is a single
`git checkout v2.0.5` and rebuild.

---

## Files added in v2.1.0

* `arbicore/intelligence/wave1b/{__init__, bridge, registry,
   activation, inmemory_repos}.py`
* `arbicore/scanners/wave1b/{__init__, bridge, registry, adapters,
   activation}.py`
* `tests/test_wave1b_alpha.py`
* `tests/test_wave1b_beta.py`
* `tests/test_wave1b_gamma.py`
* `docs/RELEASE_NOTES_v2.0.6.md`
* `docs/RELEASE_NOTES_v2.1.0-alpha.md`
* `docs/RELEASE_NOTES_v2.1.0-beta.md`
* `docs/RELEASE_NOTES_v2.1.0.md` (this file)
* `docs/DEPLOYMENT_CHECKLIST_v2.1.0.md`
* `services/__init__.py`, `services/db.py`  (running instance shim)

## Files modified in v2.1.0

* `app/backend/arbicore/auth/__init__.py` — v2.0.6 (seed) + v2.0.7 (find_user)
* `app/backend/server.py` — Wave 1B-α + 1B-β wiring, endpoints, auth diagnostics
* `VERSION` — `2.0.5` → `2.1.0`
