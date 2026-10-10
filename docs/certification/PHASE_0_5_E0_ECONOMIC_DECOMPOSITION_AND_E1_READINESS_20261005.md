# Phase 0.5 — E0 economic decomposition and E1 readiness

**Date:** 2026-10-05

**Mode:** read-only. No source edit, configuration edit, scanner change, RPC change, Network Config change, Gate 7 change, deploy, restart, signing, broadcast, strategy activation, or production database write.

**Certification run:** `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065`

**E0 result:** **E0_PARTIAL**

**E1 readiness:** **PARTIAL**

PASS in this document means the negative economic evidence is internally trustworthy. It does not mean the search was profitable. No family in this window has a positive stored gross or a Gate 7 pass.

---

## 1. Executive summary

The 180 complete m2.3 bundles are an internally consistent negative sample at a quoted size of **$10,000**. Every stored gross is negative. The hop-amount chain matches the stored gross on every bundle. The stored atomic profit matches the assessor formula, including a **$50.00** model haircut, within **$0.00005** on every bundle.

That consistency does not make every family a clean fee-floor control. Pool-fee telemetry on the 180 bundles is **0.10% to 1.05%**. Fifteen bundles have stored gross below **−10%**, and ten more sit between **−10%** and **−5%**. On the worst rows the excess over the compounded fee floor is located on the shallowest hops. Those hops are a few percent of stored `depth_usd`. Separate price-impact, reserves, and ticks are not stored, so the split between trade size and route choice stays partial.

`MULTI_DEX` has **0** complete bundles. All **34** rows are inside the **108** Gate 7 outcomes that never received an `evidence_bundles` document. Gross for that family is **NOT_PROVABLE**.

Historical block headers, receipts, logs, and `eth_call` at about a 14-day lookback succeed on the already-configured Alchemy hosts. `debug_*` and `trace_*` are rejected as unavailable on the current Free tier, including the Base URL named `ARBICORE_ARCHIVE_RPC_URL`. A full internal-call census is not available on the production endpoints. This document does not attach any new endpoint and does not run the census.

**Next gate:** `E1_REALIZED_ARBITRAGE_CENSUS_READ_ONLY` — not started, not authorized by this note.

---

## 2. Exact files and data inspected

| Source | What was read |
|---|---|
| `arbicore_x.arbicore_discovery_candidates` | 288 rows with `verified_at` in `[1791178068.514, 1791179884.232)` and `verified_outcome` matching `gate_7:atomic_profit` |
| `arbicore_x.evidence_bundles` | 180 documents, `source_component=flash_loan_arb_verifier`, `diagnostics.worker_id=flash_loan_arb:0eb9228c`, `created_at` in the certification window. A second query found **0** bundles, any component and any time, for the other 108 `candidate_id`s |
| `arbicore_x.evidence_bundles` indexes | Unique index on `bundle_id`. No validator. No TTL |
| `arbicore_x.arbicore_config` `_id=network` | Key names and RPC hostnames only. URL paths and credentials were not copied into this note |
| Certified image `phase0-823a79b`, in memory | `observe_strategy_intelligence` (`phase0.strategy_intelligence.v1`) applied to each of the 288 rows. No document was written |
| Worktree economics path | `app/backend/arbicore/scanners/economics.py`, `flash_loan_arbitrage/economics.py`, `verifier.py`, `live_quote_provider.py`, `data/mongo/evidence_bundles_repo.py` |
| Prior notes | `SHADOW_30MIN_REAL_FLASH_LOAN_20261005.md`, `REAL_SHADOW_288_ECONOMICS_STRATEGY_ANALYSIS_20261005.md`, `REAL_SHADOW_288_STRATEGY_ECONOMICS_RANKING_20261005.md`, `PHASE_0_5_OPPORTUNITY_LEDGER_ARCHITECTURE_AUDIT_20261005.md` |
| Container environment names | `ARBICORE_RPC_URL`, `ARBICORE_RPC_URL_{ETHEREUM,ARBITRUM,BASE,OPTIMISM,POLYGON,BNB}`, `ARBICORE_ARCHIVE_RPC_URL`. Values were used only for a capability probe and were not printed |
| Backend logs, `2026-10-05T05:27:00Z`–`06:05:00Z` | 29,555 lines on `arbicore-x-backend-new`. No `DuplicateKey`, `E11000`, or traceback line in that slice |
| Historical RPC probe | One read-only lookback of about 14 days on the existing hosts: block header, balance, `eth_call`, a two-block `eth_getLogs`, a receipt, and trace methods. No scanner, config, or production process was pointed at a new URL |

Family counts from the observer match the ranking note: `TRIANGULAR` 92, `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` 83, `MULTI_DEX` 34, `MULTI_HOP` 27, `CROSS_POOL` 27, `DEX_TO_DEX` 17, `CROSS_PROTOCOL` 8.

The component snapshot in `REAL_SHADOW_288_ECONOMICS_STRATEGY_ANALYSIS_20261005.md` reports gross spread mean **−0.278%**, minimum **−1.709%**, maximum **−0.091%**. A direct read of `economics.gross_spread_pct` on these 180 bundles has the same maximum (**−0.091142%**) and a wider body: minimum **−16.27286%**, mean **−2.80209%**, median **−1.29421%**. This note uses that direct read.

---

## 3. 180-bundle decomposition

### Population

