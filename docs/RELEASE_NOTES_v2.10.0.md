# ArbiCore X — v2.10.0 Release Notes

**Release**: v2.10.0 (Canonical Runtime Activation — Slice 1 + 1.1)
**Date**: 2026-08-05
**Branches merged**: `hotfix/canonical-slice-1`, `hotfix/canonical-slice-1.1`

---

## Highlights

Phase 2 of the runtime activation program: the **Opportunity Pipeline** is now backed by the real canonical engine end-to-end. All hardcoded/preview opportunity data has been removed from the `/api/arbicore/opportunities*` endpoints, replaced with reads/writes against `arbicore_opportunities` (Mongo) and `arbicore_opportunity_journal` (append-only audit).

All six opportunity endpoints are now session-cookie auth-gated. Anonymous callers receive `401 {"detail":"not_authenticated"}`.

---

## What's New

### Slice 1 — Canonical Opportunity Pipeline
- `GET /api/arbicore/opportunities` — reads exclusively from `_CANONICAL_OPP_REPO`. Empty DB → empty items. `source: 'canonical'` on every response.
- `GET /api/arbicore/opportunities/summary` — aggregation over canonical rows by `opportunity_type` / `chain` / `status`. Empty DB → `{total: 0, by_family: {}, by_chain: {}, by_status: {}}`.
- `GET /api/arbicore/opportunities/{id}` — canonical detail; 404 `{error: 'not_found', id}` for unknown ids.
- `POST /api/arbicore/opportunities/{id}/approve` — routes through canonical FSM (`mark_validated → mark_approved`), persists via `_CANONICAL_OPP_REPO.upsert`, records an `operator_approved` event on the journal.
- `POST /api/arbicore/opportunities/{id}/reject` — `canonical.mark_rejected(reason)`, records `operator_rejected` on the journal.
- `GET /api/arbicore/opportunities/{id}/timeline` — extended with a per-opp journal tap so operator decisions appear in the audit trail alongside the existing 10 cross-collection taps. Event `kind` is raw (no `journal:` prefix).
- **New audit-trail bridge** — `_journal_record_operator_event` seeds a `record_discovery` row when a canonically-seeded opp has no prior journal entry, guaranteeing every operator action produces an audit row.

### Slice 1.1 — Session-cookie auth gate
- All 6 opportunity endpoints now require an authenticated operator session.
- Cookie path (`access_token`, HttpOnly, SameSite=Lax) and bearer path (`Authorization: Bearer <access_token>`) both accepted via the unified `_resolve_current_user` resolver.
- Frontend uses `withCredentials` — no UI change required.

---

## Removed
- `_V2_OPPS` — the 8-row hardcoded preview universe.
- `_hydrate_opps` — the helper that stamped `seen_at` onto preview rows.
- Canonical-first / preview-fallback merge branches from the `/opportunities` list and detail handlers.
- Hardcoded `{total: 14, ...}` summary.

---

## Contract Changes

| Endpoint | Change |
|---|---|
| `GET /arbicore/opportunities*` | New: `401 {"detail":"not_authenticated"}` for anonymous callers. 200 responses unchanged. |
| `GET /arbicore/opportunities` | `source` field now always `'canonical'` (never `'preview'` / `'merged'` / `'hybrid'`). |
| `GET /arbicore/opportunities/summary` | Aggregation is now live; empty DB → empty maps. |
| `GET /arbicore/opportunities/{id}/timeline` | Event `kind` values for journal-derived events are the raw kind (`operator_approved`, `discovered`), not `journal:*`. |
| Everything else | Unchanged. |

---

## Test Evidence

| Iteration | Scope | Result |
|---|---|---|
| iter3 | Slice 1 first pass | 26/27 (1 HIGH: audit-trail gap, fixed in a3e06a3) |
| iter4 | Slice 1 retest | 18/18 PASS |
| iter5 | Slice 1.1 auth + regression | 55/55 PASS (37 auth + 18 regression) |

Reports: `/app/test_reports/iteration_3.json`, `iteration_4.json`, `iteration_5.json`.
Pytest suites:
- `app/backend/tests/test_canonical_slice1_iter3.py`
- `app/backend/tests/test_canonical_slice1_iter4.py`
- `app/backend/tests/test_canonical_slice1_iter5.py`

---

## Deployment Impact

| Vector | Impact |
|---|---|
| API contract | Additive 401 on `/opportunities*` for anonymous callers. All 200 shapes preserved. |
| Frontend | **No changes.** `withCredentials` + SameSite=Lax cookies already in use. |
| Storage schema | **No changes.** Existing `arbicore_opportunities` + `arbicore_opportunity_journal` collections. |
| Migration | None. Empty-DB behaviour is correct. |
| Feature flag | Not used. |
| Rollback | `git revert 3b092ec a3e06a3 3d69bd2`. No stateful side effects. |
| Performance | No material regression (list ~2.8ms avg, summary ~3ms avg). |
| Observability | Improved: journal now audits operator decisions; exceptions in approve/reject are logged instead of swallowed. |

---

## Upgrade Notes

1. No env-var changes.
2. No data migration.
3. If any external automation still calls `/api/arbicore/opportunities*` unauthenticated, it must now log in first (POST `/api/auth/login` with admin creds; the returned `access_token` cookie can be reused, or its JWT sent as `Authorization: Bearer <token>`).
4. Frontend clients: no change (existing cookie-based session works).

---

## Next

Slice 2 — Scanner / Discovery activation. See `docs/roadmap_v2.10/CANONICAL_ACTIVATION_ROADMAP.md`.
