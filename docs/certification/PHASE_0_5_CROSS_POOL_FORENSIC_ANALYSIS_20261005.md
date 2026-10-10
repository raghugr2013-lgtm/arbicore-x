# Phase 0.5 Cross-Pool forensic opportunity analysis — 2026-10-05

**Classification: CROSS_POOL_FORENSIC_ANALYSIS_COMPLETE**

Read-only forensic reading of the 27 `CROSS_POOL` Gate-7 records in certification run `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065`. No source file, MongoDB document, configuration, RPC, gate, scanner, SHADOW session, deploy, restart, commit, or push was changed. The Phase 0 classifier ran in memory. Its inputs were not written back.

Every one of the 27 records was examined. Each one is a complete m2.3 bundle. Each stored gross spread is negative. Each stored true net is negative. There is no positive-gross / negative-net row. Stored gas is at most $0.531497 and the stored flash-loan fee is $0.00, $5.00, or $30.00. On every row those two dollar amounts together are smaller than the absolute true net. The stored quotes are already economically negative.

---

## 1. Scope

| | |
|---|---|
| Run | `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065` |
| Certification document | `arbicore_shadow_certifications`, `schema_version=shadow_cert_v1` |
| Window | `2026-10-05T05:27:48.513927+00:00` inclusive through `2026-10-05T05:58:04.231514+00:00` exclusive |
| Certification status | `ABORTED`, fail reason `aborted: real_30min_flash_loan_shadow_complete` |
| Population rule | `arbicore_discovery_candidates` with `verified_at` inside that window and `verified_outcome` containing `gate_7:atomic_profit` |
| Classifier | `observe_strategy_intelligence(bundle, candidate)` |
| Classifier version | `phase0.strategy_intelligence.v1` |
| Image | `arbicore-x-backend:phase0-823a79b` in the already-running `arbicore-x-backend-new` |
| Bundle join | `evidence_bundles.source_model_id = candidate_id`, `schema_version=m2.3`, `source_component=flash_loan_arb_verifier` |
| Certified worker | `flash_loan_arb:0eb9228c` |
| Prior DEX→DEX conclusion used for comparison | `DEPRIORITIZE_DEX_TO_DEX` (`DEX_TO_DEX_FORENSIC_ANALYSIS_COMPLETE`) |

Candidates are not keyed by certification run id. Membership is the certification document’s half-open time window, the same window used for the 288-row ranking. Epoch bounds taken from that document are `1791178068.513927` and `1791179884.231514`.

The same in-memory pass reproduced the ranking’s family counts for the window: `TRIANGULAR` 92, `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` 83, `MULTI_DEX` 34, `CROSS_POOL` 27, `MULTI_HOP` 27, `DEX_TO_DEX` 17, `CROSS_PROTOCOL` 8. Bundle presence on the 288 was `COMPLETE_BUNDLE` 180 and `NO_BUNDLE` 108. Joined bundles in the window were all worker `flash_loan_arb:0eb9228c`.

Gross profit dollars, DEX-fee dollars, slippage dollars, gas price, true-net percent, and total cost are absent from the m2.3 writer. Those fields stay NULL. They were not filled by formula. The live-quote assessor is called with `gross_is_quote_inclusive=True`, so `economics.gross_spread_pct` is the stored round-trip quote percent. `fees.total_swap_fee_pct` is stored telemetry of the observed hop fee rates (`sum of hop fee_bps / 100`). It is not a second stored dollar deduction.

---

## 2. Population validation

| Check | Result |
|---|---|
| `CROSS_POOL` rows | **27** |
| Distinct `candidate_id` | **27** |
| Complete m2.3 (`bundle_presence=COMPLETE_BUNDLE`) | **27 / 27** |
| Decision-only | **0** |
| Bundles per candidate | **1** |
| Worker | `flash_loan_arb:0eb9228c` on all 27 |
| Scanner audit id | `flarb_audit:a89e889be81c` on all 27 |
| Schema / source | `m2.3` / `flash_loan_arb_verifier` on all 27 |
| `verification_status` | `DENIED` on all 27 |
| `broadcast` | `false` on all 27 |
| `opportunity_id` | null on all 27 |
| `provenance` | `REAL` on all 27 |
| `hint_source` | `flash_loan_route_search` on all 27 |
| Classification state | `COMPLETE` on all 27 |
| Strategy completeness | `FULLY_CLASSIFIED` on all 27 |
| Confidence | `HIGH` on all 27 |
| Secondary tags | none on all 27 |
| Family from bundle alone | `CROSS_POOL` on all 27 |
| Family from candidate alone | `CROSS_POOL` on all 27 |
| Rows with `verified_at` outside the certification window | **0** |
| Phase 0 `economics.completeness` | `PARTIAL` on all 27 |
| Calculator version | not stored |

The 27 `verified_at` values run from `2026-10-05T05:29:35.837050+00:00` through `2026-10-05T05:57:58.946959+00:00`, inside the certification window. No other worker’s bundle was joined to these candidates.

### Chain distribution

| Chain | n |
|---|---:|
| Optimism | 14 |
| Base | 13 |
| Ethereum, Arbitrum, Polygon, BNB | 0 |

### Flash-loan provider distribution

Provider is the stored flash-loan provider (`flash_loan_provider`, `hint_metric.provider`, and the provider token inside `subject_id`). Those three agree on all 27. The classifier records the provider and states that it is not a route protocol.

| Provider | n |
|---|---:|
| `aave_v3` | 11 |
| `balancer_v2` | 9 |
| `uniswap_v3` | 7 |

### Route distribution

Family comes from the Phase 0 classifier, not from route shape. The stored route fields that the classifier used are uniform:

