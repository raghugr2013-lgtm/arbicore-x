# SHADOW 30-minute Gate-7 profit distribution — 2026-10-04

> **READ-ONLY.** Closed window. SHADOW was not rerun. No code, configuration, RPC, Network Config, deploy, or restart. The $25 Gate-7 floor was not changed.

- **Classification:** **PROFIT_DATA_PARTIAL**
- **Window (half-open):** `verified_at >= 1791103189.7415638` and `verified_at < 1791104989.7415638`
- **Window ISO:** `2026-10-04T08:39:49.741564Z` inclusive through `2026-10-04T09:09:49.741564Z` exclusive
- **Observed verified_at span:** `2026-10-04T08:40:20.457495Z` … `2026-10-04T09:09:46.371853Z`
- **Container:** `arbicore-x-backend-new` (read-only `docker exec` / Mongo queries)
- **Database / collection:** `arbicore_x.arbicore_discovery_candidates`
- **Filter:** `verified_outcome` contains `gate_7`
- **Collected at (UTC):** `2026-10-04T09:46:14.856377Z`

## Classification

**PROFIT_DATA_PARTIAL**

Every one of the 256 Gate-7 rows has a persisted decision value: the `atomic_profit` amount inside `verified_outcome`. That string is the value this report uses for min, max, average, median, percentiles, buckets, best, and worst.

A richer breakdown is persisted on `evidence_bundles` (`source_component = flash_loan_arb_verifier`) for **166 / 256** candidate ids, joined on `source_model_id` = `candidate_id` with `outcome_tag` equal to `verified_outcome` (one bundle each). On those 166 bundles the stored fields are:

- Net: `economics.atomic_profit_usd` and `economics.expected_net_after_costs_usd` (identical on all 166; the decision string is that net rounded to cents; maximum absolute difference vs the decision value is $0.004952)
- Gross: `economics.gross_spread_pct` and `quotes.gross_profit_pct` (equal on all 166 joined bundles). Both are percents.
- Gas: `gas.gas_cost_usd` on all 166. `gas.tx_gas_units` is present on 143 and absent on 23 (ethereum 18, base 3, polygon 2).
- Flash-loan fee USD: `fees.flash_loan_fee_usd` on all 166.
- Other costs: `fees.total_swap_fee_pct` and `fees.total_slippage_pct` on all 166 (percents).
- Borrow notional USD: `economics.borrow_amount_usd`, `input_amount_usd`, and `quotes.quote_notional_usd`, each `10000.0` on all 166.

The other **90** candidate ids have no `evidence_bundles` document with that `source_model_id` (also none under any other `source_component`). Their gross, gas, flash-loan fee, and borrow USD are unavailable. A gross-profit **dollar** amount is not stored on any row. A net profit **percent** is not stored on any row. No profit figure in this report was rebuilt from TVL, quotes, or fee percents.

## Verified counts

| Check | Result |
|---|---|
| Gate-7 rows in the window | **256** |
| Distinct `candidate_id` | **256** |
| Passes (`atomic_profit` at or above $25) | **0** |
| Rejection text | all 256 are `denied:gate_rejection:gate_7:atomic_profit $<amount> < floor $25.00` |
| Floor parsed from the outcome | **$25.00** on all 256 |
| ethereum | 40 |
| arbitrum | 48 |
| base | 48 |
| optimism | 40 |
| polygon | 40 |
| bnb | 40 |
| Asset | USDC on all 256 |
| Evidence bundles joined | **166** |
| Evidence bundles absent | **90** (bnb 40, polygon 32, base 15, arbitrum 3, ethereum 0, optimism 0) |

Chain counts match the prior census. The query, not the prior census, is the source of the figures below.

## 1. Best candidate per chain

Best means the highest Gate-7 decision net (least negative). Ties list every candidate at that exact decision value.

| Chain | Decision net | Gap below $25 | candidate_id | Timestamp (UTC) | Provider | Bundle |
|---|---:|---:|---|---|---|---|
| ETH | -109.96 | 134.96 | `e4b3e6f0f44c0dad8aad` | 2026-10-04T08:40:36.011736Z | balancer_v2 | yes |
| ARB | -136.46 | 161.46 | `07ffe890a06db8eb757a` | 2026-10-04T09:05:40.983186Z | balancer_v2 | yes |
| BASE | -83.69 | 108.69 | `7e45d1eea1f28e2ef915` | 2026-10-04T09:09:29.105057Z | balancer_v2 | yes |
| OP | -210.25 | 235.25 | `436cc31fd43155f73109` | 2026-10-04T09:09:44.659617Z | balancer_v2 | yes |
| OP | -210.25 | 235.25 | `c260303f3e507a31b307` | 2026-10-04T09:06:04.591324Z | balancer_v2 | yes |
| POLYGON | -216.94 | 241.94 | `06ab720ee0173c0e8d09` | 2026-10-04T08:40:49.037263Z | balancer_v2 | yes |
| BNB | -143.80 | 168.80 | `96d2b6a61ee50716873f` | 2026-10-04T08:44:09.890620Z | aave_v3 | no |

### ETH best

**`e4b3e6f0f44c0dad8aad`** at `2026-10-04T08:40:36.011736Z`

- Decision net (parsed from `verified_outcome`): **$-109.96**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-109.96 < floor $25.00`
- Provider: `balancer_v2` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 4 hops USDC→WETH→WBTC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDT:WBTC:500 > uniswap_v3:USDC:USDT:500
- subject_id: `flash_loan:balancer_v2:ethereum:USDC:ethereum:USDC:uniswap_v3:USDC:WETH:500:uniswap_v3:WBTC:WETH:3000:uniswap_v3:USDT:WBTC:500:uniswap_v3:USDC:USDT:500`
- Persisted full-precision `economics.atomic_profit_usd`: $-109.961052 (rounds to the decision value)
- `economics.expected_net_after_costs_usd`: $-109.961052 (stored equal to `atomic_profit_usd`)
- Projected gross: `economics.gross_spread_pct` = -0.475571% ; `quotes.gross_profit_pct` = -0.475571%
- Projected gross USD: unavailable (no gross-profit dollar field on the candidate or the bundle)
- Gas: `gas.gas_cost_usd` = $12.404 ; `gas.tx_gas_units` = 387625
- Flash-loan fee: `fees.flash_loan_fee_usd` = $0.00 ; `fees.flash_loan_fee_bps` = 0
- Other persisted costs: `fees.total_swap_fee_pct` = 0.45% ; `fees.total_slippage_pct` = 0.0%
- Borrow notional: `economics.borrow_amount_usd` = $10000.00 ; `input_amount_usd` = $10000.00 ; `quotes.quote_notional_usd` = $10000.00
- Net profit percent: unavailable (not stored)
- Hint `borrow_amount_wei`: 200000000 (not converted)
- Hint `borrow_amount_provenance`: deterministic_probe
- Hint `estimated_total_fee_pct`: 0.45% (discovery hint percent, not a dollar cost)

### ARB best

**`07ffe890a06db8eb757a`** at `2026-10-04T09:05:40.983186Z`

- Decision net (parsed from `verified_outcome`): **$-136.46**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-136.46 < floor $25.00`
- Provider: `balancer_v2` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000
- subject_id: `flash_loan:balancer_v2:arbitrum:USDC:arbitrum:USDC:uniswap_v3:USDC:WETH:500:uniswap_v3:WBTC:WETH:500:uniswap_v3:WBTC:WETH:3000:uniswap_v3:USDC:WETH:3000`
- Persisted full-precision `economics.atomic_profit_usd`: $-136.462128 (rounds to the decision value)
- `economics.expected_net_after_costs_usd`: $-136.462128 (stored equal to `atomic_profit_usd`)
- Projected gross: `economics.gross_spread_pct` = -0.859695% ; `quotes.gross_profit_pct` = -0.859695%
- Projected gross USD: unavailable (no gross-profit dollar field on the candidate or the bundle)
- Gas: `gas.gas_cost_usd` = $0.4926432 ; `gas.tx_gas_units` = 410536
- Flash-loan fee: `fees.flash_loan_fee_usd` = $0.00 ; `fees.flash_loan_fee_bps` = 0
- Other persisted costs: `fees.total_swap_fee_pct` = 0.7% ; `fees.total_slippage_pct` = 0.0%
- Borrow notional: `economics.borrow_amount_usd` = $10000.00 ; `input_amount_usd` = $10000.00 ; `quotes.quote_notional_usd` = $10000.00
- Net profit percent: unavailable (not stored)
- Hint `borrow_amount_wei`: 200000000 (not converted)
- Hint `borrow_amount_provenance`: deterministic_probe
- Hint `estimated_total_fee_pct`: 0.7% (discovery hint percent, not a dollar cost)

### BASE best

**`7e45d1eea1f28e2ef915`** at `2026-10-04T09:09:29.105057Z`

- Decision net (parsed from `verified_outcome`): **$-83.69**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-83.69 < floor $25.00`
- Provider: `balancer_v2` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000
- subject_id: `flash_loan:balancer_v2:base:USDC:base:USDC:uniswap_v3:USDC:WETH:500:uniswap_v3:USDC:WETH:3000`
- Persisted full-precision `economics.atomic_profit_usd`: $-83.691492 (rounds to the decision value)
- `economics.expected_net_after_costs_usd`: $-83.691492 (stored equal to `atomic_profit_usd`)
- Projected gross: `economics.gross_spread_pct` = -0.335908% ; `quotes.gross_profit_pct` = -0.335908%
- Projected gross USD: unavailable (no gross-profit dollar field on the candidate or the bundle)
- Gas: `gas.gas_cost_usd` = $0.100692 ; `gas.tx_gas_units` = 167820
- Flash-loan fee: `fees.flash_loan_fee_usd` = $0.00 ; `fees.flash_loan_fee_bps` = 0
- Other persisted costs: `fees.total_swap_fee_pct` = 0.35% ; `fees.total_slippage_pct` = 0.0%
- Borrow notional: `economics.borrow_amount_usd` = $10000.00 ; `input_amount_usd` = $10000.00 ; `quotes.quote_notional_usd` = $10000.00
- Net profit percent: unavailable (not stored)
- Hint `borrow_amount_wei`: unavailable (not converted)
- Hint `borrow_amount_provenance`: unavailable
- Hint `estimated_total_fee_pct`: 0.35% (discovery hint percent, not a dollar cost)

### OP best

**`436cc31fd43155f73109`** at `2026-10-04T09:09:44.659617Z`

- Decision net (parsed from `verified_outcome`): **$-210.25**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-210.25 < floor $25.00`
- Provider: `balancer_v2` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000
- subject_id: `flash_loan:balancer_v2:optimism:USDC:optimism:USDC:uniswap_v3:USDC:WETH:500:uniswap_v3:USDC:WETH:3000`
- Persisted full-precision `economics.atomic_profit_usd`: $-210.25246 (rounds to the decision value)
- `economics.expected_net_after_costs_usd`: $-210.25246 (stored equal to `atomic_profit_usd`)
- Projected gross: `economics.gross_spread_pct` = -1.598466% ; `quotes.gross_profit_pct` = -1.598466%
- Projected gross USD: unavailable (no gross-profit dollar field on the candidate or the bundle)
- Gas: `gas.gas_cost_usd` = $0.4058868 ; `gas.tx_gas_units` = 676478
- Flash-loan fee: `fees.flash_loan_fee_usd` = $0.00 ; `fees.flash_loan_fee_bps` = 0
- Other persisted costs: `fees.total_swap_fee_pct` = 0.35% ; `fees.total_slippage_pct` = 0.0%
- Borrow notional: `economics.borrow_amount_usd` = $10000.00 ; `input_amount_usd` = $10000.00 ; `quotes.quote_notional_usd` = $10000.00
- Net profit percent: unavailable (not stored)
- Hint `borrow_amount_wei`: 200000000 (not converted)
- Hint `borrow_amount_provenance`: deterministic_probe
- Hint `estimated_total_fee_pct`: 0.35% (discovery hint percent, not a dollar cost)

**`c260303f3e507a31b307`** at `2026-10-04T09:06:04.591324Z`

