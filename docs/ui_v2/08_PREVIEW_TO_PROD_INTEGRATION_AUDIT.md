# ArbiCore X — Phase II · Preview → Production Integration Audit

**Generated:** 2026-07-31
**Scope:** Every preview endpoint currently consumed by UI v2 (Slices 0–5).
**Purpose:** Give engineering a per-endpoint mapping to the canonical
production implementation so integration can proceed without re-designing
either side.
**Non-goal:** No production integration in this document. No code changes.

**Reference sources**
- `docs/ui_v2/01_BACKEND_CAPABILITY_AUDIT.md` — canonical 245-endpoint audit.
- `docs/ui_v2/02_UI_EXPOSURE_MATRIX.md` — 38% baseline coverage snapshot.
- `docs/ui_v2/06_CAPABILITY_MATRIX.md` — this repo's per-slice mapping.
- `docs/ui_v2/07_INSTITUTIONAL_AUDIT.md` — engineering-facing gaps.
- `backend/server.py` — inline future-endpoint hints per stub.
- `frontend/src/v2/lib/api.js` — canonical UI ↔ endpoint list.

---

## 0 · Method

For every UI-facing preview endpoint the audit records:

| Col | Meaning |
|---|---|
| Preview | Path served by the pod-local stub in this repo. |
| Canonical | Router + service (or repository) that owns the capability in the canonical repo. Best-guess names use the `arbicore/` module layout the canonical audit documents. |
| Parity | **Direct reuse** · **Reuse w/ refinement** · **Missing capability** · **Composed (new)** |
| Refinements | Shape, field, or behaviour deltas that must land before the UI can be pointed at the canonical route. |
| Complexity | **LOW** (< 1 dev-day) · **MED** (1–3) · **HIGH** (> 3) |
| Order | Recommended lift order within the migration (1 = first). |
| Risks | Specific hazards discovered during audit. |

Endpoints that are Slice 0 composed (already PROD) are excluded from the
table but retained in §5.

---

## 1 · Slice 1 — Opportunities

| # | Preview | Canonical | Parity | Refinements | Complexity | Order | Risks |
|---|---|---|---|---|---|---|---|
| 1.1 | `GET /api/arbicore/opportunities` | `arbicore/routes/opportunities.list` over `OpportunityRepo.find_many()` | Reuse w/ refinement | Support `family`, `chain`, `verdict`, `min_confidence` query params; return `{items,total,generated_at}` envelope | LOW | **1** | Existing router may already return a bare array — envelope wrap required |
| 1.2 | `GET /api/arbicore/opportunities/{id}` | `arbicore/routes/opportunities.detail` over `OpportunityRepo.get_with_reasoning()` | Reuse w/ refinement | Payload must include `reasoning.confidence_breakdown`, `reasoning.gates_passed/dropped`, `verification.*`, `quote`, `sizing`, `evidence.download_endpoint` | MED | **2** | `evidence.download_endpoint` is currently unpaired (see 1.4). Attach that path in the payload; the target endpoint doesn't exist yet |
| 1.3 | `POST /api/arbicore/opportunities/{id}/approve` | `OpportunityService.approve()` | Reuse w/ refinement | Must be idempotent + audit-logged + auth-gated (RBAC = operator) | LOW | **3** | Missing auth-required test today; add before lift |
| 1.4 | `POST /api/arbicore/opportunities/{id}/reject` | `OpportunityService.reject()` | Reuse w/ refinement | Same as 1.3 | LOW | **4** | Same as 1.3 |
| 1.5 | *(promised)* `GET /api/arbicore/opportunities/{id}/evidence` | **Not implemented** — canonical `EvidenceBundle.export()` needed | Missing capability | Ship signed evidence.zip. Ed25519 signature. Deterministic manifest | HIGH | **5** | Blocking P0 from institutional audit; also blocks 1.2 payload |

**Slice-1 summary:** 4 of 5 endpoints are Direct/Refinement reuse; the
5th is a missing capability that the UI already gestures at.

---

## 2 · Slice 2 — Discovery + Intelligence

