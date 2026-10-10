# Phase 0.5 — Triangular stored-gross analysis

**Classification: TRIANGULAR_STORED_GROSS_ANALYSIS_COMPLETE**

**Date:** 2026-10-05

**Mode:** read-only. No source edit, MongoDB write, deploy, restart, RPC or Network Config change, scanner control, SHADOW or PAPER start, Gate change, MEV change, execution-mode change, signing, or broadcast.

**Run:** `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065`

**Window used:** `verified_at >= 1791178068.513927` and `verified_at < 1791179884.231514` (`2026-10-05T05:27:48.513927Z` inclusive through `2026-10-05T05:58:04.231514Z` exclusive). Gate-7 filter: `verified_outcome` contains `gate_7:atomic_profit`. This is the same window as the certified ranking.

**Population check:** 288 Gate-7 candidates, 180 `flash_loan_arb_verifier` bundles, no candidate with more than one bundle. Classifier `phase0.strategy_intelligence.v1`, called in memory as `observe_strategy_intelligence(bundle, candidate)`. Family is `strategy.primary_family`. The call does not write.

**Gross rule:** a gross figure is used only when `economics.gross_spread_pct` is stored on an m2.3 bundle. Rows with no bundle are counted and then left out of every gross statistic. No missing percent, fee, gas, or net was filled in. The MEDIUM MEV label is reported as stored. `mev_penalty_pct` is not on these bundles, and it is not used below.

Median, wherever a median is given: odd count, the middle value of the sorted stored sample; even count, the average of the two central stored values.

---

## 1. How many TRIANGULAR candidates?

**92.**

All 92 are `classification_state=COMPLETE`, `strategy_completeness=FULLY_CLASSIFIED`, confidence `MEDIUM`, `hint_source=flash_loan_route_search`. Every row carries secondary tag `CROSS_POOL` only. `STABLECOIN` and `LST_LRT` were not assigned.

The other 196 Gate-7 candidates in the window are other primaries. They are not in the tables below.

## 2. How many have complete m2.3 bundles?

**73 complete. 19 have no bundle.**

`bundle_presence=COMPLETE_BUNDLE` on 73: schema `m2.3`, worker `flash_loan_arb:0eb9228c`, `quotes.route_quote_status=ok`, `quotes.exact_size=true`, `broadcast=false`, `verification_status=DENIED`.

The 19 without a bundle are Polygon 18 and BNB 1. Their decision-net text is stored on the candidate. Their gross, fee, gas, and true net are not stored. They do not appear in the gross statistics.

## 3. Stored gross spread

Source: `economics.gross_spread_pct` on the 73 bundles. `quotes.gross_profit_pct` is also stored on all 73. No pair differs by more than `0.000001`. On the best row the quote field is `-0.18981233` and the economics field is `-0.189812`.

| | Stored gross % |
|---|---:|
| n | 73 |
| Minimum | -16.272860 |
| Maximum | -0.189812 |
| Mean | -4.124721 |
| Median | -1.589965 |

## 4. Counts against zero and against flash fee + gas + $25

| Test | Count | Basis |
|---|---:|---|
| Gross stored | 73 | `economics.gross_spread_pct` present |
| Gross not stored | 19 | no bundle |
| `gross > 0` | **0** | of the 73 |
| `gross >= 0` | **0** | of the 73 |
| `gross == 0` | **0** | of the 73 |
| Gross at or above the cost threshold | **0** | of 73 evaluable rows |
| Threshold not evaluable | **0** | of the 73. Each has stored gross, `fees.flash_loan_fee_usd`, `gas.gas_cost_usd`, and `economics.borrow_amount_usd` |

Threshold, applied per row and not stored as its own field:

`need_gross_pct = (flash_loan_fee_usd + gas_cost_usd + 25) / borrow_amount_usd * 100`

compared with stored `gross_spread_pct`. Borrow is `$10,000` on all 73, and it equals `quotes.quote_notional_usd` and `input_amount_usd` on those rows. The stored MEV penalty is not in the formula because it is not on the bundle. `fees.flash_loan_fee_bps` is stored as `0` on these rows and is not the dollar fee; the threshold uses `fees.flash_loan_fee_usd` (`$0`, `$5`, or `$30`).

