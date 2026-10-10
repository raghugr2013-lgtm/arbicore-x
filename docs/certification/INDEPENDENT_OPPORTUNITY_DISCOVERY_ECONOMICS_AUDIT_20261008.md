# ARBiCORE X — Independent Opportunity Discovery & Economics Audit

**Date:** 2026-10-08  
**Mode:** READ-ONLY forensic research. No production code, MongoDB, queue, Gate7, RPC, Hybrid E, scanner, deploy, LIVE, signing, or broadcast changes.  
**Production changes:** 0 · **Deployments:** 0 · **Live transactions:** 0

**Status gates (given, verified against artifacts):**

| Gate | Status | Verified |
|---|---|---|
| Hybrid E | PASS | `/tmp/hybrid-e-rpc-9244ebd_shadow/summary.json` SHADOW PASS_OBSERVABILITY |
| RPC fallback `9244ebd` | PASS / FROZEN | same; no further RPC tuning |
| Pre-verification economic signal | NO-GO | `/tmp/candidate_funnel_audit/` — no pre-verify P&L; last-24h Gate7 n=4,848 all &lt;$0 (best −$60.25) |

**Artifacts reused (not rebuilt):**

| Artifact | Path |
|---|---|
| E1 recall audit | `docs/certification/PHASE_0_5_REALIZED_ARBITRAGE_RECALL_AUDIT_20261005.md` |
| E1.5 v4/v2 replay | `docs/certification/PHASE_0_5_E1_5_V4_V2_COVERAGE_REPLAY_AUDIT_20261005.md` |
| E1.6 TRUMP / alpha | `docs/certification/PHASE_0_5_E1_6_ADDITIONAL_REPLAY_ALPHA_CONFIRMATION_20261005.md` |
| E1 census digest | `/tmp/e1_audit/class_digest.txt` |
| E1.5 raw | `/tmp/e15/*.json` |
| E1.6 raw | `/tmp/e16/econ.json`, `rest.json` |
| Flash census | `/tmp/census2.json`, `/tmp/realized_arb_census.json` |
| Funnel / Gate7 | `/tmp/candidate_funnel_audit/FUNNEL_AUDIT_REPORT.md` |
| Root-cause memo | `docs/certification/ARBiCORE_X_ROOT_CAUSE_AND_BEST_PATH_ANALYSIS_20261005.md` |

Evidence labels below: **PROVEN**, **RECONSTRUCTED**, **INFERRED**, **NOT_PROVABLE**.

---

## Phase 1 — Independent opportunity universe

Universe is **not** “what ArbiCore discovered.” Sources in preference order:

### U1 — E1 six-chain flash-classified atomic arbs (1 hour)

From `/tmp/e1_audit/class_digest.txt` (**PROVEN**):

| Metric | Value |
|---|---:|
| `ATOMIC_ARB` total | 289 |
| of which flash-sourced (`flash_arbs`) | **247** |
| multipool non-flash sample | 42 |
| Multipool nonflash population | ~21,522 (E1.5 cites 21,868) |

**Verified:** “247 closed cycles” in prior briefing maps to **`flash_arbs 247`**, not a separate closed-cycle table.

Recall labels on the 247 (**PROVEN**):

| Recall | n |
|---|---:|
| `MISSED_SIZE` | 92 |
| `MISSED_COVERAGE` | 79 |
| `OUTSIDE_UNIVERSE` | 65 |
| `POTENTIALLY_FOUND` | **11** |

Naive ERC-20 net ≥ $25: **9** rows (same nine as E1.5). Of those, **8/9** touch Uniswap v4 PoolManager `0x000000000004444c5dc75cB358380D2e3dE08A90` (**PROVEN** from `/tmp/e15/phase1.json`).

### U2 — E1.5 exact 9-row corpus (replayed)

Ethereum blocks 26,125,444–26,125,744. All nine receipts re-read; E1.5 replayed **9/9** (**PROVEN**).

### U3 — E1.6 TRUMP bridge census (same hour, not flash-limited)

| Set | n | Label |
|---|---:|---|
| Forward closed WETH cycles | **68** | **PROVEN** (`/tmp/e16/econ.json` `candidate_cycles`) |
| Reverse closed taxed cycles | **55** | **PROVEN** |
| Reverse non-closed (double-lot) | 3 | excluded — not closed arb |
| Distinct previous-block states with peak ≥ $25 | **7** | **PROVEN** |

Mechanism: two MAGA/TRUMP tokens + Uniswap v2 WETH pairs + mint/redeem (`0x24a29d50` / `0x41477451`) with **0.9801** mint ratio = two 1% taxes (**PROVEN**).

