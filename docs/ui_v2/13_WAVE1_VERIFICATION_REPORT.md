# ArbiCore X — Wave 1 · Canonical Verification, Scheduler Validation & Activation Report

**Generated:** 2026-07-31
**Purpose:** Fulfil the three pre-Wave-2 verification requests using **direct
inspection of the canonical repository** extracted from
`/app/arbicore-x-v1.0.2.bundle`.

**Method correction.** In prior audits I stated the canonical source was
not present in this pod. That was wrong — the v1.0.2 git bundle at
`/app/arbicore-x-v1.0.2.bundle` (1.5 MB) is a full git repository. It has
now been extracted to `/tmp/canonical_extract/` for this verification.
All findings below are **file-verified**, not documentary-only.

---

## 1 · Canonical Verification (Task 1)

### 1.1 What was actually found in canonical v1.0.2

Structure (verified):
```
app/backend/
├── arbicore/
│   ├── data/mongo/                 · repositories
│   ├── intel/launch/               · launch-arb intelligence
│   ├── intelligence/validators/    · validator layer
│   ├── learning/
│   │   ├── base.py
│   │   ├── calibration.py          · INTERFACE ONLY — "Not implemented yet"
│   │   ├── outcomes.py
│   │   ├── route_success.py
│   │   ├── weights.py
│   │   └── concrete/               · 14 files (see §1.2)
│   ├── models/                     · pydantic
│   ├── routes/                     · arbicore.py, scanners.py, opportunity_center.py
│   ├── runtime/
│   ├── scanner/                    · legacy
│   ├── scanners/
│   │   ├── cex_arbitrage/
│   │   ├── cross_chain_arbitrage/
│   │   ├── dex_arbitrage/
│   │   ├── discovery/
│   │   ├── flash_loan_arbitrage/
│   │   ├── funding_arbitrage/
│   │   ├── launch_arbitrage/
│   │   └── gates/                   · gate library
│   ├── shadow/                     · shadow-execution layer
│   └── scripts/
├── services/
│   ├── auth.py, balances.py, capability.py, collector.py, db.py
│   ├── discovery.py, exchange_private.py, holdprob.py, key_health.py
│   ├── observation.py, portal_price.py, seed.py, telegram_alerts.py
│   ├── vault.py, ws_manager.py, health_analytics.py
│   ├── venue_monitor/
│   └── execution/                  · 51 files (see §1.3)
├── engines/
├── connectors/
├── core/
├── routes/
├── scripts/
└── tests/
```

### 1.2 Learning-layer engines — ground truth

`app/backend/arbicore/learning/concrete/` contains:

| File | Verified role |
|---|---|
| `route_success_tracker.py` | **MongoRouteSuccessTracker** — real, active. Wave-1 assumption confirmed. |
| `confidence_engine.py` | **ConfidenceScorer** — real, active. |
| `outcome_tracker.py` | Outcome ingestion into learning loop. |
| `regime_classifier.py` + `regime_worker.py` | **RegimeDetector** — real, active. **Has a worker (scheduled).** |
| `adaptive_weights.py` | Weight-tuning back-loop for scorers. |
| `audit_log.py` | **DecisionAuditLog** — real, active. |
| `metrics_aggregator.py` | Rollups. |
| `evaluator_worker.py` | **General learning evaluator — scheduled worker.** |
| `sequence_miner.py` | **Sequence patterns** — actually implemented (previously listed as dormant, wrong). |
| `state_observers.py` | Learning-side observers. |
| `survival.py` | **Survival model** — actually implemented (per-opportunity survival curves). |
| `models.py` | Pydantic models for the learning layer. |

### 1.3 Execution-layer engines — ground truth

`app/backend/services/execution/` contains 51 files. Highlights that
contradict earlier audit assumptions:

| File | Verified role | Prior audit claim | Corrected classification |
|---|---|---|---|
| `approval_workflow.py` | **State machine PROPOSED → APPROVED → QUOTED → CLOSED**, with proposal engine | "Not Implemented — new subsystem" | **Active — Reuse. Not net-new.** |
| `approval_proposer.py` | Approval proposal engine | (implied new) | Active — Reuse |
| `certification_evidence.py` | **8-section evidence package assembler** | "Not Implemented — new subsystem" | **Active — Reuse. Evidence bundle already exists.** |
| `certification_review.py` | Shadow certification review pipeline (READY_FOR_MICROCAPITAL_REVIEW / NEEDS_MORE_DATA / NOT_READY verdict) | "RouteCertifier — dormant" | **Active — Reuse. RouteCertifier exists as certification_review.py.** |
| `certification.py` | Shadow certification report analytics | idem | Active — Reuse |
| `safety_interlock.py` | **SafetyInterlock** — real | Confirmed active | Reuse |
| `opportunity_gate.py` | **GateDropAudit** source | Partial | Active — Refine (surface `gates/dropped` per family) |
| `exchange_intelligence.py` | **VenueRegistry + venue qualification** | Confirmed | Reuse |
| `venue_registry.py` | Explicit venue registry | Confirmed | Reuse |
| `portal_diag.py` | **Portal Quote Diagnostic** | Active per pulse pointer | Reuse |
| `ledger.py` + `permanent_ledger.py` | **TreasuryLedger** primary + append-only | Confirmed | Reuse |
| `bdag_transfers.py`, `blockdag_rpc.py` | **Wallet transfer executor (BDAG-specific)** | (implied new / scattered) | Reuse. WalletRegistry-adjacent. |
| `wallet_observer.py` | **Wallet observation loop** — actual WalletRegistry proxy | "WalletRegistry — dormant / scattered" | **Active — Refine (consolidate observation + BDAG transfers as WalletRegistry facade).** |
| `sizing.py` | Position sizing | Confirmed | Reuse |
| `fees.py` + `fee_provenance.py` + `bdag_transfers.py` | Fee catalogue with real-vs-assumption provenance | Confirmed | Reuse |
| `drift_engine.py` + `drift_runner.py` | Price-drift monitor (part of freshness gate) | Confirmed | Reuse |
| `arbitrage_cycles.py` + `cycle_model.py` + `cycle_timing.py` | Cycle lifecycle | Confirmed active | Reuse |
| `audit.py` | Execution audit log | Confirmed | Reuse |
| `fresh_cycle_analytics.py` + `fresh_cycle_watch.py` | Cycle freshness monitor | Confirmed | Reuse |
| `quote_capture.py` + `quote_resolver.py` | Quote layer | Confirmed | Reuse |
| `shadow.py` | **Shadow execution** — parallel to real execution | (missed by prior audit) | Active — Reuse |
| `recovery_proof.py` | Stuck-cycle recovery evidence | (missed by prior audit) | Active — Reuse |
| `campaign.py` | Certification campaigns | (missed) | Active — Reuse |
| `fund_tracker.py` | Cross-cycle fund flow tracking | (missed) | Active — Reuse |
| `integration_monitor.py` + `integration_prep.py` | Integration health rollups | Confirmed | Reuse |
| `operator_console.py` | Server-side operator console primitives | (missed) | Active — Reuse |
| `production_workflow.py` | Production-gate workflow | (missed) | Active — Reuse |

### 1.4 Route surface — ground truth

`app/backend/arbicore/routes/arbicore.py` already exposes (verified via
grep, all `require_auth`-gated):

