# DEX_TO_DEX forensic analysis — October 5 ledger

**Classification: DEX_TO_DEX_FORENSIC_ANALYSIS_COMPLETE**

**Date:** 2026-10-05

Read-only. No code change, no database write, no scanner, no SHADOW, no deploy, no restart, no RPC change, no Network Config change, no Gate change, no commit, and no push.

Source: `arbicore_opportunity_ledger` only, run `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065`. Economics below are the stored ledger fields. Unavailable fields stay unavailable. Analysis labels in this note are not written back to the ledger and are not Gate reasons.

---

## 1. Scope

The question is where the 17 `DEX_TO_DEX` decision nets lost money. The classifier on every row is `phase0.strategy_intelligence.v1`. Its stored reason on all 17 is the same rule: hop count 2, a closed 2-token path, distinct pools, and two distinct per-leg protocols. `CROSS_POOL` and `CROSS_PROTOCOL` are secondary tags on all 17. This note does not reclassify any row.

The collection holds 288 rows. All 288 have this `run_id`. Rows with any other `run_id`: 0.

---

## 2. Population validation

| Check | Result |
|---|---:|
| `primary_family = DEX_TO_DEX` | 17 |
| `bundle_presence = COMPLETE_BUNDLE` | 16 |
| `bundle_presence = NO_BUNDLE` (decision-only) | 1 |
| `classification_state = COMPLETE` | 17 |
| `classification_completeness = FULLY_CLASSIFIED` | 17 |
| Legs stored | 2 on all 17 |
| `run_id` | the October 5 certification id on all 17 |

| Chain | Rows |
|---|---:|
| `base` | 16 |
| `bnb` | 1 |

| Flash-loan provider | Rows | Complete bundles | Decision-only |
|---|---:|---:|---:|
| `aave_v3` | 7 | 6 | 1 (BNB) |
| `uniswap_v3` | 6 | 6 | 0 |
| `balancer_v2` | 4 | 4 | 0 |

Confidence is `HIGH` on the 16 complete bundles and `MEDIUM` on the BNB decision-only row. `calculator_version` is null on all 17.

Decision nets on these 17: best `-$59.31`, worst `-$273.39`, mean `-$94.963529` (half-up `-$94.96`). All 17 are below `$0` and below `$25`. Gate 7 status is `FAIL` on the 16 bundles. The decision-only row has no gate object; its final status text is still the Gate-7 denial `atomic_profit $-273.39 < floor $25.00`.

---

## 3. Opportunity-by-opportunity table

Decision net is the stored Gate-7 cent value. True net is stored `true_net_usd`. Gross spread is stored `gross_spread_pct`. Blank gross means the field is null.

