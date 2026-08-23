# ArbiCore X — Flash-Loan Market / Competitive Intelligence Audit

**Mode:** READ-ONLY research + analysis. No production code modified, no branches merged, no patches applied, no implementation begun.
**Baseline:** builds on `docs/FLASH_LOAN_ARCHITECTURE_AUDIT.md` (Phase 0).
**Infra assumed:** 12 vCPU / 48 GB RAM VPS, Docker, MongoDB + Redis available, Base the only genuinely wired chain.

**Evidence tags:**
`[FACT]` = observed in the ArbiCore X codebase (Phase 0).
`[EXT]` = external research (2026-current, sources cited inline).
`[INF]` = inference/reasoning from FACT+EXT.
`[REC]` = recommendation (not applied).

---

## 0. Executive thesis

`[INF]` **ArbiCore X should evolve into an integrated flash-loan *searcher execution plane*, not a separate MEV bot, and should stay Base-first.** The strongest practical system on our infrastructure is:

> **local pool-state cache + local AMM math + fast route search + atomic single-transaction execution on Base (then Arbitrum), with a private co-located RPC/WSS, governed by the provenance/certification/mode scaffolding ArbiCore already has.**

Three external facts drive this:
1. `[EXT]` On Base there is **no public mempool and no Flashbots-style bundle relay**; a Coinbase sequencer orders by priority-fee + arrival (FCFS). Competitive edge = **latency + local state + atomicity**, achieved by packing the whole route into one revert-on-failure executor tx. (ai-frb.com, blinklabs docs, 2026)
2. `[EXT]` For our capital tier, **L2 rollups give superior median ROI**; Ethereum L1 atomic MEV is an incumbent moat (8-figure capital, exclusive orderflow, BuilderNet/TEE, co-lo LD4/NY4). Arbitrum + Base are the **primary density** for searchers. (ai-frb.com, arxiv 2605.04471, greenfieldcapital 2026)
3. `[EXT]` Rollup arbitrage opportunities now average **<340 ms lifespan**; rollup blocks are often full. **Latency and local state — not chain count — decide profitability.** (arxiv 2406.02172, caaw.io 2026)

**Do NOT assume more chains = more profit.** `[INF]` Adding a chain multiplies RPC/WSS/ops cost and dilutes the latency budget; a second chain only pays if it has independent opportunity density (Arbitrum qualifies; Optimism/Polygon are marginal until Base+Arbitrum are saturated).

---

## A. Flash-loan opportunity classes — assessment

Ranked by **realistic profit-per-eng-effort on Base/L2** for our infra.

| Class | What it is | Base/L2 viability `[EXT]/[INF]` | ArbiCore status `[FACT]` |
|---|---|---|---|
| **Cross-DEX arbitrage** | Same pair, price gap across 2 DEXs (e.g. Aerodrome vs Uniswap V3) | **HIGH** — core atomic L2 strategy; median gas $0.15–$1.10; needs speed | IMPLEMENTED (dex_arbitrage + FL scanner) |
| **Cross-pool / fee-tier arbitrage** | Same DEX, different fee tiers / CL tick states | **HIGH** — abundant on Base (Uni V3 500/3000/10000, Aerodrome CL) | PARTIAL (venues exist in `base_venues.py`; no dedicated scorer) |
| **Triangular / multi-hop** | Closed cycle A→B→C→A within one tx | **HIGH** — `RouteSearchEngine` already does closed-cycle DFS | IMPLEMENTED (route_search.py) |
| **Stablecoin dislocation** | USDC/USDT/DAI/USDbC depeg micro-gaps (Curve/Aerodrome stable pools) | **MEDIUM-HIGH** — frequent small gaps, low risk, but thin margins; Curve invariant math needed | PARTIAL (stable pairs exist; no StableSwap math) |
| **Backrun (atomic)** | React to a large swap that moves price, arb the imbalance same/next tx | **MEDIUM on Base** — no public mempool means you backrun **confirmed** state block-to-block, not pending tx; still valuable via fast per-block re-scan | MISSING (no per-block state diff trigger) |
| **Liquidation-assisted (flash-funded)** | Flash-borrow to repay an underwater loan, seize+sell collateral, repay | **MEDIUM** — Base/Arbitrum recapture ~89%; 57% of L2 liquidators use *speculative* (oracle-anticipating) tactics; needs lending-protocol adapters + oracle watch | MISSING |
| **Wrapped/native (WETH/cbETH/wstETH/rETH)** | LST/wrapped de-peg vs underlying | **MEDIUM** — recurring on Base; overlaps cross-DEX | PARTIAL (routes exist) |
| **Sandwich / frontrun** | Insert before+after victim | **NOT WORTH BUILDING** — no public mempool on Base; ethically/repetitionally toxic; out of scope per your mandate | N/A |
| **Cross-chain "atomic" FL** | borrow chain A → bridge → repay A | **NOT POSSIBLE atomically** — Phase-0 already flags; keep as non-atomic inventory strategy only | Correctly NOT modeled as atomic `[FACT]` |

