# ArbiCore X — Competitive Power-Up: Research & Strategy Report

Legend: **[E]** = evidence from research · **[I]** = inference · **[P]** = proposed architecture.
No guaranteed-profit claims. M3 remains the final safety authority in every proposal.
Prepared while production stays on `2.9.2-78b2a8c` (untouched); signing/LIMITED_LIVE/FULL_LIVE OFF.

---

## 1. CURRENT ARBICORE X COMPETITIVE POSITION
- **[I]** ArbiCore X today is a *safety-first, read-only-validated* Base flash-loan arbitrage
  engine. Its differentiator is NOT speed — it is a rigorous, fail-closed validation spine
  (fresh quote/price/TVL/economics/MEV/flashloan + block/reorg/deadline + all-in cost) that
  refuses to sign unless a genuinely profitable, verifiable opportunity exists.
- **[E]** Real-Base testing (this repo) shows the pipeline reads live quotes, TVL (~$8.2M UniV3),
  Balancer vault liquidity, real `eth_feeHistory` congestion, and now a true all-in fee
  (L2 gas ceiling + Base L1 GasPriceOracle fee + flash + slippage). Current canonical routes are
  **unprofitable** (gross −0.017%…−0.571%) → correctly DENIED.
- **[I]** Position: *late entrant on a crowded chain, but with unusually disciplined risk
  architecture.* We are not yet competitive on opportunity **sourcing** or **execution latency**.

## 2. WHO WE ARE COMPETING AGAINST (competitive map)
- **[E]** Flashbots research (2024–2026): Base has **thousands** of active bot addresses;
  competition has shifted from broad on-chain probing (gas-expensive) to **targeted / off-chain
  search**; **Flashblocks** (~200ms preconfirmations) and **fee-floor** changes reshaped the
  equilibrium; top searchers win on **execution architecture**, not strategy ideas.
- Category map ([E] roles / [I] where we can compete):
  | Category | Good at | Advantage | Expensive infra | Hard to copy | ArbiCore realistic angle |
  |---|---|---|---|---|---|
  | Professional searchers | latency, bundles | colocated nodes, builder ties | private nodes, DA | orderflow deals | **avoid head-to-head latency** |
  | Independent searchers | niche routes | agility | modest | — | **out-search on breadth+discipline** |
  | Searcher/builders | inclusion control | own block building | builder stack | relay/builder rep | not now |
  | Liquidation bots | oracle timing | health-factor feeds | oracle streams | protocol coverage | **liquidations later (good edge)** |
  | DEX arb bots | spread capture | route libraries | RPC fan-out | tuned sizing | **multi-chain breadth + EV ranking** |
  | Private orderflow systems | exclusive flow | RFQ/OFA deals | partnerships | relationships | not reachable early |
  | Commercial MEV systems | turnkey | scale | infra | data moats | differentiate on transparency |

## 3. WHAT IS ACTUALLY SPECIAL (honest advantage vs hygiene)
For each: "does it help us WIN money vs competitors?"
1. Multi-strategy — **[I] Advantage (potential)**: diversifies away from the most-contested single
   game; only real once ≥2 strategies ship.
2. Multi-chain — **[I] Advantage (potential)**: opportunity breadth on less-saturated chains
   (Gnosis, Avalanche) can beat fighting Base whales. Real once ≥2 chains ship.
3. Shared M3 safety — **[I] Hygiene, not edge** in raw PnL, BUT enables *safe autonomy at scale*
   (fewer catastrophic losses) → indirect edge via survival. Keep.
4. Real-time fresh validation — **[I] Hygiene + risk edge** (avoids stale/reverting trades =
   fewer failed-tx gas burns, which searchers cite as a top cost).
