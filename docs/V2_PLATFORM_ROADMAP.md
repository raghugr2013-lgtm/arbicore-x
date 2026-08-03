# ArbiCore X — Platform Roadmap (v2.0.0 → Autonomous Institutional Arbitrage Intelligence Platform)

**Status:** ratified 2026-08-02 (post v2.0.0 canonical consolidation)
**Companion documents:**
- [`V2_CONSOLIDATION_AUDIT.md`](V2_CONSOLIDATION_AUDIT.md) — how the two source repositories were merged into v2.0.0
- [`V2_INTELLIGENCE_AUDIT.md`](V2_INTELLIGENCE_AUDIT.md) — subsystem-by-subsystem capability audit
- [`V2_MIGRATION_GUIDE.md`](V2_MIGRATION_GUIDE.md) — VPS deployment / upgrade flow
- [`ROADMAP.md`](ROADMAP.md) — repository governance / release process (not this document)

> This document is the **product roadmap** — what the platform is evolving into, in what order, and why. `docs/ROADMAP.md` remains the **repository governance** doc.

---

## 1. Vision

**ArbiCore X is not a flash-loan executor. It is an Autonomous Institutional Arbitrage Intelligence Platform.**

The distinction matters because it changes what the platform must remember and how it must learn:

- A **flash-loan executor** cares about the trade in front of it: preflight → sign → broadcast → confirm.
- An **institutional intelligence platform** cares about every trade it has ever seen, every trade it never took, every trade it might have taken, and why it made the decisions it did. It records the market itself — not just its own executions — and treats every observation as training data for a continuously improving decision engine.

The three-fold objective:

1. **Autonomous** — the platform runs its own discovery, evaluation, gating, and (when authorised) execution loop without operator hand-holding.
2. **Institutional** — decisions are auditable, sized under strict capital policy, signed with cryptographic evidence, and reversible via a kill switch.
3. **Intelligence** — every opportunity — executed or not — is retained and mined for regime, seasonality, decay, survival, provider quality, capital efficiency, and route evolution.

---

## 2. Deployment posture (unchanged)

1. **Deploy v2.0.0 to the target VPS** as-is. No P0 gaps.
2. **Operate in SHADOW mode.** Every strategy defaults to `SHADOW` on first boot. The Auto Executor drains the pipeline but writes only journal + ledger rows — no chain writes.
3. **Continuously collect market intelligence** while SHADOW mode runs. Every 60-second discovery tick adds market observations to the historical store. Every candidate opportunity is journalled with its full lifecycle.
4. **Validate the autonomous pipeline** against real market data (opportunities discovered, gated, verdicted). Verify calibration curves converge. Verify adaptive weights are producing sane recommendations under OBSERVE mode.
5. **Evolve into a continuously learning platform** — enable ENFORCE mode once SHADOW telemetry validates the loop; promote per strategy from SHADOW → PAPER → LIMITED_LIVE → FULL_LIVE on the operator's terms, backed by evidence.

The platform must never require a code deploy to change posture. Every posture change is a UI action + a signed audit event.

---

## 3. Priority framework (adjusted)

Priority reflects the **institutional intelligence platform** objective, not just the LIMITED_LIVE flash-loan objective. The audit's classification is adjusted below.

### Priority ladder

| Tier | Objective | When |
|---|---|---|
| **P0** | Deployment blockers | before v2.0.0 → VPS |
| **P1** | Foundation of institutional intelligence | during the SHADOW validation window |
| **P1↔P2 bridge** | Introspection loop (replay + outcome) | at SHADOW → LIMITED_LIVE transition |
| **P2** | Optimisation intelligence | during LIMITED_LIVE ramp |
| **P3** | Systemic expansion | during / after FULL_LIVE |
| **P4** | AI readiness | v2.3+, deferred |

### P0 — Deployment blockers

**None.** v2.0.0 is deployment-ready per the audit. All P0 concerns for the first LIMITED_LIVE broadcast were closed in Phase 10.10.6.

---

### P1 — Foundation of institutional intelligence (SHADOW window)

The platform's memory has to be built **before** its cognition. P1 is entirely about giving the platform durable, structured, queryable memory of the market and of every opportunity it has ever seen. Once memory is complete, everything downstream (analytics, recommendation, prediction, replay, RL) is derivative and cheap.

#### P1-α — **Market Intelligence Database** _(highest P1, first capability to build — Sprint 1)_