The smallest shortfall is still negative. Candidate `aca9e16d661b7c5ead5f` has stored gross `-0.199894%`, stored flash fee `$0`, stored gas `$0.3805824`, so the stored-cost threshold is `+0.253806%`. Gap: `-0.453700` percentage points. The best-gross row is the next-closest and is short by `-0.493968` percentage points because its stored flash fee is `$5`.

## 5. By chain

Base has **zero** Triangular candidates in this window. Gross statistics use only rows that stored `economics.gross_spread_pct`.

| Chain | Candidates | Complete bundles | Gross stored | Min % | Max % | Mean % | Median % | `> 0` | `>= 0` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Ethereum | 9 | 9 | 9 | -0.704278 | -0.402875 | -0.603226 | -0.702526 | 0 | 0 |
| Arbitrum | 27 | 27 | 27 | -1.133325 | -0.189812 | -0.840480 | -0.941768 | 0 | 0 |
| Base | 0 | 0 | 0 | — | — | — | — | — | — |
| Optimism | 31 | 31 | 31 | -16.272860 | -1.600648 | -7.291553 | -2.678246 | 0 | 0 |
| Polygon | 24 | 6 | 6 | -14.053429 | -1.589965 | -7.824084 | -7.818884 | 0 | 0 |
| BNB | 1 | 0 | 0 | — | — | — | — | — | — |
| **All** | **92** | **73** | **73** | **-16.272860** | **-0.189812** | **-4.124721** | **-1.589965** | **0** | **0** |

Arbitrum is the least-negative chain and its best stored gross is still `-0.189812%`. Optimism’s best stored gross is `-1.600648%`. Polygon’s six stored grosses are all `<= -1.589965%`. The 18 Polygon rows and the one BNB row without a bundle contribute candidates and no gross.

## 6. By route shape

Shape is the letter form of the stored `cycle_token_path` (bundle path when a bundle exists, otherwise `hint_metric.cycle_token_path`). It is a label of the stored path. It is not a profit estimate.

| Shape | Candidates | Complete bundles | Gross stored | Min % | Max % | Mean % | Median % | `> 0` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `A→B→A` | 0 | 0 | 0 | — | — | — | — | — |
| `A→B→C→A` | 53 | 34 | 34 | -14.053429 | -0.189812 | -2.948050 | -2.373075 | 0 |
| `A→B→C→B→A` | 39 | 39 | 39 | -16.272860 | -0.402875 | -5.150537 | -0.963037 | 0 |
| other | 0 | 0 | 0 | — | — | — | — | — |

Hop count on the stored fields: 39 rows are 4 hops on both the bundle and the hint; 34 bundled rows are 3 hops on both; the 19 without a bundle have hint hop count 3 and no bundle hop count. The 4-hop rows stay `TRIANGULAR` under the classifier because the stored path has exactly three distinct tokens. That is the classifier’s recorded reason, not a second family assignment.

## 7. By flash-loan provider

Provider is `flash_loan_provider` on the 73 bundles and `hint_metric.provider` on the 19 without a bundle. On the 73, the bundle provider and the hint provider agree.

| Provider | Candidates | Complete bundles | Gross stored | Min % | Max % | Mean % | Median % | `> 0` | Stored flash fee $ on bundled rows |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Aave V3 | 32 | 25 | 25 | -16.265011 | -0.189812 | -4.091231 | -1.589965 | 0 | `$5` on all 25 |
| Balancer V2 | 30 | 24 | 24 | -16.265011 | -0.199894 | -4.142029 | -1.356357 | 0 | `$0` on all 24 |
| Uniswap V3 | 30 | 24 | 24 | -16.272860 | -0.199894 | -4.142299 | -1.366986 | 0 | `$30` on all 24 |

No provider has a stored gross at or above zero. The best gross in the family is an Aave row. The best Balancer and Uniswap grosses are `-0.199894%`.

## 8. Stored gross against stored true net

On all 73 bundles:

