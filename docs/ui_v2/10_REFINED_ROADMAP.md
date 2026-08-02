# ArbiCore X — Phase II · Refined Implementation Roadmap

**Generated:** 2026-07-31
**Purpose:** Convert the Phase II audits into an executable sequence that
maximises reuse of the canonical backend and minimises the number of new
subsystems required to reach production posture.
**Non-goal:** No implementation. No integration. No UI changes.

**Inputs**
- `06_CAPABILITY_MATRIX.md` — 48-endpoint UI ↔ backend inventory.
- `07_INSTITUTIONAL_AUDIT.md` — cross-layer gaps and P0/P1 backlog.
- `08_PREVIEW_TO_PROD_INTEGRATION_AUDIT.md` — per-endpoint canonical
  target + refinement + risks.
- `09_TREASURY_SECURITY_ARCHITECTURE.md` — engine design + subsystems.

---

## 0 · Scoping principle

The prior roadmap in `05_IMPLEMENTATION_ROADMAP.md` was built around
UI slicing (Slices 0–6). That job is done. This roadmap is built
around **backend consolidation + preview retirement**, not more UI.

> **CORRECTION (2026-07-31, after file-verified canonical audit — see
> `13_WAVE1_VERIFICATION_REPORT.md`).** The claim below that Approval
> Workflow is the "only genuinely new subsystem" is **wrong**. File
> verification of `arbicore-x-v1.0.2.bundle` shows Approval Workflow
> ALREADY EXISTS as `services/execution/approval_workflow.py` with a
> PROPOSED → APPROVED → QUOTED → CLOSED state machine. Similarly the
> Evidence Bundle already exists as
> `services/execution/certification_evidence.py`. The **only** engines
> that remain genuinely absent from the canonical repo are:
>   1. A concrete `ConfidenceCalibrator` behind
>      `learning/calibration.py` (interface exists, implementation
>      does not).
>   2. `ComplianceRegistry` (no code found).
>   3. SPATIAL_ARBITRAGE + STATISTICAL_ARBITRAGE scanners (deferred).
>
> **Phase E and Phase F below therefore change classification:**
> Phase E becomes "wire existing `approval_workflow.py` through UI +
> add threshold policy config" (Refine + Expose, not New). Phase F
> Evidence Bundle becomes "sign + endpoint-wrap
> `certification_evidence.py`" (Refine, not New). Only the concrete
> ConfidenceCalibrator + ComplianceRegistry remain as genuinely
> net-new builds.

Only ONE genuinely new subsystem is required to reach production
posture: **Approval Workflows** (§10 of the Treasury & Security
architecture doc). Every other item is a lift, refinement, or
consolidation of existing canonical code.

---

## 1 · Phased plan (5 phases, ~8 dev weeks total)

Each phase is independently deployable and independently rollback-able
via the corresponding feature flag.

### Phase A · Contract Freeze (0.5 week) — no code change

**Goal:** make the UI ↔ backend contract auditable and unblock every
downstream phase.

- Freeze `docs/ui_v2/appendix/endpoints_ui_v2.tsv` (48 rows, one per
  UI-consumed endpoint).
- Copy `backend/tests/test_v2_slice{0..5}.py` into canonical repo
  `app/backend/tests/`.
- Add `UI_V2_PROD_SLICE_{1..5}` env flags to canonical `server.py`;
  default all false; stubs remain the current handler.
- Publish the response-envelope + timestamp + error conventions
  (Preview→Prod audit §9, items CX-A / CX-B / CX-C) as a section
  of `docs/ui_v2/design_language.md`.

**Exit:** contract tests run green against production. All red tests
become the working queue for later phases.

---

### Phase B · Reuse Reads (2 weeks)

**Goal:** lift every read endpoint that is a Direct-reuse or shape-
refinement mapping. Zero writes in this phase. Highest confidence,
lowest risk.

- **Wave A (Opportunities + Portfolio reads)** — steps 1, 2, 6, 7 from
  Preview→Prod audit §8.
  - Slice 1: `GET /opportunities`, `GET /opportunities/{id}`.
  - Slice 4: `GET /positions`, `GET /balances`.
- **Wave B (Discovery + Intelligence reads)** — steps 8, 10, 11.
  - Slice 2: `GET /discovery/candidates`, `GET /intelligence/recommendations`
    (this one is composed — see Phase D), `GET /intelligence/decisions`.
- **Wave C (Operations reads)** — steps 12, 13, 15, 18, 19, 20.
  - Slice 3: venues, scanners, cycles, integrations (composed — Phase D),
    queues, alerts.
- **Wave D (Portfolio read tail)** — transfers, deployable, treasury,
  ledger, exposure, allocation (Slice 4 remainder).
