# Real SHADOW strategy × economics ranking — 2026-10-05

**Classification: STRATEGY_ECONOMICS_RANKING_COMPLETE**

Read-only ranking of the closed 30-minute Phase 0 SHADOW population. No source file, MongoDB document, configuration, RPC, Gate threshold, scanner control, SHADOW start, deploy, restart, commit, or push was performed. The classifier ran in memory. Its inputs were not written back.

| | |
|---|---|
| Run | `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065` |
| Stored window | `2026-10-05T05:27:48.513927+00:00` inclusive through `2026-10-05T05:58:04.231514+00:00` exclusive |
| Certification status | `ABORTED` (operator stop recorded on `arbicore_shadow_certifications`) |
| Classifier | `observe_strategy_intelligence(bundle, candidate)` |
| Classifier version | `phase0.strategy_intelligence.v1` |
| Image used to import the classifier | `arbicore-x-backend:phase0-823a79b` in `arbicore-x-backend-new` |
| Population | 288 distinct Gate-7 candidates |

The half-open window is the certification document’s `started_at` and `completed_at`. Rows are `arbicore_discovery_candidates` with `verified_at` inside that window and `verified_outcome` containing `gate_7:atomic_profit`. The same window also contains 480 `denied:venue_unreadable` verifications. Those 480 are outside this ranking.

---

## Method

Family labels are `strategy.primary_family` from the Phase 0 classifier. A certified m2.3 bundle is passed together with its candidate when one bundle exists. A decision-only row is passed as the candidate alone. One certified bundle was found for each of 180 candidates (`schema_version=m2.3`, `source_component=flash_loan_arb_verifier`, `diagnostics.worker_id=flash_loan_arb:0eb9228c`). The other 108 candidates have no evidence bundle.

Calling the classifier on the bundle alone reproduces the family counts already recorded for those 180 bundles. Passing the candidate as well left all 180 primary families unchanged. Candidate-only classification of those same 180 rows also matched. The 108 decision-only labels exist because the candidate `hint_metric` is an input the classifier already accepts.

The decision net is `economics.fields.decision_net_usd` from that same observation: the cent-rounded `atomic_profit` amount in the stored Gate-7 text. On all 288 rows that value matched the amount in `verified_outcome`. The stored floor on all 288 rows is `$25.00`.

Statistics use those cent values. The mean is the arithmetic mean. Quartiles use linear interpolation at position `(n − 1) × q` on the ascending sample. For an even count, the median is the mean of the two central values. P25 and P75 are reported for every proven family. The smallest family has 8 rows, so those quartiles are descriptive.

Display in the ranking table is half-up to the cent. Each family section also gives the exact quotient.

`bundle_presence = COMPLETE_BUNDLE` is the count used for “complete m2.3 economics.” That flag requires schema `m2.3`, a stored path, hop count, pools, per-leg protocols, hop legs, `economics.atomic_profit_usd`, fees, gas, and `gates.gate_7`. The observer’s separate `economics.completeness` string is `PARTIAL` on all 288 rows. On the 180 complete bundles that string stays `PARTIAL` because DEX-fee dollars, gross dollars, slippage dollars, and gas price are absent, and flash-loan fee percent, MEV penalty, MEV-adjusted percent, and true-net percent are `AVAILABLE_NOT_PERSISTED`. Decision net is present on every row. Full-precision `atomic_profit_usd` is present on the 180 bundles and absent on the 108 decision-only rows. Gas units are present on 146 rows and absent on 142, including 34 of the complete bundles.

Flash-loan provider is read from `subject_id`, `hint_metric.provider`, and, when a bundle exists, `flash_loan_provider`. Those three agree on every row. The classifier records the provider and does not treat it as a route protocol. Chain is the stored candidate chain.

Route letter-shapes and stored protocol sequences are listed after the family ranking. They are sample descriptions. They are not family labels.

---

## Population check

