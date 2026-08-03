# ArbiCore X — Flash Loan Capability Audit (v2.0.0)

**Date:** 2026-08-02
**Purpose:** determine the strongest possible flash-loan platform we can ship **in a single v2.0.x deployment**, before expanding into CEX arb, margin, treasury capital, cross-chain capital, or institutional credit in later phases.
**Scope:** flash-loan-only capabilities. Everything else is deliberately deferred.
**Operating constraint:** the platform must be able to operate with **only gas fees + minimal capital**. All notional comes from flash loans; the operator supplies gas + a tiny working balance only.
**Approach:** activate dormant modules, refine partial modules, build only what does not exist. Never rebuild.

**Legend:**
- ✅ **COMPLETE** — production-ready, wired into `server.py`, tested green
- 🟡 **PARTIAL** — foundation exists, needs refinement
- ⚪ **DORMANT** — full implementation in tree, not wired
- 🔴 **MISSING** — must be built

---

## 1. Core Platform

| # | Capability | Status | What exists / partial / dormant / missing | Effort | Before deploy? |
|---|---|:-:|---|:-:|:-:|
| 1.1 | **Discovery Engine** | 🟡 | **Exists:** `arbicore/execution/discovery.py` `ContinuousDiscovery` (60 s tick, thin activator). **Dormant to wire in:** `scanners/discovery/discovery_source.py` (DexScreenerHintSource + registry) + `dex_arbitrage/scanner.py` + `flash_loan_arbitrage/scanner.py`. **Refine:** replace the thin universe loader with the dormant scanner orchestrators via `DiscoveryQueue`. **Missing:** none. | M | ✅ **YES** |
| 1.2 | **Live Quote Engine** | ✅ | `arbicore/execution/quoter.py` — `QuoterRegistry` with 3 backends: `UniV3QuoterV2`, `AerodromeSlipStreamQuoter`, `AerodromeClassicQuoter`, plus deterministic fallback path. Runs via `eth_call`. Active in production. | — | — |
| 1.3 | **Live Gas Engine** | ✅ | `arbicore/execution/gas.py` — `StaticGasOracle` (default, offline-safe) + `RpcGasOracle` (eth_gasPrice, opt-in). Endpoint `/execution/gas` exposes both. | — | — |
| 1.4 | **Economics Engine** | ⚪ | **Universal aggregator ships dormant** in `scanners/economics.py` (`LegCost`, `aggregate_economics`, `per_chain_gas_estimate_usd`). **Flash-loan-specific ships dormant** in `scanners/flash_loan_arbitrage/economics.py` (`FlashLoanEconomicsAssessor` — models flash-loan premium as an appended `LegCost(fee_kind='flash_loan_premium')` leg). **Partially active** via `execution/planner.py` dry-run which does inline economics — sufficient for single-hop, insufficient for multi-hop. **Refine:** route planner through the universal aggregator so multi-hop opportunities get the same substrate as single-hop. | S | ✅ **YES** |
| 1.5 | **Opportunity Scoring** | ⚪ | **Dormant:** `arbicore/intelligence/scoring.py` `ScoringEngine` (spread + persistence + liquidity dimensions, chain-profile-aware). **Active shim:** `/opportunities` uses `sort_by={confidence,spread,depth,freshness}` at the API layer. **Refine:** wire `ScoringEngine.score()` into the opportunity write path so every persisted opportunity carries a `score_breakdown` field. | S | ✅ **YES** |
| 1.6 | **Certification Pipeline** | ✅ | `arbicore/execution/certification.py` — 6-gate ladder (kill_switch → mode → capital → secret → preflight → operator_confirm). Endpoint `/execution/certification/run` production-verified. | — | — |
| 1.7 | **Broadcast Pipeline** | ✅ | `arbicore/execution/broadcast.py` + `calldata.py` + `live_signer.py` — Balancer V2 flashLoan encoder, UniV3 exactInputSingle encoder, executor.execute() encoder, revert decoder (`decode_revert_data`), `debug_traceCall` fallback. | — | — |
| 1.8 | **Autonomous Executor** | ✅ | `arbicore/execution/auto_executor.py` — 30 s tick, batch 25. Wired at startup. | — | — |
| 1.9 | **Opportunity Journal** | ✅ | `arbicore/data/journal.py` — append-only, one doc per `opp_id`, `events[]` array. 3 endpoints (`/journal`, `/journal/summary`, `/journal/{id}`). | — | — |
| 1.10 | **Learning Engine** | 🟡 | **Active:** `arbicore/learning/ledger.py` + `learning/concrete/calibration_worker.py` + `learning/concrete/adaptive_weights_worker.py` (OBSERVE mode). **Refine:** activate dormant `outcome_tracker.py` + wire `SignalConfidenceEngine` + `EntityScorer` into the learner's read path. **Missing (Phase 2, not before deploy):** ENFORCE promotion governance. | S | 🟡 partial |
| 1.11 | **Policy Engine** | ✅ | `arbicore/execution/mode.py` (mode ladder × 7 strategies) + `capital_policy.py` (7 seeded per-strategy policies). | — | — |
| 1.12 | **Historical Opportunity Recording** | ✅ | Immutable append semantic already enforced by journal write path (`$push` to `events[]`; documents never mutate). TTL disabled by design. | — | — |