- **Wave E (Settings reads)** — account, vaults, execution config,
  exchanges, notifications, operational (Slice 5 GETs).

**Exit:** every read endpoint is served by canonical routers; every
contract test is green; UI still looks identical.

**Explicit reuses** (no new code):
- `OpportunityRepo`, `DiscoveryRepo`, `DecisionAuditLog`,
  `ScannerRegistry`, `CycleRepo`, `VenueRegistry`, `AlertRepo`,
  `WorkerRegistry`, `ExecutionPositionRepo`, `VenueBalanceService`,
  `TreasuryLedger`, `CapitalRouter`, `AllocationPolicy`,
  `ExposureAnalyzer`, `UserService`, `ExecutionPolicy`,
  `NotificationConfig`, `OperatorFlags`, `SafetyInterlock`.

**Refinements only (no new services)**
- Envelope standardisation (CX-A).
- ISO timestamps (CX-B).
- Pagination cursors on `decisions`, `ledger`, `alerts`, `transfers`
  (CX-G).
- Preview badge (CX-D) — will flip false as each wave ships.

---

### Phase C · Safe Writes (1.5 weeks)

**Goal:** lift every write endpoint whose risk profile is bounded by
existing service-layer checks — that is, writes that don't move money
and don't disarm safety.

Endpoints in scope:
- `POST /opportunities/{id}/approve|reject` (Slice 1).
- `POST /discovery/candidates/{id}/action` (Slice 2).
- `POST /scanners/{family}/action` (Slice 3).
- `POST /alerts/{id}/ack` (Slice 3).
- `PATCH /settings/account` (Slice 5, whitelisted keys).
- `PATCH /settings/notifications` (Slice 5).
- `PATCH /settings/operational` (Slice 5, non-emergency toggles).

**Reuses:** existing services listed in Phase B. All extended with:
- Idempotency key handling (CX-H) — thin decorator.
- Correlation ID propagation (Treasury & Security §13.2) — read from
  request middleware.
- Audit-log entry per write (via existing `DecisionAuditLog`, extended
  in Phase E).

**Explicit non-goals** in this phase:
- No approval workflow yet.
- No interlock DISARM lift.
- No settings changes to `max_position_usd`, `max_daily_notional_usd`,
  `auto_execute_enabled`, `read_only`, `maintenance_mode`,
  `trading_paused`, or `kill_switch_wired`.
- No vault reconcile lift.
- No exchange TEST/rotate lift.

**Exit:** all read + safe-write endpoints are on production. UI still
looks identical. 33 of 48 endpoints have moved to PROD.

---

### Phase D · Composed & Long-running (1 week)

**Goal:** ship the two new composed endpoints that Phase B skipped,
plus the two long-running endpoints that need a 202-accepted
protocol.

**Composed (new endpoints)**
- `GET /arbicore/intelligence/recommendations` — composes
  `RouteScoreRepo` + `ChainAnalytics` + `EntityGraph.top()`. 60 s cache.
- `GET /arbicore/operations/integrations` — composes portal-diagnostic
  + RPC health + CoinGecko + Telegram + Chainlink into one payload.

**Long-running (protocol change, existing services)**
- `POST /settings/vaults/{v}/reconcile` — 202 with polling URL. Add
  WS broadcast on completion.
- `POST /settings/exchanges/{k}/test` — synchronous is fine (< 3 s),
  but wrap in a per-actor 30 s throttle (CX-F).

**Reuses:** all listed services. No new subsystem.

**Exit:** 37 of 48 endpoints on production. UI still identical.
Recommendations tab now shows real intelligence data.

---

### Phase E · Approval Workflows exposure (was: subsystem build) — 1 week

> **CORRECTED SCOPE (post file-verified audit).** Approval Workflows
> already exists in canonical (`services/execution/approval_workflow.py`).
> Phase E is now an **expose + refine**, not a build.

**Goal:** wire the existing Approval Workflow through the UI and add a
threshold policy configuration surface. Route high-risk mutations
through it.

**Reused code (verified)**
- `services/execution/approval_workflow.py` — PROPOSED → APPROVED →
  QUOTED → CLOSED state machine + staleness handling.
- `services/execution/approval_proposer.py` — proposal engine.
- `learning/concrete/audit_log.py` — extended for cross-subsystem write
  audit.

**Refinements (small)**
- Add threshold policy read/write via new endpoint (e.g. > $50k
  outgoing).
- Add UI Approval Inbox as a new Ops sub-tab (deferred UI ticket, not
  in Phases A–G).

**Goal:** stand up the Approval Workflows subsystem (§10 of the
Treasury & Security architecture) and route every high-risk mutation
through it.