| Known result | Measured |
|---|---|
| 288 distinct Gate-7 candidates | 288 documents, 288 distinct `candidate_id` |
| 180 certified m2.3 bundles | 180 `COMPLETE_BUNDLE` |
| 108 decision-only | 108 `NO_BUNDLE` |
| All decision nets negative | 288 negative, 0 zero, 0 positive |
| Best decision net `-$59.31` | `-$59.31` |
| Mean `-$345.32` | exact `-$345.321319`, half-up `-$345.32` |
| 0 candidates `>= $0` | 0 |
| 0 candidates `>= $25` | 0 |
| All six chains reached Gate 7 | ethereum 45, arbitrum 54, base 54, optimism 45, polygon 45, bnb 45 |
| Providers Aave V3, Balancer V2, Uniswap V3 | `aave_v3` 134, `balancer_v2` 82, `uniswap_v3` 72 |
| Complete strategy evidence on all 288 | `classification_state=COMPLETE` and `strategy_completeness=FULLY_CLASSIFIED` on all 288 |
| Stablecoin and LST/LRT not proven | primary counts 0; the classifier emitted no stablecoin assignment note and no LST/LRT assignment note |

Confidence is `HIGH` on 43 rows and `MEDIUM` on 245. The 43 `HIGH` rows are inside the 180 bundles. All 108 decision-only rows are `MEDIUM`. `hint_source` is `flash_loan_route_search` on all 288. Decision-net sum is `-$99,452.54`. Population median is `-$238.02` (the mean of `-$238.58` and `-$237.46`). Population P25 is `-$348.655`. Population P75 is `-$159.9825`.

---

## Proven primary families

The classifier’s family list includes nine names. Seven occurred as `primary_family` in this population. `STABLECOIN_CROSS_PROTOCOL` and `LST_LRT_CROSS_PROTOCOL` occurred zero times.

Every requested family occurred as a primary:

| Primary family | Rows |
|---|---:|
| `TRIANGULAR` | 92 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 83 |
| `MULTI_DEX` | 34 |
| `CROSS_POOL` | 27 |
| `MULTI_HOP` | 27 |
| `DEX_TO_DEX` | 17 |
| `CROSS_PROTOCOL` | 8 |
| `STABLECOIN_CROSS_PROTOCOL` | 0 |
| `LST_LRT_CROSS_PROTOCOL` | 0 |
| `UNCLASSIFIED` / `UNKNOWN` | 0 |

`MULTI_DEX` is absent from the bundle-only count of 180. All 34 of its rows are decision-only. The label is still the classifier’s `primary_family`, from stored candidate route fields.

Secondary tags are recorded here and are not ranked as primaries. A tag can sit on a row whose primary is a different family.

| Secondary tag | Rows carrying the tag |
|---|---:|
| `CROSS_POOL` | 261 |
| `CROSS_PROTOCOL` | 134 |
| `TRIANGULAR` | 91 |
| `MULTI_HOP` | 34 |

`CROSS_POOL` as a primary is 27 rows. The other `CROSS_POOL` tags sit on other primaries. The same split applies to `CROSS_PROTOCOL` (8 primary, 134 tagged), `TRIANGULAR` (92 primary, 91 tagged), and `MULTI_HOP` (27 primary, 34 tagged). `MULTI_DEX` appears only as a primary.

---

## Ranking by mean decision net

Higher mean is closer to zero. All means are negative. `CROSS_POOL` and `MULTI_HOP` tie at the displayed cent. Their exact means differ by `$0.000741`.