| Stored field | Result |
|---|---|
| `economics.gross_spread_pct` | `< 0` on all 73 |
| `economics.atomic_profit_usd` | `< 0` on all 73. This is the stored true net |
| `economics.expected_net_after_costs_usd` | equal to `atomic_profit_usd` on all 73. Largest absolute difference `$0` |
| Candidate `verified_outcome` cent amount | same sign, same denial. Largest absolute difference versus `atomic_profit_usd` is `$0.004897` |
| Pairing | **73 / 73 are `gross < 0` and `true net < 0`** |
| `gross > 0` and `true net < 0` | **0** |
| `gross > 0` and `true net >= 0` | **0** |

True-net distribution on these 73 only (the 19 without a bundle are excluded): minimum `-$1,709.903549`, maximum `-$70.369952`, mean `-$476.356780`, median `-$210.284722`.

Stored alongside the gross, and not used to rebuild it:

| Field | On the 73 |
|---|---|
| `fees.total_slippage_pct` | `0.0` on all 73 |
| `fees.total_swap_fee_pct` | stored and non-zero: `0.15` (3), `0.40` (9), `0.65` (19), `0.70` (39), `0.90` (3) |
| `gas.gas_cost_usd` | minimum `$0.176549`, maximum `$12.907904` |
| `mev.level` / `mev.label` | `MEDIUM` |
| `mev.score` | `48.0` |
| `economics.mev_penalty_pct` | key absent on all 73. Observer status `AVAILABLE_NOT_PERSISTED` |
| Gate 7 | `FAIL` on all 73 |
| Gate 8 | `NOT_EVALUATED` on all 73 |
| Gate 9 | `NOT_EVALUATED` on all 73 |

Gross percent and true-net dollars are different units. The sign comparison does not require converting one into the other. The true net is more negative in dollars than the gross percent alone. This file does not assign that dollar gap to the MEV penalty, because the penalty percent is not stored.

## 9. What kind of loss this is

**A. Already gross-negative.**

Not B. No bundled row has positive stored gross, so costs are not what turned a winning quote into a loss.

Not C. The 73 stored grosses are all negative. The 19 rows without a gross are absent data, not a positive-gross subset.

## 10. Best stored-gross Triangular candidate

Selection: maximum stored `economics.gross_spread_pct`. One row holds that maximum. It is not the best true-net row. The best true net in the family is `-$70.369952` on `aca9e16d661b7c5ead5f`, whose stored gross is `-0.199894%`, slightly worse than the row below.

### Identity

| Field | Stored value |
|---|---|
| `candidate_id` | `aa840b3648dd3573867c` |
| `bundle_id` | `flarb:aa840b3648dd3573867c:1791178414` |
| Chain | `arbitrum` on the candidate and the bundle |
| `flash_loan_provider` | `aave_v3` (hint provider agrees) |
| `borrow_token` | `USDC` |
| `hint_source` / `discovery_source` | `flash_loan_route_search` |
| Worker | `flash_loan_arb:0eb9228c` |
| `scanner_tick_id` | `3` |
| `audit_run_id` | `flarb_audit:a89e889be81c` (scanner process id, not the certification run id) |
| Schema | `m2.3` |
| `provenance` | `REAL` |
| `verification_status` | `DENIED` |
| `opportunity_id` | null |
| `broadcast` | `false` |
| Classifier | `TRIANGULAR`, `COMPLETE`, `FULLY_CLASSIFIED`, confidence `MEDIUM`, secondary `CROSS_POOL` |
| `hint_observed_at` | `1791178144.9977598` |
| `verified_at` | `1791178414.655949` (`2026-10-05T05:33:34.655949Z`) |
| Bundle `created_at` | `2026-10-05T05:33:34.638980Z` |

### Route

| Field | Stored value |
|---|---|
| `cycle_token_path` | `USDC → WETH → WBTC → USDC` |
| Shape | `A→B→C→A` |
| `hop_count` | `3` on the bundle and the hint |
| `route_dex_protocols` | `uniswap_v3`, `uniswap_v3`, `uniswap_v3` |
| `route_pools` | `uniswap_v3:USDC:WETH:500`, `uniswap_v3:WBTC:WETH:500`, `uniswap_v3:USDC:WBTC:500` |
| `route_pool_addresses` | `0xd0b53D9277642d899DF5C87A3966A349A798F224`, null, null |

### Quote legs