**Core Platform verdict:** 8 COMPLETE · 3 need pre-deploy refinement (Discovery, Economics, Scoring wiring) · 1 partial (Learning wiring). No missing items in Core Platform.

---

## 2. Flash Loan Opportunity Discovery

| # | Capability | Status | What exists / partial / dormant / missing | Effort | Before deploy? |
|---|---|:-:|---|:-:|:-:|
| 2.1 | **DEX ↔ DEX Arbitrage** | ⚪ | Full canonical scanner in `arbicore/scanners/dex_arbitrage/` — 8 files: `scanner.py` (orchestrator), `sources.py`, `quoter.py`, `quote_cache.py`, `filter.py` (gates), `economics.py` (`DEXEconomicsAssessor`), `verifier.py`, `__init__.py`. Boot posture: DORMANT. **Activate** by importing scanner factory into ContinuousDiscovery. | M | ✅ **YES** |
| 2.2 | **Multi-hop Arbitrage** | ⚪ | Full canonical scanner in `arbicore/scanners/flash_loan_arbitrage/` — 8 files including `route_search.py` (`RouteSearchEngine` — DFS-based N-token cycle discovery over pool adjacency graph). **This IS the multi-hop capability.** Route length is a search parameter. **Activate** together with 2.1. | (bundled with 2.1) | ✅ **YES** |
| 2.3 | **Triangular DEX Arbitrage** | ⚪ | Triangular is the **N=3 case** of the RouteSearchEngine in 2.2. No separate module needed. Once `flash_loan_arbitrage` is activated with `max_cycle_len=3`, triangular is produced by construction. **Refine:** expose the cycle-length knob via a Universe / discovery config surface so operators can enable/disable 3-token loops per chain. | S | ✅ **YES** |
| 2.4 | **Stablecoin Depeg Arbitrage** | 🔴 | Not present as a standalone scanner. **Analysis:** stablecoin depeg arbitrage is architecturally a **specialisation of DEX-arb where the cost model + gating changes** (very small spread, extreme size, tight-window depeg detection). **Recommended path:** implement as a **new gate + filter** layered on the dormant `dex_arbitrage` scanner, not as a new scanner tree. Requires: (a) stablecoin-pair whitelist, (b) reference-price oracle (Chainlink / on-chain TWAP), (c) tighter spread gate (≥ 5 bps vs standard 30 bps), (d) larger notional band. **Effort:** M (~1 week; net-new but small — extends existing scanner). | M | 🟡 recommend YES |
| 2.5 | **Liquidation Engine** | 🔴 | Not present. **Analysis:** liquidation is a **fundamentally different flow** from arbitrage — reads borrower positions from lending protocols (Aave, Compound, Radiant, Morpho), monitors health factor < 1, calls `liquidationCall(collateral, debt, user, amount, false)` via flash loan for collateral. Would require: (a) subgraph/on-chain scanner for underwater positions per lending protocol, (b) liquidation-specific broadcast path (different calldata than arb), (c) different verifier chain (health factor recompute at broadcast time), (d) profitability model including liquidation bonus (Aave: 5%, Compound: 8%). **Effort:** L (~2 weeks — genuinely new subsystem; reuses flash-loan infra but adds ~1500 LOC). **Recommendation:** DEFER to Phase 2 unless operator explicitly wants day-one liquidation capability. Liquidations are a specialty flow with different latency requirements (sub-block) and different risk (borrower health can change mid-tx). Adding it pre-deploy widens the LIMITED_LIVE certification surface materially. | L | ❌ **NO** — defer to Phase 2 |