| Rank | Primary family | n | Mean | Median | Best | Worst | `>= $0` | `>= $25` | P25 | P75 | Complete m2.3 | Decision-only |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `DEX_TO_DEX` | 17 | -94.96 | -89.29 | -59.31 | -273.39 | 0 | 0 | -95.43 | -64.42 | 16 | 1 |
| 2 | `CROSS_PROTOCOL` | 8 | -183.40 | -160.36 | -126.03 | -262.70 | 0 | 0 | -234.61 | -149.48 | 4 | 4 |
| 3 | `CROSS_POOL` | 27 | -196.91 | -193.76 | -133.81 | -259.74 | 0 | 0 | -224.51 | -166.94 | 27 | 0 |
| 3 | `MULTI_HOP` | 27 | -196.91 | -158.60 | -114.82 | -419.73 | 0 | 0 | -185.96 | -142.93 | 15 | 12 |
| 5 | `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 83 | -350.18 | -297.39 | -142.90 | -1068.05 | 0 | 0 | -336.05 | -228.87 | 45 | 38 |
| 6 | `MULTI_DEX` | 34 | -352.82 | -335.56 | -153.86 | -889.60 | 0 | 0 | -374.98 | -217.19 | 0 | 34 |
| 7 | `TRIANGULAR` | 92 | -485.62 | -316.58 | -70.37 | -1709.90 | 0 | 0 | -455.36 | -152.48 | 73 | 19 |

Exact means, medians, and linear quartiles:

| Primary family | Sum | Exact mean | Exact median | Exact P25 | Exact P75 |
|---|---:|---:|---:|---:|---:|
| `DEX_TO_DEX` | -1614.38 | -94.963529 | -89.29 | -95.43 | -64.42 |
| `CROSS_PROTOCOL` | -1467.18 | -183.397500 | -160.36 | -234.6125 | -149.48 |
| `CROSS_POOL` | -5316.61 | -196.911481 | -193.76 | -224.51 | -166.94 |
| `MULTI_HOP` | -5316.63 | -196.912222 | -158.60 | -185.955 | -142.925 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | -29065.05 | -350.181325 | -297.39 | -336.05 | -228.865 |
| `MULTI_DEX` | -11996.00 | -352.823529 | -335.555 | -374.9775 | -217.1875 |
| `TRIANGULAR` | -44676.69 | -485.616196 | -316.575 | -455.3575 | -152.4775 |

The seven sums equal the population sum `-$99,452.54`.

---

## Chain distribution

Counts. A zero means that family has no Gate-7 row on that chain in this window.

| Primary family | Ethereum | Arbitrum | Base | Optimism | Polygon | BNB |
|---|---:|---:|---:|---:|---:|---:|
| `DEX_TO_DEX` | 0 | 0 | 16 | 0 | 0 | 1 |
| `CROSS_PROTOCOL` | 0 | 0 | 3 | 0 | 4 | 1 |
| `CROSS_POOL` | 0 | 0 | 13 | 14 | 0 | 0 |
| `MULTI_HOP` | 15 | 3 | 0 | 0 | 3 | 6 |
| `MULTI_DEX` | 0 | 0 | 0 | 0 | 14 | 20 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 21 | 24 | 22 | 0 | 0 | 16 |
| `TRIANGULAR` | 9 | 27 | 0 | 31 | 24 | 1 |
| **All families** | **45** | **54** | **54** | **45** | **45** | **45** |

Mean decision net by chain inside the family, where the count is at least 1:

| Primary family | Ethereum | Arbitrum | Base | Optimism | Polygon | BNB |
|---|---:|---:|---:|---:|---:|---:|
| `DEX_TO_DEX` | — | — | -83.81 | — | — | -273.39 |
| `CROSS_PROTOCOL` | — | — | -137.30 | — | -222.77 | -164.22 |
| `CROSS_POOL` | — | — | -169.01 | -222.82 | — | — |
| `MULTI_HOP` | -148.92 | -401.60 | — | — | -308.63 | -158.69 |
| `MULTI_DEX` | — | — | — | — | -451.49 | -283.75 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | -582.57 | -216.50 | -308.01 | — | — | -303.68 |
| `TRIANGULAR` | -134.83 | -146.19 | — | -791.85 | -617.58 | -146.87 |

Optimism and Polygon account for the `TRIANGULAR` family mean. Ethereum and Arbitrum `TRIANGULAR` means are `-$134.83` (n=9) and `-$146.19` (n=27). Those chain slices stay inside `TRIANGULAR` because that is the classifier primary.

---

## Flash-loan provider distribution

Counts. Every proven family was observed with all three providers.

| Primary family | `aave_v3` | `balancer_v2` | `uniswap_v3` |
|---|---:|---:|---:|
| `DEX_TO_DEX` | 7 | 4 | 6 |
| `CROSS_PROTOCOL` | 4 | 2 | 2 |
| `CROSS_POOL` | 11 | 9 | 7 |
| `MULTI_HOP` | 14 | 8 | 5 |
| `MULTI_DEX` | 26 | 6 | 2 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 40 | 23 | 20 |
| `TRIANGULAR` | 32 | 30 | 30 |
| **All families** | **134** | **82** | **72** |

Mean decision net by provider inside the family:

| Primary family | `aave_v3` | `balancer_v2` | `uniswap_v3` |
|---|---:|---:|---:|
| `DEX_TO_DEX` | -103.11 | -73.97 | -99.45 |
| `CROSS_PROTOCOL` | -172.28 | -179.66 | -209.37 |
| `CROSS_POOL` | -194.56 | -195.70 | -202.16 |
| `MULTI_HOP` | -180.24 | -191.36 | -252.50 |
| `MULTI_DEX` | -316.69 | -419.19 | -623.45 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | -357.34 | -333.26 | -355.33 |
| `TRIANGULAR` | -469.23 | -479.29 | -509.42 |

Provider order does not change the family ranking. Inside `DEX_TO_DEX`, `balancer_v2` is the least negative provider slice (n=4, mean `-$73.97`, best `-$59.31`) and remains below zero.

---

## Family evidence

### `DEX_TO_DEX` — 17 rows

| Metric | Value |
|---|---|
| Mean / median / best / worst | `-$94.963529` / `-$89.29` / `-$59.31` / `-$273.39` |
| `>= $0` / `>= $25` | 0 / 0 |
| P25 / P75 | `-$95.43` / `-$64.42` |
| Chains | Base 16, BNB 1 |
| Providers | `aave_v3` 7, `uniswap_v3` 6, `balancer_v2` 4 |
| Complete m2.3 / decision-only | 16 / 1 |
| Classification | `COMPLETE`, `FULLY_CLASSIFIED` on all 17 |
| Confidence | `HIGH` 16, `MEDIUM` 1 |
| Secondary tags | `CROSS_POOL` + `CROSS_PROTOCOL` on all 17 |

The classifier reason on these rows is a closed 2-token path, hop count 2, distinct pools, and distinct per-leg protocols. `CROSS_PROTOCOL` is a secondary tag on this primary.

Best row: `31df13631b18c7175c30`, Base, `balancer_v2`, `-$59.31`, complete bundle, confidence `HIGH`. This is also the best row in the population of 288. Worst row: BNB, `aave_v3`, `-$273.39`, the one decision-only row in the family, confidence `MEDIUM`.

The 16 complete bundles, taken as a subset of this same primary, have mean `-$83.811875`, median `-$79.95`, best `-$59.31`, worst `-$141.74`. That subset is still entirely negative.

### `CROSS_PROTOCOL` — 8 rows

| Metric | Value |
|---|---|
| Mean / median / best / worst | `-$183.397500` / `-$160.36` / `-$126.03` / `-$262.70` |
| `>= $0` / `>= $25` | 0 / 0 |
| P25 / P75 | `-$234.6125` / `-$149.48` |
| Chains | Polygon 4, Base 3, BNB 1 |
| Providers | `aave_v3` 4, `balancer_v2` 2, `uniswap_v3` 2 |
| Complete m2.3 / decision-only | 4 / 4 |
| Classification | `COMPLETE`, `FULLY_CLASSIFIED` on all 8 |
| Confidence | `MEDIUM` on all 8 |
| Secondary tags | `TRIANGULAR` + `CROSS_POOL` on all 8 |

The classifier reason is distinct per-leg protocols on hop count 3, with the stable, LST, complex-triangular, multi-DEX, and 2-hop DEX-to-DEX rules not taking priority. n=8 is the smallest proven family. Quartiles are descriptive. Four of the eight rows have no m2.3 bundle.

Best row: Base, `balancer_v2`, `-$126.03`, decision-only. Worst row: Polygon, `uniswap_v3`, `-$262.70`, complete bundle.

### `CROSS_POOL` — 27 rows

| Metric | Value |
|---|---|
| Mean / median / best / worst | `-$196.911481` / `-$193.76` / `-$133.81` / `-$259.74` |
| `>= $0` / `>= $25` | 0 / 0 |
| P25 / P75 | `-$224.51` / `-$166.94` |
| Chains | Optimism 14, Base 13 |
| Providers | `aave_v3` 11, `balancer_v2` 9, `uniswap_v3` 7 |
| Complete m2.3 / decision-only | 27 / 0 |
| Classification | `COMPLETE`, `FULLY_CLASSIFIED` on all 27 |
| Confidence | `HIGH` on all 27 |
| Secondary tags | none |

The classifier reason is hop count 2, a closed 2-token path, one explicit protocol on every hop, and at least two distinct pool ids. This is the only family with a complete m2.3 bundle and `HIGH` confidence on every row.

Best row: Base, `balancer_v2`, `-$133.81`. Worst row: Optimism, `uniswap_v3`, `-$259.74`.

### `MULTI_HOP` — 27 rows

| Metric | Value |
|---|---|
| Mean / median / best / worst | `-$196.912222` / `-$158.60` / `-$114.82` / `-$419.73` |
| `>= $0` / `>= $25` | 0 / 0 |
| P25 / P75 | `-$185.955` / `-$142.925` |
| Chains | Ethereum 15, BNB 6, Arbitrum 3, Polygon 3 |
| Providers | `aave_v3` 14, `balancer_v2` 8, `uniswap_v3` 5 |
| Complete m2.3 / decision-only | 15 / 12 |
| Classification | `COMPLETE`, `FULLY_CLASSIFIED` on all 27 |
| Confidence | `MEDIUM` on all 27 |
| Secondary tags | `CROSS_POOL` on all 27 |

The classifier reason is hop count 4 or more on a path that is not a 3-token cycle, with per-leg protocols not distinct. The family mean ties `CROSS_POOL` at the cent. The median (`-$158.60`) and the best row (`-$114.82`) are closer to zero than `CROSS_POOL`. The worst row (`-$419.73`) is deeper.

Best row: Ethereum, `balancer_v2`, `-$114.82`, complete bundle. Worst row: Arbitrum, `uniswap_v3`, `-$419.73`, decision-only.

### `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` — 83 rows

| Metric | Value |
|---|---|
| Mean / median / best / worst | `-$350.181325` / `-$297.39` / `-$142.90` / `-$1068.05` |
| `>= $0` / `>= $25` | 0 / 0 |
| P25 / P75 | `-$336.05` / `-$228.865` |
| Chains | Arbitrum 24, Base 22, Ethereum 21, BNB 16 |
| Providers | `aave_v3` 40, `balancer_v2` 23, `uniswap_v3` 20 |
| Complete m2.3 / decision-only | 45 / 38 |
| Classification | `COMPLETE`, `FULLY_CLASSIFIED` on all 83 |
| Confidence | `MEDIUM` on all 83 |
| Secondary tags | `TRIANGULAR` + `CROSS_POOL` + `CROSS_PROTOCOL` on all 83 |

The classifier reason is a closed 3-token path, hop count greater than 3, and distinct per-leg protocols. Ethereum carries the deep tail (mean `-$582.57`, worst `-$1068.05`). Arbitrum is the least negative chain slice (mean `-$216.50`, best `-$142.90`).

Best row: Arbitrum, `balancer_v2`, `-$142.90`, complete bundle. Worst row: Ethereum, `uniswap_v3`, `-$1068.05`, complete bundle.

### `MULTI_DEX` — 34 rows

| Metric | Value |
|---|---|
| Mean / median / best / worst | `-$352.823529` / `-$335.555` / `-$153.86` / `-$889.60` |
| `>= $0` / `>= $25` | 0 / 0 |
| P25 / P75 | `-$374.9775` / `-$217.1875` |
| Chains | BNB 20, Polygon 14 |
| Providers | `aave_v3` 26, `balancer_v2` 6, `uniswap_v3` 2 |
| Complete m2.3 / decision-only | 0 / 34 |
| Classification | `COMPLETE`, `FULLY_CLASSIFIED` on all 34 |
| Confidence | `MEDIUM` on all 34 |
| Secondary tags | `MULTI_HOP` + `CROSS_POOL` + `CROSS_PROTOCOL` on all 34 |

The classifier reason is hop count at least 3, a path that is not a 3-token cycle, and distinct per-leg protocols. Strategy evidence is complete. Component economics are decision-net only: no row has an m2.3 bundle, so fee, gas, and full-precision atomic profit are absent. Polygon (n=14, mean `-$451.49`, worst `-$889.60`) is deeper than BNB (n=20, mean `-$283.75`, best `-$153.86`).

### `TRIANGULAR` — 92 rows

| Metric | Value |
|---|---|
| Mean / median / best / worst | `-$485.616196` / `-$316.575` / `-$70.37` / `-$1709.90` |
| `>= $0` / `>= $25` | 0 / 0 |
| P25 / P75 | `-$455.3575` / `-$152.4775` |
| Chains | Optimism 31, Arbitrum 27, Polygon 24, Ethereum 9, BNB 1 |
| Providers | `aave_v3` 32, `balancer_v2` 30, `uniswap_v3` 30 |
| Complete m2.3 / decision-only | 73 / 19 |
| Classification | `COMPLETE`, `FULLY_CLASSIFIED` on all 92 |
| Confidence | `MEDIUM` on all 92 |
| Secondary tags | `CROSS_POOL` on all 92 |

The classifier reason is a closed path with exactly 3 distinct tokens, with cross-protocol not proven. Hop count is 3 on 53 rows and 4 on 39 rows. The classifier keeps the hop-count-4 rows in `TRIANGULAR`. Its evidence text states that `MULTI_HOP` is not the primary for that shape.

This family contains the second-best row in the population and the worst row in the population. Best: `-$70.37`, Arbitrum, `balancer_v2`, complete bundle, hop count 3. Worst: `-$1709.90`, candidate `cbeec5f983b249cc71d8`, Optimism, `uniswap_v3`, complete bundle, hop count 4. Optimism mean `-$791.85` (n=31) and Polygon mean `-$617.58` (n=24) set the family mean. The Arbitrum slice mean is `-$146.19`.

`TRIANGULAR` has the largest complete-bundle count (73). Confidence is `MEDIUM` on every row, including those bundles.

### Families with no rows

`STABLECOIN_CROSS_PROTOCOL` and `LST_LRT_CROSS_PROTOCOL` have count 0. The classifier did not attach a stablecoin note or an LST/LRT note to any of the 288 evidence lists. Eight `CROSS_PROTOCOL` reason strings mention the words “stable” and “LST” only as the names of higher-priority rules that did not match.

---

## Raw route shapes

These shapes are letter forms of the stored token path. The same letter form appears under more than one primary family. The family column is the classifier label for that subset, copied here so the shape table can be checked. The shape is not the label.

| Stored letter shape | Hop count | Classifier primary on these rows | n | Best | Worst | Mean |
|---|---:|---|---:|---:|---:|---:|
| `A→B→A` | 2 | `DEX_TO_DEX` | 17 | -59.31 | -273.39 | -94.96 |
| `A→B→A` | 2 | `CROSS_POOL` | 27 | -133.81 | -259.74 | -196.91 |
| `A→B→C→A` | 3 | `CROSS_PROTOCOL` | 8 | -126.03 | -262.70 | -183.40 |
| `A→B→C→A` | 3 | `TRIANGULAR` | 53 | -70.37 | -1483.17 | -415.67 |
| `A→B→C→B→A` | 4 | `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 83 | -142.90 | -1068.05 | -350.18 |
| `A→B→C→B→A` | 4 | `TRIANGULAR` | 39 | -103.04 | -1709.90 | -580.68 |
| `A→B→C→D→A` | 4 | `MULTI_HOP` | 27 | -114.82 | -419.73 | -196.91 |
| `A→B→C→D→A` | 4 | `MULTI_DEX` | 34 | -153.86 | -889.60 | -352.82 |