`[REC]` Priority order for *new* families: **cross-pool/fee-tier scorer → stablecoin (Curve/StableSwap math) → per-block backrun trigger → liquidation adapters.** Sandwich and cross-chain-atomic are explicitly out.

---

## B. MEV / searcher infrastructure — capability matrix

`[EXT]` The 2026 reference searcher stack: event-driven collectors → **local pool-state cache updated from `Sync`/`Swap`/`Mint`/`Burn` logs (no RPC per quote)** → **local AMM math fast-filter (<100 ns, cfmms-rs style)** → **revm forked simulation with state overrides** → optimal sizing (ternary search on unimodal profit curve) → atomic executor / bundle submit. (paradigm Artemis, evm-amm-state, revm, rusty-sando, reth-mev, 2026)

| Capability | Importance on Base | ArbiCore classification `[FACT]/[INF]` |
|---|---|---|
| Real-time **block** monitoring (WSS `newHeads`) | **Critical** (per-block re-scan is the trigger) | **MISSING** — scanner runs on a fixed `interval_s` timer, not block events |
| **Mempool** monitoring | **Not applicable on Base** (private mempool) | Correctly absent; do NOT build for Base |
| **WebSocket feeds** | **Critical** | **MISSING** — quoting is request/response `eth_call` |
| **Local pool-state cache** | **Critical** (kills per-quote RPC latency) | **MISSING** — every hop is a live `eth_call` via `QuoterRegistry` |
| **Incremental pool updates** (log-driven) | **Critical** | **MISSING** |
| **Local AMM math** (Uni V3 tick math, Aerodrome CL, Curve invariant) | **Critical** | **WEAK** — relies on on-chain quoter, no local math kernel |
| **Route search** | High | **PRESENT** (`RouteSearchEngine` DFS, bounded) `[FACT]` |
| **Optimal trade sizing** | High | **PARTIAL** — `economics/size_optimizer.py` exists; not integrated into FL hot path `[FACT]` |
| **Transaction simulation** | Critical | **PARTIAL** — `atomic_executor_sim.py` + anvil/archive replay exist, but never PASSed on fixtures; not in per-candidate hot loop `[FACT]` |
| **Private tx submission** | Medium on Base (commercial private RPCs / Blink searcher net; no chain-level bundles) | **MISSING** (uses public broadcast path) |
| **Bundles / builder / relay** | **N/A on Base**; relevant only on Ethereum L1 | Correctly absent for Base |
| **Inclusion probability** | Medium (FCFS → latency proxy, not bid modeling) | **MISSING** — no execution-probability model |
| **Competitive bidding** | Low on Base FCFS (priority fee floor 5M WEI) | Not needed for Base FCFS `[EXT]` |
| **Reorg handling** | Low on Base (fast finality, rare shallow reorgs) | **MISSING** but low priority |