5. Evidence/provenance — **[I] Hygiene now**; becomes edge only if it feeds learning (see #8).
6. Strategy Factory (autonomous strategy gen) — **[I] Potential moat, unproven**; do NOT build now.
7. Foreman multi-agent — **[I] Hygiene/scaffolding**; not an edge by itself.
8. Continuous research/learning from outcomes — **[I] Real potential edge**: compounding
   "which routes/sizes/times actually paid" is exactly the *targeted off-chain search* the
   Flashbots data says now wins. This is our best moat candidate.
9. Cross-strategy opportunity ranking (EV) — **[I] Advantage** once multi-strategy exists.
10. Risk-aware decisioning — **[I] Hygiene + survival edge**.
11. Parallel specialized workers — **[I] Scaffolding**; edge only via #8/#9.
**Honest verdict:** today most items are *hygiene*. The credible future edges are
**(8) outcome-learning-driven targeted search**, **(2) chain breadth**, and **(9) cross-strategy EV ranking** — all gated by M3.

## 4. CURRENT WEAKNESSES
- **[I]** No event-driven/WSS discovery — we don't *find* opportunities fast, we validate given ones.
- **[I]** No private submission / builder path → on a fast chain, public-mempool arb is largely
  pre-empted. **[E]** targeted search + fast inclusion is where the money moved.
- **[I]** Single chain, single strategy (cyclic DEX arb) → smallest, most-contested surface.
- **[I]** No historical profitability learning yet (evidence bundles exist but don't feed ranking).
- **[I]** Public RPC only in dev → rate-limited; no local node / latency measurement.
- **[I]** Sizing is static (probe-amount scaled), not liquidity/EV-optimal.

## 5. TOP 10 UPGRADES TO BECOME MORE COMPETITIVE (ranked)
1. **[P] Event-driven WSS discovery + Flashblocks-aware polling** (Base) — react to pool state
   sub-block. Highest sourcing leverage.
2. **[P] Outcome-learning ranker** — feed evidence bundles → per-route/time/size success & realized
   PnL → EV ranking (our moat candidate #8).
3. **[P] Dedicated Base RPC/local node + latency budget** — removes the single biggest dev limit.
4. **[P] Liquidity-aware dynamic sizing** — size to the route's TVL/depth to maximize net EV.
5. **[P] Private/protected submission research** (builder/relay on Base; document trust risks).
6. **[P] Liquidation strategy worker** (Aave/Moonwell on Base) — different, often less-latency-bound edge.
7. **[P] Stablecoin + LST/LRT arb workers** — narrow, frequent, lower-competition spreads.
8. **[P] Competitor Intelligence Layer** (address-behavior only) — learn which routes/DEX combos pay.
9. **[P] Parallel route simulation + pruning** — evaluate many candidates per block cheaply.
10. **[P] Multi-chain expansion (Arbitrum → Gnosis/Avalanche)** — breadth over saturated Base.

## 6. BEST NETWORK × STRATEGY COMBINATIONS
Freq / Edge / Competition / Infra / Complexity / Risk / When (build now|later|reject):
- **Base × cyclic DEX arb** — High / Low / **Very High** / High / Med / Med / **now (current track)**.
- **Base × liquidations** — Med / Med-High / High / Med (oracle feeds) / Med / Med / **later (P1)**.
- **Arbitrum × DEX arb** — High / Low-Med / High / High / Med / Med / **later (P2)**.
- **Gnosis/Avalanche × stablecoin arb** — Med / Low-Med / **Lower** / Med / Low-Med / Low-Med / **later (P2, good breadth)**.
- **Ethereum × LST/LRT arb** — Low-Med / Med / High / High (gas) / High / Med-High / **later (P3)**.
- **Any × triangular/multi-hop** — Med / Low / High / Med / Med / Med / **later (extends cyclic)**.
- **Any × oracle-update / backrunning** — Low-Med / Med-High / **Very High** (latency) / Very High / High / High / **reject for now**.
- **Cross-domain/statistical arb** — Low / Med / Med / High (inventory, non-atomic) / High / **High** / **reject for now** (breaks atomic-flashloan safety model).

## 7. MULTI-AGENT ARCHITECTURE (proposed, M3 authoritative)
- **[P]** Foreman/Orchestrator → Chain workers (Base first) → Strategy workers (DEX arb now;
  liquidation/stablecoin/LST later) → **Opportunity Bus** (normalized candidate schema) →
  EV Ranking → Risk engine → **M3 safety (unchanged gatekeeper)** → Execution (human-confirmed).
- **Hard rule [P]:** workers only *generate/analyze/rank/propose*. They pass candidate plans to M3;
  they CANNOT sign/broadcast or relax gates. M3 + broadcaster remain the single execution authority
  (mirrors today's `require_revalidation=True`, fail-closed).
- **[I]** Build order: opportunity-bus schema + one extra strategy worker BEFORE any orchestration
  framework. Do NOT build Foreman before there are ≥2 workers to coordinate.

## 8. COMPETITOR INTELLIGENCE ARCHITECTURE (address-behavior, NOT attribution)
- **[P]** Passive read-only worker indexing recent blocks/logs to cluster *addresses* by observable
  behavior: DEX combos, route patterns, frequency, gas-bidding, success/fail ratio, chain preference.
- **[E/I]** Keep strict separation: we characterize **address behavior**, never claim human/company
  attribution. Output feeds the ranker (#2): "these route shapes are being actively contested / paid".

## 9. LIVE MEV / FLASH-LOAN DATA SOURCES (identify, don't build dashboards)
- **[E]** Flashbots (research + Dune dashboards, mempool/transparency data).
- **[E]** EigenPhi (MEV/arb/liquidation analytics + APIs) — arb & sandwich & liquidation feeds.
- **[E]** Dune / Flipside (SQL on DEX events, flash-loan calls, liquidations) — automatable.
- **[E]** DEX subgraphs (Uniswap/Aerodrome) + direct event streams (WSS `logs`) — pool state.
- **[E]** Base block explorers / traces; lending-protocol data (Aave, Moonwell) for liquidations.
- **[I] Recommend for automated research workers:** Dune/Flipside (batch), EigenPhi (arb/liq deltas),
  direct WSS logs (real-time pool state), Flashbots research (equilibrium shifts).

## 10. P0 / P1 / P2 / P3 ROADMAP
(benefit · revenue impact · complexity · deps · risk · parallelizable · needs-prod · before/after first revenue)
- **P0 — MUST HAVE BEFORE FIRST REVENUE**
  - True all-in fee gate (**DONE this session**) · avoids loss trades · High rev-protect · Med · RPC · Low · no(validation) · yes-parallel · **before**.
  - Genuine profitable candidate discovery (dedicated RPC + real bundles via Spread Widener Watch) · unlocks revenue · High · Med · dedicated RPC · Med · yes(VPS read) · no-serial · **before**.
  - Controlled-Live readiness checklist (signer identity, gas/slippage/loss caps, preflight eth_call/estimateGas, receipt/PnL) · enables first trade · High · Med-High · P0 discovery · Med · yes(VPS) · partly · **before**.
- **P1 — HIGH-VALUE COMPETITIVE UPGRADES**
  - Event-driven WSS + Flashblocks-aware discovery · more/earlier opps · High · Med · Base WSS · Med · no · yes · **after**.
  - Outcome-learning EV ranker · compounding edge · High(long-run) · Med · evidence bundles · Low · no · yes · **after**.
  - Dedicated node/RPC + latency budget · removes throttling · Med-High · Med · infra · Low · yes(infra) · yes · **after**.
  - Liquidity-aware dynamic sizing · higher net/opportunity · Med · Low-Med · quotes+TVL · Med · no · yes · **after**.
- **P2 — SCALE / MULTI-CHAIN**
  - Opportunity-bus schema + 2nd strategy worker (liquidations) · diversify · Med-High · Med · P1 · Med · no · yes · **after**.
  - Arbitrum then Gnosis/Avalanche chain workers · breadth · Med · Med-High · abstractions · Med · yes(prod) · yes · **after**.
  - Competitor Intelligence Layer · targeted search · Med · Med · indexer · Low · no · yes · **after**.
- **P3 — LONG-TERM MOAT**
  - Foreman orchestration (only after ≥2 workers) · scale autonomy · Med · High · P2 · Med · yes · yes · **after**.
  - Strategy Factory (autonomous strategy gen) · potential moat · Unproven · Very High · learning+bus · High · no · yes · **after**.
  - Private/protected submission + builder integration · inclusion edge · Med-High · High · trust review · **High** · no · yes · **after (with risk doc)**.

## 11. WHAT MUST WAIT UNTIL AFTER FIRST REVENUE
- All P1/P2/P3 items above. Specifically: WSS/Flashblocks discovery, learning ranker, multi-chain,
  liquidation/stablecoin/LST workers, competitor-intel layer, Foreman, Strategy Factory, private
  submission. **[I]** None of these should delay: Base → M3 GREEN → controlled-live → first trade.

## 12. RECOMMENDED NEXT 30-DAY EXECUTION PLAN
- **Days 1–7 (primary track):** on VPS with dedicated Base RPC, run Spread Widener Watch against
  real CONFIRMED bundles; when a route flags, run full M3 → capture clean GREEN audit
  (m3_final_gates.ok=true, broadcast_sent=false). No thresholds lowered.
- **Days 5–12 (primary track):** build Controlled-Live Readiness checklist (signer identity, capital/
  gas/slippage/loss caps, preflight eth_call + eth_estimateGas wired into the all-in gate,
  receipt/PnL). Human-confirmation only, tiny capital. First real trade.
- **In parallel (research track, non-prod):** stand up Dune/EigenPhi/WSS *read-only* research workers
  to measure the real Base opportunity landscape and validate whether genuine profitable spreads
  recur (feeds go/no-go on P1 investment).
- **Gate:** do NOT start P1 build until (a) first controlled-live trade settles with correct PnL,
  and (b) research shows recurring profitable spreads. If Base proves structurally unprofitable at
  our size, pivot the research track to Gnosis/Avalanche stablecoin arb before scaling infra.

### Bottom-line thesis (Part 7)
**[I]** *ArbiCore X does not try to beat professional searchers on raw latency or private orderflow.
It competes by combining (X) a fail-closed, all-in-cost-honest safety spine that avoids the losing
trades that bleed most bots, (Y) outcome-learning-driven targeted search that compounds "what
actually paid", and (Z) multi-chain × multi-strategy breadth via M3-gated worker agents — and it
specializes in (A) capital-safe autonomous operation, (B) transparent evidence/provenance, and
(C) disciplined expansion into less-saturated chain×strategy niches rather than the most-contested
Base latency race.* Realistic, not guaranteed.