| Stored route fact | Value | n |
|---|---|---:|
| Token path | `USDC → WETH → USDC` | 27 |
| Hop count | 2 | 27 |
| Per-leg protocol | `uniswap_v3`, `uniswap_v3` | 27 |
| Distinct pool ids | 2 | 27 |
| Pool order `uniswap_v3:USDC:WETH:500` then `uniswap_v3:USDC:WETH:10000` | Base | 13 |
| Pool order `uniswap_v3:USDC:WETH:500` then `uniswap_v3:USDC:WETH:3000` | Optimism | 11 |
| Pool order `uniswap_v3:USDC:WETH:3000` then `uniswap_v3:USDC:WETH:500` | Optimism | 3 |

Hint path, hint pools, and hint protocols equal the bundle route on all 27. Optimism hints also carry `route_hops` of length 2. Base hints do not. Bundle-only classification is still `CROSS_POOL` on every row.

Classifier evidence, present on every row:

- `cycle_token_path=USDC→WETH→USDC` from `verifier_bundle.route.cycle_token_path`
- `leg[0].protocol=uniswap_v3` and `leg[1].protocol=uniswap_v3` from `quotes.hop_legs[].dex_protocol`
- `distinct_pools=2` from `verifier_bundle.route.route_pools`
- `per_leg_protocols=[uniswap_v3] count=2 distinct=1`
- `path_closed=True distinct_tokens=2`
- `cross_protocol not proven` because the per-leg protocols are not distinct. Venue ids, pool ids, and pool addresses were not parsed as protocols.
- `primary_family=CROSS_POOL` because hop count is 2, the path is a closed 2-token path, every hop has one explicit protocol (`uniswap_v3`), and there are at least two distinct pool ids.
- `secondary_tags=(none)`

### Venue and pool identifiers explicitly stored

Route venue on the hop is `venue_id` `uniswap_v3:base` (13) or `uniswap_v3:optimism` (14). Both hops of a row use that same venue id. Quote `source_id` is `uniswap_v3_quoter_base` or `uniswap_v3_quoter_optimism`, again the same on both hops.

`route_pool_addresses` is stored for both hops on all 27. The writer resolves those strings through `canonical_pool_by_id` in the Base pool registry, with no chain argument. The same three address strings are therefore stored for the symbolic ids on both chains:

| Symbolic pool id | Stored address | Rows |
|---|---|---:|
| `uniswap_v3:USDC:WETH:500` | `0xd0b53D9277642d899DF5C87A3966A349A798F224` | 27 |
| `uniswap_v3:USDC:WETH:10000` | `0x0b1C2DCbBfA744ebD3fC17fF1A96A1E1Eb4B2d69` | 13 |
| `uniswap_v3:USDC:WETH:3000` | `0x6c561B446416E1A00E8E93E221854d6eA4171372` | 14 |

Hop token addresses are chain-specific and are not those pool addresses:

| Chain | USDC `token_in` / `token_out` | WETH |
|---|---|---|
| Base | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | `0x4200000000000000000000000000000000000006` |
| Optimism | `0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85` | `0x4200000000000000000000000000000000000006` |

Quote blocks are also chain-scoped: Base `52194414`–`52195259`, Optimism `157789707`–`157790549`. The symbolic pool id, the hop token addresses, and the block number are the chain-scoped quote identity. The stored `route_pool_addresses` are Base-registry strings on the Optimism rows as well.

---

## 3. Opportunity-by-opportunity table

Sorted by decision net, closest to zero first. Gross spread is stored `economics.gross_spread_pct`. Quote gross is stored `quotes.gross_profit_pct`. They agree in sign on every row. The largest absolute difference is `4.8e-7` percentage points (26 rows); one row is identical (`791ffbb5ab95980437de`).

The following stored fields are NULL on all 27 and are omitted as columns: gross profit dollars, DEX-fee dollars, slippage dollars, gas price, MEV penalty, true-net percent, total cost. Slippage percent is the stored number 0 on all 27. Gate 7 canonical reason on every row is `atomic_profit $<decision net> < floor $25.00`, and that sentence is also the body of `verified_outcome` (`denied:gate_rejection:gate_7:…`) and `outcome_tag`. Attribution is an analysis label only. It is not a stored field and it does not replace the Gate 7 reason.

