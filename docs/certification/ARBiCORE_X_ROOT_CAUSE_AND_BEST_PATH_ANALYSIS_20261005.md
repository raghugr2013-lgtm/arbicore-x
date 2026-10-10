# ArbiCore X — Root-Cause and Best-Path Analysis

**Date:** 2026-10-05 (production state re-checked 2026-10-06)
**Role:** independent principal architect / trading-system reviewer
**Mode:** read-only. No source edit, deploy, restart, configuration change, database write, gate change, signing, or broadcast. This file is the only artifact created.
**Deployed code reviewed:** `823a79b` (worktree `/tmp/arbicore-b1b2-reconcile-9ed2718`), container `arbicore-x-backend-new`.

Every major conclusion carries one of three labels:

- **EVIDENCE-BACKED**: measured in our own data, read in our code, or stated in a primary public source cited here.
- **STRONG INFERENCE**: follows from several pieces of evidence, but was not measured directly.
- **HYPOTHESIS**: plausible, not yet tested. Each one is paired with the test that would settle it.

---

## 1. Executive conclusion

**ArbiCore X is not failing because its code is bad. It is failing because it chose the most competed, least profitable slice of on-chain trading, and then built a discovery system that is about 1,000× too slow to compete in that slice even if it were profitable.** The audit loop is a symptom: when a system cannot find an edge, every audit finds the same nothing, and that nothing gets re-read as a coverage gap.

The five facts that decide this:

1. **No edge exists in the universe we observe.** In a 30-minute production window, 33,311 candidates were discovered and 768 verified. All 180 that received a real quote had negative gross, from −$59 to −$1,710. The best Base route is a −0.091% round trip between two pools whose combined fee is about 0.10%: those pools sit inside their no-arbitrage band. **EVIDENCE-BACKED.**
2. **The market's typical arbitrage is two to three orders of magnitude smaller than our floor.** Across five EVM chains in the 30 days to 29 August 2026, 97.2% of credible arbitrages earned under $1, 2.8% earned $1–$100, and 0.035% earned more than $100. Base averages $0.43 per arbitrage in 2026, a 0.25% return on committed capital, and roughly $170 of notional per trade. Gate 7 plus the 0.5-point MEV haircut needs about 0.80% gross at $10k notional. That is about 3× the average Base margin, at roughly 60× the average Base trade size. **EVIDENCE-BACKED** (Bitquery 2026 investigation; arithmetic is ours).
3. **The market is shrinking and concentrated.** Base credible arbitrage profit fell from $25.9M in 2024 to $20.7M in 2025, and to $6.0M in the first eight months of 2026 (about $25k a day for the whole chain). That is shared by about 1,300 executor contracts. Two entities produce more than 80% of Base spam. **EVIDENCE-BACKED.**
4. **ArbiCore cannot see a one-block opportunity.** Discovery is a 60-second poller feeding a Mongo queue. It verifies about 2–3% of what it discovers, with a median discovery-to-verification delay of about 14 minutes. Base orders transactions by priority fee inside 200 ms Flashblocks. **EVIDENCE-BACKED.**
5. **Where real ≥ $25 arbitrages were found, competition took the value.** In the Ethereum replay (E1.6), winners paid builders $30–$111 of $31–$119 opportunities and kept $1–$13. **EVIDENCE-BACKED** (one hour, small sample).

**Decision.** Stop building strategy, discovery, and certification capability for generic DEX atomic arbitrage. Do two things only:

- **(a) Fix the live security exposure.** It exists today regardless of trading. Three legacy backends share production state and secrets, and production logs its RPC key about 1,600 times per hour.
- **(b) Run one cheap, decisive, public-data experiment.** Measure the size, concentration, and reaction time of the ≥ $25 arbitrage tail on Base and Arbitrum. If that tail is too small, too concentrated, or won inside the triggering Flashblock, stop atomic DEX arbitrage for good. If it passes, run the per-Flashblock measurement and the engineering transaction in parallel, then a tightly bounded canary.

**This revises my own memo of earlier today** (`FIRST_LIVE_PATH_DECISION_MEMO_20261005.md`):

- The 72-hour per-block measurement is no longer the first experiment. Its prior is low, and a one-day public-data census can kill the thesis more cheaply.
- The engineering transaction (LIVE 0) has almost no decision value if the census fails, so it moves behind the census.
- The memo's "≥ 3 states in 72 hours" pass bar proves existence, not viability. Section 21 replaces it.

Two factual corrections:

- The legacy containers hit the **fallback-tier** RPC keys, not production's primary tier.
- **Production itself** also logs its full Alchemy URL, key included.

---

## 2. Current-state diagnosis

Production state as verified on 2026-10-06 (credential values not reproduced):

| Item | State | Label |
|---|---|---|
| Production backend | `arbicore-x-backend-new`, image `phase0-823a79b`, `EXECUTION_MODE=SHADOW` | EVIDENCE-BACKED |
| Provenance | `823a79b` still absent from GitHub. Container label `arbicore.gitsha=2a6fadb8…` (wrong) | EVIDENCE-BACKED |
| Legacy backends | `b7-candidate`, `h05` and `w1` are still running with `DB_NAME=arbicore_x` on `factory-mongo`. Their `VAULT_KEY` and `JWT_SECRET` hashes are identical to production's | EVIDENCE-BACKED |
| RPC 429s, last hour | Production 1. Legacy 1,720 / 2,810 / 2,789 | EVIDENCE-BACKED |
| Log lines containing a full Alchemy key URL, last hour | Production about 1,600. Each legacy container about 1,700–2,000 | EVIDENCE-BACKED |
| H05 exact sizing | `ARBICORE_BORROW_SIZER_ENABLED=true`, `ARBICORE_PRICE_FEED_ENABLED=true`. The "probe → zero confirms" trap is **not** active in production | EVIDENCE-BACKED |
| T2 per-block Base searcher | `ARBICORE_T2_SEARCHER_ENABLED=true`, but no WSS variable is set, so it is inert | EVIDENCE-BACKED |
| Base executor | V1 `FlashLoanReceiver`. Repayment is enforced, there is no on-chain minimum profit, it holds no funds, and it has never traded | EVIDENCE-BACKED |

The discovery funnel in one 30-minute production window (2026-10-05 05:27–05:57 UTC):

| Stage | Count | Note |
|---|---|---|
| Candidates discovered | 33,311 | Ethereum 8,586 · Arbitrum 8,208 · Polygon 6,777 · Base 4,916 · Optimism 2,808 · BNB 2,016 |
| Verified in window | 768 (2.3%) | 33,299 discovered rows were still unclaimed at query time |
| Denied `venue_unreadable` | 480 | 448 of them on Ethereum |
| Real quote and economics | 180 | Base only 29, i.e. about one Base economic evaluation per minute |
| Gross ≥ 0 | **0** | Net range −$1,710 to −$59, median −$194 |

Two distinct scanner workers (`flash_loan_arb:33291a96`, 480 bundles, all `venue_unreadable`; and `flash_loan_arb:0eb9228c`, 180 bundles) wrote to the same database in that window. I could not attribute them to containers from the logs. That a legacy backend is polluting canonical evidence is a **HYPOTHESIS**, but it is consistent with the shared-database finding, and the fix (section 16, F1) is the same either way.

---

## 3. Root-cause ranking

