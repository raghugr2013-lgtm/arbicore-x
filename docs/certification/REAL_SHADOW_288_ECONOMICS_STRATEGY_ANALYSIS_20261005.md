# Real SHADOW — 288 Gate-7 economics and strategy evidence (2026-10-05)

**READ-ONLY.** No source, MongoDB, configuration, scanner, SHADOW, deploy, Docker, RPC, threshold, commit, or push change. Analysis uses stored `arbicore_discovery_candidates` and `evidence_bundles` only.

**Certification run:** `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065`  
**Cert record:** `arbicore_shadow_certifications`, `started_at=2026-10-05T05:27:48.513927+00:00`, `completed_at=2026-10-05T05:58:04.231514+00:00`, status `ABORTED`  
**Scanner:** `flash_loan_arb` (certified worker `flash_loan_arb:0eb9228c` on bundled rows)

**Overall classification:** **REAL_SHADOW_ECONOMICS_PARTIAL**

Decision-net dollars are stored on all **288** Gate-7 rows via `verified_outcome`. Full m2.3 economics components are stored on **180** rows (certified verifier bundles). **108** rows have Gate-7 decision text and discovery route hints only—no certified bundle—so component economics and failure attribution stay partial for those rows.

---

## Population proof

### Exact query / window

| Field | Value |
|---|---|
| Database | `arbicore_x` |
| Collection | `arbicore_discovery_candidates` |
| `verified_at` | `>= 1791178068.514` (`2026-10-05T05:27:48.514+00:00`) **and** `< 1791179884.232` (`2026-10-05T05:58:04.232+00:00`) |
| `verified_outcome` | regex `gate_7:atomic_profit` |
| Certification run ID | `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065` (time bounds match cert `started_at` / `completed_at`; candidates are not keyed by run id in Mongo) |

Observed `verified_at` span inside the filter: **1791178175.395** … **1791179880.972** (`2026-10-05T05:29:35Z` … `2026-10-05T05:58:00Z`).

### Counts

| Check | Result |
|---|---|
| Gate-7 rows | **288** |
| Distinct `candidate_id` | **288** |
| Rows from outside this window | **0** in the result set |
| Other Gate-7 rows in Mongo (any time) | **523,935** outside `[START, END)` — **not included** |
| Joined `evidence_bundles` (`flash_loan_arb_verifier`) | **180** (all worker `flash_loan_arb:0eb9228c`) |
| No bundle | **108** |

### Chain counts (288)

| Chain | n |
|---|---:|
| Ethereum | 45 |
| Arbitrum | 54 |
| Base | 54 |
| Optimism | 45 |
| Polygon | 45 |
| BNB | 45 |

### Provider counts (288, from `hint_metric.provider` / `subject_id`)

| Provider | n |
|---|---:|
| `aave_v3` | 134 |
| `balancer_v2` | 82 |
| `uniswap_v3` | 72 |
| Morpho Blue | **0** |
| Other | **0** |

---

## Gate-7 formula (reference only — not used to fill gaps)

Same as Phase 0 / m2.3 documentation: `FlashLoanGate7AtomicProfit` compares stored `atomic_profit_usd` to `min_atomic_profit_usd` (default **$25.00**). Outcome text: `denied:gate_rejection:gate_7:atomic_profit $<amount> < floor $25.00`.

Assessor path (`aggregate_economics`, `gross_is_quote_inclusive=True`) computes spread, flash fee, swap fees, gas drag, slippage, MEV penalty, then `atomic_profit_usd`. The **cent-rounded amount in `verified_outcome`** is the Gate-7 decision net. Missing bundle fields are **not** recomputed here.

---

## 1. Economics (288 rows)

### All 288 — always stored

| Field | Availability |
|---|---|
| **decision atomic_profit_usd** (Gate-7 decision net) | **STORED** on all 288 (`verified_outcome` parse) |
| **Gate-7 threshold** | **STORED** — **$25.00** on all 288 |
| **Gate-7 rejection** | **STORED** — all `FAIL` / denied via outcome text |
| **Gate-7 result** | deny all 288 |

### Certified bundles only (n = 180)

Read via Phase 0 `observe_strategy_intelligence` → `economics.fields` (no recomputation).