| Item | Value |
|---|---|
| Complete bundles | **180 / 180** `schema_version=m2.3`, worker `flash_loan_arb:0eb9228c` |
| `quotes.route_quote_status` | `ok` on 180 |
| `quotes.exact_size` / `size_basis` | `true` / `exact` on 180 |
| `economics.borrow_amount_usd` and `quotes.quote_notional_usd` | **10000.0** on 180 |
| `mev.level` | `MEDIUM` on 180 |
| Positive stored gross | **0** |
| Stored gross ≥ 0 | **0** |
| Gate 7 | `FAIL` on 180. Floor text **$25.00** |

### Field status (all 180)

| # | Requested field | Status | Where it lives |
|---|---|---|---|
| 1 | Stored gross | **STORED as percent.** `economics.gross_spread_pct` and `quotes.gross_profit_pct` agree within **4.9e-7** percentage points. Dollar gross is **NOT_STORED**. `gross_usd` below is **DERIVED** as `notional × gross_pct / 100` | Bundle economics and quotes |
| 2 | Flash-loan fee | **STORED as dollars.** Applied bps are **AVAILABLE_NOT_PERSISTED**. `fees.flash_loan_fee_bps` is **0** on all 180 and is the quote-override coercion, not the catalog rate | `fees.flash_loan_fee_usd` |
| 3 | DEX / protocol fees | **STORED as telemetry percent** `fees.total_swap_fee_pct`. Dollar DEX fee is **NOT_STORED**. On the live path `gross_is_quote_inclusive=True`, so this percent is already inside the quote and is not deducted again | `fees.total_swap_fee_pct`, per-hop `fee_bps` |
| 4 | Price impact / slippage | Slippage percent is **STORED and is 0.0** on all 180. That zero means the live path did not add a separate slippage term. A separate price-impact figure is **NOT_STORED** | `fees.total_slippage_pct` |
| 5 | Gas | **STORED as dollars.** Units stored on **146**. Units **NOT_AVAILABLE** on **34**. Gas price is **NOT_STORED** | `gas.gas_cost_usd`, `gas.tx_gas_units` |
| 6 | L2 data fee | **NOT_AVAILABLE.** No L1-calldata or L2-data field exists on the bundle | — |
| 7 | Other known economic cost | MEV penalty percent is **AVAILABLE_NOT_PERSISTED**. The dollar haircut below is **DERIVED_MODEL_HAIRCUT** from the identity in this section. It is a `MEDIUM → 0.5` percentage-point model term, not an observed builder payment | `mev.level` stored; penalty not copied |
| 8 | Residual price dislocation | **DERIVED.** `gross_spread_pct − compounded_fee_floor_pct`. The floor is `100 × (Π(1 − fee_bps/10000) − 1)` from stored per-hop `fee_bps`. It is the first-order closed-cycle fee floor. It is not a measured impact | Derived from stored gross and stored `fee_bps` |
| 9 | Breakeven gross | **DERIVED** from the identity. The gross percent that makes atomic profit zero, and the gross percent that makes it **$25** | Derived |
| 10 | Cause class | Assigned from stored residual, hop-amount consistency, and stored depth. Impact itself remains **NOT_STORED** | This note |

### Stored distributions (n = 180)

| Component | min | p25 | median | mean | p75 | max |
|---|---:|---:|---:|---:|---:|---:|
| Gross % | −16.27286 | −2.37308 | −1.29421 | −2.80209 | −0.83709 | −0.09114 |
| Derived gross $ | −1,627.29 | −237.31 | −129.42 | −280.21 | −83.71 | −9.11 |
| Flash-loan fee $ | 0.00 | 0.00 | 5.00 | 11.00 | 30.00 | 30.00 |
| DEX fee telemetry % | 0.10 | 0.40 | 0.65 | 0.590 | 0.70 | 1.05 |
| Slippage % | 0 | 0 | 0 | 0 | 0 | 0 |
| Gas $ | 0.050 | 0.353 | 0.509 | 3.160 | 3.963 | 14.909 |
| Atomic profit $ | −1,709.904 | −298.446 | −195.491 | −344.370 | −147.411 | −59.313 |

Flash-loan fee dollars match the catalog at a $10,000 notional on every row: Aave V3 **$5.00** (66), Balancer V2 **$0.00** (59), Uniswap V3 **$30.00** (55).

Gross percent buckets:

| Bucket | Bundles |
|---|---:|
| [−0.3, 0) | 16 |
| [−0.6, −0.3) | 6 |
| [−1, −0.6) | 45 |
| [−2, −1) | 66 |
| [−5, −2) | 22 |
| [−10, −5) | 10 |
| < −10 | 15 |

The 25 rows at or below −5% are Ethereum 10, Optimism 12, Polygon 3.

### Identity (all 180)

The live assessor stores quote-inclusive gross, adds the flash-loan premium as a fee percent, adds gas as gas drag, adds the MEV factor for the stored level, and does not deduct pool fees a second time. With `MEV.MEDIUM = 0.5` percentage points:

`atomic = notional / 100 × (gross_pct − slippage_pct − flash_fee_usd/notional×100 − gas_usd/notional×100 − 0.5)`

The predicted atomic profit minus the stored `economics.atomic_profit_usd` is between **−$0.000049** and **+$0.000048** on all 180. Removing the 0.5 point leaves a residual of **+$50.00** within **$0.00005**. The decision-text cents and the stored atomic profit differ by at most **$0.00495**.

Where `tx_gas_units` is present (146), `gas_cost_usd` equals the code default for that chain times `units / 250000`, with zero mismatches. The defaults are Ethereum $8.00, BNB $0.40, Arbitrum $0.30, Base $0.15, Optimism $0.15, Polygon $0.05, before that scale. Where units are absent (34: Ethereum 21, Arbitrum 6, Polygon 4, Base 3), `gas_cost_usd` equals the unscaled chain default on all 34. That gas figure is a static estimate. It does not itemize an L2 data fee.

