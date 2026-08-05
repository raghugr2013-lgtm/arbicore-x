# ArbiCore X — v2.10.1 Release Notes

**Release**: v2.10.1 (Canonical Runtime Activation — Slice 2)
**Date**: 2026-08-05
**Branch merged**: `hotfix/canonical-slice-2`

---

## Highlights

The **Discovery page** is now backed by the real canonical Opportunity Pipeline. `_V2_DISCOVERY` (7 hardcoded narrative candidates) has been deleted from `server.py`; the Discovery view is now a projection of the same `arbicore_opportunities` collection activated in Slice 1, presenting the early-lifecycle rows.

Per user directive, no narrative-intelligence engine, no external integrations (Twitter/CoinGecko/GitHub), and no new collections were introduced. Discovery is the pre-approval view of the execution funnel.

---

## What's New

### Slice 2 — Canonical Discovery View
- `GET /api/arbicore/discovery/candidates` — projects `arbicore_opportunities` into the existing UI contract (`id / asset / kind / chain / source / score / status / why / signals / seen_at`). `source: 'canonical'`. Filters `status / kind / min_score / limit` all honored. Empty DB → empty items.
- `POST /api/arbicore/discovery/candidates/{id}/action?action={watch|promote|dismiss|reset}`:
  - `watch` → `canonical.mark_validated` (UI: NEW → WATCHING).
  - `promote` → `mark_validated → mark_approved` (UI: → PROMOTED).
  - `dismiss` → `canonical.mark_rejected("discovery_action:dismiss")` (UI: → DISMISSED).
  - `reset` → no-op (canonical FSM has no reset; response reports current UI status with `no_op: true`).
  - Unknown verb → no-op.
  - Illegal FSM transition (e.g. `watch` on a REJECTED opp) → 200 `{ok:false, error:<msg>}`.
- Journal entries `discovery_watch / discovery_promote / discovery_dismiss` written to `arbicore_opportunity_journal` on every mutation and surface in `/opportunities/{id}/timeline`.
- Real calibration block: `n_samples` reflects the real canonical row count; decile promotion rates computed from live data. When <10 samples, rates default to 0.0 (no faked figures).
- All 2 endpoints are session-cookie auth-gated via `_require_operator_ctx` (Slice 1.1 pattern).

---

## Removed
- `_V2_DISCOVERY` — 7 hardcoded rows (PENDLE, TIA, MOODENG, berachain, ORDI, sushiswap:WETH-USDT, hyperliquid:BTC-PERP).
- `_hydrate_discovery` — timestamp hydration helper.
- Hardcoded calibration `{n_samples: 214, promotion_rate_top_decile: 0.62, ...}`.

---

## Contract Changes

| Endpoint | Change |
|---|---|
| `GET /arbicore/discovery/candidates` | Same shape; `source: 'canonical'` added additively. `n_samples` now real. `401` for anonymous callers. |
| `POST /arbicore/discovery/candidates/{id}/action` | Same shape; `no_op: true` added on `reset` / unknown verbs. `ok: false` on illegal FSM transitions. `401` for anon. `404 {error, id}` for unknown id. |

---

## Test Evidence

| Iteration | Scope | Result |
|---|---|---|
| iter6 | Slice 2 first pass | 33/34 (1 MEDIUM: C7 dead-code guard, fixed in eb6c8a3) |
| iter7 | Slice 2 retest + full Slice 1/2 regression | **79/79 PASS** |

Reports: `test_reports/iteration_6.json`, `iteration_7.json`.
Pytest suites: `app/backend/tests/test_canonical_slice2_iter6.py`, `test_canonical_slice2_iter7.py`.

---

## Deployment Impact

- No frontend changes.
- No storage-schema changes.
- No new collections.
- No migrations.
- Rollback: `git revert eb6c8a3 c1ca7d0`.

---

## Next

**Slice 3 — Market Intelligence** live endpoints (fees, gas, liquidity snapshots). See `docs/roadmap_v2.10/CANONICAL_ACTIVATION_ROADMAP.md`.

**Narrative Intelligence** is intentionally out-of-scope for the limited-live roadmap and will be designed as a separate future capability.
