# ArbiCore X — Wave 2 · Expose File-Verified Canonical Engines · Deliverable

**Generated:** 2026-07-31
**Wave:** 2 of 7 (revised scope per Wave-1 verification report)
**Objective:** Expose two file-verified canonical engines (RouteCertifier
via `certification_review.py`, Entity Graph via `/entities` endpoints)
as read-only reference panels; close learning loop LE-10. No new business
logic, no workflow changes, no production integration.

**Engineering priority order applied (revised, Wave-1 §4):**
Verify → Reuse → Refine → Expose → Activate → Merge → New.

---

## 1 · What was done this wave

### 1.1 Backend preview endpoints

| Endpoint | Reused canonical | Action | Notes |
|---|---|---|---|
| `GET /api/arbicore/intelligence/certification` | `services/execution/certification_review.py::latest_review()` | **Reuse + Expose** | Shape mirrors canonical response 1:1 — same field names, same `sections[].{title,verdict,evidence[]}` shape, same `readiness_criteria` keys, same `recommendation` vocabulary (READY_FOR_MICROCAPITAL_REVIEW / NEEDS_MORE_DATA / NOT_READY) |
| `GET /api/arbicore/intelligence/entities` | `arbicore/routes/arbicore.py::list_entities()` + `top_entity_scores()` (composed) | **Reuse + Expose (composed)** | Composed shape matches `/entities` list + `top()` score; carries the frozen `EntityType` vocabulary as `vocabulary[]` |

Both endpoints live in `backend/server.py` alongside their inline mapping
to production sources. Zero business logic added; the stubs just serve
representative shapes so the UI can be built and the future canonical
lift becomes a one-line handler swap.

### 1.2 v2Api client (frontend)

Additive only:
- `v2Api.certification()`
- `v2Api.entities(params)`

### 1.3 UI panels (Intelligence page)

Two placeholders previously reserved for later slices are now backed by
real read-only panels:

- **Intelligence → Certification & Evidence** — Shadow Certification
  Review panel:
  - Recommendation chip color-coded per verdict (GO/soft-NO/hard-NO).
  - 6 metric tiles (Total cycles · Completion% · Stuck% · Recovery% ·
    Avg realised · Safe cycle size).
  - Readiness sections table with per-metric evidence (`metric · value
    vs threshold · status`).
  - Next-steps list (from canonical `next_steps` field).
  - Mandatory read-only safety note reproduced verbatim.
- **Intelligence → Knowledge** — Entity Graph panel:
  - Total + per-type counters (SMART_MONEY, MARKET_MAKER,
    EXCHANGE_WALLET, LIQUIDITY_PROVIDER, LAUNCH_PARTICIPANT,
    CEX_ACCOUNT, DEX_POOL, WALLET, UNKNOWN).
  - Type filter chip row (frozen vocabulary).
  - Rank table (label, type-tag, score%, samples, notable extras).

Both panels reuse the existing v2 patterns established in earlier
slices — same `CARD` / `TABLE` / `TH` / `TD` primitives, same
`StateTag` component, same design tokens.

### 1.4 Documentation corrections (docs 10 + 11)

The prior audit contained multiple assumptions that file verification
proved wrong. Corrections applied **in place** so downstream readers
never see conflicting documentation:

- `docs/ui_v2/10_REFINED_ROADMAP.md` §0 — CORRECTION callout added.
- `docs/ui_v2/10_REFINED_ROADMAP.md` Phase E — retitled and rescoped
  from "the one new subsystem" to "expose + refine".
- `docs/ui_v2/10_REFINED_ROADMAP.md` Phase F — retitled and rescoped
  from "net-new build" to "wrap existing evidence bundler + build the
  two genuinely absent capabilities".
- `docs/ui_v2/11_ENGINE_ACTIVATION_AUDIT.md` §0 — confidence note
  updated to "file-verified".
- `docs/ui_v2/11_…` row updates:
  - **CalibrationRepo (L3-08)** — Dormant → **Interface only**.
  - **ModelRegistry (L3-09)** — Dormant → **Partially Active as
    `/shadow/status`**.
  - **GateDropAudit (L3-10)** — corrected to fully active with
    scanner `/gate-analysis`.
  - **Approval Workflow (L4-04)** — Not Implemented → **Active**
    (Reuse, not New).
  - **Kill-Switch (L4-05)** — Not Implemented → **Partially Active**
    (Refine, not New).
  - **Evidence Bundle (L5-08)** — Not Implemented → **Active as
    assembler** (Refine, not New).
  - **RouteCertifier (L6-09)** — Dormant → **Active** (Refine +
    Expose).
  - **Entity Graph (L6-10)** — Dormant → **Active with 5 canonical
    endpoints** (Refine + Expose).
  - **Similarity Search (L6-11)** — Dormant → **Partially Active**.
  - **WalletRegistry (L6-06)** — clarified as three cooperating files
    (`services/vault.py`, `services/execution/wallet_observer.py`,
    `bdag_transfers.py`, `/wallets` endpoint) — Merge classification
    stands.
  - **SPATIAL_ARBITRAGE (L2-07)** — Dormant → **Not Implemented**
    (previous "Activate" reclassified as deferred New build).
  - **STATISTICAL_ARBITRAGE (L2-08)** — Active 6/h → **Not
    Implemented** (previous "Active" was fixture-only; there is no
    canonical scanner).
