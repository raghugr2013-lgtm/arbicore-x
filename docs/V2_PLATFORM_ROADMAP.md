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
| **Providers** — per-capital-source availability + observed cost + revert-count snapshots (initially flash-loan providers; extensible to CEX venue accounts, margin credit lines, treasury allocations, institutional-credit facilities) | Provider Intelligence (P2); depth-aware borrow selection (Sprint 2 refinement) | `arbicore/execution/adapters.py` — no new adapters |
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
4. **No parallel systems** — the MID **replaces** any ad-hoc historical-state writes elsewhere in the codebase. Any producer discovered to write outside the façade during Sprint 1A is refactored to use the façade in the same PR.
5. **Zero new external dependencies** — every writer reuses already-active substrate (Quoter, Gas oracle, Adapter registry, Journal). The MID is a persistence layer, not a data-source expansion.

**Design invariant 6 — Strategy-agnostic. Platform-wide, not flash-loan-specific.**

The MID is designed as **the platform's permanent intelligence foundation**, not as a flash-loan-specific database. Every stored entity across all 11 domains carries the same additive metadata block:

```
{
  strategy_type:   "flash_loan_arbitrage" | "cex_dex_arbitrage" | "funding_rate" |
                   "liquidation" | "treasury_yield" | "institutional_credit" |
                   "cross_chain_arbitrage" | ...  (open enum, extensible)

  opportunity_type: "dex_arbitrage" | "multi_hop" | "triangular" |
                    "cex_dex" | "funding_delta" | "liquidation_call" |
                    "stablecoin_depeg" | "yield_arbitrage" | ...  (open enum)

  capital_source:  "flash_loan_aave_v3" | "flash_loan_balancer_v2" |
                   "flash_loan_uniswap_v3" | "wallet_burner" | "wallet_treasury" |
                   "cex_venue_binance" | "cex_venue_okx" | "margin_bybit" |
                   "credit_facility_prime_broker" | "vault_yield" | ...  (open enum)

  chain:           "base" | "arbitrum" | "optimism" | "polygon" | "ethereum" |
                   "solana" | "sui" | "off_chain_cex" | ...  (open enum,
                   "off_chain_cex" for CEX-only opportunities that touch no chain)

  protocol:        "uniswap_v3" | "aerodrome_slipstream" | "aave_v3" |
                   "balancer_v2" | "binance_spot" | "okx_spot" |
                   "bybit_perp" | "compound_v3" | ...  (open enum — any DEX, CEX,
                   lending market, perp venue, or credit protocol)

  execution_mode:  "shadow" | "paper" | "limited_live" | "full_live"
                                                        (closed enum — mode ladder)

  market_regime:   "UNKNOWN" | "CALM" | "VOLATILE" | "TRENDING" | "CHOP" | ...
                                                        (open enum; default "UNKNOWN"
                    at write time; regime engine — dormant until Sprint 1B —
                    back-annotates this field without schema change)

  tags:            [str]              // free-form tags, e.g. ["depeg", "usdc_bridge",
                                      //                        "high_volatility_regime"]
}
```

**Design invariant 7 — Replay-ready from day one.**

Every persisted MID row retains enough context to reconstruct the market moment later. In addition to the domain-specific payload, every row (where applicable) carries a `replay_context` block:

```
{
  block_number:            Optional[int]    // on-chain block at write time
  block_timestamp:         Optional[str]    // ISO-8601 UTC — chain-clock, not host-clock
  quote_snapshot_id:       Optional[str]    // stable ID of the mid_quotes row that
                                            //   captured the quote used at this moment
  liquidity_snapshot_id:   Optional[str]    // stable ID of the mid_liquidity row
  gas_snapshot_id:         Optional[str]    // stable ID of the mid_gas row
  route_snapshot_id:       Optional[str]    // stable ID of the mid_routes row
  decision_snapshot_id:    Optional[str]    // stable ID of the mid_decisions row
                                            //   (upstream gate verdict, if any)
  market_snapshot_id:      Optional[str]    // stable ID of the mid_market_state row
                                            //   for the same (chain, dex, pair, ts)
}
```

**Design invariant 8 — Stable canonical identifiers, no duplication.**

Every MID row exposes stable identifiers so downstream analytics reference by ID instead of duplicating payload:

| ID | Semantics | Assigned when |
|---|---|---|
| `mid_id` | Every row's own canonical UUID (v4). Stable for row lifetime. Primary key alternative to Mongo `_id`. | On write |
| `event_id` | Every `mid_opportunities` row's canonical event ID (`{opp_id}:{event_ordinal}`). Foreign-keyable from other domains. | On write |
| `route_id` | Stable fingerprint of a route (`{chain}:{family}:{in_token}→{out_token}:{dex_path_hash}`). Same route across weeks always resolves to the same `route_id`. | Computed on first observation, memoised in `mid_routes` |
| `provider_id` | Stable canonical provider identifier (`{provider_family}:{chain}` — e.g. `aave_v3:base`, `binance_spot:off_chain_cex`, `prime_broker_jump:off_chain`). | Registered in `mid.enums` + memoised in `mid_providers` |
| `market_snapshot_id` | Stable canonical ID for a market moment. Rows that describe the same market moment across domains share this ID. | Assigned by the first writer to observe the market moment; reused by subsequent writers at the same tick |

**Downstream contract:** any consumer that needs to correlate rows across domains **MUST** join by these IDs, never by duplicating payload. The Opportunity Knowledge Graph (P3-8) is expressed entirely in terms of these IDs.

**Consequences:**

- **v2.1.0 populates only flash-loan-family values** (`strategy_type = "flash_loan_arbitrage"`, `capital_source in {flash_loan_aave_v3, flash_loan_balancer_v2, flash_loan_uniswap_v3}`) — but the schema is not narrowed to those values.
- **Future strategy families require zero schema migration.** When CEX-DEX arbitrage launches (some later phase), its writer simply calls `mid.write_opportunity_event(..., strategy_type="cex_dex_arbitrage", capital_source="cex_venue_binance", chain="off_chain_cex", protocol="binance_spot", execution_mode="shadow", ...)`. All existing indexes, queries, endpoints, TTL policies, and analytics continue to work.
- **Every query surface accepts the metadata block as filters.** Endpoints like `/mid/query/opportunities?strategy_type=flash_loan_arbitrage&chain=base` and `/mid/query/outcomes?capital_source=cex_venue_binance` are supported from Sprint 1A.
- **No flash-loan-specific storage architecture exists anywhere in the codebase.** Any producer discovered to hardcode strategy assumptions (e.g. a Mongo write that omits `strategy_type`, or a collection named `flash_loan_*` outside the `mid_` namespace, or a schema that treats "borrow provider" and "capital source" as different things) is refactored in the same PR.

**Enum registry (`arbicore/data/mid/enums.py`):** open enums are registered in a single module with a `register(strategy_type="…")` helper. Registration is verified at process start; unknown values written to the MID emit a warning log and a `mid_enum_warnings` audit row rather than fail — the enum is a documentation surface, not a validation gate. This ensures new strategy families never crash Sprint-1A-era producers still running when Sprint-6+ strategies launch.

---

**Sprint 1 split (2026-08-02 amendment):**

**Sprint 1A — Pre-deployment (MID foundation only)**
- `arbicore/data/mid/` façade (`__init__.py`, `writers.py`, `readers.py`, `enums.py`, `schemas.py`)
- 10 new Mongo collections in the `mid_` namespace, each with the strategy-agnostic metadata block indexed alongside the domain-specific fields
- Per-domain TTL policies applied via `ensure_indexes()`
- 11 producers wired to the façade (see Sprint 1A step list in `V2_FLASH_LOAN_CAPABILITY_AUDIT.md` §8)
- Query endpoints: `GET /api/arbicore/mid/status`, `GET /api/arbicore/mid/query/{domain}?...` — with metadata filters
- Settings UI card: **Settings → Market Intelligence Database** (per-domain TTL + cadence)
- Regression: all 1442 existing tests must still pass; new MID tests added
- **Deliverable of Sprint 1A:** the platform can be deployed to the VPS in SHADOW mode with the MID capturing every observation from t=0. Sprint 1A produces a tagged release (`v2.0.1` — MINOR).

**Sprint 1B onward — Post-deployment, MID-consuming work**
Sprint 1B (formerly "Sprint 2") through Sprint 5 continue on the deployed platform. From the moment the VPS is up, the MID is accumulating data; every subsequent sprint reads from and writes to the MID that is already live. No code lands on the VPS between Sprint 1A and Sprint 1B — the VPS accumulates data unimpeded while development continues in the canonical repo.

**Effort:**
- Sprint 1A (pre-deploy): **~1 week** — MID façade + 10 collections + 11 producers + query endpoints + Settings card + regression. Producers wire minimal happy-path writes; Sprint 1B expands the write contents as new information sources come online.
- Sprints 1B–5 (post-deploy): ~5 weeks total, unchanged from prior plan.

**Deployment impact (Sprint 1A):** ~10 new Mongo collections (all additive, all under the `mid_` prefix, all indexed on `strategy_type` + `chain` + timestamp); one new background writer per domain (11 total, batched writes 30–300 s cadence); no new external calls.