**Flash Loan Opportunity Discovery verdict:** 3 DORMANT (activate as a single wave) · 1 recommended MISSING (Stablecoin Depeg — thin extension of DEX arb) · 1 MISSING deferred (Liquidation — separate subsystem, better as Phase 2).

---

## 3. Flash Loan Capital Intelligence

| # | Capability | Status | What exists / partial / dormant / missing | Effort | Before deploy? |
|---|---|:-:|---|:-:|:-:|
| 3.1 | **Multi-provider Flash Loan Router** | ✅ | `arbicore/execution/adapters.py` `FlashLoanAdapter` protocol + registry. 3 providers registered and production-active: `AaveV3FlashLoanAdapter` (5 bps), `BalancerV2FlashLoanAdapter` (0 bps), `UniswapV3FlashLoanAdapter` (pool tier). `AdapterRegistry` selects at plan time. | — | — |
| 3.2 | **Borrow Provider Selection** | 🟡 | `execution/planner.py` already picks the lowest-fee provider that supports the requested `(chain, token, amount)`. **Refine:** add a live pool-depth precheck (`getReserveData` for Aave, pool balance for Balancer, pool liquidity for UniV3) so the planner does not select a provider whose pool is too shallow for the required notional. **Reuse:** the same eth_call plumbing used by the Live Quote Engine. **Effort:** S (~2 days). | S | ✅ **YES** |
| 3.3 | **Borrow Optimization** | 🟡 | Currently: static fee ranking. **Refine to include:** (a) live pool depth (from 3.2), (b) time-of-day availability pattern (from Market History Storage — P1-α — which is coming), (c) provider-level historical revert rate (from Provider Intelligence — P2). **Pre-deploy:** deliver only the depth-aware selection (3.2). Time-of-day + historical revert rate become live post-deploy once the memory foundation is built. | (folded into 3.2) | 🟡 partial |

**Flash Loan Capital Intelligence verdict:** 1 COMPLETE · 2 PARTIAL — both pre-deploy refinements are the same ~2-day change (depth-aware provider selection).

---

## 4. Flash Loan Intelligence