| Field | Stored count / status |
|---|---|
| gross spread % (`economics.gross_spread_pct` / `quotes.gross_profit_pct`) | **180 / 288** STORED |
| gross profit $ | **NOT STORED / UNAVAILABLE** on m2.3 bundle (0 / 288) |
| flash-loan fee $ (`fees.flash_loan_fee_usd`) | **180 / 288** STORED |
| flash-loan fee bps (applied rate) | **NOT STORED / UNAVAILABLE** (`AVAILABLE_NOT_PERSISTED` on assessor output) |
| flash-loan fee bps raw (`fees.flash_loan_fee_bps`, override coerced `or 0`) | **180 / 288** STORED where bundle exists (often **0** on bundle—not catalog rate) |
| DEX/swap fee % (`fees.total_swap_fee_pct`) | **180 / 288** STORED |
| DEX/swap fee $ | **NOT STORED / UNAVAILABLE** (0 / 288) |
| gas $ (`gas.gas_cost_usd`) | **180 / 288** STORED |
| gas units (`gas.tx_gas_units`) | **146 / 288** STORED (34 bundles missing units) |
| slippage % (`fees.total_slippage_pct`) | **180 / 288** STORED (all **0.0** on stored rows) |
| slippage $ | **NOT STORED / UNAVAILABLE** |
| MEV risk (`mev.level` / label on bundle) | **180 / 288** STORED where bundle exists |
| MEV penalty % / $ | **NOT STORED / UNAVAILABLE** (`AVAILABLE_NOT_PERSISTED`) |
| true net $ (`economics.atomic_profit_usd` / `expected_net_after_costs_usd`) | **180 / 288** STORED; matches decision net within **$0.005** on bundled rows |
| true net % | **NOT STORED / UNAVAILABLE** |
| `atomic_profit_usd` (stored assessor output) | **180 / 288** STORED |

### No certified bundle (n = 108)

All component fields above: **NOT STORED / UNAVAILABLE** except **decision net** and **Gate-7 floor** from `verified_outcome`. Route token path may exist on `hint_metric` for strategy classification only.

### Stored component snapshot (180 certified bundles only)

| Component | mean | min | max |
|---|---:|---:|---:|
| gross spread % | **-0.278** | -1.709 | -0.091 |
| flash-loan fee $ | **8.47** | 0.0 | 30.0 |
| DEX/swap fee % | **0.0** | 0.0 | 0.0 |
| gas $ | **2.47** | 0.05 | 13.37 |
| slippage % | **0.0** | 0.0 | 0.0 |

Stored gross spread is **≤ 0 on all 180** bundled evaluations (no positive raw spread in persisted assessor output).

---

## 2. Profitability distribution (288 decision nets)

Source: parsed **`verified_outcome`** only (stored Gate-7 decision net).

| Metric | Value (USD) |
|---|---:|
| Best (closest to passing) | **-59.31** |
| Worst | **-1,709.90** |
| Mean | **-345.32** |
| Median | **-238.02** |
| P25 | **-348.66** |
| P75 | **-159.98** |
| P90 | **-133.12** |
| Total sum | **-99,452.54** |
| Average distance to $25 floor (`25 − net`) | **370.32** |

| Bucket | Count |
|---|---:|
| ≥ $0 | 0 |
| > $0 | 0 |
| ≥ $25 | 0 |
| $0 to $25 | 0 |
| -$25 to $0 | 0 |
| -$50 to -$25 | 0 |
| -$100 to -$50 | 15 |
| < -$100 | 273 |

**Closest to passing Gate 7:** `candidate_id=31df13631b18c7175c30`, **Base**, **balancer_v2**, decision net **-$59.31**, distance **$84.31** below floor.

**October 4 comparison (256-row window, read-only):** that window had the same **$25** floor and **0** passes; mean decision net **≈ -$316** vs **-$345** here—structurally similar, not analysed further.

---

## 3. Chain economics (decision net, 288)

No chain has stored economics supporting profitability (all nets negative, 0 ≥ $25).