> The permanent memory of the platform itself.
>
> **Naming (2026-08-02 amendment):** originally scoped as "Market History Storage" — renamed to **Market Intelligence Database (MID)** because the scope has expanded beyond price/depth history. The MID is the single authoritative persistent store for **everything the platform observes, decides, or produces**, unified under one collection namespace and one write path so downstream intelligence layers (P1-β, P1-γ, P1↔P2 bridge, P2, P3) all read from a single consistent memory.

**What the MID persistently stores (one write path, no parallel systems):**

| Domain | Purpose | Reuses / activates |
|---|---|---|
| **Market state** — mid, depth (bid/ask at multiple size steps), spread, imbalance per `(chain, dex, pair, timestamp)` | Foundation for volatility, seasonality, regime confirmation, replay context | Live Quoter registry (already active) |
| **Quotes** — every route quote produced by discovery / planner (successful and rejected) | Provenance for every opportunity decision; feeds Route Confidence + counter-factual replay | `arbicore/execution/quoter.py` — no new quote logic |
| **Liquidity** — pool depth snapshots per `(chain, dex, pool, timestamp)` with reserves + tick liquidity where applicable | Depth-aware borrow selection (P1-α consumer); Liquidity Mapping (P3 consumer) | Quoter eth_call plumbing — no new adapter |
| **Gas** — gas price + priority fee snapshots per `(chain, timestamp)` | Gas Intelligence (P2), Volatility, Prediction | `arbicore/execution/gas.py` — no new oracle |
| **Providers** — per-flash-loan-provider availability + observed premium + revert-count snapshots | Provider Intelligence (P2); depth-aware borrow selection (Sprint 2 refinement) | `arbicore/execution/adapters.py` — no new adapters |
| **Routes** — every unique route fingerprint the platform has ever seen, with cumulative persistence + first_seen + recurrence counters | Route Ranking (dormant `intelligence/scoring.py`); Route Confidence (dormant `intelligence/confidence.py`); AI Opportunity Ranking (dormant `intel/scorer.py`) | Existing route-fingerprint scheme |
| **Opportunities** — the full write path of every candidate opportunity, retained permanently regardless of terminal verdict (executed / shadow / rejected / policy-denied / expired) | Opportunity Lifetime (P1-β) reads from here; Historical Market Intelligence (P1-γ) reads from here | Extends `arbicore/data/journal.py` — no new journal |
| **Confidence** — every confidence score emitted + inputs at the time of emission | Auditability, calibration drift telemetry, replay | Wires dormant `SignalConfidenceEngine` write path |
| **Decisions** — every gate verdict (kill_switch/mode/capital/secret/preflight/operator) per opportunity | Full audit trail; feeds Replay's "why did it fail" answer | Extends existing certification pipeline write path |
| **Outcomes** — every terminal outcome (executed pnl_usd, gas_actual, revert reason, shadow synthetic outcome) | Learning Ledger label source; Replay's "why did it succeed" answer | Wires dormant `learning/outcomes.py` + `learning/concrete/outcome_tracker.py` |
| **Replay data** — computed counter-factual outcomes for the 5-question replay contract | Populates lazily as replay runs; caches results | Written by P1↔P2 bridge module |

**Design invariants:**

1. **Single write path** — one `MID` façade module (`arbicore/data/mid/__init__.py`) exposes a small typed API (`write_market_state`, `write_quote`, `write_liquidity_snapshot`, `write_gas_snapshot`, `write_provider_snapshot`, `write_route_observation`, `write_opportunity_event`, `write_confidence`, `write_decision`, `write_outcome`, `write_replay`). Every producer in the codebase writes through this façade. Never directly to Mongo.
2. **Additive-only Mongo schema** — new collections under a shared namespace (`mid_market_state`, `mid_quotes`, `mid_liquidity`, `mid_gas`, `mid_providers`, `mid_routes`, `mid_confidence`, `mid_decisions`, `mid_outcomes`, `mid_replay`). Existing collections (`opportunities`, `opportunity_journal`, `calibration_log`, `arbicore_signal_metrics`) remain untouched — the MID is a superset that references them.
3. **Retention policy is per-domain** — TTL index configurable per collection via UI (Settings → Market Intelligence Database). Sensible defaults: `mid_market_state` 90d, `mid_quotes` 30d, `mid_liquidity` 90d, `mid_gas` 180d, `mid_providers` 365d, `mid_routes` **no TTL** (permanent), `mid_confidence` 90d, `mid_decisions` **no TTL** (permanent audit), `mid_outcomes` **no TTL** (permanent), `mid_replay` 30d (recomputable).
4. **No parallel systems** — the MID **replaces** any ad-hoc historical-state writes elsewhere in the codebase. Any producer discovered to write outside the façade during Sprint 1 is refactored to use the façade in the same PR.
5. **Zero new external dependencies** — every writer reuses already-active substrate (Quoter, Gas oracle, Adapter registry, Journal). Sprint 1 is a persistence layer, not a data-source expansion.

