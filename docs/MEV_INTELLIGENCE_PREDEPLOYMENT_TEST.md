# MEV Intelligence — Pre-Deployment READ-ONLY Test

**Mode:** research/analysis only. **No** execution, signer, broadcast, gate/kill-switch/
allowlist/Mongo changes. Safety posture unchanged: **SHADOW=READY · PAPER=BLOCKED ·
LIMITED_LIVE=BLOCKED · FULL_AUTOMATION=BLOCKED.**
**No fabricated opportunities or profits.** Every transaction below is a real, publicly
verifiable Base mainnet tx hash. Fields that public data cannot reliably reconstruct are
left explicitly as **NOT RECONSTRUCTABLE / DATA INSUFFICIENT** — never guessed.

---

## EXECUTIVE SUMMARY

- **Data source:** public Base mainnet JSON-RPC `https://mainnet.base.org` (chain_id **8453**),
  read-only, via an isolated probe script (`/app/scripts/mev_intel_readonly.py`). Provenance =
  **PUBLIC_RESEARCH** (public chain data).
- **TODAY (chain UTC):** **2026-09-03**. Sampled window: blocks **50,831,821 → 50,833,821**
  (2,000 blocks ≈ **16:32:03 → 17:38:43 UTC**, ~67 min). A full-day scan (~43k Base blocks) is
  **not feasible** on a rate-limited public RPC in this environment (see *Data limitations*).
- **Observed in-window:** **65** flash-loan transactions (Aave V3 + Balancer V2); **40**
  reconstructed; **7** are arbitrage-shaped (flash-loan + ≥2 DEX swap legs, success).
- **Dominant real pattern today:** *Balancer V2 fee-free flash loan → 2 Uniswap V3 swaps →
  repay* (classic 2-leg DEX↔DEX atomic arb), tiny gas (~2.5e-6 ETH), small notionals
  (~0.0067–0.0089 WETH or ~431 USDC).
- **Decisive limitation:** the public RPC **does not support `debug_trace*` / `trace_block`**,
  so **searcher gross/net profit and builder bribes are NOT reliably reconstructable**. Gas
  cost and priority fee *are* (from receipts). Per directive, profit is reported as
  **NOT RECONSTRUCTABLE**, not fabricated.
- **ArbiCore replay:** these opportunities are **architecturally detectable** by ArbiCore
  (archetypes `dex_dex`/`flash_funded`; Uniswap V3/V2 + Balancer supported). But ArbiCore's
  **own** economics/EV/simulation require a configured RPC + live quotes/liquidity, which are
  **not provisioned** (`ARBICORE_RPC_URL` unset) — so a **quantitative** capturable-profit
  figure is **DATA INSUFFICIENT**. No second economics model was invented for this test.

---

## TODAY'S OBSERVED MEV ACTIVITY (real, verifiable)

| Metric | Value |
|---|---|
| Chain | Base mainnet (8453) |
| TODAY (UTC) | 2026-09-03 |
| Window blocks | 50,831,821 – 50,833,821 (2,000) |
| Window UTC | 16:32:03 – 17:38:43 (~67 min) |
| Flash-loan txs observed | 65 |
| Flash-loan txs reconstructed | 40 (bounded cap) |
| Arbitrage-shaped (flash + ≥2 swaps, ok) | 7 |
| Trace support on RPC | **No** (`debug_trace*`/`trace_block` unsupported) |

**Classification coverage (§4):** observable in-window today —
A. DEX→DEX arbitrage ✅ (7 samples), B. Multi-hop ⚠️ (2-leg seen; ≥3-leg not in sample),
C. Flash-loan-assisted ✅ (all 65), D. Cross-pool ✅ (distinct pools per tx),
E. Stablecoin arb ⚠️ (USDC-funded sample present), F. Liquidation flash liquidity —
not isolated in this window, G. Lending atomic — not isolated, H. Backrun/ordering —
**not attributable without traces/mempool**, I. Other complex atomic — not isolated.

---

## FLASH-LOAN ACTIVITY