- Decision net (parsed from `verified_outcome`): **$-210.25**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-210.25 < floor $25.00`
- Provider: `balancer_v2` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000
- subject_id: `flash_loan:balancer_v2:optimism:USDC:optimism:USDC:uniswap_v3:USDC:WETH:500:uniswap_v3:USDC:WETH:3000`
- Persisted full-precision `economics.atomic_profit_usd`: $-210.25246 (rounds to the decision value)
- `economics.expected_net_after_costs_usd`: $-210.25246 (stored equal to `atomic_profit_usd`)
- Projected gross: `economics.gross_spread_pct` = -1.598466% ; `quotes.gross_profit_pct` = -1.598466%
- Projected gross USD: unavailable (no gross-profit dollar field on the candidate or the bundle)
- Gas: `gas.gas_cost_usd` = $0.4058868 ; `gas.tx_gas_units` = 676478
- Flash-loan fee: `fees.flash_loan_fee_usd` = $0.00 ; `fees.flash_loan_fee_bps` = 0
- Other persisted costs: `fees.total_swap_fee_pct` = 0.35% ; `fees.total_slippage_pct` = 0.0%
- Borrow notional: `economics.borrow_amount_usd` = $10000.00 ; `input_amount_usd` = $10000.00 ; `quotes.quote_notional_usd` = $10000.00
- Net profit percent: unavailable (not stored)
- Hint `borrow_amount_wei`: 200000000 (not converted)
- Hint `borrow_amount_provenance`: deterministic_probe
- Hint `estimated_total_fee_pct`: 0.35% (discovery hint percent, not a dollar cost)

### POLYGON best

**`06ab720ee0173c0e8d09`** at `2026-10-04T08:40:49.037263Z`

- Decision net (parsed from `verified_outcome`): **$-216.94**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-216.94 < floor $25.00`
- Provider: `balancer_v2` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:USDC:WBTC:3000
- subject_id: `flash_loan:balancer_v2:polygon:USDC:polygon:USDC:uniswap_v3:USDC:WETH:500:uniswap_v3:WBTC:WETH:500:uniswap_v3:USDC:WBTC:3000`
- Persisted full-precision `economics.atomic_profit_usd`: $-216.938571 (rounds to the decision value)
- `economics.expected_net_after_costs_usd`: $-216.938571 (stored equal to `atomic_profit_usd`)
- Projected gross: `economics.gross_spread_pct` = -1.66769% ; `quotes.gross_profit_pct` = -1.66769%
- Projected gross USD: unavailable (no gross-profit dollar field on the candidate or the bundle)
- Gas: `gas.gas_cost_usd` = $0.169582 ; `gas.tx_gas_units` = 847910
- Flash-loan fee: `fees.flash_loan_fee_usd` = $0.00 ; `fees.flash_loan_fee_bps` = 0
- Other persisted costs: `fees.total_swap_fee_pct` = 0.4% ; `fees.total_slippage_pct` = 0.0%
- Borrow notional: `economics.borrow_amount_usd` = $10000.00 ; `input_amount_usd` = $10000.00 ; `quotes.quote_notional_usd` = $10000.00
- Net profit percent: unavailable (not stored)
- Hint `borrow_amount_wei`: 200000000 (not converted)
- Hint `borrow_amount_provenance`: deterministic_probe
- Hint `estimated_total_fee_pct`: 0.4% (discovery hint percent, not a dollar cost)

### BNB best

**`96d2b6a61ee50716873f`** at `2026-10-04T08:44:09.890620Z`

- Decision net (parsed from `verified_outcome`): **$-143.80**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-143.80 < floor $25.00`
- Provider: `aave_v3` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 3 hops USDC→BTCB→USDT→USDC [pancakeswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:USDT:500 > pancakeswap_v3:USDC:USDT:500
- subject_id: `flash_loan:aave_v3:bnb:USDC:bnb:USDC:pancakeswap_v3:BTCB:USDC:500:pancakeswap_v3:BTCB:USDT:500:pancakeswap_v3:USDC:USDT:500`
- Evidence bundle: none for this candidate_id. Gross, gas, flash-loan fee, swap-fee percent, slippage percent, and borrow USD are unavailable.
- Net profit percent: unavailable
- Projected gross USD: unavailable
- Hint `borrow_amount_wei`: 50000000000000000 (not converted)
- Hint `borrow_amount_provenance`: deterministic_probe
- Hint `estimated_total_fee_pct`: 0.15% (discovery hint percent, not a dollar cost)

## 2. Worst candidate per chain

Worst means the lowest Gate-7 decision net.

| Chain | Decision net | candidate_id | Timestamp (UTC) | Provider | Bundle |
|---|---:|---|---|---|---|
| ETH | -1050.20 | `c993564a85d1091ab5c9` | 2026-10-04T08:44:03.348918Z | uniswap_v3 | yes |
| ARB | -430.58 | `ccf7f515b0496a7b5d87` | 2026-10-04T08:40:51.784124Z | uniswap_v3 | no |
| BASE | -380.71 | `f4661767f92c48647927` | 2026-10-04T08:40:39.159028Z | uniswap_v3 | no |
| OP | -1690.66 | `37b915af7559d159d549` | 2026-10-04T08:40:36.866573Z | uniswap_v3 | yes |
| POLYGON | -1440.99 | `b599b3c4ce8be4376674` | 2026-10-04T08:44:20.181719Z | uniswap_v3 | yes |
| BNB | -381.43 | `ec87d531c20359e85826` | 2026-10-04T09:09:35.755913Z | aave_v3 | no |

### ETH worst

**`c993564a85d1091ab5c9`** at `2026-10-04T08:44:03.348918Z`

- Decision net (parsed from `verified_outcome`): **$-1050.20**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-1050.20 < floor $25.00`
- Provider: `uniswap_v3` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 4 hops USDC→WETH→USDT→WETH→USDC [uniswap_v3+sushiswap_v2+uniswap_v3+sushiswap_v2] uniswap_v3:USDC:WETH:500 > sushiswap_v2:USDT:WETH:v2 > uniswap_v3:USDT:WETH:500 > sushiswap_v2:USDC:WETH:v2
- subject_id: `flash_loan:uniswap_v3:ethereum:USDC:ethereum:USDC:uniswap_v3:USDC:WETH:500:sushiswap_v2:USDT:WETH:v2:uniswap_v3:USDT:WETH:500:sushiswap_v2:USDC:WETH:v2`
- Persisted full-precision `economics.atomic_profit_usd`: $-1050.196071 (rounds to the decision value)
- `economics.expected_net_after_costs_usd`: $-1050.196071 (stored equal to `atomic_profit_usd`)
- Projected gross: `economics.gross_spread_pct` = -9.621961% ; `quotes.gross_profit_pct` = -9.621961%
- Projected gross USD: unavailable (no gross-profit dollar field on the candidate or the bundle)
- Gas: `gas.gas_cost_usd` = $8.00 ; `gas.tx_gas_units` = unavailable
- Flash-loan fee: `fees.flash_loan_fee_usd` = $30.00 ; `fees.flash_loan_fee_bps` = 0
- Other persisted costs: `fees.total_swap_fee_pct` = 0.7% ; `fees.total_slippage_pct` = 0.0%
- Borrow notional: `economics.borrow_amount_usd` = $10000.00 ; `input_amount_usd` = $10000.00 ; `quotes.quote_notional_usd` = $10000.00
- Net profit percent: unavailable (not stored)
- Hint `borrow_amount_wei`: 200000000 (not converted)
- Hint `borrow_amount_provenance`: deterministic_probe
- Hint `estimated_total_fee_pct`: 0.7% (discovery hint percent, not a dollar cost)

### ARB worst

**`ccf7f515b0496a7b5d87`** at `2026-10-04T08:40:51.784124Z`

- Decision net (parsed from `verified_outcome`): **$-430.58**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-430.58 < floor $25.00`
- Provider: `uniswap_v3` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 4 hops USDC→WETH→WBTC→ARB→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:ARB:WBTC:3000 > uniswap_v3:ARB:USDC:3000
- subject_id: `flash_loan:uniswap_v3:arbitrum:USDC:arbitrum:USDC:uniswap_v3:USDC:WETH:500:uniswap_v3:WBTC:WETH:500:uniswap_v3:ARB:WBTC:3000:uniswap_v3:ARB:USDC:3000`
- Evidence bundle: none for this candidate_id. Gross, gas, flash-loan fee, swap-fee percent, slippage percent, and borrow USD are unavailable.
- Net profit percent: unavailable
- Projected gross USD: unavailable
- Hint `borrow_amount_wei`: 200000000 (not converted)
- Hint `borrow_amount_provenance`: deterministic_probe
- Hint `estimated_total_fee_pct`: 0.7% (discovery hint percent, not a dollar cost)

### BASE worst

**`f4661767f92c48647927`** at `2026-10-04T08:40:39.159028Z`

- Decision net (parsed from `verified_outcome`): **$-380.71**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-380.71 < floor $25.00`
- Provider: `uniswap_v3` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome_slipstream+aerodrome+aerodrome] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:WETH:volatile > aerodrome:USDC:WETH:volatile
- subject_id: `flash_loan:uniswap_v3:base:USDC:base:USDC:uniswap_v3:USDC:WETH:500:aerodrome_slipstream:AERO:WETH:200:aerodrome:AERO:WETH:volatile:aerodrome:USDC:WETH:volatile`
- Evidence bundle: none for this candidate_id. Gross, gas, flash-loan fee, swap-fee percent, slippage percent, and borrow USD are unavailable.
- Net profit percent: unavailable
- Projected gross USD: unavailable
- Hint `borrow_amount_wei`: unavailable (not converted)
- Hint `borrow_amount_provenance`: unavailable
- Hint `estimated_total_fee_pct`: 0.2% (discovery hint percent, not a dollar cost)

### OP worst

**`37b915af7559d159d549`** at `2026-10-04T08:40:36.866573Z`

- Decision net (parsed from `verified_outcome`): **$-1690.66**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-1690.66 < floor $25.00`
- Provider: `uniswap_v3` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 4 hops USDC→WETH→USDC.e→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC.e:WETH:3000 > uniswap_v3:USDC.e:WETH:500 > uniswap_v3:USDC:WETH:3000
- subject_id: `flash_loan:uniswap_v3:optimism:USDC:optimism:USDC:uniswap_v3:USDC:WETH:500:uniswap_v3:USDC.e:WETH:3000:uniswap_v3:USDC.e:WETH:500:uniswap_v3:USDC:WETH:3000`
- Persisted full-precision `economics.atomic_profit_usd`: $-1690.664486 (rounds to the decision value)
- `economics.expected_net_after_costs_usd`: $-1690.664486 (stored equal to `atomic_profit_usd`)
- Projected gross: `economics.gross_spread_pct` = -16.082826% ; `quotes.gross_profit_pct` = -16.082826%
- Projected gross USD: unavailable (no gross-profit dollar field on the candidate or the bundle)
- Gas: `gas.gas_cost_usd` = $2.3818854 ; `gas.tx_gas_units` = 3969809
- Flash-loan fee: `fees.flash_loan_fee_usd` = $30.00 ; `fees.flash_loan_fee_bps` = 0
- Other persisted costs: `fees.total_swap_fee_pct` = 0.7% ; `fees.total_slippage_pct` = 0.0%
- Borrow notional: `economics.borrow_amount_usd` = $10000.00 ; `input_amount_usd` = $10000.00 ; `quotes.quote_notional_usd` = $10000.00
- Net profit percent: unavailable (not stored)
- Hint `borrow_amount_wei`: 200000000 (not converted)
- Hint `borrow_amount_provenance`: deterministic_probe
- Hint `estimated_total_fee_pct`: 0.7% (discovery hint percent, not a dollar cost)

### POLYGON worst

**`b599b3c4ce8be4376674`** at `2026-10-04T08:44:20.181719Z`

- Decision net (parsed from `verified_outcome`): **$-1440.99**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-1440.99 < floor $25.00`
- Provider: `uniswap_v3` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000
- subject_id: `flash_loan:uniswap_v3:polygon:USDC:polygon:USDC:uniswap_v3:USDC:WETH:500:uniswap_v3:WBTC:WETH:3000:uniswap_v3:USDC:WBTC:3000`
- Persisted full-precision `economics.atomic_profit_usd`: $-1440.98641 (rounds to the decision value)
- `economics.expected_net_after_costs_usd`: $-1440.98641 (stored equal to `atomic_profit_usd`)
- Projected gross: `economics.gross_spread_pct` = -13.606138% ; `quotes.gross_profit_pct` = -13.606138%
- Projected gross USD: unavailable (no gross-profit dollar field on the candidate or the bundle)
- Gas: `gas.gas_cost_usd` = $0.3726026 ; `gas.tx_gas_units` = 1863013
- Flash-loan fee: `fees.flash_loan_fee_usd` = $30.00 ; `fees.flash_loan_fee_bps` = 0
- Other persisted costs: `fees.total_swap_fee_pct` = 0.65% ; `fees.total_slippage_pct` = 0.0%
- Borrow notional: `economics.borrow_amount_usd` = $10000.00 ; `input_amount_usd` = $10000.00 ; `quotes.quote_notional_usd` = $10000.00
- Net profit percent: unavailable (not stored)
- Hint `borrow_amount_wei`: 200000000 (not converted)
- Hint `borrow_amount_provenance`: deterministic_probe
- Hint `estimated_total_fee_pct`: 0.65% (discovery hint percent, not a dollar cost)

### BNB worst

**`ec87d531c20359e85826`** at `2026-10-04T09:09:35.755913Z`

