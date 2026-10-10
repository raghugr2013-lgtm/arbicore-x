# SHADOW 30-minute flash-loan strategy economics — 2026-10-04

> **READ-ONLY.** Closed window. SHADOW was not rerun. No code, configuration, RPC, Network Config, threshold, deploy, or restart. No commit or push. The $25 Gate-7 floor was not changed. Missing economics were not reconstructed.

- **Classification:** **ECONOMICS_ATTRIBUTION_PARTIAL**
- **Window (half-open):** `verified_at >= 1791103189.7415638` and `verified_at < 1791104989.7415638`
- **Window ISO:** `2026-10-04T08:39:49.741564Z` inclusive through `2026-10-04T09:09:49.741564Z` exclusive
- **Observed verified_at span:** `2026-10-04T08:40:20.457495Z` … `2026-10-04T09:09:46.371853Z`
- **Container:** `arbicore-x-backend-new` (read-only `docker exec` / Mongo queries)
- **Database / collection:** `arbicore_x.arbicore_discovery_candidates`, joined to `arbicore_x.evidence_bundles` on `source_model_id = candidate_id`
- **Filter:** `verified_outcome` contains `gate_7`
- **Queried at (UTC):** `2026-10-04T12:23:38Z`

## Sufficiency

Stored data **is sufficient** to name the flash-loan provider on all **256** Gate-7 evaluations. `subject_id` (`flash_loan:{provider}:...`) and `hint_metric.provider` agree on every row. On the 166 joined bundles, `flash_loan_provider` agrees as well. Mismatches: **0**.

Stored data **is not sufficient** to say which of the six route families produced all 256 evaluations. No candidate and no joined bundle stores a strategy label (`strategy`, `strategy_hint`, `activation_source`, `route_class`, or any of the six family names). One family is established from stored route metadata under the flash-loan classifier’s own rule:

- **Triangular: 156 / 256.** `classify_strategy` in `strategy_tagging.py` returns `TRIANGULAR` when the stored token path is closed and contains exactly three distinct symbols. That rule uses `hint_metric.cycle_token_path`. It does not use chain, DEX name, hop count, or flash-loan provider. None of these 156 paths are all-stable or LST/LRT, so the earlier branches of that function do not apply.
- **DEX→DEX, Multi-hop, Multi-DEX, Cross-pool, Cross-protocol: UNAVAILABLE** on every row. Assigning them would use hop count or the DEX-name set as the reason. Those signals are stored and are listed below as raw fields. They are not promoted into those families. `classify_strategy` would return `MULTI_HOP` for 51 rows and `GENERIC_DEX` for 49 rows; those returns are hop-count branches and are not mapped onto the six requested names.

`opportunity_engine.classify_route` also returns `triangular` when `hop_count == 3` and the open token path has three distinct symbols. That holds for **57** of the 156. The other **99** are four-hop, three-node paths (`A→B→C→B→A`). `classify_strategy` still calls them `TRIANGULAR`. `classify_route` and `multichain_opportunity_doc._classify` call them `multi_hop` because the hop count is 4. This report keeps those 99 in Triangular under `classify_strategy` and does not add Multi-hop, because that second label is the hop-count branch.

## Gate-7 formula (name only)

`FlashLoanOpportunityVerifier.verify` builds a `FlashLoanEconomicsResult`. `FlashLoanGate7AtomicProfit.evaluate` compares `atomic_profit_usd` with `min_atomic_profit_usd` (default `25.0`). On failure the stored reason is `denied:gate_rejection:gate_7:atomic_profit $<amount:.2f> < floor $<floor:.2f>`.

`FlashLoanEconomicsAssessor.assess` calls `aggregate_economics` with `gross_is_quote_inclusive=True`. The named formula is:

```text
fee_bps = provider_fee_bps(provider, override_tier_bps=flash_loan_fee_bps_override)
flash_fee_usd = borrow_amount_usd * (fee_bps / 10_000)

gas_cost = per_chain_gas_estimate_usd(chain)
if tx_gas_units is not None and tx_gas_units > 0:
    gas_cost = gas_cost * (tx_gas_units / 250_000)

total_slippage_pct = Σ slippage_pct
total_fee_pct      = Σ (fee_bps / 100)          # hop deduction is 0 on this path
gas_drag_pct       = (total_gas_usd + total_extra_cost_usd) / notional_usd * 100
net_after_costs    = gross_spread_pct - total_slippage_pct - total_fee_pct - gas_drag_pct
mev_adjusted_net   = net_after_costs - mev_penalty_pct(mev_risk_level)
atomic_profit_usd  = notional_usd * (mev_adjusted_net / 100)
```

Catalog defaults in `provider_fee_bps`, when no override is stored: `aave_v3` 5 bps, `balancer_v2` 0 bps, `uniswap_v3` 30 bps. `DEFAULT_PER_CHAIN_GAS_USD`: ethereum $8.00, bnb $0.40, arbitrum $0.30, base $0.15, optimism $0.15, polygon $0.05. `DEFAULT_MEV_RISK_FACTORS`: LOW 0.0, MEDIUM 0.5, HIGH 1.5 percentage points. `assess` does not pass custom MEV factors.

The cent-rounded amount inside `verified_outcome` is the stored Gate-7 decision net. Components that are absent on a row stay **UNAVAILABLE / NOT STORED**. They are not filled from this formula.

Workspace and container copies of `economics.py`, `scanners/economics.py`, `verifier.py`, and `strategy_tagging.py` share the same SHA-256.

## Verified population

| Check | Result |
|---|---|
| Gate-7 rows | **256** |
| Distinct `candidate_id` | **256** |
| Other verified outcomes in the same window | **480** `denied:venue_unreadable` (section J). Window verified total **736**. No other outcome prefix |
| Outcome text | all 256 are `denied:gate_rejection:gate_7:atomic_profit $<amount> < floor $25.00` |
| Decision net sign | **256 negative**, **0** at or above $25 |
| Floor parsed from the outcome | **$25.00** on all 256 |
| Decision-net sum / mean / median | **$-80,956.85** / **$-316.2376953125** / **$-250.395** |
| Median definition | even count: mean of the two central sorted decision nets, **$-251.27** and **$-249.52** |
| `opportunity_type` | `FLASH_LOAN_ARBITRAGE` on all 256 |
| `hint_source` | `flash_loan_route_search` on all 256 |
| Asset / `hint_metric.borrow_token` | `USDC` on all 256 |
| Evidence bundles joined | **166** (`source_component = flash_loan_arb_verifier`, one bundle each, zero outcome mismatches) |
| No bundle | **90** (bnb 40, polygon 32, base 15, arbitrum 3) |
| Chain counts | ethereum 40, arbitrum 48, base 48, optimism 40, polygon 40, bnb 40 |

On the 166 bundles, `economics.atomic_profit_usd` equals `economics.expected_net_after_costs_usd`. The largest absolute gap versus the cent-rounded decision net is **$0.004952**.

## A. Strategy

No stored strategy label on any of the 256 candidates or 166 bundles.

| Family | Rows where the stored route satisfies the codebase rule used here | Rule |
|---|---:|---|
| Triangular | **156** | `classify_strategy`: closed `cycle_token_path`, exactly 3 distinct symbols. 57 are `A→B→C→A` (`hop_count` 3). 99 are `A→B→C→B→A` (`hop_count` 4). |
| DEX→DEX | **UNAVAILABLE** | No stored label. `GENERIC_DEX` is the classifier’s residual for the 49 two-hop routes. That name is not DEX→DEX, and the two-hop split is hop count. |
| Multi-hop | **UNAVAILABLE** | `MULTI_HOP` in `classify_strategy` is `legs > 3` after the token-path checks. That is hop count. 51 closed four-token paths (`A→B→C→D→A`) would receive it. They are not counted here. |
| Multi-DEX | **UNAVAILABLE** | No classifier returns this name. A count of names in `route_dex_protocols` would be a DEX-name inference. |
| Cross-pool | **UNAVAILABLE** | No classifier returns this name. `same_dex_fee_tier` is `hop_count == 2` and one DEX name. |
| Cross-protocol | **UNAVAILABLE** | No classifier returns this name. Two protocol names would be a DEX-name inference. The flash-loan provider is not a route protocol. |