- **Providers observed:** Balancer V2 Vault (`0xBA12…F2C8`) and Aave V3 Pool
  (`0xA238…d1c5`). The 7 arb-shaped txs today were **all Balancer V2** (fee-free flash),
  consistent with fee-minimising 2-leg arbs.
- **Borrowed assets/amounts (real, decoded from the FlashLoan event):** WETH ~0.0067–0.0089,
  or USDC 431.25. **Balancer flash fee = 0.** Flash-loan size ≠ profit (per directive).

## ARBITRAGE ACTIVITY

All 7 are single-tx atomic flash arbs: borrow → 2 swaps (Uniswap V3, one V3+V2) → repay,
success status = 1, very low gas. This matches ArbiCore's `dex_dex`/`flash_funded` archetypes.

---

## TOP OBSERVED OPPORTUNITIES (real tx hashes — verifiable on Basescan)

Amounts human-readable; **actual net profit = NOT RECONSTRUCTABLE** (no trace/balance-diff).

| # | Tx hash | Block | Flash (provider / asset / amount) | Route (swap legs) | Distinct pools | Gas cost (ETH) | Priority fee (ETH) | Actual net profit |
|---|---|---|---|---|---|---|---|---|
| 1 | `0x85b73563…3ac48f` | 50,831,898 | Balancer V2 / WETH / 0.006752 | 2× Uniswap V3 | 2 | 0.0000024 | ~0 | NOT RECONSTRUCTABLE |
| 2 | `0x42756211…c05bc13` | 50,832,048 | Balancer V2 / USDC / 431.25 | Uni V3 + Uni V2 | 2 | 0.00007974 | see note | NOT RECONSTRUCTABLE |
| 3 | `0x21e6af50…05a2f3` | 50,832,056 | Balancer V2 / WETH / 0.006740 | 2× Uniswap V3 | 2 | 0.00000261 | ~0 | NOT RECONSTRUCTABLE |
| 4 | `0xa6efd514…94940bc` | 50,832,135 | Balancer V2 / WETH / 0.008940 | 2× Uniswap V3 | 2 | 0.00000256 | ~0 | NOT RECONSTRUCTABLE |
| 5 | `0x7644b13a…538e94e` | 50,832,293 | Balancer V2 / WETH / 0.006749 | 2× Uniswap V3 | 2 | 0.00000255 | ~0 | NOT RECONSTRUCTABLE |
| 6 | `0x6859405f…01fa74a` | 50,832,372 | Balancer V2 / WETH / 0.008118 | 2× Uniswap V3 | 2 | 0.00000255 | ~0 | NOT RECONSTRUCTABLE |
| 7 | `0xcb7a0e42…f66914` | 50,832,452 | Balancer V2 / WETH / 0.008938 | 2× Uniswap V3 | 2 | 0.00000261 | ~0 | NOT RECONSTRUCTABLE |

Full hashes + raw evidence: `/app/docs/mev_evidence/arb_enriched.json`,
`/app/docs/mev_evidence/mev_probe_1.json`.
**Liquidity/slippage per pool:** DATA INSUFFICIENT here — requires per-pool reserve/tick reads
(archive state at block) which the public RPC did not reliably serve for the sampled blocks.

---

## ARBICORE X THEORETICAL CAPTURE ANALYSIS

Using the **existing** ArbiCore architecture (no new economics model). Where a check needs
ArbiCore's live economics (quotes/liquidity/EV/simulation) it is marked **DATA INSUFFICIENT**
because `ARBICORE_RPC_URL` is unset in this environment and traces are unavailable.

Per representative opportunity (all 7 share the same shape):