- Decision net (parsed from `verified_outcome`): **$-381.43**
- Full rejection reason: `denied:gate_rejection:gate_7:atomic_profit $-381.43 < floor $25.00`
- Provider: `aave_v3` (subject_id provider matches hint; bundle provider matches where a bundle exists)
- Route: 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500
- subject_id: `flash_loan:aave_v3:bnb:USDC:bnb:USDC:pancakeswap_v3:BTCB:USDC:500:pancakeswap_v3:BTCB:WETH:500:uniswap_v3:USDT:WETH:500:pancakeswap_v3:USDC:USDT:500`
- Evidence bundle: none for this candidate_id. Gross, gas, flash-loan fee, swap-fee percent, slippage percent, and borrow USD are unavailable.
- Net profit percent: unavailable
- Projected gross USD: unavailable
- Hint `borrow_amount_wei`: 50000000000000000 (not converted)
- Hint `borrow_amount_provenance`: deterministic_probe
- Hint `estimated_total_fee_pct`: 0.2% (discovery hint percent, not a dollar cost)

## 3. All 256 Gate-7 rows

Sorted by chain (ETH, ARB, BASE, OP, POLYGON, BNB), then decision net descending, then `candidate_id`.

`decision_net_usd` is the `atomic_profit` number parsed from `verified_outcome`. That is the figure Gate 7's rejection text compared with the $25 floor. Cost columns come from the joined evidence bundle. `unavailable` means the field is not stored for that row. `borrow_amount_wei` is the raw hint integer and is not converted to dollars. `hint_estimated_total_fee_pct` is the discovery hint percent, not a verifier dollar cost.