`[INF]` **The single biggest performance gap** is items 1–6: ArbiCore quotes **per-hop over the network** on a timer, while competitors quote **locally from a log-synced cache** and re-scan every block. This is *the* reason candidate throughput and freshness are limited, and it is the highest-leverage upgrade after correctness.

---

## C. DEX coverage — what matters per chain

`[EXT]` (eco.com/defillama/plisio 2026) + `[INF]` ranking for flash-loan arbitrage relevance:

| Chain | Must-cover venues (in priority order) | Notes |
|---|---|---|
| **Base** (primary) | **Aerodrome + Aerodrome Slipstream (50–63% of Base volume)**, Uniswap V3, Uniswap V4 (hooks), PancakeSwap V3/Infinity | ArbiCore already covers Aerodrome + Uni V3 `[FACT]`; **add Uni V4 + Pancake V3** |
| **Arbitrum** (2nd) | Uniswap V3/V4, **Camelot**, PancakeSwap V3, Curve | highest searcher density alongside Base `[EXT]` |
| **Ethereum** (data/quote only) | Uniswap V3/V4, **Curve**, Balancer V2/V3 | use for reference/liquidation, **not** for competing atomic arb `[INF]` |
| **Optimism** | **Velodrome** (ve(3,3), Aerodrome sibling), Uniswap V3 | marginal until Base+Arb saturated |
| **Polygon** | Uniswap V3, **Quickswap**, Curve | lowest priority; gas cheap but thinner opportunity density |

`[INF]` Concentrated-liquidity (Uni V3/V4, Aerodrome Slipstream, Curve V2) is now standard — a serious engine **needs local tick-aware CL math**, not just constant-product. This is a concrete gap (see B).

---

## D. Flash-loan providers — comparison

`[EXT]` (aave docs, morpho-blue, chen4903/FlashLoan-Comparisons, 2026):

| Provider | Fee | Liquidity / assets | Chains | Integration | Verdict for ArbiCore |
|---|---|---|---|---|---|
| **Balancer V2 Vault** | **0%** | unified vault, major assets | ETH/Base/Arb/OP/Poly | callback | **Primary** — already integrated `[FACT]`; zero fee = best for thin-margin L2 arb |
| **Aave V3** | 0.05% (gov-set `FLASHLOAN_PREMIUM_TOTAL`) | **deepest**, broadest assets, multi-asset `flashLoan` | ETH/Base/Arb/OP/Poly | `flashLoanSimple`/`flashLoan` | **Secondary** — already integrated `[FACT]`; use when Balancer liquidity insufficient |
| **Uniswap V3 flash** | pool tier (0.01–1%) | per-pool | all | `pool.flash()` callback | **Niche** — path-internal loans; integrated `[FACT]` |
| **Morpho Blue** | **0%** | singleton, gas-efficient | **ETH + Base** | singleton callback | `[REC]` **ADD** — free + cheap gas; strong Base fit |
| Balancer V3 | 0% | LST-heavy, hooks (late-2025) | ETH first | callback | Watch; add with LST strategies |
| FlashRouter-style meta-router | routes to cheapest | aggregates above | multi | one API | `[INF]` we should build our **own** provider-selection layer (§F), not depend on 3rd-party middleware |

`[REC]` Provider selection kernel: **prefer Balancer V2 (0 fee) → Morpho Blue (0 fee, Base) → Aave V3 (depth) → Uni V3 flash (path-internal)**, chosen per-route by *available liquidity for the borrow asset* via a **real `health_probe()`**, replacing today's config-toggle "enabled" (`[FACT]` Phase 0: providers are Protocol stubs, not health-probed).

---

## E. Competitive landscape — capabilities to extract (not a project list)

`[EXT]` Distilled architectural capabilities of serious open-source/production searchers (Artemis, reth-mev, rusty-sando, cfmms-rs, evm-amm-state, aether, mev-engineering-stack):