| # | Capability | Status | What exists / partial / dormant / missing | Effort | Before deploy? |
|---|---|:-:|---|:-:|:-:|
| 4.1 | **Massive Route Expansion** | ⚪ | **Dormant:** `arbicore/scanners/flash_loan_arbitrage/route_search.py` `RouteSearchEngine` — DFS over pool adjacency graph, produces `RouteCycle` objects, exposes `last_wall_ms` + `last_explored` metrics, honours max-depth + max-cycles knobs. **This is the route-expansion engine.** Activate as part of the 2.1/2.2 wave. | (bundled with 2.1) | ✅ **YES** |
| 4.2 | **Route Ranking** | ⚪ | **Dormant:** `arbicore/intelligence/scoring.py` `ScoringEngine` — spread_score + persistence_score + liquidity_score. `ScoreBreakdown` dataclass. **Wire** into the opportunity write path so every persisted opportunity carries `score_breakdown` + a composite `score` field. **Also active:** API-layer `sort_by` at `/opportunities`. | S | ✅ **YES** |
| 4.3 | **Route Confidence** | ⚪ | **Dormant:** `arbicore/intelligence/confidence.py` `SignalConfidenceEngine` + `RouteStats` (persistence_rate, confidence_score, InMemory + Protocol-based store). **Active shim:** `/roi-probability?route_id=…` reads from `MongoRouteSuccessTracker`. **Refine:** swap the shim for a real read of `SignalConfidenceEngine` backed by `RouteStats` in Mongo. | S | ✅ **YES** |
| 4.4 | **AI Opportunity Ranking** | ⚪ | **Dormant:** `arbicore/intel/scorer.py` `EntityScorer` (Universal Entity Scorer — record_outcome, get, top). **Dormant supporting:** `intel/cluster_detector.py`, `intel/entity_repo.py`, `intel/resolver.py`. **Refine:** wire `EntityScorer` into the ledger's outcome-consumption path so venues/pairs/adapters accumulate an entity score; expose via `/intelligence/entities/top`. | M | ✅ **YES** |
| 4.5 | **Opportunity Prediction** | 🔴 | Not present. **Analysis:** requires a time-series model over (Market History Storage — P1-α, missing) + (Opportunity Lifetime Intelligence — P1-β, missing) + (regime signal — dormant). All three dependencies are P1 work per the platform roadmap; the predictor sits **on top** of them. **Recommendation:** DEFER to Phase 2 (P2-5 in the platform roadmap). Shipping it before deployment means shipping it on empty data — no historical context, no lifetime evidence, no regime observations. | L | ❌ **NO** — depends on P1 memory foundation |

**Flash Loan Intelligence verdict:** 4 DORMANT (activate as a single "intelligence wave") · 1 MISSING but deferred (Prediction needs P1 memory foundation first).

---

## 5. Flash Loan Learning

| # | Capability | Status | What exists / partial / dormant / missing | Effort | Before deploy? |
|---|---|:-:|---|:-:|:-:|
| 5.1 | **Market History Storage** | 🔴 | **Missing.** No `market_history` collection, no snapshot writer. **This is the P1-α item in the platform roadmap** — the foundation for everything downstream. **Build new:** `MarketHistoryWriter` background task snapshotting `(chain, dex, pair, adapter, timestamp) → {mid, depth, quote_bps_1eth, quote_bps_10eth}` at 30 s cadence, TTL 90 days by default. Reuses the already-active Quoter registry (no new external calls). **Effort:** M (~1 week). **Recommendation:** BUILD BEFORE DEPLOYMENT. This is the single upstream capability that unblocks everything. Deploying without it means every downstream analytic starts with a cold-start delay of 30+ days on the VPS. Building it pre-deploy means the VPS starts collecting from t=0. | M | ✅ **YES** — critical |
| 5.2 | **Opportunity Lifetime Intelligence** | 🔴/🟡 | **Journal already captures `first_seen` + `last_seen` implicitly** through `created_at` and the terminal event timestamp. **Missing:** `disappeared_at` (requires a discovery-tick delta observation), `lifetime_ms` derived field, `recurrence_count` (per route fingerprint), survival curve. **This is P1-β.** **Reuse:** dormant `arbicore/learning/concrete/survival.py` Kaplan-Meier module for the survival math. **Effort:** M (~1 week). **Recommendation:** BUILD BEFORE DEPLOYMENT. It is a purely additive extension of the journal write path — no risk, high value, and the moment the VPS is live it begins accumulating a full biography of every opportunity. Deferring loses forever the opportunities discovered in the pre-instrumentation window. | M | ✅ **YES** |
| 5.3 | **Historical Market Intelligence** | 🔴/🟡 | **Learning Ledger already emits synthetic labels** for SHADOW-mode observations. **Missing:** first-class `observation_only` sample class distinct from `executed`, backfill runner over journal, endpoints (`/learning/observations`, `/observations/summary`, `POST /ledger/backfill`). **This is P1-γ.** **Reuse:** activate dormant `arbicore/learning/outcomes.py` + `learning/concrete/outcome_tracker.py`. **Effort:** M (~1 week). **Recommendation:** BUILD BEFORE DEPLOYMENT — mostly refinement of the existing ledger; each observed-not-executed opportunity is a permanent training sample the platform will never generate again if we skip pre-deploy. | M | ✅ **YES** |
| 5.4 | **Replay & Outcome Intelligence** | 🔴 | Not present. Full 5-question contract (why success / why fail / better route? / better provider? / better size?) requires (5.1 Market History) + (5.2 Lifetime) + (5.3 Historical Intel) + planner reuse. **This is the P1↔P2 bridge in the platform roadmap.** **Effort:** L (~1.5 weeks). **Recommendation:** BUILD **partial** BEFORE DEPLOYMENT (basic 2-question form: why succeed / why fail — using data already in the journal). Full 5-question form (with counter-factual alternatives) requires 5.1 to have accumulated history, so the "better route / better provider / better size" answers get **wired but return `insufficient_data`** on day one, and self-populate once Market History accumulates. This way we deploy with the endpoint contract stable and the platform self-improves over time. | L (partial S) | 🟡 **partial YES** |
| 5.5 | **Market Regime Learning** | ⚪ | **Dormant:** `arbicore/learning/concrete/regime_classifier.py` + `regime_worker.py` + `data/mongo/regime_snapshot_repo_mongo.py` + `arbicore_regime_snapshots` collection. Full canonical implementation. **Activate** by wiring `regime_worker` into `server.py` startup. **Effort:** S (~2 days). **Recommendation:** ACTIVATE BEFORE DEPLOYMENT. It runs in the background writing regime snapshots; the moment we deploy it starts accumulating regime evidence used by all downstream intelligence. | S | ✅ **YES** |
| 5.6 | **Route Success History** | ✅ | `MongoRouteSuccessTracker` — active, feeds Slice-0 `/roi-probability`. Rolling win-rate + sample count per route fingerprint. | — | — |