### Breakeven gross (derived, n = 180)

Zero-profit gross percent = slippage + flash percent + gas percent + 0.50.

| | min | median | max |
|---|---:|---:|---:|
| Breakeven gross for $0 atomic | 0.501% | 0.575% | 0.949% |
| Stored gross − that breakeven | — | about −1.97 percentage points | — |

**0** stored gross values reach the zero-profit breakeven. The $25 floor is a further **0.25** percentage points of gross on a $10,000 notional. The best stored gross is **−0.091%**, so the gap to a zero atomic profit remains about **0.59** percentage points on that row, of which **0.50** is the model haircut and about **0.09** is the quote itself.

### Quote consistency (all 180)

| Check | Result |
|---|---|
| Last-hop `amount_out_wei` versus first-hop `amount_in_wei`, converted with the same wei ratio the quoter uses | Matches `quotes.gross_profit_pct` with maximum absolute delta **0** |
| Hop `amount_out_wei` equals the next hop `amount_in_wei` | **0** breaks |
| Distinct `block_number` inside one route | **65 / 180**. Span maximum **14** blocks, median **0** |
| `liquidity.min_pool_tvl_usd_in_route` | **0.0** on all 180 |
| Per-hop `depth_usd` | **> 0** on every hop. Minimum hop depth across bundles: **$113,932.68** to **$41,051,287.75**, median of those minima **$367,656.92** |
| Quoted notional / minimum hop depth | **0.024%** to **8.78%**, median **2.72%** |
| Hop `price` | null on every hop |
| `route_pool_addresses` | **316 / 596** slots empty |
| Hops with stored `fee_bps = 0` | 10 bundles (Polygon 4 hops, Arbitrum 6 hops) |

The amount chain is intact, including on the rows below −10%. Multi-block quotes exist and are a timing fact. They do not explain the worst rows: those worst rows are single-block.

### Cause rule used on every complete bundle

| Class | Rule | Count |
|---|---|---:|
| Primarily fee-floor | Compounded-fee residual ≥ −0.10 percentage points, closed path, amount chain intact | 48 |
| Mixed fee and residual | Residual in (−0.50, −0.10) | 32 |
| Excess beyond the fee floor | Residual ≤ −0.50, amount chain intact. Stored depth is positive and the trade is 0.37% to 8.78% of the shallowest hop on these rows | 100 |
| Quote-amount mismatch | Amount chain broken, or wei gross disagrees with stored gross by > 0.01 percentage points | **0** |
| Route not closed | Path does not return to the start token | **0** |

“Excess beyond the fee floor” is a measured gap. It is not a stored price-impact field. Section 4 locates that gap on specific hops where stored prices allow a dollar split.

---

## 4. Family-by-family analysis

Complete-bundle components. Decision-only rows have a Gate 7 sentence and no component block; they are counted and not filled with estimates.

| Family | Rows | Complete | Decision-only | Gross % median (complete) | Gross % min | Fee-floor residual median | Atomic $ median |
|---|---:|---:|---:|---:|---:|---:|---:|
| `DEX_TO_DEX` | 17 | 16 | 1 | −0.103 | −0.629 | **+0.247** | −79.95 |
| `MULTI_HOP` | 27 | 15 | 12 | −0.808 | −0.924 | −0.110 | −143.06 |
| `CROSS_POOL` | 27 | 27 | 0 | −1.418 | −1.792 | −1.068 | −193.76 |
| `CROSS_PROTOCOL` | 8 | 4 | 4 | −1.829 | −1.835 | −1.480 | −235.93 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 83 | 45 | 38 | −1.721 | −9.964 | −1.271 | −238.71 |
| `MULTI_DEX` | 34 | 0 | 34 | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE |
| `TRIANGULAR` | 92 | 73 | 19 | −1.590 | −16.273 | −0.703 | −210.28 |

### `DEX_TO_DEX` — valid fee-floor negative

Sixteen Base bundles, all 2-hop, all `fee_bps` 5 then 30 (telemetry **0.35%**). Shallowest hop depth is about **$8.6M to $9.1M**. Quoted size is about **0.11%** of that depth. Thirteen rows have a positive residual against the fee floor: the quote lost less than the summed pool fees and was still negative. The best gross is **−0.091142%** (**−$9.11** derived) on `31df13631b18c7175c30` and `55517c3623fab219bc65`. Three `uniswap_v3` + `aerodrome` rows reach about **−0.63%** gross, residual about **−0.27** percentage points.

The best decision net, **−$59.31**, is that **−$9.11** quote plus **$0.18** gas plus the **$50.00** model haircut, with a **$0** Balancer fee. The quote itself is negative before the haircut (about **−$9.31** if the haircut is removed on that row). No reverse quote is stored.

One BNB row is decision-only. It does not change the 16-row Base result.

### `CROSS_POOL` — mixed

All 27 rows have a bundle. The Base slice uses fee telemetry **1.05%** and a residual near **−0.05** percentage points (`1a073219555cdc12bded`, gross **−1.102%**). That slice behaves as a fee floor on a ~$772k minimum depth.

The Optimism slice is an excess. Worst row `cacd4da09a9494e99f47`: gross **−1.792%**, fee telemetry **0.35%**, residual **−1.442** percentage points, minimum depth **$296,366**, size/depth **3.37%**, one block, amount chain intact. The excess is real. A separate impact number is not stored.

### `MULTI_HOP` — mixed, small excess