1. **No-RPC quoting**: local reserve/tick cache synced from event logs; RPC only for resync. (`evm-amm-state`)
2. **Two-stage pipeline**: pure-math fast filter (<100 ns) → revm forked sim with executor bytecode injected as state override. (`revm`, `aether`)
3. **Node-adjacent search**: run search inside/next to the node (reth-mev) to read state directly and cut latency.
4. **Graph pathfinding**: Bellman-Ford/SPFA negative-cycle detection for arbitrage discovery.
5. **Optimal sizing**: ternary/golden-section search on the (usually unimodal) profit curve; brute grid for non-monotone.
6. **Calldata decoders** for Universal Router / 1inch / Balancer Vault (for backrun targeting).
7. **Split-language**: Rust hot path (math/sim), Go/async I/O for network + submission; persistent bytecode caches (`redb`), bounded RPC concurrency (`tokio::Semaphore`).
8. **Route-aware submission** (L1 only): MEV-Share vs private builder, information-leakage-aware bidding.

`[INF]` **What ArbiCore already has that most bots lack:** governance/mode-ladder, provenance classification, evidence signing, shadow certification, capital policy, kill-switch, operator console. **What sophisticated searchers have that ArbiCore lacks:** items 1–5 above (local state, local CL math, revm sim in the hot loop, event-driven per-block triggering, integrated sizing). **Our moat is safety+provenance; our gap is speed+local-state.**

---

## F. ArbiCore capability comparison (consolidated)

| Capability | Classification |
|---|---|
| Closed-cycle route search | **ALREADY PRESENT** `[FACT]` |
| Honest live quoting (refuse-if-unpriceable) | **ALREADY PRESENT** (design principle worth preserving) `[FACT]` |
| Flash-loan economics (fee/gas/slippage/MEV/atomic-profit gate) | **ALREADY PRESENT** but on a **timer + per-hop RPC** `[FACT]` |
| Provider registry (Aave/Balancer/Uni) | **PARTIALLY PRESENT** — catalog yes, real health no `[FACT]` |
| Governance / mode ladder / capital policy / kill-switch | **ALREADY PRESENT** (competitive advantage) `[FACT]` |
| Provenance + certification + evidence signing | **ALREADY PRESENT** (but contaminable — Phase 0) `[FACT]` |
| Local pool-state cache | **MISSING** |
| Log-driven incremental updates | **MISSING** |
| Local AMM/CL/StableSwap math | **WEAK / MISSING** |
| revm/anvil sim in per-candidate hot loop | **PARTIALLY PRESENT** (exists, not in loop, never PASSed on fixtures) `[FACT]` |
| Per-block (WSS) trigger | **MISSING** |
| Optimal trade sizing integrated into FL path | **PARTIALLY PRESENT** (`size_optimizer.py` unwired) `[FACT]` |
| Real TVL / liquidity | **MISSING** (hardcoded `5_000_000` sentinel) `[FACT]` |
| ChainAdapter abstraction | **MISSING** `[FACT]` |
| Private/co-located RPC + WSS | **MISSING / infra** |
| Morpho Blue provider | **MISSING** |
| Uni V4 / Pancake V3 on Base | **MISSING** |
| Liquidation family | **MISSING** |
| Backrun (confirmed-state) family | **MISSING** |
| Sandwich / L1 bundles / builder | **NOT WORTH BUILDING YET** (Base has no bundles; L1 is a moat) |

---

## G. How Phase-0 defects map to profitability

`[INF]` Each Phase-0 defect is not just a correctness bug — it directly suppresses or *falsifies* opportunity discovery:

| Phase-0 defect | Profit impact |
|---|---|
| thin_activator writes `SIMULATED` into canonical repo | **Falsifies** the opportunity stream; operators can't trust counts; certification inflated |
| `noop_quote_provider` default / activation gated by env | If canonical scanner isn't live-wired → **every candidate `venue_unreadable`** → 0 real discovery |
| OBSERVE silent fallback | Opportunities silently dropped as "no analysis" → **hidden zeroing** of the funnel |
| dual economics surfaces | Two different profit numbers → **untrustworthy ranking** |
| dual RPC namespaces | UI says configured, scanner reads a different var → **quotes fail → venue_unreadable** |
| hardcoded TVL sentinel | Gate 8 is a no-op → **no real liquidity/sizing** → false positives or bad fills |
| certification provenance contamination | Synthetic counted as executable → **fake "readiness"** |
| no ChainAdapter | Multi-chain is code-work → **expansion stalls** |
| only Base wired | Single chain → fine (Base-first is correct) but no redundancy |

**→ TIER 0 must land before any performance work, or every downstream metric lies.** `[INF]`

---

## H. What our infra (12 vCPU / 48 GB) can vs cannot do

`[INF]` grounded in `[EXT]` latency thresholds (P50 <120 ms, P95 <200 ms to Base WSS; opp lifespan <340 ms).

**Achievable now on this box:**
- Local pool-state cache for Base's relevant venue graph (hundreds of pools → easily <1 GB RAM; Redis + in-proc).
- Log-driven incremental updates via WSS `logs` subscriptions.
- Local AMM math (Uni V3 tick math, Aerodrome CL, Curve invariant) in Python (numba/np) or a small Rust sidecar.
- Per-block re-scan of the full Base graph within the latency budget **if quoting is local** (not per-hop RPC).
- revm/anvil simulation as a co-located sidecar for final validation of top-N candidates.
- Bounded-concurrency async orchestration, MongoDB persistence, Redis queue/cache.
- **Single-chain (Base) searcher-grade loop is comfortably within 12 vCPU / 48 GB.** `[INF]`

**Requires better/added infra:**
- **Tier-1 private RPC + WSS, co-located us-east (near Coinbase sequencer, AWS us-east-1).** This is the **#1 external dependency**; public `mainnet.base.org` is rate-limited and unusable for production `[EXT]`.
- Self-hosted **op-node** (rate-limit immunity, sequencer gossip) — advanced/optional; adds CPU/disk + ops.
- **Sub-120 ms P50** execution latency → benefits from co-location; a generic VPS region may miss the tightest opps but still captures the wider band `[INF]`.
- **Multi-chain in parallel** → each added chain = another WSS+RPC+cache+sim pipeline; 2 chains fit on 12 vCPU, 4–5 chains will contend for CPU during volatility and likely need a second box `[INF]`.
- Rust hot-path (only if Python sizing/sim proves too slow at per-block cadence) — engineering cost, not hardware.

**Python caveat** `[INF]`: Python is fine for detection/orchestration/economics; the tightest atomic races (<340 ms, full-block CL recompute) may need a Rust/numba kernel for the math filter. Start Python; measure; offload only the proven bottleneck.

---

## I. Upgrade ranking (multi-factor)

Scale: ★☆☆ low → ★★★ high. "Diff" = implementation difficulty (higher = harder).