Adopted overlap among the six families: none. Only Triangular is adopted. The 99 four-hop three-node routes stay in that one family.

Raw path shapes on all 256 (every path is closed; `len(route_pools) == hop_count`; no repeated pool id):

| Shape | Hop count | Distinct tokens | Rows |
|---|---:|---:|---:|
| `A→B→A` | 2 | 2 | 49 |
| `A→B→C→A` | 3 | 3 | 57 |
| `A→B→C→B→A` | 4 | 3 | 99 |
| `A→B→C→D→A` | 4 | 4 | 51 |

Symbols that appear: USDC, WETH, WBTC, USDT, ARB, AERO, USDC.E, WMATIC, BTCB, WBNB.

`route_hops` and `borrow_amount_wei` are present on all 208 non-Base rows and absent on all 48 Base rows. Where `route_hops` is present, each hop `dex` equals `route_dex_protocols` (mismatches: 0).

Raw `hop_count` and the set of names in `route_dex_protocols`. This is not a strategy class. Nets are cent-rounded decision nets. Median for an even count is the mean of the two central values.

| Hop count | Stored protocol set | Candidates | Bundles | Best Net | Worst Net | Average Net | Median Net |
|---:|---|---:|---:|---:|---:|---:|---:|
| 4 | uniswap_v3 | 50 | 47 | -109.96 | -1690.66 | -287.0412 | -147.4750 |
| 3 | uniswap_v3 | 48 | 30 | -180.92 | -1440.99 | -437.2194 | -381.0250 |
| 2 | uniswap_v3 | 45 | 45 | -83.69 | -286.86 | -195.3564 | -215.2500 |
| 4 | pancakeswap_v3 + uniswap_v3 | 31 | 0 | -152.66 | -381.43 | -292.9648 | -319.5800 |
| 4 | sushiswap_v3 + uniswap_v3 | 21 | 21 | -218.13 | -262.51 | -232.9181 | -224.5200 |
| 4 | sushiswap_v2 + uniswap_v3 | 16 | 16 | -184.13 | -1050.20 | -634.5262 | -756.5750 |
| 4 | quickswap_v3 + uniswap_v3 | 14 | 0 | -327.36 | -883.82 | -409.9071 | -334.1400 |
| 4 | aerodrome + aerodrome_slipstream + uniswap_v3 | 12 | 0 | -225.22 | -380.71 | -309.7433 | -316.2100 |
| 4 | pancakeswap_v3 | 6 | 0 | -151.75 | -155.61 | -154.1667 | -155.0100 |
| 3 | aerodrome + aerodrome_slipstream + uniswap_v3 | 3 | 0 | -128.86 | -158.86 | -140.5133 | -133.8200 |
| 2 | aerodrome + uniswap_v3 | 3 | 3 | -105.52 | -135.52 | -117.1867 | -110.5200 |
| 3 | quickswap_v3 + uniswap_v3 | 2 | 2 | -242.95 | -247.95 | -245.4500 | -245.4500 |
| 3 | sushiswap_v2 + uniswap_v3 | 2 | 2 | -222.14 | -252.13 | -237.1350 | -237.1350 |
| 2 | pancakeswap_v3 + uniswap_v3 | 1 | 0 | -278.24 | -278.24 | -278.2400 | -278.2400 |
| 3 | pancakeswap_v3 | 1 | 0 | -143.80 | -143.80 | -143.8000 | -143.8000 |
| 3 | pancakeswap_v3 + uniswap_v3 | 1 | 0 | -160.68 | -160.68 | -160.6800 | -160.6800 |

One distinct protocol name: **150**. More than one: **106**.

## B. Route