**Flash Loan Learning verdict:** 1 COMPLETE · 1 DORMANT (activate) · 4 MISSING (three are the foundational P1 memory build; one is the P1↔P2 bridge deliverable — recommended partial-scope pre-deploy).

---

## 6. Consolidated Table — Pre-deployment plan

| Bucket | Items | Effort | Deploy scope |
|---|---|:-:|:-:|
| **Already Production-Ready** (no work) | Live Quote Engine (1.2) · Live Gas Engine (1.3) · Certification (1.6) · Broadcast Pipeline (1.7) · Autonomous Executor (1.8) · Opportunity Journal (1.9) · Policy Engine (1.11) · Historical Opportunity Recording (1.12) · Multi-provider Flash Loan Router (3.1) · Route Success History (5.6) | — | ✅ ship |
| **Activate Before Deployment** (dormant → wired, no code) | Economics Engine (1.4) · Opportunity Scoring (1.5) · Market Regime Learning (5.5) · Route Ranking (4.2) · Route Confidence (4.3) · AI Opportunity Ranking (4.4) · DEX↔DEX Arbitrage scanner (2.1) · Multi-hop Arbitrage scanner (2.2 — bundled) · Triangular case (2.3 — cycle-length knob) · Massive Route Expansion (4.1 — bundled) | ~1 week total | ✅ ship |
| **Refine Before Deployment** (small extension of existing code) | Discovery Engine — wire dormant scanners into ContinuousDiscovery (1.1) · Learning Engine — wire outcome tracker + confidence engine (1.10) · Borrow Provider Selection — depth-aware precheck (3.2, 3.3) | ~4 days | ✅ ship |
| **Build Before Deployment** (genuinely new but foundational) | Market History Storage (5.1) · Opportunity Lifetime Intelligence (5.2) · Historical Market Intelligence (5.3) · Replay & Outcome Intelligence — partial (2-question form) (5.4 partial) · Stablecoin Depeg gate (2.4) | ~4–5 weeks | ✅ ship |
| **Safe to Leave Until Phase 2** | Liquidation Engine (2.5) · Opportunity Prediction (4.5) · Replay & Outcome Intelligence — full 5-question form (5.4 remainder) · ENFORCE promotion governance · Provider Intelligence · Multi-chain expansion · Additional protocol activation (Radiant, dYdX, Compound v3, Morpho) · Additional DEXes (SushiSwap, Curve, PancakeSwap) · Autonomous Research · AI-generated strategy discovery | — | Post-deploy |