| Endpoint | Prior audit claim | Correction |
|---|---|---|
| `GET /health`, `/learning-status` | (missing) | **Active** — surface these on Ops → Integrations |
| `GET /outcomes`, `/route-stats` | Slice 0 pointer to `/roi-probability` | **Already exists directly.** Slice-0 composed endpoint is a proper superset. |
| `GET /weights/current` | (missing) | **Active** — surface these on Intelligence → Weights (future tab) |
| `GET /confidence/score` | Slice 0 composed | Already exists — reuse |
| `GET /regime/latest`, `/regime/history` | "regime history not surfaced" | **`/regime/history` already exists** — Wave-1's AI-1 sparkline is a straight reuse, not new capability |
| `GET /sequences/patterns` | Not listed | **Active** — surface as future Intelligence tab |
| `GET /survival/{subject_id}` | Not listed | **Active** — could surface per-opp in Drawer |
| `GET /entities`, `/entities/clusters`, `/entities/scores/top`, `/entities/resolve`, `/entities/{id}` | "Entity Graph — dormant" | **Active with 5 endpoints.** Prior audit was wrong. |
| `GET /audit_log` | "cross-subsystem coverage missing" | **Already exists** — reuse |
| `GET /shadow/status` | "ModelRegistry — dormant" | **Shadow status already exposed.** Approximate ModelRegistry surface. |
| `GET /provenance` | (missing) | **Active** — attestation trail already exposed |
| `GET /wallets`, `POST /wallets/get_many` | "WalletRegistry — scattered" | **Wallets endpoint exists.** Prior audit wrong. |
| `GET /opportunities`, `/opportunities/{id}` | Slice 1 preview | Real production endpoints exist — Wave-B lift is a direct reuse |
| `GET /discovery_candidates/stats` | Slice 2 preview | Real endpoint exists |
| `GET /analytics/timeseries`, `/analytics/funnel` | (missing) | **Active** — could power future Portfolio → Analytics |
| `GET /release/manifest`, `/release/bundle` | (missing) | **Active** — deployment/backup reference |
| `GET /scanners/{family}/status`, `POST /scanners/{family}/kill|resume`, `PUT /config`, `GET /gate-analysis` | Slice 3 preview | Real endpoints exist per family — direct reuse |

### 1.5 Scanner surface — ground truth

`app/backend/arbicore/scanners/` contains **6 scanner families**, not 8:
- `cex_arbitrage`, `cross_chain_arbitrage`, `dex_arbitrage`,
  `flash_loan_arbitrage`, `funding_arbitrage`, `launch_arbitrage`.
- **NO `spatial_arbitrage` directory. NO `statistical_arbitrage` directory.**

### 1.6 Corrected engine-existence status

| Engine | Prior Wave-1 audit | **File-verified reality** |
|---|---|---|
| **CalibrationRepo (L3-08)** | "Dormant" | **INTERFACE ONLY** — `learning/calibration.py` declares `ConfidenceCalibrator` ABC + `"Not implemented yet"`. No concrete class. |
| **ModelRegistry (L3-09)** | "Dormant" | **No file named ModelRegistry.** Closest analogue is `/shadow/status` endpoint + `shadow.py`. Model-version tracking is implicit via file naming, not a formal registry. |
| **RouteCertifier (L6-09)** | "Dormant" | **ACTIVE** — `certification.py` + `certification_review.py` implement the full shadow-certification state machine (READY / NEEDS_MORE_DATA / NOT_READY). Wave-1 audit was wrong. |
| **Approval Workflow (L4-04)** | "Not Implemented — net-new subsystem" | **ACTIVE** — `services/execution/approval_workflow.py` has PROPOSED → APPROVED → QUOTED → CLOSED state machine with staleness handling. **This is not net-new; it is Reuse.** |
| **Evidence Bundle (L5-08)** | "Not Implemented — net-new" | **ACTIVE** — `certification_evidence.py` assembles the 8-section evidence package. Only the download endpoint + signing bytes are missing. **Refine, not New.** |
| **ComplianceRegistry (L6-08)** | "Not Implemented — net-new" | **Still not implemented.** No sanctions/restricted-list module found. This remains a genuine gap. |
| **Kill-switch (L4-05)** | "Not Implemented / activate" | Interlock arm/disarm exists; no global "kill" endpoint distinct from disarm. Small gap — refinement of `safety_interlock.py`. |
| **Entity Graph (L6-10)** | "Dormant" | **ACTIVE with 5 endpoints** (`/entities/*`). Wave-1 audit was wrong. |
| **Similarity Search (L6-11)** | "Dormant" | **Partially active** via entities/clusters + sequence patterns. No dedicated KNN endpoint. Refine, not New. |
| **WalletRegistry (L6-06)** | "Partially active — Merge" | **ACTIVE** as `services/vault.py` + `wallet_observer.py` + `bdag_transfers.py` + `/wallets` endpoint. Still needs consolidation but is not scattered — three cooperating files. Merge classification stands. |
| **SecretManagement (L6-07)** | "Partially active — Merge" | **Partially confirmed** — env-var + `.env.production.example` present; no dedicated KMS module found. Merge classification stands. |
| **Gas Strategy (L4-07)** | "Partially active — hardcoded" | **Partially confirmed** — no dedicated `gas.py`; gas handling lives inside `bdag_transfers.py` + `fees.py`. Refine classification stands. |
| **Slippage Attribution (L4-06)** | "Dormant" | **Data present in `arbitrage_cycles.py` + `evidence_accuracy.py`**; no aggregate surface. Activate, not New. |
| **GateDropAudit (L3-10)** | "Partial" | **ACTIVE** in `opportunity_gate.py` + scanner `gate-analysis` endpoints. Refine classification stands. |
| **SPATIAL_ARBITRAGE (L2-07)** | "Dormant" | **NOT IMPLEMENTED.** No directory, no code. Cannot be activated — must be built if scope. |
| **STATISTICAL_ARBITRAGE (L2-08)** | "Active (6/h)" | **NOT IMPLEMENTED.** No directory, no code. Wave-1 audit was wrong. |