- `docs/ui_v2/11_…` §5 counts — updated to reflect the corrected
  reality (2 genuine New engines + 2 deferred New scanners, down
  from 3 claimed).
- `docs/ui_v2/11_…` §7 gaps — reworked to distinguish "genuinely
  net-new" (concrete ConfidenceCalibrator + ComplianceRegistry) from
  "exposure / refinement of existing engines" (Approval, Evidence,
  RouteCertifier, EntityGraph, SimilaritySearch, Kill-switch).

---

## 2 · Reuse / Refine / Expose / Activate / Merge / New tally

| Action | Count | Items |
|---|---|---|
| **Verify** | 12 | Row-by-row canonical grep against `/tmp/canonical_extract` for every previously-inferred engine |
| **Reuse** | 4 | `certification_review.latest_review()`, `list_entities()`, `top_entity_scores()`, `EntityType` enum (as UI vocabulary) |
| **Refine** | 0 | (this wave is exposure-only; no shape refinement of existing endpoints) |
| **Expose** | 2 | Certification review panel, Entity Graph panel |
| **Activate** | 1 | LE-10 (RouteCertifier learning loop) — closed by exposure |
| **Merge** | 0 | — |
| **New** | 0 | — |

**Zero net-new engines, zero refactors, zero workflow changes, 100%
contract-preserving.** Wave-2 objective achieved.

---

## 3 · Learning-loop status after Wave 2

| # | Loop | Wave-1 state | Wave-2 state |
|---|---|---|---|
| LE-1 | Route success | Closed (continuous) | Closed (continuous) |
| LE-2 | ConfidenceScorer weights | Observable via calibration surface | Observable |
| LE-3 | SafetyScorer thresholds | Partial | Partial |
| LE-4 | RegimeDetector distributions | Partial | Partial |
| LE-5 | DecisionAuditLog | Read-only + version-stamped | Read-only + version-stamped |
| LE-6 | CalibrationRepo | **Observable (endpoint)** | Observable + **UI panel** |
| LE-7 | ModelRegistry meta-loop | **Observable (endpoint)** | Observable + **UI panel** |
| LE-8 | STATISTICAL_ARBITRAGE stats | Closed (internal) — **corrected: scanner does not exist** | Marked Not Implemented; loop retired |
| LE-9 | DiscoveryScorer calibration | Observable | Observable |
| LE-10 | RouteCertifier | Still dormant | **Observable + UI panel — LOOP CLOSED** |

**Wave-2 delta.** LE-10 moved from Dormant → **Observable UI-side**
via the existing canonical `certification_review.latest_review()`
implementation. Combined with the Wave-1 activations, the observable
learning-loop count is now **5** (LE-1, LE-6, LE-7, LE-9, LE-10) plus
2 version-traceable loops (LE-2, LE-5).

---

## 4 · Before vs After UI surface area

Before Wave 2, Intelligence had:
- 2 live sub-tabs (Recommendations, Confidence).
- 2 Wave-1 sub-tabs (Calibration, Models).
- 5 "scheduled for Slice X" placeholders.

After Wave 2:
- 4 live sub-tabs (unchanged from Wave 1).
- **2 additional live sub-tabs** (Certification & Evidence, Knowledge).
- 3 remaining "scheduled for Slice X" placeholders (Analytics, Market,
  Learning) — these have real canonical counterparts too (`analytics/timeseries`,
  narrative feeds, `weights/current`) and will be exposed similarly in
  future waves.

Existing UI contracts intact. No route removed. No component renamed.

---

## 5 · Tests executed

- `backend/tests/test_v2_wave2.py` — **7/7 pass** (new).
  - `TestCertification::test_get` — verifies every top-level and nested
    field in the canonical shape (phase, available, recommendation,
    campaign block, summary block with 17 fields, readiness_criteria
    block, sections shape).
  - `TestCertification::test_safety_note_present` — asserts the
    read-only safety note is preserved verbatim.
  - `TestEntities::test_get` — verifies frozen EntityType vocabulary,
    entity row shape, bounded score.
  - `TestEntities::test_filter_by_type` — verifies `?entity_type=`
    filter.
  - `TestEntities::test_counts_by_type` — verifies count parity with
    total_entities.
  - `TestBackwardsCompat::test_wave1_still_works` — asserts
    calibration, models, decisions endpoints unaffected.
  - `TestBackwardsCompat::test_slice0_pulse_still_works` — asserts
    Slice-0 pulse unaffected.