"Why are we suffering?" ranked by how much each cause explains the absence of a profitable trade. Several causes are coupled: 1 and 2 are the economic reason, and 3 is the engineering reason we could not have known sooner.

| Rank | Cause (from the list) | Verdict | Label |
|---|---|---|---|
| 1 | **7. Weak strategy** | Generic atomic DEX arbitrage on blue-chip pools is commoditized. The observed universe is pools at the edge of their fee band. The ≥ $25 tail is a tiny fraction of a small market. | EVIDENCE-BACKED for our universe; STRONG INFERENCE for the class |
| 2 | **6. MEV competition + 5. Market conditions** | About 1,300 Base contracts; two entities produce more than 80% of spam; Base arbitrage profit is down about 3.5× annualized since 2024. On Ethereum, builders take most of the value. | EVIDENCE-BACKED |
| 3 | **4. Wrong discovery model + 9. Latency** | Discovery is a poller and queue with a ~14-minute median versus 200 ms Flashblocks. Even a real opportunity would be invisible. | EVIDENCE-BACKED |
| 4 | **8. Insufficient venue coverage** | On Base, 95% of arbitrage trades are Uniswap-vs-PancakeSwap or intra-Uniswap. ArbiCore's Base registry is 30 hand-picked blue-chip Uniswap V3 and Aerodrome pools, with no PancakeSwap and no Uniswap v4. Our own E1.6 data shows extra coverage adds opportunities whose value is then bid away. | EVIDENCE-BACKED for the gap; STRONG INFERENCE that closing it alone would not produce profit |
| 5 | **11. Production engineering** (process) | About 109k Python lines and ~90 certification documents around a hot path that serious searchers write in a few thousand lines. Shared production state and leaked credentials. This consumed the time that should have gone to one decisive measurement. | EVIDENCE-BACKED |
| 6 | **10. Profitability model** | Miscalibrated (fixed $10k size, flat 0.5-point MEV penalty, no priority fee, no failed-transaction cost, no L1 data fee on the Gate 7 path). It is **not** why we have zero trades, since gross is already negative. It will matter only if an edge appears. | EVIDENCE-BACKED |
| 7 | **2. Incomplete wiring** | The T2 searcher is inert (no WSS), the loss loop is not wired, and the V2 executor is not deployed. These block LIVE, not discovery. | EVIDENCE-BACKED |
| 8 | **3. Wrong architecture** | For the current goal, the hot path is wrong (rank 3). The safety architecture is sound. | STRONG INFERENCE |
| 9 | **1. Bad code** | Not a material cause. The code is mostly sound or ordinary debt, and has no correctness bug that hides profit. | EVIDENCE-BACKED (code review, section 4) |
| — | **12. Combination** | Yes: 1+2 (economics) × 3 (blindness) × 5 (process). | — |

---

## 4. Code-quality assessment

Scope: discovery, quoting, sizing, economics, searcher, execution, RPC, concurrency, tests, at `823a79b`. Classes:

- **A** production blocker
- **B** ordinary debt
- **C** unnecessary sophistication
- **D** sound

| Area | Finding | Class |
|---|---|---|
| Economics identity | `gross_is_quote_inclusive=True`, so swap fees are not counted twice. The flash fee is counted once (`economics.py:192-216`) | **D** |
| Quoting | Chained on-chain QuoterV2/router `eth_call` with exact amounts. Correct, but slow | **D** (correctness) / **B** (latency) |
| Gates 7/8/9 | Fail-closed, consistent (`filter.py:32-140`) | **D** |
| Broadcast ladder | Single `eth_sendRawTransaction` site, preflight, revalidation at $25 + $10 | **D** |
| RPC handling | Ordered failover, 429 backoff, chain-id check | **D** |
| Block pinning | Each hop is quoted at `latest`; `quote_block = max(hops)`, so there is no single pinned block | **B** |
| Verification | Sequential over a claim batch of 32, plus a 140 ms per-host throttle | **B** |
| Sizing | Fixed $10k. A grid optimizer exists but is off the verifier path; no continuous size search | **B** |
| MEV term | Flat 0.5 percentage points (about $50 on $10k). All 180 stored rows were labelled MEDIUM | **B** (false pessimism) |
| Gas | Static per-chain table; the L1 data fee lives on a parallel path, not Gate 7 | **B** |
| Transaction type | Legacy `gasPrice`. No EIP-1559 priority fee, no private submission (`MevRouter` is metadata only) | **B** |
| Nonce / concurrency | `pending` nonce at send, no broadcast lock. AutoExecutor polls every 30 s | **B** |
| Errors | About 593 `except Exception` blocks; the scanner tick swallows everything | **B** |
| Tests | About 385 files and 3,300 tests, mostly mocks; the fork end-to-end test is opt-in | **B** |
| Duplication | Two calldata stacks, two executor interfaces, three sizers, two gas paths, two discovery engines | **C** |
| Size | `server.py` is 8,750 lines; about 81k lines in `arbicore/` | **C** |
| T2 searcher | Parallel SHADOW engine with local V2/single-tick V3 math, fixed `amount_in=1.0`, 30 pools | **C/D** |
| Learning, intel, certification, readiness modules | Built for a strategy that has no edge | **C** |

**Class A (genuine production blockers):** none for SHADOW. For LIVE, the blockers are production and security items, not code quality (section 11). The code survey's "H05 off → zero confirms" is not active, because both flags are on in production.

**Conclusion:** bad code is not why ArbiCore has no trades. The code is careful, defensive, and over-engineered for its job. **EVIDENCE-BACKED.**

---

## 5. Wiring assessment

**Answer to "are opportunities absent, or are we failing to detect them?": both, in different places.**

- **In the universe we watch** (blue-chip Uniswap V3 / Aerodrome pools at $10k), opportunities are **absent**. The pools sit at their fee band, every quote is negative, and two windows agree. **EVIDENCE-BACKED.**
- **In the market as a whole**, opportunities **exist and we fail to detect them**:
  - On Base, roughly 58k credible arbitrages a day; 3,760 flash-loan transactions in our own Base sample slices came from 137 distinct recipients.
  - Our cadence cannot see them: about one Base evaluation per minute versus about 300 Flashblocks per minute.
  - Our universe excludes where they happen: no PancakeSwap or Uniswap v4 on Base, no long-tail tokens, a 30-pool registry.
  - **EVIDENCE-BACKED** for existence and blindness. **STRONG INFERENCE** that most of them are below $1.

| Wiring item | State | Label |
|---|---|---|
| Block-driven vs periodic | Periodic 60 s tick. The T2 block-driven engine is inert | EVIDENCE-BACKED |
| Event ingestion / pool state | None on the canonical path. T2 has WSS `newHeads`/logs (2 s blocks, not 200 ms Flashblocks) | EVIDENCE-BACKED |
| Quote freshness | Minutes. Per-hop `latest`, 5 s cache, p50 discovery→verification about 14 minutes, 0% within one block | EVIDENCE-BACKED |
| Verification throughput | About 2–3% of discoveries are ever verified; candidate TTL 900 s means the rest expire | EVIDENCE-BACKED |
| Venue coverage on Base | Uniswap V3 (4 fee tiers), Aerodrome Slipstream and classic. No PancakeSwap, no Uniswap v4, no Curve | EVIDENCE-BACKED |
| Token coverage | Blue chips plus AERO/DEGEN. No long-tail or launch tokens | EVIDENCE-BACKED |
| Route generation | DFS, 4 hops, 64-candidate cap, 5 s wall clock, TVL ≥ $100k; both directions | EVIDENCE-BACKED (sound) |
| Sizing | Fixed $10k; no optimal size per route | EVIDENCE-BACKED |
| Concentrated liquidity | Exact via on-chain quoter; T2 uses single-tick math (wrong when a trade crosses ticks) | EVIDENCE-BACKED |
| Mempool visibility | None. Base has no public mempool; ordering happens inside the sequencer's builder | EVIDENCE-BACKED (Base docs) |
| Opportunity persistence | Never measured at block or Flashblock granularity | EVIDENCE-BACKED (gap) |