**Headline correction.** The prior audit identified 3 net-new engines
(Approval Workflow, Evidence Bundle, ComplianceRegistry). File verification
finds that **only 1 of those is actually net-new (ComplianceRegistry).**
The other 2 are already implemented and only need refinement + endpoint
wiring. Two "dormant" engines (SPATIAL + STATISTICAL scanners) don't
exist at all — the prior audit was factually incorrect.

---

## 2 · Scheduler Validation (Task 2)

### 2.1 Canonical scheduler inventory

Grep for scheduler / worker / periodic hooks in the canonical repo
identified the following:

| Scheduler / Worker | Location | Cadence | Owns |
|---|---|---|---|
| **regime_worker** | `arbicore/learning/concrete/regime_worker.py` | continuous | Recomputes market regime; feeds `RegimeDetector` |
| **evaluator_worker** | `arbicore/learning/concrete/evaluator_worker.py` | continuous | General learning evaluator — reads outcomes, updates learning stats |
| **fresh_cycle_watch** | `services/execution/fresh_cycle_watch.py` | short interval | Cycle freshness monitor |
| **drift_runner** | `services/execution/drift_runner.py` | short interval | Price-drift check (freshness gate driver) |
| **wallet_observer** | `services/execution/wallet_observer.py` | short interval | Wallet observation loop |
| **integration_monitor** | `services/execution/integration_monitor.py` | short interval | Integration health rollups |
| **campaign** | `services/execution/campaign.py` | campaign-scoped | Certification campaign lifecycle |
| **approval_workflow** cleanup_stale | `services/execution/approval_workflow.py` | 30 s staleness threshold | Auto-promotes stale approvals |

No `celery`, `apscheduler`, or `crontab` module was found. The workers
appear to be **long-lived asyncio loops or process-run modules**, not a
formal scheduler framework.

### 2.2 Wave-1 scheduler recommendations — corrected home

| Job | Scheduler home |
|---|---|
| Confidence calibration recompute | Extend `evaluator_worker` (existing) — do NOT add a new worker |
| Regime calibration | Already covered by `regime_worker` + `evaluator_worker` |
| DiscoveryScorer calibration | Extend `evaluator_worker` |
| ModelRegistry refresh | New tiny extension of `evaluator_worker` (~ 20 LOC) |

**Ownership.** Learning-worker family (`arbicore/learning/concrete/*_worker.py`)
is owned by the learning layer. Calibration recomputation belongs
there. No new scheduler process is required.

**Dependencies.**
- `evaluator_worker` already depends on `route_success_tracker` and
  `outcome_tracker` — perfect fit for calibration + model-registry
  surfaces.
- `regime_worker` already writes regime snapshots — perfect fit for
  regime history sparkline surface (AI-1).

**Cadence proposal (subject to canonical owner review).**
- Calibration recompute: 1 hour rolling window.
- ModelRegistry snapshot: 5 minutes (mostly a read of already-persisted
  shadow.py state).
- DiscoveryScorer calibration: 6 hours (candidates are lower-volume).

**No new scheduler infrastructure is needed. All Wave-1 activations
live within the existing worker family.**

---

## 3 · Activation Validation Report (Task 3)

For each engine activated in Wave 1:

### 3.1 CalibrationRepo (L3-08) — Activate

- **Reused components:** existing `arbicore/learning/base.py` interface
  vocabulary; existing `evaluator_worker` scheduling substrate;
  existing `route_success_tracker` + `outcome_tracker` outcome feeds.