Every Gate-7 row stores `chain`, `candidate_id`, `subject_id`, `verified_at`, `hint_metric.cycle_token_path`, `hint_metric.hop_count`, `hint_metric.route_dex_protocols`, and `hint_metric.route_pools`. Pool ids are composite venue ids (`dex:token:token:fee`), not raw addresses, on all 256. Joined bundles repeat the path, hop count, and protocol list and add `route.route_pool_addresses` and `quotes.hop_legs` (`dex_protocol`, `fee_bps`, `venue_id`).

| Stored route fact | Count |
|---|---:|
| `hop_count` 2 | 49 |
| `hop_count` 3 | 57 |
| `hop_count` 4 | 150 |
| Composite `route_pools` | 256 |
| `route_hops` present | 208 |
| `route_hops` absent (all Base) | 48 |

Two-hop pool ids, from the fee component stored in `route_pools`:

| Rows | Distinct pools | Fee components | Distinct protocol names | Token path |
|---:|---:|---|---:|---|
| 27 | 2 | 500, 3000 | 1 | USDC → WETH → USDC |
| 15 | 2 | 500, 10000 | 1 | USDC → WETH → USDC |
| 3 | 2 | 3000, 500 | 1 | USDC → WETH → USDC |
| 3 | 2 | 500, volatile | 2 | USDC → WETH → USDC |
| 1 | 2 | 500, 3000 | 2 | USDC → BTCB → USDC |

The full route for the best decision-net row is in section I. The best triangular row under the adopted rule is `b82ef23fc763cd1e9f23` (base, `balancer_v2`, `hop_count` 3, USDC → WETH → AERO → USDC, decision net **$-128.86**).

## C. Provider

Provider is taken from `subject_id`, `hint_metric.provider`, and, when a bundle exists, `flash_loan_provider`. Chain defaults were not used.

| Provider | Candidates | Where it is stored |
|---|---:|---|
| `aave_v3` | 120 | subject_id, hint, and bundle when joined (61 bundles) |
| `balancer_v2` | 76 | subject_id, hint, and bundle when joined (56 bundles) |
| `uniswap_v3` | 60 | subject_id, hint, and bundle when joined (49 bundles) |
| Any other provider | 0 | — |

BNB’s 40 rows are all `aave_v3`.

| Field | What is stored |
|---|---|
| Provider | Present on all 256 |
| Asset borrowed | `USDC` on all 256 |
| Borrow USD | `10000.0` on all **166** bundles (`borrow_amount_usd`, `input_amount_usd`, `quote_notional_usd`). **UNAVAILABLE** on **90** |
| Borrow amount (wei) | `quotes.quoted_amount_in_wei` on all **166** (`size_basis = exact`). Hint `borrow_amount_wei` is the discovery probe on non-Base rows and is absent on all 48 Base rows. It was not converted into a quoted size |
| Fee $ | `fees.flash_loan_fee_usd` on all **166**: `aave_v3` **$5.00** (61), `balancer_v2` **$0.00** (56), `uniswap_v3` **$30.00** (49). **UNAVAILABLE** on **90** |
| Fee rate | **UNAVAILABLE as an applied rate.** `fees.flash_loan_fee_bps` is `0` on all 166. That field is the missing quote override coerced to 0. It is not a stored copy of the catalog bps |

## D. Profit

The decision net is the `atomic_profit` amount in `verified_outcome`. Other components are reported only where a field exists.