**New code (justified — capability does not exist)**
- `arbicore/security/approvals.py` — state machine `PROPOSED →
  APPROVED_BY_A → APPROVED_BY_B → EXECUTED / REJECTED / EXPIRED`.
- `arbicore/security/audit.py` — extension of existing
  `DecisionAuditLog` to accept every subsystem's writes with a common
  entry shape.

**Endpoints now routed through approvals**
- `POST /interlock/action?action=disarm` — two-person confirm.
- `POST /interlock/action?action=arm` — no approval (safety default).
- `PATCH /settings/execution` for `max_position_usd`,
  `max_daily_notional_usd`, `auto_execute_enabled`.
- `PATCH /settings/operational` for `read_only`, `maintenance_mode`,
  `trading_paused`.
- `POST /settings/vaults/{v}/reconcile` if diff is non-zero.
- Future: outgoing transfer above $50k threshold (blocked until
  transfers write endpoint is added — not in current UI).

**Reuses:** none — this is the only justified net-new subsystem.

**Contract impact:** each endpoint may now return `202 Accepted` with
`{workflow_id, next_state, next_actor_role}`. UI already ignores
unknown top-level fields — no UI change required. A follow-up UI
addition (Approval Inbox) is P1 backlog, not this phase.

**Exit:** 41 of 48 endpoints on production. Institutional gate for
safe-disarm + parameter changes achieved.

---

### Phase F · Missing Capability Build + Refinements (1.5 weeks)

> **CORRECTED SCOPE (post file-verified audit).** Evidence Bundle
> already exists (`services/execution/certification_evidence.py`).
> Only signing + HTTP endpoint wrapping is missing. Concrete
> ConfidenceCalibrator and ComplianceRegistry are the truly net-new
> items.

**Goal:** wrap the existing evidence bundler with signing + an HTTP
endpoint, build the two genuinely absent capabilities, and activate
the global kill-switch endpoint.

**Refinements (small — reuse existing engines)**
- `GET /opportunities/{id}/evidence` → wraps
  `certification_evidence.build()` with an Ed25519 signature.
- Global kill-switch endpoint on top of existing
  `services/execution/safety_interlock.py`.

**Genuinely net-new builds**
- **Concrete `ConfidenceCalibrator`** implementation behind
  `learning/calibration.py::ConfidenceCalibrator` ABC. Feeds the
  `/intelligence/calibration` endpoint activated in Wave 1 with real
  data.
- **ComplianceRegistry** — new module + endpoint. Consumed on Ops →
  Venues, Portfolio → Balances, Settings → Exchanges.

**Goal:** ship the two capabilities identified as **Missing** in the
Preview→Prod audit and the P0 items from institutional audit.

**Missing capabilities (from §7 of Preview→Prod audit)**
- `GET /opportunities/{id}/evidence` → `EvidenceBundle.export(cycle_id)`
  (institutional audit 1.6.6, EX-4).
- Signed evidence.zip with Ed25519 signature.

**P0 institutional gaps**
- **Kill-switch API** — `POST /arbicore/security/kill_switch`
  (institutional audit SEC-5). Header UI button follows in a later
  UI ticket, not this phase.
- **Compliance flags** — `GET /arbicore/security/compliance/{target}`
  reused across Ops → Venues and Portfolio → Balances rows
  (institutional audit SEC-4). UI wiring is a later UI ticket.

**Reuses**
- Existing signing key or KMS handle from Secret Management.
- `AlertRepo` for kill-switch broadcast.

**Exit:** 44 of 48 endpoints on production. The remaining 4 are Slice-0
composed (already PROD from day 1). **All UI functional migration
complete.**

---

### Phase G · Consolidation & Retirement (0.5 week)

**Goal:** delete the temporary scaffolding.

- Remove all `_V2_*` seed data from `backend/server.py`.
- Split `server.py` into `arbicore/routes/{...}.py` per Phase-II
  cross-cutting CX-6.
- Remove `LegacyLanding` from `frontend/src/App.js`.
- Point `/` to the v2 shell (Slice 6 cutover).
- Remove pod-local `.env` files (canonical repo owns env).
- Flip `preview: false` on every response envelope.

**Exit:** production posture achieved. Contract tests still green.

---

## 2 · Timeline & dependencies

```
Week:  1     2     3     4     5     6     7     8
A ┃█░░░
B ┃    █████████░░
C ┃              ██████░░
D ┃                    ████░░
E ┃                          ████████░░
F ┃                                    ██████░░
G ┃                                          ██░
```

- **B ← A** (need frozen contract before any lift).
- **C ← B** (writes ride on read-endpoint stability).
- **D can overlap with C** (independent surfaces).
- **E ← C** (must own audit log first).
- **F can overlap with E** (independent evidence build).
- **G ← F** (retire scaffolding only after everything is lifted).