| # | candidate_id | chain | flash provider | notional | gross spread % | quote gross % | DEX fee % | flash fee $ | gas $ | slippage % | true net $ | decision net $ | Gate 7 | attribution |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | `1c6f7a93b43ebee3128e` | base | `balancer_v2` | 10000.00 | -0.837086 | -0.83708595 | 1.05 | 0.00 | 0.105320 | 0 | -133.813915 | -133.81 | FAIL | NO_GROSS_EDGE |
| 2 | `cffd225d4ad602718b54` | base | `aave_v3` | 10000.00 | -0.83707 | -0.83706967 | 1.05 | 5.00 | 0.105320 | 0 | -138.812287 | -138.81 | FAIL | NO_GROSS_EDGE |
| 3 | `1a073219555cdc12bded` | base | `balancer_v2` | 10000.00 | -1.102075 | -1.10207487 | 1.05 | 0.00 | 0.105921 | 0 | -160.313408 | -160.31 | FAIL | NO_GROSS_EDGE |
| 4 | `1fb392c8321a075af4c8` | base | `uniswap_v3` | 10000.00 | -0.837086 | -0.83708595 | 1.05 | 30.00 | 0.105320 | 0 | -163.813915 | -163.81 | FAIL | NO_GROSS_EDGE |
| 5 | `a3534d5f403ce79336b9` | base | `balancer_v2` | 10000.00 | -1.140015 | -1.14001456 | 1.05 | 0.00 | 0.105897 | 0 | -164.107353 | -164.11 | FAIL | NO_GROSS_EDGE |
| 6 | `7189a46c5c447cce14f0` | base | `aave_v3` | 10000.00 | -1.102075 | -1.10207487 | 1.05 | 5.00 | 0.105921 | 0 | -165.313408 | -165.31 | FAIL | NO_GROSS_EDGE |
| 7 | `3f137ff35c6066db767d` | base | `aave_v3` | 10000.00 | -1.115165 | -1.11516515 | 1.05 | 5.00 | 0.105903 | 0 | -166.622418 | -166.62 | FAIL | NO_GROSS_EDGE |
| 8 | `3aa9ba4a64eadce6faea` | base | `aave_v3` | 10000.00 | -1.121619 | -1.12161902 | 1.05 | 5.00 | 0.102388 | 0 | -167.264290 | -167.26 | FAIL | NO_GROSS_EDGE |
| 9 | `e0874df69498561c41cb` | base | `aave_v3` | 10000.00 | -1.140014 | -1.14001402 | 1.05 | 5.00 | 0.105897 | 0 | -169.107299 | -169.11 | FAIL | NO_GROSS_EDGE |
| 10 | `8e4fbdd5413d44886c5c` | base | `uniswap_v3` | 10000.00 | -1.102075 | -1.10207487 | 1.05 | 30.00 | 0.105921 | 0 | -190.313408 | -190.31 | FAIL | NO_GROSS_EDGE |
| 11 | `a33985f243f1badfe61f` | base | `uniswap_v3` | 10000.00 | -1.115165 | -1.11516515 | 1.05 | 30.00 | 0.105903 | 0 | -191.622418 | -191.62 | FAIL | NO_GROSS_EDGE |
| 12 | `c89a76ede7a450c68a82` | optimism | `balancer_v2` | 10000.00 | -1.417802 | -1.41780223 | 0.35 | 0.00 | 0.405907 | 0 | -192.186130 | -192.19 | FAIL | NO_GROSS_EDGE |
| 13 | `791ffbb5ab95980437de` | base | `uniswap_v3` | 10000.00 | -1.122387 | -1.12238700 | 1.05 | 30.00 | 0.105913 | 0 | -192.344613 | -192.34 | FAIL | NO_GROSS_EDGE |
| 14 | `51af9e80a0f4d94a1bcc` | base | `uniswap_v3` | 10000.00 | -1.13655 | -1.13655033 | 1.05 | 30.00 | 0.102372 | 0 | -193.757405 | -193.76 | FAIL | NO_GROSS_EDGE |
| 15 | `7b4969c598418b21fb72` | optimism | `aave_v3` | 10000.00 | -1.417802 | -1.41780223 | 0.35 | 5.00 | 0.405907 | 0 | -197.186130 | -197.19 | FAIL | NO_GROSS_EDGE |
| 16 | `306269a485f5a83c707e` | optimism | `balancer_v2` | 10000.00 | -1.70049 | -1.70049046 | 0.35 | 0.00 | 0.405374 | 0 | -220.454420 | -220.45 | FAIL | NO_GROSS_EDGE |
| 17 | `4a230930cddc90b68d23` | optimism | `balancer_v2` | 10000.00 | -1.702115 | -1.70211467 | 0.35 | 0.00 | 0.405974 | 0 | -220.617441 | -220.62 | FAIL | NO_GROSS_EDGE |
| 18 | `8db1a158ce004326fa23` | optimism | `balancer_v2` | 10000.00 | -1.713427 | -1.71342727 | 0.35 | 0.00 | 0.405962 | 0 | -221.748689 | -221.75 | FAIL | NO_GROSS_EDGE |
| 19 | `2f4715a684951d684239` | optimism | `balancer_v2` | 10000.00 | -1.715806 | -1.71580648 | 0.35 | 0.00 | 0.405962 | 0 | -221.986610 | -221.99 | FAIL | NO_GROSS_EDGE |
| 20 | `b409ebc98acdc9a58da6` | optimism | `uniswap_v3` | 10000.00 | -1.431684 | -1.43168441 | 0.35 | 30.00 | 0.405922 | 0 | -223.574363 | -223.57 | FAIL | NO_GROSS_EDGE |
| 21 | `4f9aff6dd77ea2865607` | optimism | `aave_v3` | 10000.00 | -1.70049 | -1.70049046 | 0.35 | 5.00 | 0.405374 | 0 | -225.454420 | -225.45 | FAIL | NO_GROSS_EDGE |
| 22 | `116b5b7d14e654715c90` | optimism | `aave_v3` | 10000.00 | -1.702115 | -1.70211467 | 0.35 | 5.00 | 0.405974 | 0 | -225.617441 | -225.62 | FAIL | NO_GROSS_EDGE |
| 23 | `2eb5c84ea1b03acad041` | optimism | `balancer_v2` | 10000.00 | -1.755247 | -1.75524679 | 0.35 | 0.00 | 0.531497 | 0 | -226.056176 | -226.06 | FAIL | NO_GROSS_EDGE |
| 24 | `d79c2c3ad871cb8704e5` | optimism | `aave_v3` | 10000.00 | -1.713427 | -1.71342727 | 0.35 | 5.00 | 0.405962 | 0 | -226.748689 | -226.75 | FAIL | NO_GROSS_EDGE |
| 25 | `1be363dfd051ca55de34` | optimism | `aave_v3` | 10000.00 | -1.715806 | -1.71580648 | 0.35 | 5.00 | 0.405962 | 0 | -226.986610 | -226.99 | FAIL | NO_GROSS_EDGE |
| 26 | `b12fb1855661846d62f5` | optimism | `aave_v3` | 10000.00 | -1.755247 | -1.75524679 | 0.35 | 5.00 | 0.531497 | 0 | -231.056176 | -231.06 | FAIL | NO_GROSS_EDGE |
| 27 | `cacd4da09a9494e99f47` | optimism | `uniswap_v3` | 10000.00 | -1.792158 | -1.79215807 | 0.35 | 30.00 | 0.521026 | 0 | -259.736833 | -259.74 | FAIL | NO_GROSS_EDGE |

Decision-net sum is `-$5,316.61`. Exact decision-net mean is `-$196.911481`. Exact true-net mean is `-$196.911714`. The largest absolute gap between a row’s decision net and its stored `atomic_profit_usd` is `$0.004613`. `atomic_profit_usd` equals `expected_net_after_costs_usd` on every row. Phase 0 reads that stored dollar as true net.

