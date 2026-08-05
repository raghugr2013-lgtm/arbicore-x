# Slice 2 — Canonical Discovery View
## Verification Report & GO/NO-GO

**Branch**: `hotfix/canonical-slice-2`
**Commits**:
- `c1ca7d0` — activate canonical Discovery view; remove `_V2_DISCOVERY`
- `eb6c8a3` — fix C7: let canonical FSM raise on invalid discovery transitions
**Test reports**: `iter6.json` (33/34, 1 MEDIUM), `iter7.json` (79/79 PASS)

---

## 1. Recommendation: **FULL GO**

All Slice 2 requirements verified. 79/79 tests pass serial (42 Slice 2 + 37 Slice 1 regression). C7 spec deviation from iter6 resolved cleanly with a 6-line guard removal.

---

## 2. Pass / Fail Matrix

| # | Section | Result |
|---|---|---|
| A | Auth (anon 401, cookie 200, bearer 200 dual path) | **PASS** 6/6 |
| B | GET contract (source, shape, filters, stats, calibration, empty, placeholder scrub) | **PASS** 14/14 |
| C | POST action FSM (watch / promote / dismiss / reset / unknown / unknown-id) | **PASS** 7/7 |
| C+ | Invalid FSM transitions (C7 + C7b–C7h) | **PASS** 8/8 |
| D | Journal + Slice 1 regression + auth v2.9.3 | **PASS** 6/6 |
| E | Performance (<100ms budget) | **PASS** (avg ~5–8ms on 10-row store) |
| S1 | Slice 1 regression under Slice 2 code | **PASS** 37/37 |

---

## 3. Files Changed

| File | Δ lines | Purpose |
|---|---|---|
| `app/backend/server.py` | +229 / −63 | Removed `_V2_DISCOVERY` + `_hydrate_discovery`; added `_canonical_opp_to_discovery`, `_canonical_discovery_calibration`, status/action mapping tables; rewrote GET/POST discovery handlers; wired auth gate + journal audit |
| `app/backend/tests/test_canonical_slice2_iter6.py` | +new | 34 cases |
| `app/backend/tests/test_canonical_slice2_iter7.py` | +new | 8 invalid-transition cases |

Zero frontend changes. Zero storage-schema changes. Zero new collections.

---

## 4. Before / After Architecture

### Before Slice 2
```
GET /api/arbicore/discovery/candidates
     │
     └─► _V2_DISCOVERY (7 hardcoded narrative rows: PENDLE, TIA, MOODENG, ...)
         └─► filter + hardcoded calibration {n_samples:214, ...}

POST /discovery/candidates/{id}/action
     │
     └─► mutates _V2_DISCOVERY in memory (transient); returns UI status
```

### After Slice 2
```
GET /api/arbicore/discovery/candidates       (auth-gated)
     │
     ├─► _CANONICAL_OPP_REPO.find({})
     ├─► _canonical_opp_to_discovery() per row
     │      ├─ score = normalized confidence (0–1)
     │      ├─ status = _CANONICAL_STATUS_TO_UI[canonical.status]
     │      ├─ kind = 'venue_pair' if route/venues else 'asset'
     │      ├─ source = f"canonical:{provenance.lower()}"
     │      ├─ why = f"{type} · on {chain} · spread {x}% · confidence {y}"
     │      └─ signals = [type:X, provenance:X, chain:X, route:X]
     ├─► filter (status/kind/min_score/limit)
     ├─► sort by score desc
     └─► return {items, total, stats, calibration, source:'canonical'}
              └─ calibration.n_samples = real Mongo count
                 top_/bottom_decile promotion rates from live data

POST /discovery/candidates/{id}/action       (auth-gated)
     │  verb ∈ {watch, promote, dismiss, reset, <unknown>}
     ├─► _CANONICAL_OPP_REPO.get(id)   (404 if missing)
     ├─► reset / unknown → no_op:true, return current UI status
     ├─► watch    → canonical.mark_validated()
     ├─► promote  → mark_validated?() → mark_approved()
     ├─► dismiss  → mark_rejected("discovery_action:dismiss")
     │       └─ FSM raises InvalidTransitionError on illegal source status
     │          → except branch returns {ok:false, error:<msg>}
     ├─► _CANONICAL_OPP_REPO.upsert(canonical)
     └─► _journal_record_operator_event(canonical, kind=f"discovery_{verb}", ...)
```

FSM ↔ UI status mapping:
```
CANDIDATE  ↔ NEW
VALIDATED  ↔ WATCHING
APPROVED   ↔ PROMOTED
REJECTED   ↔ DISMISSED
```

---

## 5. Deployment Impact

| Vector | Impact |
|---|---|
| API contract | Response fields unchanged (added `source:'canonical'` additively). New `no_op:true` field on reset/unknown-verb responses (additive). New 401 on anonymous callers (Slice 1.1 parity). |
| Frontend | **No changes.** Frontend ignores unknown fields; existing `withCredentials` handles auth. |
| Storage schema | **No changes.** Reuses `arbicore_opportunities` + `arbicore_opportunity_journal`. |
| Migration | None. |
| Rollback | `git revert eb6c8a3 c1ca7d0`. |
| Feature flag | Not used. |
| Performance | Well under budget (~5–8ms vs 100ms target). |
| Observability | Improved. Discovery actions now write `discovery_watch/promote/dismiss` events to the journal. |

---

## 6. Behavioural Deltas (Frontend-visible)

1. **Real candidates**: Discovery no longer shows fake PENDLE/TIA/MOODENG rows; it shows the real early-stage rows from the execution pipeline.
2. **Real calibration**: `n_samples` reports the real canonical row count. When <10 samples, decile rates default to 0.0 (no faked figures).
3. **Real FSM guards**: `watch` on already-terminal opps returns `ok:false` with an error message instead of silently succeeding.
4. **Real audit trail**: Every discovery action writes an event to the journal and surfaces in `/opportunities/{id}/timeline`.
5. **Auth**: Anonymous callers receive `401 {"detail":"not_authenticated"}` (Slice 1.1 parity).

---

## 7. Follow-ups (Non-blocking)

1. Optional: split `server.py` (>5000 lines) into `routes/*.py` per bounded context.
2. Optional: centralise `_require_operator_ctx` as an APIRouter-wide `Depends()`.
3. Optional: `pytest.ini` addopts filter to make iter6 B7 xdist-safe (product code is fine; test-only nit).
4. Narrative Intelligence — out-of-scope for the limited-live roadmap per user directive; will be designed as a separate future capability.
5. Next slice: Slice 3 — Market Intelligence live endpoints (fees, gas, liquidity snapshots).