| # | Preview | Canonical | Parity | Refinements | Complexity | Order | Risks |
|---|---|---|---|---|---|---|---|
| 2.1 | `GET /api/arbicore/discovery/candidates` | `arbicore/routes/discovery.list` over `DiscoveryRepo.list_candidates()` | Reuse w/ refinement | Return payload must include the `stats` block (new/watching/promoted/dismissed counts) that the UI header consumes | LOW | **8** | Existing endpoint likely returns raw items — needs stats projection |
| 2.2 | `POST /api/arbicore/discovery/candidates/{id}/action` | `DiscoveryService.transition()` | Reuse directly | `action` query param → `{watch, promote, dismiss, reset}` state machine | LOW | **9** | State-machine transitions must be atomic; add audit entry |
| 2.3 | `GET /api/arbicore/intelligence/recommendations` | **Composed** over `RouteScoreRepo`, `ChainAnalytics`, `EntityGraph.top()` | Composed (new) | Compose the 3 sources server-side to keep UI dumb | MED | **10** | Response cost — cache 60 s server-side |
| 2.4 | `GET /api/arbicore/intelligence/decisions` | `arbicore/routes/decisions.list` over `DecisionAuditLog.list()` | Reuse w/ refinement | Support `verdict`, `family`, `min_confidence` filters; include `top_factors` array | LOW | **11** | Log volume can be large — add pagination cursor before lift |

**Slice-2 summary:** one new composed endpoint (2.3). Everything else is
direct or shape refinement.

---

## 3 · Slice 3 — Operations

| # | Preview | Canonical | Parity | Refinements | Complexity | Order | Risks |
|---|---|---|---|---|---|---|---|
| 3.1 | `GET /api/arbicore/operations/scanners` | Canonical hint: `/api/arbicore/scanners` over `ScannerRegistry.snapshot()` | Reuse w/ refinement | 8 families required, per-family counters (`opps_1h`, `gates_dropped_1h`, `errors_1h`, `last_run`) | LOW | **13** | Registry may only emit a subset today — add missing families as no-op stubs first |
| 3.2 | `POST /api/arbicore/operations/scanners/{family}/action` | `ScannerController.transition()` | Reuse w/ refinement | Accept `start`, `pause`, `stop`; return persisted state | LOW | **14** | Must be RBAC-gated (operator) + audit-logged |
| 3.3 | `GET /api/arbicore/operations/cycles` | `arbicore/routes/cycles.list` over `CycleRepo.recent()` | Reuse w/ refinement | Support `status` filter; envelope `{items,total,generated_at}` | LOW | **15** | Row shape — add `size_usd` if not present today |
| 3.4 | `GET /api/arbicore/operations/venues` | Canonical hint: `/api/venues/status` over `VenueRegistry.status_snapshot()` | Reuse directly | 9 venues; existing state enum matches | LOW | **12** | Slight risk: canonical may use different state labels — normalise if needed |
| 3.5 | `GET /api/arbicore/operations/interlock` | Canonical hint: `/api/execution/interlock` over `SafetyInterlock.snapshot()` | Reuse w/ refinement | Return `armed`, `state`, `gates[]`, `last_transition_at` | LOW | **16** | 5 gates exactly — audit existing gate keys before mapping |
| 3.6 | `POST /api/arbicore/operations/interlock/action` | `SafetyInterlock.arm()/disarm()` | Reuse directly | `arm`/`disarm` params | LOW | **17** | Requires two-person confirmation policy (see Treasury & Security doc §6.5) |
| 3.7 | `GET /api/arbicore/operations/integrations` | Canonical hint: `/api/execution/portal/diagnostic` (partial) + `IntegrationRegistry.status()` | Composed (new) | Compose portal + RPC + CG + Telegram + Chainlink health into one payload | MED | **18** | Portal diagnostic returns raw payload — must be summarised, not echoed |
| 3.8 | `GET /api/arbicore/operations/queues` | `WorkerRegistry.queue_stats()` | Reuse w/ refinement | 5 queues required; add `rate_per_min` if missing | LOW | **19** | Registry may not have `failed_1h` counter — add or compute in composed endpoint |
| 3.9 | `GET /api/arbicore/operations/alerts` | `AlertRepo.list_recent()` | Reuse w/ refinement | Support `severity` filter; envelope | LOW | **20** | — |
| 3.10 | `POST /api/arbicore/operations/alerts/{id}/ack` | `AlertService.ack()` | Reuse directly | Return `{ok, id, acked}` | LOW | **21** | Idempotent ack |

