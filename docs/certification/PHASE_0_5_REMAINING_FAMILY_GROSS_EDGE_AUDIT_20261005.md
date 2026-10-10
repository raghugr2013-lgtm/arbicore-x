# Phase 0.5 — Remaining family stored-gross audit — 2026-10-05

**Classification: REMAINING_FAMILY_GROSS_EDGE_AUDIT_COMPLETE**

Read-only audit of stored gross edge for the four strategy families still open after the DEX-to-DEX, cross-pool, and triangular eliminations. No source file, MongoDB document, configuration, RPC endpoint, Gate threshold, scanner control, SHADOW start, PAPER session, deploy, restart, commit, or push was performed. The classifier ran in memory. Its inputs were not written back.

| | |
|---|---|
| Run | `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065` |
| Certification status | `ABORTED` (operator stop on `arbicore_shadow_certifications`) |
| Stored window | `verified_at >= 2026-10-05T05:27:48.513927+00:00` and `< 2026-10-05T05:58:04.231514+00:00` |
| Population | 288 distinct Gate-7 candidates (`verified_outcome` contains `gate_7:atomic_profit`) |
| Classifier | `observe_strategy_intelligence(bundle, candidate)` |
| Classifier version | `phase0.strategy_intelligence.v1` |
| Image | `arbicore-x-backend:phase0-823a79b` in `arbicore-x-backend-new` |
| LIVE 1 | Remains NO-GO |

The three prior eliminations are the starting point for scope, not re-litigated here: `DEPRIORITIZE_DEX_TO_DEX`, `DEPRIORITIZE_CROSS_POOL`, `DEPRIORITIZE_TRIANGULAR`. This audit measures `CROSS_PROTOCOL`, `MULTI_HOP`, `MULTI_DEX`, and `COMPLEX_TRIANGULAR_CROSS_PROTOCOL`. A population sign check on the other primaries is included only so the universe question is answered from the same read.

---

## Method

Family membership is `strategy.primary_family` from Phase 0. A certified m2.3 bundle is passed with its candidate when one bundle exists. A decision-only row is passed as the candidate alone. Bundle join: `evidence_bundles` with `schema_version=m2.3`, `source_component=flash_loan_arb_verifier`, and `diagnostics.worker_id=flash_loan_arb:0eb9228c`. Each of the 288 candidates has at most one such bundle. 180 bundles joined. 108 candidates have none.

`COMPLETE_BUNDLE` is the observer’s `bundle_presence` flag: schema `m2.3`, stored path, hop count, pools, per-leg protocols, hop legs, atomic profit, fees, gas, and `gates.gate_7`. `NO_BUNDLE` is decision-only. The observer’s separate `economics.completeness` string is `PARTIAL` on every row in these four families, including complete bundles, because gross dollars, true-net percent, the MEV penalty, and the applied flash-fee percent are not persisted.

Stored gross percent is the observer field `gross_profit_pct`. On every complete bundle in these families its status is `available`, its source is `verifier_bundle.economics.gross_spread_pct`, and the observer note is that this value agrees with `quotes.gross_profit_pct` within `1e-4`. The audit did not recompute it. Rows with status `unavailable` stay out of the min, max, mean, median, and sign counts. Missing gross is not filled from the decision net, from token symbols, or from `notional × percent`.

The gross unit is the stored percent: `100 × (quoted_out − quoted_in) / quoted_in` on the live quote path. A value of `-1.014496` is `-1.014496%`. Quote status on every complete bundle in these four families is `ok` with `exact_size=true`.

Mean is the arithmetic mean of the observer values. Median is the linear-interpolation median at position `(n − 1) × 0.5` on the ascending sample. For an even count that is the mean of the two central stored values.

The clearance test is applied only when four stored numbers exist: gross percent, `fees.flash_loan_fee_usd`, `gas.gas_cost_usd`, and `quotes.quote_notional_usd`. The hurdle in dollars is flash fee + gas + `$25`. The row clears when `notional × stored_gross_pct / 100` is at least that hurdle. That identity is the assessor’s gross-dollar relation. It is used only as a comparison. It is not written back as a stored gross dollar. `economics.gross_profit_usd` is absent on these bundles. Borrow amount is not substituted when quote notional is missing. In this window every testable row has quote notional `$10,000`.

True net is stored `economics.atomic_profit_usd`, which the observer also reads as `true_net_usd`. On every row where both exist, it matches `expected_net_after_costs_usd` and matches the cent-rounded Gate-7 decision text within `$0.005`. True-net percent is `AVAILABLE_NOT_PERSISTED`.

Protocol identity is taken only from the classifier’s explicit per-leg sources: `quotes.hop_legs[].dex_protocol`, `route_dex_protocols`, or `route_hops[].dex`. Venue ids, pool ids, and pool addresses are not protocols. The flash-loan provider is not a route protocol. Route letter-shapes are a compression of the stored `cycle_token_path`. They are descriptions, not family labels.