| Check | Result | Basis |
|---|---|---|
| ArbiCore detectable? | **YES** | maps to `dex_dex`/`flash_funded` archetype (allow-listed strategy_type) |
| Route-supported? | **YES** | Uniswap V3 (`v3_state`/quoter), Uniswap V2, Aerodrome all supported |
| DEX-supported? | **YES** | Uniswap V3/V2 supported; Balancer V2 modelled in flash allowlist |
| Sufficient liquidity? | **DATA INSUFFICIENT** | needs live pool reserves/ticks (RPC not wired) |
| Slippage acceptable? | **DATA INSUFFICIENT** | needs live quote vs size (RPC not wired) |
| Economics positive? | **DATA INSUFFICIENT** | ArbiCore `net_profit` needs live quote+gas+repayment |
| EV positive? | **DATA INSUFFICIENT** | ArbiCore EV needs confidence + live inputs |
| Simulation requirements satisfied? | **NO (fail-closed)** | ArbiCore sim gate requires live eth_call preflight (RPC) → cannot pass without RPC |
| Executor-compatible? | **PARTIAL** | proven executor path is **Aave V3**; these are **Balancer V2** flash — Balancer executor path is **unverified** in current build → likely executor limitation |
| Theoretically capturable? | **UNPROVEN** | detectable & route-supported, but economics/sim/executor cannot be certified in this env |
| Estimated ArbiCore net profit | **DATA INSUFFICIENT** | will not fabricate |

**Interpretation (honest):** ArbiCore can *see and shape* these opportunities (detection +
routing + flash archetype). It **cannot be shown to capture** them here because (a) its own
economics/simulation need a configured RPC, and (b) the proven executor path is Aave V3 while
today's live arbs used Balancer V2. Both are *provisioning/coverage* gaps, not fabricated wins.

---

## IMPORTANT FINAL TABLE

| Opportunity | Actual Net Profit | ArbiCore Detectable | Economically Positive | Executable Under Current Architecture | Estimated Capturable Net Profit |
|---|---|---|---|---|---|
| #1–#7 (Balancer flash + 2 DEX legs) | NOT RECONSTRUCTABLE | YES | DATA INSUFFICIENT (needs ArbiCore live economics) | PARTIAL — Balancer executor path unverified (Aave path proven) | DATA INSUFFICIENT — not fabricated |

### Summary counts (this bounded window)

- **TOTAL OBSERVED PROFIT:** NOT RECONSTRUCTABLE (no trace/balance-diff on public RPC).
- **TOTAL POTENTIALLY ADDRESSABLE PROFIT:** DATA INSUFFICIENT (7 opportunities are
  *addressable in shape*; monetary value not reconstructable).
- **TOTAL THEORETICALLY CAPTURABLE PROFIT (estimated):** DATA INSUFFICIENT — not fabricated.
- **NUMBER OF CAPTURABLE OPPORTUNITIES:** 0 *proven* capturable (cannot certify economics/sim/
  executor in this env); 7 *detectable & route-supported*.
- **NUMBER REJECTED BY ECONOMICS:** unknown (economics not runnable — RPC unset).
- **NUMBER REJECTED BY LIQUIDITY/SLIPPAGE:** unknown (live pool state unavailable).
- **NUMBER REJECTED BY SIMULATION:** 7 would fail-closed *here* (sim gate needs live eth_call).
- **NUMBER REJECTED BY EXECUTOR LIMITATIONS:** up to 7 (Balancer V2 executor path unverified;
  proven path is Aave V3).
- **NUMBER WHERE DATA WAS INSUFFICIENT:** 7 (net-profit reconstruction blocked by no traces).

Wording per directive: values above are *estimated theoretical* at most; there is **no
"expected earnings"** claim — evidence does not support it.

---

## OUR CURRENT ARBICORE BASELINE (context, not today's whole market)

Latest known ArbiCore internal baseline: 134 routes · 16 evaluated · 13 real quotes ·
13 negative economics · 0 positive net · 0 positive EV · 13 simulation candidates ·
0 simulation passes. This is ArbiCore's **internal** run, **not** the whole Base market today.
It is consistent with today's observation that live Base flash-arbs are **small-notional,
thin-margin** — most fail ArbiCore's conservative net/EV gates, which is the intended
fail-closed behavior, not a defect.

---

## MEV INTELLIGENCE — DESIGN FINDINGS (what the real feature needs)

Derived from what was reconstructable vs blocked. **Not built now** — this is scoping.