---

## 3 · Endpoint accounting (48 endpoints)

| Origin phase | Count | Notes |
|---|---|---|
| Phase 0 (Slice 0 composed, already PROD) | 4 | pulse, deck, opps_summary, roi_probability |
| Phase 0 (Slice 0 system) | 1 | /system/status |
| Phase B (read lifts) | 28 | direct + refinement reads |
| Phase C (safe writes) | 7 | approve/reject/action/ack/patch |
| Phase D (composed + long-running) | 4 | recommendations, integrations, reconcile, test |
| Phase E (via approvals) | 4 | interlock, execution PATCH (high-risk), operational PATCH (high-risk), vaults reconcile (non-zero diff) — *same routes as B/C/D, re-routed* |
| Phase F (missing) | ≥ 2 | evidence, kill-switch, compliance-flags (additive) |
| **Total surfaced** | **48+** | plus 2–3 new endpoints from F |

Endpoints in Phase E overlap Phase B/C/D — they are the same URL paths
gaining an approval hop. Not double-counted.

---

## 4 · Reuse scorecard

Consolidated from Preview→Prod audit §7.

| Category | Count | % |
|---|---|---|
| Direct reuse | 6 | 12.5% |
| Reuse w/ refinement | 34 | 71% |
| Composed (new endpoint, reused services) | 4 | 8.3% |
| Missing capability (net-new endpoint over reused signing/notif services) | 2 | 4.2% |
| New subsystem | 1 (Approval Workflows) | 2% |
| **Total** | **48** | **100%** |

**Net-new code volume:** ≈ 1 subsystem (approvals ~ 400–600 LOC) + ≈ 2
missing-capability endpoints (~ 200 LOC each) + refinements (~ 40
endpoints × 20–50 LOC each). Everything else is reuse.

---

## 5 · Non-goals of this roadmap

- No new UI screens. The UI addition items in institutional audit §8
  (P1..P3) are staged **after** Phase G.
- No new pages, tabs, or components in Phases A–G.
- No refactor of existing scanner engines, scoring engines, or
  execution routers.
- No replacement of any working subsystem — only consolidation of
  scattered logic into the ownership map (§15 of Treasury & Security).
- No adoption of new frameworks, no ORM migration, no DB migration.

---

## 6 · Risk register (roll-up)

Full detail lives in Preview→Prod audit §10 and Treasury & Security §16.
Top-line:

| # | Risk | Phase | Mitigation |
|---|---|---|---|
| 1 | Contract shape drift as endpoints are refined | B, C | Freeze TSV before B; contract tests are tripwire |
| 2 | Auth boundary silently open post-lift | B, C, E | Add 401/403 tests to every slice before its lift |
| 3 | Approval-workflow expiration policy misconfigured | E | Ship with conservative 24 h default; measure before tuning |
| 4 | Evidence-bundle signing key handling | F | Route through Secret Management from day 1; audit-log every use |
| 5 | Latency regression when swapping stub for real repo | B | Add p95 SLO tests to `pulse` + read endpoints (< 300 ms / < 500 ms) |
| 6 | Kill-switch broadcast to live UI sessions | F | Piggyback on existing WS/SSE channel if present; fallback poll |
| 7 | Composed endpoint fan-out cost | D | 60 s cache; degrade-to-null per source |

---

## 7 · Exit criteria for production posture

After Phase G is complete, the following must all hold:

- [ ] 48 preview endpoints retired; 44+ production endpoints serving
      the same UI contract.
- [ ] All 62 contract tests green against production.
- [ ] Approval Workflow enforces every mutation on the whitelist
      (Treasury & Security §10).
- [ ] Audit Log covers every mutation and cycle-level decision.
- [ ] Kill-switch verified end-to-end (endpoint → broadcast → session
      state).
- [ ] Evidence bundle exports for a completed cycle, signature verifies
      against published public key.
- [ ] Latency p95 within SLO for every read endpoint.
- [ ] Zero pod-local seed data in production `server.py`.

---

## 8 · Deliverable status (Phase II total)

- [x] Preview → Production Integration Audit
      (`08_PREVIEW_TO_PROD_INTEGRATION_AUDIT.md`).
- [x] Treasury & Security Engine Architecture
      (`09_TREASURY_SECURITY_ARCHITECTURE.md`).
- [x] Refined Implementation Roadmap (this document,
      `10_REFINED_ROADMAP.md`).
- [ ] Contract TSV freeze — pending user action (Phase A entry gate).
- [ ] Answers to `09` §16 open questions — pending user input.

No production integration performed. No UI feature added. No code
generated beyond ownership-map recommendations.
