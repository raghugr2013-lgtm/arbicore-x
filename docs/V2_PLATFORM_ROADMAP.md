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

#### P1-α — **Market History Storage** _(highest P1, first capability to build after deployment)_

> The permanent memory of the market itself.

- **New Mongo collection:** `market_history` — time-series (candle-style) of every observed price/depth per `(chain, dex, pair, adapter, timestamp)` tuple.
- **New background writer:** `MarketHistoryWriter` — asyncio task that snapshots at a configurable cadence (default 30 s) using the already-active Quoter registry. No new external dependencies beyond RPC.
- **Retention policy:** TTL index — 90 days rolling by default; configurable via UI (Settings → Historical Data). Deep-archive path documented in `docs/OPERATIONS.md` (mongodump + rclone).
- **Schema is additive.** No breaking migrations. New collection only.
- **Effort:** M (~1 week)
- **Deployment impact:** additive Mongo writes; ~few MB/day at default cadence and universe size.
- **Rationale:** every downstream P1/P2/P3 intelligence — volatility, seasonality, regime confirmation, opportunity prediction, replay learning — is either impossible or cripplingly incomplete without this.

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

**Aggregate P3 effort:** ~10–12 weeks, spread over the FULL_LIVE ramp.

---

### P4 — AI readiness (v2.3+)

- Knowledge Hub (vector store + doc ingestion + retrieval)
- Strategy Evolution (evolutionary / bandit loop that mutates policy toward observed reward)
- AI Research Assistant (LLM-assisted operator queries against the knowledge hub)
- Reinforcement Learning (actor-critic over mode / capital / adapter action space)

All P4 items are deferred, non-blocking, and gated on P2 + P3 being mature. Emergent LLM key already available in the deployment for when the platform is ready to consume it.

---

## 4. Priority matrix (final)

| Item | Original audit tier | New tier | Rationale for change |
|---|:-:|:-:|---|
| Market History Storage | P2 | **P1-α (top)** | First capability to build post-deploy — foundation for every downstream intelligence |
| Opportunity Lifetime Intelligence | P1 (partial) | **P1-β** | Permanent record of first_seen / last_seen / disappeared_at / lifetime / recurrence / survival probability |
| Historical Market Intelligence | (implicit in Historical Learning) | **P1-γ** | Learn from observed-but-not-executed — first-class in the roadmap now |
| Zero-risk activations (from audit Phase 3-A) | P1 | **P1-δ** | Stays P1; runs in parallel with α/β/γ |
| Replay & Outcome Intelligence (5 questions) | (implicit in Market Replay Engine) | **P1↔P2 bridge** | Elevated to bridge; explicit five-question contract |
| Provider Intelligence | P2 | **P2-1** | Retained |
| Borrow Optimization | P2 | **P2-2** | Retained |
| Capital Allocator (portfolio-aware upgrade) | P2 | **P2-3** | Retained |
| Multi-chain Optimization | P2 | **P2-4** | Retained |
| Opportunity Prediction | P2 | **P2-5** | Retained |
| Dormant scanner activation | P3 | **P3-1 / P3-2** | Retained |
| Additional protocol activation | P3 | **P3-3** | Retained |
| Autonomous Research | (implicit) | **P3-4** | Elevated to explicit P3 item |
| AI-generated strategy discovery | (implicit in P4) | **P3-5** | Elevated to explicit P3 item; consumes P4 knowledge hub when available |

---

## 5. Sequence & timing

```
   t=0            deploy v2.0.0 → VPS. Enter SHADOW mode. Collect market data.
   t=+1 wk        P1-δ activations complete (regime, outcome, stubs, drift)
   t=+2 wk        P1-α (Market History Storage) writing to Mongo
   t=+3 wk        P1-β (Opportunity Lifetime) live + endpoint surfaced
   t=+4 wk        P1-γ (Historical Market Intelligence) — backfill complete
   t=+5.5 wk      P1↔P2 bridge (Replay & Outcome Intelligence) live
                  → SHADOW → LIMITED_LIVE promotion authorisation gate opens
   t=+6 → +14 wk  P2 items land incrementally during LIMITED_LIVE ramp
   t=+14 wk       LIMITED_LIVE → FULL_LIVE for the first strategy
   t=+15 → +26 wk P3 items land during FULL_LIVE operation
   t=+26 wk+      P4 (AI readiness) begins
```

**Cadence:** one release per landed capability. Tag `v2.1.0` after P1-α, `v2.2.0` after P1↔P2 bridge, `v2.3.0` after full P2, `v3.0.0` when P4 begins introducing LLM-integrated flows.

---

## 6. Non-negotiables (governance layered on this roadmap)

These invariants extend `docs/ROADMAP.md` §7 and `CONTRIBUTING.md`:

1. **Additive-only Mongo schema** through every P1/P2/P3 release. No breaking migrations before v3.0.0.
2. **Dormant modules stay dormant until activated.** No implicit imports into `server.py`. Every activation moves the corresponding test file back from `tests/_pending_scanner_activation/`.
3. **No P2 work begins until at least P1-α is live.** Every downstream intelligence would be starved of data and produce misleading conclusions.
4. **Replay & Outcome Intelligence (the P1↔P2 bridge) is the SHADOW → LIMITED_LIVE gate.** A strategy may only be promoted to LIMITED_LIVE once its replay summary demonstrates the platform's decisions are outperforming plausible alternatives.
5. **Every capability writes to the journal or the market history store.** Nothing that produces observable state is allowed to exist as ephemeral in-memory data.
6. **Every learning surface exposes both an "executed" and an "observation-only" sample stream.** The platform never treats the two as equivalent nor discards either.
7. **AI/LLM-integrated flows (P4) never gate operator actions.** They are advisory. The operator always has the final signature.

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

### P4 acceptance
- Knowledge Hub answering operator queries with ≥90% factual accuracy against a fixed evaluation set
- Reinforcement Learning proposals accepted by operator at rate ≥40%
- Strategy Evolution running unattended with weekly operator-review cadence

---

## 8. Changelog for this document

| Date | Change |
|---|---|
| 2026-08-02 | Initial ratification alongside v2.0.0 canonical release |

---

_This document is the platform roadmap. It is expected to be revised as capabilities land and priorities are re-validated against SHADOW telemetry. Amendments require a `docs/` PR and land alongside the release that first implements the amendment._
