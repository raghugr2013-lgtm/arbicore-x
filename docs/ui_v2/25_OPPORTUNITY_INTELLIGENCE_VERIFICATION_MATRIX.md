# Opportunity Intelligence · Capability Verification Matrix

**Audit date:** 2026-08-01
**Scope:** Continuous Opportunity Discovery → Ranking → Scoring → Certification → Execution Queue → Lifecycle → History → Memory → Learning/Calibration/Adaptive Weights → Execution Timeline + UI surfaces.
**Method:** Direct file inspection of the two source trees (running `/app/backend` + canonical bundle at `/tmp/cx/repo`).
**No code was modified.**

**Classification legend:**

- ✅ **Present & production-ready** — verified in the running backend.
- 🟡 **Present but needs refinement** — file exists, minor gaps.
- 🟠 **Dormant** — implemented in the canonical bundle but **not** imported/wired in `/app/backend`.
- 🔵 **Existing UI surface already built** — v2 page already ships with data-test-ids and API bindings.
- 🔴 **Genuinely missing** — no implementation anywhere; justification required to build new.

---

## 0 · Headline finding

**Ninety-plus percent of the Opportunity Intelligence pipeline already exists.** The canonical bundle carries a *complete, integrated* pipeline — from provenance-typed discovery candidates through category-agnostic emission, canonical opportunity persistence, lifecycle FSM, learning-eligibility gating, five-horizon outcome tracking, provenance-graded state observation, entity resolution, calibration, adaptive weights, audit log, and route-scoped confidence store. It is wired through an `EmissionBus` (`arbicore/emission_bus.py`) that every family scanner (CEX, DEX, funding, cross-chain, launch, flash-loan) already uses. The `arbicore/runtime/composition.py` (1204 LOC) is the orchestrator that ties it together.

**None of this canonical machinery is currently imported into `/app/backend`.** Instead, `/app/backend/server.py` carries **its own hand-rolled stubs** for `/api/arbicore/opportunities`, `/api/arbicore/discovery/candidates`, `/api/arbicore/intelligence/{recommendations, decisions, calibration, models, certification, entities}` (see server.py lines 414, 484, 548, 594, 620, 682, 739, 779, 849). These stubs are what the already-built v2 UI pages (`OpportunitiesPage.jsx`, `DiscoveryPage.jsx`, `IntelligencePage.jsx`) consume today.

**Consequence:** Almost every gap identified in prior audits can be closed by **ACTIVATION** of the canonical modules, not by writing new code. The v2 UI already exists too — it just needs to be pointed at the same shapes the canonical pipeline emits.

---

## 1 · Capability Verification Matrix