---

## Population anchor

| Check | Result |
|---|---|
| Gate-7 candidates | 288 distinct `candidate_id` |
| Certified m2.3 bundles | 180 `COMPLETE_BUNDLE` |
| Decision-only | 108 `NO_BUNDLE` |
| Classification | `COMPLETE` / `FULLY_CLASSIFIED` on all 288 |
| Raw `economics.gross_spread_pct` on the 180 bundles | 180 negative, 0 zero, 0 positive |
| Observer disagreement with `quotes.gross_profit_pct` above `1e-4` | 0 |
| Hint fields containing gross, spread, profit, or atomic | none on the 288 |

Primary counts from this read match the prior ranking: `TRIANGULAR` 92, `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` 83, `MULTI_DEX` 34, `CROSS_POOL` 27, `MULTI_HOP` 27, `DEX_TO_DEX` 17, `CROSS_PROTOCOL` 8, `STABLECOIN_CROSS_PROTOCOL` 0, `LST_LRT_CROSS_PROTOCOL` 0.

Stored-gross sign check on the three families already eliminated, from this same pass, stored rows only:

| Primary | Candidates | Complete bundles | Stored gross n | Max stored gross % | `> 0` | `>= 0` |
|---|---:|---:|---:|---:|---:|---:|
| `DEX_TO_DEX` | 17 | 16 | 16 | -0.091142 | 0 | 0 |
| `CROSS_POOL` | 27 | 27 | 27 | -0.837070 | 0 | 0 |
| `TRIANGULAR` | 92 | 73 | 73 | -0.189812 | 0 | 0 |

[EVIDENCE] The closest stored gross in the whole window is the `DEX_TO_DEX` maximum, `-0.091142%`. It is negative.

---

## `CROSS_PROTOCOL` — primary family, 8 rows

| Metric | Value |
|---|---|
| Candidates | 8 |
| Complete m2.3 bundles | 4 |
| Decision-only | 4 |
| Classification | `COMPLETE`, `FULLY_CLASSIFIED` on all 8 |
| Confidence | `MEDIUM` on all 8 |
| `economics.completeness` | `PARTIAL` on all 8 |
| Stored gross n | 4 |
| Minimum stored gross % | -1.835343 |
| Maximum stored gross % | -1.014496 |
| Mean stored gross % | -1.627178 |
| Median stored gross % | -1.8294365 |
| Gross `> 0` | 0 |
| Gross `>= 0` | 0 |
| Clearance tested | 4 |
| Clears flash fee + stored gas + `$25` | 0 |
| Secondary tags | `TRIANGULAR` and `CROSS_POOL` on all 8 |

The four stored gross values, ascending, are `-1.835343`, `-1.832351`, `-1.826522`, `-1.014496`. All four quotes are `ok` and `exact_size=true`. Slippage percent is stored `0.0` on all four. Quote notional is `$10,000` on all four.

[EVIDENCE] The primary family has no positive stored gross. The four decision-only rows have no stored gross percent. Their Gate-7 decision nets are negative and are not used as gross.

### Explicit per-leg protocol proof

The classifier evidence line `cross_protocol proven` means every hop has an explicit protocol and at least two distinct values. Venue ids are not that evidence.

Inside the primary family, all 8 rows carry that line.

| Proof source | Rows | Bundle | Stored gross |
|---|---:|---|---|
| `quotes.hop_legs[].dex_protocol` on every hop | 4 | complete m2.3 | stored, all negative |
| `hint_metric.route_dex_protocols` only | 4 | decision-only | not stored |

The four complete rows also store `route.route_dex_protocols`, and that list equals the hop-leg `dex_protocol` sequence. Hop-leg `dex_protocol` is the source the classifier recorded.

The four decision-only rows:

| Candidate | Chain | Provider | Stored protocol sequence | `route_hops[].dex` | Decision net $ | Gross |
|---|---|---|---|---|---:|---|
| `24239a5d83bfd4447b9d` | base | `balancer_v2` | `uniswap_v3`, `aerodrome_slipstream`, `aerodrome` | absent | -126.03 | not stored |
| `a5d2d65c2795b8988e07` | base | `aave_v3` | same sequence | absent | -129.83 | not stored |
| `676f211c57ae9ac80305` | base | `uniswap_v3` | same sequence | absent | -156.03 | not stored |
| `9ebe5e7bc3aa72d291c0` | bnb | `aave_v3` | `pancakeswap_v3`, `uniswap_v3`, `pancakeswap_v3` | equals the route-protocol list | -164.22 | not stored |