### U4 — Flash+v4 intersection (same hour)

45 flash-loan txs that also emitted v4 Swap (**PROVEN**, E1.5/E1.6).

### U5 — ArbiCore verified candidates (context only; circular for discovery)

| Population | Gate7 ≥ $0 | Gate7 ≥ $25 | Best net |
|---|---:|---:|---:|
| SHADOW 288 (2026-10-05) | 0 | 0 | −$59.31 |
| Funnel last 24h Gate7 denials | 0 / 4,848 | 0 | −$60.25 |
| Hybrid E `9244ebd` window | 0 | 0 | −$59.77 |

Pre-verify fields store fee/TVL/hops only — **no gross/net** (**PROVEN**, funnel audit). Matches STATUS “pre-verification NO-GO.”

**Artifact gap (verified by inventory):** full E1 row dumps `/tmp/e1_arbs.json` and `/tmp/e1_kept_*.json` are **gone**; recoverable corpus is `/tmp/e1_audit/class_digest.txt` + `/tmp/e15` + `/tmp/e16` + the Phase 0.5 markdowns. No exact “25,000 candidates / best net −$53.86” Gate7 signal audit was found on disk. Closest measured best nets: SHADOW **−$59.31**, funnel 24h **−$60.25**, Hybrid **−$59.77**; MULTI_DEX family best **−$153.86**. Qualitative STATUS (Gate7 ≥ $0 = 0, weak/no pre-verify signal) stands.

---

## Phase 2 — Economic classification

Thresholds used throughout:

- **Gross / before-builder:** swap surplus − gas (− flash fee when observed).
- **Searcher net:** before-builder − observed coinbase tip / priority-fee bid.
- **Gate7 bar (reporting):** $25; dynamic floor may be $0 but does not create edge if quote is negative.

| Cat | Definition | Independent evidence |
|---|---|---|
| **1** Clearly profitable after reconstructable costs **and** after competition (≥ $25 kept) | **0** events | E1.6: all 7 pre-block ≥$25 cells kept ≤ $7.28 |
| **2** Grossly profitable; not after gas/fees | Majority of naive E1 “large WETH” rows | E1.5: 8/9 collapse to pennies after native ETH |
| **3** Gross exists; competition/builder removes most/all | **COMPETITION_ERASED** | TRUMP 7 cells: peaks $31–$119 → kept $0.96–$7.28 |
| **4** Insufficient data | Many of 247; Polygon/BNB incomplete in early E1; ~5,377 non-flash v4 txs unpriced | **NOT_PROVABLE** as profit distribution |
| **5** Not actually arb | Aave 718.89 WETH migration; 3 double-lot reverse TRUMP | **PROVEN** |

Confidence: **HIGH** on U2/U3 reconstructed rows; **MEDIUM** on U1 family labels; **LOW** on dollar TAM of unpriced residual.

---

## Phase 3 — Realized net economics (mandatory split)

### E1.5 nine-row corrected summary (**RECONSTRUCTED**)

| # | Naive E1 USD | Corrected before builder | Searcher kept | Builder/tip | Class |
|---|---:|---:|---:|---:|---|
| 1 | 2,503 | +$0.10 | −$0.19 | $0.30 | Cat 2/3 |
| 2 | 350 | $32.97 (mostly TRUMP v2) | $2.97 | ~$30 | Cat 3 |
| 3–6,8 | 34–142 | $0.09–$0.79 | $0.04–$0.60 | small | Cat 2 |
| 7 | 37.59 | $37.59 realized; **$5.96** prev-block peak (E1.6 two-tax) | $3.39 | $34.20 | Cat 3 / TRADE_BLOCK boosted |
| 9 | ~1.95M | not arb | — | — | Cat 5 |

Flash fees on decoded Morpho/Balancer events: **0** where observed (**OBSERVED**).

### TRUMP forward closed cycles (**PROVEN**, `/tmp/e16/econ.json`)

| Bucket | n |
|---|---:|
| Gross &gt; $0 | 68 |
| Before builder ≥ $25 | 8 |
| After builder ≥ $25 | **0** |
| After builder &gt; $0 | 67 |
| Max searcher net | **$14.33** (TRADE_BLOCK_ONLY) |
| Max pre-block peak | **$118.81** |

SEARCHER GROSS ≠ SEARCHER NET ≠ BUILDER PAYMENT — auction took essentially all ≥$25 surplus.

### Flash+v4 (45) after native-ETH accounting

Aside from migration + mixed TRUMP row: next after-gas surpluses **$4.78, $2.97, $1.47**; none Gate7-scale after tip (**PROVEN**).

---