---

## 6. Market assessment

**Can a generic DEX arbitrage system reasonably expect ≥ $25 net opportunities today?** Not on blue-chip pools at the edge of their fee band. In the long tail they exist, but they are rare and won within the triggering Flashblock. **STRONG INFERENCE**, tested by the census in section 21.

Evidence:

- **Size and trend.** Base credible arbitrage profit was $25.9M in 2024, $20.7M in 2025, and $6.0M in January–August 2026 (about $9M annualized). Profit per trade fell from $2.06 to $0.43. Distinct executor contracts went from 1,918 to 1,296. **EVIDENCE-BACKED** (Bitquery, ["Crypto Arbitrage in 2026"](https://bitquery.io/investigations/crypto-arbitrage-69-cents)).
- **Distribution.** Across five chains, 47.7% of trades earn under 1¢ (net negative after fees), 49.5% earn 1¢–$1, 2.8% earn $1–$100, and 0.035% earn over $100. Fewer than 3,000 trades a month earn a third of all profit. **EVIDENCE-BACKED** (same source).
- **Margin.** Base return on committed capital is 0.272% over 12 months (0.25% in 2026). Every chain sits within 0.3 percentage points of the others. **EVIDENCE-BACKED.**
- **Where it happens on Base.** Uniswap vs PancakeSwap is 48.6% of trades; inside Uniswap alone is 46.3%, and the intra-Uniswap route earns about 6× the margin. **EVIDENCE-BACKED.**
- **Spread compression on our pairs.** Base USDC/WETH Uniswap V3 at 5 bps vs Slipstream at about 5 bps gives a −0.091% best round trip: the pools are inside the fee band. **EVIDENCE-BACKED.**
- **Block frequency and ordering.** Base produces 2 s blocks built as ten 200 ms Flashblocks. Ordering is by priority fee *at selection time*, and once a Flashblock is broadcast its order is locked. **EVIDENCE-BACKED** ([Base transaction ordering](https://docs.base.org/specifications/transactions/transaction-ordering)). The Denim upgrade (native 200 ms blocks) is planned for Sepolia in October 2026 and mainnet in November 2026. **EVIDENCE-BACKED** ([Denim overview](https://docs.base.org/upgrades/denim/overview)).
- **Lifetime.** CEX-DEX price gaps on rollups lasted 10–20 blocks on average. That is pre-Flashblocks data, and it is *non-atomic* value worth 0.03–0.05% of volume ([arXiv 2406.02172](https://arxiv.org/abs/2406.02172)). The companion paper "Layer-2 Arbitrage: An Empirical Analysis of Swap Dynamics and Price Disparities on Rollups" reports a decay of about 420 s on Base. Atomic DEX-DEX gaps are closed by on-chain probes or targeted bots within the same or next Flashblock. **STRONG INFERENCE** from the probing and spam literature.
- **Realistic execution window** for an atomic DEX-DEX arbitrage on Base: one Flashblock (≤ 200 ms) after the triggering swap becomes visible. **STRONG INFERENCE.**

---

## 7. Strategy assessment

Current model: price discrepancy → quote → flash loan → execute → repay → profit.

**Classification: D for blue-chip generic atomic DEX arbitrage (economically obsolete or commoditized), and at best C for specialized long-tail classes (viable only for specialized opportunity classes, and those still need B-level execution).** **STRONG INFERENCE**, tested by the census.

Reasons:

1. The class is the most crowded in MEV, with about 1,300 Base contracts, and its typical trade earns well under a dollar. **EVIDENCE-BACKED.**
2. Flash loans are not an edge on L2s. Base arbitrage notional averages about $170, which bots hold as inventory. A flash loan adds a fee (5 bps on Aave) and gas. **STRONG INFERENCE.**
3. The value that does exist sits in long-tail tokens, token-launch shocks, and intra-Uniswap fee-tier and v4 routes. Capturing it needs fast pool discovery and reaction within one Flashblock. **EVIDENCE-BACKED** (Bitquery route mix; "To Wait or To Probe" token-launch episode).
4. Our own realized-arbitrage replays (E1–E1.6) found ≥ $25 surpluses, but builders were paid almost all of them. **EVIDENCE-BACKED** (Ethereum, one hour).

---

## 8. MEV competition assessment

| Chain | How competition is paid | Our position | Label |
|---|---|---|---|
| Ethereum | Builder auction. Naked arbitrage: 915,194 bundles, mean $57.40, median $3.15, mean 67% paid to builders (libMEV, Sep 2024–Aug 2025). Bitquery: operators keep 41.3% of surplus. E1.6: winners kept $1–$13 of $31–$119 | Hopeless without builder relationships | EVIDENCE-BACKED |
| Base | No in-transaction bribe market; competition is priority fees, latency, and spam probes. On-chain "optimistic" arbitrage used >50% of Base gas in Q1 2025, but paid under a quarter of fees, with a success rate of 0.58% for top contracts. Probabilistic search is 23% of arbitrage activity but 95% of spam; Flashblocks select *against* broad on-chain probing and favour targeted search | Targeted per-Flashblock search is the only plausible design for us; we have none running | EVIDENCE-BACKED ([Flashbots](https://writings.flashbots.net/mev-and-the-limits-of-scaling), [AFT 2025 Optimistic MEV](https://arxiv.org/abs/2506.14768), ["To Wait or To Probe"](https://arxiv.org/abs/2606.00720)) |
| Arbitrum | Timeboost express lane plus FCFS. Smallest field (380 contracts), $0.39 per trade | Same latency problem | EVIDENCE-BACKED (Bitquery) |
| CEX-DEX (Ethereum) | Three searchers took three-quarters of volume and value; profitability is tied to builder integration | Not accessible | EVIDENCE-BACKED ([arXiv 2507.13023](https://arxiv.org/abs/2507.13023)) |

**Can ArbiCore compete architecturally? No, not today.** It has no event-driven state, no pending-state simulation, no optimal sizing, no priority-fee bidding, no private or revert-protected submission, and Python plus Mongo on the hot path. **EVIDENCE-BACKED** for the gaps; that it cannot compete is a **STRONG INFERENCE**.

---

## 9. Latency assessment

Lifecycle of the current canonical path. Budgets come from code; medians from production data.

| Stage | Current | What a competitive targeted searcher does (Base) |
|---|---|---|
| State change → detection | 0–60 s tick, plus DFS ≤ 5 s per chain and borrow token | Flashblock WSS push, ≤ 200 ms (~10–50 ms after publish) |
| Detection → quote | Queue claim backlog. p50 discovery→verification about 844 s; 2–3% ever verified | In-memory, < 5 ms |
| Quote | Sequential per-hop `eth_call` (150–300 ms + 140 ms throttle per hop) | Local AMM math or revm on cached state, < 1 ms per route |
| Candidate storage | Mongo upsert, then claim | None on the hot path (log asynchronously) |
| Gate 7 | Milliseconds | Same |
| Transaction construction | `eth_call` + `estimateGas` + vault decrypt (~2–3 RPC round trips) | Pre-signed template, gas from simulation, < 5 ms |
| Submission | Public RPC, legacy `gasPrice` | Direct to sequencer RPC with an EIP-1559 priority fee; on-chain minimum profit |
| **Total** | **Minutes (p50 ≈ 14 min)** | **≈ 50–250 ms** |

**Can this capture a one-block opportunity? No.** The gap is about 3–4 orders of magnitude. **EVIDENCE-BACKED.**

**Minimum redesign, if and only if the census passes.** The hot path becomes one in-process loop:

1. Subscribe to Base Flashblocks (`newFlashblocks` / `pendingLogs`).
2. Update an in-memory pool state (V2 reserves; V3 `slot0` plus initialized ticks).
3. Look up only the cycles that touch the changed pools.
4. Compute exact output at the pending state with local math, cross-checked against `eth_simulateV1` (which runs on the pre-confirmed Flashblock state) or revm.
5. Size with closed-form or golden-section search.
6. Build calldata for the **V2** executor (on-chain `minProfit`).
7. Send an EIP-1559 transaction with a priority fee derived from the expected profit.

Mongo, the queue, the certification bundle, and the evidence bus move off the hot path to asynchronous logging. The existing T2 module is the nearest starting point, but it needs Flashblocks instead of `newHeads`, multi-tick V3 math or simulation instead of single-tick math, optimal size instead of `amount_in=1.0`, and a census-driven pool set instead of 30 hand-picked pools. **STRONG INFERENCE.**

---

## 10. Economic model assessment

| Cost element | Handled? | Direction of error | Label |
|---|---|---|---|
| Pool fees | Yes, inside the quote; not double-counted | Sound | EVIDENCE-BACKED |
| Flash-loan fee | Yes, once (Aave 5 bps, Balancer 0) | Sound | EVIDENCE-BACKED |
| Gas (L2 execution) | Static table ($0.15 on Base, scaled by gas units) | Roughly right on Base | EVIDENCE-BACKED |
| L1 data fee | Not in Gate 7 (parallel path only) | **Falsely optimistic** (small on Base post-4844) | EVIDENCE-BACKED |
| Slippage / price impact | Inside the exact-size quote | Sound at the quoted size, but only one size | EVIDENCE-BACKED |
| Quote freshness | Minutes old; per-hop `latest`, not pinned | **Stale.** Can go either way; on competed pairs it is optimistic | EVIDENCE-BACKED |
| MEV | Flat 0.5 points ≈ $50 on $10k. On Base there is no bribe market inside the transaction; competition cost is priority fee plus failed attempts, not proportional to notional | **Falsely pessimistic** on Base; directionally right on Ethereum | EVIDENCE-BACKED |
| Priority fee | Not modelled; legacy `gasPrice` | **Falsely optimistic** | EVIDENCE-BACKED |
| Builder payment | Proxied only by the MEV term | Missing explicit model (Ethereum: 49–67% of value) | EVIDENCE-BACKED |
| Execution probability | Not modelled (implicitly 1) | **Falsely optimistic** | EVIDENCE-BACKED |
| Failed-transaction cost | Not modelled | **Falsely optimistic** (cents on Base; dollars on Ethereum) | EVIDENCE-BACKED |
| Opportunity decay | Not modelled | **Falsely optimistic** | EVIDENCE-BACKED |
| Double counting | Fixed (`gross_is_quote_inclusive`) | None remaining found | EVIDENCE-BACKED |
| Size | Fixed $10k, about 60× the average Base arbitrage | Prices impact at a size the market does not trade | EVIDENCE-BACKED |

**Effective bar today.** At $10k notional on Aave, Gate 7 requires roughly $25 + $5 flash fee + $50 MEV + $0.15 gas, i.e. about 0.80% gross. Pre-broadcast revalidation ($35) requires about 0.90%. The Base average realized margin is 0.25%.

The model's errors cancel in an unhelpful way. It is too pessimistic on MEV and size, so it would reject some real Base opportunities. It is too optimistic on probability, decay, and priority fee, so it would accept unwinnable ones.

None of this explains the zero-trade result, because gross is negative before any of these costs. **Do not change Gate 7 or the MEV term in production.** In the measurements below, record gross, net-before-MEV, and net-after-MEV separately, so a calibrated competition cost can be estimated from data instead of argued.

---

## 11. Production / security assessment

The findings to verify, each re-checked on 2026-10-06:

| Finding | Verified state | Severity |
|---|---|---|
| Old backend containers share production DB/state | **True.** Three legacy backends run on `arbicore_x` / `factory-mongo` with scanner autostart. Two distinct scanner workers wrote to the canonical collections in one window | **CRITICAL** (before any key is loaded; HIGH today) |
| Shared vault / JWT secrets | **True.** Identical `VAULT_KEY` and `JWT_SECRET` hashes in all four containers | **CRITICAL** (same) |
| Live RPC 429s | **True for legacy** (1,720–2,810 per hour on fallback-tier keys); production 1 per hour | **MEDIUM**. Resolved by isolating the legacy backends |
| `realized_loss_usd` not written | **True.** Read in `capital_policy.py:173-192`; no writer anywhere | **HIGH** for LIVE 1; NOT A REAL BLOCKER for LIVE 0 |
| Circuit breaker gets no real outcomes | **True.** `CircuitBreaker.record_outcome` has no caller on the broadcast path, and its state is in memory | **HIGH** for LIVE 1; NOT A REAL BLOCKER for LIVE 0 |
| Capital sizing tied to wrong/empty wallet | **True.** Capped at 20% of the gas-wallet balance, which is empty, and that is not the sending wallet. Also `policy.get(k) or DEFAULT[k]` turns an operator `0` into the default (e.g. `max_daily_loss_usd=0` becomes $100) | **HIGH** for LIVE 1 (fails closed today); the `or DEFAULT` bug is **MEDIUM** because it inverts safety intent |
| Credential exposure (general) | **True.** Admin password is plaintext in the container env, guessable, and the UI is public | **CRITICAL** before LIVE; **HIGH** today |
| Admin password exposure | Same as above. The operator role can arm modes and disengage the kill switch | **CRITICAL** before LIVE |
| RPC key in logs | **True, including production** (~1,600 lines per hour) | **HIGH** (quota theft or abuse; not fund loss) |
| Executor V1 lacks on-chain minimum profit | **True.** V2 with `ProfitBelowMinimum` exists in source, not deployed. Loss is bounded to gas by atomic repayment | **HIGH** for LIVE 1; NOT A REAL BLOCKER for LIVE 0 |
| Base mainnet USDC in Technical Validation | **True.** Defaults to Sepolia USDC (`technical_validation.py:51-52,184`) | **MEDIUM** (blocks LIVE 0 only; ~2 hours) |
| Vault signer integration in Technical Validation | **True.** Reads `ARBICORE_VALIDATION_SIGNER_KEY` from env, labelled "testnet only"; `amountOutMin=0` | **HIGH** for LIVE 0 (raw key visible to `docker inspect` and to shared-env containers) |

**Canonicality.** The deployed commit is still not on GitHub; the container label is wrong; the launch override still lives in `/tmp`. Content matches `823a79b`. **Severity: MEDIUM.** It does not block SHADOW or the census; it must precede any deploy that carries LIVE code.

**Minimum remediation, about half a day, no refactor:**

1. Push the branch containing `823a79b` and tag it.
2. Commit the override into the repo's compose `.env`.
3. Build only from a clean checkout of the tag.
4. Verify five identities: tag SHA, image label, container label, `BUILD_INFO`, content diff.
5. Write one deploy record per deploy, instead of SHA-stamping commits.

This is unchanged from my memo; I still agree with it.

---

## 12. Open-source benchmark

Status checked through the GitHub API on 2026-10-05. Being public is not evidence of profitability; several of these warn explicitly that they are not profitable.

| Project | Discovery | Pool state | Route / sim / sizing | Submission / competition | Status | Profitable today? |
|---|---|---|---|---|---|---|
| [flashbots/simple-arbitrage](https://github.com/flashbots/simple-arbitrage) (TypeScript) | Every block | Local V2 reserves via a batch-read contract | Cross-market V2 pairs; local math; 9 fixed test volumes plus bisection | Flashbots bundle; default 80% of profit to the miner | Last push Feb 2024 | README: "very unlikely to be profitable" (**EVIDENCE-BACKED**) |
| [paradigmxyz/artemis](https://github.com/paradigmxyz/artemis) (Rust) | Collectors (blocks, mempool, logs) → strategies → executors | Strategy-defined | Framework only | Executors for mempool and Flashbots | Last push Mar 2024 | Framework; no strategy edge |
| [mouseless0x/rusty-sando](https://github.com/mouseless0x/rusty-sando) (Rust) | Mempool | revm fork of local state | Binary-search sizing; exact simulation | Bundles with bribe | **Archived** Aug 2023 | Sandwich (not our class) |
| [solidquant/mev-templates](https://github.com/solidquant/mev-templates) (Python/JS/Rust) | Every block | Local V2 reserves | Flash-loan arbitrage template, simulated | Bundles | Last push Nov 2023 | Teaching template |
| [darkforestry/amms-rs](https://github.com/darkforestry/amms-rs) (Rust) | Event-synced state space (reorg-aware) | V2, V3, Balancer, ERC4626 | Library | — | Active (Oct 2025) | Infrastructure only |
| [bluealloy/revm](https://github.com/bluealloy/revm) (Rust) | — | EVM | Exact local simulation | — | Active (Oct 2026) | Infrastructure only |
| [flashbots/mev-inspect-py](https://github.com/flashbots/mev-inspect-py) (Python) | Post-hoc | Traces | Classifier | — | **Archived** Nov 2024 | Measurement tool |
| Public Base / Aerodrome searcher | None credible and maintained was found in this review | — | — | — | — | Absence is consistent with edge being private (**HYPOTHESIS**) |

**Patterns every serious searcher shares, compared with ArbiCore:**

| Pattern | Serious searchers | ArbiCore (canonical path) | ArbiCore (T2, inert) |
|---|---|---|---|
| Trigger | Block, Flashblock, or pending state | 60 s timer | `newHeads` (2 s) |
| State | In-memory, event-updated pool state | None (RPC each time) | In-memory cache |
| Price | Local exact math or revm | Remote `eth_call` per hop | Local, single-tick V3 |
| Sizing | Closed form, bisection, or golden section | Fixed $10k | Fixed 1.0 |
| Search scope | Only cycles touched by changed pools | Full DFS every tick | Enumerated cycles |
| Hot-path storage | None | Mongo queue | None |
| Submission | Bundle / private / priority fee; on-chain `minProfit` | Public RPC, legacy gas, no `minProfit` (V1) | None |
| Code size | Thousands of lines | ~81k lines plus an 8.7k-line `server.py` | ~3.3k lines |

---

## 13. Clone vs adapt vs rebuild decision

| Option | Verdict | Why |
|---|---|---|
| A. Direct clone | **No** | No public bot is profitable as-is; simple-arbitrage says so itself. Cloning imports a known-crowded strategy |
| B. Selective architectural borrowing | **Yes, conditional on the census passing** | Borrow the *patterns* in section 12: event-driven state, local exact simulation, sizing search, minimum profit on-chain, priority-fee submission. Reuse amms-rs/revm-style ideas inside the existing T2 module |
| C. Rebuild hot path | **Not now.** Only after a canary shows realized capture | A competitive Rust plus own-node hot path is hundreds of hours (**HYPOTHESIS**). Do not spend it before the market is proven contestable |
| D. Keep current architecture | **Keep the safety, execution, and evidence shell; stop evolving the poller** | The broadcast ladder, kill switch, gates, and economics identity are sound. The poller cannot compete and should be frozen as a SHADOW monitor |
| E. Hybrid | **This is the recommendation:** D for the shell + B for a thin hot path, gated on the census | Smallest change that could compete, if competition is possible at all |

---

## 14. Minimum viable architecture

This is the architecture that should exist even if only one strategy is ever deployed. It is deliberately not a multi-strategy "MEV search engine".

```text
Base Flashblocks WSS ──► in-memory pool state (census-chosen pools)
                              │  (only changed pools)
                              ▼
                     affected-cycle lookup ──► exact sim at pending state
                                                (local math; eth_simulateV1 / revm check)
                                                      │
                                                      ▼
                                   optimal size + Gate 7 (unchanged $25) + Gate 8
                                                      │
                                                      ▼
                          existing broadcast ladder (kill switch, mode, vault signer,
                          preflight, revalidation) ──► V2 executor (on-chain minProfit)
                                                      │
                                                      ▼
                       receipt reconciliation ──► realized_pnl / realized_loss_usd
                                               ──► CircuitBreaker.record_outcome (persisted)
                                                      │
                                     async evidence log (Mongo), off the hot path
```

Strategy modules are pure functions of "pool state → candidate trade". Build **one**. Liquidations, hooks, solver/RFQ, backruns, and other families are **deferred** until one module shows realized profit. **STRONG INFERENCE.**

---

## 15. What to KEEP

- **The broadcast gate ladder** (`execution/broadcast.py`), kill switch, mode ladder, and limited-live eligibility. They are sound and fail closed.
- **The economics identity** (`gross_is_quote_inclusive`), Gates 7/8/9 as written, and pre-broadcast revalidation.
- **The flash-loan executor contracts**, with V2 as the target for any strategy trade.
- **Technical Validation** as the LIVE 0 vehicle.
- **The T2 searcher module** as the seed of the hot path and as the measurement instrument.
- **The RPC failover / backoff / chain-id layer.**
- **The poller**, frozen, as a low-cost SHADOW monitor, or switched off. No further development.

## 16. What to FIX

Each item states why, its success criterion, and its stop condition.

| # | Fix | Why | Success criterion | Stop condition |
|---|---|---|---|---|
| F1 | Stop the three legacy backends, or repoint them to an isolated database with new secrets | Shared DB, vault key, and JWT secret with old code; evidence pollution; quota burn | `docker exec … printenv DB_NAME` ≠ `arbicore_x` for all three, or they are stopped. One scanner worker ID in new bundles | Done once verified; ~1 hour |
| F2 | Rotate the admin password (out of compose env), JWT secret, and Alchemy keys; issue a production-only `VAULT_KEY`; redact RPC URLs in logs | Live credential exposure today, independent of trading | Zero log lines containing a key URL over 1 hour; old keys revoked; login with old credentials fails | Done once verified; ~3 hours |
| F3 | Canonical provenance (section 11) | Required before any LIVE deploy | Five identities equal the tag SHA | Done once verified; ~4 hours. **Only if the census passes** |
| F4 | LIVE 0 prerequisites: Technical Validation accepts Base USDC, resolves the key from the vault, non-zero `amountOutMin` | LIVE 0 path | Dry run (`execute=false`) passes on Base mainnet state | **Only if the census passes**; ~6 hours |
| F5 | LIVE 1 prerequisites: deploy V2 executor; receipt reconciliation writes `realized_pnl`/`realized_loss_usd` and calls a persisted breaker; capital policy uses the sending wallet and treats `0` as `0`; EIP-1559 priority fee | Loss loop and on-chain invariant | Fork test: a forced loss trips the breaker and survives restart; V2 reverts below `minProfit` | **Only if the 72-hour measurement passes**; ~40–60 hours |

## 17. What to DELETE / DEFER

- **Stop:** any further forensic reading of the 256/288/180 stored rows; any further 30-minute generic SHADOW runs; Phase 0.5 ledger/explorer work; E-series replays; six-chain RPC tuning; SHA-stamping documentation commits.
- **Defer:**
  - Strategy Factory integration and Foreman Sentinel control-plane work for ArbiCore.
  - The learning, intel, and outcome-tracker modules.
  - Duplicate calldata stacks, sizers, and gas paths (consolidate only when touched).
  - Liquidation research (section 22).
  - Five of the six chains: keep Base, plus Arbitrum for the census only.
- **Delete (housekeeping, not urgent):** the abandoned validator containers and mongos, once F1 is done.

## 18. What NOT to build

- A new research or certification platform, opportunity ledger v2, or any "MEV search engine" framework.
- New strategy families (liquidations, hooks, solver/RFQ, backruns, launch sniping) before one strategy shows realized profit.
- A Uniswap v4 engine, a Curve adapter, or more chains. Coverage without speed only adds opportunities that are already taken.
- ML, meta-learning, autonomous parameter mutation, or AI authority over risk limits, kill switches, allowlists, addresses, signing, mode, RPC topology, or capital.
- A Rust rewrite or own Base node, until a canary shows realized capture.
- A Gate 7 reduction, or any MEV-term change, in production.
- A frontend for any of the above.

---

## 19. Shortest path to the first real transaction

The first real transaction is the **engineering transaction (LIVE 0)**: one Aave flash loan plus one Uniswap V3 swap on Base through Technical Validation, costing cents.

- **Revision of my memo:** sequence it **after** the census passes. If the census fails, a mainnet transaction teaches us nothing we need. If the owner wants it anyway for confidence, it is cheap, but it must not delay the census.
- **Path:** F1 → F2 → census (day 1–2) → if PASS: F3 + F4 → kill-switch drill → LIVE 0 with the signer holding ≤ 0.01 ETH and the executor holding nothing.
- **Effort:** about 14 hours of engineering after F1/F2. About 3–4 working days from today if the census passes on day 2.
- **Why:** proves real addresses, gas (including the L1 data fee), inclusion, receipt and event decoding, and evidence persistence.
- **Success criterion:** one confirmed success with a decoded `ExecutionCompleted` event, gas within 25% of the estimate, and evidence persisted.
- **Stop condition:** two failed attempts with an unexplained cause means stop and diagnose offline. No third attempt in the same session.

## 20. Shortest path to the first strategy trade

**Only through this chain, with no shortcuts:** census PASS → 72-hour per-Flashblock measurement PASS → F5 → a bounded canary (LIVE 1). The canary uses an **envelope approval**, not per-trade approval:

- Base only, one strategy, V2 executor;
- signer ≤ 0.01 ETH;
- ≤ $25 cumulative gas budget;
- ≤ 50 attempts;
- 7 days;
- Gate 7 unchanged at $25, revalidation at $35;
- automatic breaker; kill switch tested first.

**Earliest realistic date:** about 2–3 weeks from today, *if* both measurements pass. **HYPOTHESIS** on timing.

Canary stop conditions:

- realized net < 0 after 20 attempts;
- win rate < 10% after 30 attempts;
- any loss outside the gas envelope;
- any safety-gate anomaly.

---

## 21. 72-hour experiment design

The memo's 72-hour experiment stays, but it becomes **step 2**. Step 1 is cheaper and can make it unnecessary.

### Step 1: E-A, ≥ $25 tail census (public data, ~1–2 days, no infrastructure, no keys)

- **Why:** decides whether *any* contestable ≥ $25 atomic arbitrage flow exists on Base or Arbitrum. If not, nothing we build can capture it.
- **Method:**
  - Source: Bitquery DEX-trade API (the 2026 investigation states the same records are queryable) or Dune, over 30 days, for Base and Arbitrum.
  - For each credible arbitrage transaction, record realized net after gas (token balance deltas of the executor contract and sender), tokens, venues, pools, priority fee paid, executor contract, block, and transaction index.
  - Also record the transaction index of the preceding swap on the same pools (the "trigger").
  - Hand-validate 20 rows against receipts before trusting the query.
- **Pre-registered metrics:**
  - M1: ≥ $25 tail count per day and tail profit per day.
  - M2: number of distinct executor contracts winning the tail, and the top-3 share.
  - M3: share of tail profit on venues and tokens buildable in two weeks (Uniswap V2/V3/v4, Aerodrome, PancakeSwap; majors and mid-caps).
  - M4: share of tail trades immediately adjacent to their trigger (index gap ≤ 2). This is a proxy for "won inside the trigger's Flashblock"; Flashblock boundaries are not stored on-chain.
- **PASS (all must hold):**
  - M1 tail profit ≥ $5,000 per day on Base;
  - M2 ≥ 10 distinct winners and top-3 share < 70%;
  - M3 ≥ 30%;
  - M4 ≤ 70%.
- **KILL if any one fails.** Stop generic atomic DEX arbitrage. No further measurement and no LIVE 0 for strategy purposes.
- **Rationale for $5,000/day:** a new entrant capturing about 2% of the tail (**HYPOTHESIS**) would make about $3,000 a month. That is roughly the minimum that justifies infrastructure plus the remaining engineering hours.
- **Stop condition for the task itself:** if the query cannot be validated against 20 hand-checked receipts within 16 hours, stop and use the Bitquery published aggregates as the answer. They already imply a small tail.

### Step 2: E-B, 72-hour per-Flashblock Base SHADOW measurement (only if E-A passes)

- **Why:** E-A says the flow exists. E-B tests whether *our* detection sees it before it is taken.
- **Setup (no signing, no broadcast, no gate change):**
  - T2 with a Flashblocks WSS endpoint.
  - Pool set = the pools behind the E-A tail, not the 30 hand-picked pools.
  - Exact pending-state simulation via local math cross-checked against `eth_simulateV1`.
  - Optimal size search.
  - Record gross, net-before-MEV, and net-after-MEV separately.
- **Metrics:**
  - B1: qualifying states (net ≥ $35 before the MEV term, Gate 8 passes, `eth_call` succeeds at pending state) per day.
  - B2: survival, i.e. whether the state still exists one Flashblock (200 ms) after our detection.
  - B3: recall, the share of E-A-style tail arbitrages on our pools that we flagged *before* their inclusion.
- **PASS for LIVE 1:** B1 ≥ 30 in 72 hours (≈ 10 a day) **and** median B2 ≥ 1 Flashblock **and** B3 ≥ 20%.
- **GREY** (3–29 qualifying states, or recall 5–20%): no LIVE 1. At most one more 72-hour run after one specific, named latency fix. Then decide. No third run.
- **KILL:** fewer than 3 qualifying states, or recall < 5%. Stop atomic DEX arbitrage on this infrastructure.
- **Why the bar moved from "≥ 3":** 3 in 72 hours at $35 each, with any realistic win rate, is under $50 a month. That proves existence, not a business.
- **Effort:** 24–40 hours of setup, 72 hours of wall clock, 4 hours of analysis.

## 22. Decision tree after the experiment

```text
F1 + F2 (security) ── always, now
        │
E-A census (1–2 days)
 ├─ KILL ──► Stop generic atomic DEX arb. Freeze ArbiCore in SHADOW (or off).
 │            No LIVE 0, no T2 work. Optional: ≤ 40 h to write ONE thesis for a
 │            structurally advantaged niche (we must name the edge we own:
 │            order flow, inventory, private information, or a protocol
 │            relationship). No named edge → end the trading project.
 └─ PASS ──► F3 + F4 → LIVE 0 (parallel)   and   E-B 72 h measurement
               ├─ KILL ──► same as E-A KILL
               ├─ GREY ──► one named latency fix → one more 72 h → PASS or KILL
               └─ PASS ──► F5 → LIVE 1 envelope canary (7 days, ≤ $25 gas, ≤ 50 attempts)
                             ├─ realized net < 0, or win rate < 10% ──► stop; post-mortem; no rebuild
                             └─ realized net > 0 and win rate ≥ 10% ──► only now consider hot-path
                                                                       rebuild (Rust / own node), one strategy
```

**Liquidation research: B, park it.** Of 31 events, 30 were priced; none reached a reconstructable net ≥ $25, and on Ethereum the coinbase transfer roughly equals the surplus. Coverage was incomplete, so "clearly unpromising" is not proven. There is also no evidence or advantage that justifies another census now. **EVIDENCE-BACKED** for the sample.

**E1 / E1.5 / E1.6 tell us three things:**

- Real arbitrage exists outside our universe (Uniswap v4, a TRUMP v2/bridge mechanism).
- Where it was ≥ $25, it was competed down to $1–$13 kept.
- Uniswap v4 had no repeatable pre-block opportunity.

This is evidence *for* competition, not for alpha. **EVIDENCE-BACKED** (one Ethereum hour; not reinterpretable as edge).

---

## 23. Estimated engineering effort

Hour ranges are **HYPOTHESIS** estimates.

| Step | Hours | Condition |
|---|---|---|
| F1 isolate legacy backends | 1 | Always |
| F2 rotate credentials, redact logs | 3 | Always |
| E-A census | 8–16 | Always |
| F3 canonical provenance | 4 | E-A PASS |
| F4 + LIVE 0 | 10 | E-A PASS |
| E-B setup + run + analysis | 28–44 (+72 h wall clock) | E-A PASS |
| F5 LIVE 1 prerequisites | 40–60 | E-B PASS |
| LIVE 1 canary operation | 10–20 over 7 days | E-B PASS |
| Competitive hot-path rebuild (Rust, own node) | 300–600 | Canary PASS only |
| **Total if E-A kills** | **≈ 12–20** | |
| **Total to a LIVE 1 verdict if all pass** | **≈ 105–160** | |

**Business reality** (estimates are **HYPOTHESIS** unless marked):

- **Market:** Base's whole credible arbitrage market is about $25k a day, shared by about 1,300 contracts. The average per contract is about $580 a month (mean, heavily skewed). **EVIDENCE-BACKED** arithmetic.
- **Running cost of a competitive setup:**
  - Flashblocks-capable RPC: $50–$500 a month.
  - Own Base node, if needed: $300–$800 a month.
  - Gas: cents per Base attempt plus priority fees.
  - Development: the dominant cost.
- **Time to statistical evidence:** at about 10 qualifying states a day and a 30% win rate, about 10 days to reach 30 realized trades. At 1 a day, months.
- **Is it still rational as a business?** Not as generic atomic DEX arbitrage, unless E-A shows a contestable ≥ $25 tail of at least about $5k a day on Base. My prior that E-A passes is about 20–30% (**HYPOTHESIS**). The money already spent is sunk and should not influence the next 500 hours.

## 24. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Census mis-measures (decoding gaps; Bitquery says its totals are floors) | False KILL | Hand-validate 20 rows. Floors bias toward KILL, which is the cheaper error here |
| Flashblock-boundary proxy (M4) is approximate | Wrong reaction-time read | Treat M4 as a gate only at its extremes; E-B measures it directly |
| Denim (native 200 ms blocks, mainnet planned Nov 2026) changes the stream API | E-B or hot-path rework | Base publishes a migration guide; keep the ingest adapter thin |
| Legacy backends left running | Signer key decryptable by old code once loaded | F1 before any key enters the vault, unconditionally |
| Credential abuse via logs or the admin UI | Mode or kill-switch tampering; quota theft | F2 now |
| Sunk-cost pressure to "lower Gate 7 just once" | Buys losses; destroys the evidence | Gate 7 is not on the decision path. Its changes require new evidence, not a new memo |
| Process relapse (a new audit after each result) | Loop resumes | Every task here has a stop condition. A result that triggers KILL is final, not a prompt for a new census |
| Canary with V1 executor | Gate 7 is only an estimate; trade lands at ~$0 | V2 is mandatory for LIVE 1 (F5) |

## 25. Final GO / NO-GO recommendations

| Item | Decision |
|---|---|
| F1 + F2 security remediation | **GO now.** Unconditional |
| E-A ≥ $25 tail census | **GO now.** It is the first finite experiment |
| LIVE 0 engineering transaction | **CONDITIONAL GO.** After E-A PASS, in parallel with E-B |
| E-B 72-hour per-Flashblock measurement | **CONDITIONAL GO.** After E-A PASS |
| LIVE 1 strategy canary | **NO-GO** until E-B PASS and F5 are complete |
| Gate 7 / MEV term change | **NO-GO** |
| Any new strategy family, chain, venue engine, or platform | **NO-GO** |
| Continued poller development, audits, replays, census expansions | **NO-GO** |

### Mandatory final decision table

| Area | Current State | Problem? | Severity | Action |
|---|---|---|---|---|
| Strategy class | Generic atomic DEX arbitrage, blue chips | Yes. Commoditized; our universe is at the fee band | CRITICAL | E-A census decides continue or stop |
| Market | Base ~$25k/day total, ~1,300 contracts, $0.43 per trade | Yes. Small, shrinking, concentrated | CRITICAL | Measure the ≥ $25 tail (E-A) |
| Discovery model | 60 s poller + Mongo queue | Yes. ~14 min p50; 2–3% verified | HIGH | Freeze. Event-driven T2 only after E-A PASS |
| Latency | Minutes versus 200 ms Flashblocks | Yes | HIGH | Per-Flashblock loop (section 9) only after E-A PASS |
| Venue coverage | 30 Base pools; no PancakeSwap or v4 on Base | Yes, but secondary | MEDIUM | Pool set driven by E-A data, not hand-picked |
| Economic model | Sound identity; flat MEV, fixed size, missing probability / priority fee / failure cost | Miscalibrated, not causal | MEDIUM | Record gross / pre-MEV / post-MEV in E-B. No gate change |
| Code quality | Mostly D/B; heavy C | No (not causal) | LOW | Freeze; consolidate only when touched |
| Safety / broadcast ladder | Fail-closed, single send site | No | — | Keep |
| Legacy backends on production state | Running, shared DB / vault / JWT | Yes | CRITICAL | F1 now |
| Credentials | Admin password plaintext; RPC key in production logs | Yes | CRITICAL (before LIVE) / HIGH | F2 now |
| Loss loop / breaker | No writer, no caller, in memory | Yes, for LIVE 1 | HIGH | F5, only after E-B PASS |
| Capital policy | Wrong wallet; `or DEFAULT` bug | Yes, for LIVE 1 | HIGH / MEDIUM | F5 |
| Executor | V1, no on-chain `minProfit` | Yes, for LIVE 1 | HIGH | Deploy V2 in F5 |
| Technical Validation | Sepolia USDC, env key, `amountOutMin=0` | Yes, for LIVE 0 | HIGH / MEDIUM | F4, after E-A PASS |
| Provenance | Commit not on GitHub; wrong label; `/tmp` override | Yes, before LIVE deploy | MEDIUM | F3, after E-A PASS |
| Liquidations | 0/30 net ≥ $25; coverage incomplete | Not now | LOW | Park |
| Research / certification programme | ~90 documents, repeated re-reads | Yes. This is the loop | HIGH (process) | Stop |

| Path | Recommendation |
|---|---|
| Continue current generic DEX architecture | **No.** Freeze the poller as a SHADOW monitor or switch it off. No further development |
| Clone open-source bot | **No.** None is profitable as-is; the canonical example says so itself |
| Selectively borrow proven architecture | **Yes, conditional on E-A PASS.** Event-driven state, local exact simulation, sizing search, on-chain `minProfit`, priority-fee submission, inside the existing T2 module |
| Rebuild hot path | **Not now.** Only after a LIVE 1 canary shows realized net > 0 |
| Build new strategy family | **No.** Defer all families until one strategy shows realized profit |
| Run Base engineering transaction | **Conditional.** After E-A PASS, in parallel with E-B; cheap but has no decision value if E-A fails |
| Run 72h measurement | **Conditional.** Only after E-A PASS, with the revised pass bar (section 21) |
| Continue broad research | **No.** Stop now |

---

## FINAL VERDICT

**PRIMARY FAILURE MODE:** Strategy–market mismatch. ArbiCore targets generic atomic DEX arbitrage on blue-chip pools. That class is commoditized: it averages $0.43 per trade on Base, the chain's whole market is about $25k a day across about 1,300 bots, and our observed pools sit at their fee band. A $25 floor sits in the market's extreme tail. **EVIDENCE-BACKED.**

**SECONDARY FAILURE MODE:** Wrong discovery and latency architecture. A 60-second poller and Mongo queue (~14-minute median, 2–3% of discoveries verified, about one Base evaluation per minute) cannot observe opportunities that live for one 200 ms Flashblock, on a venue set that excludes most of Base's arbitrage routes. **EVIDENCE-BACKED.**

**TERTIARY FAILURE MODE:** Process and production engineering. Effort went into certification, replay, and governance (~109k lines, ~90 documents) instead of one decisive market measurement. Meanwhile, production shares state and secrets with three legacy backends and leaks its RPC key in logs. **EVIDENCE-BACKED.**

**BEST PATH:** Fix the security exposure now (F1, F2). Run the one-to-two-day public-data census of the ≥ $25 tail on Base and Arbitrum with pre-registered kill thresholds. Only if it passes: do LIVE 0 and a per-Flashblock 72-hour SHADOW measurement in parallel, then a bounded envelope canary on the V2 executor. Rebuild the hot path only after realized profit.

**FIRST FINITE EXPERIMENT:** E-A, the ≥ $25 tail census (section 21). Thirty days of Base and Arbitrum credible arbitrages, measuring tail profit per day, winner concentration, venue reachability, and adjacency to the trigger. 8–16 hours, no infrastructure, no keys, no production change.

**STOP CONDITION:** Stop generic atomic DEX arbitrage permanently if any of these holds:

- Base ≥ $25 tail profit < $5,000 a day;
- fewer than 10 distinct winners, or top-3 share ≥ 70%;
- < 30% of the tail on venues and tokens we could reach in two weeks;
- > 70% of tail trades adjacent to their trigger;
- later: E-B < 3 qualifying states in 72 hours, or recall < 5%;
- later still: the canary's realized net < 0 after 20 attempts.

A KILL result is final. It does not justify a new census.

**WHAT WE SHOULD NOT BUILD:**

- another research, certification, or ledger platform;
- a multi-strategy MEV engine;
- new strategy families;
- a v4/Curve engine or more chains;
- ML or autonomous parameter control;
- a Rust rewrite or own node before realized profit;
- any Gate 7 or MEV-term relaxation.

### "If this were your own money and your own next 500 hours, what exactly would you do from this point?"

- **Hours 0–4.** Stop the three legacy backends and rotate every exposed credential (admin password, JWT secret, Alchemy keys, a production-only vault key), with log redaction. I would do this even if I planned to shut the project down tomorrow, because it is live exposure today.
- **Hours 4–20.** Write and hand-validate the Base and Arbitrum ≥ $25 tail census, then apply the pre-registered thresholds without reinterpretation.
- **If it fails, which I expect with roughly 70–80% probability (HYPOTHESIS):**
  - I would stop generic DEX arbitrage. I would not spend the remaining ~480 hours on it.
  - I would spend at most 40 hours writing down whether we own any structural edge: exclusive order flow, inventory and a CEX relationship for non-atomic CEX-DEX on L2s, private information, or a protocol relationship.
  - If I could not name one concretely, I would end the trading project. I would salvage the reusable safety and execution infrastructure for Foreman or other products, and put the hours elsewhere.
  - I would not build a v4 engine, a liquidation bot, or a Rust searcher hoping that coverage or speed creates an edge the census says is not there.
- **If it passes:**
  - About 14 hours to LIVE 0 on Base, and about 40 hours to run the per-Flashblock measurement on the census's pools.
  - If that passes, about 50 hours to deploy V2, wire the loss loop and breaker, and fix the capital policy.
  - Then a 7-day envelope canary with ≤ 0.01 ETH in the signer, ≤ $25 of gas, and Gate 7 untouched.
  - Only if the canary shows positive realized net and a ≥ 10% win rate would I spend the remaining ~300 hours on a lean, single-strategy, event-driven hot path. At every step I would hold myself to the same stop conditions.