---

## 4. Economics waterfall

Stored on all 27:

| Field | Stored result |
|---|---|
| Notional | `quotes.quote_notional_usd` = `economics.borrow_amount_usd` = `input_amount_usd` = **$10,000.00** |
| Gross spread % | **negative on 27 / 27**. Economics copy from **-0.83707%** to **-1.792158%**, mean **-1.368222%**. Quote copy from **-0.83706967%** to **-1.79215807%**, mean **-1.368222%** |
| Gross profit $ | **NULL** (no m2.3 field) |
| DEX fee % | **0.35** on all 14 Optimism rows; **1.05** on all 13 Base rows. Mean **0.687037** |
| DEX fee $ | **NULL** |
| Flash-loan fee $ | **$0.00** on 9 `balancer_v2` rows, **$5.00** on 11 `aave_v3` rows, **$30.00** on 7 `uniswap_v3` rows. Mean **$9.814815** |
| Flash-loan fee rate | `fees.flash_loan_fee_bps` is the stored override integer **0** on all 27. Applied fee percent is `AVAILABLE_NOT_PERSISTED`. The stored dollar fee is the fee amount that is present |
| Gas $ | **$0.102372** to **$0.531497**, mean **$0.274678** |
| Gas units | **170,620** to **885,828**, mean **457,796** |
| Gas price | **NULL** |
| Slippage % | **0** on all 27 |
| Slippage $ | **NULL** |
| MEV label | `level=MEDIUM`, `label=MEDIUM`, `score=48`, `is_atomic=true`, `bridge=atomic_flashloan`, `asset=USDC`, `notional_usd=10000` on all 27 |
| MEV penalty | `AVAILABLE_NOT_PERSISTED` (NULL) |
| Total cost | **NULL** (no stored total) |
| True net $ | **-133.813915** to **-259.736833**, mean **-196.911714**. All negative |
| Decision net $ | **-133.81** to **-259.74**, mean **-196.911481**, median **-193.76**, P25 **-224.51**, P75 **-166.94** |
| Net % | `AVAILABLE_NOT_PERSISTED` (NULL) |
| Gate 7 | `FAIL` on all 27. Floor **$25.00**. Canonical reason `atomic_profit $<amount> < floor $25.00` |
| Gate 8 | `NOT_EVALUATED`, reason null, on all 27 |
| Gate 9 | `NOT_EVALUATED`, reason null, on all 27 |

Quote binding, stored on all 27: `route_quote_status=ok`, `size_basis=exact`, `exact_size=true`, `quoted_amount_in_wei=10000000000`, `borrow_token=USDC`.

### Primary counts

| | Count |
|---|---:|
| A. Positive gross spread | **0** |
| B. Zero or negative gross spread | **27** (27 negative, 0 zero) |
| C. Positive gross and negative true net | **0** |
| D. Economics-incomplete for this sign question | **0** |

A row is in D only when gross spread or true net is missing, so it cannot be placed in A or B. Both numbers are stored on all 27. Phase 0 still marks `economics.completeness=PARTIAL` on all 27 because gross dollars, DEX-fee dollars, slippage dollars, gas price, applied flash-fee percent, MEV penalty, and true-net percent are absent. That component gap does not leave the sign of the spread or the sign of the net unknown.

Where two or three rows share the same chain, the same pool order, and the same hop wei amounts, their stored gas costs match and their true nets differ by the difference of their stored flash-loan fees. Example: `1c6f7a93b43ebee3128e` (`balancer_v2`, flash `$0.00`, true net `-133.813915`) and `1fb392c8321a075af4c8` (`uniswap_v3`, flash `$30.00`, true net `-163.813915`) are the same Base quote. The net gap is `$30.00`. The shared gross spread is `-0.837086%`. The flash-loan fee is an additive shift on a quote whose stored gross is already negative.

The analytical sum of the two stored dollar costs (gas and flash fee) is at most `$30.521026`. The smallest absolute true net is `$133.813915`. On every row the absolute true net is larger than that sum.

---

## 5. Cross-Pool structure

In these 27 records, `CROSS_POOL` means the classifier’s rule and nothing broader: a closed USDC→WETH→USDC cycle, two hops, the same explicit protocol on both hops (`uniswap_v3`), and two distinct pool ids. Cross-protocol was not proven. Secondary tags are empty. The flash-loan provider is not part of the route classification.

The two pools are two Uniswap V3 fee tiers of the same pair.

| Chain | Ordered pools | Hop `fee_bps` | Stored `total_swap_fee_pct` | n |
|---|---|---|---:|---:|
| Base | 500 then 10000 | 5 then 100 | 1.05 | 13 |
| Optimism | 500 then 3000 | 5 then 30 | 0.35 | 11 |
| Optimism | 3000 then 500 | 30 then 5 | 0.35 | 3 |

`fee_bps` on the hop matches the fee integer in the pool id divided by 100 (500→5, 3000→30, 10000→100). That is the stored pair of fields. `total_swap_fee_pct` equals the sum of those hop `fee_bps` values divided by 100.

There are **17** distinct round trips by chain, pool order, and hop wei amounts. The other 10 rows are the same wei quote stored again under a second or third flash-loan provider.

Both legs have `status=ok`. Hop `price` is stored null on all 54 legs. `amount_out_wei` of leg 1 equals `amount_in_wei` of leg 2 on all 27, so the stored legs are one continuous quote.

---

## 6. Price-path analysis

Ordered legs are the two stored hops. Token symbols are the stored path. Token addresses are the stored hop fields in section 2. Protocol on every leg is `uniswap_v3`. Quote source is the hop `source_id`. Fee, block, depth, and wei amounts are the stored hop fields. Depth dollars in the table are the stored `depth_usd` rounded to the cent for display. Exact ranges are in section 8.