## Phase 4 — Pre-transaction replay (no hindsight leakage)

| Opportunity | Pre-tx state | Quote method | Result |
|---|---|---|---|
| TRUMP 7 cells | `getReserves` at block N−1; traded size + 0.01 ETH grid | v2 CP + 0.9801 tax | Peaks $31–$119; **$10k size −$1k+** |
| v4 IMD | previous block | v4 quoter | +$0.28 |
| v4 APE/FUSE | previous block | v4 | negative; pennies only in-block |
| v4 WBTC public | previous block | v4→v3 | negative at $2.5k and $10k |
| ArbiCore covered pools (SHADOW) | `latest` live quote | QuoterV2 path | gross ≤ 0 on all 180 bundles |

**If ArbiCore had known the TRUMP state at N−1:** a correctly sized quote could see ≥$25 **before** the auction. The production engine quotes **$10,000** and would see a large **loss**. It has **no** adapter for the mint/redeem hop.

---

## Phase 5 — Discovery coverage test

| Event class | Chain covered? | Venues? | Pools? | Tokens? | Route family? | Classification | Exact reason |
|---|---|---|---|---|---|---|---|
| 8/9 E1 large rows (v4) | ETH yes | **No** | PoolManager not indexed | long-tail | v4 hops | **NOT_DISCOVERABLE** | v4 PoolManager unsupported |
| TRUMP pure v2 (row 7, 68 cycles) | ETH yes | **No** | Uni v2 factory not in graph | TRUMP A/B missing | mint/redeem | **NOT_DISCOVERABLE** | Uni v2 factory absent; Sushi-only v2 quoter; bridge selectors unsupported |
| DEXTF index | ETH yes | **No** | index mint | DEXTF | vault-vs-pool | **NOT_DISCOVERABLE** | index mint not a quoter path |
| E1 `POTENTIALLY_FOUND` | mixed | partial | — | — | — | **11 / 247** only | fee/token/size still often wrong |
| ArbiCore SHADOW routes | 6 chains | UniV3/Aerodrome/etc. | blue-chip | registry | 2–4 hop DFS | discoverable | economics all negative |

**Do not say “scanner missed it.”** For U2/U3 winners the reason is concrete venue/route absence.

---

## Phase 6 — Timing / latency

| Stage | Measured / code fact |
|---|---|
| Discovery interval | 60 s default (**PROVEN**) |
| Verify batch | ≤32 / tick; ~2–3% of discoveries verified in certified window |
| Median discovery→verify | ~14 minutes (root-cause memo) |
| Quote state | `latest`, not N−1 |
| TRUMP opportunity lifetime | previous-block positive until same-block winner; auction in inclusion block |
| Flash logs at tx index 0 | 14 / 5,635 sample (**PROVEN**) |

For **theoretically discoverable** ArbiCore routes: timing is moot — stored gross already ≤ 0.

For TRUMP / v4 independent events: even if discovery were instant, observed winners kept ≤ $7.28 on ≥$25 pre-block cells → classify timing as **LATE** relative to the auction **and** capturable edge as **competition-erased**. Latency alone is not demonstrated as the primary failure mode for ≥$25 capturable profit.

Classification on capturable ≥$25 independent cells: **UNKNOWN / N/A** (none capturable). On pre-block gross cells: ArbiCore path would be **LATE** if it could see them.

---

## Phase 7 — Would Gate7 have accepted?

Gate7 reads `atomic_profit_usd` from `aggregate_economics` (flash fee, gas estimate, slippage, MEV penalty). Floor historically $25; dynamic mode may be $0 (**PROVEN**, `GATE7_DYNAMIC_PROFITABILITY_CHANGE_20261007.md`). Not modified in this audit.

| Independent event | Gate7 at production $10k | Gate7 at realized/optimal size, pre-builder | After observed builder | Label |
|---|---|---|---|---|
| TRUMP 7 cells | FAIL (quote −$1k+) | Would likely clear $25 on peak states | kept ≤ $7.28 | **GATE7_WOULD_FAIL_CORRECTLY** vs post-competition reality; size model wrong for pre-competition |
| Corrected v4 rows | FAIL | FAIL (sub-$1) | FAIL | **GATE7_WOULD_FAIL_CORRECTLY** |
| Migration 718 WETH | — | not arb | — | Cat 5 |
| ArbiCore 4,848 Gate7 denials | FAIL | gross already ≤0 | — | **GATE7_WOULD_FAIL_CORRECTLY** — not false negatives |

**No evidence that Gate7 systematically rejects independently reconstructed post-competition ≥$25 profits.** Those profits were **not observed**. Gate7 is **not** the binding viability failure.