| Capability | Status | Canonical file(s) | Current running impl | Classification | Remaining gap |
|---|:-:|---|---|:-:|---|
| **Continuous Opportunity Discovery** | 🟠 | `arbicore/scanners/{cex,dex,funding,cross_chain,launch,flash_loan}_arbitrage/scanner.py` (~5-7 KLOC total); `arbicore/scanners/discovery_source.py`; `arbicore/scanners/http_retry.py`; `arbicore/runtime/composition.py` (`start_evaluator`, `start_scanner` for each family, lines 759-1120) | Wave 7A `arbicore/execution/discovery.py` — a **thin activator** with one hard-coded WETH/USDC universe on Base. Runs, but is a stand-in. | **ACTIVATE** the canonical scanner tree (6 families) via `runtime/composition.py`; retire the Wave-7A thin activator. | Zero net-new code; import + wire dependencies (emission_bus, discovery_queue, outcome_repo, entity_resolver, audit_log). Deployment-time env config for source credentials. |
| **Opportunity Ranking** | 🟡 | Ranking is expressed as *ordered filters* per family (e.g. `arbicore/scanners/flash_loan_arbitrage/filter.py` — Gates 7 / 8 / 9). `arbicore/routes/arbicore.py` L171 `/outcomes` returns rows sortable by realised profit. Server stub at `server.py:414` returns `verdict` + `confidence` + `spread_bps` + `depth_usd` + `return_low/high` (already the ranking primitives). | Stub emits per-item ranking fields but no composite score ordering endpoint. | **REFINE** — add a single ordering param (`sort_by=confidence|spread|depth|freshness`) to `/api/arbicore/opportunities` once the canonical `EmissionBus` is wired. | Composite ranking function is already present (canonical `intelligence/scoring.py::ScoringEngine.score()` — see next row). |
| **Opportunity Scoring** | ✅ (canonical) / 🟠 (running) | `arbicore/intelligence/scoring.py::ScoringEngine` (120 LOC) — deterministic `spread × persistence × liquidity / (gas × mev)` with injectable weights. `arbicore/intelligence/confidence.py::SignalConfidenceEngine` — route-scoped confidence store. `arbicore/intelligence/roi_probability.py::ROIProbabilityEngine`. | The scoring math is not being consumed by the running `/api/arbicore/opportunities` stub. Wave 3-4 already wired the *calibrator* and *adaptive-weights observer* but not the primary scoring engine. | **ACTIVATE** the `ScoringEngine` + `SignalConfidenceEngine` + `ROIProbabilityEngine`; wire them into the running EmissionBus per family. | Zero new code. |
| **Opportunity Certification** | ✅ | `server.py:779` `/api/arbicore/intelligence/certification` (Shadow-certification review). `arbicore/execution/certification.py::ExecutionCertifier` (Wave 6E — 11-stage deterministic per-plan certification). | Both are live. The Intelligence-page `Certification` component (see `IntelligencePage.jsx` L226-311) already reads the shadow-cert review. The Flash-Loan page reads the execution-cert per plan. | **PRESENT** — nothing new needed. | Only tightening: cross-link the per-opportunity certification result into `/api/arbicore/opportunities/{id}` payloads. |
| **Execution Queue** | 🟡 (partial) | `arbicore/data/discovery_queue.py::DiscoveryQueue` (183 LOC) — Mongo-backed cooperative claim queue with idempotency, claim TTL, worker lock, TTL-expiring rows. **This is the queue.** `arbicore/execution/planner.py::ExecutionPlansRepo` persists plans, but there is no explicit ready-to-execute ordering yet. | `db.execution_plans` collection exists (Wave 6B). No claim/lock/worker semantics. | **REUSE** canonical `DiscoveryQueue` pattern (it's category-agnostic despite the name) to add an `ExecutionQueue` view over `db.execution_plans` — 1-file refinement OR **MERGE** semantics onto the existing plans repo. | The pattern is proven; the concrete `ExecutionQueue` on plans is a small refinement, not a new capability. |
| **Opportunity Lifecycle** | ✅ (canonical, dormant) | `arbicore/models/canonical.py::CanonicalOpportunity` — full lifecycle FSM `CANDIDATE → VALIDATED → APPROVED → EXECUTED → COMPLETED` (plus `REJECTED`) with `_ALLOWED_TRANSITIONS` guard, `InvalidTransitionError`, `can_transition()`, `mark_validated()`, `mark_approved()`, `mark_rejected(reason)`. `arbicore/models/enums.py::OpportunityStatus`. | Server stub emits a `status` string per item (`server.py:414`) but there is no state-machine enforcement path in the running backend. `arbicore/opportunities/{id}/{approve,reject}` endpoints (server.py 484, 493) mutate the row but don't consult the FSM. | **ACTIVATE** `CanonicalOpportunity`; route approve/reject through `_transition()`. **REUSE** verbatim. | The FSM already exists — the running endpoints just need to route through it. |
| **Opportunity History** | ✅ (canonical) / 🟠 (running) | `arbicore/data/mongo/opportunity_repo_mongo.py` — persistent opportunity store keyed on `opportunity_id`. `arbicore/data/outcome_repo.py::OutcomeRepository` — 5-horizon outcome rows. `arbicore/learning/concrete/outcome_tracker.py::OutcomeTracker`. `arbicore/routes/arbicore.py:171` `/outcomes` endpoint. | `db.arbicore_opportunities` collection is not created because the canonical repo isn't imported. The Wave-7A thin activator writes to a *different* collection (`db.opportunities`). | **ACTIVATE** the canonical Mongo repo (7 file group under `arbicore/data/mongo/`). Migrate the Wave-7A `db.opportunities` rows into the canonical `arbicore_opportunities` collection at activation. | No new persistence code. |
| **Opportunity Memory** | ✅ (canonical) / 🟠 (running) | Two layers: (a) **route-scoped**: `arbicore/intelligence/confidence.py::InMemoryConfidenceStore` + `RouteStats` — rolling win/trials/mean-ROI per route (survival subject_id). (b) **entity-scoped**: `arbicore/intel/{resolver,scorer,cluster_detector,entity_repo}.py` — universal cross-family entity graph with `EntityScorer.top()` (used by the Intelligence-page `Entities` component). | Neither is imported. Server stub returns hand-written mock entities. | **ACTIVATE** the entire `arbicore/intel/*` package (~1200 LOC) alongside the intelligence tree; wire `EntityResolver` into the EmissionBus (it's the fourth downstream tap in `emission_bus.py` L112). | Zero new code. |
| **Learning integration** | ✅ (running for calibration + weights only) | `arbicore/learning/concrete/{outcome_tracker,audit_log,survival,regime_worker,regime_classifier}.py`. Provenance gate: `arbicore/data/provenance.py::is_learning_eligible` — only VERIFIED_REAL and REAL data reach learning. | Waves 3-4 activated the calibrator + adaptive-weights observer over a **manual** feed. The canonical `OutcomeTracker` (that ingests 5 outcome horizons from real emissions) is not wired. | **ACTIVATE** `OutcomeTracker` + `provenance.is_learning_eligible` in the EmissionBus. The Wave-3 calibrator + Wave-4 weights are already listening — they just need the OutcomeTracker to produce the rows. | Zero new code. |
| **Calibration integration** | ✅ (running) | Wave 3 · `arbicore/learning/concrete/calibrator_isotonic.py` + `calibration_worker.py`. Canonical `arbicore/data/mongo/calibration_models_repo.py`. Frontend surface at `IntelligencePage.jsx::Calibration` component reads `/api/arbicore/intelligence/calibration`. | Both endpoints (`/calibration`, `/calibration/status`, `/calibration/history`) are live at server.py 682, 1410, 1416. UI reads the reliability diagram + Brier + ECE + drift alert. | **PRESENT** — nothing new needed. | Once real outcomes flow (see Learning row above), the calibrator will start filling with real data instead of the current bootstrap. |
| **Adaptive Weights integration** | ✅ (running, OBSERVE mode) | Wave 4 · `arbicore/learning/concrete/adaptive_weights_observer.py` + `adaptive_weights_worker.py`. Canonical `arbicore/data/mongo/adaptive_weights_repo.py`. Endpoints at server.py 1432, 1473, 1507, 1513. | OBSERVE mode is deliberate — weights recommendations are computed but not applied. Frontend has no dedicated component; the sub-nav slot on IntelligencePage (`Models`) hosts adjacent info. | **PRESENT** in OBSERVE. To flip to ACTIVE: swap the router that reads weights from the identity baseline to the observed baseline. | Documented as a follow-on refinement — not a gap. |
| **Execution Timeline** | 🟠 (partial) | Canonical `arbicore/shadow/observer.py::ShadowBindingObserver` (per-cycle timeline for shadow trades). `arbicore/data/outcome_repo.py::StateRow` — per-emission state snapshot with `captured_at_ts`. Wave 6D `kill_switch_audit`, `execution_mode_audit`, Wave 6B `execution_plans` all already carry timestamps. | No consolidated "timeline" endpoint exists in the running backend. Individual audit endpoints do (kill-switch/audit, mode/history, weights/history, calibration/history). | **MERGE + EXPOSE** — Read-only aggregator that fans across the existing audit collections (`execution_mode_audit`, `capital_policy_audit`, `kill_switch_audit`, `execution_plans`, `evidence_bundles`, `arbicore_outcome_rows`, `arbicore_state_snapshots`) and emits one unified `/api/arbicore/execution/timeline?opportunity_id=…` feed. | The collections already exist — this is a **join view**, not a new persistence layer. |
| **UI surface — Opportunities** | 🔵 | Frontend: `/app/frontend/src/v2/pages/OpportunitiesPage.jsx` (223 LOC) — filter chips (family/verdict/chain/min-conf), dense table with 10 columns, keyboard-driven `↑↓` `Enter` `A` `R`, deep-link `?id=`, drawer via `OpportunityDrawer` component. | Fully built; already binds to `/api/arbicore/opportunities` + approve/reject endpoints. Data-testids present on every row. | **PRESENT** — no UI work. | Backend must return the canonical shape once the canonical repo is activated. |
| **UI surface — Discovery** | 🔵 | Frontend: `/app/frontend/src/v2/pages/DiscoveryPage.jsx` (219 LOC) — two-pane inbox (list left / detail right), status/kind chips, `MetricStat` header cards for `total/new/watching/promoted/dismissed`, action buttons `WATCH` / `PROMOTE` / `DISMISS`. | Fully built; binds to `/api/arbicore/discovery/candidates` and `/api/arbicore/discovery/candidates/{id}/action`. | **PRESENT** — no UI work. | Backend needs to return the canonical `DiscoveryCandidate` shape (from `arbicore/models/discovery.py`). |
| **UI surface — Intelligence (Recommendations / Confidence / Calibration / Models / Certification / Entities)** | 🔵 | Frontend: `/app/frontend/src/v2/pages/IntelligencePage.jsx` (573 LOC) — sub-rail with 9 sections, four are fully wired (Recommendations, Confidence, Calibration, Models, Certification, Entities). Analytics, Market, Learning show scheduled-slice placeholders. | Fully built. Data-testids on every table cell. | **PRESENT** — no UI work for the six activated sub-tabs. | Once canonical scoring/confidence engines are activated, the same components will show real data instead of bootstrap. |
| **UI surface — Flash Loan Operator** | 🔵 | Phase 7B `/app/frontend/src/v2/pages/FlashLoanOperatorPage.jsx` — end-to-end operator workflow (Kill Switch banner + Wallets + Secrets + Health + Mode + Discovery + Cert & Broadcast). | Live. | **PRESENT.** | No UI work. |
| **UI surface — Certification & Evidence timeline** | 🔴 (dedicated view) / 🔵 (partial) | The `Certification` component on `IntelligencePage.jsx` (L226-311) already shows the shadow-certification review. There is **no dedicated timeline view** joining evidence bundles + certification reports + execution audits into a single scrollable trail per opportunity. | Individual audit endpoints exist; no timeline. | **MERGE + NEW UI** — add a per-opportunity Timeline component (~150 LOC) once the backend timeline endpoint (§Execution Timeline row) ships. | The only genuinely new UI surface in this audit — and only ~150 LOC. |

---

## 2 · Reuse / Refine / Activate / Merge / Expose / New — summary

| Action | Modules | Count |
|---|---|:-:|
| ✅ **Present & production-ready** (no work) | Certification (Wave 6E · Shadow-cert · Flash-loan cert), Calibration integration, Adaptive Weights integration (OBSERVE) | 3 |
| 🔄 **REUSE** (verbatim, no changes) | Discovery queue pattern (`DiscoveryQueue`), Confidence store + RouteStats, Scoring engine, Provenance gate, Emission bus, `OutcomeRepository` / `OutcomeTracker`, `EntityResolver` / `EntityScorer`, `CanonicalOpportunity` FSM | 8 |
| 🔧 **REFINE** (minor edits) | Opportunity Ranking (add sort_by), Execution Queue (add claim view over `execution_plans`), migrate Wave-7A `db.opportunities` rows into canonical `arbicore_opportunities` at activation | 3 |
| 🚀 **ACTIVATE** (import + wire, zero net-new code) | Continuous Discovery (6 family scanners); Opportunity Scoring pipeline (`ScoringEngine`, `SignalConfidenceEngine`, `ROIProbabilityEngine`); Opportunity History (Mongo repo family); Opportunity Memory (Entity graph, InMemoryConfidenceStore); Learning integration (OutcomeTracker in EmissionBus); Lifecycle FSM enforcement on approve/reject | 6 |
| 🔗 **MERGE + EXPOSE** (aggregation only, no new persistence) | Execution Timeline (join view across 7 existing audit collections) | 1 |
| 🖥️ **Existing UI surfaces already built** (no UI work) | OpportunitiesPage, DiscoveryPage, IntelligencePage (6 sub-tabs), FlashLoanOperatorPage | 4 pages, 10+ sub-views |
| 🆕 **New code** (justified only where truly absent) | Per-opportunity Timeline view (~150 LOC React) — depends on the merge-expose endpoint above | 1 |

**Total new-code footprint required to complete Opportunity Intelligence:** approximately **150 LOC of new React** + **≈ 200 LOC of aggregation glue in `server.py`**. Every substantive engine, repo, model, and scanner **already exists in the canonical tree**.

---

## 3 · Remaining gaps (justified for new development)

Only two items in the entire audit fail the "already exists" test:

1. **Per-opportunity Execution Timeline UI panel** — no equivalent view exists. Justification: operators need one scrollable trail per opportunity showing every state transition, every audit entry, every evidence bundle, and every broadcast attempt. This is a *composition* of already-existing data with no new business logic. Recommend implementation as a Slice-4 UI drop.

2. **Ranking sort-order query parameter** — the ranking primitives (`confidence`, `spread_bps`, `depth_usd`, `return_low/high`) are already emitted per row. Adding a `sort_by=…` param to `/api/arbicore/opportunities` is a ~10-LOC refinement, not a new capability.

Everything else is **either activation of a dormant canonical module** or **already live**.

---

## 4 · Recommendation

**Do not build any new Opportunity Intelligence infrastructure.**

Instead, schedule a focused **"Wave 8 · Canonical Intelligence Activation"** wave with a single objective: import and wire the following canonical modules from `/tmp/cx/repo/app/backend/arbicore` into `/app/backend/arbicore`, then rewire the existing `server.py` intelligence stubs to consume the canonical shapes:

- `arbicore/emission_bus.py`
- `arbicore/models/{canonical.py, discovery.py, enums.py, category_metadata.py}`
- `arbicore/data/{opportunity_repo.py, outcome_repo.py, discovery_queue.py, provenance.py, wallet_profile_repo.py, regime_snapshot_repo.py, venue_capability_repo.py, discovery_source_metrics_repo.py, metrics_repo.py, state_observer.py, scanner_config_repo.py, horizons.py, _inmemory.py}` + `arbicore/data/mongo/*.py`
- `arbicore/intelligence/{scoring.py, confidence.py, roi_probability.py, capital.py, audit_log.py, validators/*.py}` (**Note: `capital.py` and `validators/*` are already used indirectly — verify they aren't double-imported.**)
- `arbicore/intel/{resolver.py, scorer.py, entity_repo.py, entity_types.py, cluster_detector.py, models.py, launch/*}`
- `arbicore/learning/concrete/{outcome_tracker.py, audit_log.py, survival.py, regime_worker.py, regime_classifier.py}`
- `arbicore/scanners/*` (all six family scanners plus `discovery_source.py`, `opportunity_verifier.py`, `verification_evidence.py`, `http_retry.py`)
- `arbicore/shadow/observer.py`
- `arbicore/runtime/composition.py` (as the orchestrator)

After this activation, the running server will emit **canonical** opportunity shapes to the **already-built** v2 UI pages, and the entire Opportunity Intelligence pipeline (Discovery → Ranking → Scoring → Certification → Queue → Lifecycle → History → Memory → Learning → Calibration → Adaptive Weights → Timeline) will function end-to-end.

**Estimated effort:** 1 focused engineering day for import + wire + verification tests. **No new business logic is required.**

---

*This audit is verification-only. No code was written or modified during the audit. Every classification is backed by a canonical file reference above.*