USDC in wei is `10000000000` on every first hop. USDC out wei is the second hop’s `amount_out_wei`. On every row the final USDC wei is smaller than the starting USDC wei, on the same token address. That is the stored round trip. The stored quote gross percent is the persisted expression of it. No per-pool price was reconstructed. Hop `price` remains null, so the bundle does not contain two pool prices that could be subtracted.

| # | candidate_id | path | pool A | pool B | fee bps | blocks | depth A $ | depth B $ | USDC in wei | WETH mid wei | USDC out wei | source |
|---:|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|
| 1 | `1c6f7a93b43ebee3128e` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52194417/52194417 | 10011622.68 | 771663.44 | 10000000000 | 3706458413589364817 | 9916291405 | `uniswap_v3_quoter_base` |
| 2 | `cffd225d4ad602718b54` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52194414/52194414 | 10011622.68 | 771663.44 | 10000000000 | 3706459024252858369 | 9916293033 | `uniswap_v3_quoter_base` |
| 3 | `1a073219555cdc12bded` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52195052/52195052 | 10026740.12 | 772158.40 | 10000000000 | 3696519913124856811 | 9889792513 | `uniswap_v3_quoter_base` |
| 4 | `1fb392c8321a075af4c8` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52194417/52194417 | 10011622.68 | 771663.44 | 10000000000 | 3706458413589364817 | 9916291405 | `uniswap_v3_quoter_base` |
| 5 | `a3534d5f403ce79336b9` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52194951/52194951 | 10028722.86 | 772229.53 | 10000000000 | 3695096987048292075 | 9885998544 | `uniswap_v3_quoter_base` |
| 6 | `7189a46c5c447cce14f0` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52195047/52195047 | 10026740.12 | 772158.40 | 10000000000 | 3696519913124856811 | 9889792513 | `uniswap_v3_quoter_base` |
| 7 | `3f137ff35c6066db767d` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52195149/52195149 | 10027430.19 | 772182.94 | 10000000000 | 3696028962441160623 | 9888483485 | `uniswap_v3_quoter_base` |
| 8 | `3aa9ba4a64eadce6faea` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52195254/52195254 | 10027770.23 | 772195.04 | 10000000000 | 3695786910409939307 | 9887838098 | `uniswap_v3_quoter_base` |
| 9 | `e0874df69498561c41cb` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52194946/52194946 | 10028722.86 | 772229.53 | 10000000000 | 3695097007268208029 | 9885998598 | `uniswap_v3_quoter_base` |
| 10 | `8e4fbdd5413d44886c5c` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52195052/52195052 | 10026740.12 | 772158.40 | 10000000000 | 3696519913124856811 | 9889792513 | `uniswap_v3_quoter_base` |
| 11 | `a33985f243f1badfe61f` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52195153/52195153 | 10027430.19 | 772182.94 | 10000000000 | 3696028962441160623 | 9888483485 | `uniswap_v3_quoter_base` |
| 12 | `c89a76ede7a450c68a82` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:3000` | 5/30 | 157789707/157789708 | 295858.54 | 5650841.95 | 10000000000 | 3659470677596315558 | 9858219777 | `uniswap_v3_quoter_optimism` |
| 13 | `791ffbb5ab95980437de` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52195259/52195259 | 10027770.23 | 772195.04 | 10000000000 | 3695758107073936367 | 9887761300 | `uniswap_v3_quoter_base` |
| 14 | `51af9e80a0f4d94a1bcc` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:10000` | 5/100 | 52194953/52194953 | 10028722.86 | 772229.53 | 10000000000 | 3695226912605697143 | 9886344967 | `uniswap_v3_quoter_base` |
| 15 | `7b4969c598418b21fb72` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:3000` | 5/30 | 157789707/157789708 | 295858.54 | 5650841.95 | 10000000000 | 3659470677596315558 | 9858219777 | `uniswap_v3_quoter_optimism` |
| 16 | `306269a485f5a83c707e` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:3000` | 5/30 | 157790346/157790346 | 296446.13 | 5657537.27 | 10000000000 | 3649566217845318402 | 9829950954 | `uniswap_v3_quoter_optimism` |
| 17 | `4a230930cddc90b68d23` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:3000` | 5/30 | 157790443/157790443 | 296449.63 | 5657577.34 | 10000000000 | 3649505905399886944 | 9829788533 | `uniswap_v3_quoter_optimism` |
| 18 | `8db1a158ce004326fa23` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:3000` | 5/30 | 157790244/157790244 | 296505.50 | 5657856.09 | 10000000000 | 3649085832439136647 | 9828657273 | `uniswap_v3_quoter_optimism` |
| 19 | `2f4715a684951d684239` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:3000` | 5/30 | 157790549/157790549 | 296449.63 | 5657914.63 | 10000000000 | 3648997484938030140 | 9828419352 | `uniswap_v3_quoter_optimism` |
| 20 | `b409ebc98acdc9a58da6` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:3000` | 5/30 | 157789808/157789808 | 295854.04 | 5650772.63 | 10000000000 | 3659547850276669791 | 9856831559 | `uniswap_v3_quoter_optimism` |
| 21 | `4f9aff6dd77ea2865607` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:3000` | 5/30 | 157790343/157790343 | 296446.13 | 5657537.27 | 10000000000 | 3649566217845318402 | 9829950954 | `uniswap_v3_quoter_optimism` |
| 22 | `116b5b7d14e654715c90` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:3000` | 5/30 | 157790443/157790443 | 296449.63 | 5657577.34 | 10000000000 | 3649505905399886944 | 9829788533 | `uniswap_v3_quoter_optimism` |
| 23 | `2eb5c84ea1b03acad041` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:3000` | `uniswap_v3:USDC:WETH:500` | 30/5 | 157790034/157790034 | 5656628.63 | 296366.42 | 10000000000 | 3689217816291659794 | 9824475321 | `uniswap_v3_quoter_optimism` |
| 24 | `d79c2c3ad871cb8704e5` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:3000` | 5/30 | 157790241/157790241 | 296505.50 | 5657856.09 | 10000000000 | 3649085832439136647 | 9828657273 | `uniswap_v3_quoter_optimism` |
| 25 | `1be363dfd051ca55de34` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:500` | `uniswap_v3:USDC:WETH:3000` | 5/30 | 157790549/157790549 | 296449.63 | 5657914.63 | 10000000000 | 3648997484938030140 | 9828419352 | `uniswap_v3_quoter_optimism` |
| 26 | `b12fb1855661846d62f5` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:3000` | `uniswap_v3:USDC:WETH:500` | 30/5 | 157790034/157790034 | 5656628.63 | 296366.42 | 10000000000 | 3689217816291659794 | 9824475321 | `uniswap_v3_quoter_optimism` |
| 27 | `cacd4da09a9494e99f47` | USDC→WETH→USDC | `uniswap_v3:USDC:WETH:3000` | `uniswap_v3:USDC:WETH:500` | 30/5 | 157790038/157790038 | 5656628.63 | 296366.42 | 10000000000 | 3689217816291659794 | 9820784193 | `uniswap_v3_quoter_optimism` |