| # | candidate_id | chain | verified_at_utc | decision_net_usd | provider | route | verified_outcome | gross_spread_pct | gas_cost_usd | flash_loan_fee_usd | total_swap_fee_pct | total_slippage_pct | borrow_amount_usd | borrow_amount_wei | hint_estimated_total_fee_pct | evidence_bundle |
|---:|---|---|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | `e4b3e6f0f44c0dad8aad` | ethereum | 2026-10-04T08:40:36.011736Z | -109.96 | balancer_v2 | 4 hops USDC→WETH→WBTC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDT:WBTC:500 > uniswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-109.96 < floor $25.00` | -0.475571 | 12.404 | 0.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 2 | `102d7030622cdded8f0a` | ethereum | 2026-10-04T08:40:27.277721Z | -114.96 | aave_v3 | 4 hops USDC→WETH→WBTC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDT:WBTC:500 > uniswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-114.96 < floor $25.00` | -0.475571 | 12.404 | 5.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 3 | `caac00f636a047bb3850` | ethereum | 2026-10-04T08:48:16.639691Z | -136.33 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-136.33 < floor $25.00` | -0.743489 | 11.977472 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 4 | `6d097cbe8995e6dc34e1` | ethereum | 2026-10-04T08:52:09.328061Z | -136.34 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-136.34 < floor $25.00` | -0.743604 | 11.977472 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 5 | `cab512232e15c91da3e6` | ethereum | 2026-10-04T08:56:37.755808Z | -136.38 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-136.38 < floor $25.00` | -0.744019 | 11.977472 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 6 | `c62e894f0fb6103f2095` | ethereum | 2026-10-04T09:01:16.908289Z | -137.12 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-137.12 < floor $25.00` | -0.751469 | 11.977792 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 7 | `4f787b93a0012d8346ef` | ethereum | 2026-10-04T09:09:44.380967Z | -138.72 | balancer_v2 | 4 hops USDC→WETH→USDT→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDT:WETH:500 > uniswap_v3:USDT:WBTC:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-138.72 < floor $25.00` | -0.755269 | 13.188832 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 8 | `945fef14ccf179a31a74` | ethereum | 2026-10-04T08:40:41.821301Z | -139.96 | uniswap_v3 | 4 hops USDC→WETH→WBTC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDT:WBTC:500 > uniswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-139.96 < floor $25.00` | -0.475571 | 12.404 | 30.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 9 | `6cfdd4749cfa9176b5c4` | ethereum | 2026-10-04T08:51:59.760579Z | -141.06 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-141.06 < floor $25.00` | -0.741144 | 11.947328 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 10 | `d27dd0e45cf17004d16d` | ethereum | 2026-10-04T08:48:09.639220Z | -141.28 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-141.28 < floor $25.00` | -0.742994 | 11.977472 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 11 | `32c11b5540107b4c26d3` | ethereum | 2026-10-04T08:56:28.855479Z | -141.32 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-141.32 < floor $25.00` | -0.743467 | 11.977472 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 12 | `211c7bca25604521b0fb` | ethereum | 2026-10-04T09:01:01.613640Z | -142.16 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-142.16 < floor $25.00` | -0.751808 | 11.977792 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 13 | `511e42160e3621314067` | ethereum | 2026-10-04T09:09:41.560582Z | -143.71 | aave_v3 | 4 hops USDC→WETH→USDT→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDT:WETH:500 > uniswap_v3:USDT:WBTC:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-143.71 < floor $25.00` | -0.755235 | 13.188832 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 14 | `ce140363a44afbe57a07` | ethereum | 2026-10-04T08:40:50.862670Z | -152.17 | balancer_v2 | 4 hops USDC→WETH→WBTC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDT:WBTC:3000 > uniswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-152.17 < floor $25.00` | -0.897626 | 12.404768 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 15 | `0aa98dfbf53536c5c411` | ethereum | 2026-10-04T08:40:47.717764Z | -157.17 | aave_v3 | 4 hops USDC→WETH→WBTC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDT:WBTC:3000 > uniswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-157.17 < floor $25.00` | -0.897626 | 12.404768 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 16 | `1fbc9403b64fd6287a14` | ethereum | 2026-10-04T09:09:31.680611Z | -159.41 | balancer_v2 | 4 hops USDC→WETH→USDT→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDT:WETH:500 > uniswap_v3:USDT:WBTC:3000 > uniswap_v3:USDC:WBTC:500 | `denied:gate_rejection:gate_7:atomic_profit $-159.41 < floor $25.00` | -0.946991 | 14.706944 | 0.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 17 | `aed300e5bb709c294fd7` | ethereum | 2026-10-04T09:09:25.435871Z | -164.55 | aave_v3 | 4 hops USDC→WETH→USDT→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDT:WETH:500 > uniswap_v3:USDT:WBTC:3000 > uniswap_v3:USDC:WBTC:500 | `denied:gate_rejection:gate_7:atomic_profit $-164.55 < floor $25.00` | -0.946579 | 14.894944 | 5.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 18 | `e78347b899e15e148b55` | ethereum | 2026-10-04T08:52:15.992970Z | -166.15 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-166.15 < floor $25.00` | -0.742056 | 11.947328 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 19 | `61449b3bbce08138226a` | ethereum | 2026-10-04T08:48:24.404400Z | -166.33 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-166.33 < floor $25.00` | -0.743489 | 11.977472 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 20 | `2dfc54de979a823c41d8` | ethereum | 2026-10-04T08:56:43.777867Z | -166.42 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-166.42 < floor $25.00` | -0.744383 | 11.977472 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 21 | `b6cf154d4e0af70d2e4d` | ethereum | 2026-10-04T09:01:24.815951Z | -167.18 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-167.18 < floor $25.00` | -0.752028 | 11.977984 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 22 | `baf44719b5e4aac1965b` | ethereum | 2026-10-04T09:05:57.250041Z | -184.13 | balancer_v2 | 4 hops USDC→WETH→WBTC→USDT→USDC [uniswap_v3+sushiswap_v2+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > sushiswap_v2:WBTC:WETH:v2 > uniswap_v3:USDT:WBTC:500 > uniswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-184.13 < floor $25.00` | -1.261277 | 8.00 | 0.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 23 | `7cef42bd597744ed7865` | ethereum | 2026-10-04T09:09:36.831372Z | -189.41 | uniswap_v3 | 4 hops USDC→WETH→USDT→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDT:WETH:500 > uniswap_v3:USDT:WBTC:3000 > uniswap_v3:USDC:WBTC:500 | `denied:gate_rejection:gate_7:atomic_profit $-189.41 < floor $25.00` | -0.946991 | 14.706944 | 30.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 24 | `9dd0b56c2b45310b74c4` | ethereum | 2026-10-04T09:05:50.471499Z | -189.76 | aave_v3 | 4 hops USDC→WETH→WBTC→USDT→USDC [uniswap_v3+sushiswap_v2+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > sushiswap_v2:WBTC:WETH:v2 > uniswap_v3:USDT:WBTC:500 > uniswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-189.76 < floor $25.00` | -1.267616 | 8.00 | 5.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 25 | `5e03addfc0819db2457d` | ethereum | 2026-10-04T09:06:04.085557Z | -214.10 | uniswap_v3 | 4 hops USDC→WETH→WBTC→USDT→USDC [uniswap_v3+sushiswap_v2+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > sushiswap_v2:WBTC:WETH:v2 > uniswap_v3:USDT:WBTC:500 > uniswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-214.10 < floor $25.00` | -1.260996 | 8.00 | 30.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 26 | `e3b45395fa80046e01bf` | ethereum | 2026-10-04T09:05:36.777852Z | -222.14 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+sushiswap_v2+uniswap_v3] uniswap_v3:USDC:WETH:500 > sushiswap_v2:WBTC:WETH:v2 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-222.14 < floor $25.00` | -1.641378 | 8.00 | 0.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 27 | `ee870c09607813b2cc00` | ethereum | 2026-10-04T09:05:43.342011Z | -252.13 | uniswap_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+sushiswap_v2+uniswap_v3] uniswap_v3:USDC:WETH:500 > sushiswap_v2:WBTC:WETH:v2 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-252.13 < floor $25.00` | -1.641319 | 8.00 | 30.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 28 | `66bcd1f7cdb5885c8cc0` | ethereum | 2026-10-04T08:44:18.754750Z | -454.05 | balancer_v2 | 4 hops USDC→WETH→USDT→WETH→USDC [uniswap_v3+sushiswap_v2+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > sushiswap_v2:USDT:WETH:v2 > uniswap_v3:USDT:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-454.05 < floor $25.00` | -3.960535 | 8.00 | 0.00 | 0.95 | 0.0 | 10000.00 | 200000000 | 0.95 | yes |
| 29 | `fb19193e554b8c6d2793` | ethereum | 2026-10-04T08:44:11.099077Z | -459.15 | aave_v3 | 4 hops USDC→WETH→USDT→WETH→USDC [uniswap_v3+sushiswap_v2+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > sushiswap_v2:USDT:WETH:v2 > uniswap_v3:USDT:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-459.15 < floor $25.00` | -3.961451 | 8.00 | 5.00 | 0.95 | 0.0 | 10000.00 | 200000000 | 0.95 | yes |
| 30 | `b93406699d656bf0bd91` | ethereum | 2026-10-04T08:44:26.085544Z | -483.44 | uniswap_v3 | 4 hops USDC→WETH→USDT→WETH→USDC [uniswap_v3+sushiswap_v2+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > sushiswap_v2:USDT:WETH:v2 > uniswap_v3:USDT:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-483.44 < floor $25.00` | -3.954381 | 8.00 | 30.00 | 0.95 | 0.0 | 10000.00 | 200000000 | 0.95 | yes |
| 31 | `d676a6344bce587ffdb2` | ethereum | 2026-10-04T08:48:40.073634Z | -756.21 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v2] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v2:USDC:WETH:v2 | `denied:gate_rejection:gate_7:atomic_profit $-756.21 < floor $25.00` | -6.982083 | 8.00 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 32 | `282b13abf4a1a69b73e2` | ethereum | 2026-10-04T08:56:59.206445Z | -756.56 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v2] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v2:USDC:WETH:v2 | `denied:gate_rejection:gate_7:atomic_profit $-756.56 < floor $25.00` | -6.98556 | 8.00 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 33 | `a0b84ad44b43d026211b` | ethereum | 2026-10-04T08:52:27.617774Z | -756.59 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v2] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v2:USDC:WETH:v2 | `denied:gate_rejection:gate_7:atomic_profit $-756.59 < floor $25.00` | -6.985939 | 8.00 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 34 | `408aba1992e311c94b45` | ethereum | 2026-10-04T09:01:48.080712Z | -757.19 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v2] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v2:USDC:WETH:v2 | `denied:gate_rejection:gate_7:atomic_profit $-757.19 < floor $25.00` | -6.99189 | 8.00 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 35 | `83821c7e571511316c41` | ethereum | 2026-10-04T08:52:21.609856Z | -761.52 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v2] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v2:USDC:WETH:v2 | `denied:gate_rejection:gate_7:atomic_profit $-761.52 < floor $25.00` | -6.985181 | 8.00 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 36 | `05db012b47b4986ddfd2` | ethereum | 2026-10-04T08:56:51.641865Z | -761.56 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v2] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v2:USDC:WETH:v2 | `denied:gate_rejection:gate_7:atomic_profit $-761.56 < floor $25.00` | -6.98556 | 8.00 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 37 | `e86ab10a8e77519f802f` | ethereum | 2026-10-04T08:48:31.697788Z | -761.57 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v2] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v2:USDC:WETH:v2 | `denied:gate_rejection:gate_7:atomic_profit $-761.57 < floor $25.00` | -6.985724 | 8.00 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 38 | `db71021ced3264a763b6` | ethereum | 2026-10-04T09:01:36.797490Z | -762.21 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v2] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v2:USDC:WETH:v2 | `denied:gate_rejection:gate_7:atomic_profit $-762.21 < floor $25.00` | -6.992128 | 8.00 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 39 | `2ae8cd35378e58e8b33a` | ethereum | 2026-10-04T08:44:34.179685Z | -1044.18 | aave_v3 | 4 hops USDC→WETH→USDT→WETH→USDC [uniswap_v3+sushiswap_v2+uniswap_v3+sushiswap_v2] uniswap_v3:USDC:WETH:500 > sushiswap_v2:USDT:WETH:v2 > uniswap_v3:USDT:WETH:3000 > sushiswap_v2:USDC:WETH:v2 | `denied:gate_rejection:gate_7:atomic_profit $-1044.18 < floor $25.00` | -9.81177 | 8.00 | 5.00 | 0.95 | 0.0 | 10000.00 | 200000000 | 0.95 | yes |
| 40 | `c993564a85d1091ab5c9` | ethereum | 2026-10-04T08:44:03.348918Z | -1050.20 | uniswap_v3 | 4 hops USDC→WETH→USDT→WETH→USDC [uniswap_v3+sushiswap_v2+uniswap_v3+sushiswap_v2] uniswap_v3:USDC:WETH:500 > sushiswap_v2:USDT:WETH:v2 > uniswap_v3:USDT:WETH:500 > sushiswap_v2:USDC:WETH:v2 | `denied:gate_rejection:gate_7:atomic_profit $-1050.20 < floor $25.00` | -9.621961 | 8.00 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 41 | `07ffe890a06db8eb757a` | arbitrum | 2026-10-04T09:05:40.983186Z | -136.46 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-136.46 < floor $25.00` | -0.859695 | 0.4926432 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 42 | `e4942eafae73d9fab05f` | arbitrum | 2026-10-04T08:48:13.662319Z | -136.60 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-136.60 < floor $25.00` | -0.860984 | 0.5018868 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 43 | `f43d442b3bcbb5c550a7` | arbitrum | 2026-10-04T08:52:05.847815Z | -137.37 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-137.37 < floor $25.00` | -0.868758 | 0.4915128 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 44 | `5463a0c3e077c12c7fd4` | arbitrum | 2026-10-04T08:56:34.959108Z | -137.41 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-137.41 < floor $25.00` | -0.869145 | 0.4915128 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 45 | `ccab56fb62555840068f` | arbitrum | 2026-10-04T09:09:28.877508Z | -138.01 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-138.01 < floor $25.00` | -0.875109 | 0.5018868 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 46 | `27c78535c6b87e3417ac` | arbitrum | 2026-10-04T09:01:11.816495Z | -138.05 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-138.05 < floor $25.00` | -0.87561 | 0.4925952 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 47 | `362c9ed4d3ba87e5493e` | arbitrum | 2026-10-04T09:05:32.390325Z | -141.46 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-141.46 < floor $25.00` | -0.859695 | 0.4926432 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 48 | `b93a42baa2c36b53dfa3` | arbitrum | 2026-10-04T08:48:05.131926Z | -141.60 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-141.60 < floor $25.00` | -0.860984 | 0.5018868 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 49 | `cf3e0d335ace98700f74` | arbitrum | 2026-10-04T08:51:55.827050Z | -142.37 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-142.37 < floor $25.00` | -0.868758 | 0.4915128 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 50 | `e89927710be570594110` | arbitrum | 2026-10-04T08:56:23.595579Z | -142.41 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-142.41 < floor $25.00` | -0.869145 | 0.4915128 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 51 | `98be764654319184169d` | arbitrum | 2026-10-04T09:09:20.139950Z | -143.01 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-143.01 < floor $25.00` | -0.875109 | 0.5018868 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 52 | `6bae55dd4c28bd81fe5d` | arbitrum | 2026-10-04T09:00:54.311343Z | -143.05 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-143.05 < floor $25.00` | -0.87561 | 0.4925952 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 53 | `7fc6f989808bb2d668db` | arbitrum | 2026-10-04T08:44:08.583982Z | -151.24 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-151.24 < floor $25.00` | -1.007013 | 0.5373048 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 54 | `a58c863f13960aae1d41` | arbitrum | 2026-10-04T08:43:59.565583Z | -156.24 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-156.24 < floor $25.00` | -1.007013 | 0.5373048 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 55 | `a5c65e0ed2adb4c82bd7` | arbitrum | 2026-10-04T09:05:47.440920Z | -166.46 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-166.46 < floor $25.00` | -0.859695 | 0.4926432 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 56 | `6aa1bb6dedd5a12e49cf` | arbitrum | 2026-10-04T08:48:20.668850Z | -166.60 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-166.60 < floor $25.00` | -0.860984 | 0.5018868 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 57 | `c5afd3ad7fcaab4bab2b` | arbitrum | 2026-10-04T08:52:12.117190Z | -167.37 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-167.37 < floor $25.00` | -0.868758 | 0.4915128 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 58 | `e05959f8c3c55a1f9871` | arbitrum | 2026-10-04T08:56:41.103746Z | -167.41 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-167.41 < floor $25.00` | -0.869145 | 0.4915128 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 59 | `0643e1f61f4870f56476` | arbitrum | 2026-10-04T09:01:20.382696Z | -168.06 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-168.06 < floor $25.00` | -0.875722 | 0.4925952 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 60 | `23173ade3f3974ddd278` | arbitrum | 2026-10-04T09:09:34.577201Z | -168.25 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-168.25 < floor $25.00` | -0.877481 | 0.5018868 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 61 | `152921d450d78936f0d9` | arbitrum | 2026-10-04T08:40:32.081314Z | -180.92 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-180.92 < floor $25.00` | -1.304892 | 0.4321656 | 0.00 | 0.4 | 0.0 | 10000.00 | 200000000 | 0.4 | yes |
| 62 | `2175a5e13a0bbe4ca218` | arbitrum | 2026-10-04T08:44:14.839950Z | -181.24 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-181.24 < floor $25.00` | -1.007013 | 0.5373048 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 63 | `716031ecd4aea4bfe041` | arbitrum | 2026-10-04T08:40:20.457495Z | -185.92 | aave_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-185.92 < floor $25.00` | -1.304892 | 0.4321656 | 5.00 | 0.4 | 0.0 | 10000.00 | 200000000 | 0.4 | yes |
| 64 | `e6a514c9151636e516c7` | arbitrum | 2026-10-04T08:40:38.639017Z | -210.92 | uniswap_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-210.92 < floor $25.00` | -1.304892 | 0.4321656 | 30.00 | 0.4 | 0.0 | 10000.00 | 200000000 | 0.4 | yes |
| 65 | `f24d9bf44c7064e9bda2` | arbitrum | 2026-10-04T08:48:34.569239Z | -218.13 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-218.13 < floor $25.00` | -1.669918 | 1.138512 | 0.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 66 | `0fe1d901c981648f15be` | arbitrum | 2026-10-04T08:52:24.607097Z | -218.86 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-218.86 < floor $25.00` | -1.677332 | 1.128138 | 0.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 67 | `97e621d2d9691aeb37bb` | arbitrum | 2026-10-04T08:56:55.810528Z | -218.88 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-218.88 < floor $25.00` | -1.677497 | 1.128138 | 0.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 68 | `2c1ae0e5c17fae022cba` | arbitrum | 2026-10-04T09:01:41.856329Z | -219.49 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-219.49 < floor $25.00` | -1.683627 | 1.1292204 | 0.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 69 | `989f979facdb86f10db8` | arbitrum | 2026-10-04T09:06:00.071635Z | -219.52 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-219.52 < floor $25.00` | -1.683902 | 1.129218 | 0.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 70 | `c3201dab70ada8404376` | arbitrum | 2026-10-04T09:09:43.069373Z | -221.27 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-221.27 < floor $25.00` | -1.70136 | 1.1384616 | 0.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 71 | `f63341ef2b0be1346c24` | arbitrum | 2026-10-04T08:48:29.343747Z | -223.13 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-223.13 < floor $25.00` | -1.669918 | 1.138512 | 5.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 72 | `20216509694ee6225d56` | arbitrum | 2026-10-04T08:52:19.045352Z | -223.86 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-223.86 < floor $25.00` | -1.677332 | 1.128138 | 5.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 73 | `9102e9572b7d8fb7df82` | arbitrum | 2026-10-04T08:56:47.405382Z | -223.88 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-223.88 < floor $25.00` | -1.677497 | 1.128138 | 5.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 74 | `e51553c1759cdb9718d5` | arbitrum | 2026-10-04T09:01:30.981692Z | -224.49 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-224.49 < floor $25.00` | -1.683627 | 1.1292204 | 5.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 75 | `35f57892dcd32ac7b541` | arbitrum | 2026-10-04T09:05:54.289891Z | -224.52 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-224.52 < floor $25.00` | -1.683902 | 1.129218 | 5.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 76 | `4e0dca72e728196976ab` | arbitrum | 2026-10-04T09:09:39.807915Z | -226.27 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-226.27 < floor $25.00` | -1.70136 | 1.1384616 | 5.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 77 | `67f7b46557ded63cf6df` | arbitrum | 2026-10-04T08:44:30.574064Z | -232.51 | balancer_v2 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:WBTC:WETH:500 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-232.51 < floor $25.00` | -1.813315 | 1.17393 | 0.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 78 | `8a1dce2677bb8d8b1715` | arbitrum | 2026-10-04T08:44:21.997659Z | -237.51 | aave_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:WBTC:WETH:500 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-237.51 < floor $25.00` | -1.813315 | 1.17393 | 5.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 79 | `4c5dc58f8deb75ffae82` | arbitrum | 2026-10-04T08:48:42.705929Z | -248.43 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-248.43 < floor $25.00` | -1.672975 | 1.128138 | 30.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 80 | `0907ba46f336cbce9da7` | arbitrum | 2026-10-04T08:52:30.880943Z | -248.86 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-248.86 < floor $25.00` | -1.677332 | 1.128138 | 30.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 81 | `5bd3f9f4927169d3cc28` | arbitrum | 2026-10-04T08:57:03.305426Z | -248.88 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-248.88 < floor $25.00` | -1.677497 | 1.128138 | 30.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 82 | `c3c52b15555720277911` | arbitrum | 2026-10-04T09:01:52.250049Z | -249.49 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-249.49 < floor $25.00` | -1.683627 | 1.1292204 | 30.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 83 | `f0a67eab0ef81e454322` | arbitrum | 2026-10-04T09:06:09.403872Z | -249.52 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-249.52 < floor $25.00` | -1.683902 | 1.129218 | 30.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 84 | `784b959df97942b75e72` | arbitrum | 2026-10-04T09:09:46.023787Z | -251.27 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-251.27 < floor $25.00` | -1.70136 | 1.1384616 | 30.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 85 | `d46b3a6369a6be3396be` | arbitrum | 2026-10-04T08:44:38.723036Z | -262.51 | uniswap_v3 | 4 hops USDC→WETH→WBTC→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+sushiswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:WBTC:WETH:500 > sushiswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-262.51 < floor $25.00` | -1.813315 | 1.17393 | 30.00 | 0.45 | 0.0 | 10000.00 | 200000000 | 0.45 | yes |
| 86 | `91827ae902bb10f457d7` | arbitrum | 2026-10-04T08:40:49.898029Z | -400.58 | balancer_v2 | 4 hops USDC→WETH→WBTC→ARB→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:ARB:WBTC:3000 > uniswap_v3:ARB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-400.58 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.7 | no |
| 87 | `a982fbe2822e5d38751f` | arbitrum | 2026-10-04T08:40:44.803302Z | -405.58 | aave_v3 | 4 hops USDC→WETH→WBTC→ARB→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:ARB:WBTC:3000 > uniswap_v3:ARB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-405.58 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.7 | no |
| 88 | `ccf7f515b0496a7b5d87` | arbitrum | 2026-10-04T08:40:51.784124Z | -430.58 | uniswap_v3 | 4 hops USDC→WETH→WBTC→ARB→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:ARB:WBTC:3000 > uniswap_v3:ARB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-430.58 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.7 | no |
| 89 | `7e45d1eea1f28e2ef915` | base | 2026-10-04T09:09:29.105057Z | -83.69 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-83.69 < floor $25.00` | -0.335908 | 0.100692 | 0.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 90 | `b8b80b0e25d6ca74e770` | base | 2026-10-04T09:05:41.218086Z | -84.08 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-84.08 < floor $25.00` | -0.339826 | 0.100692 | 0.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 91 | `dd18071c4d7202498ea1` | base | 2026-10-04T08:56:35.322853Z | -84.97 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-84.97 < floor $25.00` | -0.348648 | 0.1007316 | 0.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 92 | `714396db9cda99ca91b0` | base | 2026-10-04T09:09:20.625234Z | -88.72 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-88.72 < floor $25.00` | -0.336233 | 0.100692 | 5.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 93 | `2fc7f2b7ac91f44057c9` | base | 2026-10-04T09:05:33.294751Z | -89.08 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-89.08 < floor $25.00` | -0.339839 | 0.100692 | 5.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 94 | `4471a57cd89ec9509755` | base | 2026-10-04T08:48:05.767642Z | -89.18 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-89.18 < floor $25.00` | -0.340771 | 0.1007076 | 5.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 95 | `7e30b6b6b82b9fb97689` | base | 2026-10-04T08:51:56.298034Z | -89.97 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-89.97 < floor $25.00` | -0.348651 | 0.1007316 | 5.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 96 | `dabe7fcb5f028e9c7753` | base | 2026-10-04T08:56:24.326277Z | -89.97 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-89.97 < floor $25.00` | -0.348648 | 0.1007316 | 5.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 97 | `763e3937214759a890a2` | base | 2026-10-04T09:00:55.521721Z | -90.15 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-90.15 < floor $25.00` | -0.350536 | 0.1007316 | 5.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 98 | `b1777e86abffa6de4868` | base | 2026-10-04T08:44:08.922886Z | -105.52 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+aerodrome] uniswap_v3:USDC:WETH:500 > aerodrome:USDC:WETH:volatile | `denied:gate_rejection:gate_7:atomic_profit $-105.52 < floor $25.00` | -0.553677 | 0.15 | 0.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.1 | yes |
| 99 | `dae38c1115841aa96a1b` | base | 2026-10-04T08:43:59.970755Z | -110.52 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+aerodrome] uniswap_v3:USDC:WETH:500 > aerodrome:USDC:WETH:volatile | `denied:gate_rejection:gate_7:atomic_profit $-110.52 < floor $25.00` | -0.553677 | 0.15 | 5.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.1 | yes |
| 100 | `31bfda6457cc7289aef3` | base | 2026-10-04T09:09:34.808852Z | -113.69 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-113.69 < floor $25.00` | -0.335908 | 0.100692 | 30.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 101 | `30fddae50d3034ca03e9` | base | 2026-10-04T09:05:47.825322Z | -114.08 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-114.08 < floor $25.00` | -0.339819 | 0.100692 | 30.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 102 | `c89647e462b7699b1dfd` | base | 2026-10-04T08:48:13.870737Z | -114.18 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-114.18 < floor $25.00` | -0.340771 | 0.1007076 | 30.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 103 | `7c2d69a5b5a74a5b3870` | base | 2026-10-04T08:56:41.373439Z | -114.97 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-114.97 < floor $25.00` | -0.348648 | 0.1007316 | 30.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 104 | `8b33f794990887625c04` | base | 2026-10-04T08:52:06.120325Z | -114.97 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-114.97 < floor $25.00` | -0.348651 | 0.1007316 | 30.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 105 | `8b30cbfb1ff85e40b472` | base | 2026-10-04T09:01:12.971542Z | -115.13 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-115.13 < floor $25.00` | -0.350245 | 0.1007316 | 30.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.35 | yes |
| 106 | `b82ef23fc763cd1e9f23` | base | 2026-10-04T08:40:50.267008Z | -128.86 | balancer_v2 | 3 hops USDC→WETH→AERO→USDC [uniswap_v3+aerodrome_slipstream+aerodrome] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:USDC:volatile | `denied:gate_rejection:gate_7:atomic_profit $-128.86 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.15 | no |
| 107 | `e246a2423944c5be1187` | base | 2026-10-04T08:40:45.317345Z | -133.82 | aave_v3 | 3 hops USDC→WETH→AERO→USDC [uniswap_v3+aerodrome_slipstream+aerodrome] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:USDC:volatile | `denied:gate_rejection:gate_7:atomic_profit $-133.82 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.15 | no |
| 108 | `3959bcf834c946e74f83` | base | 2026-10-04T08:44:15.686302Z | -135.52 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+aerodrome] uniswap_v3:USDC:WETH:500 > aerodrome:USDC:WETH:volatile | `denied:gate_rejection:gate_7:atomic_profit $-135.52 < floor $25.00` | -0.553677 | 0.15 | 30.00 | 0.35 | 0.0 | 10000.00 | unavailable | 0.1 | yes |
| 109 | `89ebddb519b05374d4d2` | base | 2026-10-04T08:40:51.946852Z | -158.86 | uniswap_v3 | 3 hops USDC→WETH→AERO→USDC [uniswap_v3+aerodrome_slipstream+aerodrome] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:USDC:volatile | `denied:gate_rejection:gate_7:atomic_profit $-158.86 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.15 | no |
| 110 | `7848fa587efc87663505` | base | 2026-10-04T08:44:31.232284Z | -225.22 | balancer_v2 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome+aerodrome_slipstream+uniswap_v3] uniswap_v3:USDC:WETH:500 > aerodrome:AERO:WETH:volatile > aerodrome_slipstream:AERO:WETH:200 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-225.22 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.45 | no |
| 111 | `b76f2a0aa9a181fb408d` | base | 2026-10-04T08:44:23.822635Z | -230.22 | aave_v3 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome+aerodrome_slipstream+uniswap_v3] uniswap_v3:USDC:WETH:500 > aerodrome:AERO:WETH:volatile > aerodrome_slipstream:AERO:WETH:200 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-230.22 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.45 | no |
| 112 | `b06b470f908e83f7f0be` | base | 2026-10-04T08:44:39.367875Z | -255.19 | uniswap_v3 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome+aerodrome_slipstream+uniswap_v3] uniswap_v3:USDC:WETH:500 > aerodrome:AERO:WETH:volatile > aerodrome_slipstream:AERO:WETH:200 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-255.19 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.45 | no |
| 113 | `1472079f8c7ca3bdee45` | base | 2026-10-04T09:09:43.081223Z | -255.50 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-255.50 < floor $25.00` | -2.053777 | 0.1238922 | 0.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 114 | `47854ca327d0007e5ec5` | base | 2026-10-04T09:06:00.479662Z | -255.87 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-255.87 < floor $25.00` | -2.057511 | 0.1238922 | 0.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 115 | `b3f2006f7e57fbe68666` | base | 2026-10-04T08:56:56.255383Z | -256.80 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-256.80 < floor $25.00` | -2.066773 | 0.1239318 | 0.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 116 | `7346c4b68e75b3455904` | base | 2026-10-04T09:09:40.163598Z | -260.50 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-260.50 < floor $25.00` | -2.053777 | 0.1238922 | 5.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 117 | `1c5e91c881c775cb0c51` | base | 2026-10-04T09:05:54.882681Z | -260.88 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-260.88 < floor $25.00` | -2.057526 | 0.1238922 | 5.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 118 | `5f780a70e52ff5f47a81` | base | 2026-10-04T08:48:21.412923Z | -260.96 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-260.96 < floor $25.00` | -2.058387 | 0.1239078 | 5.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 119 | `ab1590571a70d518d69a` | base | 2026-10-04T08:52:12.511845Z | -261.73 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-261.73 < floor $25.00` | -2.06606 | 0.1239318 | 5.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 120 | `e15d20e4608eff3469c6` | base | 2026-10-04T08:56:48.079945Z | -261.73 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-261.73 < floor $25.00` | -2.066035 | 0.1239318 | 5.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 121 | `2220dd4dc1c2aa298e24` | base | 2026-10-04T09:01:21.318600Z | -261.88 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-261.88 < floor $25.00` | -2.067599 | 0.1239318 | 5.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 122 | `1d4a773386a007c8a974` | base | 2026-10-04T09:09:46.371853Z | -285.50 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-285.50 < floor $25.00` | -2.053777 | 0.1238922 | 30.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 123 | `b7dd4ce203bed0704aca` | base | 2026-10-04T09:06:09.846119Z | -285.87 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-285.87 < floor $25.00` | -2.057475 | 0.1238922 | 30.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 124 | `2d27d1d98751b5159f3b` | base | 2026-10-04T08:48:29.608984Z | -285.96 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-285.96 < floor $25.00` | -2.058387 | 0.1239078 | 30.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 125 | `4e762ff480e1f4a87d37` | base | 2026-10-04T08:52:19.281031Z | -286.73 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-286.73 < floor $25.00` | -2.06606 | 0.1239318 | 30.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 126 | `f83548da33167bd59e49` | base | 2026-10-04T08:57:03.631797Z | -286.80 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-286.80 < floor $25.00` | -2.066773 | 0.1239318 | 30.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 127 | `3466c910838ba45857cb` | base | 2026-10-04T09:01:31.548282Z | -286.86 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:10000 | `denied:gate_rejection:gate_7:atomic_profit $-286.86 < floor $25.00` | -2.067366 | 0.1239318 | 30.00 | 1.05 | 0.0 | 10000.00 | unavailable | 1.05 | yes |
| 128 | `1323a41f3d52cf91cf01` | base | 2026-10-04T08:48:43.386085Z | -312.47 | balancer_v2 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome_slipstream+aerodrome+uniswap_v3] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:WETH:volatile > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-312.47 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.45 | no |
| 129 | `d0c9f3b48d777869b2e1` | base | 2026-10-04T08:52:32.069870Z | -313.54 | balancer_v2 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome_slipstream+aerodrome+uniswap_v3] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:WETH:volatile > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-313.54 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.45 | no |
| 130 | `f3319e7136582c7d3f3b` | base | 2026-10-04T09:01:52.773619Z | -314.91 | balancer_v2 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome_slipstream+aerodrome+uniswap_v3] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:WETH:volatile > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-314.91 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.45 | no |
| 131 | `d3840a6c3c1e4222e047` | base | 2026-10-04T08:48:35.845782Z | -317.51 | aave_v3 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome_slipstream+aerodrome+uniswap_v3] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:WETH:volatile > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-317.51 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.45 | no |
| 132 | `dd95bf1432147fdc5ec5` | base | 2026-10-04T08:52:25.531492Z | -318.54 | aave_v3 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome_slipstream+aerodrome+uniswap_v3] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:WETH:volatile > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-318.54 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.45 | no |
| 133 | `f1f75b8eff042d8e5484` | base | 2026-10-04T09:01:42.777844Z | -319.91 | aave_v3 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome_slipstream+aerodrome+uniswap_v3] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:WETH:volatile > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-319.91 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.45 | no |
| 134 | `423fd770e9ea35ef3d18` | base | 2026-10-04T08:40:32.566101Z | -361.82 | balancer_v2 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome_slipstream+aerodrome+aerodrome] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:WETH:volatile > aerodrome:USDC:WETH:volatile | `denied:gate_rejection:gate_7:atomic_profit $-361.82 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.2 | no |
| 135 | `717be40dfe348a2137dc` | base | 2026-10-04T08:40:23.224305Z | -366.88 | aave_v3 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome_slipstream+aerodrome+aerodrome] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:WETH:volatile > aerodrome:USDC:WETH:volatile | `denied:gate_rejection:gate_7:atomic_profit $-366.88 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.2 | no |
| 136 | `f4661767f92c48647927` | base | 2026-10-04T08:40:39.159028Z | -380.71 | uniswap_v3 | 4 hops USDC→WETH→AERO→WETH→USDC [uniswap_v3+aerodrome_slipstream+aerodrome+aerodrome] uniswap_v3:USDC:WETH:500 > aerodrome_slipstream:AERO:WETH:200 > aerodrome:AERO:WETH:volatile > aerodrome:USDC:WETH:volatile | `denied:gate_rejection:gate_7:atomic_profit $-380.71 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 0.2 | no |
| 137 | `436cc31fd43155f73109` | optimism | 2026-10-04T09:09:44.659617Z | -210.25 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-210.25 < floor $25.00` | -1.598466 | 0.4058868 | 0.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 138 | `c260303f3e507a31b307` | optimism | 2026-10-04T09:06:04.591324Z | -210.25 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-210.25 < floor $25.00` | -1.598466 | 0.4058868 | 0.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 139 | `f64cf3058c2c80e5b64e` | optimism | 2026-10-04T08:56:59.683353Z | -212.67 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-212.67 < floor $25.00` | -1.622654 | 0.4052976 | 0.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 140 | `f4a5d75c8e376e95e570` | optimism | 2026-10-04T08:52:28.215541Z | -213.64 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-213.64 < floor $25.00` | -1.632342 | 0.4059024 | 0.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 141 | `b25005039f5ae194e64e` | optimism | 2026-10-04T08:48:40.544425Z | -213.76 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-213.76 < floor $25.00` | -1.633627 | 0.4020732 | 0.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 142 | `71165421a4bd4958602e` | optimism | 2026-10-04T09:01:48.638719Z | -214.03 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-214.03 < floor $25.00` | -1.63624 | 0.405912 | 0.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 143 | `369df8a666250fd57201` | optimism | 2026-10-04T09:05:57.821910Z | -215.25 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-215.25 < floor $25.00` | -1.598466 | 0.4058868 | 5.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 144 | `b7e2d548a41038aa9453` | optimism | 2026-10-04T09:09:41.964021Z | -215.25 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-215.25 < floor $25.00` | -1.598466 | 0.4058868 | 5.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 145 | `c363f94d063061c7e0dc` | optimism | 2026-10-04T08:44:11.830906Z | -215.43 | balancer_v2 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:3000 > uniswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-215.43 < floor $25.00` | -1.649539 | 0.4774872 | 0.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 146 | `3397cbc5b94be837e377` | optimism | 2026-10-04T08:56:52.504904Z | -217.67 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-217.67 < floor $25.00` | -1.622654 | 0.4052976 | 5.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 147 | `a506ced82ee382f2c6ad` | optimism | 2026-10-04T08:52:22.255437Z | -218.64 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-218.64 < floor $25.00` | -1.632342 | 0.4059024 | 5.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 148 | `baca5558694ae2a2d77b` | optimism | 2026-10-04T08:48:32.364439Z | -218.91 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-218.91 < floor $25.00` | -1.635028 | 0.405912 | 5.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 149 | `ab8b58ef38973fcea551` | optimism | 2026-10-04T09:01:38.658706Z | -219.03 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-219.03 < floor $25.00` | -1.63624 | 0.405912 | 5.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 150 | `17aa1d98201cd049b432` | optimism | 2026-10-04T08:44:05.199277Z | -220.43 | aave_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:3000 > uniswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-220.43 < floor $25.00` | -1.649539 | 0.4774872 | 5.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 151 | `effb7c1052254a291b76` | optimism | 2026-10-04T08:44:19.358416Z | -245.43 | uniswap_v3 | 2 hops USDC→WETH→USDC [uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:3000 > uniswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-245.43 < floor $25.00` | -1.649539 | 0.4774872 | 30.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 152 | `f594f961b1d9ef1991cb` | optimism | 2026-10-04T08:40:48.326351Z | -253.38 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:3000 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-253.38 < floor $25.00` | -2.031705 | 0.2050236 | 0.00 | 0.9 | 0.0 | 10000.00 | 200000000 | 0.9 | yes |
| 153 | `5ad24df7a4d6edb9083a` | optimism | 2026-10-04T08:40:42.797384Z | -258.38 | aave_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:3000 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-258.38 < floor $25.00` | -2.031705 | 0.2050236 | 5.00 | 0.9 | 0.0 | 10000.00 | 200000000 | 0.9 | yes |
| 154 | `d827e741447d87d6a3d4` | optimism | 2026-10-04T08:40:51.100213Z | -283.38 | uniswap_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:3000 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-283.38 < floor $25.00` | -2.031705 | 0.2050236 | 30.00 | 0.9 | 0.0 | 10000.00 | 200000000 | 0.9 | yes |
| 155 | `16edcf1083366033541c` | optimism | 2026-10-04T09:05:44.051820Z | -348.19 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-348.19 < floor $25.00` | -2.97691 | 0.4949556 | 0.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 156 | `2f12f79727befeb0832a` | optimism | 2026-10-04T09:09:32.375054Z | -348.19 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-348.19 < floor $25.00` | -2.97691 | 0.4949556 | 0.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 157 | `134712d6a189edb8e015` | optimism | 2026-10-04T08:56:38.995706Z | -350.55 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-350.55 < floor $25.00` | -3.000553 | 0.4943664 | 0.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 158 | `e0bda1735709a4a09add` | optimism | 2026-10-04T08:52:10.065322Z | -351.50 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-351.50 < floor $25.00` | -3.010047 | 0.4949712 | 0.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 159 | `59e79bbd139195bc1fd9` | optimism | 2026-10-04T08:48:17.684739Z | -351.76 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-351.76 < floor $25.00` | -3.012671 | 0.4949652 | 0.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 160 | `d3e73d1914a0260a2634` | optimism | 2026-10-04T09:01:17.816714Z | -351.88 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-351.88 < floor $25.00` | -3.013858 | 0.4911324 | 0.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 161 | `22f16c0b435b80fb8039` | optimism | 2026-10-04T09:05:38.769799Z | -353.19 | aave_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-353.19 < floor $25.00` | -2.97691 | 0.4949556 | 5.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 162 | `af1e04b9c3b59699fd9e` | optimism | 2026-10-04T09:09:26.450260Z | -353.19 | aave_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-353.19 < floor $25.00` | -2.97691 | 0.4949556 | 5.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 163 | `b41100d6310861b5803d` | optimism | 2026-10-04T09:01:05.866364Z | -355.79 | aave_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-355.79 < floor $25.00` | -3.002968 | 0.4949712 | 5.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 164 | `06b93961e056b447bcc5` | optimism | 2026-10-04T08:56:31.133971Z | -356.46 | aave_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-356.46 < floor $25.00` | -3.009629 | 0.4949712 | 5.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 165 | `92bf0a65f7e6ba941360` | optimism | 2026-10-04T08:52:01.251574Z | -356.50 | aave_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-356.50 < floor $25.00` | -3.010047 | 0.4949712 | 5.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 166 | `45d58968b2c7204c40dd` | optimism | 2026-10-04T08:48:11.138252Z | -356.76 | aave_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-356.76 < floor $25.00` | -3.012671 | 0.4949652 | 5.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 167 | `cfdefc7a1f2ae305ea6f` | optimism | 2026-10-04T09:09:37.494367Z | -378.19 | uniswap_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-378.19 < floor $25.00` | -2.97691 | 0.4949556 | 30.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 168 | `da1ec563edcf31807f84` | optimism | 2026-10-04T09:05:51.837243Z | -378.19 | uniswap_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-378.19 < floor $25.00` | -2.97691 | 0.4949556 | 30.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 169 | `3447fbde63fe2a6ca9bd` | optimism | 2026-10-04T08:56:45.043286Z | -380.55 | uniswap_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-380.55 < floor $25.00` | -3.000553 | 0.4943664 | 30.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 170 | `4d62dec2e0e753363293` | optimism | 2026-10-04T08:52:16.867086Z | -381.50 | uniswap_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-381.50 < floor $25.00` | -3.010047 | 0.4949712 | 30.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 171 | `8ffb66b224f5d76d3eb9` | optimism | 2026-10-04T08:48:26.409744Z | -381.76 | uniswap_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-381.76 < floor $25.00` | -3.012671 | 0.4949652 | 30.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 172 | `2ab6c71630db2c32075f` | optimism | 2026-10-04T09:01:25.815403Z | -381.88 | uniswap_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-381.88 < floor $25.00` | -3.013858 | 0.4949652 | 30.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 173 | `b68aee79e25c010f1bdf` | optimism | 2026-10-04T08:40:28.435036Z | -1660.66 | balancer_v2 | 4 hops USDC→WETH→USDC.e→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC.e:WETH:3000 > uniswap_v3:USDC.e:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-1660.66 < floor $25.00` | -16.082826 | 2.3818854 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 174 | `e91e9c9533f5caeaaf59` | optimism | 2026-10-04T08:44:35.574490Z | -1670.12 | balancer_v2 | 4 hops USDC→WETH→USDC.e→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:3000 > uniswap_v3:USDC.e:WETH:500 > uniswap_v3:USDC.e:WETH:3000 > uniswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-1670.12 < floor $25.00` | -16.175907 | 2.5307646 | 0.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 175 | `2847f5e318c8e7307921` | optimism | 2026-10-04T08:44:27.654929Z | -1675.12 | aave_v3 | 4 hops USDC→WETH→USDC.e→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:3000 > uniswap_v3:USDC.e:WETH:500 > uniswap_v3:USDC.e:WETH:3000 > uniswap_v3:USDC:WETH:500 | `denied:gate_rejection:gate_7:atomic_profit $-1675.12 < floor $25.00` | -16.175907 | 2.5307646 | 5.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 176 | `37b915af7559d159d549` | optimism | 2026-10-04T08:40:36.866573Z | -1690.66 | uniswap_v3 | 4 hops USDC→WETH→USDC.e→WETH→USDC [uniswap_v3+uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:USDC.e:WETH:3000 > uniswap_v3:USDC.e:WETH:500 > uniswap_v3:USDC:WETH:3000 | `denied:gate_rejection:gate_7:atomic_profit $-1690.66 < floor $25.00` | -16.082826 | 2.3818854 | 30.00 | 0.7 | 0.0 | 10000.00 | 200000000 | 0.7 | yes |
| 177 | `06ab720ee0173c0e8d09` | polygon | 2026-10-04T08:40:49.037263Z | -216.94 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-216.94 < floor $25.00` | -1.66769 | 0.169582 | 0.00 | 0.4 | 0.0 | 10000.00 | 200000000 | 0.4 | yes |
| 178 | `2b31e92169cf278ab13f` | polygon | 2026-10-04T08:40:43.715567Z | -222.61 | aave_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-222.61 < floor $25.00` | -1.674361 | 0.1695788 | 5.00 | 0.4 | 0.0 | 10000.00 | 200000000 | 0.4 | yes |
| 179 | `0076f591cd7b487f7e6e` | polygon | 2026-10-04T08:44:37.034033Z | -242.95 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+quickswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > quickswap_v3:WBTC:WETH:algebra > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-242.95 < floor $25.00` | -1.929018 | 0.05 | 0.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 180 | `c808a7e30defcda7925f` | polygon | 2026-10-04T08:40:51.336838Z | -246.94 | uniswap_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:500 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-246.94 < floor $25.00` | -1.66769 | 0.169582 | 30.00 | 0.4 | 0.0 | 10000.00 | 200000000 | 0.4 | yes |
| 181 | `24665f1ca1903b2e406e` | polygon | 2026-10-04T08:44:28.919361Z | -247.95 | aave_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+quickswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > quickswap_v3:WBTC:WETH:algebra > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-247.95 < floor $25.00` | -1.929018 | 0.05 | 5.00 | 0.35 | 0.0 | 10000.00 | 200000000 | 0.35 | yes |
| 182 | `ec4f63a7a0f1515d09d7` | polygon | 2026-10-04T08:48:41.397036Z | -327.36 | balancer_v2 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-327.36 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 183 | `e72f11eed309df4b7ef3` | polygon | 2026-10-04T08:52:29.314641Z | -327.48 | balancer_v2 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-327.48 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 184 | `242c1d0d2b04b5f5dd8e` | polygon | 2026-10-04T09:09:45.146400Z | -328.06 | balancer_v2 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-328.06 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 185 | `547e4c83f50ce1d87b1d` | polygon | 2026-10-04T09:06:06.132895Z | -331.12 | balancer_v2 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-331.12 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 186 | `2e4c964542964d95145f` | polygon | 2026-10-04T08:48:33.678262Z | -332.36 | aave_v3 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-332.36 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 187 | `29596bd1a17ec1f75043` | polygon | 2026-10-04T08:52:23.494036Z | -332.48 | aave_v3 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-332.48 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 188 | `a4ba141980f30b83d774` | polygon | 2026-10-04T09:09:42.751501Z | -333.06 | aave_v3 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-333.06 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 189 | `3095f7e890cc5112d291` | polygon | 2026-10-04T09:01:49.801895Z | -335.22 | balancer_v2 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-335.22 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 190 | `c47b7719e8565b7a7614` | polygon | 2026-10-04T09:05:59.068942Z | -336.13 | aave_v3 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-336.13 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 191 | `86855a4dfe8e398dba7c` | polygon | 2026-10-04T08:57:01.071319Z | -336.28 | balancer_v2 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-336.28 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 192 | `39f05e492f5962357c45` | polygon | 2026-10-04T09:01:40.558325Z | -340.22 | aave_v3 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-340.22 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 193 | `1dcf67ca9bec4aa336db` | polygon | 2026-10-04T08:56:54.430072Z | -341.29 | aave_v3 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-341.29 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 194 | `057a958fa03d2bf88a48` | polygon | 2026-10-04T08:52:11.011041Z | -438.39 | balancer_v2 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-438.39 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 195 | `9563f5068b763661370e` | polygon | 2026-10-04T09:09:33.708024Z | -438.74 | balancer_v2 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-438.74 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 196 | `3d2cadee6fb36250cc2b` | polygon | 2026-10-04T08:48:18.766543Z | -439.74 | balancer_v2 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-439.74 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 197 | `764e2eca09303548862f` | polygon | 2026-10-04T09:05:45.877791Z | -441.83 | balancer_v2 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-441.83 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 198 | `31756b983ec432228185` | polygon | 2026-10-04T08:56:39.805966Z | -442.38 | balancer_v2 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-442.38 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 199 | `11f8e9b2080a4b1d7c1a` | polygon | 2026-10-04T09:01:18.849607Z | -443.30 | balancer_v2 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-443.30 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 200 | `b143576423a94c5e3a29` | polygon | 2026-10-04T08:52:03.872231Z | -443.39 | aave_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-443.39 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 201 | `c853088f5a49b6c329d0` | polygon | 2026-10-04T09:09:27.851664Z | -443.74 | aave_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-443.74 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 202 | `2a922eac261b79bef9df` | polygon | 2026-10-04T08:48:12.457902Z | -444.74 | aave_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-444.74 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 203 | `0dd5e376750ce1ed220f` | polygon | 2026-10-04T09:05:39.843765Z | -446.83 | aave_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-446.83 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 204 | `869106dd718b1d031d26` | polygon | 2026-10-04T08:56:33.204397Z | -447.38 | aave_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-447.38 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 205 | `c568ae548a5c51f5e35f` | polygon | 2026-10-04T09:01:08.478130Z | -448.30 | aave_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-448.30 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 206 | `15a77329f5b3e1b45dda` | polygon | 2026-10-04T08:52:17.967315Z | -468.40 | uniswap_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-468.40 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 207 | `e6c8ca6e012b90bf1117` | polygon | 2026-10-04T09:09:38.825728Z | -468.73 | uniswap_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-468.73 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 208 | `58870ca0c3bd2ec8b48c` | polygon | 2026-10-04T08:48:27.798790Z | -469.74 | uniswap_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-469.74 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 209 | `affae437b2447d3f0982` | polygon | 2026-10-04T09:05:52.952598Z | -471.83 | uniswap_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-471.83 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 210 | `3a5941436e11931b70f4` | polygon | 2026-10-04T08:56:46.094687Z | -472.38 | uniswap_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-472.38 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 211 | `5d7c35ee5058499c0fb1` | polygon | 2026-10-04T09:01:27.982023Z | -473.30 | uniswap_v3 | 3 hops USDC→WETH→WMATIC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:500 > uniswap_v3:USDC:WMATIC:500 | `denied:gate_rejection:gate_7:atomic_profit $-473.30 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.15 | no |
| 212 | `73236a3664336655e2eb` | polygon | 2026-10-04T08:40:31.396453Z | -853.82 | balancer_v2 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:3000 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-853.82 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.4 | no |
| 213 | `dfed18ef51486c56c081` | polygon | 2026-10-04T08:40:38.016751Z | -883.82 | uniswap_v3 | 4 hops USDC→WETH→WMATIC→USDT→USDC [uniswap_v3+uniswap_v3+uniswap_v3+quickswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WETH:WMATIC:3000 > uniswap_v3:USDT:WMATIC:500 > quickswap_v3:USDC:USDT:algebra | `denied:gate_rejection:gate_7:atomic_profit $-883.82 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 200000000 | 0.4 | no |
| 214 | `9006e25057ef00c5d5e4` | polygon | 2026-10-04T08:44:13.450487Z | -1410.99 | balancer_v2 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-1410.99 < floor $25.00` | -13.606138 | 0.3726026 | 0.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 215 | `046f891fb69f2001ca39` | polygon | 2026-10-04T08:44:06.374869Z | -1415.99 | aave_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-1415.99 < floor $25.00` | -13.606138 | 0.3726026 | 5.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 216 | `b599b3c4ce8be4376674` | polygon | 2026-10-04T08:44:20.181719Z | -1440.99 | uniswap_v3 | 3 hops USDC→WETH→WBTC→USDC [uniswap_v3+uniswap_v3+uniswap_v3] uniswap_v3:USDC:WETH:500 > uniswap_v3:WBTC:WETH:3000 > uniswap_v3:USDC:WBTC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-1440.99 < floor $25.00` | -13.606138 | 0.3726026 | 30.00 | 0.65 | 0.0 | 10000.00 | 200000000 | 0.65 | yes |
| 217 | `96d2b6a61ee50716873f` | bnb | 2026-10-04T08:44:09.890620Z | -143.80 | aave_v3 | 3 hops USDC→BTCB→USDT→USDC [pancakeswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:USDT:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-143.80 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.15 | no |
| 218 | `2889e4239f68444cf963` | bnb | 2026-10-04T09:01:15.884526Z | -151.75 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-151.75 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 219 | `07ade8fd85018b51b288` | bnb | 2026-10-04T09:05:42.546704Z | -152.59 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-152.59 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 220 | `9b59e8f7e1554286bbf0` | bnb | 2026-10-04T08:40:40.095762Z | -152.66 | aave_v3 | 4 hops USDC→BTCB→WBNB→USDT→USDC [pancakeswap_v3+uniswap_v3+uniswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WBNB:500 > uniswap_v3:USDT:WBNB:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-152.66 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 221 | `8789153f2698396081b8` | bnb | 2026-10-04T08:40:33.708907Z | -153.54 | aave_v3 | 4 hops USDC→BTCB→WBNB→USDT→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WBNB:500 > pancakeswap_v3:USDT:WBNB:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-153.54 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 222 | `a427e76c505ced4c73f6` | bnb | 2026-10-04T08:52:07.688017Z | -155.00 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-155.00 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 223 | `507a98a5ab43f0955d90` | bnb | 2026-10-04T08:48:15.341524Z | -155.02 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-155.02 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 224 | `56c330b01e4df893841a` | bnb | 2026-10-04T08:56:36.550061Z | -155.03 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-155.03 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 225 | `3601192fcf57541dc2ca` | bnb | 2026-10-04T09:09:30.097573Z | -155.61 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-155.61 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 226 | `f3d66a4ab718adbc1be7` | bnb | 2026-10-04T08:44:25.004049Z | -160.68 | aave_v3 | 3 hops USDC→BTCB→USDT→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:USDT:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-160.68 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.15 | no |
| 227 | `3914e4b5d85d4cdbb526` | bnb | 2026-10-04T09:01:45.952944Z | -179.34 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-179.34 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.45 | no |
| 228 | `18cb99189af6cab7c9be` | bnb | 2026-10-04T08:48:38.635758Z | -180.03 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-180.03 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.45 | no |
| 229 | `986d7b62129569c3f074` | bnb | 2026-10-04T09:06:02.335269Z | -180.10 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-180.10 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.45 | no |
| 230 | `3487ad51a23e4130f599` | bnb | 2026-10-04T08:52:26.733537Z | -180.50 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-180.50 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.45 | no |
| 231 | `856da8ff577aa254f584` | bnb | 2026-10-04T08:56:57.951107Z | -180.53 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-180.53 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.45 | no |
| 232 | `aeac67a661c0b72c6c9e` | bnb | 2026-10-04T09:09:43.598906Z | -183.11 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-183.11 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.45 | no |
| 233 | `2729a72d0ff3664e98bb` | bnb | 2026-10-04T08:40:50.545731Z | -278.24 | aave_v3 | 2 hops USDC→BTCB→USDC [pancakeswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-278.24 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.35 | no |
| 234 | `63620f7e06820e0e1ca3` | bnb | 2026-10-04T08:40:24.530514Z | -290.80 | aave_v3 | 4 hops USDC→BTCB→WBNB→BTCB→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WBNB:500 > pancakeswap_v3:BTCB:WBNB:500 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-290.80 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.45 | no |
| 235 | `031baca295e78af3f42e` | bnb | 2026-10-04T08:44:32.618238Z | -293.94 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [uniswap_v3+pancakeswap_v3+uniswap_v3+pancakeswap_v3] uniswap_v3:BTCB:USDC:3000 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:BTCB:USDC:500 | `denied:gate_rejection:gate_7:atomic_profit $-293.94 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 236 | `f12c535605914383ff46` | bnb | 2026-10-04T08:44:01.484587Z | -304.96 | aave_v3 | 4 hops USDC→BTCB→USDT→BTCB→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:USDT:500 > uniswap_v3:BTCB:USDT:500 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-304.96 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.45 | no |
| 237 | `cad23048a2d727a6a415` | bnb | 2026-10-04T08:44:17.622914Z | -305.59 | aave_v3 | 4 hops USDC→BTCB→USDT→BTCB→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:USDT:500 > pancakeswap_v3:BTCB:USDT:500 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-305.59 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.45 | no |
| 238 | `fe112ac6764b2fb8833d` | bnb | 2026-10-04T08:48:30.583462Z | -317.13 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-317.13 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 239 | `2092aaf467970da5cec7` | bnb | 2026-10-04T08:52:20.219324Z | -317.60 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-317.60 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 240 | `53df5cf32f481dfd2e56` | bnb | 2026-10-04T08:56:49.016916Z | -317.63 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-317.63 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 241 | `3c80fe80404765492569` | bnb | 2026-10-04T09:01:33.658376Z | -319.58 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-319.58 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 242 | `422fd1b66872c0454151` | bnb | 2026-10-04T09:05:55.977999Z | -319.58 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-319.58 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 243 | `4939e051dd1b5e588750` | bnb | 2026-10-04T09:00:59.206886Z | -321.00 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:WETH:3000 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-321.00 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 244 | `083669f1fcf55033a6c6` | bnb | 2026-10-04T09:05:35.346094Z | -321.08 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:WETH:3000 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-321.08 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 245 | `ab310d121cea2b39f7ec` | bnb | 2026-10-04T09:09:40.997822Z | -322.57 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+uniswap_v3+pancakeswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WETH:3000 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-322.57 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 246 | `c43bd31899c9f98d0216` | bnb | 2026-10-04T08:56:25.651982Z | -323.02 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:WETH:3000 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-323.02 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 247 | `dac8f2e9f3874c864b2f` | bnb | 2026-10-04T08:51:58.114380Z | -323.45 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:WETH:3000 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-323.45 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 248 | `21a34ce12e16fd86f4f1` | bnb | 2026-10-04T08:48:07.837923Z | -323.87 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:WETH:3000 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-323.87 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 249 | `ccfbd05dddac1af89de2` | bnb | 2026-10-04T09:09:22.019986Z | -324.04 | aave_v3 | 4 hops USDC→BTCB→WETH→BTCB→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+uniswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:BTCB:WETH:3000 > uniswap_v3:BTCB:USDC:3000 | `denied:gate_rejection:gate_7:atomic_profit $-324.04 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.7 | no |
| 250 | `545e8d6766e7fe001a30` | bnb | 2026-10-04T09:01:22.961732Z | -375.15 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-375.15 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 251 | `10b05c883194df699eda` | bnb | 2026-10-04T08:52:13.782851Z | -376.81 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-376.81 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 252 | `453304a5f711cc23d58e` | bnb | 2026-10-04T08:40:46.310272Z | -376.83 | aave_v3 | 4 hops USDC→BTCB→WBNB→USDT→USDC [pancakeswap_v3+uniswap_v3+uniswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > uniswap_v3:BTCB:WBNB:500 > uniswap_v3:USDT:WBNB:3000 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-376.83 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.45 | no |
| 253 | `b131473d17d4b76b86dc` | bnb | 2026-10-04T08:56:42.706939Z | -376.84 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-376.84 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 254 | `3fa3eb5e39102ac09ab0` | bnb | 2026-10-04T09:05:49.145797Z | -378.57 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-378.57 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 255 | `a925f599d3e67c4e178e` | bnb | 2026-10-04T08:48:22.805565Z | -380.63 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-380.63 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |
| 256 | `ec87d531c20359e85826` | bnb | 2026-10-04T09:09:35.755913Z | -381.43 | aave_v3 | 4 hops USDC→BTCB→WETH→USDT→USDC [pancakeswap_v3+pancakeswap_v3+uniswap_v3+pancakeswap_v3] pancakeswap_v3:BTCB:USDC:500 > pancakeswap_v3:BTCB:WETH:500 > uniswap_v3:USDT:WETH:500 > pancakeswap_v3:USDC:USDT:500 | `denied:gate_rejection:gate_7:atomic_profit $-381.43 < floor $25.00` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 50000000000000000 | 0.2 | no |

subject_id for each row is `flash_loan:{provider}:{chain}:USDC:{chain}:USDC:` followed by the route pools joined with `:`. The route column lists those pools. Provider on the hint, on `subject_id`, and on the bundle (when present) agree on all 256 rows.

## 4. Buckets

Buckets are half-open on the right, applied to the decision net: `< $0` is below zero; `$0–$5` is `0 <= x < 5`; `$5–$10` is `5 <= x < 10`; and so on through `$20–$24.99` as `20 <= x < 25`. `>= $25` is the pass region.

| Bucket | All | ETH | ARB | BASE | OP | POLYGON | BNB |
|---|---:|---:|---:|---:|---:|---:|---:|
| < $0 | 256 | 40 | 48 | 48 | 40 | 40 | 40 |
| $0–$5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| $5–$10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| $10–$15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| $15–$20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| $20–$24.99 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| >= $25 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **256** | **40** | **48** | **48** | **40** | **40** | **40** |

All 256 decision values fall in `< $0`. Every other bucket, including `>= $25`, is 0 overall and on every chain.

## 5. Overall distribution

Statistics use the 256 parsed decision values (cents). Percentiles use linear interpolation at index `(n-1) * p/100` on the sorted sample (n = 256). Median for an even count is the mean of the two central values.

| Statistic | Decision net (USD) |
|---|---:|
| Count | 256 |
| Min | -1690.66 |
| Max | -83.69 |
| Average | -316.2377 |
| Median | -250.395 |
| Central pair (ranks 128 and 129) | -251.27 and -249.52 |
| P90 | -136.53 |
| P95 | -113.9825 |
| Count negative | 256 |
| Count zero | 0 |
| Count positive and below $25 | 0 |
| Count >= $25 | 0 |
| Count at the closest value (see below) | 1 |

P90 = -136.53 means 90% of decision values are at or below that number. Because every value is negative, P90 and P95 sit toward zero, above the median.

### Closest to the $25 floor

The closest decision value is **$-83.69** on candidate `7e45d1eea1f28e2ef915` (base, balancer_v2, `2026-10-04T09:09:29.105057Z`).
Distance from that decision value up to the $25 floor is **$108.69**.
Candidates sharing that exact decision value: **1**.
Candidates with decision net >= -75 (within $100 of the floor): **0**.
Candidates with decision net >= -100: **9**.
Candidates with decision net >= 0: **0**.
Candidates with decision net >= 25: **0**.

The nine decision values at or above -$100, all on Base:

| decision_net_usd | gap below $25 | candidate_id | provider | timestamp_utc | gross_spread_pct | gas_cost_usd | flash_loan_fee_usd |
|---:|---:|---|---|---|---:|---:|---:|
| -83.69 | 108.69 | `7e45d1eea1f28e2ef915` | balancer_v2 | 2026-10-04T09:09:29.105057Z | -0.335908 | 0.100692 | 0.00 |
| -84.08 | 109.08 | `b8b80b0e25d6ca74e770` | balancer_v2 | 2026-10-04T09:05:41.218086Z | -0.339826 | 0.100692 | 0.00 |
| -84.97 | 109.97 | `dd18071c4d7202498ea1` | balancer_v2 | 2026-10-04T08:56:35.322853Z | -0.348648 | 0.1007316 | 0.00 |
| -88.72 | 113.72 | `714396db9cda99ca91b0` | aave_v3 | 2026-10-04T09:09:20.625234Z | -0.336233 | 0.100692 | 5.00 |
| -89.08 | 114.08 | `2fc7f2b7ac91f44057c9` | aave_v3 | 2026-10-04T09:05:33.294751Z | -0.339839 | 0.100692 | 5.00 |
| -89.18 | 114.18 | `4471a57cd89ec9509755` | aave_v3 | 2026-10-04T08:48:05.767642Z | -0.340771 | 0.1007076 | 5.00 |
| -89.97 | 114.97 | `7e30b6b6b82b9fb97689` | aave_v3 | 2026-10-04T08:51:56.298034Z | -0.348651 | 0.1007316 | 5.00 |
| -89.97 | 114.97 | `dabe7fcb5f028e9c7753` | aave_v3 | 2026-10-04T08:56:24.326277Z | -0.348648 | 0.1007316 | 5.00 |
| -90.15 | 115.15 | `763e3937214759a890a2` | aave_v3 | 2026-10-04T09:00:55.521721Z | -0.350536 | 0.1007316 | 5.00 |

### Full-precision net on the 166 joined bundles

These figures are `economics.atomic_profit_usd` and cover only the 166 rows that have a bundle. They are not a substitute for the 256-row decision-value distribution. BNB is absent from this subset, and most Polygon rows are absent.

| Statistic | atomic_profit_usd |
|---|---:|
| Count | 166 |
| Min | -1690.664486 |
| Max | -83.691492 |
| Average | -307.8924 |
| Median | -218.9693 |
| P90 | -114.9657 |
| P95 | -93.9952 |

On these 166, `expected_net_after_costs_usd` equals `atomic_profit_usd` (166 / 166). Rounded to cents, each matches its `verified_outcome` amount (max abs difference $0.004952).

## 6. Chain comparison

Decision-net statistics, same percentile method as the overall table.

| Chain | n | bundles | min | max | average | median | P90 | P95 | negative | positive < $25 | >= $25 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ETH | 40 | 40 | -1050.20 | -109.96 | -346.8695 | -166.8 | -136.376 | -135.2615 | 40 | 0 | 0 |
| ARB | 48 | 45 | -430.58 | -136.46 | -205.7594 | -214.525 | -138.038 | -137.384 | 48 | 0 | 0 |
| BASE | 48 | 33 | -380.71 | -83.69 | -208.7587 | -255.345 | -89.15 | -86.2825 | 48 | 0 | 0 |
| OP | 40 | 40 | -1690.66 | -210.25 | -431.7092 | -349.37 | -213.748 | -212.549 | 40 | 0 | 0 |
| POLYGON | 40 | 8 | -1440.99 | -216.94 | -483.18 | -440.785 | -247.849 | -241.933 | 40 | 0 | 0 |
| BNB | 40 | 0 | -381.43 | -143.80 | -264.7408 | -305.275 | -153.452 | -152.548 | 40 | 0 | 0 |
| **All** | **256** | **166** | **-1690.66** | **-83.69** | **-316.2377** | **-250.395** | **-136.53** | **-113.9825** | **256** | **0** | **0** |

Best decision net by chain:

| Chain | Best decision net | Distance below $25 |
|---|---:|---:|
| ETH | -109.96 | 134.96 |
| ARB | -136.46 | 161.46 |
| BASE | -83.69 | 108.69 |
| OP | -210.25 | 235.25 |
| POLYGON | -216.94 | 241.94 |
| BNB | -143.80 | 168.80 |

Provider counts (from `hint_metric.provider`, matching `subject_id`):

| Chain | aave_v3 | balancer_v2 | uniswap_v3 |
|---|---:|---:|---:|
| ETH | 15 | 15 | 10 |
| ARB | 16 | 16 | 16 |
| BASE | 19 | 13 | 16 |
| OP | 15 | 16 | 9 |
| POLYGON | 15 | 16 | 9 |
| BNB | 40 | 0 | 0 |
| **All** | **120** | **76** | **60** |

Where a bundle exists, `fees.flash_loan_fee_usd` is $5.00 on all 61 joined aave_v3 rows, $0.00 on all 56 joined balancer_v2 rows, and $30.00 on all 49 joined uniswap_v3 rows. `fees.flash_loan_fee_bps` is 0 on all 166 joined bundles, including the rows whose dollar fee is $5.00 or $30.00. The dollar column is the persisted fee amount. Fee USD was not copied onto the 90 rows that have no bundle.

Joined-bundle gas (`gas.gas_cost_usd`) by chain:

| Chain | bundled n | gas min | gas median | gas max |
|---|---:|---:|---:|---:|
| ETH | 40 | 8.00 | 11.9624 | 14.894944 |
| ARB | 45 | 0.4321656 | 0.5373048 | 1.17393 |
| BASE | 33 | 0.100692 | 0.1238922 | 0.15 |
| OP | 40 | 0.2050236 | 0.4943664 | 2.5307646 |
| POLYGON | 8 | 0.05 | 0.169582 | 0.3726026 |
| BNB | 0 | unavailable | unavailable | unavailable |

Base is the closest chain (best $-83.69, median $-255.345). Arbitrum's best is $-136.46 and its average ($-205.7594) is the highest chain average. Optimism's worst is the window minimum ($-1690.66). Polygon's best is $-216.94. BNB's best is $-143.80 and has no cost bundle. Ethereum's best is $-109.96, with persisted gas $12.404 on that row.

## 7. How close the strategy gets to the $25 gate

It does not reach the floor. The best decision value in the window is **$-83.69**, which is **$108.69 below $25**.

That row is Base candidate `7e45d1eea1f28e2ef915` at `2026-10-04T09:09:29.105057Z`, balancer_v2, 2 hops USDC→WETH→USDC on `uniswap_v3:USDC:WETH:500` and `uniswap_v3:USDC:WETH:3000`. Its joined bundle stores gross spread **-0.335908%**, gas **$0.100692**, flash-loan fee **$0.00**, swap-fee percent **0.35%**, slippage percent **0%**, and borrow **$10000.00**. Full-precision net is **$-83.691492**. Net profit percent and gross profit USD are not stored. The negative decision value sits next to a negative gross-spread percent; the persisted gas and flash-loan fee on this row are $0.100692 and $0.00.

Nine Base rows are at or above -$100, all the same 2-hop USDC/WETH/USDC shape. Their persisted flash-loan fees are $0.00 (balancer_v2), $5.00 (aave_v3), or, just below this band, $30.00 (uniswap_v3). Moving from the best balancer row ($-83.69) to the nearest uniswap_v3 row on this shape ($-113.69, candidate `31bfda6457cc7289aef3`) is a $30.00 difference in the decision value, matching the $30.00 difference in persisted `flash_loan_fee_usd`. That still leaves the zero-fee row $108.69 under the floor.

No chain has a decision value within $100 of $25. The next-best chain is Ethereum at $-109.96 ($134.96 below the floor). BNB's best persisted decision value is $-143.80 ($168.80 below the floor) with no cost breakdown stored. Optimism never gets above $-210.25.

Across all 256 evaluations the median decision net is $-250.395 and the average is $-316.2377. P95 is $-113.9825, so even the upper tail of this window remains more than $100 under the floor (P95 is $138.9825 below $25).

## Evidence join and fields that are not stored

Join key that worked: `evidence_bundles.source_model_id` = `arbicore_discovery_candidates.candidate_id`, `source_component = flash_loan_arb_verifier`, and `outcome_tag` = `verified_outcome`. 166 ids matched exactly one bundle. 90 ids matched zero bundles under `source_model_id` for any `source_component`.

Bundle coverage by chain and verified_at span:

| Chain | with bundle | bundle verified_at span | without bundle | missing verified_at span |
|---|---:|---|---:|---|
| ETH | 40 | 2026-10-04T08:40:27.277721Z … 2026-10-04T09:09:44.380967Z | 0 | none |
| ARB | 45 | 2026-10-04T08:40:20.457495Z … 2026-10-04T09:09:46.023787Z | 3 | 2026-10-04T08:40:44.803302Z … 2026-10-04T08:40:51.784124Z |
| BASE | 33 | 2026-10-04T08:43:59.970755Z … 2026-10-04T09:09:46.371853Z | 15 | 2026-10-04T08:40:23.224305Z … 2026-10-04T09:01:52.773619Z |
| OP | 40 | 2026-10-04T08:40:28.435036Z … 2026-10-04T09:09:44.659617Z | 0 | none |
| POLYGON | 8 | 2026-10-04T08:40:43.715567Z … 2026-10-04T08:44:37.034033Z | 32 | 2026-10-04T08:40:31.396453Z … 2026-10-04T09:09:45.146400Z |
| BNB | 0 | none | 40 | 2026-10-04T08:40:24.530514Z … 2026-10-04T09:09:43.598906Z |

Other collections checked for a joined in-window candidate id (`candidate_id` equality): `arbicore_outcomes`, `arbicore_opportunities`, `arbicore_opportunity_journal`, `mid_opportunities`, `mid_outcomes`, `profit_alerts`, `execution_plans`, and `arbicore_paper_evidence` returned 0 documents. `decision_history` has no usable `candidate_id` lookup within a 4 second bound, so it was not joined. No second profit breakdown was taken from those collections.

Persisted notional fields, reported separately and not converted:

| Chain | hint `borrow_amount_wei` | hint provenance | bundle `borrow_amount_usd` where joined |
|---|---|---|---|
| ETH | 200000000 × 40 | deterministic_probe × 40 | 10000.00 × 40 |
| ARB | 200000000 × 48 | deterministic_probe × 48 | 10000.00 × 45 |
| BASE | absent × 48 | absent × 48 | 10000.00 × 33 |
| OP | 200000000 × 40 | deterministic_probe × 40 | 10000.00 × 40 |
| POLYGON | 200000000 × 40 | deterministic_probe × 40 | 10000.00 × 8 |
| BNB | 50000000000000000 × 40 | deterministic_probe × 40 | unavailable |

On joined rows, hint `estimated_total_fee_pct` equals bundle `fees.total_swap_fee_pct` on **163 / 166**. That hint is still a percent. It is present on all 256 candidates, including the 90 without bundles, and it is not a gas or flash-loan dollar amount.

Slippage percent is 0 on all 166 bundles. Swap-fee percent on those bundles ranges from 0.35 to 1.05. Neither is stored as a dollar amount.

## Method notes

- Population: discovery candidates with `verified_at` in the half-open window and `verified_outcome` containing `gate_7`.
- Decision net regex: `atomic_profit $(-?[0-9.]+) < floor $([0-9.]+)`. All 256 outcomes matched. All floors were 25.00.
- Distribution statistics use that parsed decision net for every row, including rows whose bundle also stores a full-precision `atomic_profit_usd`.
- Best / worst / buckets / percentiles use the same decision net.
- No SHADOW rerun, no threshold edit, no profit reconstructed from TVL, pool fees, or hop quotes.