[EVIDENCE] Those four protocol lists are explicit protocol strings on the candidate. They are not venue ids. No venue id is stored on these four rows. Three Base rows have no `route_hops` list. The BNB row’s `route_hops[].dex` matches `route_dex_protocols`. None of the four has a quote-leg `dex_protocol`, because none has a bundle.

Complete-bundle protocol and venue, stored separately:

| n | `dex_protocol` sequence | `venue_id` sequence | Gross % min / max |
|---:|---|---|---|
| 3 | `uniswap_v3`, `quickswap_v3`, `uniswap_v3` | `uniswap_v3:polygon`, `quickswap_v3:polygon`, `uniswap_v3:polygon` | -1.835343 / -1.826522 |
| 1 | `uniswap_v3`, `uniswap_v3`, `quickswap_v3` | `uniswap_v3:polygon`, `uniswap_v3:polygon`, `quickswap_v3:polygon` | -1.014496 |

[EVIDENCE] On these four, the venue id carries a chain suffix and the protocol field does not. The family assignment uses `dex_protocol`. The venue strings differ on the same hops where the protocol strings differ. That coincidence is not the proof. Across the 142 window rows with `cross_protocol proven`, zero rows have two or more distinct venue ids and only one distinct protocol.

Window-wide predicate, separate from this primary of 8:

| Set | Rows | Complete bundle | Decision-only | Stored gross `> 0` |
|---|---:|---:|---:|---:|
| `cross_protocol proven` | 142 | 65 | 77 | 0 |
| Proof from hop-leg `dex_protocol`, distinct values | 65 | 65 | 0 | 0 |
| Proof from `route_dex_protocols` only | 77 | 0 | 77 | no gross stored |

The 142 break down by primary as `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` 83, `MULTI_DEX` 34, `DEX_TO_DEX` 17, and this primary 8. The other 134 are not reassigned to this primary. `MULTI_HOP`, `CROSS_POOL`, and `TRIANGULAR` account for the 146 rows whose evidence line is `cross_protocol not proven`.

### Best and worst stored gross

Best stored gross: `4fd464c533822275ab5c`, polygon, `aave_v3`, complete bundle, confidence `MEDIUM`.

| Field | Stored value |
|---|---|
| Gross % | -1.014496 |
| True net $ | -156.499616 |
| Decision net $ | -156.50 |
| Flash fee $ | 5.00 |
| Gas $ | 0.05 |
| Notional $ | 10,000 |
| Hurdle % for flash + gas + `$25` | 0.3005 |
| Clears | no |
| Protocols | `uniswap_v3`, `uniswap_v3`, `quickswap_v3` |
| Path | `USDC→WETH→USDT→USDC` |
| Shape | `A→B→C→A` |

This row is also the best true net inside the four complete bundles.

Worst stored gross: `939848dbd0d62d16b8b9`, polygon, `aave_v3`, gross `-1.835343%`, true net `-$238.584263`, decision net `-$238.58`, flash `$5.00`, gas `$0.05`. Same hurdle class, does not clear.

The closest decision net in the family is `-$126.03` on `24239a5d83bfd4447b9d`. That row is decision-only. It has no stored gross and is not the best gross candidate.

### True-net comparison

On the 4 complete bundles, gross percent and true net dollars are both negative. Zero rows have positive gross and negative true net. The largest absolute gap between true net and the cent decision text is `$0.004858`.

[EVIDENCE] Fee, gas, and the `$25` floor are not what turned a positive gross into a loss on these four rows. The stored quote percent is already negative. Flash fee on the four bundles is `$5`, `$0`, `$5`, and `$30`, matching `aave_v3`, `balancer_v2`, `aave_v3`, and `uniswap_v3`. Gas is `$0.05` on all four.

### Chain and provider

| Chain | n | Complete | Decision-only | Stored gross % min / mean / max |
|---|---:|---:|---:|---|
| polygon | 4 | 4 | 0 | -1.835343 / -1.627178 / -1.014496 |
| base | 3 | 0 | 3 | not stored |
| bnb | 1 | 0 | 1 | not stored |

| Provider | n | Complete | Decision-only | Stored gross n | Stored gross % min / max |
|---|---:|---:|---:|---:|---|
| `aave_v3` | 4 | 2 | 2 | 2 | -1.835343 / -1.014496 |
| `balancer_v2` | 2 | 1 | 1 | 1 | -1.832351 |
| `uniswap_v3` | 2 | 1 | 1 | 1 | -1.826522 |

Hint provider and bundle `flash_loan_provider` agree on every complete row. Ethereum, Arbitrum, and Optimism have no primary `CROSS_PROTOCOL` Gate-7 row in this window.

### Route shape