---

## Phase 8 — Competition / capture

| Finding | Evidence | Class |
|---|---|---|
| Builder takes ≥$25 surplus | Tips/priority $30–$111 on TRUMP ≥$25 fills | **COMPETITION_ERASED** |
| Same-block residual | Later txs in block find $5 left | **COMPETITION_REDUCED** |
| Searcher kept ≥$25 | **0** closed cycles | — |
| Max kept | $14.33 (in-block created, not pre-block $25) | **SEARCHER_CAPTURED** only at sub-$25 |
| Concentration | Optimism Balancer recipient 540/695; Base/ETH many recipients | competition present |

Distinguish: **too slow** vs **no capturable edge** → observed timely winners still have **no ≥$25 capturable edge**.

---

## Phase 9 — Coverage matrix

| Chain | Venue | Opportunity events | Profitable after competition ≥$25 | ArbiCore covers? | Reason if not |
|---|---|---:|---:|---|---|
| Ethereum | Uniswap v4 PoolManager | 8/9 large + 45 flash∩v4 + 7,703 swaps/hr | **0** demonstrated | No | no v4 backend |
| Ethereum | Uniswap v2 factory | TRUMP 68+55; APE leg | **0** ≥$25 kept | No | Sushi-only v2 quoter |
| Ethereum | TRUMP mint/redeem bridge | 123 closed | **0** ≥$25 kept | No | custom selectors + tax |
| Ethereum | DEXTF index | 2 | 0 (≤$1) | No | index mint |
| Ethereum | Morpho Blue flash | majority of ETH flash tape | unknown USD | Catalog yes; certified mix often absent | provider mix |
| Base | UniV3 + Aerodrome (covered) | SHADOW quotes | 0 (gross ≤0) | Yes | economics |
| Base | PancakeSwap / v4 | market mix (Bitquery) | not measured here | No | registry gap |
| Arbitrum/OP/Poly/BNB | mixed flash | E1 247 mix | insufficient USD | partial | fee tiers 100/10000; tokens |

**v4 gap is real. v4 Gate7 alpha is not demonstrated.** Do not add v4 from this audit.

Repeatability: TRUMP repeated ~25 minutes / 32 blocks; auction outcome repeated (**PROVEN**). Not a scalable ≥$25 keep.

---

## Phase 10 — Four-way decision matrix

| Reality | ArbiCore sees it? | ArbiCore timely? | Conclusion |
|---|---|---|---|
| profitable after competition ≥$25 | — | — | **Not observed** in reconstructed independent set |
| profitable before competition, unprofitable after | no (TRUMP/v4) | would be late anyway | **economic/competition problem** (distinct mode) |
| unprofitable after real costs (covered universe) | yes | — | **economic opportunity problem** |
| apparent large profit (naive ERC-20) | no (v4) | — | accounting artifact, not alpha |

Primary supported letter classes A–E from briefing: **C** (with secondary coverage gaps that do not contain demonstrated capturable ≥$25 edge).

---

## Phase 11 — Business viability ratios

Definitions used:

- **N** = independent events with reconstructed economics in the deep set: **9** E1 large rows + **123** TRUMP closed cycles − **2** overlapping hashes (rows 2 & 7) ≈ **130**, plus **45** flash∩v4 for venue context (migration excluded from profit counts).
- **N_profitable** = before-builder surplus ≥ $25 after gas/fees/tax: **10** fills (8 forward + 2 reverse); **7** distinct pre-block states.
- **N_capturable** = searcher net ≥ $25 after builder/priority: **0**.
- **N_discoverable** among N_profitable: **0**.
- **N_timely** among capturable: **0** (vacuous).
- **N_gate7** that would pass on post-competition capturable ≥$25: **0**.

| Ratio | Value | Confidence |
|---|---|---|
| discovery coverage `N_discoverable / N_profitable` | **0 / 10 = 0%** | HIGH that discoverable=0; MEDIUM that n=10 is complete for the hour |
| timely capture `N_timely / N_profitable` | **not meaningful** (0 capturable) | — |
| Gate7 recognition of capturable | **n/a** (denominator 0) | — |
| capturable / pre-competition ≥$25 | **0 / 10 = 0%** | HIGH for this hour |

E1 census **247**: naive net≥$25 = 9; after E1.5/E1.6 correction capturable≥$25 = **0**.

ArbiCore own universe Gate7≥$0 rate: **0%** (4,848; 288; Hybrid).

---

## Phase 12 — Final decision

### Primary conclusion: **C. ECONOMIC / COMPETITION PROBLEM**

**Evidence:**