`quotes.route_quote_status=ok`, `exact_size=true`, `size_basis=exact`, `quote_block=511830857`, `quote_notional_usd=10000.0`. Per-leg `price` is null. Per-leg `source_id` is `uniswap_v3_quoter_arbitrum`. Per-leg `venue_id` is `uniswap_v3:arbitrum`. Per-leg `fee_bps` is `5`.

| Hop | Block | Token in | Token out | Amount in (wei) | Amount out (wei) | `depth_usd` | Status |
|---:|---:|---|---|---:|---:|---:|---|
| 0 | 511830856 | `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` | `0x82aF49447D8a07e3bd95BD0d56f35241523fBab1` | 10000000000 | 3705676999732920365 | 36880854.995920345 | ok |
| 1 | 511830857 | `0x82aF49447D8a07e3bd95BD0d56f35241523fBab1` | `0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f` | 3705676999732920365 | 11692288 | 36173839.24321048 | ok |
| 2 | 511830857 | `0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f` | `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` | 11692288 | 9981018767 | 7995417.18915004 | ok |

The stored quote gross matches those wei amounts: final out `9981018767` against start `10000000000` is `quotes.gross_profit_pct = -0.18981233`. Hop 0’s block is one below the route quote block. That is a stored fact. It is not a second quote of the same leg, and it is not used here as a decay finding.

### Economics stored on this row

| Field | Stored value |
|---|---|
| `economics.gross_spread_pct` | **-0.189812** |
| `quotes.gross_profit_pct` | -0.18981233 |
| `economics.borrow_amount_usd` | 10000.0 |
| `input_amount_usd` | 10000.0 |
| `fees.flash_loan_fee_usd` | 5.0 |
| `fees.flash_loan_fee_bps` | 0 |
| `fees.total_swap_fee_pct` | 0.15 |
| `fees.total_slippage_pct` | 0.0 |
| `gas.gas_cost_usd` | 0.4156356 |
| `gas.tx_gas_units` | 346363 |
| `economics.atomic_profit_usd` | -74.396869 |
| `economics.expected_net_after_costs_usd` | -74.396869 |
| `verified_outcome` | `denied:gate_rejection:gate_7:atomic_profit $-74.40 < floor $25.00` |
| Gate 7 | `FAIL`, reason `atomic_profit $-74.40 < floor $25.00` |
| Gate 8 | `NOT_EVALUATED` |
| Gate 9 | `NOT_EVALUATED` |
| `mev` | `level=MEDIUM`, `label=MEDIUM`, `score=48.0`, `notional_usd=10000.0`, `is_atomic=true`, `asset=USDC`, `bridge=atomic_flashloan` |
| MEV penalty percent | not stored |

Cost threshold for this row, from the stored dollar fee, stored gas, and stored borrow: `(5 + 0.4156356 + 25) / 10000 * 100 = 0.304156%`. Stored gross `-0.189812%` is below that line.

### Other stored fields on this row that this analysis does not turn into a cause

`liquidity.min_pool_tvl_usd_in_route` is `0.0`. `liquidity.tvl_provenance` is `onchain_reserves`. Gate 8 did not run.

`liquidity.price_provenance` for WETH records block `52194518` and pool `0xd0b53D9277642d899DF5C87A3966A349A798F224`. The hop quotes record blocks `511830856` and `511830857`. WBTC price provenance is `status=not_evaluated`, `price_usd=null`. USDC price provenance is `configured_numeraire`, `price_usd=1.0`. The gross percent above is the stored USDC-out versus USDC-in on the hop legs. It does not depend on the WETH dollar mark. This analysis does not treat the provenance block as the reason the quote is negative, and it does not treat it as a reason to keep the family open.

---

## What was not done

- No SHADOW or PAPER window.
- No recomputation of `aggregate_economics`.
- No conversion of the 19 missing grosses from decision-net text, token names, or DEX names.
- No use of the default `0.5` point MEDIUM penalty. The label and the score are stored. The penalty percent is not.

The 19 rows without a bundle remain a persistence gap, concentrated on Polygon and BNB. They do not contain a stored gross that this read could have missed.

---

## Strategic conclusion

DEPRIORITIZE_TRIANGULAR