Stored per-leg protocol sequences with at least 7 rows. Protocol names are the stored sequence. They are not an additional family.

| n | Primary already assigned | Stored protocol sequence | Complete m2.3 | Decision-only | Best | Mean |
|---:|---|---|---:|---:|---:|---:|
| 52 | `TRIANGULAR` | `uniswap_v3` × 3 | 34 | 18 | -70.37 | -420.83 |
| 39 | `TRIANGULAR` | `uniswap_v3` × 4 | 39 | 0 | -103.04 | -580.68 |
| 27 | `CROSS_POOL` | `uniswap_v3` × 2 | 27 | 0 | -133.81 | -196.91 |
| 21 | `MULTI_HOP` | `uniswap_v3` × 4 | 15 | 6 | -114.82 | -207.83 |
| 18 | `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | `uniswap_v3` × 3, `sushiswap_v3` | 18 | 0 | -220.92 | -235.81 |
| 14 | `MULTI_DEX` | `uniswap_v3` × 3, `quickswap_v3` | 0 | 14 | -326.24 | -451.49 |
| 13 | `DEX_TO_DEX` | `uniswap_v3`, `aerodrome_slipstream` | 13 | 0 | -59.31 | -74.58 |
| 7 | `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | `uniswap_v3` × 3, `sushiswap_v2` | 7 | 0 | -746.94 | -768.11 |
| 7 | `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | `uniswap_v3`, `aerodrome_slipstream`, `aerodrome`, `uniswap_v3` | 0 | 7 | -293.33 | -320.88 |
| 7 | `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | `pancakeswap_v3` × 2, `uniswap_v3` × 2 | 0 | 7 | -262.12 | -309.02 |
| 7 | `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | `pancakeswap_v3`, `uniswap_v3`, `pancakeswap_v3`, `uniswap_v3` | 0 | 7 | -277.66 | -298.31 |
| 7 | `MULTI_DEX` | `pancakeswap_v3` × 2, `uniswap_v3`, `pancakeswap_v3` | 0 | 7 | -153.86 | -340.63 |

Distinct stored protocol sequences per primary: `CROSS_POOL` 1, `MULTI_HOP` 2, `DEX_TO_DEX` 3, `TRIANGULAR` 3, `CROSS_PROTOCOL` 4, `MULTI_DEX` 8, `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` 17. The remaining sequences have 6 or fewer rows.

Stored symbol paths, likewise not families, are dominated by USDC-quoted cycles. The most frequent are `USDC→WETH→WBTC→WETH→USDC` (62), `USDC→WETH→USDC` (43), and `USDC→WETH→WBTC→USDC` (36). Five rows are quoted from USDT rather than USDC (`USDT→WETH→WBTC→WETH→USDT`).

---

## Findings

### A. Best existing strategy family

**Evidence-supported conclusion.** `DEX_TO_DEX` is the best proven family on the mean (`-$94.96`), the median (`-$89.29`), and the best row (`-$59.31`). It is ahead of the next family, `CROSS_PROTOCOL`, by about `$88` on the mean. Sixteen of its 17 rows have complete m2.3 bundles, and 16 have confidence `HIGH`.

**Insufficient evidence.** The sample is 17 rows, 16 of them on Base. One BNB decision-only row at `-$273.39` is inside the family mean. This window does not show how the family behaves on Ethereum, Arbitrum, Optimism, or Polygon.

### B. Closest-to-profitable family

**Evidence-supported conclusion.** `DEX_TO_DEX` is also the closest family to profitable. Closeness here is the same three statistics: mean, median, and best row. The population’s best candidate is inside this family.

The closest row is still a loss. `-$59.31` is `$59.31` below zero and `$84.31` below the stored `$25` floor. The family median is `-$89.29`. Zero rows in this family, and zero rows in the other families, are at or above `$0` or `$25`.

`TRIANGULAR` holds the second-best single row in the population (`-$70.37`). That row does not make `TRIANGULAR` the closest family. Its mean is the worst of the seven.

### C. Worst family

**Evidence-supported conclusion.** `TRIANGULAR` is the worst family on the mean criterion used for the ranking (`-$485.62`) and it contains the worst row in the population (`-$1,709.90`). It is also the largest family (92 rows, 73 complete bundles), so the mean is not a small-sample artifact.

`MULTI_DEX` has a slightly worse median (`-$335.555` versus `-$316.575`) and a slightly better mean (`-$352.82`). Under the mean criterion, `MULTI_DEX` is sixth and `TRIANGULAR` is seventh.

The `TRIANGULAR` loss is concentrated on Optimism (31 rows, mean `-$791.85`) and Polygon (24 rows, mean `-$617.58`). The Arbitrum slice of the same primary has mean `-$146.19`. Those slices remain one family under the classifier.

### D. Most complete family evidence

**Evidence-supported conclusion.** `CROSS_POOL` has the most complete family evidence. All 27 rows are `FULLY_CLASSIFIED`, all 27 have a complete m2.3 bundle, all 27 have confidence `HIGH`, and none are decision-only.

`DEX_TO_DEX` is next on completeness rate: 16 of 17 complete bundles and 16 of 17 `HIGH`. `TRIANGULAR` has the largest absolute bundle count (73) with `MEDIUM` confidence on all 92 rows. `MULTI_DEX` is fully classified and has no m2.3 bundle on any of its 34 rows, so its economics evidence is the decision net alone.

Every proven family is `FULLY_CLASSIFIED`. Completeness in this finding is the joint of that strategy state, complete m2.3 bundles, and `HIGH` confidence.

### E. Most promising family for refinement

**Evidence-supported conclusion.** Among families that already have a measured decision-net distribution, `DEX_TO_DEX` is the least negative and the one with nearly complete m2.3 coverage. `CROSS_POOL` is fully covered by complete bundles and is about twice as far from zero on the mean.

**Insufficient evidence.** Nothing in this window shows that a change to `DEX_TO_DEX` would reach `$0` or `$25`. The family has no row near either line. Chain coverage outside Base is one decision-only BNB row.

**Strategic inference.** If an existing family is refined before new alpha work, the economics point to `DEX_TO_DEX` first. `CROSS_POOL` is the alternative when the selection criterion is completeness of evidence rather than distance to zero. `TRIANGULAR`, `COMPLEX_TRIANGULAR_CROSS_PROTOCOL`, and `MULTI_DEX` are the deep-loss families on this sample. `MULTI_DEX` would also be refined from decision nets only.

### F. Whether any existing family justifies further SHADOW or paper work

**Evidence-supported conclusion.** No proven family justifies further SHADOW or paper work as a search for a non-negative result under the economics already measured. All 288 decision nets are below zero. All seven family means are below `-$94`. The best observation in the window is `-$59.31`. The stored Gate-7 floor of `$25` was not met by any candidate. `CROSS_POOL`, the family with the cleanest evidence, has a best row of `-$133.81` and a mean of `-$196.91`.

**Insufficient evidence.** This is one window of about 30 minutes. It does not measure another time, another size, or another cost regime. It cannot, by itself, prove what a different regime would return.

**Strategic inference.** A repeat of this mix would be aimed at a distribution that, in this certified window, sat entirely below zero. That is a reason to pause unchanged shadow and paper continuation of these families. It is not a design for a new run.

### G. Whether the data supports moving to stablecoin + cross-protocol

**Evidence-supported conclusion.** This population does not support a move to stablecoin plus cross-protocol on performance. `STABLECOIN_CROSS_PROTOCOL` has 0 rows. `LST_LRT_CROSS_PROTOCOL` has 0 rows. The classifier recorded no stablecoin assignment and no LST/LRT assignment. The proven `CROSS_PROTOCOL` family has 8 rows, mean `-$183.40`, best `-$126.03`, and 0 rows at or above `$0`.

`DEX_TO_DEX` carries `CROSS_PROTOCOL` as a secondary tag on all 17 of its rows. Those rows keep the primary `DEX_TO_DEX`. They are not a stablecoin family.

**Insufficient evidence.** There is no stablecoin decision-net sample in this window, so this ranking cannot estimate stablecoin economics.

**Strategic inference.** Choosing stablecoin plus cross-protocol as the next build would be new alpha outside the seven measured families. This window does not supply an economic result in favor of that choice.

---

## Scope of the classification

`STRATEGY_ECONOMICS_RANKING_COMPLETE` means the requested ranking is finished for this population: every Gate-7 candidate has a canonical primary family and a decision net, every requested family is accounted for, and the absent stablecoin and LST/LRT primaries are recorded as zero. `economics.completeness = PARTIAL` on all 288 rows is the observer’s component-level result, reported above, and it leaves the decision-net ranking intact. `MULTI_DEX` is ranked on decision nets with zero complete m2.3 bundles.