### MUST HAVE
- **Trace/archive RPC integration** (`debug_traceTransaction` / `trace_block` or balance-diff
  on archive) — the single blocker for real gross/net profit + builder-bribe reconstruction.
- **Flash-loan event ingestion** (Aave V3 + Balancer V2 topics) — already proven reconstructable
  from public logs (asset/amount/premium).
- **Swap-leg decoding** (Uniswap V3/V2 + Aerodrome swap topics) → route reconstruction.
- **Per-tx gas + priority-fee accounting** (from receipt: gasUsed × effectiveGasPrice, and
  effective − baseFee) — already reconstructable.
- **Provenance tagging** on every observation (PUBLIC_RESEARCH by default; never mark observed
  third-party searcher strategies as INTERNAL/GENERATED).
- **Read-only isolation** (no execution authority; must pass existing ArbiCore gates to matter).

### SHOULD HAVE
- **Per-pool live state reads** (V3 tick/liquidity, V2 reserves) for slippage/liquidity checks.
- **Searcher/builder attribution** (sender, coinbase transfers via traces).
- **Bounded time-window aggregation** with pagination to cover a full UTC day within rate limits.
- **ArbiCore replay harness** that feeds observed routes into the *existing* economics/EV/sim
  engine (once RPC is wired) to produce a genuine capturable-profit estimate.
- **Balancer V2 executor-path coverage** assessment (today's arbs were Balancer-funded).

### LATER
- Cross-chain MEV comparison (labelled supplementary only).
- Liquidation / lending-atomic classifiers (F/G) once trace data available.
- Backrun/ordering detection (needs mempool + block-ordering data).
- Historical trend dashboards / competitiveness benchmarking.

---

## FINAL REPORT (§12)

- **Data sources used:** public Base mainnet JSON-RPC `mainnet.base.org` (read-only). No private
  repos, no paywalls, no prohibited scraping. Provenance: PUBLIC_RESEARCH.
- **Date/time window:** 2026-09-03 UTC, blocks 50,831,821–50,833,821 (~16:32–17:38 UTC, ~67 min).
- **Transactions examined:** ~40 flash-loan tx receipts reconstructed out of 65 flash-loan txs
  detected via event logs in-window.
- **Classified:** 7 arbitrage-shaped flash-loan txs (all Balancer V2 + 2 DEX legs).
- **Flash-loan transactions:** 65 detected (Aave V3 + Balancer V2).
- **Arbitrage transactions:** 7 (in the reconstructed subset).
- **Reliable profit reconstruction:** **0** — blocked by lack of trace/archive RPC (no fabrication).
- **Potentially addressable by ArbiCore:** 7 (by shape/route); monetary value DATA INSUFFICIENT.
- **Theoretically capturable:** 0 proven (economics/sim/executor not certifiable in this env).
- **Estimated theoretical capturable net profit:** DATA INSUFFICIENT — not fabricated.
- **Major rejection reasons:** simulation fail-closed (no live RPC), executor path (Balancer vs
  proven Aave), and unquantifiable economics/liquidity without RPC.
- **Data limitations:** public RPC = no `debug_trace*`/`trace_block`, no reliable archive state,
  rate-limited (full-day/all-provider scan infeasible); net profit/builder bribe not derivable.
- **Provenance limitations:** on-chain sender is observable but searcher identity/strategy intent
  is not; observed strategies are third-party PUBLIC_RESEARCH observations, not our IP.
- **Recommended permanent features:** see MUST/SHOULD/LATER above — headlined by trace/archive
  RPC + flash/swap event ingestion + an ArbiCore-replay harness on the existing engine.

**Blocker to a complete, monetised result:** provision a **trace-enabled archive Base RPC**
(e.g. Alchemy/QuickNode with `debug_traceTransaction`) and wire `ARBICORE_RPC_URL`. Until then
net-profit and ArbiCore capturable-profit remain honestly **DATA INSUFFICIENT**.

*No deployment. No live execution. No safety changes. No Mongo writes. Stopping for approval.*