---

## 7. Effort summary

| Track | Effort | Comment |
|---|---|---|
| Track A — Activate (10 dormant modules) | ~5 days | Import + registry wiring + one endpoint each. Zero new logic. |
| Track B — Refine (3 small extensions) | ~4 days | Depth-aware borrow selection · scanner-wire in discovery · outcome tracker in learning. |
| Track C — Build (4 new modules + 1 partial) | ~4–5 weeks | Market History Storage · Opportunity Lifetime · Historical Market Intel · Replay partial (2-question) · Stablecoin Depeg gate. |
| **Total to deploy the strongest flash-loan platform** | **~6 weeks from now** | Sequential-ish; some Track A can proceed in parallel with Track C. |

Compare to the audit's original P1 estimate of ~4 weeks — the extra ~2 weeks buys **fully-activated multi-hop + triangular + intelligence stack + market memory day-one on the VPS**, which is exactly what the operator's "deploy once, minimize post-deploy architectural changes" objective demands.

---

## 8. Recommended implementation order

### Sprint 1 (week 1) — Activate the intelligence surface
Zero-risk dormant activations. Nothing new is built. Every one of these is a wiring change.

1. Wire `regime_worker` at startup (5.5)
2. Wire `outcome_tracker` into pipeline terminal (1.10 · 5.3 groundwork)
3. Wire `ScoringEngine` into opportunity write path (1.5 · 4.2)
4. Wire `SignalConfidenceEngine` behind `/roi-probability` (4.3)
5. Wire `EntityScorer` behind a new `/intelligence/entities/top` (4.4)
6. Swap `/intelligence/decisions` static stub for live confidence engine
7. Swap `/intelligence/recommendations` static stub for live Mongo aggregation

**Deliverable:** intelligence stack fully active, no new data yet.

### Sprint 2 (weeks 2–3) — Activate the discovery + economics surface

8. Wire universal economics aggregator through `execution/planner.py` (1.4)
9. Import `dex_arbitrage/scanner.py` + `flash_loan_arbitrage/scanner.py` factories into `ContinuousDiscovery` (2.1 · 2.2 · 4.1 bundled)
10. Expose cycle-length knob for triangular (2.3)
11. Add depth-aware borrow precheck to planner (3.2 · 3.3)
12. Move associated tests back from `tests/_pending_scanner_activation/` — `test_d1_discovery_layer`, `test_d4_5_launch_scanner`, `test_d5_2_composition_and_invariants`, `test_d6_1_verifier_scanner_sources`, `test_opportunity_gate`

**Deliverable:** ContinuousDiscovery is now producing multi-hop + triangular flash-loan opportunities from live pool graphs, ranked by real scoring engine, filtered by 9-gate verifier chain.

### Sprint 3 (weeks 3–4) — Build the market memory foundation

13. Build `MarketHistoryWriter` background task + `market_history` collection (5.1)
14. Extend Journal for lifetime fields (first_seen / last_seen / disappeared_at / lifetime_ms / recurrence_count) + activate `survival.py` for the survival curve (5.2)
15. Extend Learning Ledger to emit first-class `observation_only` samples + backfill runner (5.3)

**Deliverable:** the VPS begins collecting market history + opportunity biographies + labelled samples from t=0.

### Sprint 4 (week 5) — Deliver the introspection surface

16. Build Stablecoin Depeg gate + reference oracle wiring layered on dex_arbitrage scanner (2.4)
17. Build Replay & Outcome Intelligence — partial (2-question form: why success / why fail from existing data; 3 counter-factual questions return `insufficient_data` until Market History accumulates) (5.4 partial)

**Deliverable:** every opportunity can be introspected with the two immediately-answerable questions; the platform is honest about the three questions that need history to accumulate.

### Sprint 5 (week 6) — Regression + certification