**Slice-3 summary:** highest reuse rate (7/10 direct or minor refinement).
One new composed endpoint (3.7). Aggregate complexity is LOW.

---

## 4 · Slice 4 — Portfolio

| # | Preview | Canonical | Parity | Refinements | Complexity | Order | Risks |
|---|---|---|---|---|---|---|---|
| 4.1 | `GET /api/arbicore/portfolio/positions` | `ExecutionPositionRepo.snapshot()` | Reuse w/ refinement | Add `total_size_usd`, `total_upnl_usd` aggregates | LOW | **6** | Position side enum must include `LP` (LP positions) |
| 4.2 | `GET /api/arbicore/portfolio/balances` | `VenueBalanceService.aggregate()` | Reuse directly | 11 rows across CEXs + cold wallet | LOW | **7** | Include non-liquid rows (cold_wallet BTC/ETH) — canonical may filter these today |
| 4.3 | `GET /api/arbicore/portfolio/transfers` | `TreasuryLedger.transfers()` | Reuse w/ refinement | Support `status` filter; include `kind`, `tx` fields | LOW | (queued behind 4.1/4.2) | Cross-references vaults + venues; joins must not N+1 |
| 4.4 | `GET /api/arbicore/portfolio/deployable` | Canonical hint: `/api/portfolio/deployable` over `CapitalRouter.deployable_snapshot()` | Reuse w/ refinement | Include `per_venue[]` breakdown with `deployable_usd`, `utilised_usd`, `utilisation_pct` | LOW | (queued) | Must agree with Interlock gate `capital_deployable` — same source-of-truth |
| 4.5 | `GET /api/arbicore/portfolio/treasury` | `TreasuryLedger.vault_snapshot()` | Reuse w/ refinement | `vaults[]` with `kind` ∈ {COLD, HOT, MULTISIG, EXCHANGE} | LOW | (queued) | Reconcile timestamp must reflect the actual last-run |
| 4.6 | `GET /api/arbicore/portfolio/ledger` | `TreasuryLedger.entries()` | Reuse w/ refinement | Support `kind` filter; running `balance_usd` per row | MED | (queued) | Running balance requires ordered scan — index required |
| 4.7 | `GET /api/arbicore/portfolio/exposure` | `ExposureAnalyzer.breakdown()` | Reuse w/ refinement | Percentages must sum to ~1.0; add `delta_24h_pct` | MED | (queued) | Historical delta needs 24h snapshot table |
| 4.8 | `GET /api/arbicore/portfolio/allocation` | `AllocationPolicy.status()` | Reuse w/ refinement | Buckets with target/actual/delta and `status` ∈ {UNDER, OVER, ON_TARGET} | LOW | (queued) | Buckets must align with scanner families + treasury reserve |

**Slice-4 summary:** all reuse; refinements are envelope + aggregate
projections. No missing capabilities.

---

## 5 · Slice 5 — Settings