| Opportunity | Chain | Provider | Bundle | Gross spread % | Flash fee $ | Gas $ | Slippage % | True net $ | Decision net $ | Gate 7 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| `31df13631b18c7175c30` | base | balancer_v2 | complete | -0.09134 | 0.0 | 0.1794258 | 0.0 | -59.313385 | -59.31 | FAIL |
| `c5e085b8a929d2fc8e22` | base | balancer_v2 | complete | -0.092391 | 0.0 | 0.1762584 | 0.0 | -59.41531 | -59.42 | FAIL |
| `05ff2878f26a9c378d7b` | base | aave_v3 | complete | -0.091142 | 5.0 | 0.179304 | 0.0 | -64.29349 | -64.29 | FAIL |
| `0fa1f5122a2dca2f936e` | base | aave_v3 | complete | -0.09135 | 5.0 | 0.1794258 | 0.0 | -64.314403 | -64.31 | FAIL |
| `6bd9090183b8f4f6e652` | base | aave_v3 | complete | -0.092391 | 5.0 | 0.1762584 | 0.0 | -64.41531 | -64.42 | FAIL |
| `182073b1b8b26be11548` | base | balancer_v2 | complete | -0.152462 | 0.0 | 0.1795716 | 0.0 | -65.425748 | -65.43 | FAIL |
| `7da7b02af6824ef30da4` | base | aave_v3 | complete | -0.115733 | 5.0 | 0.1793646 | 0.0 | -66.752633 | -66.75 | FAIL |
| `4e298d34ffc3125fd2dc` | base | aave_v3 | complete | -0.154349 | 5.0 | 0.1754748 | 0.0 | -70.610343 | -70.61 | FAIL |
| `55517c3623fab219bc65` | base | uniswap_v3 | complete | -0.091142 | 30.0 | 0.179304 | 0.0 | -89.29349 | -89.29 | FAIL |
| `7c5a7119667209068462` | base | uniswap_v3 | complete | -0.09134 | 30.0 | 0.1794258 | 0.0 | -89.313385 | -89.31 | FAIL |
| `30c3c066c2ab11b279fa` | base | uniswap_v3 | complete | -0.092537 | 30.0 | 0.1762584 | 0.0 | -89.429958 | -89.43 | FAIL |
| `ab2ae34391791a9f744b` | base | uniswap_v3 | complete | -0.113189 | 30.0 | 0.1793586 | 0.0 | -91.498258 | -91.50 | FAIL |
| `a057d0bb6d4001fbc5aa` | base | uniswap_v3 | complete | -0.152462 | 30.0 | 0.1795716 | 0.0 | -95.425748 | -95.43 | FAIL |
| `a6c6d472203dc3908426` | base | balancer_v2 | complete | -0.615912 | 0.0 | 0.15 | 0.0 | -111.741151 | -111.74 | FAIL |
| `8792d075021e2159e080` | base | aave_v3 | complete | -0.628623 | 5.0 | 0.15 | 0.0 | -118.012291 | -118.01 | FAIL |
| `d93f1137920fdf6ad369` | base | uniswap_v3 | complete | -0.615912 | 30.0 | 0.15 | 0.0 | -141.741151 | -141.74 | FAIL |
| `6e19aac0d20e5fbd73dd` | bnb | aave_v3 | decision-only | unavailable | unavailable | unavailable | unavailable | unavailable | -273.39 | unavailable |

Every complete row’s Gate 7 reason is `atomic_profit $<decision net> < floor $25.00`. Gates 8 and 9 are `NOT_EVALUATED` on all 16 bundles. `gross_profit_usd`, `dex_fee_usd`, `slippage_usd`, `flash_loan_fee_pct`, `gas_price`, `mev_penalty`, `mev_adjusted_net_pct`, `true_net_pct`, and `total_cost_usd` are null on all 17. On the 16 bundles, `mev_adjusted_net_usd` equals `true_net_usd` because both hold the stored atomic-profit dollars. `mev_penalty` is still null, so that equality is not a separate MEV measurement.

`dex_fee_pct` is `0.35` on all 16 bundles and null on the BNB row. That percent is stored telemetry. The dollar DEX fee is unavailable.

---

## 4. Economics waterfall

### Counts

| Question | Result |
|---|---|
| A. Positive stored gross spread | **0** |
| B. Zero stored gross spread | **0** |
| C. Negative stored gross spread | **16** |
| D. Positive gross spread and negative true net | **0** |
| E. Gross spread unavailable | **1** (the BNB decision-only row) |

The 16 complete records can be answered. Each stored gross spread is negative, between `-0.091142%` and `-0.628623%`. Notional is `$10,000` on all 16. True net is negative on all 16. There is no complete row whose stored gross spread is a gain.

The decision-only row has a decision net and no gross spread, so it cannot support a gross-edge statement.

### What the stored dollars do show

Slippage percent is the explicit zero `0.0` on all 16 bundles. Gas dollars are between `$0.15` and `$0.1795716`. Flash-loan fee dollars are `0.0` (4 Balancer rows), `5.0` (6 Base Aave rows), or `30.0` (6 Uniswap V3 flash rows).

Several Base rows share the same stored hop amounts, the same gross spread, and the same gas, and differ in true net by the stored flash fee:

| Shared second-leg amount out | Block | Gross spread % | Balancer net (fee $0) | Aave net (fee $5) | Uniswap-flash net (fee $30) |
|---|---:|---:|---:|---:|---:|
| `9990760948` | 52194421 | -0.092391 | -59.42 | -64.42 | — |
| `9984753824` | 52194958 | -0.152462 | -65.43 | — | -95.43 |
| `9990885814` | 52195261 area | -0.091142 | — | -64.29 | -89.29 |
| `9990866041` | 52195060 | -0.09134 | -59.31 | — | -89.31 |
| `9938408849` | 52194750 | -0.615912 | -111.74 | — | -141.74 |

The `$5` and `$30` gaps match the stored flash fees. Gas on each pair is the same stored number. The Balancer row in each pair still has a negative gross spread and a true net near `-$59` to `-$112` with a flash fee of `0.0` and gas under `$0.18`.

The stored flash fee and gas are too small to account for the whole true-net loss, and there is no stored positive gross spread for them to erase. Gross profit dollars are unavailable, so this note does not convert `gross_spread_pct` into dollars and does not assign the residual to MEV.

---

## 5. Price-path analysis

All 17 rows have two legs. The Phase 0 evidence line on each row states distinct per-leg protocols. That is the classifier’s own DEX_TO_DEX evidence, quoted from the ledger, not a shape-only label added here.

### Base USDC / WETH, 13 rows

Leg 1 protocol `uniswap_v3`, fee bps `5`, pool id `uniswap_v3:USDC:WETH:500`, pool address `0xd0b53D9277642d899DF5C87A3966A349A798F224`, venue `uniswap_v3:base`, source `uniswap_v3_quoter_base`.

Leg 2 protocol `aerodrome_slipstream`, fee bps `30`, pool id `aerodrome_slipstream:USDC:WETH:100`, pool address `0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59`, venue `aerodrome_slipstream:base`, source `aerodrome_quoter_base`.