| Component | Persisted where | Rows |
|---|---|---:|
| Decision net $ | `verified_outcome` | 256 |
| Full-precision net $ | `economics.atomic_profit_usd` = `economics.expected_net_after_costs_usd` | 166 |
| Net % | not on these candidates or bundles | **0 — NOT STORED** |
| Threshold | `$25.00` inside `verified_outcome`; bundle `gates.gate_7` | 256 |
| Decision | Gate 7 **FAIL** on all 256 | 256 |
| Gross spread % | `economics.gross_spread_pct`. `quotes.gross_profit_pct` is present on the same 166. Max absolute difference `4.8e-7` | 166 |
| Gross $ | no field | **0 — UNAVAILABLE** |
| DEX / swap fee $ | no field | **0 — UNAVAILABLE** |
| DEX / swap fee % | `fees.total_swap_fee_pct` | 166 |
| Flash-loan fee $ | `fees.flash_loan_fee_usd` | 166 |
| Gas $ | `gas.gas_cost_usd` | 166 |
| Gas units | `gas.tx_gas_units` | 143 (absent on 23: ethereum 18, base 3, polygon 2) |
| Slippage % | `fees.total_slippage_pct` = `0.0` | 166 |
| Slippage $ | no field | **0 — UNAVAILABLE** |
| `total_fee_pct`, `gas_drag_pct`, `mev_penalty_pct`, `mev_adjusted_net_pct` | computed inside `aggregate_economics` and not copied onto the bundle | **0 — NOT STORED** |

`mev.label` is `MEDIUM` on all 166 bundles. The penalty percent that the formula selects for that label is not stored.

Hop swap fees sit inside the quote gross on this path (`gross_is_quote_inclusive=True`). `total_swap_fee_pct` is telemetry. A separate protocol-fee dollar, other than `flash_loan_fee_usd`, is **UNAVAILABLE**.

## E. Aggregate by strategy family

Nets are cent-rounded decision nets. Only Triangular is established. The other families have no adopted rows, so their nets are **UNAVAILABLE**. The 100 rows outside Triangular stay out of this table.

| Strategy | Candidates | Best Net | Worst Net | Average Net | Median Net |
|---|---:|---:|---:|---:|---:|
| DEX→DEX | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| Triangular | 156 | -128.86 | -1690.66 | -368.8557 | -305.275 |
| Multi-hop | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| Multi-DEX | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| Cross-pool | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| Cross-protocol | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |

Inside the 156, the two stored path shapes:

| Stored path | Also `classify_route` triangular | Candidates | Best Net | Worst Net | Average Net | Median Net |
|---|---|---:|---:|---:|---:|---:|
| `A→B→C→A` | yes (`hop_count` 3) | 57 | -128.86 | -1440.99 | -397.8547 | -356.50 |
| `A→B→C→B→A` | no (`hop_count` 4; that function returns `multi_hop`) | 99 | -136.33 | -1690.66 | -352.1593 | -248.43 |

Triangular rows by chain and by stored provider (decision nets only):

| Chain | Triangular rows | Best | Average | Median |
|---|---:|---:|---:|---:|
| ethereum | 27 | -136.33 | -437.6581 | -252.13 |
| arbitrum | 45 | -136.46 | -191.9936 | -185.92 |
| base | 15 | -128.86 | -275.8973 | -313.54 |
| optimism | 25 | -253.38 | -560.3092 | -356.46 |
| polygon | 26 | -216.94 | -522.6346 | -444.24 |
| bnb | 18 | -143.80 | -297.2400 | -318.605 |

| Provider | Triangular rows | Best | Average | Median |
|---|---:|---:|---:|---:|
| `aave_v3` | 66 | -133.82 | -356.9583 | -317.615 |
| `balancer_v2` | 49 | -128.86 | -383.9171 | -253.38 |
| `uniswap_v3` | 41 | -158.86 | -370.0073 | -252.13 |

## F. Aggregate by recorded provider

Nets are decision nets for every candidate of that provider. Flash-loan fee totals sum `fees.flash_loan_fee_usd` only where that field exists.

| Provider | Candidates | Chains | Best Net | Average Net | Median Net | Flash-loan fee total |
|---|---:|---|---:|---:|---:|---|
| `aave_v3` | 120 | ethereum, arbitrum, base, optimism, polygon, bnb | -88.72 | -297.7523 | -260.69 | **$305.00** over **61 / 120**. **59** have no stored fee |
| `balancer_v2` | 76 | ethereum, arbitrum, base, optimism, polygon | -83.69 | -334.3778 | -228.865 | **$0.00** over **56 / 76**. **20** have no stored fee |
| `uniswap_v3` | 60 | ethereum, arbitrum, base, optimism, polygon | -113.69 | -330.2310 | -250.395 | **$1,470.00** over **49 / 60**. **11** have no stored fee |
| Other | 0 | — | — | — | — | — |