All 8 stored paths are the letter shape `A→B→C→A`, hop count 3. Stored symbol paths: `USDC→WETH→AERO→USDC` (3, all decision-only), `USDC→WETH→WBTC→USDC` (3, all complete), `USDC→WETH→USDT→USDC` (1, complete), `USDC→BTCB→USDT→USDC` (1, decision-only). Symbols were not used to assign the family. The assignment is the hop-count-3 cross-protocol rule after the stable, LST, complex-triangular, multi-DEX, and 2-hop DEX-to-DEX rules did not take priority.

---

## `MULTI_HOP` — primary family, 27 rows

| Metric | Value |
|---|---|
| Candidates | 27 |
| Complete m2.3 bundles | 15 |
| Decision-only | 12 |
| Classification | `COMPLETE`, `FULLY_CLASSIFIED` on all 27 |
| Confidence | `MEDIUM` on all 27 |
| `economics.completeness` | `PARTIAL` on all 27 |
| Stored gross n | 15 |
| Minimum stored gross % | -0.923967 |
| Maximum stored gross % | -0.507919 |
| Mean stored gross % | -0.776217 (unrounded -0.7762168) |
| Median stored gross % | -0.808335 |
| Gross `> 0` | 0 |
| Gross `>= 0` | 0 |
| Clearance tested | 15 |
| Clears flash fee + stored gas + `$25` | 0 |
| Secondary tags | `CROSS_POOL` on all 27 |
| `cross_protocol proven` | 0 |

All 27 paths are hop count 4, four distinct tokens, letter shape `A→B→C→D→A`. All 27 have exactly one distinct protocol. The 15 complete bundles prove that protocol from `quotes.hop_legs[].dex_protocol`. The 12 decision-only rows prove it from `hint_metric.route_dex_protocols`, and on those 12 `route_hops[].dex` equals that list. Quote status `ok`, `exact_size=true`, slippage `0.0`, notional `$10,000` on all 15 complete bundles.

[EVIDENCE] Genuine primary `MULTI_HOP` has stored gross on 15 rows and every one of those values is negative. There is no positive gross evidence in the primary.

### Classification boundary

| Set | Rows | What the classifier did | Stored gross `> 0` |
|---|---:|---|---:|
| Primary `MULTI_HOP` | 27 | hop count ≥ 4, not a 3-token cycle, protocols not distinct | 0 of 15 stored |
| Secondary tag `MULTI_HOP` | 34 | tag on primary `MULTI_DEX` only; all decision-only | no gross stored |
| `TRIANGULAR` with hop count > 3 | 39 | evidence text keeps the primary as `TRIANGULAR`; `MULTI_HOP` is not assigned | outside this family |

[EVIDENCE] The genuine multi-hop sample is the primary of 27. The secondary tag on `MULTI_DEX` is a different primary: distinct protocols, no bundle, no gross. The 39 four-hop triangular rows are a third shape and are not in this family. None of these three sets contributes a positive stored gross observation to `MULTI_HOP`.

### Best and worst stored gross

Best stored gross: `00f8b1a1d8f5abf0c3d1`, ethereum, `uniswap_v3`, complete bundle.

| Field | Stored value |
|---|---|
| Gross % | -0.507919 |
| True net $ | -142.785561 |
| Decision net $ | -142.79 |
| Flash fee $ | 30.00 |
| Gas $ | 11.993696 |
| Notional $ | 10,000 |
| Hurdle % | 0.669937 |
| Clears | no |
| Protocols | `uniswap_v3` × 4 |
| Venues | `uniswap_v3:ethereum` × 4 |
| Path | `USDC→WETH→WBTC→USDT→USDC` |

Worst stored gross: `3333b4d165a2b0240ff2`, ethereum, `aave_v3`, gross `-0.923967%`, true net `-$162.305425`, flash `$5.00`, gas `$14.908768`. Does not clear.

Best true net inside the 15 is a different row: `dd464734481f0186d9b3`, ethereum, `balancer_v2`, gross `-0.514478%`, true net `-$114.817453`, decision net `-$114.82`. The gross on that row is still negative. Worst true net inside the 15 is `69720821a9af63293381`, ethereum, `uniswap_v3`, gross `-0.923967%`, true net `-$187.305425`.

### True-net comparison

On all 15 complete bundles, gross percent and true net dollars are both negative. Zero rows have positive gross. The largest absolute gap between true net and the cent decision text is `$0.004575`.

[EVIDENCE] The least-negative gross in the family (`-0.507919%`) still has a true net of `-$142.79`. The least-negative true net (`-$114.82`) sits on gross `-0.514478%`. Costs change the dollar loss. They do not create a positive-gross row.

### Chain, provider, protocol, shape

| Chain | n | Complete | Decision-only | Stored gross % min / mean / max |
|---|---:|---:|---:|---|
| ethereum | 15 | 15 | 0 | -0.923967 / -0.776217 / -0.507919 |
| bnb | 6 | 0 | 6 | not stored |
| arbitrum | 3 | 0 | 3 | not stored |
| polygon | 3 | 0 | 3 | not stored |