Fifteen Ethereum bundles. Gross **−0.924%** to **−0.508%**. Residual **−0.474** to **−0.048** percentage points. The deeper rows (minimum depth about **$10.4M**) sit on the fee floor. The shallower rows (minimum depth about **$378k**, size/depth **2.6%**) carry the **−0.47** point residual. Gas on these rows is **$11.99 to $14.91**, which is the scaled Ethereum default, and it is larger in dollars than the residual. Twelve further rows are decision-only, so the family is not fully observed.

### `CROSS_PROTOCOL` — insufficient for a cause

Four Polygon bundles, gross **−1.835%** to **−1.014%**, residual **−1.485** to **−0.915** percentage points, minimum depth about **$143k**, size/depth about **7%**. The middle hop stores `fee_bps = 0` on `quickswap_v3`, so the compounded fee floor is missing that leg’s fee and the residual is overstated by an unknown fee. Four more rows have no bundle. Cause is **INSUFFICIENT_EVIDENCE**.

### `TRIANGULAR` — mixed, with a measured thin-hop tail

Seventy-three bundles. Fifteen are fee-floor rows on deep Ethereum liquidity. Example `d293d0e245726e544af4`: gross **−0.403%**, residual **+0.296** percentage points, minimum depth **$40,910,785**, size/depth **0.024%**, same-block uniswap v3 cycle `USDC→WETH→WBTC→WETH→USDC`.

Fifteen bundles are below **−10%** gross. The worst six are one Optimism shape, `USDC→WETH→USDC.e→WETH→USDC`, single block on the worst ids, amount chain intact, fee telemetry **0.70%** (30/5/30/5 bps). Minimum depth about **$114k**. Size/depth about **8.8%**.

Worst id `cbeec5f983b249cc71d8`, gross **−16.27286%** (derived **−$1,627.29**), atomic **−$1,709.90**, flash **$30**, gas **$2.62**. Stored prices: USDC **$1.00**, WETH **$2,700.712885**. `USDC.e` price provenance is `not_evaluated`. Using the stored WETH price and the stored hop wei:

| Leg | Pools and fee | Stored depth | Derived USD result |
|---|---|---:|---|
| USDC → WETH, 30 bps | depth $5,655,850 | **−$36.48** | About a 30 bps fee ($30) plus a few dollars |
| WETH → USDC.e → WETH, 5 bps then 30 bps | depths $114,047 and $165,383 | **−$1,488.09** | WETH value destroyed inside the USDC.e loop |
| WETH → USDC, 5 bps | depth $296,299 | **−$102.71** | Larger than a 5 bps fee on this leg |

The **−16%** gross is the USDC round trip (`8372714007` out versus `10000000000` in). About **$1,488** of the **$1,627** USDC loss sits in the two USDC.e hops. A 35 bps fee on those hops does not account for that loss. USDC.e has no stored USD price, so this split does not prove a stale USDC.e peg versus concentrated-liquidity impact. It does prove the loss is on those two shallow hops, on one block, with a continuous amount chain.

### `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` — mixed size and route, not a fee floor

Forty-five bundles. Gross **−9.964%** to **−0.906%**, median **−1.721%**. Compounded-fee residual is negative on **all 45**: **−9.102** to **−0.457** percentage points, median **−1.271**. Ten rows are in **[−10%, −5%)**. Zero rows meet the fee-floor rule. Thirty-eight further rows have no bundle, including every Base row of this family and every BNB row.

The worst stored gross in this family is Ethereum, not a broken amount chain.

`bada530c082f29c6d8c2`, gross **−9.963626%**, atomic **−$1,059.36**, flash **$5**, gas **$8.00** (units absent, so the unscaled Ethereum default). Path `USDC→WETH→USDT→WETH→USDC`. One block, `26124139`. Protocols `uniswap_v3`, `sushiswap_v2`, `uniswap_v3`, `sushiswap_v2`. Stored prices: WETH **$2,701.877481**, USDT **$0.999216**, USDC **$1**.

| Leg | Venue | Fee bps | Stored depth | Derived USD change |
|---|---|---:|---:|---:|
| USDC → WETH | uniswap v3 | 5 | $98,173,597 | **−$10.51** (in line with a 5 bps fee) |
| WETH → USDT | sushiswap v2 | 30 | $649,157 | **−$328.02** |
| USDT → WETH | uniswap v3 | 30 | $111,275,159 | **−$25.56** (inside a 30 bps fee) |
| WETH → USDC | sushiswap v2 | 30 | $288,949 | **−$632.28** |

The deep v3 legs behave like their fees. The two v2 legs produce the **−9.96%**. The final v2 hop is **3.5%** of its stored depth and about **$603** worse than a 30 bps fee. The same pattern is on `52ba5e58c4a31aed20eb` (gross **−9.800%**, same block family, same v2 venues). Reserves and ticks are not stored, so a constant-product impact formula cannot be recomputed. A smaller-size quote of the same route was not stored, so “this size” and “this v2 venue” are both present and are not separated.

Twenty-five of the 45 bundles span more than one block (maximum span 14). The **−9.96%** and **−9.80%** rows do not. Block skew is a real property of 25 quotes and is not the cause of those two tails.

### `MULTI_DEX`

No complete bundle. See section 5. No gross, fee, gas, slippage, or impact figure is stored. No cause class is assigned.

### Artifact checklist