Stored fee dollars sum to **$1,775.00** across **166 / 256** rows.

| Chain | aave_v3 | balancer_v2 | uniswap_v3 |
|---|---:|---:|---:|
| ethereum | 15 | 15 | 10 |
| arbitrum | 16 | 16 | 16 |
| base | 19 | 13 | 16 |
| optimism | 15 | 16 | 9 |
| polygon | 15 | 16 | 9 |
| bnb | 40 | 0 | 0 |

## G. Aggregate by chain

Strategy is Triangular where section A established it, and **UNAVAILABLE** on the other rows of that chain. Best, average, and median use every Gate-7 candidate on the chain. Fee and gas totals use only rows whose bundle stores the field. DEX fee dollars are **UNAVAILABLE** on every chain.

| Chain | Candidates | Triangular / other | Providers | Best Net | Average Net | Median Net | Flash-loan fees | Gas | DEX fees $ |
|---|---:|---|---|---:|---:|---:|---|---|---|
| ETH | 40 | 27 / 13 UNAVAILABLE | aave_v3, balancer_v2, uniswap_v3 | -109.96 | -346.8695 | -166.80 | $375.00 over 40/40 | $420.378560 over 40/40 | UNAVAILABLE (0/40) |
| Arbitrum | 48 | 45 / 3 UNAVAILABLE | aave_v3, balancer_v2, uniswap_v3 | -136.46 | -205.759375 | -214.525 | $525.00 over 45/48 | $35.711004 over 45/48 | UNAVAILABLE (0/48) |
| Base | 48 | 15 / 33 UNAVAILABLE | aave_v3, balancer_v2, uniswap_v3 | -83.69 | -208.75875 | -255.345 | $455.00 over 33/48 | $3.819380 over 33/48 | UNAVAILABLE (0/48) |
| Optimism | 40 | 25 / 15 UNAVAILABLE | aave_v3, balancer_v2, uniswap_v3 | -210.25 | -431.70925 | -349.37 | $345.00 over 40/40 | $25.642904 over 40/40 | UNAVAILABLE (0/40) |
| Polygon | 40 | 26 / 14 UNAVAILABLE | aave_v3, balancer_v2, uniswap_v3 | -216.94 | -483.18 | -440.785 | $75.00 over 8/40 | $1.726551 over 8/40 | UNAVAILABLE (0/40) |
| BNB | 40 | 18 / 22 UNAVAILABLE | aave_v3 | -143.80 | -264.74075 | -305.275 | UNAVAILABLE (0/40) | UNAVAILABLE (0/40) | UNAVAILABLE (0/40) |

Stored `gas.gas_cost_usd` sums to **$487.278399** over **166 / 256** rows.

## H. Completeness

| Measure | Count | Definition used |
|---|---:|---|
| Total Gate-7 rows | **256** | `verified_at` in the half-open window and `verified_outcome` contains `gate_7` |
| Complete economic evidence | **0** | Gross $, gross %, DEX fee $, flash-loan fee $, gas $, slippage $, net $, and net % all stored. Gross $, DEX fee $, slippage $, and net % are absent on every row |
| Partial economic evidence | **166** | Decision net plus a joined bundle that stores gross %, gas $, flash-loan fee $, swap-fee %, and slippage % |
| No joinable evidence | **90** | No `evidence_bundles` document for that `candidate_id`. Decision net, route fields, and provider are still on the candidate |
| Strategy completeness | **156 / 256** Triangular. **100 / 256** with no adopted family. **0 / 256** for each of the other five families | Section A |
| Provider completeness | **256 / 256** | `subject_id` provider equals `hint_metric.provider`. Bundle provider matches on 166/166 joins |
| Gross completeness | gross % **166 / 256**. Gross $ **0 / 256** | Stored fields only |
| Net completeness | decision net $ **256 / 256**. Full-precision net $ **166 / 256**. Net % **0 / 256** | Stored fields only |