Base and Optimism have no primary `MULTI_HOP` row.

| Provider | n | Complete | Decision-only | Stored gross n | All stored gross `< 0` |
|---|---:|---:|---:|---:|---|
| `aave_v3` | 14 | 6 | 8 | 6 | yes |
| `balancer_v2` | 8 | 6 | 2 | 6 | yes |
| `uniswap_v3` | 5 | 3 | 2 | 3 | yes |

| Stored protocol sequence | n | Complete | Decision-only | Stored gross % min / max |
|---|---:|---:|---:|---|
| `uniswap_v3` × 4 | 21 | 15 | 6 | -0.923967 / -0.507919 |
| `pancakeswap_v3` × 4 | 6 | 0 | 6 | not stored |

Venue ids on the 15 complete bundles are `uniswap_v3:ethereum` on every hop. Venue is stored and is not the protocol source. The 12 decision-only rows have no venue id.

Stored symbol paths, not used as the family label: `USDC→WETH→USDT→WBTC→USDC` (10), `USDC→WETH→WBTC→USDT→USDC` (5), `USDC→BTCB→WETH→USDT→USDC` (5), `USDC→WETH→WBTC→ARB→USDC` (3), `USDC→WETH→USDT→WMATIC→USDC` (3), `USDC→BTCB→WBNB→USDT→USDC` (1).

---

## `MULTI_DEX` — primary family, 34 rows

| Metric | Value |
|---|---|
| Candidates | 34 |
| Complete m2.3 bundles | 0 |
| Decision-only | 34 |
| Classification | `COMPLETE`, `FULLY_CLASSIFIED` on all 34 |
| Confidence | `MEDIUM` on all 34 |
| `economics.completeness` | `PARTIAL` on all 34 |
| Stored gross n | 0 |
| Minimum / maximum / mean / median stored gross % | not stored |
| Gross `> 0` | no stored observation |
| Gross `>= 0` | no stored observation |
| Clearance tested | 0 |
| Clears flash fee + stored gas + `$25` | not testable |
| True net $ | not stored |
| Secondary tags | `MULTI_HOP`, `CROSS_POOL`, and `CROSS_PROTOCOL` on all 34 |

[EVIDENCE] **`MULTI_DEX` gross edge is `INSUFFICIENT_EVIDENCE`.** Strategy classification is complete. Component economics are not. Every row is `NO_BUNDLE`. The observer gross status is `unavailable` on all 34. No hint field on these candidates stores a gross, spread, or profit percent. The audit does not reconstruct one.

The stored decision net exists on all 34 and is negative on all 34 (minimum `-$889.60`, maximum `-$153.86`). That figure is the cent-rounded Gate-7 atomic profit. It is not a gross percent and it is not entered in the gross statistics.

### What is stored about shape and protocol

All 34 are hop count 4, letter shape `A→B→C→D→A`, four distinct tokens, exactly two distinct protocols. `cross_protocol proven` is true on all 34 from `hint_metric.route_dex_protocols`. On all 34, `route_hops[].dex` equals that list. No hop-leg `dex_protocol` exists. No venue id is stored.

| Stored protocol sequence | n | Chain concentration |
|---|---:|---|
| `uniswap_v3` × 3, `quickswap_v3` | 14 | polygon |
| `pancakeswap_v3` × 2, `uniswap_v3`, `pancakeswap_v3` | 7 | bnb |
| `pancakeswap_v3`, `uniswap_v3`, `pancakeswap_v3` × 2 | 6 | bnb |
| `pancakeswap_v3`, `uniswap_v3` × 2, `pancakeswap_v3` | 3 | bnb |
| `uniswap_v3`, `pancakeswap_v3` × 2, `pancakeswap_v3` | 1 | bnb |
| `uniswap_v3`, `pancakeswap_v3`, `uniswap_v3`, `pancakeswap_v3` | 1 | bnb |
| `uniswap_v3` × 2, `pancakeswap_v3`, `pancakeswap_v3` | 1 | bnb |
| `uniswap_v3` × 3, `pancakeswap_v3` | 1 | bnb |

| Chain | n | Complete | Decision-only |
|---|---:|---:|---:|
| bnb | 20 | 0 | 20 |
| polygon | 14 | 0 | 14 |

| Provider | n | Complete |
|---|---:|---:|
| `aave_v3` | 26 | 0 |
| `balancer_v2` | 6 | 0 |
| `uniswap_v3` | 2 | 0 |

Stored symbol paths: `USDC→BTCB→WETH→USDT→USDC` (15), `USDC→WETH→WMATIC→USDT→USDC` (14), `USDC→BTCB→WBNB→USDT→USDC` (5). These paths did not assign the family. The assignment is distinct per-leg protocols, hop count at least 3, and a path that is not a 3-token cycle.