Token fields on the legs are the Base USDC and WETH addresses (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` and `0x4200000000000000000000000000000000000006`). The pool ids store the symbols USDC and WETH. Input amount on leg 1 is `10000000000` (the `$10,000` USDC quote size) on every one of these rows. Quote price and quote timestamp are null. Quote status is `ok` on both legs. Both legs usually share one block; four rows differ by one or two blocks.

### Base USDC / WETH, 3 rows

Same Uniswap V3 leg and pool as above. Leg 2 protocol `aerodrome`, fee bps `30`, pool id `aerodrome:USDC:WETH:volatile`, pool address `0xcDAC0d6c6C59727a65F871236188350531885C43`, venue `aerodrome:base`. Gas dollars are `0.15` and gas units are null. Gross spread is about `-0.62%`, deeper than the slipstream cluster.

### BNB, 1 decision-only row

Symbols `USDC → BTCB → USDC`. Protocols `pancakeswap_v3` then `uniswap_v3`. Pool ids `pancakeswap_v3:BTCB:USDC:500` and `uniswap_v3:BTCB:USDC:3000`. Amounts, fees, venues, sources, blocks, pool addresses, and quote timestamps are null. The classifier still recorded DEX_TO_DEX from the stored protocol list and the closed two-token path.

Quote price is null on every leg of all 17. Per-leg slippage is not a leg field. Route slippage percent is `0.0` on the 16 bundles.

---

## 6. Timing evidence

| Interval | Evidence |
|---|---|
| Discovery → quote | **TIMING_EVIDENCE_MISSING.** `quote_timestamp` is null on every leg. |
| Quote → verification | **TIMING_EVIDENCE_MISSING.** No quote clock is stored to subtract from `verified_at`. |
| Verification → Gate 7 | **TIMING_EVIDENCE_MISSING** as a separate stage. Gate 7 is inside the verification outcome. On the 16 bundles, `bundle_created_at` is within a few hundredths of a second of `verified_at`. |
| Discovery → verification | **DERIVABLE** on all 17. Both `hint_observed_at` and `verified_at` are stored. |

That discovery-to-verification gap runs from `45.7` seconds to `913.4` seconds. Several rows share one discovery timestamp and are verified together later. The stored gross spread on those later verifications is already negative. The gap is not a second quote, so it is not evidence that a positive quote decayed during the wait.

---

## 7. Loss attribution

Labels below are analytical only.

| Label | Rows | Why |
|---|---:|---|
| `NO_GROSS_EDGE` | 16 | Stored `gross_spread_pct` is negative. Slippage percent is stored `0.0`. |
| `INSUFFICIENT_EVIDENCE` | 1 | BNB decision-only. Decision net `-$273.39`. Gross spread and cost components are null. |
| `COSTS_EXCEED_EDGE` | 0 | No row has a positive stored gross spread. |
| `GAS_DOMINATES` | 0 | Stored gas is under `$0.18` while true-net losses are about `$59` to `$142`. |
| `FLASH_FEE_DOMINATES` | 0 | Stored flash fee is `$0`, `$5`, or `$30`. The `$0` fee rows are still about `$59` to `$112` negative, with negative gross spread. |
| `SLIPPAGE_DOMINATES` | 0 | Stored slippage percent is `0.0`. Slippage dollars are null. |
| `DEX_FEE_DOMINATES` | 0 | DEX fee dollars are null. The stored `0.35` percent is not a dollar attribution. |
| `MEV_EVIDENCE` | 0 | `mev_penalty` is null. No inclusion or external-transaction field is on these rows. |
| `QUOTE_DECAY_EVIDENCE` | 0 | One quote per leg. No quote time. No second quote. |

The flash-fee pairs in section 4 show a real stored cost difference. That difference sits on top of a quote that is already a loss. It is not evidence that fees destroyed a positive edge.

---

## 8. Competition / MEV evidence

The 17 records support this split:

| Hypothesis | Result |
|---|---|
| A. A positive opportunity existed and a competitor captured it | Not supported. No row stores a positive gross spread, a positive true net, an execution, an inclusion, a submission time, or an external transaction. |
| B. The stored quote was already economically weak | Supported for the 16 complete rows. Gross spread is negative at the stored quote, including rows with flash fee `0.0`. |
| C. The evidence cannot separate A from B | True for competitor capture, and true for the BNB row’s gross edge. It is not true for the 16 Base quotes: those quotes are stored losses. |

Competitor capture cannot be proven from this ledger. A negative decision net is not that proof. `mev_adjusted_net_usd` matching `true_net_usd` does not add an MEV event. One- and two-block gaps between the two legs are stored block numbers, not a price path across blocks.

---

## 9. Route-quality observations

These 17 rows cluster tightly. This is a description of the sample, not a market-wide rate.

| Cluster | Rows | What is stored |
|---|---:|---|
| Base, USDC/WETH, Uniswap V3 fee-500 pool plus Aerodrome Slipstream pool `…:100` | 13 | Gross spread about `-0.09%` to `-0.15%`. Best decision net `-$59.31`. |
| Base, same Uniswap pool plus Aerodrome `volatile` pool | 3 | Gross spread about `-0.62%`. Decision nets `-$111.74` to `-$141.74`. |
| BNB, USDC/BTCB, PancakeSwap V3 plus Uniswap V3 | 1 | Decision net only, `-$273.39`. |

The 13 slipstream rows are repeated observations of the same two pool addresses across the half hour, quoted at the same `$10,000` size, then repeated under Aave, Balancer, and Uniswap flash fees. Four Base pool addresses appear in total: one Uniswap V3 pool, one Slipstream pool, one Aerodrome volatile pool, and none on BNB with an address.

Fee bps stored on Base legs are `5` then `30`. The BNB fee bps are null; the pool ids contain `500` and `3000`.

---

## 10. Cross-family comparison

Aggregate decision nets already stored on this run. No row was reclassified.

| Family | n | Mean | Best | Worst |
|---|---:|---:|---:|---:|
| `DEX_TO_DEX` | 17 | -94.96 | -59.31 | -273.39 |
| `CROSS_PROTOCOL` | 8 | -183.40 | -126.03 | -262.70 |
| `CROSS_POOL` | 27 | -196.91 | -133.81 | -259.74 |
| `MULTI_HOP` | 27 | -196.91 | -114.82 | -419.73 |
| `MULTI_DEX` | 34 | -352.82 | -153.86 | -889.60 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 83 | -350.18 | -142.90 | -1068.05 |
| `TRIANGULAR` | 92 | -485.62 | -70.37 | -1709.90 |

`DEX_TO_DEX` is the least negative family on the mean and on the best row. `TRIANGULAR`’s best row, `-$70.37`, is the next-closest single observation and that family’s mean is the worst. The DEX_TO_DEX mean is also the mean of a narrow sample: 16 of 17 rows are one Base pair, and 13 of those are one pool pair. The ranking is real for this window. It is not evidence of a broad DEX_TO_DEX edge.

The 16 complete DEX_TO_DEX rows, excluding the BNB decision-only net, have mean decision net `-$83.81`. That subset is still entirely below zero, and every one of those 16 has a negative gross spread.

---

## 11. Four core questions

### A. Are we failing because there is no gross arbitrage edge?

**PROVEN** for the 16 complete records.

Stored `gross_spread_pct` is negative on all 16. None is zero. None is positive. Notional is `$10,000`. The best row, Balancer flash fee `0.0`, still has gross spread `-0.09134%` and true net `-$59.31`.

The BNB row does not contain gross spread. It does not supply a counterexample.

### B. Are fees, gas, slippage, or flash costs destroying a real edge?

**NOT_PROVEN.**

A real edge would be a positive stored gross spread. There are zero such rows. Stored slippage is `0.0`. Stored gas is under `$0.18`. Stored flash fees of `$0`, `$5`, and `$30` move true net between matched quotes, and the `$0` fee quotes remain losses of about `$59` to `$112`. DEX fee dollars, slippage dollars, MEV penalty, and total cost are unavailable, so a full cost split of the true net is not in the ledger.

### C. Are quotes decaying before verification?

**INSUFFICIENT_EVIDENCE.**

Quote timestamps are null. Each leg has one amount pair. Discovery-to-verification delays of about 46 seconds to about 15 minutes are stored, and the gross spread at verification is already negative. That delay is not a before-and-after quote.

### D. Do we have actual evidence of competitor or MEV capture?

**NOT_PROVEN.**

No execution, inclusion, submission, external transaction, or MEV penalty is stored. The complete quotes are already negative. Competitor capture cannot be concluded from an unprofitable Gate-7 result.

---

## 12. Strategic conclusion

**DEPRIORITIZE_DEX_TO_DEX** as a near-profit family in this window.

It is the least negative family in the certified ranking, and the forensic read shows why that ranking does not describe a hidden winner. The 16 complete records are repeated Base USDC/WETH quotes with a negative stored gross spread. Flash fee and gas are visible and small beside that quote loss. There is no stored positive edge for a cost-side refinement to recover.

The sample is 17 rows and essentially one pool cluster plus a single BNB decision-only row. This is not a statement about every DEX-to-DEX route outside these pools.

Another unchanged SHADOW of the same discovery mix would add more decision nets of this kind. It would not fill gross profit dollars, DEX fee dollars, slippage dollars, MEV penalty, or quote timestamps, because those fields are absent on the rows this ledger already holds. The useful missing evidence is not another copy of the same negative gross spread.

---

## 13. Evidence limitations

- One decision-only row has no component economics and no hop amounts.
- Gross profit dollars are null even on complete bundles, so gross spread was not converted into dollars here.
- DEX fee dollars, slippage dollars, flash-fee percent, gas price, MEV penalty, MEV-adjusted percent, true-net percent, and total cost are null.
- `mev_adjusted_net_usd` duplicates stored atomic profit. It is not an independent MEV observation.
- Quote price and quote time are null. Per-leg slippage is not stored.
- Gate 8 and Gate 9 did not run.
- No execution or inclusion records exist for these 17.
- Fee bps on the Slipstream leg is `30` while the pool id ends in `100`. Both values are stored. This note does not choose between them.
- Seventeen rows, sixteen of them one Base pair, cannot support a market-wide DEX_TO_DEX rate.

All 17 ledger records were examined.

DEX_TO_DEX_FORENSIC_ANALYSIS_COMPLETE
