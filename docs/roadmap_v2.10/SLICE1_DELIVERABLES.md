# Slice 1 — Canonical Opportunity Pipeline Activation
## Verification Report & GO/NO-GO

**Branch**: `hotfix/canonical-slice-1`
**Commits**:
- `3d69bd2` — activate canonical Opportunity pipeline; remove `_V2_OPPS`
- `a3e06a3` — seed journal row on operator decision; normalize timeline kind
**Test reports**: `/app/test_reports/iteration_3.json` (first pass), `/app/test_reports/iteration_4.json` (post-fix, GO)

---

## 1. Recommendation: **GO**

All Slice 1 blocking findings from the first testing pass (iter3) are resolved and re-verified (iter4). 18/18 pytest cases pass. No critical issues remain. One documented spec drift on auth-gating is intentionally deferred to a follow-up slice.

---

## 2. Pass / Fail Matrix

| # | Section | Result | Notes |
|---|---|---|---|
| 1 | Canonical Opportunity API | **PASS** | list / summary / detail / approve / reject / timeline all return `source='canonical'`; filters (family/chain/verdict/min_confidence), limit, sort_by all verified; unknown id returns 404 `{error:'not_found', id:<id>}` |
| 2 | Placeholder Elimination | **PASS** | `_V2_OPPS` removed from `server.py`; no `source: preview/merged/hybrid` markers; empty DB → `{items:[], total:0}` verified by code path (server.py:522–568) |
| 3 | Canonical Repo & Audit-Trail Integrity | **PASS** (iter3 HIGH #1 FIXED) | Approve on a fresh canonically-seeded opp seeds journal with `['discovered','operator_approved']`, `execution_status='approved'`; reject seeds `['discovered','operator_rejected']`; second mutation appends to existing row without duplication |
| 4 | UI Compatibility (contract-shape) | **PASS** | Response shape unchanged from prior canonical branch; `canonical: true` on list items; frontend consumes empty arrays via existing `EMPTY_STATE_WIDGET_SWEEP.md` handling |
| 5 | Auth Regression (v2.9.3) | **PASS** | `/api/auth/setup`, `/login`, `/logout`, `/me` all work; `access_token` + `refresh_token` HttpOnly, SameSite=Lax cookies set correctly. See §7 for the deferred spec drift. |
| 6 | Performance | **PASS** | `/opportunities` avg 3.06ms / p95 4.44ms; `/opportunities/summary` avg 3.02ms / p95 3.09ms — no material regression vs iter3 baseline (2.2ms / 1.7ms), well within tolerance |

---

## 3. Files Changed

Scope of Slice 1 relative to pre-branch (`5f11ab1`):

| File | Δ lines | Purpose |
|---|---|---|
| `app/backend/server.py` | +268 / −138 | Removed `_V2_OPPS`; wired `/opportunities*` endpoints to `_CANONICAL_OPP_REPO` + `_OPPORTUNITY_JOURNAL`; added `_journal_record_operator_event` audit-trail bridge; normalized timeline `kind`; improved exception logging in approve/reject |
| `app/backend/tests/test_canonical_slice1_iter3.py` | +358 (new) | 27 pytest cases (canonical API, placeholder elimination, repo integrity, UI compatibility, auth regression, performance) |
| `app/backend/tests/test_canonical_slice1_iter4.py` | +324 (new) | 18 pytest cases focused on the audit-trail bridge + regressions from iter3 |

Zero frontend files were touched. Zero engine files were touched. Zero storage schema changes.

---

## 4. Before / After Architecture

### Before (pre-Slice 1)
```
GET /api/arbicore/opportunities
     │
     ├─► _V2_OPPS (8 hard-coded rows) ── merged with ──► _CANONICAL_OPP_REPO.find({})
     │                                                       │
     └─► _hydrate_opps() ── returns {items, total, source:'preview' or 'hybrid'}

POST /approve, /reject
     │
     ├─► mutates _V2_OPPS in memory (transient)
     └─► optionally _CANONICAL_OPP_REPO.upsert (best-effort)

GET  /opportunities/summary  → hardcoded {total:14, by_family:{...}}
GET  /timeline               → 10 cross-collection taps, no journal per-opp tap
```

### After (Slice 1)
```
GET /api/arbicore/opportunities
     │
     └─► _CANONICAL_OPP_REPO.find({})    ── returns {items, total, source:'canonical'}
         └─► (empty DB → items:[], total:0 — no fallback branch)

POST /approve
     │
     ├─► _CANONICAL_OPP_REPO.get(id)     ── 404 if missing
     ├─► canonical.mark_validated() → mark_approved()   (FSM)
     ├─► _CANONICAL_OPP_REPO.upsert(canonical)
     └─► _journal_record_operator_event(canonical, kind='operator_approved', …)
             │  (bridge)
             ├─► _OPPORTUNITY_JOURNAL.record_event(id, …)
             │      └─► returns None if row missing
             ├─► if None: _OPPORTUNITY_JOURNAL.record_discovery(canonical,
             │                                                    mode='OPERATOR',
             │                                                    scanner_family='operator_console')
             └─► _OPPORTUNITY_JOURNAL.record_event(id, …)   (re-attempt)

POST /reject     — same shape, kind='operator_rejected', persists `reason`.

GET /opportunities/summary
     │
     └─► aggregation over _CANONICAL_OPP_REPO.find({}) grouped by
         opportunity_type / chain / status  (empty DB → {} everywhere)

GET /timeline
     │
     ├─► canonical opportunity state (arbicore_opportunities)
     ├─► opportunity_journal per-opp tap  ── raw kind (no 'journal:' prefix)
     └─► 9 additional cross-collection taps (unchanged)
```

Key invariants introduced by Slice 1:
- Every `/opportunities*` response reports `source: 'canonical'`.
- Empty Mongo → empty responses. No demo/placeholder branch remains.
- Every operator decision produces an audit-trail row (even on canonically-seeded opps that never passed through discovery).
- The journal's contract (`record_event` never creates rows) is unchanged; the bridge lives in `server.py` where the canonical-first flow originates.

---

## 5. Test Evidence

### iter3 — first pass (26/27; 1 real HIGH bug + 1 spec drift)
- Report: `/app/test_reports/iteration_3.json`
- Pytest: `/app/app/backend/tests/test_canonical_slice1_iter3.py`
- HIGH #1 (audit-trail gap) — journal event silently dropped for opps without discovery row.
- HIGH #2 (auth-gate) — reclassified as spec drift by user (see §7).
- minor #1 — timeline event `kind` prefixed with `journal:`.

### iter4 — retest (18/18; GO)
- Report: `/app/test_reports/iteration_4.json`
- Pytest: `/app/app/backend/tests/test_canonical_slice1_iter4.py`
- Audit-trail bridge verified end-to-end (A1..A4): fresh opp → approve → journal row seeded with `['discovered','operator_approved']`; `execution_status='approved'`; timeline emits raw kinds.
- Approve/reject on already-journaled opps still append without duplication.
- Auth regression green.
- Performance within tolerance.

### Manual verification (main-agent smoke, pre-testing-agent)
```
PRE journal row:  None
APPROVE resp:     200 {ok:True, id:'slice1-fix-verify-001', status:'approved', canonical:True}
POST journal row exists:  True
events kinds:     ['discovered', 'operator_approved']
execution_status: approved
TIMELINE journal kinds:  ['operator_approved', 'discovered']    ← no 'journal:' prefix
```

---

## 6. Deployment Impact Assessment

| Vector | Impact |
|---|---|
| API contract | **No breaking changes.** Response shapes preserved; new `source: 'canonical'` field is additive (was already present on canonical rows). |
| Frontend | **Zero changes required.** Empty-state handling already in place (see `docs/roadmap_v2.10/EMPTY_STATE_WIDGET_SWEEP.md`). |
| Storage schema | **No changes.** Uses existing `arbicore_opportunities` and `arbicore_opportunity_journal` collections. |
| Migration | **None.** No data backfill required. Empty DB behaves correctly. |
| Rollback | **Trivial.** `git revert 3d69bd2 a3e06a3` restores the previous merged path. No stateful side-effects to undo. |
| Feature flag | Not used. Change is behaviour-only within canonical-only code path. |
| Auth surface | **Unchanged.** See §7. |
| Performance | **No regression.** Latency deltas are within ambient variance on a 2-row dataset. |
| Observability | **Improved.** Journal now captures operator decisions on all canonical opps; exceptions in approve/reject are logged instead of swallowed. |

---

## 7. Spec Drift — CLOSED by Slice 1.1

**Update (Slice 1.1, commit `3b092ec`)**: All `/api/arbicore/opportunities*` endpoints are now session-cookie auth-gated (Option 1 from the original recommendation). Anonymous callers receive `401 {"detail":"not_authenticated"}`. Both cookie (access_token, HttpOnly, SameSite=Lax) and bearer (`Authorization: Bearer <access_token>`) paths accepted via the unified `_resolve_current_user` resolver.

Testing: iter5 report `/app/test_reports/iteration_5.json` — **55/55 PASS** (37 auth-matrix cases + 18 regression). GO for merge to main.

Gated endpoints:
- `GET /arbicore/opportunities`
- `GET /arbicore/opportunities/summary`
- `GET /arbicore/opportunities/{id}`
- `POST /arbicore/opportunities/{id}/approve`
- `POST /arbicore/opportunities/{id}/reject`
- `GET /arbicore/opportunities/{id}/timeline`

Frontend: no change (`withCredentials` already in use).

---

## 8. Outstanding / Recommended Follow-ups (Non-blocking)

1. ~~Auth-gate decision (§7).~~ ✅ Closed by Slice 1.1.
2. `server.py` is 5053 lines — recommend splitting into `routes/*.py` per bounded context in a dedicated cleanup slice.
3. Optional: make `OpportunityJournal.record_event` upsert-on-missing so the bridge helper becomes unnecessary. Currently the bridge is one extra round-trip on first mutation of a canonically-seeded opp — negligible in practice.
4. Optional: convert the six per-handler `_require_operator_ctx` calls to a shared `Depends()` on an `APIRouter` (so future opportunity endpoints inherit the gate).
5. Next slice: Slice 2 (Scanner / Discovery activation) — replace preview `_V2_DISCOVERY` in `server.py` with the live `LiveMarketScanner` / `ContinuousDiscovery` engines.