**Effort:** M–L (~1.5 weeks — larger than the original "Market History Storage" scope because it unifies 11 domains under one façade; still tractable in Sprint 1 because every producer already exists).

**Deployment impact:** ~10 new Mongo collections (all additive, all under the `mid_` prefix); one new background writer per domain (11 total, all thin — batched writes every 30 s); no new external calls.

**Rationale for Sprint 1 placement (operator directive, 2026-08-02):** everything else depends on historical data. If we activate scanners and intelligence first, the platform will emit opportunities/quotes/decisions that are permanently lost. The MID must exist before any producer starts producing — so from the first tick after deployment, every observation is captured. Deferring MID even by one sprint means permanently losing the training data that would have been generated during Sprints 2–4.

#### P1-β — **Opportunity Lifetime Intelligence** _(second P1)_

> Every opportunity's full biography — remembered permanently, even if never executed.

- **Extend `arbicore/data/journal.py`** to permanently record for every opportunity:
  - `first_seen` — first tick the opportunity appeared in discovery
  - `last_seen` — most recent tick the opportunity was still visible
  - `disappeared_at` — first tick after `last_seen` where the opportunity was absent (with a stability window to avoid flapping)
  - `lifetime_ms` — duration between `first_seen` and `disappeared_at` (or "still alive" if current)
  - `recurrence_count` — how many independent "appearances" this route has had (route fingerprint = (chain, family, in_token, out_token, dex_path))
  - `recurrence_intervals_ms` — inter-appearance intervals for the same fingerprint
  - `survival_probability_curve` — Kaplan-Meier style survival estimate (computed lazily by the analytic layer)
- **New Mongo collection:** `opportunity_lifetime` — one doc per unique route fingerprint, upserted by the journal write path. Journal itself remains per-opportunity; lifetime rolls up by fingerprint.
- **New endpoint:** `GET /api/arbicore/journal/lifetime?fingerprint=…` — returns the lifetime doc + rendered survival curve.
- **Reuse:** activate dormant `arbicore/learning/concrete/survival.py` (Kaplan-Meier implementation shipped in the canonical bundle) as the survival math backend. No net-new code for the curve itself.
- **Effort:** M (~1 week, mostly journal-side + endpoint + wiring the dormant survival module)
- **Deployment impact:** one new Mongo collection + one new endpoint. Fully additive.

#### P1-γ — **Historical Market Intelligence** _(third P1)_

> The platform must learn from observed-but-never-executed opportunities, not only from executed trades.

- **New concept:** every discovered opportunity that reaches `POLICY_DENIED`, `SHADOW_RECORDED`, `REJECTED`, or expires without being executed is still a **labelled data point** — the Learning Ledger already writes a synthetic `would_have_survived` label for these in SHADOW mode. Historical Market Intelligence generalises this into a first-class query surface.
- **Extend Learning Ledger (`arbicore/learning/ledger.py`):**
  - Explicit `observation_only` sample class distinct from `executed` sample class
  - Backfill runner that walks the journal in chronological order and emits labelled samples for opportunities that pre-date the ledger's introduction
  - New sample stream feeds the existing `CalibrationWorker` + `AdaptiveWeightsWorker` unchanged (they already read `calibration_log` + `arbicore_signal_metrics`)
- **New endpoints:**
  - `GET /api/arbicore/learning/observations` — paginated view of observation-only samples
  - `GET /api/arbicore/learning/observations/summary` — aggregate stats (count, by-family, by-verdict, by-would-have-outcome)
  - `POST /api/arbicore/learning/ledger/backfill` — trigger backfill from a specified journal cursor
