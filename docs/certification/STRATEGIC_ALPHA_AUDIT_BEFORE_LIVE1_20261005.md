# ArbiCore X — Strategic alpha audit before LIVE 1

**Classification: STRATEGIC_AUDIT_COMPLETE**

**Date:** 2026-10-05

**Mode:** read-only. No source edit, MongoDB write, configuration change, Network Config change, RPC change, container change, scanner start or stop, SHADOW or PAPER start, execution-mode change, Gate 7/8/9 change, signing or broadcast change, temporary implementation script, commit, or push.

**Question this audit answers:** if the objective is sustainable profitable production with the least wasted engineering, what happens next?

**Answer:** stop the LIVE 1 program as currently framed. The routes that received an exact live quote lost money on the quote itself, before gas, flash-loan fee, or the model MEV haircut. No implemented family has a non-negative gross. The next spend is one stratified quote census that can falsify “no edge in the current graph” versus “we never quoted the routes that might have edge.” Route Search v2, Patch 1 efficiency work, MEV engineering, six-chain model splits, and a Stablecoin + Cross-Protocol build wait on that result.

---

## 1. Executive verdict

LIVE 1 is not justified. Zero families qualify.

The certified 30-minute flash-loan SHADOW (`shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065`) produced 288 Gate-7 candidates, all with a negative decision net. Mean `-$345.32`. Best `-$59.31`. None reached `$0`. None reached the `$25` floor. On the 180 rows that stored an m2.3 bundle, stored gross spread is at or below zero on every row (population range `-1.709%` to `-0.091%`). The economics path treats that gross as quote-inclusive: pool fees and price impact are already inside the quoted round trip. A negative gross is a losing swap cycle at the quoted size, not a winning cycle that costs later removed.

**[EVIDENCE]** DEX→DEX and Cross-Pool, the two families with the cleanest bundles, are negative on stored gross. Deprioritize both as LIVE candidates. The ranking that placed DEX→DEX first is a ranking of losses. It is not a profitability ranking.

**[INFERENCE]** The dollar gap on the best DEX→DEX row is mostly the default MEDIUM MEV penalty (`0.5` percentage points, about `$50` on a `$10,000` notional), plus about `$9` of negative quote and a few cents of gas. Removing the penalty does not produce a non-negative trade and does not clear `$25`. MEV engineering does not unlock LIVE 1.

**[EVIDENCE]** The same window discovered 33,311 candidates and verified 288, all with `hint_source=flash_loan_route_search`. The triangular discovery source (7,128) and the generic-DEX discovery source (1,800) did not appear in the Gate-7 set. Claim size is 32 per tick. About 10 ticks ran. The measured loss distribution describes the routes the bounded route search got quoted. It does not describe the unquoted sources, stablecoin cycles, or LST/LRT cycles. Those counts are zero in the classified Gate-7 set.

**[REQUIRES EXPERIMENT]** Whether any atomic flash-loan edge exists in the venues already registered, or only outside this graph, is unanswered. Another unchanged 30-minute SHADOW draws from the same quote distribution and will not answer it.

Safety posture observed in the certification, and left unchanged by this audit: Ethereum, Arbitrum, Base, Optimism, Polygon, BNB; RPC order NEW A → NEW B → OLD A → OLD B; execution `SHADOW`; detection-only; no signing; no broadcast; no LIVE execution. Phase 0 strategy intelligence and economics observability are deployed at `823a79b617ddb1f19397cf5073b9c516aae4e9fd` with post-deploy integrity PASS.

---

## 2. Current evidence baseline

Authoritative population is the ranking in `docs/certification/REAL_SHADOW_288_STRATEGY_ECONOMICS_RANKING_20261005.md` (`STRATEGY_ECONOMICS_RANKING_COMPLETE`), read together with `docs/certification/SHADOW_30MIN_REAL_FLASH_LOAN_20261005.md` and `docs/certification/REAL_SHADOW_288_ECONOMICS_STRATEGY_ANALYSIS_20261005.md`.

| Fact | Value | Label |
|---|---|---|
| Run | `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065` | [EVIDENCE] |
| Window | `2026-10-05T05:27:48.513927Z` through `2026-10-05T05:58:04.231514Z` | [EVIDENCE] |
| Status | `ABORTED` by operator stop after the intended 30 minutes | [EVIDENCE] |
| Image / commit | `arbicore-x-backend:phase0-823a79b` / `823a79b617ddb1f19397cf5073b9c516aae4e9fd` | [EVIDENCE] |
| Mode | `SHADOW`, `detection_only=true`, `broadcast_allowed=false`, signing key absent | [EVIDENCE] |
| Gate-7 candidates | 288, six chains, all denied, floor `$25.00` | [EVIDENCE] |
| Decision net | best `-$59.31`, mean `-$345.32`, median `-$238.02`, sum `-$99,452.54` | [EVIDENCE] |
| `>= $0` / `>= $25` | 0 / 0 | [EVIDENCE] |
| Complete m2.3 bundles | 180, worker `flash_loan_arb:0eb9228c`, `exact_size=true`, `route_quote_status=ok`, `broadcast=false` | [EVIDENCE] |
| Decision-only Gate-7 rows | 108, including all 45 BNB rows | [EVIDENCE] |
| Stored gross on 180 | mean `-0.278%`, min `-1.709%`, max `-0.091%`, all `≤ 0` | [EVIDENCE] |
| Stored slippage % | `0.0` on all 180 | [EVIDENCE] |
| Stored gas $ | mean `$2.47`, min `$0.05`, max `$13.37` | [EVIDENCE] |
| Stored flash-loan fee $ | `$0` / `$5` / `$30` (mean `$8.47`) | [EVIDENCE] |
| Rows with positive gross and negative net | 0 | [EVIDENCE] |
| Gate 8 / Gate 9 | 0 evaluations. Both `NOT_EVALUATED` on the 180 because Gate 7 failed first | [EVIDENCE] |
| Discoveries in window | 33,311 (`flash_loan_route_search` 24,383, `flash_loan_triangular` 7,128, `flash_loan_generic_dex` 1,800) | [EVIDENCE] |
| Certified `venue_unreadable` | 0 on the certified worker. 480 rows are the other worker `flash_loan_arb:33291a96` | [EVIDENCE] |
| `STABLECOIN_CROSS_PROTOCOL` / `LST_LRT_CROSS_PROTOCOL` | 0 / 0 | [EVIDENCE] |
| Prior window 2026-10-04 | 256 Gate-7 rows, mean about `-$316`, 0 passes, floor `$25` | [EVIDENCE] |

Family ranking by mean decision net. Every mean is a loss. “Proven” in the ranking document means the Phase 0 classifier assigned the family from stored route fields. It does not mean the family made money.