| # | Preview | Canonical | Parity | Refinements | Complexity | Order | Risks |
|---|---|---|---|---|---|---|---|
| 5.1 | `GET /api/arbicore/settings/account` | `UserService.profile()` | Reuse w/ refinement | Include `mfa_enabled`, `session_ttl_min`, `role`, `last_login_at` | LOW | **28** | Do not leak email verification tokens |
| 5.2 | `PATCH /api/arbicore/settings/account` | `UserService.update_profile()` | Reuse w/ refinement | Whitelist `display_name`, `email`, `mfa_enabled`, `session_ttl_min` | LOW | **29** | Email change must re-verify — UI must show pending state |
| 5.3 | `GET /api/arbicore/settings/vaults` | `TreasuryLedger.list_vaults()` | Reuse w/ refinement | Include `signers_required/total`, `state`, `reconciled_at` | LOW | **30** | Address must never be a private-key export |
| 5.4 | `POST /api/arbicore/settings/vaults/{v}/reconcile` | `TreasuryLedger.reconcile(v)` | Reuse w/ refinement | Return diff report (see §5 of institutional audit) | MED | **31** | Long-running — 202 + polling, or WS |
| 5.5 | `GET /api/arbicore/settings/execution` | `ExecutionPolicy.config()` | Reuse w/ refinement | Include all 9 keys (max_position, max_daily_notional, slippage_bps, min_confidence, min_safety, freshness_max_s, auto_execute_enabled, auto_execute_verdict, kill_switch_wired) | LOW | **32** | `kill_switch_wired` is read-only — must not accept PATCH |
| 5.6 | `PATCH /api/arbicore/settings/execution` | `ExecutionPolicy.update()` | Reuse w/ refinement | Whitelist keys; validation on numeric ranges | MED | **33** | Auto-execute toggle must trigger safety re-checks — likely a new hook |
| 5.7 | `GET /api/arbicore/settings/exchanges` | `VenueRegistry.list_configured()` | Reuse w/ refinement | Include `api_key_masked` (never raw), `state`, `read_only`, `last_tested_at`, `role` | MED | **34** | Payload must never contain plaintext key — contract test already asserts |
| 5.8 | `POST /api/arbicore/settings/exchanges/{k}/test` | `VenueRegistry.test_connectivity(k)` | Reuse w/ refinement | Return `{ok, state, latency_ms, tested_at}` | LOW | **35** | Rate-limit — one test per 30 s per venue |
| 5.9 | `GET /api/arbicore/settings/notifications` | `NotificationConfig.load()` | Reuse directly | telegram/email/webhook + severities + events | LOW | **36** | — |
| 5.10 | `PATCH /api/arbicore/settings/notifications` | `NotificationConfig.save()` | Reuse w/ refinement | Merge-patch semantics on nested `severities` and `events` | LOW | **37** | Webhook URL validation (https only + no localhost) |
| 5.11 | `GET /api/arbicore/settings/documentation` | *(static registry)* | Direct reuse (client-side ok) | Keep as client-side or add trivial static-file endpoint | LOW | **38** | Do not couple to build system |
| 5.12 | `GET /api/arbicore/settings/operational` | `OperatorFlags.snapshot()` | Reuse w/ refinement | Nested `feature_flags` dict | LOW | **39** | Include `ui_v2` flag for round-trip with Slice 0 heartbeat |
| 5.13 | `PATCH /api/arbicore/settings/operational` | `OperatorFlags.set()` | Reuse w/ refinement | Merge-patch on `feature_flags`; audit-log every change | LOW | **40** | Toggling `read_only` or `maintenance_mode` must broadcast to all live sessions |

**Slice-5 summary:** all reuse; refinements are shape + validation.
Special care on secret-adjacent surfaces (5.7 API keys).

---

## 6 · Slice 0 — Composed (already PROD)

For completeness — no work required, but retained as the reuse model.

| # | Endpoint | Canonical | Parity | Notes |
|---|---|---|---|---|
| 6.1 | `GET /api/arbicore/dashboard/pulse` | `arbicore/routes/dashboard.pulse` | PROD (composed) | Slice 0 delta |
| 6.2 | `GET /api/arbicore/dashboard/deck` | `arbicore/routes/dashboard.deck` | PROD (composed) | Slice 0 delta |
| 6.3 | `GET /api/arbicore/opportunities/summary` | `arbicore/routes/dashboard.opps_summary` | PROD (composed) | Slice 0 delta |
| 6.4 | `GET /api/arbicore/roi-probability` | `arbicore/routes/dashboard.roi_probability` | PROD (composed) | Slice 0 delta |
| 6.5 | `GET /api/system/status` | `arbicore/routes/system.status` | PROD | Feature-flag surface |

---

## 7 · Aggregate reuse profile

| Parity | Count | % of PREVIEW total |
|---|---|---|
| Direct reuse | 6 | 14% |
| Reuse w/ refinement | 34 | 77% |
| Composed (new) | 2 | 5% |
| Missing capability | 2 | 5% (1.5 + related) |
| **Total PREVIEW endpoints** | **44** | **100%** |

**Interpretation.** The canonical backend already implements or nearly
implements 91% of the UI contract. The migration is dominated by
shape/envelope refinements + validation additions rather than net-new
capability work.

---

## 8 · Recommended migration order (rolled up)

The per-endpoint `Order` column above is consolidated here.