## I. Best stored candidate

Highest decision net in the window (least negative). One row.

| Item | Value |
|---|---|
| candidate_id | `7e45d1eea1f28e2ef915` |
| subject_id | `flash_loan:balancer_v2:base:USDC:base:USDC:uniswap_v3:USDC:WETH:500:uniswap_v3:USDC:WETH:3000` |
| verified_at | `2026-10-04T09:09:29.105057Z` |
| Chain | base |
| Route | USDC → WETH → USDC |
| Hop count | 2 |
| DEX / venue | `uniswap_v3` on both hops. Bundle `venue_id` `uniswap_v3:base`, `source_id` `uniswap_v3_quoter_base` |
| Pool ids | `uniswap_v3:USDC:WETH:500`, `uniswap_v3:USDC:WETH:3000` |
| Pool addresses | `0xd0b53D9277642d899DF5C87A3966A349A798F224`, `0x6c561B446416E1A00E8E93E221854d6eA4171372` |
| Strategy | **UNAVAILABLE** among the six families. `classify_strategy` returns `GENERIC_DEX` for this two-hop path. That return is not DEX→DEX, Triangular, Multi-hop, Multi-DEX, Cross-pool, or Cross-protocol |
| Provider | `balancer_v2` (subject_id, hint, and bundle) |
| Asset | USDC |
| Borrow USD | $10,000.00 |
| Borrow amount | `quoted_amount_in_wei` = `10000000000` (`size_basis = exact`). Hint `borrow_amount_wei` is absent on this Base row |
| Gross % | `economics.gross_spread_pct` = `-0.335908`; `quotes.gross_profit_pct` = `-0.335908` |
| Gross $ | **UNAVAILABLE** |
| DEX fees | hop `fee_bps` 5 and 30; `total_swap_fee_pct` = `0.35`. Dollar DEX fee **UNAVAILABLE** |
| Flash-loan fee $ | `0.0` |
| Flash-loan fee rate | stored `flash_loan_fee_bps` = `0`. Applied catalog bps **NOT STORED** |
| Gas $ | `0.100692` (`tx_gas_units` = `167820`) |
| Slippage | `total_slippage_pct` = `0.0`. Slippage $ **UNAVAILABLE** |
| Other costs | MEV label `MEDIUM`, score `48.0`, `is_atomic` true. `mev_penalty_pct` **NOT STORED**. No separate protocol-fee dollar is stored |
| NET (decision) | **$-83.69** |
| NET (full precision) | `economics.atomic_profit_usd` = **$-83.691492** (equal to `expected_net_after_costs_usd`) |
| Net % | **NOT STORED** |
| Threshold | `$25.00` |
| Decision | Gate 7 **FAIL.** `denied:gate_rejection:gate_7:atomic_profit $-83.69 < floor $25.00`. Bundle `gates.gate_7.status` = `FAIL`. Gate 8 and Gate 9 on this bundle are `NOT_EVALUATED` |

## J. venue_unreadable

`denied:venue_unreadable` in the same half-open window: **480** rows (ethereum **448**, base **32**). The stored outcome text is exactly `denied:venue_unreadable` (one distinct value). None of these 480 also contain `gate_7`.

These rows are a quote/venue read denial. They are not failed trades and they are not monetary losses. They are not in the 256 Gate-7 rows, and they are not in the decision-net sum, the provider totals, or the chain totals above.

## Classification

**ECONOMICS_ATTRIBUTION_PARTIAL**

Provider identity is stored for all 256 Gate-7 evaluations. Triangular is established for 156 of them from the stored token path under `classify_strategy`. DEX→DEX, Multi-hop, Multi-DEX, Cross-pool, and Cross-protocol are not established. Gross dollars, DEX fee dollars, slippage dollars, net percent, and the intermediate formula terms are not stored. Full-precision net, gross percent, gas dollars, and flash-loan fee dollars are stored on 166 rows and are absent on 90. That is short of complete attribution.