- **Refinements:** none in canonical repo yet — Wave 1 only exposed a
  preview stub endpoint. Concrete implementation of the calibrator
  behind `learning/calibration.py::ConfidenceCalibrator` remains to
  be written **(this is a genuine gap identified in §1.6)**.
- **Scheduler:** intended home is `evaluator_worker` (§2.2). Not
  scheduled in this pod.
- **Inputs (production):** `(raw_confidence, succeeded)` tuples from
  every settled cycle.
- **Outputs (production):** reliability buckets, Brier, ECE, drift
  flag; consumed by Intelligence → Calibration UI panel (added this
  turn).
- **Downstream consumers:** UI panel (new); future gate that requires
  ECE < threshold before allowing shadow → active promotion.
- **Operational metrics:** Brier score (target < 0.10), ECE
  (target < 0.05), sample count, drift flag.
- **Validation evidence in this pod:**
  - Endpoint returns 200 with correct shape (`test_v2_wave1.py::TestCalibration`).
  - UI panel renders reliability diagram + drift status; screenshot
    verified.
  - Brier and ECE are within calibrated-model bounds in fixture data.

### 3.2 ModelRegistry (L3-09) — Activate

- **Reused components:** `services/execution/shadow.py` shadow-execution
  layer (proxy for shadow-model surface); `certification_evidence.py`
  for promotion evidence patterns; existing `/shadow/status` endpoint
  as behavioural precedent.
- **Refinements:** the preview endpoint mirrors what `shadow.py` +
  file-naming already implies. Formal `ModelRegistry` class is still
  absent — again a **genuine gap**.
- **Scheduler:** `evaluator_worker` extension (5-minute cadence).
- **Inputs (production):** shadow.py state (per-run manifests),
  certification_review outcomes.
- **Outputs (production):** active + shadow model list, promotion
  history (already implicit in the certification campaign log —
  reuse `campaign.py`).
- **Downstream consumers:** UI panel; audit trail for every decision
  (via decision-log `model_version` field, Wave-1 refinement).
- **Operational metrics:** number of active models, number of shadow
  models, days since last promotion, per-model eval Brier + ECE.
- **Validation evidence:** endpoint tests green; UI panel renders 4
  models + 3 promotions; screenshot verified.

### 3.3 DecisionAuditLog versioning (L3-07) — Refine

- **Reused components:** existing `learning/concrete/audit_log.py`
  (verified in canonical).
- **Refinements:** additive `model_version` + `policy_version` on every
  entry.
- **Scheduler:** N/A — write path.
- **Inputs / outputs / consumers:** unchanged except for the two new
  fields.
- **Operational metrics:** % of decisions with version stamp
  (target 100% after canonical refinement).
- **Validation evidence:** Wave-1 tests
  `TestDecisionVersioning::test_versions_present` +
  `test_shadow_model_flagged` — both green.

### 3.4 DiscoveryScorer calibration (DSC-02) — Refine

- **Reused components:** existing `arbicore/scanners/discovery/*` +
  `services/discovery.py`.
- **Refinements:** additive `calibration` block on
  `/discovery/candidates` response.
- **Scheduler:** `evaluator_worker` extension (6-hour cadence).
- **Inputs / outputs / consumers:** unchanged except additive block.
- **Operational metrics:** top-decile vs bottom-decile promotion rate,
  ECE, drift flag.
- **Validation evidence:** `TestDiscoveryCalibration::test_calibration_block`
  green; sanity check top-decile > bottom-decile passes.

### 3.5 Wave-1 UI addition (this turn) — Activate

- **Reused components:** `v2Api.calibration` + `v2Api.models` from
  Wave-1 Phase; existing `IntelligencePage` sub-nav pattern; existing
  design tokens; `fmtPct` from Primitives.
- **Refinements:** two new sub-tabs (`Calibration`, `Models`) added
  to the existing `IntelligencePage` sub-nav registry (`SUB_SECTIONS`).
- **Scheduler:** N/A — read-only UI.
- **Inputs:** `/intelligence/calibration` + `/intelligence/models`.
- **Outputs:** rendered panels — reliability diagram, model registry
  table, promotion history.