| Question | Evidence |
|---|---|
| Normal AMM fee floors | Yes on `DEX_TO_DEX`, on the deep `TRIANGULAR` and `MULTI_HOP` rows, and on the Base `CROSS_POOL` rows. No on the `COMPLEX` 45 and no on the Optimism USDC.e tail |
| Excessive trade size | Quoted size is $10,000 on every complete bundle. That size is ~0.11% of depth on `DEX_TO_DEX` and up to 8.8% of the shallowest stored depth on the −16% rows. Impact percent is still **NOT_STORED** |
| Insufficient liquidity | Stored hop depth is positive everywhere. The route-level min TVL field is stored **0** and is not the minimum of the hop depths. The shallow hops above are the liquidity fact that lines up with the large losses |
| Stale quotes | **NOT_PROVABLE** as a denial code. 65 routes span more than one block. The worst tails are single-block |
| Mismatched quote state | Amount chain matches on all 180. Wei gross matches stored gross on all 180. That class is empty |
| Incorrect direction | Forward path and per-hop `token_in` / `token_out` are stored. A reverse quote is **NOT_AVAILABLE**, so a wrong-direction claim is **NOT_PROVABLE** |
| Route construction | The large `COMPLEX` losses are on the sushiswap v2 legs the route selected. The large `TRIANGULAR` losses are on the USDC.e legs the route selected. The path is closed and the amounts chain. The route is a real searched shape that includes those legs |
| Multi-hop fee accumulation | Summed fees are 0.10% to 1.05%. They explain the fee-floor families. They do not explain residuals of several to fifteen percentage points |

---

## 5. MULTI_DEX data gap

All **34** `MULTI_DEX` rows are decision-only. Chains: Polygon **14**, BNB **20**. Providers: Aave V3 **26**, Balancer V2 **6**, Uniswap V3 **2**. Hop count **4** on all 34. Hint source `flash_loan_route_search` on all 34. Shapes: `USDC→WETH→WMATIC→USDT→USDC` (14), `USDC→BTCB→WETH→USDT→USDC` (15), `USDC→BTCB→WBNB→USDT→USDC` (5).

### Where economics stopped

The verifier computes gross, fees, gas, and atomic profit in memory, then returns the Gate 7 sentence, then calls the evidence sink. The sink is best-effort: any exception in bundle build or insert is swallowed, and the Gate 7 sentence is still returned to the discovery queue.

For these 34 candidate ids:

| Fact | Result |
|---|---|
| `verified_outcome` | Present. Pattern `denied:gate_rejection:gate_7:atomic_profit $<cents> < floor $25.00` on all 34 |
| `evidence_bundles` row for that `candidate_id` | **Absent.** Also absent for any other `source_component` and any `created_at` |
| Certified worker bundles in the window | 180, and none of them are these ids |
| Collection validator / TTL | None. Unique key is `bundle_id` only |
| Window logs | No duplicate-key line and no traceback |

The in-memory Gate 7 evaluation happened. The m2.3 document did not persist. The exception text is **NOT_PROVABLE**. The candidate row never receives an economics object; `mark_processed` stores the outcome sentence and clears `claimed_by`.

The same persistence gap covers **108** Gate 7 rows, not only `MULTI_DEX`:

| Chain | Gate 7 rows | Bundles stored | Missing |
|---|---:|---:|---:|
| Ethereum | 45 | 45 | 0 |
| Optimism | 45 | 45 | 0 |
| Arbitrum | 54 | 51 | 3, all `MULTI_HOP` |
| Base | 54 | 29 | 25: `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` 22, `CROSS_PROTOCOL` 3 |
| Polygon | 45 | 10 | 35: `TRIANGULAR` 18, `MULTI_DEX` 14, `MULTI_HOP` 3 |
| BNB | 45 | 0 | 45, every family on BNB including all 20 BNB `MULTI_DEX` rows |

`MULTI_DEX` has no separate economics stop. Every `MULTI_DEX` row in this window was on Polygon or BNB, and those evaluations were among the ones that did not persist a bundle. Base shows a related pattern: the 29 stored Base bundles are the 2-hop families, and the Base 3-hop and 4-hop Gate 7 rows are in the missing set.

### Fields on a `MULTI_DEX` candidate

Present on the discovery document: `candidate_id`, chain, provider, `cycle_token_path`, `route_pools`, `route_dex_protocols`, `route_hops` (dex, fee, pool id, token symbols), `hop_count`, `estimated_total_fee_pct` (0.15 to 0.70), `min_tvl_usd` (about $131,788 to $224,623), `borrow_amount_wei`, `borrow_amount_provenance=deterministic_probe`, the Gate 7 sentence, `verified_at`, `verification_latency_ms`.

Absent: gross percent, gross dollars, flash-loan fee, DEX fee actually charged, gas, slippage, hop `amount_in_wei` / `amount_out_wei`, quote block, hop depth, MEV level, full-precision atomic profit, `route_quote_status`, `exact_size`.

`estimated_total_fee_pct` is a discovery hint. It is not the quote gross.

### Can gross be reconstructed?

**No. Reconstruction is impossible from the stored fields.**

The Gate 7 sentence is one cent-rounded net. On the 180 bundles that net equals gross minus flash fee, gas, and the $50 haircut. For these 34, flash fee, gas units, and the haircut’s presence are not stored. Provider is stored, and the catalog fee is determined only if the notional is known. `borrow_amount_usd` is not on the hint. The hint wei is a probe (BNB example `50000000000000000`; Polygon example `200000000`), and token decimals are not stored on the candidate, so the probe’s dollar size is **NOT_PROVABLE** here. One equation with those unknowns does not yield gross.

Decision nets for these 34 were already ranked from the outcome text (mean about **−$352.82**, best **−$153.86**, worst **−$889.60**). Those figures are nets. They are not a gross.

---

## 6. Size and direction evidence

No new live scan was run.