**Rationale for the 1A/1B split (operator directive, 2026-08-02):** deploying with the MID complete but without downstream analytics gives the VPS a running head start — every second on the VPS is a second of accumulated market intelligence, even while Sprint 1B–5 development continues in the canonical repo. Waiting for all analytics before deploying costs us that head start irreversibly.


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

## 5. Sequence & timing (revised — Sprint 1A/1B split, deploy after 1A)

```
   t=0            Canonical repo at v2.0.0. Not yet deployed.
   t=+1 wk        SPRINT 1A · P1-α  Market Intelligence Database — foundation
                     → façade + 10 collections + 11 producers + query endpoints
                     + Settings card + regression green + strategy-agnostic
                       metadata block on every entity
                     → Tag v2.0.1 (MINOR — additive)
   t=+1 wk        ▶ DEPLOY v2.0.1 → VPS in SHADOW mode
                     From this moment, every market observation is permanently
                     recorded. VPS accumulates MID data continuously while
                     development continues in the canonical repo.
   t=+2 wk        SPRINT 1B · P1-δ  Activate dormant intelligence
                     → Confidence · ROI · Route Ranking · Economics · Regime
                       · Entity Scoring — every activation wires its persistence
                       through the deployed MID
   t=+3 wk        SPRINT 3 · P1-β  Opportunity Lifetime Intelligence
                     → first_seen / last_seen / disappeared_at / lifetime
                       / recurrence / survival probability
   t=+4 wk        SPRINT 4 · P1-γ  Historical Market Intelligence
                     → observation_only sample class + backfill
   t=+5 wk        SPRINT 5 · Replay & Outcome partial + Stablecoin Depeg gate
                     + regression + certification + package v2.1.0
                     → SHADOW → LIMITED_LIVE promotion authorisation gate opens
   t=+5 → +13 wk  P2 items land incrementally during LIMITED_LIVE ramp
   t=+13 wk       LIMITED_LIVE → FULL_LIVE for the first strategy
   t=+14 → +26 wk P3 items land during FULL_LIVE operation
                     → P3-8 Opportunity Knowledge Graph foundation lands here
   t=+26 wk+      P4 (AI readiness) begins
                     → P4 semantic layer over Knowledge Graph lands here
```

**Cadence:**
- **Sprint 1A → tag `v2.0.1`** (MINOR — additive: MID + strategy-agnostic metadata + 10 collections + 11 producers + query endpoints)
- Sprints 1B–5 → tag `v2.1.0` cumulative on the deployed VPS
- Full P2 lands as `v2.2.0`
- `v3.0.0` when P4 begins LLM-integrated flows

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
| 2026-08-02 | **Amendment:** split Sprint 1 into **Sprint 1A (pre-deployment)** and **Sprint 1B onward (post-deployment)**. Sprint 1A ships only the MID foundation, tagged as `v2.0.1`, then the platform is deployed to the VPS in SHADOW mode. From that moment the VPS is continuously recording market intelligence while Sprints 1B–5 continue development in the canonical repo. Added **Design invariant 6 — Strategy-agnostic** to the MID: every stored entity carries a `{strategy_type, opportunity_type, capital_source, chain, protocol, execution_mode, tags}` metadata block, making the MID the permanent intelligence foundation for the entire ArbiCore X platform — not a flash-loan-specific database. Future strategy families (CEX-DEX, funding, treasury, liquidation, institutional credit, cross-chain) populate the same MID with different metadata values; zero schema migration required. |
| 2026-08-02 | **Amendment:** Sprint 1A architectural amendments (operator-approved). (1) Replay-readiness from day one — every persisted MID row carries a `replay_context` block (`block_number`, `block_timestamp`, `quote_snapshot_id`, `liquidity_snapshot_id`, `gas_snapshot_id`, `route_snapshot_id`, `decision_snapshot_id`, `market_snapshot_id`) sufficient to reconstruct the market moment. (2) Stable canonical identifiers — every row carries `mid_id`; opportunity events carry `event_id`; routes carry `route_id`; providers carry `provider_id`; market moments carry `market_snapshot_id`. Downstream analytics reference by ID, never by payload duplication. (3) Metadata block extended with `market_regime` (default `"UNKNOWN"`; regime engine — dormant until Sprint 1B — back-annotates without schema change). (4) After Sprint 1A regression is green, immediately package and deploy `v2.0.1` to VPS in SHADOW mode — do not wait for Sprint 1B. |

---

_This document is the platform roadmap. It is expected to be revised as capabilities land and priorities are re-validated against SHADOW telemetry. Amendments require a `docs/` PR and land alongside the release that first implements the amendment._