18. Full regression run on the enlarged active surface
19. Any tests moved back from `_pending_scanner_activation/` must be green
20. Update `docs/CANONICAL_CERTIFICATION.md` with the pre-deploy activation summary + a new bullet: **"Flash-Loan v2 ready — DEX/multi-hop/triangular scanners active, intelligence surface live, market memory writing"**
21. Bump `VERSION` → `v2.1.0` (MINOR — additive: new endpoints + new collections + new active workers + new dormant-module activations; zero breaking changes)
22. Tag, package as `arbicore-x-v2.1.0.bundle`, deploy to VPS in SHADOW mode

**Deliverable:** the strongest possible flash-loan platform, deployed once, in SHADOW mode, ready to accumulate telemetry.

---

## 9. Risk assessment (pre-deploy scope)

| Risk | Severity | Mitigation |
|---|:-:|---|
| **Activating multiple scanners spikes CPU on VPS** | Medium | Feature-flag each scanner independently (`ARBICORE_SCANNER_DEX_ARB_ENABLED`, `..._FLASH_LOAN_ARB_ENABLED`, `..._TRIANGULAR_ENABLED`); default only `flash_loan_arbitrage` ON at first boot; benchmark before enabling `dex_arbitrage` alongside. |
| **Multi-hop route explosion overwhelms Mongo writes** | Medium | RouteSearchEngine already exposes `max_cycle_len` + `max_cycles` knobs; discovery-side deduplication key `(chain, family, in_token, out_token, dex_path_hash)`. |
| **Market History Storage growth uncontrolled** | Medium | TTL index 90 days by default (configurable); operator can lower cadence or narrow universe from Settings. |
| **Scoring engine + confidence engine give divergent verdicts** | Low | They serve different questions (route quality vs signal quality); both surface separately in the API. Aggregate score is a downstream concern (Phase 2). |
| **Depth-aware borrow selection adds RPC latency to planner** | Low | Cache pool depth for 60 s per pool; parallelise across providers; degrade gracefully to static fee ranking if RPC returns stale. |
| **Stablecoin Depeg gate false positives on chain congestion** | Medium | Require confirmation across 2 tick windows before emitting an opportunity; gate the reference oracle to Chainlink-only on Base (USDC.e, USDbC, DAI have stable feeds). |
| **Replay partial form ships with 3/5 questions dark** | Low | Document explicitly in the operator manual; each `insufficient_data` response includes an ETA ("available after 7 days of market history accumulation"). |

---

## 10. Final recommendation

**Deploy `v2.1.0` — the "strongest flash-loan platform" release — in ~6 weeks.**

The tree already contains the vast majority of what a strong flash-loan platform needs. Of the 27 capabilities audited:

- **10 are production-ready today** — no work.
- **10 are dormant and require only wiring** — Track A, ~1 week.
- **3 are partial and require small refinements** — Track B, ~4 days.
- **4 are genuinely missing and must be built** — Track C, ~4–5 weeks. Of these, three (Market History, Lifetime, Historical Intel) form the memory foundation the operator explicitly asked to prioritise.

Only **2 capabilities are recommended for deferral** — Liquidation Engine (separate subsystem best done in Phase 2) and Opportunity Prediction (impossible without memory accumulation, which the deployed platform will produce over time).

**One-deployment goal is achievable.** After `v2.1.0` ships, the platform will operate autonomously in SHADOW mode with:

- Multi-provider flash-loan router across 3 providers
- Live multi-hop + triangular arbitrage discovery via dormant D-3 + D-6 scanners
- Live route ranking + confidence + entity scoring
- Live regime detection
- Market memory writing from t=0
- Opportunity lifetimes recorded permanently
- Every observed opportunity fed to the learner
- Every executed (and later, un-executed) opportunity answerable via replay

**Post-deploy work is limited to what can only be built with data:** Opportunity Prediction, full Replay (3 remaining questions), Provider Intelligence, Multi-chain expansion, ENFORCE promotion governance, Liquidation Engine. None of these require an architectural change to the deployed platform — they are all additive.

_Awaiting approval to begin Sprint 1 (Activate the intelligence surface) — Sprint 1 is entirely dormant activations, ~1 week, zero net-new modules, and unlocks the intelligence stack that Sprint 2 depends on._