The stored route evidence shows a same-pair, two-pool cycle whose round trip returns fewer USDC wei than it started with. A positive price discrepancy between the pools is not present in the stored hop prices, which are null. The only USD prices on the bundle are `liquidity.price_provenance`: USDC `$1.00` from `configured_numeraire` (status `ok`, `stale=false`) and WETH from `onchain_usdc_direct` (status `ok`, `stale=false`) between `$2694.228577` and `$2703.158796`. All 27 WETH provenance rows cite pool `0xd0b53D9277642d899DF5C87A3966A349A798F224`, including the 14 Optimism candidates. Three provenance rows have price block `52195148` and head block `52195149`. One of those three is Optimism candidate `116b5b7d14e654715c90`, whose swap quote block is `157790443`. That USD reference is not a second pool quote for the cycle.

---

## 7. Timing evidence

| Clock | Stored on | What it is |
|---|---|---|
| `hint_observed_at` | all 27 candidates, and copied onto `diagnostics` | discovery |
| Quote timestamp (`quoted_at` or equivalent) | **0** | **TIMING_EVIDENCE_MISSING** |
| `block_context.verified_at_ts` | all 27 | quote-provider return clock written into the bundle |
| `verified_at` | all 27 candidates | verification time |
| `diagnostics.stamped_at` | all 27 | diagnostic stamp |
| `created_at` | all 27 bundles | bundle write |
| Gate 7 timestamp | **0** | Gate 7 is a status on the same bundle |
| Second quote, re-quote, or later state snapshot | **0** | absent |

Derived intervals from the clocks that exist:

| Interval | n | Min | Max | Mean |
|---|---:|---:|---:|---:|
| Discovery → quote-provider clock (`verified_at_ts` − `hint_observed_at`) | 27 | 30.779 s | 912.530 s | 678.731 s |
| Quote-provider clock → candidate `verified_at` | 27 | 0.0050 s | 0.0288 s | 0.0103 s |
| Bundle `created_at` → `stamped_at` | 27 | 0.000151 s | 0.001538 s | 0.000306 s |
| Verification → a separate Gate 7 clock | 0 | — | — | **TIMING_EVIDENCE_MISSING**. Gate 7 is a status on the bundle written in that same millisecond |

Five rows are verified within 30.8–50.8 s of discovery. One row takes 249.5 s. Twenty-one rows take 702–912.5 s. The only stored quote sits at verification time. A long discovery-to-verification wait with a single quote is not decay evidence.

Two Optimism rows, `7b4969c598418b21fb72` and `c89a76ede7a450c68a82`, have hop blocks `157789707` and `157789708`. Their wei amounts and gross percent are identical across that one-block gap. The other 25 rows use one block on both hops, and that block equals `quotes.quote_block` and `block_context.block_number`.

**TIMING_EVIDENCE_MISSING** for a distinct quote timestamp, a re-quote, and a Gate 7 time separate from verification. The clocks that are stored place the only quote at verification time.

---

## 8. Liquidity / TVL analysis

| Stored field | Result |
|---|---|
| `liquidity.min_pool_tvl_usd_in_route` | **0.0** on all 27 (explicit zero) |
| `liquidity.tvl_provenance` | `onchain_reserves` on all 27 |
| Hop `depth_usd` | positive on all 54 hops. No hop is 0 |
| Base 500-pool depth | `$10,011,622.68` to `$10,028,722.86` |
| Base 10000-pool depth | `$771,663.44` to `$772,229.53` |
| Optimism 500-pool depth | `$295,854.04` to `$296,505.50` |
| Optimism 3000-pool depth | `$5,650,772.63` to `$5,657,914.63` |
| Notional / quoted size | `$10,000` and `quoted_amount_in_wei=10000000000` |
| Slippage % | 0 |
| Separate price-impact field | not stored |
| Gate 8 | `NOT_EVALUATED` on all 27 |

The route-level TVL field is an explicit zero while every hop `depth_usd` on the same bundle is at least `$295,854`. Those stored numbers disagree. The zero was not replaced with a minimum of the hop depths, and Gate 8 was not applied. The smallest stored hop depth is about 30 times the `$10,000` notional. The negative gross percent sits on quotes whose stored hop depth is far above the quote size. This sample does not show the quote notional exceeding stored hop depth.

---

## 9. Loss attribution

Analysis labels only. Gate 7 reasons were not changed. No label was written to a schema.