- **Reuse:** dormant `arbicore/learning/outcomes.py` + `learning/concrete/outcome_tracker.py` — activate here rather than in the audit's Phase 3-A.
- **Effort:** M (~1 week, mostly extending the existing ledger + one backfill script)
- **Deployment impact:** extended writes to existing `calibration_log` + `arbicore_signal_metrics` collections; new endpoint set.

#### P1-δ — **Zero-risk activations from audit's Phase 3-A** _(fourth P1, in parallel)_

The audit's original Phase 3-A items **stay in P1** — they cost ~1 week total, activate work already in-tree, and are strictly additive:

1. Wire dormant **Regime Classifier + regime_worker** into startup
2. Wire dormant **Outcome Tracker** into pipeline terminal (folded into P1-γ)
3. Swap **`/intelligence/recommendations`** stub for real Mongo aggregation
4. Swap **`/intelligence/decisions`** stub for the live dormant `SignalConfidence` engine
5. Extend **`/dashboard/pulse`** to consume dormant `capital.py` + `scoring.py`
6. **Historical Learning backfill** (folded into P1-γ)
7. **Opportunity Decay Analysis** endpoint (thin analytic — becomes cheap once P1-β lifetime is in)
8. Extend **Learning Statistics** with drift telemetry (Brier score trend over calibration log)

**Aggregate P1 effort:** ~4 weeks after v2.0.0 deployment (α + β + γ ≈ 3 weeks; δ ≈ 1 week in parallel).

---

### P1↔P2 Bridge — **Replay & Outcome Intelligence** _(transition step)_

> Every execution answers five questions, permanently.

For every terminal event in the journal (executed or observation-only), the platform must be able to answer:

1. **Why did it succeed?**
2. **Why did it fail?**
3. **Would another route have performed better?**
4. **Would another provider have produced a better outcome?**
5. **Would another borrow size have improved the result?**

This becomes possible only once P1 is complete (Market History gives the counter-factual price context; Lifetime gives the temporal frame; Historical Market Intelligence gives the labelled sample stream).

- **New module:** `arbicore/intelligence/replay.py` — takes a journal row + a policy variant (alternate route / alternate provider / alternate size) and re-runs the Wave 6B planner + slippage estimator + gas oracle **against the historical market snapshot** (from P1-α) to produce a counter-factual expected outcome.
- **New endpoints:**
  - `GET /api/arbicore/replay/{opportunity_id}` — five-question answer set for a specific opportunity
  - `POST /api/arbicore/replay/{opportunity_id}/variant` — evaluate a specific counter-factual (`{"route": "...", "provider": "aave_v3", "size_usd": 5000}`)
  - `GET /api/arbicore/replay/summary` — aggregate: "in the last N days, choosing Aave over Balancer would have improved outcome in X% of cases by median Y bps"
- **Reuse:** dormant Wave 6B planner is already the correct simulator — feed it a historical market snapshot instead of a live quote.
- **New UI panel:** Opportunity detail page → "Replay & Alternatives" tab. Shows the five answers with concrete numbers.
- **Effort:** L (~1.5 weeks — the planner reuse makes this tractable; most work is the "historical quote" adapter over the P1-α store)
- **Deployment impact:** read-only compute; no external calls once P1-α is in.

**This bridge is the fulcrum of the platform.** It is the point where the system stops being a trade executor and becomes a self-critical intelligence. It also serves as the acceptance gate for moving strategies from SHADOW → LIMITED_LIVE — an operator can only promote a strategy once its replay summary shows the platform's decisions are outperforming plausible alternatives.

---

### P2 — Optimisation intelligence (LIMITED_LIVE ramp)

Built **on top of** the P1 memory + replay foundation. These are optimisation loops that require the intelligence platform to already have durable memory.

| # | Item | What it does | Reuses | Effort |
|---|---|---|---|---|
| P2-1 | **Provider Intelligence** | Per-provider (Aave / Balancer / UniV3 / future Radiant / future dYdX) performance history — success rate, revert reasons, avg gas, effective fee including slippage | replay engine, adapters, market history | M |
| P2-2 | **Borrow Optimization** | Live pool-depth aware selection between providers; adaptive to time-of-day depth patterns | provider intel, market history, adapters | M |
| P2-3 | **Capital Allocator** | Portfolio-aware sizing (currently per-plan; upgrade to portfolio VaR aware) | capital policy, journal, market history | L |
| P2-4 | **Multi-chain Optimization** | Chain profile registry + per-chain adapters + cross-chain opportunity ranking | wallet_registry, adapters, market history | L |
| P2-5 | **Opportunity Prediction** | Time-series model over journal + market history that flags likely-imminent opportunities before they surface in discovery | lifetime, regime, seasonality | L |