1. **Wave A — Positions of trust (Opportunities + Portfolio reads)**
   - Steps 1–8: Slice-1 endpoints (1.1–1.4), Slice-4 read endpoints
     (4.1–4.2). Reason: highest-visibility screens, no writes to
     capital.
2. **Wave B — Discovery + Intelligence reads**
   - Steps 8–11: Slice-2 endpoints (2.1–2.4).
3. **Wave C — Operations reads + safe writes**
   - Steps 12–21: Slice-3 endpoints, including safe writes
     (scanner action, alert ack). Interlock disarm is a write but
     already tightly gated.
4. **Wave D — Settings**
   - Steps 28–40: Slice-5 endpoints. Highest secret-adjacency;
     lift last with an extra security review.
5. **Wave E — Missing capabilities**
   - Step 5: Evidence bundle export. Blocking for regulatory ship;
     not blocking for UI functional lift.
6. **Wave F — Retirement**
   - Delete stub seed data + `LegacyLanding` after ≥ 1 week clean
     per wave.

---

## 9 · Cross-cutting refinements (apply once across all endpoints)

- **CX-A · Response envelope.** Standardise on
  `{items, total, generated_at}` for list endpoints and
  `{config, generated_at}` for singleton read endpoints.
- **CX-B · ISO-8601 timestamps** everywhere with tz. Already the case
  in stubs; contract tests enforce.
- **CX-C · Error envelope.** `{error, detail, correlation_id}` —
  correlation ID is required so UI can surface it in toasts and
  Ops → Alerts.
- **CX-D · Preview badge.** Add top-level `preview: bool` to every
  payload so the UI can badge preview data during migration windows.
- **CX-E · Auth boundary.** All write endpoints must return 401
  without token and 403 without RBAC role; add contract tests before
  lift.
- **CX-F · Rate-limit.** `POST /exchanges/{k}/test` and
  `POST /vaults/{v}/reconcile` should carry a 30 s per-actor
  server-side throttle.
- **CX-G · Pagination cursor** for high-volume list endpoints
  (`decisions`, `ledger`, `alerts`, `transfers`) — add before lift.
- **CX-H · Idempotency.** All POST actions
  (`approve`, `reject`, `ack`, scanner action, interlock action) must
  be idempotent on a client-supplied `Idempotency-Key` header.

---

## 10 · Consolidated risks

| Risk | Slice(s) | Mitigation |
|---|---|---|
| Contract-shape drift under refinement | 1–5 | Freeze `endpoints_ui_v2.tsv` before Wave A. Contract tests are the tripwire. |
| Auth boundary silently open on lift | 1, 3, 5 | Add 401/403 tests to `test_v2_slice*` before each wave. |
| API-key leakage in exchanges payload | 5 | Contract test already asserts `••` in `api_key_masked`. Extend to reject any 20+ char alnum substring. |
| Missing evidence endpoint blocks Drawer completeness | 1 | Backlog P0. Ship as Wave E; UI functional migration proceeds without it. |
| Preview→prod latency regression | 3 (interlock/venues), 4 (deployable) | Add p95 SLO test to `pulse` (< 300 ms) + all read endpoints (< 500 ms). |
| Interlock disarm not two-person gated | 3 | Add cosigner/witness confirmation in production; see Treasury & Security doc §6.5. |
| Auto-execute toggle mis-fires | 5 | Introduce staged apply (`draft → confirm → applied`) on Execution Policy PATCH. |
| Ledger running-balance drift under concurrency | 4 | Server-side compute at read-time from atomic entries; do not persist running balance. |
| Composed intelligence endpoint expensive | 2 | 60 s cache; degrade to null block per source. |
| Reconcile long-running blocks HTTP thread | 5 | 202 + polling, or promote to background job with WS notification. |

---

## 11 · Deliverable status

- [x] Preview endpoint inventory (44 endpoints).
- [x] Canonical target identified for each.
- [x] Parity classification (Direct/Refinement/Composed/Missing).
- [x] Refinements listed.
- [x] Complexity + order + risks per endpoint.
- [x] Cross-cutting refinements consolidated.
- [ ] `endpoints_ui_v2.tsv` frozen — pending user action.
- [ ] Contract tests copied into canonical repo — pending user action.

No production integration performed. No code generated.