| Label | Rows | Why |
|---|---:|---|
| `NO_GROSS_EDGE` | **27** | Stored gross spread is negative and stored true net is negative |
| `COSTS_EXCEED_EDGE` | 0 | Requires a stored positive gross |
| `GAS_DOMINATES` | 0 | Gas is `$0.10`–`$0.53` against true nets of `-$133.81` to `-$259.74` |
| `FLASH_FEE_DOMINATES` | 0 | Flash fee is `$0`, `$5`, or `$30`. Rows with a `$0` flash fee are still negative (best of those is `-$133.813915`) |
| `SLIPPAGE_DOMINATES` | 0 | Stored slippage percent is 0. Slippage dollars are NULL |
| `DEX_FEE_DOMINATES` | 0 | DEX-fee dollars are NULL. The stored fee percent is telemetry inside a quote-inclusive gross that is already negative. On all 14 Optimism rows the gross percent (`-1.418%` to `-1.792%`) is a larger magnitude than the stored fee percent (`0.35`). On Base the fee percent is `1.05` and the gross percent is `-0.837%` to `-1.140%`. No pre-fee gross is stored, so a positive pre-fee edge was not assigned |
| `MEV_EVIDENCE` | 0 | No capture evidence. See section 10 |
| `QUOTE_DECAY_EVIDENCE` | 0 | No second quote. See section 7 |
| `INSUFFICIENT_EVIDENCE` | 0 | Gross sign and true-net sign are stored on every row |

---

## 10. MEV / competition evidence

Searched fields on all 27 bundles include quote, execution, diagnostics, gates, and MEV. No document contains a re-quote, competitor marker, backrun, sandwich, transaction hash, or inclusion record.

| Looked for | Stored result |
|---|---|
| Positive gross edge | 0 rows |
| Positive net before execution | 0 rows. True net is negative at verification, before any broadcast |
| Subsequent price deterioration of a positive quote | no second quote |
| External transaction interaction | none stored |
| Execution / inclusion | `broadcast=false`. `execution_plan.status=BLOCKED` on all 27. Base reason `b7_execution_handoff_receiver_not_deployed` (13). Optimism reason `b7_execution_handoff_non_base_not_supported` (14). `opportunity_id` null |
| MEV penalty | not persisted |
| Gate 9 | `NOT_EVALUATED` |
| Block-to-block change inside one quote | 2 rows, one block apart, identical wei and identical negative gross |

The stored MEV object is the same risk class on every row (`MEDIUM`, score 48, atomic flash loan, $10,000 USDC). That label is not a capture event.

**COMPETITOR_CAPTURE_NOT_PROVEN**

---

## 11. Chain analysis

Samples are 13 and 14 rows, each concentrated on one fee-tier pair. These are descriptive counts for this window.

| Chain | n | Mean decision net | Best | Worst | Positive gross | Complete bundles |
|---|---:|---:|---:|---:|---:|---:|
| Base | 13 | `-$169.013846` | `-$133.81` | `-$193.76` | 0 | 13 |
| Optimism | 14 | `-$222.816429` | `-$192.19` | `-$259.74` | 0 | 14 |

Base gas is `$0.102372`–`$0.105921`. Optimism gas is `$0.405374`–`$0.531497`. Both chains are negative on the stored gross percent before that gas difference. Base gross percent is `-0.837%` to `-1.140%`. Optimism gross percent is `-1.418%` to `-1.792%`.

---

## 12. Provider analysis

Provider here is the stored flash-loan provider. The route protocol is `uniswap_v3` on both hops for every provider.

| Provider | n | Mean decision net | Best decision net | Positive gross | Complete bundles | Stored flash fee $ |
|---|---:|---:|---:|---:|---:|---|
| `aave_v3` | 11 | `-$194.560909` | `-$138.81` | 0 | 11 | 5.00 on all 11 |
| `balancer_v2` | 9 | `-$195.698889` | `-$133.81` | 0 | 9 | 0.00 on all 9 |
| `uniswap_v3` | 7 | `-$202.164286` | `-$163.81` | 0 | 7 | 30.00 on all 7 |

Chain mix differs: Aave is Optimism 6 / Base 5, Balancer is Optimism 6 / Base 3, Uniswap V3 flash loans are Base 5 / Optimism 2. The within-quote pairs in section 4 show the net gap between providers on the same wei quote equals the flash-fee gap. All three providers have a negative stored gross on every row.

---

## 13. DEX→DEX comparison

Same window, same classifier, same read-only pass. DEX→DEX was not reclassified. Its completed forensic conclusion remains `DEPRIORITIZE_DEX_TO_DEX`. This pass re-read the stored economics so the comparison uses the same field rules.

| | `CROSS_POOL` | `DEX_TO_DEX` |
|---|---|---|
| Rows | 27 | 17 |
| Complete m2.3 / decision-only | 27 / 0 | 16 / 1 |
| Positive gross on complete rows | 0 | 0 |
| Gross spread on complete rows | `-1.792158%` to `-0.837070%`, mean `-1.368222%` | `-0.628623%` to `-0.091142%`, mean `-0.205142%` |
| Positive gross and negative net | 0 | 0 |
| Decision-net mean / best / worst | `-$196.911481` / `-$133.81` / `-$259.74` | `-$94.963529` / `-$59.31` / `-$273.39` |
| True net on complete rows | `-$259.736833` to `-$133.813915` | `-$141.741151` to `-$59.313385` |
| Gas on complete rows | `$0.102372`–`$0.531497` | `$0.150000`–`$0.179572` |
| Flash fee on complete rows | `$0`, `$5`, `$30` | `$0`, `$5`, `$30` |
| DEX fee % stored | 0.35 or 1.05 | 0.35 on all 16 complete rows |
| Slippage % | 0 | 0 |
| Notional | `$10,000` | `$10,000` on the 16 complete rows |
| Route protocols stored | `uniswap_v3` + `uniswap_v3` on all 27 | distinct per-leg protocols on the completed analysis (`uniswap_v3` with `aerodrome_slipstream` or `aerodrome` on the 16 Base bundles; the decision-only row is BNB `pancakeswap_v3` + `uniswap_v3`) |
| Hop `price` | null on all legs | null on all complete-bundle legs |
| Second quote / re-quote | absent | absent |
| MEV | label `MEDIUM` on all 27; penalty not stored; capture not proven | label `MEDIUM` on 16 complete bundles; capture not proven in the completed analysis |
| `broadcast` | `false` | `false` on the 16 complete bundles |