[INFERENCE] A negative decision net is compatible with a negative gross and also with a positive gross that fees and gas consumed. Both stories fit the stored decision text. The bundle fields that would separate them were not persisted. The inference stops there.

---

## `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` — primary family, 83 rows

| Metric | Value |
|---|---|
| Candidates | 83 |
| Complete m2.3 bundles | 45 |
| Decision-only | 38 |
| Classification | `COMPLETE`, `FULLY_CLASSIFIED` on all 83 |
| Confidence | `MEDIUM` on all 83 |
| `economics.completeness` | `PARTIAL` on all 83 |
| Stored gross n | 45 |
| Minimum stored gross % | -9.963626 |
| Maximum stored gross % | -0.906264 |
| Mean stored gross % | -3.219899 (unrounded -3.2198987) |
| Median stored gross % | -1.720936 |
| Gross `> 0` | 0 |
| Gross `>= 0` | 0 |
| Clearance tested | 45 |
| Clears flash fee + stored gas + `$25` | 0 |
| Secondary tags | `TRIANGULAR`, `CROSS_POOL`, and `CROSS_PROTOCOL` on all 83 |

All 83 are a closed 3-token path, hop count 4, letter shape `A→B→C→B→A`. Distinct protocol count is 2 on 61 rows and 3 on 22 rows. `cross_protocol proven` is true on all 83. The 45 complete bundles record the proof from `quotes.hop_legs[].dex_protocol`, and `route_dex_protocols` equals that sequence. The 38 decision-only rows record the proof from `hint_metric.route_dex_protocols`. Of those 38, 16 also have `route_hops[].dex` equal to the protocol list, and 22 have no `route_hops` list. No venue id is stored on the 38. Slippage is `0.0` and notional is `$10,000` on all 45 complete bundles. Quote status is `ok` and `exact_size=true`.

### How the negative result is composed

[EVIDENCE] On the 45 rows with stored gross, the gross percent is negative on every row. The result is not mixed. The family is not a decision-only artifact: 45 is the majority, and those 45 are universally gross-negative. The 38 decision-only rows have no gross sign. They do not reverse the stored-gross result, and they are not large enough to dominate the family count.

The label “complex” is the classifier’s name for a 3-token cycle with hop count greater than 3 and distinct per-leg protocols. It is not an alpha finding. Every stored gross observation in the family loses at the quote.

### Best and worst stored gross

Best stored gross: `e8e558bb43b0700ded24`, arbitrum, `aave_v3`, complete bundle.

| Field | Stored value |
|---|---|
| Gross % | -0.906264 |
| True net $ | -145.926369 |
| Decision net $ | -145.93 |
| Flash fee $ | 5.00 |
| Gas $ | 0.30 |
| Notional $ | 10,000 |
| Hurdle % | 0.303 |
| Clears | no |
| Protocols | `uniswap_v3` × 3, `camelot_v3` |
| Venues | `uniswap_v3:arbitrum` × 3, `camelot_v3:arbitrum` |
| Path | `USDC→WETH→WBTC→WETH→USDC` |

Best true net is a different row: `5c8806bfc47b71a1dcfc`, arbitrum, `balancer_v2`, gross `-0.925954%`, true net `-$142.895355`, decision net `-$142.90`. Still gross-negative.

Worst stored gross: `bada530c082f29c6d8c2`, ethereum, `aave_v3`, gross `-9.963626%`, true net `-$1,059.362613`, flash `$5.00`, gas `$8.00`, protocols `uniswap_v3`, `sushiswap_v2`, `uniswap_v3`, `sushiswap_v2`, path `USDC→WETH→USDT→WETH→USDC`.

Worst true net is `52ba5e58c4a31aed20eb`, ethereum, `uniswap_v3`, gross `-9.80047%`, true net `-$1,068.047015`, decision net `-$1,068.05`.

### True-net comparison

On all 45 complete bundles, gross percent and true net dollars are both negative. Zero rows have positive gross with a negative true net. The largest absolute gap between true net and the cent decision text is `$0.004952`.

[EVIDENCE] The best gross in the family is `-0.906264%`, about 1.2 percentage points under its own flash-plus-gas-plus-`$25` hurdle, and the true net on that row is `-$145.93`. The deep Ethereum tail reaches about `-10%` gross. That tail is a quote loss, not a fee story sitting on top of a positive quote.

### Chain and provider

| Chain | n | Complete | Decision-only | Stored gross % min / mean / max |
|---|---:|---:|---:|---|
| arbitrum | 24 | 24 | 0 | -1.825504 / -1.538973 / -0.906264 |
| ethereum | 21 | 21 | 0 | -9.963626 / -5.140956 / -1.154984 |
| base | 22 | 0 | 22 | not stored |
| bnb | 16 | 0 | 16 | not stored |

