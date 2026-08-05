# ArbiCore X — v2.11 Release Notes

**Release**: v2.11 — Execution Ready
**Date**: 2026-08-05
**Branch merged**: `hotfix/canonical-v2.11`
**Test evidence**: `test_reports/iteration_8.json` — **145 / 145 PASS**

---

## Highlights

v2.11 finishes the backend canonicalisation of the ArbiCore Execution Pipeline. The Market Intelligence panel and the Execution Planner surface are now fully backed by real canonical engines and Mongo stores. Every protected endpoint uses one uniform session-cookie auth pattern via a single `Depends(_require_operator_dep)` gate. No placeholder data remains in the operator UI paths.

This is our next VPS-deployment target.

---

## What's New

### Slice 3 — Market Intelligence canonical activation (6 endpoints)

- `GET /api/arbicore/intelligence/recommendations` — top_routes / top_chains / top_entities derived from `arbicore_opportunities` + `get_entity_scorer`. Empty stores → empty lists.
- `GET /api/arbicore/intelligence/decisions` — derived from `arbicore_opportunity_journal` events joined with `arbicore_opportunities`. Verdict mapping (operator/discovery events → GO/HARD_NO/SOFT_NO).
- `GET /api/arbicore/intelligence/calibration` — reads `_CALIBRATION_REPO.get_active('confidence')`. Empty → `{available:false, buckets:[], n_samples:0}`.
- `GET /api/arbicore/intelligence/models` — reads `_CALIBRATION_REPO.list_recent('confidence')` + active adaptive-weights row.
- `GET /api/arbicore/intelligence/certification` — wraps `services.execution.certification_review.latest_review()`.
- `GET /api/arbicore/intelligence/entities` — wraps `get_entity_repo()` + `get_entity_scorer().top()`. Vocabulary from the `EntityType` enum.

### Slice 4 — Execution Planning readiness (20 planner routes)

- Session-cookie auth-gated all 20 planner routes: `/adapters`, `/plans/build`, `/plans`, `/plans/{id}`, `/simulation/status`, `/gas`, `/mev/routers`, `/plans/{id}/simulate`, `/plans/{id}/sign`, `/plans/{id}/calldata`, `/plans/{id}/broadcast`, `/capital-policy`, `/capital-policy/{strategy}` (GET+PATCH), `/capital-policy/{strategy}/evaluate`, `/kill-switch`, `/kill-switch/engage`, `/kill-switch/disengage`, `/kill-switch/audit`, `/certification/stages`, `/certification/run`.
- End-to-end pipeline verified: build → simulate → sign → calldata → broadcast(dry) all pass on a real Balancer flash-loan payload.
- **Bug fix**: `POST /plans/build` with an incomplete `swap_hops` payload no longer 500s with `KeyError`. It now returns a caller-visible error message listing the missing required field(s).
- **Bug fix**: removed a dead orphan `except Exception` block after the broadcast handler's early return.

### Phase C — Auth pattern consolidation

- Migrated all 14 Slice 1/1.1/2/3 endpoints from the per-handler `await _require_operator_ctx(request, authorization)` pattern to router-level `dependencies=[Depends(_require_operator_dep)]`. All 34 protected endpoints in `server.py` now share exactly one auth pattern.
- Moved `_require_operator_ctx` + `_require_operator_dep` to the top of `server.py` so decorators throughout the file bind their `Depends()` at import time.

---

## Contract Changes

| Endpoint | Change |
|---|---|
| `/intelligence/recommendations` | Empty response when canonical stores are empty; `source: 'canonical'` added. |
| `/intelligence/decisions` | Now derives from journal; `source: 'canonical'` added. Filters preserved. |
| `/intelligence/calibration` | New `available` boolean; empty state returns `available:false, buckets:[], n_samples:0`. |
| `/intelligence/models` | Now lists real models; empty when nothing has been fitted. |
| `/intelligence/certification` | Empty state `available:false` when no shadow campaign has completed. |
| `/intelligence/entities` | Empty state when the scorer / repo has no data. |
| `/execution/*` (20 routes) | Now require an authenticated session; anonymous → `401 {"detail":"not_authenticated"}`. |
| `/plans/build` | Incomplete swap hops now return a `ValueError` bubble as `{error: "..."}`, no more 500s. |

Frontend requires no changes.

---

## Test Evidence

| Iteration | Scope | Result |
|---|---|---|
| iter8 | v2.11 full regression (Slice 3 + Slice 4 + Phase C + Slice 1/1.1/2 baseline + auth v2.9.3 + perf) | **145 / 145 PASS** |

Report: `test_reports/iteration_8.json`.
Pytest: `app/backend/tests/test_v211_full_regression.py` (66 v2.11 cases) + preserved iter5/6/7 baseline files (79 cases).

---

## Deployment Impact

- No frontend changes.
- No storage-schema changes, no new collections, no migrations.
- No config / env-var changes.
- Rollback: `git revert 133ffdb 17a41ec 57fb80f`.
- No stateful side effects; ephemeral planner artifacts are UUID-keyed.

---

## Execution Readiness

v2.11 completes the canonical backend pipeline through Execution Planning. Paper Validation can begin immediately after VPS deployment by running shadow cycles. Full Limited-Live activation requires the executor smart contract deployed on the production chain(s) — see `docs/roadmap_v2.10/V2.11_DELIVERABLES.md` §8 for the concrete blocker list.

---

## Next

- v2.11 → VPS deployment → begin shadow cycles → work toward the 20-cycle certification threshold.
- v2.12 (planned): calldata encoder for aave_v3 & uniswap_v3 flash heads; executor contract deployment infra task; adaptive-weight / calibration fitting scheduler.