Cross-Pool has the fuller bundle set. Its stored gross percent and its decision net are farther from zero. The best Cross-Pool decision net (`-$133.81`) is deeper than the best DEX→DEX decision net (`-$59.31`) and deeper than every complete DEX→DEX true net except the single complete row at `-$141.74`. Gas and flash fees are small on both families relative to those losses. Both families are negative at the stored quote.

**Comparison result: B. Similarly structurally negative.**

Cross-Pool is the same economic pattern as DEX→DEX: the stored round-trip quote is already negative, and the stored gas and flash fee do not account for that sign. The measured Cross-Pool quotes are the deeper of the two.

---

## 14. Core question answers

| | Question | Answer |
|---|---|---|
| A | Does Cross-Pool produce genuine positive gross arbitrage opportunities in this window? | **NOT_PROVEN** |
| B | Are costs destroying an otherwise positive edge? | **NOT_PROVEN** |
| C | Is insufficient liquidity/TVL responsible? | **NOT_PROVEN** |
| D | Is quote decay demonstrated? | **NOT_PROVEN** |
| E | Is competitor/MEV capture demonstrated? | **NOT_PROVEN** |
| F | Is Cross-Pool more promising than DEX→DEX? | **NOT_PROVEN** |

A. All 27 stored gross spreads are negative, from `-0.83707%` to `-1.792158%`. All 17 distinct wei round trips return fewer USDC wei than they start with. A positive gross is not in this window.

B. There are 0 rows with a positive gross and a negative net. Gas is at most `$0.531497`. Flash fee is `$0.00` on 9 rows that are still negative, including the best true net in the family (`-$133.813915`). DEX-fee dollars and a pre-fee gross are not stored. The stored quote percent is already negative.

C. Hop `depth_usd` is `$295,854` to `$10,028,723` against a `$10,000` notional. Slippage percent is 0. Gate 8 did not run. The route-level TVL field is the explicit zero `0.0` and disagrees with those hop depths, so that zero is not evidence that the pools were empty. Insufficient liquidity is not what the stored quote size and stored hop depth show.

D. No second quote, no re-quote, and no quote timestamp separate from the verification-time quote clock. The one-block hop gap on two rows has identical wei and the same negative gross. The discovery-to-verification wait is as long as 912 s, and the only stored quote is at the end of that wait.

E. No positive pre-execution net, no external transaction, no inclusion, `broadcast=false`, execution plan `BLOCKED`, Gate 9 not evaluated, MEV penalty not stored. The `MEDIUM` label is a constant risk class. **COMPETITOR_CAPTURE_NOT_PROVEN**.

F. Cross-Pool’s best decision net is `-$133.81` and its mean is `-$196.911481`. DEX→DEX’s best decision net is `-$59.31` and its mean is `-$94.963529`. Cross-Pool’s complete-bundle gross mean is `-1.368%` against DEX→DEX’s `-0.205%`. Cross-Pool is fully bundled. The economics are farther from zero.

---

## 15. Strategic conclusion

**DEPRIORITIZE_CROSS_POOL**

The family is fully measured in this window: 27 of 27 rows are complete m2.3 bundles, high confidence, and closed two-pool USDC/WETH cycles on Uniswap V3. The measurement is a negative round-trip quote on every row, including all 17 distinct wei quotes and the best row in the family. Gas and flash-loan fees are present and small beside that quote. Quote decay and competitor capture are not in the stored evidence. Keeping the family as a candidate for cost or timing repair would be aimed at a positive gross this window does not contain.

Another unchanged Cross-Pool SHADOW run would reproduce the same limitations. The writer would still store one quote-inclusive gross percent, no pre-fee gross, no gross dollars, no second quote, no MEV penalty, and no Gate 8 result after a Gate 7 failure. This window already contains 27 such records on the only two fee-tier cycles the classifier emitted, across both chains and all three flash-loan providers. A later window could store a different gross percent, because that field exists. It would not add the missing evidence types, and it would not change the finding that these stored quotes are economically negative.

---

## 16. Evidence limitations

- Gross profit dollars, DEX-fee dollars, slippage dollars, gas price, applied flash-fee percent, MEV penalty, true-net percent, and total cost are not on the m2.3 bundle. Phase 0 completeness stays `PARTIAL` for that reason. Signs of gross spread and true net are stored.
- `fees.flash_loan_fee_bps=0` is the override-or-zero integer. The stored fee dollars are `$0`, `$5`, and `$30`.
- Hop `price` is null. A per-pool price difference was not available to read.
- `route_pool_addresses` are resolved from the Base pool registry with no chain argument, so Optimism rows store those Base address strings. Chain scope of the quote is the hop token addresses, the quote block, and `source_id`.
- WETH `price_provenance` cites Base pool `0xd0b53D9277642d899DF5C87A3966A349A798F224` on all 27 rows, including Optimism. One Optimism row’s provenance block is a Base-height block. The cycle gross does not use hop price.
- `liquidity.min_pool_tvl_usd_in_route=0.0` disagrees with positive hop `depth_usd`. Gate 8 was not evaluated. Neither number was recomputed.
- There is no second quote, so decay during the 31 s–912 s discovery wait cannot be measured.
- Candidates are selected by the certification time window. They do not carry the certification run id. The scanner audit id on these bundles is `flarb_audit:a89e889be81c`.
- Seventeen distinct wei quotes sit under 27 rows because the same quote is stored once per flash-loan provider. Chain and provider means are not 27 independent pool states.
- Base n=13 and Optimism n=14 are one fee-tier pair each. They do not support a market-wide claim.
- No execution occurred. `broadcast=false` and the execution plan is `BLOCKED`.

**CROSS_POOL_FORENSIC_ANALYSIS_COMPLETE**