| Upgrade | Opp ↑ | Profit ↑ | Diff | Latency | Reliability | Capital/Risk | Infra cost |
|---|---|---|---|---|---|---|---|
| **T0** Quarantine thin_activator + provenance write-gate | ★★★ (trust) | ★★☆ | ★☆☆ | – | ★★★ | ★★★ (safety) | none |
| **T0** Deterministic live-quoter wiring + kill OBSERVE-silent | ★★★ | ★★☆ | ★☆☆ | – | ★★★ | ★★☆ | none |
| **T0** Single economics kernel + single RPC namespace | ★★☆ | ★★☆ | ★★☆ | – | ★★★ | ★★☆ | none |
| **T1** Real TVL/liquidity + integrate size_optimizer | ★★☆ | ★★★ | ★★☆ | – | ★★☆ | ★★★ | none |
| **T1** Private co-located Base RPC + **WSS block/log feed** | ★★★ | ★★★ | ★★☆ | ★★★ | ★★★ | ★☆☆ | $ (RPC plan) |
| **T2** **Local pool-state cache + local AMM/CL math** (no-RPC quoting) | ★★★ | ★★★ | ★★★ | ★★★ | ★★☆ | ★☆☆ | none (uses box) |
| **T2** Per-block trigger + two-stage (fast filter → revm sim) | ★★★ | ★★★ | ★★★ | ★★★ | ★★☆ | ★★☆ | CPU |
| **T3** Morpho Blue + Uni V4 + Pancake V3 (Base) | ★★☆ | ★★☆ | ★★☆ | – | ★★☆ | ★★☆ | none |
| **T3** Stablecoin (Curve math) + cross-pool scorer | ★★☆ | ★★☆ | ★★☆ | – | ★★☆ | ★★★ | none |
| **T3** Liquidation family (Aave/Comet adapters + oracle watch) | ★★☆ | ★★★ | ★★★ | ★★☆ | ★★☆ | ★★☆ | none |
| **T4** ChainAdapter + Arbitrum | ★★☆ | ★★☆ | ★★★ | – | ★★☆ | ★★☆ | $ (RPC) + CPU |
| **T4** Optimism / Polygon | ★☆☆ | ★☆☆ | ★★☆ | – | ★★☆ | ★★☆ | $$ |
| **T5** Private submission (Blink/commercial) + inclusion model | ★☆☆ | ★★☆ | ★★☆ | ★★☆ | ★★☆ | ★★☆ | $ |
| **T5** Rust hot-path / self-hosted op-node | ★☆☆ | ★★☆ | ★★★ | ★★★ | ★★☆ | ★☆☆ | $$$ |

---

## J. Smallest change → largest opportunity increase (§11)

`[INF]` **The minimal high-leverage set:**

1. **Make the canonical FL scanner authoritative and actually live-wired at boot** (deterministic `make_live_quote_provider` install; quarantine thin_activator; OBSERVE→explicit error). → converts "0 executable / contaminated stream" into a *trustworthy real* stream. **Effort: low. Impact: unlocks everything.**
2. **Replace per-hop `eth_call` quoting with a local, log-synced pool-state cache + local AMM/CL math**, driven by a **WSS per-block trigger** on a **private co-located Base RPC**. → this alone likely multiplies the number of *fresh, real* candidates evaluated per unit time by 1–2 orders of magnitude while cutting quote latency, which is the binding constraint given <340 ms opp lifespan. **Effort: medium-high. Impact: the biggest single profitability lever.**
3. **Real TVL + integrated optimal sizing.** → turns "priced" routes into *correctly-sized, executable* ones and activates the (currently no-op) liquidity gate. **Effort: medium. Impact: converts discoveries into fills.**

Everything else (more families, more chains) is additive but secondary to (1)–(3).

---

## K. Should ArbiCore become an integrated searcher plane? (§7)

`[REC]` **Yes — integrate, do not fork a separate bot.** Rationale `[INF]`:
- ArbiCore already owns the *hard governance surface* (mode ladder, capital policy, kill-switch, provenance, certification, evidence) that a greenfield bot would take months to earn trust on.
- The searcher hot-path (state cache + AMM math + sim + atomic executor) is *additive* to the existing canonical scanner/verifier/economics/executor chain — it slots in as a faster quote+trigger substrate behind the same gates.
- A separate bot would recreate the competing-authority problem Phase 0 just diagnosed. One canonical plane, one provenance model, one economics kernel.
- Keep the honest-refusal principle (`venue_unreadable` when unpriceable) — it is a *feature* vs bots that fabricate profit.

---

## L. Final prioritized roadmap

> Governance rule preserved throughout: OBSERVE→PAPER→SHADOW→LIMITED_LIVE→FULL_LIVE; never auto-promote; never fabricate data; never lower gates to inflate counts.