| Question | Complete bundles (180) | Decision-only (108), including all 34 `MULTI_DEX` |
|---|---|---|
| Requested trade size | Hint `borrow_amount_wei` is a `deterministic_probe` on 151 rows and absent on 29. Where present on 6-decimal USDC routes the probe wei is **200000000** (200 USDC). It is not the quoted size | Probe wei is stored. Dollar size of the probe is **NOT_PROVABLE** where decimals are not stored. BNB sample wei `50000000000000000` |
| Quoted trade size | **Stored.** `quote_notional_usd = 10000`, `quoted_amount_in_wei = 10000000000` on the USDC routes, `exact_size = true`. Economics used this notional, not the probe | **NOT_AVAILABLE** |
| Available liquidity | Per-hop `depth_usd` stored and positive. Route-level min TVL stored as **0**, which does not equal the min hop depth. `tvl_provenance = onchain_reserves` | Hint `min_tvl_usd` only. No hop depth |
| Route direction | Stored forward path and per-hop `token_in` / `token_out` | Stored symbol path and hint hops. No quoted addresses or amounts |
| Reverse direction | **NOT_AVAILABLE** | **NOT_AVAILABLE** |
| Pool reserves / ticks | **NOT_AVAILABLE.** Leg keys are `amount_in_wei`, `amount_out_wei`, `block_number`, `depth_usd`, `dex_protocol`, `fee_bps`, `price` (null), `source_id`, `status`, `token_in`, `token_out`, `venue_id` | **NOT_AVAILABLE** |
| Slippage | Stored **0.0** | **NOT_AVAILABLE** |
| Price impact | **NOT_STORED.** The derived residual and the hop USD splits in section 4 are the available substitutes, and they are labelled | **NOT_AVAILABLE** |

Size and direction can be evaluated for the 180 at the quoted $10,000 forward route. They cannot be evaluated as a reverse quote, as active-tick liquidity, or as a second size. They cannot be evaluated for the 108 beyond the discovery hint.

---

## 7. Negative-control validity

The 180 are trustworthy as an accounting record of this search:

- The quote closed in the borrow token and the wei ratio equals the stored gross.
- Costs that were persisted, plus the $50 model haircut implied by `MEDIUM`, reproduce atomic profit.
- No complete bundle has a positive gross, and none reaches the derived zero-profit breakeven.

They are not one kind of negative:

| What the negative shows | Validity |
|---|---|
| This $10,000 forward search did not store a positive gross | Trustworthy on the 180 |
| The loss is the AMM fee floor | Trustworthy for `DEX_TO_DEX` and for the deep, small-residual slices of `TRIANGULAR`, `MULTI_HOP`, and Base `CROSS_POOL` |
| The loss is an efficient market on every family | Not supported for `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` or for the Optimism USDC.e tail. Those gross figures exceed the fee floor by 1 to 15 percentage points, on identified shallow hops |
| `MULTI_DEX` is a measured negative gross | Not supported. Gross was not stored |

The $50 haircut makes every decision net at least $50 worse than quote-minus-flash-minus-gas. On the best `DEX_TO_DEX` row it is most of the decision net. The quote on that row is still about −$9. Removing the haircut does not create a positive gross anywhere in the 180, because every gross percent is already negative and the identity was checked with and without the 0.5 point.

---

## 8. E0 classification

| Family | Class | Why |
|---|---|---|
| `DEX_TO_DEX` | **VALID_NEGATIVE_CONTROL** | 16/17 complete. Gross inside or next to the fee floor. Depth ~$9M. Quote still negative |
| `CROSS_POOL` | **MIXED** | Base rows are fee-floor. Optimism rows are about 1.4 percentage points worse than a 0.35% fee, at ~3.4% of stored depth, with an intact quote |
| `MULTI_HOP` | **MIXED** | Complete rows are within 0.47 percentage points of the fee floor. 12/27 have no components |
| `CROSS_PROTOCOL` | **INSUFFICIENT_EVIDENCE** | 4 complete rows, a stored 0 fee on a quickswap leg, 4 rows with no bundle |
| `TRIANGULAR` | **MIXED** | A fee-floor subset on deep pools, and a < −10% subset whose loss is on the USDC.e hops |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | **MIXED** | No fee-floor row among the 45. The −10% class is the sushiswap v2 legs. Size and route are both visible. 38 rows have no gross |
| `MULTI_DEX` | **INSUFFICIENT_EVIDENCE** | 0 bundles. Gross reconstruction impossible |

**Overall: E0_PARTIAL**

`E0_PASS` would require the negative result to be a trustworthy fee-floor control across the measured families, with components present. The 180 identities are trustworthy, and several slices are real fee floors. The deep tail is a measured excess on shallow legs, and 108 Gate 7 rows, including every `MULTI_DEX` row, have no components. `E0_FAIL` would require the 180 gross figures to be internally inconsistent. They are not.

No strategy is rescued by this classification. The excess loss is a reason to distrust a fee-floor reading of those families. It is not a design for a new size, a new route, or a new engine.

---

## 9. E1 data requirements

E1 is a realized-arbitrage census: at least 14 historical days on each supported chain where the data exists. Chains: Ethereum, Arbitrum, Base, Optimism, Polygon, BNB Chain. The census looks for atomic arbitrage transactions that executed. Classes are assigned only when the evidence supports them: `DEX_TO_DEX`, `CROSS_POOL`, `TRIANGULAR`, `MULTI_HOP`, `CROSS_PROTOCOL`, `LIQUIDATION`, `BACKRUN`, `NATIVE_PROTOCOL_MECHANISM`, `INTENT/SOLVER`, `OTHER`. A transaction that does not meet a class stays unclassified.