- **Full backend suite: 77/77 pass** (70 pre-existing + 7 new Wave-2).
- ESLint clean.
- Playwright screenshots verified both new panels render correctly:
  - Certification: `NEEDS_MORE_DATA` chip, 6 metric tiles, readiness
    sections table with PASS/FAIL/INFO tags per row, evidence
    breakdown per row, next-steps block, safety note footer.
  - Entities: 10 entities across 8 EntityType values, type filter
    chip row, rank table with score coloring for ≥ 80%.

---

## 6 · Measurable improvements (Wave 1 → Wave 2)

| Metric | Wave 1 | Wave 2 | Delta |
|---|---|---|---|
| UI-consumable learning surfaces | 3 endpoints | **5 endpoints** | +2 |
| Live Intelligence sub-tabs | 4 | **6** | +2 |
| Learning loops with UI surface | 3 (LE-6, LE-7, LE-9) | **5 (+LE-1, LE-10)** | +2 |
| Slice-4 / Slice-5 placeholders remaining | 5 | 3 | −2 |
| Contract tests on Intelligence surface | 12 | **19** | +7 |
| Canonical engines exposed via UI | 6 | **8** | +2 |
| Docs with corrected canonical-verified content | 1 (`13_…`) | **3** (`10_`, `11_`, `13_`) | +2 |
| Existing UI contracts broken | 0 | **0** | — |
| Net-new business logic added | 0 | **0** | — |

---

## 7 · Files touched this wave

- `backend/server.py` — 2 new preview endpoints (`certification`, `entities`),
  ~ 120 additive LOC. Inline production-source mapping documented in
  the section header.
- `frontend/src/v2/lib/api.js` — 2 thin wrappers (`certification`, `entities`).
- `frontend/src/v2/pages/IntelligencePage.jsx` — 2 new components
  (`Certification`, `Entities`), 2 route bindings replacing placeholders,
  1 sub-nav registry update (slice labels changed from `4`/`5` to `W2`),
  ~ 200 additive LOC. Existing components untouched.
- `backend/tests/test_v2_wave2.py` — 7 new contract tests.
- `docs/ui_v2/10_REFINED_ROADMAP.md` — CORRECTION callout in §0, Phase E
  + Phase F headers + first paragraphs updated.
- `docs/ui_v2/11_ENGINE_ACTIVATION_AUDIT.md` — confidence note, 11 row
  updates (L2-07, L2-08, L3-08, L3-09, L3-10, L4-04, L4-05, L4-06, L5-08,
  L6-06, L6-07, L6-09, L6-10, L6-11), §5 counts, §7 gaps.
- `docs/ui_v2/14_WAVE2_DELIVERABLE.md` — this document.

No other files modified. No env change. No dependency added. No
supervisor / build config change.

---

## 8 · Wave-3 setup (for user's stated priority)

Wave 3 (approved priority): implement the **concrete
`ConfidenceCalibrator`** behind
`learning/calibration.py::ConfidenceCalibrator` so the Wave-1
calibration endpoint becomes production-backed.

**Preparation this wave puts in place:**
- Endpoint shape is frozen and contract-tested
  (`test_v2_wave1.py::TestCalibration`).
- UI panel already renders the shape correctly (verified visually).
- The interface exists (`learning/calibration.py::ConfidenceCalibrator`
  ABC) and only needs a concrete subclass computing:
  - `n_samples` per confidence bucket
  - `predicted` bucket midpoint (or mean of predicted values in bucket)
  - `realised` positive-outcome rate in bucket
  - `brier_score` and `ece` scalar aggregates
  - `drift_alert` boolean threshold check.
- The scheduler home is `evaluator_worker` (per Wave-1 §5).

Nothing else in Wave 3 requires backend or UI work — pure
implementation of the ABC.

---

## 9 · Remaining blockers

None for Wave 2 itself. For Wave 3 to begin:

- **B-1** Confirm which persistence layer to use for calibration
  histograms — reuse `services/db.py` collections or add a new
  `calibration_buckets` collection.
- **B-2** Confirm rolling-window definition (30 days recommended in
  Wave-1 stub).
- **B-3** Confirm cadence (1 hour recommended in Wave-1 §5).

---

## 10 · Rules observed

- **Verify** → done against extracted canonical bundle.
- **Reuse** → both endpoints wrap existing canonical implementations.
- **Refine** → not required this wave (exposure only).
- **Expose** → 2 new UI panels + 2 new preview endpoints.
- **Activate** → LE-10 loop closed via exposure.
- **Merge** → not required this wave.
- **New** → **zero net-new engines**.

No LLM introduced. No production integration performed. No SPATIAL /
STATISTICAL scanner built (deferred per user direction). No workflow
change. Read-only observability only.