Optimism and Polygon have no primary row in this family. Arbitrum is the least negative chain slice and is still entirely below zero. Ethereum holds the deep tail.

| Provider | n | Complete | Decision-only | Stored gross % min / max |
|---|---:|---:|---:|---|
| `aave_v3` | 40 | 16 | 24 | -9.963626 / -0.906264 |
| `balancer_v2` | 23 | 15 | 8 | -7.143171 / -0.925954 |
| `uniswap_v3` | 20 | 14 | 6 | -9.800470 / -0.933785 |

Hint provider and bundle provider agree on every complete row. Every provider slice with stored gross is entirely negative.

### Protocol sequences with stored gross

| n | Complete | Stored protocol sequence | Gross % min | Gross % max | Gross % mean |
|---:|---:|---|---:|---:|---:|
| 18 | 18 | `uniswap_v3` × 3, `sushiswap_v3` | -1.825504 | -1.697631 | -1.729914 |
| 7 | 7 | `uniswap_v3` × 3, `sushiswap_v2` | -7.143171 | -6.889429 | -7.036850 |
| 6 | 6 | `uniswap_v3` × 3, `camelot_v3` | -1.010301 | -0.906264 | -0.966151 |
| 5 | 5 | `uniswap_v3`, `sushiswap_v2`, `uniswap_v3`, `sushiswap_v2` | -9.963626 | -4.374956 | -6.580087 |
| 5 | 5 | `uniswap_v3`, `sushiswap_v2`, `uniswap_v3`, `uniswap_v3` | -3.920207 | -1.494611 | -2.949969 |
| 3 | 3 | `uniswap_v3` × 2, `sushiswap_v2`, `uniswap_v3` | -1.170627 | -1.154984 | -1.165413 |
| 1 | 1 | `uniswap_v3` × 2, `sushiswap_v2` × 2 | -7.555615 | -7.555615 | -7.555615 |

The least negative sequence mean is the camelot slice, `-0.966151%`. It does not reach zero.

Decision-only sequences, gross not stored: `pancakeswap_v3` × 2 then `uniswap_v3` × 2 (7), `pancakeswap_v3`, `uniswap_v3`, `pancakeswap_v3`, `uniswap_v3` (7), `uniswap_v3`, `aerodrome_slipstream`, `aerodrome`, `uniswap_v3` (7), plus six shorter Aerodrome and PancakeSwap sequences of 1 or 3 rows. Venue ids on the complete bundles match the protocol name plus the chain suffix (`:arbitrum` or `:ethereum`). The protocol source remains `dex_protocol`.

Stored symbol paths, not family labels: `USDC→WETH→WBTC→WETH→USDC` (35), `USDC→WETH→AERO→WETH→USDC` (22), `USDC→BTCB→WETH→BTCB→USDC` (12), `USDC→WETH→USDT→WETH→USDC` (5), `USDT→WETH→WBTC→WETH→USDT` (5), and two BTCB paths of 2 rows each.

---

## Answers

### Does any implemented family show positive stored gross?

**NO.**

[EVIDENCE] No currently implemented strategy family in this certified window shows positive stored gross edge. The 180 certified bundles store a negative `economics.gross_spread_pct` on every row. Inside the four families audited here, stored-gross counts above zero are 0, 0, and 0, and `MULTI_DEX` has no stored gross observation at all. The three families already eliminated are also negative on every stored gross row, with a window maximum of `-0.091142%`.

[EVIDENCE] The existing strategy universe has not demonstrated gross alpha.

`MULTI_DEX` prevents a proof that every one of its 34 rows is gross-negative. It does not show a positive gross, and it does not change the answer above. The question asks what the stored evidence shows. The stored evidence shows no positive gross in any family.

### Strategic conclusion

**`DEPRIORITIZE_CURRENT_STRATEGY_UNIVERSE`**

[EVIDENCE] Where gross percent is stored, every primary family is universally gross-negative, and none of those rows clears flash fee + stored gas + `$25`. The best remaining-family gross is `MULTI_HOP` at `-0.507919%`, with true net `-$142.79`. The best true net in that family is `-$114.82` on gross `-0.514478%`.

[EVIDENCE] `RETAIN_EXISTING_FAMILY_FOR_NEXT_QUOTE_CENSUS` is not supported. No family has a non-negative stored gross to census again. `MULTI_DEX` is `INSUFFICIENT_EVIDENCE` for gross, which is an absence of a measurement, not a family to retain.

[INFERENCE] Another pass of the same route generator would be sampling a distribution whose stored quotes are already below zero.

---

## 1. Family-by-family gross table

Stored gross statistics use only rows where the observer gross status is `available`. Decision-only rows are excluded from those statistics.