| Data | Why it is required | Status on the current endpoints |
|---|---|---|
| Historical blocks | 14-day window, block time, coinbase, tx count | **Available.** `eth_getBlockByNumber` succeeded at a ~14-day lookback on all six Alchemy hosts |
| Transactions | from, to, input, nonce, gas fields, tx index | **Available.** `eth_getTransactionByBlockNumberAndIndex` returned a transaction on Ethereum at that depth |
| Receipts | status, gas used, logs bloom, contract address | **Available.** Receipt read succeeded for that transaction |
| Logs | Swap, flash-loan, and ERC-20 Transfer events | **Available.** A two-block `eth_getLogs` at that depth returned 134 logs on Ethereum |
| Historical state | Pool reserves, ticks, or a balance at the census block | **Partially demonstrated.** `eth_getBalance` at the old block succeeded on all six hosts. One historical `eth_call` (WETH `balanceOf`) succeeded on Ethereum. A six-chain `eth_call` matrix was not run |
| Traces / internal calls | Call tree, internal ETH, searcher profit that never emits a log | **NOT_AVAILABLE.** `debug_traceBlockByNumber`, `debug_traceTransaction`, and `trace_block` return HTTP 400: not available on the Free tier. The same Free-tier rejection was returned by `ARBICORE_ARCHIVE_RPC_URL` |
| Token transfers | Profit in ERC-20 when Transfer logs exist | **Available as logs**, when the contracts emit them |
| Pool state | Compare a realized route to the pool ArbiCore would have quoted | **Not stored for E1.** Historical `eth_call` is the method, and it was only spot-checked |
| Protocol events | Flash-loan and swap signatures for classification | **Available as logs**, decoder not run |
| Gas used | Receipt `gasUsed` | **Available** on the receipt probe |
| Priority fee | `maxPriorityFeePerGas` and `effectiveGasPrice` when the transaction object carries them | **Present on the sampled Ethereum transaction fields.** A 14-day distribution was not computed |
| Builder payment | Coinbase transfer or a known builder address, when visible without a trace | **Partial.** A trace-free census can see explicit value transfers that appear in logs or in the transaction `value`. Internal coinbase payments need traces and are **NOT_AVAILABLE** on this tier |
| Searcher contract / address | `from` and `to` | **Available** on the transaction object |
| Block transaction index | `transactionIndex` | **Available** |

`ARBICORE_ARCHIVE_RPC_URL` is host `base-mainnet.g.alchemy.com`, the same host as the Base primary URL in the container environment. It is not a six-chain archive, and it does not serve debug traces on this tier. The bootstrap Base URL `mainnet.base.org` failed the head request. Production Network Config already points Base at Alchemy. This probe did not change that.

---

## 10. Available versus missing data

| Need | Available now | Missing |
|---|---|---|
| 14-day headers, transactions, receipts, logs | Yes, on the six configured Alchemy hosts, demonstrated by a single-depth probe | A volume test and a decoder |
| Historical `eth_call` / balance | Yes at the probed depth | Per-pool slot0 / reserve calls for the census blocks |
| Traces and internal calls | No | A trace-capable research endpoint |
| `MULTI_DEX` and the other 108 gross figures | Decision net text only | The m2.3 bundle, and the exception that dropped it |
| Reverse quotes, reserves, ticks, separate impact | No on the shadow bundles | Not recoverable from these documents |
| Builder-payment completeness | Priority-fee fields on the tx object | Internal payments |

Running the full 14-day census on these hosts would be a new, large read against the same RPC the scanner uses. This note did not do that.

---

## 11. Safe archive-data architecture

The production RPC topology stays as it is. Network Config is not edited. The scanner is not given a second URL. No archive host is added to `rpc_urls`.

| Piece | Rule |
|---|---|
| Research reader | A separate process. It does not import the scanner loop, does not open a certification run, and does not write `arbicore_discovery_candidates`, `evidence_bundles`, `arbicore_config`, or `arbicore_opportunities` |
| Endpoints | Its own credential and URL, supplied only to that process. If traces are required, that credential is a trace-capable plan. The current Free-tier hosts are not that source |
| Production services | They keep the certified Network Config revision. They are not restarted to pick up a research URL |
| Output | A research file or a research database, outside the certified collections |
| What the current hosts can support, if a later gate authorizes the volume | Headers, transactions, receipts, logs, and historical `eth_call` |
| What they cannot support | `debug_trace*` and `trace_*` |

Required data source for a **complete** E1, including internal calls:

| | |
|---|---|
| REQUIRED DATA SOURCE | A trace-capable archive endpoint for each chain in scope, on a research credential |
| DATA NEEDED | `debug_traceTransaction` or `trace_replay` / `trace_block` for candidate transactions, plus the logs and receipts already readable |
| WHY NEEDED | Searcher profit, internal ETH, and many builder payments are inside the call tree and are absent from the Free-tier methods |
| SAFE READ-ONLY METHOD | The research reader above. No Network Config write, no scanner env change, no production restart |

A **log-and-receipt** census can start without that source and must be labelled partial wherever the call tree is required.

---

## 12. E1 census design

Not implemented.