| Rank | Family | n | Mean | Best | Complete m2.3 | Decision-only |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `DEX_TO_DEX` | 17 | -94.96 | -59.31 | 16 | 1 |
| 2 | `CROSS_PROTOCOL` | 8 | -183.40 | -126.03 | 4 | 4 |
| 3 | `CROSS_POOL` | 27 | -196.91 | -133.81 | 27 | 0 |
| 3 | `MULTI_HOP` | 27 | -196.91 | -114.82 | 15 | 12 |
| 5 | `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 83 | -350.18 | -142.90 | 45 | 38 |
| 6 | `MULTI_DEX` | 34 | -352.82 | -153.86 | 0 | 34 |
| 7 | `TRIANGULAR` | 92 | -485.62 | -70.37 | 73 | 19 |

Quoted symbol paths are narrow. The ranking’s most frequent stored paths are `USDC→WETH→WBTC→WETH→USDC` (62), `USDC→WETH→USDC` (43), and `USDC→WETH→WBTC→USDC` (36). Five rows are USDT-quoted. **[EVIDENCE]**

Chain means differ inside one family. `TRIANGULAR` on Arbitrum is mean `-$146.19` (n=27). The same primary on Optimism is mean `-$791.85` (n=31) and on Polygon is mean `-$617.58` (n=24). That split is why the family mean is the worst of the seven. **[EVIDENCE]**

Document conflict, recorded so it is not reused: section 7 of `REAL_SHADOW_288_ECONOMICS_STRATEGY_ANALYSIS_20261005.md` prints family means and best-rows that do not match this ranking (for example it assigns Cross-Pool a best of `-$114.8`, which is the Multi-Hop best in the ranking). The near-pass table in that same file matches the ranking’s best row (`31df13631b18c7175c30`, Base, Balancer, DEX→DEX, `-$59.31`, gross `-0.091%`). This audit uses the ranking for family statistics and the near-pass table only as a gross snapshot of the least-negative bundled rows.

This audit did not re-query MongoDB. Family gross ranges below are the operator forensic where one was supplied, otherwise the published near-pass rows plus the population bound that every stored gross is `≤ 0`.

### What the decision net contains

`FlashLoanEconomicsAssessor.assess` calls `aggregate_economics` with `gross_is_quote_inclusive=True`. On that path, hop swap fees are not deducted again. Slippage on the live path is supplied as zero because price impact is inside the quote. The flash-loan premium is added as fee bps (`aave_v3` 5, `balancer_v2` 0, `uniswap_v3` default 30). Gas is one USD figure. Default MEV factors are LOW `0`, MEDIUM `0.5`, HIGH `1.5` percentage points. `assess` does not pass a custom factor. Stored bundles in this window carry MEV label `MEDIUM`. The penalty percent is computed and then omitted from the denial bundle (`AVAILABLE_NOT_PERSISTED`). **[EVIDENCE]** code in `economics.py`, `scanners/economics.py`, `verifier.py`; persistence gap in the Phase 0.5 architecture audit.

**[INFERENCE]** On the published best row (gross `-0.091%`, flash fee `$0`, gas `$0.18`, net `-$59.31`), a `$10,000` notional and a `0.5` point MEDIUM penalty reproduce a net within a few cents of `-$59.31`. Pre-penalty result is about `-$9`. The same identity fits the next published rows that add a `$5` Aave fee and print nets near `-$64`. The `$50` term dominates the dollars. The sign is already set by the quote.

Stored `fees.total_swap_fee_pct = 0` on the 180 is a stored zero. It is not evidence that pools charged zero. The quote-inclusive design embeds swap fees in gross, and the economics analysis recorded the stored percent as zero. **[EVIDENCE]** stored zero. **[INFERENCE]** pool fee is not separately measured on these rows.

---

## 3. What DEX→DEX forensic proves

Population: 17 rows. 16 complete Base bundles, confidence `HIGH`. One BNB decision-only row at `-$273.39`. Family mean `-$94.96`, median `-$89.29`, best `-$59.31` (`31df13631b18c7175c30`, Base, `balancer_v2`). The 16 complete bundles alone have mean `-$83.81`, best `-$59.31`, worst `-$141.74`. Secondary tags `CROSS_POOL` and `CROSS_PROTOCOL` sit on all 17; the primary remains `DEX_TO_DEX`. Dominant stored protocol pair: `uniswap_v3` → `aerodrome_slipstream`, 13 rows, mean `-$74.58`, best `-$59.31`. **[EVIDENCE]**

Stored gross on the published complete Base examples is negative. The least-negative published gross in the whole 180-row set is `-0.091%`, and it belongs to this family. No positive-gross row is published for the family, and the population bound forbids one among the 16 bundles. The BNB row has no bundle, so its gross is unknown; its decision net is `-$273.39`. **[EVIDENCE]**

Conclusion **DEPRIORITIZE_DEX_TO_DEX** as a LIVE 1 candidate. **[EVIDENCE]**

What this does not prove:

- It does not prove every two-venue cycle on Base is unprofitable. The quoted slice is mostly USDC/WETH across Uniswap V3 and Aerodrome Slipstream. **[INFERENCE]** from the stored protocol sequence and the path census.
- It does not prove quote decay, competitor capture, or insufficient TVL. Gate 8 did not run. No second quote at a later block is stored. **[EVIDENCE]** of absence.
- It does not prove the quoter is wrong. Reproduction against the stored block was not done. **[REQUIRES EXPERIMENT]**
- It does not prove a fee change or a size change would flip the sign. Exact size was already true on the 16 bundles, at one notional (the assessor default and the row identity are `$10,000`). Other sizes were not stored. **[REQUIRES EXPERIMENT]**

DEX→DEX remains the right control sample for a later census because it is the closest stored gross to zero. Closeness is about nine basis points of loss. That is a scientific control, not a build target.

---

## 4. What Cross-Pool forensic proves

Population: 27 rows. Every row is a complete m2.3 bundle with confidence `HIGH`. Chains: Optimism 14, Base 13. Protocol sequence on all 27: `uniswap_v3` × 2. Shape `A→B→A`. Mean `-$196.91`, median `-$193.76`, best `-$133.81` (Base, `balancer_v2`), worst `-$259.74`. **[EVIDENCE]**

Operator forensic, accepted here and not re-queried: stored gross `-0.837%` to `-1.792%`; gas `≤ $0.53`; flash-loan fee `$0` / `$5` / `$30`; every true net negative; no positive-gross / negative-net row. The certified population aggregate says every stored gross on all 180 bundles sits between `-1.709%` and `-0.091%`. The forensic lower bound (`-1.792%`) is slightly past that published minimum. The strategic result does not depend on those eight basis points: Cross-Pool gross is on the order of `-0.8%` or worse, which is about `$80` or more on a `$10,000` notional before the MEV haircut and the flash fee. Gas under `$0.53` cannot be the cause. **[EVIDENCE]** for the ranking economics. **[EVIDENCE]** for the forensic range as supplied. This audit did not recompute it from Mongo.

Quote decay: not proven. Competitor or MEV capture: not proven. Insufficient liquidity or TVL: not proven. Gate 8 did not run. The search floor `min_pool_tvl_usd = 100_000` is a config constant, not a measurement that these pools were too thin to hold an edge. **[EVIDENCE]**

Conclusion **DEPRIORITIZE_CROSS_POOL**. Same-protocol two-hop Uniswap V3 cycles in this window are structurally negative on the quote. Further search pruning, gas tuning, or MEV modelling inside this shape spends engineering on a loss that is already present before those terms.

---

## 5. Current bottleneck ranking

Ranked by how much each factor explains the certified losses, and by how much fixing it could change the next decision. MEV is not assumed to be the cause.

| Rank | Factor | Verdict |
|---:|---|---|
| 1 | Alpha, inside the routes that were exact-quoted | Binding. Gross `≤ 0` on 180/180 bundles. |
| 2 | Strategy design / search coverage | Binding as an unmeasured gap, not as a proven edge. 33,311 discoveries, 288 quotes, one hint source, blue-chip cycles. |
| 3 | Observability of the cost stack | Binding for interpretation. The `$50` MEV haircut is inside the decision net and absent from the bundle. 108 rows have no component economics. All BNB Gate-7 rows are in that 108. |
| 4 | Quote sampling throughput | Binding for any claim about “the market.” 32 claims per tick. |
| 5 | Quote quality | Not shown to be wrong. Exact size, status `ok`, on the certified worker. Still unreproduced against an independent quoter at the stored block. |
| 6 | Economics model (fees, gas) | Real and small next to negative gross, except the flat MEV penalty, which is a model constant. |
| 7 | Liquidity | Not measured. Gate 8 did not run. |
| 8 | RPC / data plane | Degraded during the window and not the cause of the negative gross on rows that did quote. |
| 9 | Execution latency | Not measurable. Nothing was signed or broadcast. |
| 10 | MEV / competitor capture | Not measured. The penalty in the net is a constant `0.5` points. |

### Alpha — rank 1

**[EVIDENCE]** Failure attribution on the 180 bundles is `gross_spread_insufficient`. Standalone fee, gas, slippage, or MEV drag was assigned to 0 rows, because no bundled row has positive gross. The best published gross is `-0.091%`. The best Cross-Pool gross is about `-0.84%` or worse. Published near-misses in other families are also negative on gross: Triangular `-$70.37` with gross `-0.200%`; a complex triangular Ethereum row `-$103.04` with gross `-0.403%`; Multi-Hop `-$114.82` with gross `-0.514%` and gas `$13.37`.

### Route search and strategy design — rank 2

**[EVIDENCE]** `RouteSearchEngine` is a depth-bounded DFS. Defaults in code: `max_hops=4`, `wall_clock_cap_s=5`, `candidate_cap=64`, `min_pool_tvl_usd=100_000`. The scanner claims 32 candidates per tick (`claim_batch`). The certified process moved from iteration 2 to iteration 10 inside the window and claimed the 288 Gate-7 rows. Every one of those 288 has `hint_source=flash_loan_route_search`.

**[EVIDENCE]** `route_search_wall_ms` and `route_search_candidates_explored` are copied into confirm-path metadata, not into the denial bundle. This window cannot show whether the 5-second cap or the 64-cycle cap truncated a profitable frontier. That specific search limitation is undemonstrated.

**[EVIDENCE]** The non-Base pool graph is a preferred-symbol list: WETH, WBNB, WMATIC, WBTC, BTCB, USDC, USDT, DAI, USDC.e, ARB, OP, wstETH, crossed with V3 fee tiers 500 and 3000, V2, and Algebra where a quoter exists. Curve and Solidly-style venues are excluded from that graph. Base has a separate curated registry that already lists stable pairs (USDC/USDT, USDC/DAI, USDC/USDbC) and LST pairs (WETH/wstETH, WETH/cbETH, WETH/weETH, WETH/rETH). Those pairs are not in the frequent paths of the 288.

**[INFERENCE]** The bottleneck beside negative gross is that verification sampled one discovery source and a handful of blue-chip cycles. Expanding hop depth or adding a scorer, before quoting the already-discovered unquoted strata, optimizes a search that has not been shown to be the thing that hid the edge.

### Observability — rank 3

**[EVIDENCE]** Phase 0 labels are computed in memory and not stored. Decision net text exists on all 288. Component economics exist on 180. MEV penalty percent, true-net percent, gross dollars, and the applied flash-loan bps are not on the denial bundle. Gates 8 and 9 never ran. The certification `run_id` is not a field on the candidate.

This blocks clean dashboards. It does not block the gross-sign conclusion, which is already stored.

### Quote quality — rank 5

**[EVIDENCE]** Certified bundles have `quotes.route_quote_status=ok`, `exact_size=true`, `size_basis=exact`, hop legs present. Certified `denied:venue_unreadable` stayed 0. The 480 unreadable rows belong to the other worker.

**[HYPOTHESIS]** A systematic quoter bias could print negative gross on fair pools. Nothing in the stored fields proves or disproves that. The census in section 22 starts by reproducing the stored gross at the stored block.

### Economics — rank 6

**[EVIDENCE]** L2 gas on the best rows is about `$0.18`. User forensic puts Cross-Pool gas at or below `$0.53`. Ethereum gas on published near-misses is about `$12.75` to `$13.37`. Flash fee is `$0`, `$5`, or `$30`. None of these close a hole of `-9` to `-180` basis points, and none of them created the hole.

The MEV term is different: it is large in dollars and it is not an observation. Treating `-$59` as “the market took fifty dollars” is a misread of a constant.

### Liquidity — rank 7

**[EVIDENCE]** Not proven insufficient. `depth_usd = 0` is the stored sentinel when TVL was not resolved. Gate 8, which would have tested `min_pool_tvl_usd_in_route = 100_000`, did not run. Search itself drops pools under `$100,000` TVL before enumeration. That filter can hide edge in smaller pools. It can also keep the book out of pools that cannot clear `$25`. Neither effect was measured.

### RPC — rank 8

**[EVIDENCE]** In-window log lines containing `429`: Arbitrum 664, Polygon 201, BNB 201, Ethereum 104, Optimism 23, Base 9. `failing over` warnings: 433, mostly `eth_getLogs -> 400`, plus one Polygon `eth_call -> 429`. Base and BNB produced no failover line in that slice. The certified scanner still wrote 180 exact quotes with negative gross. RPC stress is operationally real. It is not the explanation of those 180 losses.

### Execution latency and MEV — ranks 9 and 10

**[EVIDENCE]** `broadcast=false` on all 180. Rows emitted 0. Confirmed 0. No inclusion time, no landing block, no competing transaction, no quote-to-block decay pair. A latency or MEV program has no failure to explain yet.

---

## 6. Strategy opportunity ranking

Ordered for the next investigation after DEX→DEX and Cross-Pool are deprioritized. This is an information ranking. It is not a forecast of profit.

### 1. `TRIANGULAR` — next forensic, not a build

**[EVIDENCE]** 92 rows, 73 complete bundles, the largest bundle count. Best row `-$70.37` is the second-best net in the population (Arbitrum, `balancer_v2`, hop count 3, stored gross `-0.200%`). Worst row `-$1,709.90` is Optimism. Family mean `-$485.62` is the Optimism and Polygon tail. Arbitrum mean `-$146.19` (n=27). Ethereum mean `-$134.83` (n=9). Confidence `MEDIUM` on every row. All 92 carry secondary `CROSS_POOL`. Cross-protocol was not the primary: stored sequences are `uniswap_v3` repeated.

**[INFERENCE]** The family mean is the wrong summary. A chain-split gross table on the 73 stored bundles can be read without a new SHADOW. If Arbitrum and Ethereum bundles are negative gross in the same way as the published `-0.200%` best row, Triangular joins the deprioritize list. If one chain’s gross is near zero while another is `-5%` or worse, the next question is quote or inventory quality on the bad chain, not a new route scorer.

**[HYPOTHESIS]** Optimism and Polygon losses are a bad quote or a thin-pool artifact. Unproven. Gate 8 did not run.

### 2. `CROSS_PROTOCOL` — insufficient evidence, do not build

**[EVIDENCE]** Smallest family, n=8. Mean `-$183.40`, best `-$126.03`. The best row is decision-only, so its gross is unknown. Four bundles exist, all confidence `MEDIUM`. Chains: Polygon 4, Base 3, BNB 1. Shape `A→B→C→A`. Secondary tags `TRIANGULAR` and `CROSS_POOL` on all 8. The classifier’s reason is distinct per-leg protocols on three hops, after stable, LST, complex-triangular, multi-DEX, and two-hop DEX-to-DEX rules did not match. These 8 rows are not a stablecoin strategy. DEX→DEX’s secondary `CROSS_PROTOCOL` tag is a different set of rows.

**[INFERENCE]** Four bundles cannot support a family decision. A gross read of those four is cheap and worth doing inside the same stored-data pass as Triangular. It is not a reason to make Cross-Protocol LIVE 2.

### 3. `MULTI_HOP` — negative gross already visible on the best bundled row

**[EVIDENCE]** n=27, mean `-$196.91`, median `-$158.60`, best `-$114.82`. That best row is a complete Ethereum bundle, `balancer_v2`, gross `-0.514%`, gas `$13.37`, flash fee `$0`. Fifteen bundles, twelve decision-only. All confidence `MEDIUM`. Chains: Ethereum 15, BNB 6, Arbitrum 3, Polygon 3. Classifier: hop count 4 or more, not a 3-token cycle, per-leg protocols not distinct. Shape `A→B→C→D→A`.

**[INFERENCE]** On that best row the quote loss is about `$51` per `$10,000` before gas and before the `$50` MEV constant. Gas is real on Ethereum and still not the sign. Multi-Hop does not outrank Triangular for investigation. The median looks closer to zero than Cross-Pool because the sample mix differs, not because a positive gross was found.

### 4. `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` — large sample of deep losses

**[EVIDENCE]** n=83, mean `-$350.18`, best `-$142.90` (Arbitrum, `balancer_v2`, complete bundle). A published Ethereum near-miss has gross `-0.403%`, gas `$12.75`, net `-$103.04`. Forty-five bundles, thirty-eight decision-only. Shape `A→B→C→B→A`, distinct per-leg protocols, hop count greater than 3. Ethereum mean `-$582.57`. Arbitrum mean `-$216.50`.

**[INFERENCE]** Same pattern as Cross-Pool: the quote is already negative, and the shape is more expensive. Deprioritize as a LIVE candidate. Include it in the stored-gross forensic only to confirm the best Arbitrum bundle is negative on gross. Do not start a complex-route program from this sample.

### 5. `MULTI_DEX` — no economics to investigate

**[EVIDENCE]** n=34, mean `-$352.82`, best `-$153.86`, worst `-$889.60`. Complete bundles: 0. All confidence `MEDIUM`. Chains: BNB 20, Polygon 14. Decision net only. The label is still a real Phase 0 primary (hop count at least 3, not a 3-token cycle, distinct per-leg protocols).

**[INFERENCE]** There is nothing to refine. The missing object is a bundle, which is an observability gap concentrated on BNB and part of Polygon, not a signal that Multi-DEX is the hidden winner. Quoting a handful of these already-stored hints belongs in the census. Building a Multi-DEX engine does not.

### Families with no rows

**[EVIDENCE]** `STABLECOIN_CROSS_PROTOCOL` 0. `LST_LRT_CROSS_PROTOCOL` 0. The Phase 0 classifier attached no stablecoin note and no LST/LRT note. `strategy_tagging.py` would label an all-stable path `STABLECOIN` and any path touching `WSTETH`, `STETH`, `RETH`, `CBETH`, `WEETH`, and the rest of its LST set as `LST_LRT`. Those symbols were not on the stored paths of the 288.

---

## 7. LIVE 1 recommendation

**No. LIVE 1 is not justified.**

A family qualifies for LIVE 1 only if stored evidence shows repeated non-negative quote-inclusive gross, large enough that flash-loan fee plus gas plus the `$25` floor is covered, on exact-size quotes, with bundles, on the chain where it would trade. Existence in code, a classifier label, or a less-negative loss does not qualify.

| Family | Qualifies | Why |
|---|---|---|
| `DEX_TO_DEX` | No | Best gross about `-0.09%`. Best net `-$59.31`. |
| `CROSS_POOL` | No | Gross about `-0.8%` or worse on every complete row. |
| `CROSS_PROTOCOL` | No | n=8, best net `-$126.03`, best row has no gross. |
| `MULTI_HOP` | No | Best bundled gross `-0.514%`. |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | No | Best net `-$142.90`. Published gross on a near-miss `-0.403%`. |
| `MULTI_DEX` | No | No bundle. Best decision net `-$153.86`. |
| `TRIANGULAR` | No | Best gross `-0.200%`. Mean is the worst family. |
| Stablecoin | No | Zero classified rows. |
| LST/LRT | No | Zero classified rows. |

**[EVIDENCE]** missing for a yes:

1. One exact-size route with stored gross above zero.
2. The same route, or the same family, clearing flash fee and gas with the MEV penalty reported separately, so a pass is not an artifact of deleting the `0.5` point constant.
3. Repetition: more than a single block and a single notional.
4. Gate 8 actually evaluated on any row that cleared Gate 7, so liquidity is measured rather than assumed.
5. A chain and provider named by that evidence. The current best chain slice is still a loss.

**[EVIDENCE]** the October 4 window (256 Gate-7 rows, 0 passes, mean about `-$316`) is a second sample of the same sign under an earlier classifier. It raises confidence that this search distribution is stably unprofitable. It is not a proof that no other distribution exists.

---

## 8. LIVE 1A / LIVE 1B recommendation

Compare the three scopes against the evidence, then split 1A and 1B.

| Option | Scope | Decision |
|---|---|---|
| A | LIVE 1 = one strongest family | Correct shape, once a family qualifies. None does. |
| B | LIVE 1 = two or three families | No second family is even close to a qualification test. |
| C | LIVE 1 = the current broad set | Rejected. The broad set’s mean is `-$345`, and five of seven families are hundreds of dollars negative. |

**Recommendation:** Option A is the only scope that should ever open, and it stays closed.

- **LIVE 1A — do not open.** There is no strongest family in the profit sense. Running the least-negative loss (DEX→DEX) live would pay the quote loss plus gas plus flash fee, on Base, in a family the forensic already deprioritized.
- **LIVE 1B — reserved, not scheduled.** 1B is the first later window in which a single named family has passed the qualification test in section 7 on SHADOW quotes, still with no broadcast, and a separate explicit decision is made to arm signing. 1B is not “the rest of the families,” and it is not Stablecoin + Cross-Protocol by default.

**[HYPOTHESIS]** that a broad live book diversifies edge. The evidence shows a broad book diversifies losses.

---

## 9. Patch 1 recommendation

Patch 1 as a bundle of efficiency projects is not evidence-backed. The loss is present before the costs those projects would shrink.

| Item | Verdict | Label |
|---|---|---|
| Search pruning | Do not do it to find alpha. Pruning the current DFS would shrink a sample that is already all-negative, and it can drop the unquoted strata that have not been measured. | [INFERENCE] |
| Route generation | The generator already emits more candidates than the verifier quotes (33,311 versus 288). More generation is not the constraint. | [EVIDENCE] |
| Route scoring | No score is stored on the denial path, and the quoted set has no positive gross to train on. A scorer fit to this window learns to rank losses. | [EVIDENCE] |
| Liquidity-aware search | TVL floor `$100,000` already exists. Gate 8 never tested the quoted routes. Adding another liquidity heuristic does not explain negative gross. | [EVIDENCE] |
| Exact-size quoting | Already true on all 180 certified bundles. Do not rebuild it. | [EVIDENCE] |
| Quote freshness | One quote time per row. No paired later quote. Freshness work is a measurement (section 13), not a cache optimization. | [REQUIRES EXPERIMENT] |
| Quote batching | Could raise how many of the 33,311 get an exact quote. That is useful only as the transport for the census, not as a general throughput program. | [INFERENCE] |
| Gas estimation | L2 gas is cents to about `$0.53` on the deprioritized families. Ethereum gas near `$13` is real and still smaller than the negative gross on the published Ethereum near-misses. | [EVIDENCE] |
| Flash-loan fee awareness | Already in the assessor at `$0` / `$5` / `$30`. Balancer is the least-negative provider slice inside DEX→DEX and remains below zero. | [EVIDENCE] |
| MEV modelling | The current model is a flat `0.5` points on MEDIUM. Replacing it with a richer model, before any decay or competitor observation, changes a constant. It does not create gross. | [EVIDENCE] |
| RPC concurrency | 429s and failovers happened. Quotes that completed were still negative. Concurrency is an ops follow-up after the census, if the census is RPC-bound. | [EVIDENCE] |
| RPC failover | Failover already ran (433 warnings) under NEW A → NEW B → OLD A → OLD B. Leave the order alone. | [EVIDENCE] |
| Chain-specific tuning | Chain means differ, especially Triangular on Optimism and Polygon. Tune nothing until those bundles’ gross is read. The difference may be the quote, not a parameter. | [REQUIRES EXPERIMENT] |
| Opportunity deduplication | `candidate_id` changes every 60 seconds for the same route, so the queue refills with repeats. Dedup would change sampling. It is justified only as part of the census design, so repeats do not crowd out unquoted shapes. | [INFERENCE] |
| Route decay measurement | Not proven necessary. It is the measurement that would later justify MEV work. Instrument it inside the census. Do not build a decay trader. | [REQUIRES EXPERIMENT] |
| Competitor capture measurement | No competing transaction is stored. Do not build a capture model. | [EVIDENCE] of absence |

What is worth doing under a measurement budget, and is not Patch 1:

1. Read stored gross by chain for the 73 Triangular bundles and the 4 Cross-Protocol bundles. Data already exists.
2. Persist, on future rows only, the assessor fields that are already computed and dropped: `mev_penalty_pct`, `mev_adjusted_net_pct`, `gas_drag_pct`, applied flash-loan bps, and gross dollars. That is a copy, not a new formula.
3. Quote a stratified sample of candidates the last window did not verify.

Everything else on the Patch 1 list waits until one of those three names a binding constraint.

---

## 10. LIVE 2 recommendation

Stablecoin + Cross-Protocol is not the strongest LIVE 2 candidate on evidence, because there is no performance evidence. It remains one of the two best unmeasured hypotheses, together with an LST/LRT atomic pair, and it should be a quote panel inside the census rather than a build.

| Candidate | What the data says | LIVE 2 stance |
|---|---|---|
| Stablecoin + Cross-Protocol, as a combined program | `STABLECOIN_CROSS_PROTOCOL` count is 0. Measured `CROSS_PROTOCOL` (n=8) is a three-hop mixed-asset cycle with mean `-$183.40`, not a stablecoin book. | Do not build the combination. |
| Cross-Protocol alone | Measured, small, negative, incomplete bundles. | Deprioritize as a build. Finish the four-bundle gross read. |
| Stablecoin alone | Zero Gate-7 paths. Base registry already lists USDC/USDT, USDC/DAI, USDC/USDbC. Default triangular intermediates include USDC, USDT, DAI. Those cycles were not in the 288. | Highest-value unmeasured hypothesis. One-block exact quotes, not a new engine. |
| Multi-Hop | Best bundled gross `-0.514%`. | No. |
| Multi-DEX | No bundles. Decision nets `-$154` to `-$890`. | No, until a bundle exists and its gross is positive. |
| Complex triangular | Large negative sample. | No. |
| LST/LRT atomic subset | Zero Gate-7 paths. Base registry lists WETH against wstETH, cbETH, weETH, rETH. Classifier symbols include those names. | Co-equal unmeasured hypothesis with stablecoin. One pair, one block, exact quote. |
| Specialised venues | Curve and Solidly-style ABIs are intentionally outside the non-Base probe graph. | Hypothesis only. After the census of venues already registered. |

**[HYPOTHESIS]** Stablecoin peg dislocations and LST secondary-market discounts are where atomic edge still appears, because the certified book only stressed major volatile cycles that public searchers already flatten. **[REQUIRES EXPERIMENT]** before any LIVE 2 engineering. If both panels print negative gross at exact size, LIVE 2 moves to “no current candidate,” not to a larger build of the same idea.

Do not invent a profit number for either panel.

---

## 11. Route Search v2 timing

**Only after a specific search limitation is demonstrated.**

| Timing | Decision |
|---|---|
| Before LIVE 1 | No. LIVE 1 itself is not open, and a new searcher does not create gross on routes whose quotes are already negative. |
| Inside Patch 1 | No. Patch 1 efficiency work is not justified (section 9). |
| After LIVE 1 | LIVE 1 has no date. Do not sequence research behind a gate that has no qualifying family. |
| After Stablecoin / Cross-Protocol | No. Those are quote experiments, not a prerequisite architecture. |
| After a demonstrated limitation | Yes. This is the only timing that matches the evidence. |

A limitation that would justify Route Search v2:

- The census quotes the current graph, including stables and LST pairs already registered, at exact size, and gross is `≤ 0` across that set, and
- An explicit inventory gap is named (a venue family with a quoter we do not call, or a token pair absent from `_PREFERRED` / the Base registry) whose omission is the reason a known public dislocation could not have been expressed.

A limitation that would not justify v2:

- The 5-second cap or the 64-candidate cap. Both exist in code. Neither is stored on the denial bundles, so neither is demonstrated for this window.
- The 32-per-tick claim cap. That is a sampling policy. Fix the sample. Do not rewrite the enumerator.
- Negative gross on USDC/WETH/WBTC. That result argues for a different universe only after the rest of the current universe is quoted.

**[HYPOTHESIS]** deeper hops or a learned scorer would find edge the DFS missed. The quoted 4-hop families are the deepest losses in the window. Depth has been tried on the blue-chip graph and the stored result is worse.

---

## 12. Opportunity Intelligence / Learning requirements

Phase 0.5, as audited in `docs/certification/PHASE_0_5_OPPORTUNITY_LEDGER_ARCHITECTURE_AUDIT_20261005.md`, is a projection of rows that already exist. It is not a trading engine. The full ledger (identity, run link, UI, Excel, learning sample) does not answer “why did this opportunity fail?” for the 180 bundled rows. The gross sign already answers that, at the level the stored quote supports: the quoted cycle was worth less at the end than at the start.

Minimum evidence to answer the question, split by where it lives:

| Question | Already available | Available but not persisted | Requires implementation | Requires PAPER or execution |
|---|---|---|---|---|
| Did the quoted cycle have edge? | Gross % on 180 bundles, all `≤ 0` | Gross dollars | Copy gross dollars onto the bundle | No |
| Was the loss fees, gas, or the quote? | Gas $, flash fee $, slippage stored `0`, decision-net text on 288 | `mev_penalty_pct`, `gas_drag_pct`, `total_fee_pct`, applied flash bps, pre-penalty net | Copy those assessor fields. Do not recompute a second formula | No |
| Which strategy was it? | Derivable by `phase0.strategy_intelligence.v1` | The label itself | Persist the observation if a later run must be re-read without an offline join | No |
| Which run? | Time-window join to `shadowcert-5605e7b9-…` | `run_id` on the row | A copied run id when a run is closed | No |
| Was the quote stale or decayed? | One block, one `verified_at` | A second quote | A paired quote at block+1 on a frozen route | A SHADOW quote pair is enough. Broadcast is not |
| Did a competitor take it? | Nothing | Nothing | A block-tx join, keyed by pool and block | Chain data, still not our broadcast |
| Did liquidity fail? | Gate 8 `NOT_EVALUATED` | TVL that the gate would have used | Run Gate 8 only on a row that passes Gate 7 | No |
| Did inclusion fail? | `broadcast=false`, emitted 0 | — | — | Yes. PAPER or a later armed mode. Absent today, correctly |
| Would the learning ledger have predicted this? | It never saw these rows. Flash-loan Gate-7 denial does not write `arbicore_opportunity_journal` | — | An observe-only sample, after the economics fields exist | A survival label based on `would_survive` would misread a negative atomic profit |

**[EVIDENCE]** Normalized kill codes (`NO_GROSS_EDGE`, `GAS_KILLED`, `MEV_KILLED`, `QUOTE_DECAY`) are not canonical. The stored denial is one Gate-7 sentence. Inventing `GAS_KILLED` from a negative net would be false on this window.

Recommendation: do not block the census on Phase 0.5-C through 0.5-H. The one persistence change that changes a human conclusion is copying the already-computed penalty and the pre-penalty net so `-$59` is not read as a market loss. That copy is smaller than the ledger program. Learning weights stay observe-only. The 288 rows must not be pushed through `would_survive`.

The 108 decision-only rows, including every BNB Gate-7 row, cannot answer “why” beyond “the decision net was negative.” Their component fields are missing, not zero.

---

## 13. MEV evidence requirements

Do not treat competitors as the reason these opportunities failed. The stored label `MEDIUM` plus a default `0.5` point penalty is a policy constant. It was applied uniformly. It was not fit to this window.

| Claim | Evidence required before the claim is allowed | Present now |
|---|---|---|
| Quote decay | Two exact-size quotes of the same route, at block N and block N+1 (or discovery time and verification time), with both gross figures stored, and a defined threshold for “decayed.” | One quote. Not present. |
| State change | The pool’s sqrt price, tick, or reserves at the two blocks, stored next to those quotes, so a gross change has a state cause. | Not present. `price` on hop legs is stored null. |
| Competitor capture | A transaction in the intervening block that touches the same pools and moves the price in the direction that removes the edge, with a tx hash stored. Our transaction is not required for this claim. | Not present. |
| Execution latency | Timestamps for quote, signing, submission, and inclusion, on a path that actually submits. | Not present. SHADOW forbids the last two, correctly. |
| Inclusion failure | A submitted transaction that was not included, with the node error or the replacement. | Not present. Emitted 0, broadcast false. |
| MEV loss | A quote that was non-negative at decision time, and a realized result that is worse, with the difference attributed to ordering rather than to a wrong quote or a fee. | Not present. Decision-time gross is already negative, so there is no edge to lose to ordering. |

MEV engineering starts only after a paired quote shows gross positive at the first block and non-positive at the next, and a competing transaction in between is identified. Until that pair exists, MEV work has nothing to recover.

**[INFERENCE]** Zeroing the `0.5` point penalty on the best stored row leaves about `-$9`. The Gate-7 floor is `$25`. The penalty is worth reporting separately so it stops dominating the narrative. It is not worth a new model.

---

## 14. Six-chain specialization

The six chains should keep one economics kernel and one strategy classifier. Chain-specific models are premature. Chain-specific reads of the data already stored are not.

**[EVIDENCE]** All six chains reached Gate 7. All six have only negative decision nets. BNB has 45 Gate-7 outcomes and zero certified bundles. Optimism’s best Gate-7 net in the window is `-$192.19`. Polygon’s best is `-$156.50`. Arbitrum’s best is `-$70.37`. Base’s best is `-$59.31`. Ethereum’s best is `-$103.04`, with gas near `$13` on the published rows. Provider mix is Aave, Balancer, and Uniswap on five chains. BNB’s catalog support in code is Aave only.

| Knob | Now | Later, and only if |
|---|---|---|
| Route scoring | Shared. No scorer is evidenced. | One chain shows positive gross and another shows negative gross on the same shape. |
| Search depth | Shared cap of 4. Deeper hops were the worst means. | A census shows a 2-hop or 3-hop shape positive on one chain and absent from the graph on another. |
| Gas model | Shared formula, chain gas already differs (`ethereum` about `$8` base before unit scaling, L2s cents). | A row is positive on gross and fails only on gas. Not this window. |
| Liquidity thresholds | Shared `$100,000` search floor and Gate 8 floor. Gate 8 did not run. | A passing Gate-7 row fails Gate 8, or a chain’s TVL reads are systematically zero. |
| Quote cadence | Shared 60-second scanner interval. | Decay pairs show edge dying inside the interval on one chain only. |
| Provider selection | Already chain-aware in the catalog (no Balancer or Uniswap flash on BNB; Morpho listed for Ethereum and Base and unused, count 0). | A provider’s fee is the difference between pass and fail on a positive-gross row. |
| MEV model | Shared MEDIUM constant. | Section 13’s capture evidence exists, and it differs by chain. |

High-value, and not a new model:

- Persist bundles on BNB. Forty-five decision nets with no gross is a hole, not a BNB strategy.
- Read Triangular gross on Optimism and Polygon versus Arbitrum before any Optimism-specific parameter exists.
- Leave RPC order and failover as they are. Base was the healthiest host in the 429 count and still produced the best, still-negative, row.

**[HYPOTHESIS]** Polygon and Optimism need their own search. **[REQUIRES EXPERIMENT]** the stored gross split first. A special model in front of that read is premature optimization.

---

## 15. Future alpha candidates

Each row is a hypothesis unless the status column says otherwise. “Atomic” means one transaction can open and close the position. “Flash-loan compatible” means the borrow and the cycle can sit in that same transaction. “Architecture fit” means the current scanner, quote path, and Gate 7 could express it without a new settlement domain. Competition and defensibility are judgments, not measurements from the 288.

| Hypothesis | Atomic | Flash-loan | Measurable now | Simulatable with current quoter | Architecture fit | Infrastructure still required | Competition | Defensibility | Priority |
|---|---|---|---|---|---|---|---|---|---|
| Stablecoin imbalance (USDC/USDT/DAI and chain variants already in the Base registry) | Yes, if both legs are DEX swaps | Yes | Gross is not stored for these pairs | Yes, where a pool is in the registry and a quoter exists | High | None beyond a directed quote. Gate 8 still unused | High on majors | Low. Public, same-block | First census panel |
| Stablecoin cross-protocol (DEX versus a different pool type, still one chain) | Yes only if both venues settle in one tx | Yes if both are quoted | No rows | Only for venues the quoter already calls | Medium | A second venue adapter where the graph omitted it (Curve is omitted) | High | Low | After same-graph stable panel, if that panel is negative |
| Concentrated-liquidity dislocation (tick outside fair value) | Yes | Yes | Not identified in the 288 | Partially. A quote sees the impact. It does not store tick | Medium | Tick or liquidity-net storage if we need a cause, not for a first gross | High | Low without a faster trigger | Later. Gross census covers the symptom |
| Lending/DEX atomic (mint or redeem versus pool) | Sometimes. Depends on the lending market’s callback | Sometimes | No | No lending quote in the flash-loan path | Low today | Protocol adapter and a callback spec | Medium | Medium if the adapter is obscure | After DEX-only census |
| LST/LRT secondary-market atomic (WETH/wstETH and the Base LST list) | Yes for a pool-to-pool or pool-to-wrapper where the wrapper is a contract call in the same tx | Yes | No Gate-7 rows. Pairs exist on the Base registry | Yes for the pool leg. Wrapper rate needs a read | High for the pool-to-pool subset | Wrapper/redemption quote if the edge is versus NAV rather than versus a second pool | High on wstETH/WETH | Low on the liquid pair | Co-equal first panel with stables. One pair |
| Wrapper/unwrapper pricing, only where the unwrap is atomic | Yes when the contract unwraps in the same tx | Yes | No | Not as a DEX hop | Medium | Explicit unwrap leg. Fail closed if the unwrap is a queue | Medium | Medium on slow-queue tokens only if we do not trade the queue | Only the atomic subset. No withdrawal queues |
| Fee-tier arbitrage (0.01% / 0.05% / 0.3% / 1% of the same pair) | Yes | Yes | DEX→DEX sample is cross-venue, not a clean fee-tier pair. Base registry lists several Uni V3 tiers | Yes | High | Include tiers the non-Base graph skips (`100` and `10000` ppm are not in `_V3_FEE_TIERS`) | High | Low | Inside the census, same pair, three tiers, one block |
| Multi-pool fragmentation | Yes | Yes | Cross-Pool was this shape on Uni V3 and gross was about `-0.8%` or worse | Already simulated, and negative, for that slice | Already fit | A different pair than USDC/WETH | High | Low | Deprioritize the measured slice. Do not generalize |
| Temporary liquidity dislocation | Yes | Yes | Not observed. Would appear as positive gross that is gone at block+1 | The census can leave a second quote | Fit | Decay pair | The definition of competition | None if we are slower | Measure in the census. Do not build a trigger yet |
| Block-to-block price dislocation | Yes | Yes | Not observed as a positive | Same | Fit | Two blocks | High | None | Same measurement |
| Backrun-style arbitrage | Yes, but it is ordered behind a triggering tx | Yes | No mempool or backrun evidence | Not with a resting quote | Poor. Needs a pending-tx feed and a different scheduler | Mempool or a builder feed. That is an MEV program | Extreme | Low | Forbidden until section 13 is satisfied. Do not start here |
| Specialised stablecoin pools (Curve-style) | Yes | Yes | No | No. Those ABIs are outside the probe graph | Low until an adapter exists | Quoter adapter, then the same gross test | High | Low | After registered stables fail |
| Other protocol-specific atomic paths (Balancer pool versus a DEX, already a discovery source) | Yes | Yes | Balancer discovery wrote candidates. They are not a separate economics table in the 288. The 288 are `flash_loan_route_search` | Yes if claimed and quoted | Already wired as a source | Get it into the quote sample | High | Low | Include a few already-discovered Balancer hints in the census. Do not assume the source is empty of edge or full of it |

No row above is supported by a positive stored gross. Priority means “worth a quote,” not “worth a roadmap slot.”

---

## 16. Cross-chain boundary

Cross-chain stays a separate engine. Nothing in the 288 is a cross-chain opportunity. The flash-loan scanner enumerates single-chain cycles. A negative single-chain book is not evidence for or against bridging.

**[HYPOTHESIS]** that inventory laid across chains earns the basis that atomic search cannot. Unproven. Mixing it into LIVE 1 would add bridge risk to a book that has not shown a one-chain edge.

What a separate program has to measure before it is a build:

| Piece | Requirement |
|---|---|
| Price intelligence | A stored pair of executable prices on chain A and chain B at named blocks, including the size those prices are valid for. A mid-price spread is not enough. |
| Inventory | A stated starting inventory per chain, because the trade does not return the asset in one transaction. Flash-loan atomicity does not apply to the bridge leg. |
| Settlement | The bridge or messaging path actually used, with a measured time distribution, not a vendor slogan. |
| Bridge risk | A written loss mode: delayed message, wrong domain, liquidity cap, and the maximum principal exposed while the message is in flight. |
| Rebalancing | The cost and the time to restore the inventory, included in the profit model. A one-way transfer that strands inventory is not a completed trade. |
| Execution | Two transactions, two inclusion clocks, and a policy for what happens when the first lands and the second does not. |
| Profitability model | Gross basis minus source fee, destination fee, bridge fee, both gases, rebalance cost, and a haircut for failed completion. The `$25` atomic floor does not govern this. |

None of those fields exist on the certified flash-loan bundles. Do not estimate a cross-chain profit from this SHADOW.

---

## 17. Optimized master roadmap

The previous ladder assumed LIVE 1 was a set of existing flash-loan families, then efficiency, then Stablecoin + Cross-Protocol, then Route Search v2. The evidence breaks that ladder at the first step.

| Step | Name | What it is | Exit |
|---|---|---|---|
| 0 | Stop | No LIVE 1, no Patch 1 efficiency bundle, no MEV build, no Route Search v2, no cross-chain, no own-capital DEX book | This document |
| 1 | Stored forensic | Read gross, gas, flash fee, and chain for the 73 Triangular bundles, the 4 Cross-Protocol bundles, the 45 complex bundles, and the 15 Multi-Hop bundles. No new SHADOW | Each family either joins DEX→DEX and Cross-Pool as deprioritized, or a chain slice is flagged for the census |
| 2 | Census | Section 22. One block per chain, exact size, gross reported before the MEV penalty | A written pass/fail per panel |
| 3 | LIVE 1A, only if step 2 or step 1 produces a qualifying family | One family, one chain, SHADOW confirmation on a fresh window aimed at that family only | Repeated non-negative gross clearing fee, gas, and `$25`, penalty reported separately |
| 4 | Measurement patch | Only the constraint step 2 names: sampling, a missing quoter, bundle persistence on BNB, or the dropped assessor fields | The next window can answer “why” without a new strategy |
| 5 | LIVE 1B | Armed mode for that one family. Separate decision. Signing and broadcast stay out of steps 0–4 | Operator decision, not this audit |
| 6 | Next hypothesis | Whichever census panel was positive and was not the LIVE 1A family. If none were positive, specialised venues (one adapter) or stop | A new gross, not a roadmap habit |
| 7 | Route Search v2 | Only under the test in section 11 | A named inventory gap |
| 8 | Separate engine | Cross-chain, under section 16 | Its own price, inventory, and bridge measurements |
| Later | Own-capital DEX | Still later. Atomic flash-loan evidence does not transfer to inventory strategies | A different profit model |

Stablecoin and LST move from “LIVE 2 build” to “census panels.” If a panel is positive, it becomes the LIVE 1A candidate and the old families stay deprioritized.

---

## 18. Top 5 things to do

1. **Treat negative quote-inclusive gross as the result.** DEX→DEX and Cross-Pool stay deprioritized. Do not schedule them for live, paper, or another identical SHADOW. **[EVIDENCE]**
2. **Read the stored bundles that do not yet have a family gross table,** starting with Triangular by chain. The rows are already in `evidence_bundles`. **[EVIDENCE]** that the rows exist. **[REQUIRES EXPERIMENT]** only if that read is ambiguous.
3. **Run the section 22 census.** It is the smallest experiment that can still change the roadmap. **[REQUIRES EXPERIMENT]**
4. **Report pre-penalty net beside decision net** on any new quote, and copy `mev_penalty_pct` onto future bundles so the `$50` constant is visible. **[INFERENCE]** that this changes interpretation. **[EVIDENCE]** that the field is computed and dropped today.
5. **Keep the safety posture.** SHADOW, no signing, no broadcast, Gate floors unchanged, RPC order unchanged, until a qualifying family exists and a separate decision arms anything. **[EVIDENCE]** that the current posture held through the certified run.

---

## 19. Top 5 things not to do

1. Do not open LIVE 1 on the current family set, and do not open it on “the least negative family.”
2. Do not run another generic 30-minute SHADOW of `flash_loan_route_search` and read the mean again. The distribution is known.
3. Do not start MEV, backrun, or latency engineering. Capture has not been observed, and the quotes are negative before ordering.
4. Do not build Route Search v2, a route scorer, or six chain-specific models to repair a gross that is already negative.
5. Do not build Stablecoin + Cross-Protocol, LST/LRT, or cross-chain as engineering programs before a quote panel shows positive gross. Do not lower the `$25` floor to manufacture a pass.

---

## 20. Biggest assumption we should stop making

**That an implemented family is a candidate for production because it is implemented, and that the least-negative loss is the one to optimize.**

**[EVIDENCE]** Seven families were fully classified. Seven means are below `-$94`. The family closest to zero is negative on gross. The roadmap’s “proven existing flash-loan families” used “proven” for presence. Presence was achieved. Profit was not.

The second assumption to retire, because it will otherwise replace the first: **that competitors are taking the edge.** **[EVIDENCE]** there is no edge in the stored quotes to take, and no competitor transaction on file. The MEDIUM penalty is ours.

---

## 21. Most important missing measurement

**Quote-inclusive gross, in percent and in dollars, before the MEV penalty, on a stratified set of routes this window did not verify, at a named block, plus a reproduction of the stored gross on the best DEX→DEX and best Triangular rows at their stored blocks.**

**[EVIDENCE]** the 180 bundled grosses answer the question for the routes that were quoted. **[EVIDENCE]** they do not answer it for `flash_loan_triangular` (7,128 discoveries), `flash_loan_generic_dex` (1,800), stablecoin pairs, LST pairs, fee tiers outside the quoted sequences, or any BNB route. **[EVIDENCE]** decay, liquidity-as-cause, and competitor capture are also missing, and they are second: they explain a disappearance of edge, and this file does not yet contain an appearance of edge.

---

## 22. Minimum next experiment

Do not run another unchanged 30-minute SHADOW.

**Name:** one-block stratified quote census.

**Posture:** read-only quotes. No signing, no broadcast, no Gate change, no scanner resume, no config write. Gross is recorded before `mev_penalty_pct` is applied. Decision net may be computed beside it, with the penalty shown as its own column.

**Design:**

| Panel | What is quoted | What a result means |
|---|---|---|
| R, reproduction | The best stored DEX→DEX route and the best stored Triangular route, at the block already on the bundle, same notional | If gross matches the stored figure, the quoter is stable for those rows and quote quality is not the bug. If it does not match, stop and fix quote identity before any strategy work. |
| S, size | Those same two routes at the same block, two other notionals (smaller and larger than the stored borrow) | If all three notionals are gross-negative, size is not the missing edge on these routes. If one size is gross-positive, the binding issue is size search, and only for routes that already sit near zero. |
| U, unquoted sources | A capped sample of `flash_loan_triangular` and `flash_loan_generic_dex` hints from the certified window that have no Gate-7 outcome, exact-sized at one fresh block | If gross is negative, those sources are not a hidden book of edge. If any gross is positive after flash fee and gas, the binding issue is claim sampling (32 per tick from `flash_loan_route_search`), not a new enumerator. |
| T, universe already registered but absent from the 288 | One stable-stable cycle per chain where the registry has both legs (Base first: USDC/USDT, USDC/DAI). One LST pool cycle where registered (Base WETH/wstETH). One same-pair fee-tier cycle (two Uni V3 tiers of WETH/USDC). | Positive gross names the LIVE 1A hypothesis. Negative gross retires that hypothesis for that block and that size. |
| D, decay | Only routes in S, U, or T whose first gross is non-negative. Re-quote at the next block. | Still non-negative: edge survived one block, which is the first decay evidence we would have. Turned non-positive: record the state change. Competitor capture still requires a tx hash in that block. Do not infer it from the price move alone. |

**Caps:** one block per chain, a few dozen quotes per panel, not a 30-minute loop. The point is stratification, not volume.

**Fail the alpha question** if panels R, U, and T are gross-negative at every quoted size. That result supports genuine absence of edge inside the current registry, at that block. It still does not support MEV engineering.

**Fail the “search was enough” question** if panel U or T shows a positive gross the 288 never contained. The fix is then to quote that stratum, not to deepen DFS on USDC/WETH/WBTC.

**Fail the quote-quality question** if panel R does not reproduce.

**Liquidity** stays unclaimed unless a positive-gross route appears. Then quote it at the size and record whether the quoter itself rejected the size. Gate 8 can be evaluated offline against stored TVL only after a Gate-7-passing gross exists. Do not lower either floor.

**Out of scope for this experiment:** Route Search v2, new venue adapters, backrun feeds, cross-chain, PAPER, LIVE, and any change to Gates 7, 8, or 9.

---

## 23. Explicit evidence gaps

1. No positive gross, at any size, on any family, in the certified window. **[EVIDENCE]** of the gap.
2. No family-level gross table in the ranking document for Triangular, Multi-Hop, Cross-Protocol, or complex triangular. Near-pass rows cover only the least-negative tail. **[EVIDENCE]** that the tail is negative. The body of each family is not reprinted here.
3. Cross-Pool forensic range `-0.837%` to `-1.792%` was supplied to this audit and not re-aggregated from Mongo. The population stored range is `-1.709%` to `-0.091%`. The deprioritize conclusion stands on either figure.
4. 108 Gate-7 rows have no bundle. All 45 BNB rows are in that set. Multi-DEX is entirely in that set.
5. MEV penalty percent is inside the decision net and absent from the bundle. Pre-penalty dollars in section 2 are an inference from the published formula and the near-pass components, not a fresh database recomputation.
6. Search wall-clock and candidate-cap hit counts are not on the denial bundles.
7. Gate 8 and Gate 9 did not run. Liquidity and MEV-class rejection are untested as causes.
8. No second quote, no competing transaction, no inclusion, no PAPER fill.
9. Stablecoin and LST/LRT economics: no rows.
10. Morpho Blue: catalogued, count 0 in this window.
11. Section 7 of the 288 economics analysis disagrees with the ranking’s family statistics. The ranking is the authority for means and best-rows.
12. Two windows (4 October and 5 October) agree on sign and disagree in classifier vocabulary. They are not a long sample. They are not a volatility-regime study.
13. This audit did not open MongoDB, did not resume a scanner, and did not reproduce a quote. Panel R is still undone.

---

## 24. Final recommendation

If this were the company’s money, the next dollar of engineering would not go to LIVE 1, Patch 1, Route Search v2, an MEV stack, or a Stablecoin + Cross-Protocol implementation.

It would go to two reads that the current certification already paid for, and one small quote census that the certification did not perform:

1. Deprioritize DEX→DEX and Cross-Pool. Say so in the roadmap. The gross is negative before costs. **[EVIDENCE]**
2. Finish the same gross forensic, from stored bundles, for Triangular by chain, then the four Cross-Protocol bundles. Expect this to deprioritize more families. If it does, accept that. **[EVIDENCE]** the bundles exist. **[INFERENCE]** the chain split in the means is large enough to require the gross, not a new model.
3. Run the one-block census in section 22. Reproduction first, then unquoted discovery sources, then one stable panel and one LST panel that the registry can already express. Judge those panels on gross before the MEV penalty. **[REQUIRES EXPERIMENT]**
4. Open LIVE 1A only for a single family that passes section 7. Until then the master roadmap’s first line is “no live family.” **[EVIDENCE]**
5. Leave cross-chain, backrun, own-capital, and six-chain specialization off the critical path. **[HYPOTHESIS]** that they matter later. They are not the binding constraint today.

The certified system is doing what it was built to do: detect, quote, and refuse unprofitable atomic cycles without signing. The strategic error would be to optimize that refusal, or to trade it, instead of asking whether any other cycle in the registry has a positive quote.

**Classification: STRATEGIC_AUDIT_COMPLETE**