- **Downstream consumers:** operator + auditor observation.
- **Operational metrics:** N/A (UI panel only).
- **Validation evidence:**
  - Playwright screenshot of `/v2/intelligence/calibration` — 10-bucket
    reliability diagram, Brier 0.0008, ECE 0.0263, drift status **OK**.
  - Playwright screenshot of `/v2/intelligence/models` — 4 model rows
    (3 ACTIVE + 1 SHADOW), 3 promotion rows.
  - Full test suite 70/70 pass — no backend regression.
  - ESLint clean.

---

## 4 · What this means for Wave 2

Wave 2 was scoped as: activate SPATIAL_ARBITRAGE + RouteCertifier + close
loop LE-10.

Corrected picture after canonical verification:

| Item | Original Wave-2 verdict | Corrected verdict |
|---|---|---|
| **SPATIAL_ARBITRAGE activation** | Activate dormant scanner | **Cannot be activated — no code exists.** Would need net-new scanner (~ 1 dev-week). Recommend **defer** until operator case is proven; do not put a preview stub in production. |
| **RouteCertifier activation** | Activate dormant engine | **Already active** as `certification.py` + `certification_review.py`. Wave-2 work is *surface exposure*, not activation. Recommend **Refine + expose** (add `/intelligence/certification` endpoint reading from `certification_review.review()`; feed Intelligence → Certification & Evidence sub-tab, which currently shows a Slice-4 placeholder). |
| **Close loop LE-10** | Dormant loop | Loop is closed inside `certification.py` reading `route_success_tracker` outcomes. Only the UI-facing surface is missing. |

**Also worth confirming with the operator before Wave 2:**
- Approval Workflow is not a Phase-E build — it's a Phase-B/C exposure of
  the existing `approval_workflow.py`. Refined roadmap (`10_…`) Phase E
  can be shortened to "wire existing approval_workflow.py through the
  UI + add threshold policy config".
- Evidence Bundle is not Phase-F net-new build — it's a signing + endpoint
  wrapping of `certification_evidence.py`. Also much smaller.
- Only ComplianceRegistry (L6-08) and (probably) a formal
  ConfidenceCalibrator concrete implementation are **genuinely net-new**.

### 4.1 Recommended Wave-2 scope (revised)

1. **Expose RouteCertifier** — add
   `GET /api/arbicore/intelligence/certification` preview endpoint mirroring
   `certification_review.review()` shape; wire Intelligence →
   Certification & Evidence sub-tab (currently a Slice-4 placeholder)
   as a read-only reference panel, consistent with the pattern used for
   Calibration + Models this turn.
2. **Expose the existing entity graph** — add
   `GET /api/arbicore/intelligence/entities` preview endpoint mirroring
   `/entities/scores/top`; wire a small Knowledge preview panel.
3. **Do NOT activate SPATIAL_ARBITRAGE** unless operator explicitly
   authorises a net-new scanner build. Recommend downgrading the audit
   entry to `Missing capability — new build` and dropping it from
   Wave-2 scope.
4. **Close LE-10** by exposing `certification_review.review()` — same
   endpoint as (1).

---

## 5 · Files touched this turn (UI panels + report)

- `frontend/src/v2/pages/IntelligencePage.jsx` — added `Calibration` + `Models`
  read-only panels (~ 150 LOC additive), extended `SUB_SECTIONS` array,
  added two `<Route>` entries. No existing component removed.
- `docs/ui_v2/13_WAVE1_VERIFICATION_REPORT.md` — this document.

No backend change. No new dependency. No UI contract broken. ESLint
clean. Full test suite still 70/70 pass.

---

## 6 · Deliverable status

- [x] Task 1 · Canonical verification against extracted v1.0.2 bundle.
- [x] Task 2 · Scheduler location + ownership + cadence + dependencies
      documented (§2).
- [x] Task 3 · Activation Validation Report — 5 rows populated (§3).
- [x] Bonus · UI panels for Calibration + Models added per read-only
      request. Screenshots verified.
- [x] Wave-2 scope re-assessed against verified reality (§4).
- [ ] Operator decision needed: Wave-2 scope revision (see §4.1).

**Rules observed.** No production integration. No LLM. No new business
logic. No workflow changes. Every UI addition is a read-only reference
panel reusing v2 design language. Existing contracts intact.