1. In ArbiCore’s covered blue-chip universe, every measured live quote has **non-positive gross**; Gate7 never rejected a positive quote (288 / 4,848 / Hybrid).
2. Independently, **real** previous-block gross opportunities ≥$25 existed (TRUMP), and **every** observed winner paid almost all surplus to the builder (kept ≤ $7.28).
3. Naive “large profits” on v4 flash rows were **ERC-20 accounting errors** (missing native ETH into PoolManager); corrected surpluses are pennies.
4. Coverage gaps (v4, Uni v2 factory, TRUMP bridge) are **PROVEN** but do **not** contain demonstrated post-competition ≥$25 capturable alpha — so this is **not** primary “A. discovery.”
5. Latency is real (60s poll vs same-block auction) but **timely winners still have no ≥$25 keep** — so this is **not** primary “B. latency.”
6. Gate7 does **not** false-negative post-competition ≥$25 events (none exist) — **not** “D.”

**Recommended next action (ONE, bounded):**  
**Do not optimize generic DEX atomic-arbitrage infrastructure (no v4/v2/bridge/workers/RPC/Hybrid/Gate7 changes).** Run one read-only public-data experiment: measure whether any **≥ $25 searcher-kept** atomic arb tail exists on Base/Arbitrum over a bounded window; if that tail is empty or fully auction-captured, permanently deprioritize this opportunity class and research a **different** edge (non-generic atomic DEX arb).

---

## EXECUTIVE CONCLUSION CARD

```
EXECUTIVE CONCLUSION: C

INDEPENDENT EVENTS: 247 (E1 flash ATOMIC_ARB census); deep economics on ~130 TRUMP+E1.5 rows (+45 flash∩v4 context)

GENUINELY PROFITABLE: 10 fills / 7 states with before-builder ≥ $25 (TRUMP); 0 after full cost correction on pure v4

PROFITABLE AFTER COMPETITION: 0 (≥ $25 kept)

DISCOVERABLE BY CURRENT ARBiCORE: 0 (of those ≥ $25 pre-competition cells)

TIMELY: 0 capturable; path would be LATE if discoverable

GATE7 WOULD ACCEPT: 0 of post-competition ≥ $25 (none exist); correctly fails covered-universe negatives

DISCOVERY COVERAGE: 0% (0/10 pre-competition ≥ $25 cells)

TIMELY CAPTURE: n/a (0 capturable)

GATE7 RECOGNITION: n/a for capturable ≥ $25; 0% ≥ $0 on ArbiCore verified Gate7 corpus

MAIN FAILURE MODE: economics / competition (apparent edge erased by costs + builder auction; covered universe has no gross edge)

TOP EVIDENCE:
1. E1 flash_arbs=247; naive net≥$25=9; 8/9 touch v4 PoolManager; in-universe recall 0/9 then 11/247 POTENTIALLY_FOUND only
2. E1.5 replay 9/9: large WETH residuals omit native ETH; corrected v4 Gate7-scale profit = 0
3. E1.6: 68+55 TRUMP closed cycles; mint ratio 0.9801; 7 pre-block ≥$25 states; kept ≤ $7.28 after tip
4. ArbiCore SHADOW/funnel/Hybrid: Gate7 ≥ $0 count = 0 (best ~−$60); pre-verify P&L absent → priority/ML/hard-filter NO-GO
5. Production $10k size quotes TRUMP states at −$1k+; auction + wrong size + missing venues compound

COVERAGE GAPS: Ethereum Uniswap v4 PoolManager; Uniswap v2 factory (Sushi-only quoter); TRUMP mint/redeem bridge; DEXTF index; fee tiers 100/10000 off-Base; Morpho often absent from certified mix

COMPETITION FINDINGS: COMPETITION_ERASED on all reconstructed ≥ $25 previous-block cells; builders/priority fees extract nearly all surplus

GATE7 FINDINGS: Correctly rejects covered negative quotes; not a false-negative factory for capturable ≥ $25 independent events; dynamic $0 floor does not create edge

BUSINESS VIABILITY: NO-GO

RECOMMENDED NEXT ACTION: One bounded read-only census of searcher-kept ≥ $25 atomic arb on Base/Arbitrum; if empty/auction-captured, abandon generic DEX arb optimization and research a different opportunity class — no venue/Gate7/RPC/Hybrid/scanner work from this gate

PRODUCTION CHANGES: 0
DEPLOYMENTS: 0
LIVE TRANSACTIONS: 0
```

---

## STRICT STOP

Audit complete. No fixes implemented. No venues added. No v4 support. No scanner/Gate7/RPC/Hybrid E changes. No deploy. No LIVE.