Also promoted to P2 (was P2 in audit already):

- Volatility / Seasonality / Multi-DEX / Gas Intelligence historical writer / Heatmaps / Daily Reports / Full Confidence + Recommendation surface / Performance Analytics extended

**P2 dependency:** all P2 items depend on at least P1-α (Market History) being live. P2-5 (Prediction) additionally depends on P1-β (Lifetime) and the P1↔P2 bridge.

**Aggregate P2 effort:** ~6–8 weeks after P1 lands.

---

### P3 — Systemic expansion (post-LIMITED_LIVE)

| # | Item | What it does | Notes |
|---|---|---|---|
| P3-1 | **Dormant scanner activation** — first wave | Wire `arbicore/scanners/flash_loan_arbitrage` into ContinuousDiscovery; move `tests/_pending_scanner_activation/test_d4_5_launch_scanner.py` back | Feature-flagged; benchmarked in SHADOW first |
| P3-2 | **Dormant scanner activation** — remaining waves | `cex_arbitrage`, `dex_arbitrage`, `cross_chain_arbitrage`, `funding_arbitrage`, `launch_arbitrage` | One family per wave; each independently validated |
| P3-3 | **Additional protocol activation** | Radiant, dYdX v3, Compound v3, Morpho — new flash-loan providers. SushiSwap, PancakeSwap, Curve, Balancer weighted pools — new DEXes | Adapter files only; framework already sound |
| P3-4 | **Autonomous Research** | Automated market-scanning agent that hypothesises new profitable route families, back-tests via replay engine, submits proposals to operator queue | Requires P1↔P2 bridge + P2-5 |
| P3-5 | **AI-generated strategy discovery** | LLM-assisted analysis of underperforming strategies → structured proposals for new gates / new sizing rules / new adapter integrations | Requires Knowledge Hub (P4) |
| P3-6 | Alerting router + Recovery hooks + ENFORCE promotion governance | (from audit's original Phase 3-E) | Institutional-grade operability polish |
| P3-7 | Market Replay Engine (batch) + Replay Learning (retro-inject) | (from audit's original Phase 3-E) | Extension of the P1↔P2 bridge |
| P3-8 | **Opportunity Knowledge Graph (foundation)** | Graph representation of relationships between routes, assets, providers, liquidity pools, market regimes, gas conditions, and outcomes, built as a materialised view on top of the Market Intelligence Database. Nodes: `Asset`, `Pool`, `Route`, `Provider`, `Regime`, `Opportunity`, `Outcome`. Edges: `flows_through`, `borrows_from`, `co-occurs-with`, `preceded`, `outperformed`. Query surface: "which routes historically outperform when regime=CALM and gas<20 gwei?" | Reads exclusively from MID (§P1-α); no new writers. Consumed by P3-4 Autonomous Research + P4 AI Research Assistant. |

**Aggregate P3 effort:** ~10–12 weeks, spread over the FULL_LIVE ramp.

---

### P4 — AI readiness (v2.3+)

- Knowledge Hub (vector store + doc ingestion + retrieval)
- Strategy Evolution (evolutionary / bandit loop that mutates policy toward observed reward)
- AI Research Assistant (LLM-assisted operator queries against the knowledge hub)
- Reinforcement Learning (actor-critic over mode / capital / adapter action space)
- **Opportunity Knowledge Graph (semantic layer)** — layered on top of the P3-8 graph foundation. Adds embedding-based similarity (asset embeddings, route embeddings, regime embeddings), natural-language query surface via the Knowledge Hub, and graph-conditioned prompts for the AI Research Assistant. Enables "find opportunities similar to opp_XYZ but on a different chain" and "explain why route X consistently outperforms route Y".

All P4 items are deferred, non-blocking, and gated on P2 + P3 being mature. Emergent LLM key already available in the deployment for when the platform is ready to consume it.

---

## 4. Priority matrix (final — 2026-08-02 amendment)

| Item | Original audit tier | New tier | Rationale for change |
|---|:-:|:-:|---|
| **Market Intelligence Database** (was: Market History Storage) | P2 | **P1-α (Sprint 1)** | Renamed to reflect expanded scope (11 domains, not just market state). Moved to Sprint 1 per operator directive: everything else depends on historical data, so the MID must exist before any producer starts producing. |
| Opportunity Lifetime Intelligence | P1 (partial) | **P1-β (Sprint 3)** | Permanent record of first_seen / last_seen / disappeared_at / lifetime / recurrence / survival probability |
| Historical Market Intelligence | (implicit in Historical Learning) | **P1-γ (Sprint 4)** | Learn from observed-but-not-executed — first-class in the roadmap now |
| Zero-risk activations (from audit Phase 3-A) | P1 | **P1-δ (Sprint 2)** | Confidence · ROI · Route Ranking · Economics · Regime · Entity Scoring — all activations only, no new code |
| Replay & Outcome Intelligence (5 questions) | (implicit in Market Replay Engine) | **P1↔P2 bridge (Sprint 5)** | Elevated to bridge; explicit five-question contract |
| Stablecoin Depeg gate | (not in original roadmap) | **P1↔P2 bridge (Sprint 5)** | Thin extension of dex_arbitrage scanner |
| Provider Intelligence | P2 | **P2-1** | Retained |
| Borrow Optimization | P2 | **P2-2** | Retained |
| Capital Allocator (portfolio-aware upgrade) | P2 | **P2-3** | Retained |
| Multi-chain Optimization | P2 | **P2-4** | Retained |
| Opportunity Prediction | P2 | **P2-5** | Retained |
| Dormant scanner activation | P3 | **P3-1 / P3-2** | Retained |
| Additional protocol activation | P3 | **P3-3** | Retained |
| Autonomous Research | (implicit) | **P3-4** | Elevated to explicit P3 item |
| AI-generated strategy discovery | (implicit in P4) | **P3-5** | Elevated to explicit P3 item; consumes P4 knowledge hub when available |
| **Opportunity Knowledge Graph — foundation** | (not in original roadmap) | **P3-8** | Graph relationships between routes/assets/providers/liquidity/regimes/gas/outcomes. Reads from MID exclusively. |
| **Opportunity Knowledge Graph — semantic layer** | (not in original roadmap) | **P4** | Embedding-based similarity + NL query surface, layered on P3-8 |

---

## 5. Sequence & timing (revised — Sprint 1 = MID first)

```
   t=0            deploy v2.0.0 → VPS. Enter SHADOW mode.
   t=+1.5 wk      SPRINT 1 · P1-α  Market Intelligence Database writing to Mongo
                     → 11 domains (market state · quotes · liquidity · gas · providers
                       · routes · opportunities · confidence · decisions · outcomes · replay)
                       persisted via single MID façade. Every future producer writes here.
   t=+2.5 wk      SPRINT 2 · P1-δ  Activate dormant intelligence surface
                     → Confidence · ROI · Route Ranking · Economics · Regime · Entity Scoring
                       All wire into MID as their persistence backing. Zero new code.
   t=+3.5 wk      SPRINT 3 · P1-β  Opportunity Lifetime Intelligence
                     → first_seen / last_seen / disappeared_at / lifetime / recurrence
                       / survival probability. Reads MID.mid_opportunities + MID.mid_routes.
   t=+4.5 wk      SPRINT 4 · P1-γ  Historical Market Intelligence
                     → observation_only sample class + backfill. Reads MID exhaustively.
   t=+6.0 wk      SPRINT 5 · Replay & Outcome (partial 5-Q) + Stablecoin Depeg gate
                     + regression + certification + package v2.1.0
                     → SHADOW → LIMITED_LIVE promotion authorisation gate opens
   t=+6.0 → +14 wk P2 items land incrementally during LIMITED_LIVE ramp
   t=+14 wk       LIMITED_LIVE → FULL_LIVE for the first strategy
   t=+15 → +26 wk P3 items land during FULL_LIVE operation
                     → P3-8 Opportunity Knowledge Graph foundation lands here
   t=+26 wk+      P4 (AI readiness) begins
                     → P4 semantic layer over Knowledge Graph lands here
```

**Cadence:** Sprint 1 (MID) tag `v2.0.1`. Sprints 2–5 tag `v2.1.0`. Full P2 lands as `v2.2.0`. `v3.0.0` when P4 begins LLM-integrated flows.

---

## 6. Non-negotiables (governance layered on this roadmap)

These invariants extend `docs/ROADMAP.md` §7 and `CONTRIBUTING.md`:

1. **Additive-only Mongo schema** through every P1/P2/P3 release. No breaking migrations before v3.0.0.
2. **Dormant modules stay dormant until activated.** No implicit imports into `server.py`. Every activation moves the corresponding test file back from `tests/_pending_scanner_activation/`.
3. **No P2 work begins until at least P1-α is live.** Every downstream intelligence would be starved of data and produce misleading conclusions.
4. **Replay & Outcome Intelligence (the P1↔P2 bridge) is the SHADOW → LIMITED_LIVE gate.** A strategy may only be promoted to LIMITED_LIVE once its replay summary demonstrates the platform's decisions are outperforming plausible alternatives.
5. **Every capability writes to the Market Intelligence Database (MID).** Nothing that produces observable state is allowed to exist as ephemeral in-memory data. All persistence flows through the MID façade — no parallel storage systems, no direct-to-Mongo writes that bypass the façade.
6. **Every learning surface exposes both an "executed" and an "observation-only" sample stream.** The platform never treats the two as equivalent nor discards either.
7. **AI/LLM-integrated flows (P4) never gate operator actions.** They are advisory. The operator always has the final signature.
8. **Opportunity Knowledge Graph reads only from the MID.** The graph (P3-8) is a materialised view. It never becomes a parallel authoritative store.

---

## 7. Success metrics

Per-tier acceptance criteria — the platform advances to the next tier only when these are met.

### P1 acceptance
- 30+ days of continuous market_history writes with zero data loss
- Every opportunity in the journal has non-null `first_seen`, `last_seen`, `disappeared_at`, `lifetime_ms`, `recurrence_count`
- ≥95% of journal rows produce a labelled learning sample (executed or observation-only)
- Calibration Brier score stable over rolling 7-day window
- Adaptive weights recommendations produce concrete "would recommend / would demote" verdicts per signal

### P1↔P2 bridge acceptance
- Every terminal journal row can be replayed within 500 ms
- Aggregate replay summary shows the platform's route choice outperformed the median alternative in ≥60% of cases
- Provider-level counter-factual signal available for every completed opportunity

### P2 acceptance
- ≥3 chains actively discovering (Base + 2 more)
- ≥6 flash-loan providers modelled (3 live, 3 shadow)
- ≥6 DEXes modelled per chain
- Opportunity Prediction endpoint returns non-null forecast horizon for ≥50% of tracked route fingerprints
- Daily Report emits successfully for 30 consecutive days

### P3 acceptance
- ≥3 scanner families activated (canonical scanner tree in production discovery)
- Autonomous Research producing ≥1 proposal per week for operator review
- Full alerting coverage: every kill-switch / mode-change / calibration-drift / worker-crash event surfaces in Telegram + audit log within 30 s
- **Opportunity Knowledge Graph (P3-8) built and queryable** — every asset / pool / route / provider / regime / opportunity / outcome represented as a node; graph queries return in <200 ms; graph is a strict materialised view (deletable + rebuildable from MID at any time)

### P4 acceptance
- Knowledge Hub answering operator queries with ≥90% factual accuracy against a fixed evaluation set
- Reinforcement Learning proposals accepted by operator at rate ≥40%
- Strategy Evolution running unattended with weekly operator-review cadence
- **Opportunity Knowledge Graph semantic layer live** — embedding-based similarity queries return meaningful nearest-neighbours; NL query surface answers ≥80% of a benchmark question set correctly

---

## 8. Changelog for this document

| Date | Change |
|---|---|
| 2026-08-02 | Initial ratification alongside v2.0.0 canonical release |
| 2026-08-02 | **Amendment:** renamed P1-α from "Market History Storage" to "Market Intelligence Database" (MID); expanded MID scope to 11 domains (market state · quotes · liquidity · gas · providers · routes · opportunities · confidence · decisions · outcomes · replay) under a single façade with no parallel storage systems. Moved MID to Sprint 1 (was Sprint 3 in the flash-loan capability audit) so the memory foundation exists before any producer starts producing. Added P3-8 Opportunity Knowledge Graph (foundation) and P4 semantic layer. Updated non-negotiables §6.5 + §6.8 to enforce MID as sole persistence surface. |

---

_This document is the platform roadmap. It is expected to be revised as capabilities land and priorities are re-validated against SHADOW telemetry. Amendments require a `docs/` PR and land alongside the release that first implements the amendment._