```
ON-CHAIN DATA
  research reader
  per chain, per day in the 14-day window
  blocks → transactions → receipts → logs
  historical eth_call only for pools that survive the log filter
        │
        ▼
ATOMIC ARBITRAGE DETECTION
  a transaction is a candidate when its logs show a flash-loan
  borrow and repay, or a closed token cycle, inside one transaction
  index. Multi-transaction strategies stay out of the atomic set.
        │
        ▼
TRACE ANALYSIS
  if a research trace source exists: call tree, internal value,
  coinbase payment.
  if it does not: record TRACE_NOT_AVAILABLE and continue with logs.
        │
        ▼
PROFIT RECONSTRUCTION
  ERC-20 Transfer deltas for the searcher and the executor.
  Gas used × effective gas price.
  Priority fee when present.
  Builder payment only when a trace or an explicit transfer shows it.
  Missing legs stay null. No fill-in from the shadow model.
        │
        ▼
STRATEGY CLASSIFICATION
  assign a class only from the realized hops.
  otherwise OTHER or UNCLASSIFIED.
  do not force LIQUIDATION, BACKRUN, or INTENT.
        │
        ▼
SEARCHER IDENTIFICATION
  transaction from, to, and any contract that receives the profit.
        │
        ▼
OPPORTUNITY RECORD
  chain, block, tx index, tx hash, class, tokens, pools, venues,
  size, profit, gas, priority fee, builder payment or null,
  trace status.
        │
        ▼
ARBICORE COVERAGE COMPARISON
  section 13. Read-only against the certified universe.
  no scanner run.
```

The pilot, when a later gate allows it, is one chain and one day, written only to the research output. The 14-day six-chain run is a second step after that pilot reconciles.

---

## 13. Coverage-diff design

For each realized atomic transaction the comparison record has two sides and a gap list.

**Realized side**

| Field | Source |
|---|---|
| `chain` | Block |
| `block_number`, `tx_index`, `tx_hash` | Transaction |
| `timestamp` | Block |
| `searcher` | `from` / profit recipient |
| `class` | Classifier or `UNCLASSIFIED` |
| `tokens` | Log order |
| `pools` | Swap event addresses |
| `venues` | Pool → protocol map, or `UNKNOWN_VENUE` |
| `direction` | Token order in the transaction |
| `size_token`, `size_raw` | Borrow or first swap amount |
| `profit_token`, `profit_raw`, `profit_usd` | Transfer delta. USD only when a price source for that block is recorded. Otherwise USD is null |
| `gas_used`, `priority_fee` | Receipt and transaction |
| `builder_payment` | Trace or explicit transfer, else null |
| `trace_status` | `PRESENT` or `TRACE_NOT_AVAILABLE` |

**ArbiCore side, from the certified universe as stored, not from a new scan**

| Field | Source |
|---|---|
| `chain_enabled` | Network Config `chains_enabled` |
| `protocol_in_search` | Discovery `route_dex_protocols` vocabulary and the route-search sources |
| `pool_known` | Pool id or address present in the certified route universe |
| `token_known` | Token on a stored path |
| `route_shape_supported` | Hop count and cycle shape the search actually emitted |
| `direction_supported` | The forward path that was quoted. Reverse is unknown |
| `size_policy` | The $10,000 exact quote used on the 180, and the probe wei on the hint |
| `quote_block` | Bundle `quote_block` when a shadow row exists for that pool |

**Gap tags, one or more, only when the field compares**

| Tag | When it is set |
|---|---|
| `missing_chain` | Realized chain is outside the six, or that chain is disabled |
| `missing_protocol` | Venue protocol is not in the search vocabulary |
| `missing_venue` | Protocol exists and this deployment or pool type does not |
| `missing_pool` | Pool address is absent from the certified universe. Empty `route_pool_addresses` (316 of 596 slots in this window) count as not-known until an address is stored |
| `missing_token` | Token absent from searched paths |
| `missing_route` | Tokens and pools are known and this cycle was not emitted |
| `unsupported_route_shape` | Hop pattern is outside the shapes the search emitted |
| `wrong_direction` | Realized order is the opposite of a stored path. Set only when both directions are known |
| `wrong_size` | Realized size and the $10,000 quote differ by a recorded ratio |
| `stale_quote` | A shadow quote block and the realized block differ. No shadow row means this tag is not set |
| `economics_mismatch` | Both profits exist and differ after the same cost categories. Missing costs stay null |
| `timing_dependent_state` | Realized profit depends on a state change inside the block that a pre-block quote cannot see |
| `other` | Named in free text |

A gap tag is omitted when the comparison field is null. The record then says which field was missing.

---

## 14. Recommended next gate

**Next gate:** `E1_REALIZED_ARBITRAGE_CENSUS_READ_ONLY`

**State:** not started.

**Readiness:** **PARTIAL**. Logs, receipts, transactions, and historical calls are readable on the current hosts. Traces are not. The census is not authorized by this document.

Do not implement, in this gate or as a side effect of it:

- a new strategy, including the research hypotheses S1 long-tail liquidation, S3 native mint/redeem, S8 intent/solver, S4 exact concentrated-liquidity fee tier, S5 hooks and dynamic fees, and S14 post-forced-flow
- liquidation detection, backrun logic, or intent/RFQ
- a scanner change, an RPC change, a Gate 7 change, a deploy, or a restart
- a production write that backfills the 108 missing bundles

The E0 result that feeds that decision is **E0_PARTIAL**:

- The 180 negative bundles are economically trustworthy as quotes and as an assessor identity.
- `DEX_TO_DEX` is a valid fee-floor negative control.
- `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` and the Optimism `TRIANGULAR` tail show a measured excess over fees on shallow hops. That is a size-and-route artifact in the quote, with impact percent itself unstored.
- `MULTI_DEX` gross is not stored, and it cannot be reconstructed.
- E1 should be designed against realized transactions. It should not be a rerun of this $10,000 shadow mix, and it should not be a build of the candidate engines above until the census and the coverage diff exist.
