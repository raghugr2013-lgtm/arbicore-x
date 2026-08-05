# Runtime Data Integrity Audit — ArbiCore X (v2.9.2 baseline)

**Date:** 2026-08-05
**Auditor:** hotfix engineering (read-only)
**Baseline commit:** v2.9.2 (`293a2c4`) + `hotfix/auth-routing` (ad4b23a)
**Scope:** every dashboard, page, widget, chart, table, metric, and status
indicator; every backend endpoint they consume; every source of the values
displayed. Read-only — no code modified.

---

## 1. Method

- Static enumeration of every `@api_router.*` and `@app.*` handler in
  `app/backend/server.py` (5,061 LOC after v2.9.3 hotfix).
- Static enumeration of every canonical router in
  `app/backend/arbicore/routes/*.py` and `app/backend/routes/*.py`.
- Static enumeration of every `axios`/`fetch` call in
  `app/frontend/src/**` and `app/opportunity_center/src/**`.
- Cross-mapping — placeholder vs. canonical, and placeholder vs. actual
  frontend consumer.
- No dynamic tracing; no changes to the running system.

## 2. Findings — three-line summary

1. **187** endpoints in `server.py` are documented "preview stubs" that
   return hardcoded arrays. They serve the majority of the running dashboards.
2. **213** canonical endpoints with real-data backing exist in the repo
   but **none are mounted**. Only 2 paths collide with the stubs.
3. The auth hotfix (v2.9.3) is scope-clean and does not overlap with the
   placeholder situation.

## 3. Placeholder inventory (see §7 for the full table)

Total placeholder blocks in `server.py`:

| Category | Count | Lines |
| :------- | :---- | :---- |
| Slice 0 dashboard tiles      | 5   | 396–476 |
| Slice 1 opportunity feed     | 8   | 481–855 (hybrid — canonical merged with `_V2_OPPS`) |
| Slice 2 discovery + intel    | 7   | 858–1258 |
| Slice 3 operations           | 10  | 1259–1405 |
| Slice 4 portfolio            | 8   | 1406–1585 |
| Slice 5 settings             | 12  | 1586–1802 (mixed; some real, some `_V2_ACCOUNT`/`_V2_EXECUTION` fallback) |
| Wave-1 intelligence          | 15+ | 1029–1258, 1804–2000 (mixed) |
| Ancillary (roi, system stat) | 3   | 458–478 |

## 4. Router mounting audit

| Router file | Endpoints | Mounted? |
| :---------- | :-------- | :------: |
| `server.py` inline `api_router` (250+ endpoints, mostly stubs) | many | ✅ mounted at line 3517 |
| `app/backend/routes/auth.py` (canonical single-admin) | 8 | ✅ mounted since v2.9.3 |
| `app/backend/routes/execution.py` | 30+ | ❌ dormant |
| `app/backend/routes/portfolio.py` | 6 | ❌ dormant |
| `app/backend/routes/venues.py` | 12 | ❌ dormant |
| `app/backend/routes/alerts.py` | 4 | ❌ dormant |
| `app/backend/routes/portal.py` | 3 | ❌ dormant |
| `app/backend/routes/vault.py` | 4 | ❌ dormant |
| `app/backend/routes/observation.py` | 2 | ❌ dormant |
| `app/backend/arbicore/routes/arbicore.py` | 20 | ❌ dormant |
| `app/backend/arbicore/routes/opportunity_center.py` | 9 | ❌ dormant |
| `app/backend/arbicore/routes/scanners.py` | 30+ | ❌ dormant |

## 5. Collision surface (canonical mount vs current stubs)

Only 2 direct path collisions detected:

- `GET /api/arbicore/opportunities` — canonical returns
  `{count, items: [as_dict]}` shape; stub returns
  `{items, total, source, generated_at}`. **Shape adapter required.**
- `GET /api/arbicore/discovery/candidates` — canonical in
  `scanners.py`; stub in `server.py`. **Shape adapter required.**

All other 211 canonical endpoints are additive; mounting them is a
no-op on existing routes.

## 6. Frontend audit

- 160 unique `/api/*` paths referenced across `frontend/` and
  `opportunity_center/` — see `docs/roadmap_v2.10/frontend_paths.txt`.
- All page components fetch from the backend at runtime — no
  hardcoded arrays in the frontend itself.
- 2 dormant frontend files (`pages/Login.jsx`,
  `v2/components/SectionPlaceholder.jsx`) are not routed.

## 7. Per-endpoint table

See `docs/roadmap_v2.10/CANONICAL_ACTIVATION_ROADMAP.md` §"Master
activation table" — that document is the authoritative per-endpoint
mapping and includes the fix recipe for each placeholder.

## 8. Provider / integration audit (spot check)

- `bdag_transfers.py`: contains `"source": "hardcoded_estimate"` in a
  degrade-path branch (fee model fallback when runtime chain
  measurement service is unavailable). Truthfully labelled; not a
  UI-facing placeholder.
- `evidence_accuracy.py`: contains
  `"classification": "Hardcoded assumption"` on internal reports.
  Same pattern — honest labelling.
- `quote_resolver.py`: strategy B and C are labelled `STUB` in the
  source; strategy A (captured wallet quotes) is real.
- `arbicore/config/stubs_migration.py` (imported by server.py:57): a
  migration harness for moving from stub to canonical repos, itself
  not a runtime data source.

## 9. Recommendation

- **Go:** deploy `hotfix/auth-routing` as v2.9.3. See
  `docs/DEPLOY_v2.9.3.md` for the pre-flight and verification.
- **Then:** proceed slice-by-slice per
  `docs/roadmap_v2.10/CANONICAL_ACTIVATION_ROADMAP.md`, starting with
  Slice 1 (Opportunity Center). Each slice ships independently with its
  own release notes, verification, and rollback path.
- **Do not:** attempt to replace all placeholders in a single hotfix.