**TIER 0 — Correctness / architecture (must land first; low effort, high trust)**
- Quarantine `ContinuousDiscovery`/thin_activator from `_CANONICAL_OPP_REPO`; route to a `SYNTHETIC/TEST` collection; provenance write-gate on canonical repo.
- Deterministically wire the live quote provider to the canonical FL scanner at boot; make OBSERVE-fallback an explicit health error, not silent.
- Converge to **one** economics kernel and **one** RPC config namespace (persistent `NetworkConfigRepo` via `env_sync`, with legacy aliases written for compatibility).
- Certification: count real vs synthetic separately; exclude synthetic from executable metrics.
- Confirm `ensure_defaults()` seeds the canonical DB on boot (add a startup health assertion).

**TIER 1 — Base profitability foundation**
- Real TVL/liquidity per pool; activate Gate 8; integrate `size_optimizer` into the FL path (ternary-search sizing).
- Provision **tier-1 private co-located Base RPC + WSS**; add block/log subscriptions.
- Real provider `health_probe()` (Balancer V2 / Aave V3 / Uni V3 flash) + provider-selection kernel (prefer 0-fee).

**TIER 2 — MEV/searcher performance (the big lever)**
- Local pool-state cache synced from `Sync`/`Swap`/`Mint`/`Burn` logs (no RPC per quote).
- Local AMM/CL/StableSwap math kernel (Uni V3 tick, Aerodrome CL, Curve invariant).
- Per-block trigger + two-stage pipeline: fast math filter → revm/anvil forked sim (state-override executor) for top-N.
- Bounded concurrency, circuit breakers, latency metrics (scan/quote/sim/exec P50/P95).

**TIER 3 — Additional flash-loan strategies**
- Add Morpho Blue (0-fee, Base) provider; add Uniswap V4 + PancakeSwap V3 venues on Base.
- Cross-pool/fee-tier arbitrage scorer; stablecoin dislocation (Curve StableSwap math).
- Confirmed-state backrun family (per-block price-impact detection).
- Liquidation-assisted family (Aave V3 / Compound-style adapters + oracle-update watch), flash-funded.

**TIER 4 — Multi-chain expansion (only after Base is saturated)**
- Build the `ChainAdapter` abstraction (chainId/native/RPC/finality/gas/token+DEX+FL registries/quoter/sim/executor/health/capability).
- **Arbitrum** first (highest independent density): Uniswap V3/V4, Camelot, PancakeSwap V3.
- Optimism (Velodrome) / Polygon (Quickswap) only if economics justify the added RPC/CPU cost.
- Chain activation gate: RPC+identity+token/DEX+quote+gas+sim+FL-provider+execution health all green.

**TIER 5 — Advanced MEV infrastructure (optional / high cost)**
- Private submission (Blink searcher net / commercial private RPC) + inclusion-probability model.
- Rust hot-path kernel and/or self-hosted co-located op-node (rate-limit immunity, sequencer gossip).
- Reorg handling (low priority on Base).

---

## M. Explicit caveats

- `[EXT]` sources are 2026-current web research; on-chain numbers (fees, TVL, gas) drift — re-verify `FLASHLOAN_PREMIUM_TOTAL`, Base priority-fee floor, and venue TVL before implementation.
- `[INF]` The "1–2 orders of magnitude more candidates" from local-state quoting is a reasoned estimate, not a measured `[FACT]`; it must be proven with a benchmark in Tier 2.
- **More chains ≠ more profit** `[INF]`: Optimism/Polygon show lower searcher density than Base/Arbitrum; adding them before Base is saturated dilutes CPU/latency for marginal gain.
- Ethereum L1 atomic arb is **not recommended** for our capital/infra tier `[EXT]` — use L1 for quotes/liquidation reference only.
- Nothing here weakens governance, gates, provenance, or signing. Tier 0 *strengthens* provenance.

**STOP — awaiting approval before any implementation.** Report saved to `docs/FLASH_LOAN_MARKET_COMPETITIVE_AUDIT.md`.