| Chain | n | Mean | Median | Best | Worst | ≥ $0 | ≥ $25 | Providers (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Ethereum | 45 | -348.47 | -175.06 | -103.04 | -1068.05 | 0 | 0 | aave 17, bal 16, uni 12 |
| Arbitrum | 54 | -191.63 | -174.56 | -70.37 | -419.73 | 0 | 0 | 18 each |
| Base | 54 | -198.63 | -168.19 | **-59.31** | -394.89 | 0 | 0 | aave 20, bal 16, uni 18 |
| Optimism | 45 | -614.82 | -318.32 | -192.19 | -1709.90 | 0 | 0 | aave 17, bal 16, uni 12 |
| Polygon | 45 | -510.22 | -441.15 | -156.50 | -1483.17 | 0 | 0 | aave 17, bal 16, uni 12 |
| BNB | 45 | -268.23 | -297.39 | -146.87 | -439.68 | 0 | 0 | aave 45 |

BNB Gate-7 rows have **no** certified m2.3 bundle in this window (108 no-bundle set includes all 45 BNB rows).

---

## 4. Provider economics (decision net, 288)

| Provider | n | Mean | Median | Best | Worst | ≥ $0 | ≥ $25 | Stored flash fee notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Aave V3 | 134 | -325.50 | -238.65 | -64.29 | -1684.12 | 0 | 0 | On **66** bundled rows: `fees.flash_loan_fee_bps=0` stored; fee **$** stored where bundle exists (typically **$5** at $10k notional when bps override absent) |
| Balancer V2 | 82 | -347.64 | -222.61 | **-59.31** | -1679.12 | 0 | 0 | **59** bundled rows: stored bps **0**; fee **$0** stored |
| Uniswap V3 | 72 | -379.57 | -251.09 | -89.29 | -1709.90 | 0 | 0 | **55** bundled rows: stored bps **0**; fee **$** often **$30** when stored |

Applied catalog bps (5 / 0 / 30) are **NOT STORED** on the bundle; only override-or-zero bps and assessor **$** fee are stored.

---

## 5. Strategy evidence (288)

**Classifier:** `phase0.strategy_intelligence.v1` (`observe_strategy_intelligence`), route evidence from stored bundle + `hint_metric` (bundle wins). **No row mutated.**

**Classification state:** `COMPLETE` **288 / 288**  
**Strategy completeness:** `FULLY_CLASSIFIED` **288 / 288**  
**Confidence:** `MEDIUM` 137, `HIGH` 43 (bundled rows with full hop-leg protocol alignment)

### Primary family (exactly one per row — proven)

| User-facing label | Primary (`primary_family`) count | Evidence rule (summary) | Completeness |
|---|---:|---|---|
| **TRIANGULAR** | **92** | Closed cycle, 3 distinct tokens, cross-protocol not proven as primary | COMPLETE |
| **TRIANGULAR** (+ cross-protocol shape) | **83** | `COMPLEX_TRIANGULAR_CROSS_PROTOCOL`: closed 3-token path, hop_count > 3, distinct per-leg protocols | COMPLETE |
| **CROSS-POOL** | **27** | hop_count=2, closed 2-token path, ≥2 distinct pool ids, protocols not treated as cross-protocol primary | COMPLETE |
| **DEX→DEX** | **17** | `DEX_TO_DEX`: hop_count=2, closed 2-token, distinct pools **and** distinct per-leg protocols | COMPLETE |
| **MULTI-DEX** | **34** | hop_count≥3, not 3-token cycle, distinct per-leg protocols | COMPLETE |
| **MULTI-HOP** | **27** | `MULTI_HOP`: hop_count≥4, not 3-token cycle, protocols not distinct | COMPLETE |
| **CROSS-PROTOCOL** | **8** | Distinct protocols on every hop; more specific rules did not apply | COMPLETE |
| **STABLECOIN** | **0** | No primary `STABLECOIN_CROSS_PROTOCOL` | — |
| **LST/LRT** | **0** | No primary `LST_LRT_CROSS_PROTOCOL` | — |

**Note:** **83** complex triangular rows are counted under **TRIANGULAR** shape with **CROSS-PROTOCOL** proven via explicit per-leg protocols (primary label `COMPLEX_TRIANGULAR_CROSS_PROTOCOL`).

### Secondary tags (additional proven predicates — not exclusive)

| Tag | Rows tagged |
|---|---:|
| `CROSS_POOL` | 288 |
| `CROSS_PROTOCOL` | 142 |
| `TRIANGULAR` | 91 |
| `MULTI_HOP` | 34 |

Secondary tags are assigned only when `classification_state=COMPLETE` and the predicate is true on **stored** pool/protocol fields (Phase 0 taxonomy). They do not replace primary family.

**STABLECOIN / LST/LRT:** not proven as primary or secondary on any of the 288 (no all-stable path; no LST/LRT symbol on stored path under classifier rules).

---

## 6. Raw route shapes (288, separate from family labels)

From stored `cycle_token_path` (bundle or `hint_metric`):

| Shape | Count |
|---|---:|
| `A→B→C→B→A` (4 hops, 3 tokens) | 122 |
| `A→B→C→A` (3 hops) | 61 |
| `A→B→A` (2 hops) | 44 |
| Other closed 4-hop / 4-token | 61 |

These are **shape labels only**, not strategy-family assignments.

---

## 7. Economics × strategy (decision net USD)

Only families with **primary** proof above (complex triangular counted under **TRIANGULAR + CROSS-PROTOCOL** for economics split):

| Proven primary family | n | Mean net | Median | Best | Worst | ≥ $0 | ≥ $25 |
|---|---:|---:|---:|---:|---:|---:|---:|
| TRIANGULAR (primary `TRIANGULAR` only) | 92 | -411.0 | -238.7 | -70.37 | -1709.90 | 0 | 0 |
| COMPLEX_TRIANGULAR + CROSS-PROTOCOL | 83 | -410.5 | -251.1 | -103.04 | -1483.17 | 0 | 0 |
| DEX→DEX | 17 | -95.0 | -64.3 | -59.31 | -152.5 | 0 | 0 |
| CROSS-POOL (primary) | 27 | -312.4 | -238.0 | -114.8 | -1068.05 | 0 | 0 |
| MULTI-DEX | 34 | -352.8 | -297.4 | -153.9 | -976.9 | 0 | 0 |
| MULTI-HOP | 27 | -283.8 | -238.7 | -114.8 | -818.6 | 0 | 0 |
| CROSS-PROTOCOL (primary) | 8 | -401.2 | -395.3 | -161.7 | -746.9 | 0 | 0 |
| STABLECOIN | UNAVAILABLE — insufficient stored evidence | | | | | | |
| LST/LRT | UNAVAILABLE — insufficient stored evidence | | | | | | |

**Best economics among proven DEX→DEX:** **-$59.31** (Base, Balancer V2).

---

## 8. Near-pass analysis — top 20 (decision net)

Distance = **$25.00 − net** (all still fail Gate 7).

| # | candidate_id | Chain | Provider | Primary family | Shape | Gross % | Flash $ | Gas $ | Slip % | MEV | Net $ | Dist to $25 |
|---:|---|---|---|---|---|---:|---:|---:|---:|---|---:|---:|
| 1 | `31df13631b18c7175c30` | base | balancer_v2 | DEX→DEX | A→B→A | -0.091 | 0.0 | 0.18 | 0 | MEDIUM | -59.31 | 84.31 |
| 2 | `c5e085b8a929d2fc8e22` | base | balancer_v2 | DEX→DEX | A→B→A | -0.092 | 0.0 | 0.18 | 0 | MEDIUM | -59.42 | 84.42 |
| 3 | `05ff2878f26a9c378d7b` | base | aave_v3 | DEX→DEX | A→B→A | -0.091 | 5.0 | 0.18 | 0 | MEDIUM | -64.29 | 89.29 |
| 4 | `0fa1f5122a2dca2f936e` | base | aave_v3 | DEX→DEX | A→B→A | -0.091 | 5.0 | 0.18 | 0 | MEDIUM | -64.31 | 89.31 |
| 5 | `6bd9090183b8f4f6e652` | base | aave_v3 | DEX→DEX | A→B→A | -0.092 | 5.0 | 0.18 | 0 | MEDIUM | -64.42 | 89.42 |
| 6 | `182073b1b8b26be11548` | base | balancer_v2 | DEX→DEX | A→B→A | -0.152 | 0.0 | 0.18 | 0 | MEDIUM | -65.43 | 90.43 |
| 7 | `7da7b02af6824ef30da4` | base | aave_v3 | DEX→DEX | A→B→A | -0.116 | 5.0 | 0.18 | 0 | MEDIUM | -66.75 | 91.75 |
| 8 | `aca9e16d661b7c5ead5f` | arbitrum | balancer_v2 | TRIANGULAR | A→B→C→A | -0.200 | 0.0 | 0.38 | 0 | MEDIUM | -70.37 | 95.37 |
| 9 | `4e298d34ffc3125fd2dc` | base | aave_v3 | DEX→DEX | A→B→A | -0.154 | 5.0 | 0.18 | 0 | MEDIUM | -70.61 | 95.61 |
| 10 | `aa840b3648dd3573867c` | arbitrum | aave_v3 | TRIANGULAR | A→B→C→A | -0.190 | 5.0 | 0.42 | 0 | MEDIUM | -74.40 | 99.40 |
| 11–15 | (base uni/bal DEX→DEX) | base | uni/bal | DEX→DEX | A→B→A | ≈ -0.09 to -0.15 | 0–30 | ≈ 0.18 | 0 | MEDIUM | -89 to -95 | 114–120 |
| 16 | `a9df9e9e8b990933d098` | arbitrum | uniswap_v3 | TRIANGULAR | A→B→C→A | -0.200 | 30.0 | 0.38 | 0 | MEDIUM | -100.37 | 125.37 |
| 17 | `d293d0e245726e544af4` | ethereum | balancer_v2 | COMPLEX_TRIANGULAR | A→B→C→B→A | -0.403 | 0.0 | 12.75 | 0 | MEDIUM | -103.04 | 128.04 |
| 18 | `e219ea6b899bd89f62b8` | ethereum | aave_v3 | COMPLEX_TRIANGULAR | A→B→C→B→A | -0.403 | 5.0 | 12.75 | 0 | MEDIUM | -108.04 | 133.04 |
| 19 | `a6c6d472203dc3908426` | base | balancer_v2 | DEX→DEX | A→B→A | -0.616 | 0.0 | 0.15 | 0 | MEDIUM | -111.74 | 136.74 |
| 20 | `dd464734481f0186d9b3` | ethereum | balancer_v2 | MULTI_HOP | 4tok/4hop | -0.514 | 0.0 | 13.37 | 0 | MEDIUM | -114.82 | 139.82 |

**Reading:** Top ranks are **Base DEX→DEX** and **low-negative gross spread** (≈ -0.09% to -0.15%) with small gas on L2; none have positive stored gross. Ethereum near-miss rows carry **large gas $** (~$13). **Slippage** stored as **0** on all listed bundled rows. **MEV** label **MEDIUM** on stored bundles; penalty **NOT STORED**.

Market read for near-pass set: **(A) structurally unprofitable** on stored quotes (gross ≤ 0) and **(C) weak / negative raw spreads**; **(B) fee/gas** matter on L1 (Ethereum) but are not the sole issue on Base; **(D) slippage** not evidenced as a drag in stored fields; **(E) 108 rows** lack bundle-level quote economics entirely.

---

## 9. Failure attribution (288)

Where stored evidence allows:

| Attribution | Count | Basis |
|---|---:|---|
| **gross_spread_insufficient** | **180** | Certified bundle: stored `gross_profit_pct` ≤ 0 |
| **insufficient_stored_economics** | **108** | No certified m2.3 bundle—cannot read gross, fees, gas, slippage from persistence |
| flash-loan / DEX / gas / slippage / MEV **drag** (standalone) | **0** | No bundled row has **positive** stored gross with negative net |
| **combination** | **0** | Not assigned without positive gross |

All 288 failures are Gate-7 **atomic profit below $25** with **negative** decision net. Dominant interpretable cause on bundled rows: **negative or zero stored gross spread** after live quote (quote-inclusive path), not a separate slippage line item in storage.

---

## 10. Final certification assessment

| Item | Status |
|---|---|
| **A. Pipeline status** | **PASS (observation)** — 10 scanner iterations, 288 Gate-7 evaluations, six chains, 0 emit/sign/broadcast in window |
| **B. Economic evidence status** | **PARTIAL** — decision net on 288; component breakdown on 180 only |
| **C. Strategy evidence status** | **STRONG** — Phase 0 classifier `COMPLETE` on 288 from stored paths/protocols |
| **D. Provider evidence status** | **PASS** — Aave / Balancer / Uni only; counts and stored fees as above |
| **E. Six-chain evidence status** | **PASS** — all six chains present at Gate 7 |
| **F. Profitability status** | **FAIL** — 0 ≥ $0, 0 ≥ $25; sum **-$99,452.54** |
| **G. Closest real opportunity** | Base Balancer V2 DEX→DEX **-$59.31** (`31df13631b18c7175c30`), **$84.31** below floor |
| **H. Best-proven strategy family (economics)** | **DEX→DEX** (primary) — best net **-$59.31** |
| **I. Still unproven** | Positive net at any threshold; MEV penalty dollars; applied flash bps; gross/swap/slippage **$**; full economics on **108** rows (incl. all BNB Gate-7); Morpho / other providers |
| **J. Recommended next step** | **Read-only extended SHADOW or targeted Base DEX→DEX observation** with bundle capture on BNB/Polygon gaps—**only after operator approval**; do **not** lower Gate-7 floor or enable execution from this evidence |

### Profitability verdict (A–E options from near-pass section)

**Primary:** **A — structurally unprofitable on stored live-quote economics** (non-positive gross spread on all 180 bundled evaluations).  
**Secondary:** **C — weak/negative raw spreads** dominate; **B — gas/fee drag** visible on L1 near-misses but not required to explain Base leaders.

---

**Queried at (UTC):** 2026-10-05 (read-only, container `arbicore-x-backend-new`)

REAL_SHADOW_288_ECONOMICS_ANALYSIS_COMPLETE