| Primary family | Candidates | Complete m2.3 | Decision-only | Gross n | Min % | Max % | Mean % | Median % | `> 0` | `>= 0` | Clears flash+gas+`$25` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `CROSS_PROTOCOL` | 8 | 4 | 4 | 4 | -1.835343 | -1.014496 | -1.627178 | -1.8294365 | 0 | 0 | 0 of 4 |
| `MULTI_HOP` | 27 | 15 | 12 | 15 | -0.923967 | -0.507919 | -0.776217 | -0.808335 | 0 | 0 | 0 of 15 |
| `MULTI_DEX` | 34 | 0 | 34 | 0 | — | — | — | — | — | — | not testable |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 83 | 45 | 38 | 45 | -9.963626 | -0.906264 | -3.219899 | -1.720936 | 0 | 0 | 0 of 45 |

`MULTI_DEX` gross verdict: **`INSUFFICIENT_EVIDENCE`**.

Population reference, same pass, not a new forensic report: `DEX_TO_DEX` max `-0.091142%` (n=16), `CROSS_POOL` max `-0.837070%` (n=27), `TRIANGULAR` max `-0.189812%` (n=73). Each of those maxima is negative. Raw bundle gross on all 180 certified bundles: 180 negative, 0 zero, 0 positive.

## 2. Positive-gross evidence

[EVIDENCE] There is none in the certified window.

No primary family has a stored gross percent above zero. No primary family has a stored gross percent equal to zero. No testable row clears flash fee + stored gas + `$25`. No complete bundle has positive gross and negative true net, because none has positive gross. The quote-inclusive gross percent is already the loss on every stored row.

## 3. Missing evidence

[EVIDENCE] Stored gross percent is missing on 4 `CROSS_PROTOCOL` rows, 12 `MULTI_HOP` rows, 34 `MULTI_DEX` rows, and 38 `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` rows. Those 88 rows are decision-only. The candidate hint does not carry a substitute gross field.

[EVIDENCE] Even on complete bundles, gross dollars, true-net percent, the MEV penalty, and the applied flash-fee rate are not persisted. `economics.completeness` stays `PARTIAL`. Stored flash-fee dollars and stored gas dollars are present on the complete bundles and were used only in the clearance comparison.

[EVIDENCE] `MULTI_DEX` has a complete strategy label and no economic bundle. That is the entire missing-gross case for that family.

[HYPOTHESIS] The negative decision nets on the 34 `MULTI_DEX` rows might be negative because the unseen gross was negative. That hypothesis is not a measurement. It is not used above.

## 4. Whether the current strategy universe has demonstrated alpha

[EVIDENCE] It has not. Seven primaries occurred. Six of them have stored gross, and that gross is negative on every stored row. The seventh, `MULTI_DEX`, has not produced a stored gross observation. `STABLECOIN_CROSS_PROTOCOL` and `LST_LRT_CROSS_PROTOCOL` occurred zero times, so they have demonstrated nothing either.

The best stored gross in the window remains `-0.091142%` on a `DEX_TO_DEX` bundle. The best stored gross among the four families in this audit is `-0.507919%`. Both are losses at the quote, before the `$25` floor.

## 5. Recommended next experiment

[REQUIRES EXPERIMENT] A route class this window did not already measure with a stored quote. The experiment has to persist gross percent on every Gate-7 evaluation. This audit does not name that class. Zero rows of `STABLECOIN_CROSS_PROTOCOL` and zero rows of `LST_LRT_CROSS_PROTOCOL` are an absence of a sample, not a result in favor of building either one.

[EVIDENCE] The stored quotes that do exist are gross-negative after an exact-size quote with status `ok`. That is a completed quote, not a missing quote. Nothing in these four families identifies a search or quote bottleneck that a patch would open. The decision-only gap is a persistence gap on rows whose Gate-7 decision text is already a loss. Filling that gap would assign a gross sign to `MULTI_DEX`. It would not be evidence that the current universe has alpha, and it is not a reason to run the same generator again.

## 6. What not to build yet

- Patch 1. The stored exact-size quotes are gross-negative. A search or quote patch is not what these rows are waiting on.
- Route Search v2 aimed at the seven measured primaries.
- A stablecoin or LST/LRT implementation. Those primaries have count 0 here.
- An MEV implementation as the fix for this window. The MEV penalty is not stored, and the stored gross percent is already negative, so a penalty is not what turned a winning quote into a loss.
- Another unchanged SHADOW of this route generator.
- PAPER, LIVE 1, or any change to Gate 7, Gate 8, Gate 9, execution mode, signing, or broadcast.
- A census that keeps `MULTI_DEX`, `MULTI_HOP`, `CROSS_PROTOCOL`, or `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` on the basis of gross alpha. The first has no stored gross. The other three have stored gross and it is negative.

---

REMAINING_FAMILY_GROSS_EDGE_AUDIT_COMPLETE
