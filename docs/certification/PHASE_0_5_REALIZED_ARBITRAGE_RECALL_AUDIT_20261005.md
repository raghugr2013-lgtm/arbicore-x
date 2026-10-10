# Phase 0.5 — Realized arbitrage ground-truth and search-recall audit

**Classification: PARTIAL**

**Date:** 2026-10-05

**Mode:** read-only. No source edit, configuration change, RPC topology change, MongoDB write, scanner control, SHADOW start, deploy, restart, signing, or broadcast.

**Requested predecessor:** `docs/certification/PHASE_0_5_REMAINING_FAMILY_GROSS_EDGE_AUDIT_20261005.md` is not in this worktree. The closed inputs used instead are the 2026-10-05 SHADOW documents for `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065`.

| Input | Result used |
|---|---|
| SHADOW run | `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065` |
| Gate-7 population | 288 evaluations, 180 complete m2.3 bundles, 108 decision-only |
| Stored decision nets | 0 positive, 0 at or above $25, best `-$59.31` |
| Stored gross spread on the 180 bundles | max `-0.091%`, all `≤ 0` |
| Prior ranking | `DEPRIORITIZE_CURRENT_STRATEGY_UNIVERSE`, LIVE 1 = NO-GO |

This audit asks whether that result is the market, the search, the economics, the clock, or the sample. It does not change the strategy universe.

---

## Scope

In scope:

- How the current flash-loan search, quote, and Gate 7 path works, from this worktree plus the certified image’s Phase 0 classifier.
- A stratified historical log sample of singleton flash-loan events on public RPCs.
- A 46-receipt classification and route-coverage sample.
- One full token-net check of the largest stablecoin inflow in that sample.

Out of scope, and not done:

- Production code, configuration, RPC, database, deploy, restart, signing, broadcast.
- A complete multi-day census of every atomic arbitrage on six chains.
- Historical quoter replay of a captured route.
- A size sweep or a both-directions quote at historical state.
- Polygon and BNB multi-hour windows. The crawl was stopped before those chains were written.

---

## Method

### What “realized” means here

A transaction is in the census only when a singleton flash-loan log was emitted by a contract address already in the ArbiCore source:

| Provider | Contract | Event |
|---|---|---|
| Aave V3 | per-chain pool in `provider_liquidity.py` | `FlashLoan(address,address,address,uint256,uint8,uint256,uint16)` |
| Balancer V2 | `0xBA12222222228d8Ba445958a75a0704d566BF2C8` (absent on BNB) | `FlashLoan(address,address,uint256,uint256)` |
| Morpho Blue | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` (Ethereum, Base) | `FlashLoan(address,address,uint256)` |

A flash-loan log is not classified as arbitrage by itself.

Receipt classes, applied only when the rule is met. Otherwise `UNKNOWN`.

| Class | Rule | Confidence |
|---|---|---|
| `LIQUIDATION` | same-transaction Aave `LiquidationCall` | HIGH |
| `CROSS_PROTOCOL` | at least two of UniV3-family `Swap`, UniV2 `Swap`, Balancer `Swap`, Curve `TokenExchange`, and at least two swaps | MEDIUM. The V3 topic is shared by forks, so the DEX name is not proven. |
| `OTHER` | flash-loan log and zero recognized swap logs | MEDIUM that it is not a recognized DEX swap. It can still be an AMM this topic list does not know. |
| `DEX_TO_DEX`, `CROSS_POOL`, `TRIANGULAR`, `MULTI_HOP` | not assigned | The swap topic does not carry the token path. Two pools with the same swap topic cannot be split into DEX-to-DEX versus cross-pool. Three swaps are consistent with a triangle and are still `UNKNOWN`. |
| `BACKRUN` | not assigned from a receipt alone | Transaction index is recorded separately. |

### Window

Seven clock hours, plus the certified SHADOW window. This is a sample of those slices, not every block from 2 October through 5 October.

| Slice | UTC |
|---|---|
| 1–7 | `2026-10-02T00`, `T12`, `2026-10-03T00`, `T12`, `2026-10-04T00`, `T12`, `2026-10-05T00`, each 60 minutes |
| SHADOW | `2026-10-05T05:27:48Z` through `2026-10-05T05:58:04Z` |

Completed with zero log gaps: Ethereum, Arbitrum, Base, Optimism.

### Route recall

For up to two swap-pool addresses on a sampled receipt, `token0`, `token1`, and `fee` were read at `latest`. Token identity of a pool does not depend on the historical price. The label is whether that pool sits in the current graph:

- Non-Base: both symbols in the chain registry and fee in `{500, 3000}` (the tiers `build_pool_graph` emits).
- Base: the pair and fee appear in `base_venues.VENUES`.

`YES` was not awarded. The three `PARTIAL` labels mean only that an inspected pool used a registry token and a searched fee. They are not closed cycles at the realized size. See the recall section.

### Profit

Stablecoin inflow is `ESTIMATED` only under a 1:1 peg, and only as an inflow. It is profit only when every other token net on that address is dust or zero. One candidate failed that test and is reported in full.

### Public RPC endpoints used

These were research calls. They were not written into Network Config.

| Chain | Endpoint | Historical logs | Historical contract code |
|---|---|---|---|
| Ethereum | `https://rpc.mevblocker.io` | yes, including the 2 October hour | yes, at block `26100914` |
| Arbitrum | `https://arb1.arbitrum.io/rpc` | yes | no. `missing trie node` / historical state unavailable |
| Base | `https://mainnet.base.org` | yes | yes |
| Optimism | `https://mainnet.optimism.io` | yes | yes |
| Polygon | not completed | `1rpc.io/matic` allows about 50 blocks per `eth_getLogs`. The hour crawl was stopped. | not established |
| BNB | not completed | a separate recent probe of 100, 300, and 800 blocks on `bsc-rpc.publicnode.com` returned 0 Aave logs and no error. `bsc-dataseed` has no archive trie. | no |

Uniswap V3 `Flash` logs were queried without an address filter for the last 200 blocks on the four completed chains. Each query returned 0. That is not a finding that pool-level flashes are absent. Several public nodes refuse or empty a topic-only scan. Pool-level flash arbitrage is therefore **not measured**.

---

## Phase 1 — Current search architecture

**Classification: PASS** as a description of the code. Nothing was changed.

Certified SHADOW image for the economics already on record: `arbicore-x-backend:phase0-823a79b`, commit `823a79b617ddb1f19397cf5073b9c516aae4e9fd`. Phase 0 classification lives in that image at `/app/arbicore/observability/taxonomy.py` (`phase0.strategy_intelligence.v1`). It is not in this worktree. The worktree classifier `classify_strategy` is a different vocabulary and does not label the 288 denials.

### 1. Candidate discovery

`FlashLoanArbitrageScanner._tick` runs only when the scanner is enabled. Each tick refreshes measured TVL, then calls every discovery source and upserts candidates. It then claims at most 32 rows and verifies them one by one.

Sources from `build_all_flash_loan_sources`:

| Source | Candidates |
|---|---|
| `flash_loan_route_search` | every closed cycle the DFS returns, crossed with each enabled provider that supports the chain |
| `flash_loan_provider_health` | none |
| `flash_loan_generic_dex` | 2-hop cycles only |
| `flash_loan_triangular` | 3-token cycles |
| Balancer V2 discovery | Balancer pools, separate from the pair graph |

The certified window’s discovery mix, from the 2026-10-05 SHADOW report, was `flash_loan_route_search` 24,383, `flash_loan_triangular` 7,128, `flash_loan_generic_dex` 1,800. The ranked 288 Gate-7 rows were all `flash_loan_route_search`.

### 2. Pool selection

`RouteSearchEngine.search` loads the chain graph, drops pools under `min_pool_tvl_usd` (default `$100,000`), drops pools that fail `hop_quote_capable`, then DFS.

Graph builders store `tvl_usd=0` until `pool_tvl_propagation` writes a measurement. An unmeasured pool stays out.

- Base: the curated `VENUES` list in `base_venues.py`. Uniswap V3, Aerodrome Slipstream, Aerodrome classic. Not the combinatorial pair product.
- Other chains: `discovery/multichain_venues.py`. Every pair among the preferred symbols that exist in the registry, for each quotable DEX.

Fee tiers emitted off Base: `500` and `3000` ppm only. `100` and `10000` are not in that list. Base’s curated list does include `100` and `10000` on specific pairs.

Excluded from the probe graph even when the registry names them: Velodrome (`solidly`), Curve (`curve`). The file says those families have no live quoter adapter in this graph.

`hop_quote_capable` keeps a pool only when a quoter backend has a contract for that DEX and chain.

### 3. Token pairs

Preferred symbols: `WETH`, `WBNB`, `WMATIC`, `WBTC`, `BTCB`, `USDC`, `USDT`, `DAI`, `USDC.e`, `ARB`, `OP`, `wstETH`. A symbol is used only when the chain registry contains it.

Base adds `cbETH`, `USDbC`, `cbBTC`, `AERO`, `rETH`, `weETH`, `DEGEN` through the curated list, not through the multichain preferred list.

Borrow tokens for route search default to `USDC`, `USDT`, `WETH`, `DAI`. A cycle is emitted only if it starts and ends on the borrow token being searched. `WBTC`, `WBNB`, `OP`, `ARB`, and the LST symbols are intermediate hops when a preferred pair exists. They are not default borrow starts.

### 4. Route directions

Each pool is one undirected node. DFS may leave through either token. A pool cannot be reused inside one cycle. The reverse of a cycle is a different walk. It is found only if the DFS reaches it before `candidate_cap` (default 64) and `wall_clock_cap_s` (default 5 seconds). There is no second pass that explicitly quotes `B → A` after `A → B`.

### 5. Trade size

One notional per verification. Flash-loan config default is `default_notional_usd = 10_000`. The scanner passes that into the verifier unless the hint overrides it.

`ExactSizeBorrowSizer` converts that single USD figure to integer wei with an on-chain price, rounding down. The certified bundles were stamped `exact_size=true` and `size_basis=exact`.

`select_borrow_size` can choose among several evaluated sizes. The live scanner does not call it. The verifier quotes one size.

If the sizer is absent, the quote is a probe (`200` units for 6 decimals, `0.05` for 18 decimals) and the verifier denies with `size_not_quoted`. The certified window had no `size_not_quoted` denials on the Gate-7 set.

### 6. Quotes

`QuoterRegistry.quote_route` calls the DEX quoter or router with `eth_call` at block tag `latest`.

| Backend | Chains |
|---|---|
| Uniswap V3 QuoterV2 | Ethereum, Arbitrum, Optimism, Polygon, Base, BNB |
| Sushi V3 | Arbitrum |
| Pancake V3 | BNB |
| Sushi V2 router | Ethereum |
| Camelot V3 (Algebra) | Arbitrum |
| QuickSwap V3 (Algebra) | Polygon |
| Aerodrome Slipstream and classic | Base |
| Balancer V2 `queryBatchSwap` | Ethereum, Base, Arbitrum, Optimism, Polygon. Requires a pool id or pool address. Not BNB. |

A route is returned only when every hop is `ok`, the path is closed, and both the input and the final output are positive. Gross percent is `(final_out - amount_in) / amount_in`, in the borrow token’s own units.

### 7. Quote freshness

The quote cache TTL on `QuoterRegistry` is 5 seconds. `probe_freshness` (default max age, and block lag default 5) lives in `live_readiness_probes.py`. `FlashLoanOpportunityVerifier.verify` does not call it. Freshness is “whatever `latest` was at the `eth_call`.”

### 8. Block state

Quotes use `latest`. There is no historical block argument on the verifier path. The search cannot ask for the state before a triggering transaction.

### 9. How often discovery runs

`interval_s` default 60. The certified scanner’s in-process counter moved 2 → 10 across the ~30 minute window, eight increments while the window was open, consistent with that interval. Each tick verifies at most 32 candidates. The same window discovered 33,311 rows. Most discovered rows were not verified inside the window.

### 10. Deduplication

`make_candidate_id` is SHA-1 of source, type, subject, asset, sorted venues, and `floor(hint_observed_at / 60)`, truncated to 20 hex characters. `upsert_many` inserts only when the id is new (`$setOnInsert`). The same route in the same minute does not create a second row. The next minute is a new id. Claim locks are not overwritten mid-flight.

### 11–13. Venues, protocols, tokens

Chains enabled in the certified run: Ethereum, Arbitrum, Base, Optimism, Polygon, BNB.

Providers enabled on that run, from the stored Gate-7 mix: `aave_v3`, `balancer_v2`, `uniswap_v3`. Morpho Blue is in the catalog for Ethereum and Base and was **not** in the 288. BNB has no Balancer V2 and no Uniswap V3 flash in the catalog’s `supports_chains` for those two providers. BNB’s catalog provider in the 288 was Aave only.

### 14. Incomplete bundles

`aggregate_economics` computes gross dollars, slippage dollars, MEV penalty percent, and MEV-adjusted net. `_build_evidence_bundle` stores gross percent, flash-loan fee dollars, gas dollars, slippage percent, and `atomic_profit_usd`. It does not store gross dollars, DEX fee dollars, slippage dollars, gas price, or the MEV penalty. Phase 0 therefore marks economics completeness `PARTIAL` on all 180 bundles that otherwise have a full route. That is a storage gap, not a second population.

### 15. Decision-only rows

`_finalize` writes the bundle inside a try/except that swallows every exception and still returns the Gate-7 outcome. A denied candidate can therefore carry `verified_outcome` and have no `evidence_bundles` row. The certified window had 108 such rows: all 45 BNB, 35 Polygon, 25 Base, 3 Arbitrum, 0 Ethereum. This audit did not re-read Mongo and does not name the exception. The code path that allows the split is the swallowed sink error. The prior audit is the source of the counts.

### 16. Phase 0 strategy classification

`classify_route` assigns a primary family only when every hop has an explicit protocol and the token path is a closed cycle. The flash-loan provider is not a protocol. Pool ids are not parsed into a protocol.

Priority: `LST_LRT_CROSS_PROTOCOL`, `STABLECOIN_CROSS_PROTOCOL`, `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` (triangular and cross-protocol and hop count > 3), 3-hop triangular cross-protocol → `CROSS_PROTOCOL`, same-protocol triangle → `TRIANGULAR`, then `MULTI_DEX`, `MULTI_HOP`, `DEX_TO_DEX` (exactly 2 hops, 2 tokens, 2 protocols, 2 pools), same-protocol 2-hop → `CROSS_POOL`.

On the 288, the prior ranking was `TRIANGULAR` 92, `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` 83, `MULTI_DEX` 34, `CROSS_POOL` 27, `MULTI_HOP` 27, `DEX_TO_DEX` 17, `CROSS_PROTOCOL` 8. Stablecoin and LST/LRT primaries were 0. All 288 decision nets were negative. `DEX_TO_DEX` was the least negative family (mean `-$94.96`, best `-$59.31`).

### 17. Gate 7 economics

`FlashLoanGate7AtomicProfit` passes only when `atomic_profit_usd ≥ 25`. The certified floor was `$25` on all 288. All 288 failed. Gates 8 and 9 were not evaluated because the verifier returns at the first failure.

`atomic_profit_usd` is `expected_profit_usd` from `aggregate_economics`:

- gross percent comes from the live quote
- pool swap fees are not deducted again when `gross_is_quote_inclusive=True` (the live path)
- flash-loan fee bps are deducted
- gas dollars are converted to a percent of notional
- slippage percent is added (stored `0` on the 180)
- MEV penalty percent is subtracted. Atomic quotes are scored with `is_atomic=True`, which adds 8 to the score, and hot assets (`WETH`, `ETH`, `WBTC`, `BTC`, `USDC`, `USDT`) add 5. With the default congestion of 30, that score is in the MEDIUM band. MEDIUM’s default penalty is `0.5` percent of notional.

On a `$10,000` notional, 0.5 percent is `$50`. The best stored gross was `-0.091%` (`-$9.10` at `$10,000`) and the best decision net was `-$59.31` on Base with Balancer (catalog flash fee 0). Those two facts sit next to each other. The stored gross percent was already negative. The MEV penalty can explain a large part of the distance from that small negative gross to the decision net. The MEV penalty dollars were not stored. This paragraph is the formula, not a recomputation of the 180 rows.

### 18. L2 data fees

`evm_gas.py` and `compute_true_net_profit` can price OP-stack `getL1Fee` and Arbitrum `getL1BaseFeeEstimate`. `FlashLoanOpportunityVerifier` does not call that path. Gate 7 uses `FlashLoanEconomicsAssessor`, which does not add an L1 data fee.

### 19. Flash-loan fees

Included. Catalog defaults: Aave 5 bps, Balancer 0, Uniswap V3 30 unless the verifier overrides the tier, Morpho 0. The 180 bundles stored flash-fee dollars from `$0` to `$30` (mean `$8.47`), which matches 0, 5, and 30 bps on a `$10,000` notional. The applied bps field on the bundle is the quote override coerced with `or 0`, not the catalog rate. The prior audit marked the applied rate `AVAILABLE_NOT_PERSISTED`.

### 20. Gas

`DEFAULT_PER_CHAIN_GAS_USD` is a static table: Ethereum `$8.00`, BNB `$0.40`, Arbitrum `$0.30`, Base `$0.15`, Optimism `$0.15`, Polygon `$0.05`. If the quote returns `tx_gas_units`, that table value is multiplied by `tx_gas_units / 250_000`. It is not `gas_used × gas_price × native_usd`, and it is not chain-specific L1 calldata. Stored gas on the 180 bundles was mean `$2.47`, max `$13.37`. Gas did not create the negative gross. The gross percent was already negative before gas.

### 21–23. Exact size, both directions, multiple sizes

Exact size: yes, one size, on the certified bundles. Both directions: only as DFS happens to enumerate them before the cap. Multiple sizes: not in the live verifier.

### 24–27. Blocks retained

| Field | Retained |
|---|---|
| Quote block | yes, on the 180 bundles: `quotes.quote_block` and `block_context.block_number`, the block the node used for `latest` |
| Quote timestamp | `verified_at_ts` / `verified_at`. No separate per-hop quote time. |
| `first_seen_block` | no such field |
| Verification block | the quote block above. There is no second block after a re-quote. |
| Execution or realization block | no. `broadcast=false` on all 180. Confirmed count 0. |

---

## Phase 2 — Historical data available without touching production

**Classification: PARTIAL**

Available, and used:

- Public `eth_getLogs` for the singleton flash-loan contracts on Ethereum, Arbitrum, Base, and Optimism, for the eight slices above, with zero recorded gaps.
- `eth_getTransactionReceipt` for 46 of those transactions.
- `token0` / `token1` / `fee` at `latest` for inspected pools.
- Historical contract code at the start of the window on Ethereum, Base, and Optimism.

Missing:

- Archive state on the Arbitrum endpoint (`historical state is not available`). A pre-block `eth_call` quote on Arbitrum cannot be done there.
- A completed Polygon hour sample. The public endpoint that answered `eth_getLogs` caps a request at about 50 blocks. The crawl was stopped.
- A completed BNB multi-hour sample. One recent probe, not the seven-hour design, returned 0 Aave logs over 800 blocks (~6 minutes at the measured 0.45 s block time). Archive trie is missing on the dataseed that was probed.
- Uniswap V3 pool `Flash` events, Balancer-free capital arbs, private-orderflow bundles that never emitted these singleton logs, and any searcher who borrowed from a pool rather than Aave, Balancer, or Morpho.
- Production Mongo was not re-read. SHADOW counts are taken from the existing certification documents.

No production RPC was added. No figure below was filled in by scaling the sample up to a full day.

---

## Phase 3 — Realized flash-loan census

**Classification: PARTIAL**

Denominator: flash-loan logs inside the eight slices, on the four completed chains. Not all arbitrage. Not six chains.

| Chain | Aave V3 | Balancer V2 | Morpho Blue | Slice total | SHADOW slice |
|---|---:|---:|---:|---:|---:|
| Ethereum | 37 | 165 | 903 | 1,105 | 65 |
| Arbitrum | 53 | 22 | n/a | 75 | 5 |
| Base | 34 | 145 | 3,581 | 3,760 | 313 |
| Optimism | 3 | 692 | n/a | 695 | 74 |
| Polygon | — | — | — | not completed | not completed |
| BNB | — | — | — | not completed | not completed |
| **Four chains** | **127** | **1,024** | **4,484** | **5,635** | **457** |

The SHADOW column is the same ~30 minutes in which ArbiCore recorded 0 positive stored gross and 0 opportunities at or above `$25`. On these four chains that window contained **457** singleton flash-loan logs. The 30-minute clock was not an empty flash-loan tape.

Borrow asset, when the address is in the ArbiCore registry. `unregistered_asset` means the borrowed token is outside that registry.

| Chain | Largest registered asset | Count | Unregistered |
|---|---|---:|---:|
| Ethereum | WETH | 785 | 61 |
| Arbitrum | WETH | 37 | 0 in the top list |
| Base | WETH | 2,544 | 23 |
| Optimism | WETH | 291 | 3 |

### Receipt sample

46 receipts. Spread across the slices, plus a few from the SHADOW slice. One receipt can carry one class.

| Class | Ethereum | Arbitrum | Base | Optimism | Total |
|---|---:|---:|---:|---:|---:|
| `LIQUIDATION` | 0 | 0 | 0 | 0 | 0 |
| `CROSS_PROTOCOL` | 0 | 0 | 1 | 0 | 1 |
| `OTHER` | 6 | 4 | 4 | 2 | 16 |
| `UNKNOWN` | 6 | 6 | 7 | 10 | 29 |
| `DEX_TO_DEX` / `CROSS_POOL` / `TRIANGULAR` / `MULTI_HOP` / `BACKRUN` | 0 | 0 | 0 | 0 | 0 |

`UNKNOWN` is the correct class for most of the sample. The swap events do not prove the token cycle. `OTHER` means no UniV2, UniV3-family, Balancer, or Curve swap topic was present. Aerodrome, Algebra-specific topics, V4, and aggregators can sit in `OTHER`. They were not forced into an arb family.

Transaction index of the flash-loan log:

| Chain | Index 0 | Index > 0 |
|---|---:|---:|
| Ethereum | 14 | 1,091 |
| Arbitrum | 0 | 75 |
| Base | 0 | 3,760 |
| Optimism | 0 | 695 |
| **Total** | **14** | **5,621** |

`5,621 / 5,635` of the sampled flash-loan logs were not the first transaction in their block.

---

## Phase 4 — Realized profit

**Classification: INSUFFICIENT_EVIDENCE** for USD profit.

No sampled receipt was promoted to a realized USD profit. Gas is observed in native units. Native-to-USD was not priced at the historical block, so gas USD is unknown.

### Checked candidate

`0x5de969970cc155755f81f3a483616ed2cd18443661532d134391280a5c686ef6`

| Field | Value | Class |
|---|---|---|
| Chain | Arbitrum | OBSERVED |
| Block | `510988470` | OBSERVED |
| Status | success (`0x1`) | OBSERVED |
| Transaction index | 2 | OBSERVED |
| From | `0xdabb085cc23511dfc1153707b6640ac23325639d` | OBSERVED |
| To | `0xa5679c4272a056bb83f039961fae7d99c48529f5` | OBSERVED |
| Flash provider | Aave V3 | OBSERVED |
| Borrow asset | USDC | OBSERVED |
| Borrow amount | `29,648.817515` USDC | OBSERVED from the event amount |
| Event fee word | 0 as decoded | OBSERVED word. A 5 bp Aave premium would be about `14.82` USDC. A zero word means the layout or the premium needs a second decoder before it is treated as a real zero fee. |
| USDC net, from-address | `+35,540.667878` | OBSERVED |
| Other token net, from-address | `-40,000` of `0xe3254397…` (18-decimal display) | OBSERVED units. Symbol and USD price were not read. |
| Contract `to` nets | no non-zero balance in the decoded transfers | OBSERVED |
| Gas | `3,044,756` gas | OBSERVED. Native USD not priced. |
| Two inspected pools | WBTC/USDC fee 500, and WBTC/WETH fee 500 | OBSERVED at `latest` |
| Realized USD profit | not established | The USDC inflow is paired with a 40,000-unit outflow of another token. |

Smaller stable inflows in the same 46 (Optimism dust at `0.001707` USDC and `0.000001` USDC/USDT, Ethereum `0.122546` USDC on a Morpho transaction that also touched a non-registry token and fee tier `100`) were not given a full multi-token net. They are inflows, not profits.

---

## Phase 5 — Would current ArbiCore have discovered the sampled transactions?

**Classification: PARTIAL**

Denominator: 46 receipts, not 5,635 logs, and not the market.

| Automated label | Count |
|---|---:|
| `YES` | 0 |
| `NO` | 24 |
| `PARTIAL` | 3 |
| `UNKNOWN` | 19 |

`NO` reasons: `missing_pool` 14, `missing_token` 10.

The three `PARTIAL` rows are not discovery hits.

| Transaction | Why the label is not a hit |
|---|---|
| Ethereum `0xac118eafe4…` | One recognized swap. Inspected pool is WBTC/USDT fee 500. The flash asset was USDC. A single pool is not a closed cycle. |
| Arbitrum `0x5de969970c…` | Two pools, two different pairs (WBTC/USDC and WBTC/WETH), both fee 500. Two hops do not return to USDC. |
| Optimism `0xd5903ac67a…` | Inspected pair USDC/OP fee 500. Borrow size about `10.96` USDC. Not shown as a closed two-pool cycle inside the searched graph. |

Failure taxonomy for the 24 `NO` rows plus these three:

| Cause | Evidence |
|---|---|
| `missing_token` | Pool `token0` or `token1` is outside the chain registry. Count 10 on the automated label. |
| `missing_pool` | Tokens are known and the fee is outside the searched set. Off Base that set is `{500, 3000}`. Observed misses include fee `100` (Ethereum WBTC route) and fee `12` (Optimism USDC/USDT). Count 14. |
| `missing_route` | The inspected hops do not form a closed cycle on `USDC` / `USDT` / `WETH` / `DAI`. The three `PARTIAL` rows. |
| `wrong_trade_size` | The live path quotes one notional. It was not re-quoted at the realized size. Not separately proven. |
| `timing` | Quotes are `latest`, once a minute, 32 verifications per tick. Not proven by a pre-block quote. |
| `quote_unavailable` / `strategy classifier` / `TVL filter` / `Gate 7` | Not re-run on these receipts. Gate 7’s behavior on the certified 288 is already known: every stored gross percent was negative, so Gate 7 was not the first filter that removed a positive quote. |
| Provider coverage | Morpho Blue is `4,484 / 5,635` of the slice logs and was absent from the certified Gate-7 provider mix. |

`0 / 46` would have been discovered as a closed, in-graph cycle on the evidence collected. That fraction is the receipt sample only.

---

## Phase 6 — Recall metrics

**Classification: PARTIAL.** Percentages below use the stated denominator. They are not market shares.

| Metric | Numerator | Denominator | Result |
|---|---|---|---|
| Opportunity recall (`YES`) | 0 | 46 receipts | `0 / 46` |
| Opportunity recall, closed-cycle even if labeled `PARTIAL` | 0 | 46 | `0 / 46` |
| Venue / pool recall | 14 `missing_pool` among rows that identified a pool | 46 | not a venue-universe rate. 14 identified pools were outside the fee set. |
| Token recall | 10 `missing_token` | 46 | 10 receipts touched a non-registry token on an inspected pool |
| Direction recall | — | — | not measured. No reverse quote was run. |
| Size recall | — | — | not measured. One size was not compared at historical state. |
| Strategy-family recall | 1 receipt labeled `CROSS_PROTOCOL`, 0 of the structural families | 46 | family of the on-chain transaction is `UNKNOWN` for 29. Cannot divide. |
| Economic recall | — | — | no historical quote, so no match against Gate 7 dollars |
| Timing recall | 14 logs at transaction index 0 | 5,635 flash logs | `14 / 5,635` were first in the block. This is not “ArbiCore would have been in time.” |

---

## Phase 7 — Pre-block replay

**Classification: INSUFFICIENT_EVIDENCE**

Historical code reads succeeded on Ethereum (block `26100914`), Base, and Optimism. That shows those three endpoints can see bytecode at the start of the window. It is not a quote.

No captured route was re-quoted at block `N-1`, `N`, and `N+1`. The receipt sample did not yield a same-pair, two-pool, fee-distinguished cycle to feed the Uniswap QuoterV2. Arbitrum’s endpoint cannot serve that state.

A forward quote at today’s `latest` was not used as a substitute.

What this separates:

- “ArbiCore’s 30-minute run stored no positive gross” is an observed fact about the routes it quoted at `latest`.
- “ArbiCore could not have seen the flash-loan transactions in this census, because those routes are outside the graph or the provider set” is supported for the inspected `NO` rows and for Morpho as a provider.
- “The spread existed in block `N-1` and was gone after the searcher’s transaction” was not tested.

---

## Phase 8 — Size sweep

**Classification: INSUFFICIENT_EVIDENCE**

Historical pool state was not quoted at small, medium, and large sizes. The production sizer remains a single notional. The code fact is that a route profitable only at another size is invisible to the live verifier. This sample does not measure how often that happens.

Observed sizes, not a sweep:

- Arbitrum Aave borrow on the checked transaction: `29,648.82` USDC, against a default search notional of `$10,000`.
- Optimism sample borrow: about `10.96` USDC.

---

## Phase 9 — Both directions

**Classification: INSUFFICIENT_EVIDENCE** for historical routes.

The engine can traverse a pool in either direction. It does not schedule the reverse cycle after the forward one. The candidate cap can drop the reverse before it is emitted. No historical `A → B` versus `B → A` quote was run, so this audit does not show a profitable reverse that the DFS missed.

---

## Phase 10 — Timing and block boundary

**Classification: PARTIAL**

Proven:

- Discovery interval default 60 seconds. The certified window’s iteration counter matches that cadence.
- Verification batch is 32 candidates per tick, against 33,311 discoveries in the same window.
- Quotes read `latest`, not the block before a trigger.
- `5,621 / 5,635` sampled flash-loan logs have transaction index greater than 0. On Arbitrum, Base, and Optimism the count at index 0 is 0.

Not proven:

- That the opportunity existed before the triggering transaction.
- That it survived into the next block.
- That block-boundary lateness is why the certified gross percents were negative. Those gross percents were properties of the routes ArbiCore actually quoted. The census routes are a different set.

The index distribution is evidence that these flash loans are packed after other transactions in the same block. A once-a-minute read of `latest` does not sample that intra-block state. That is a structural timing gap. It is not, by itself, the explanation of the stored negative gross.

---

## Phase 11 — Competition

**Classification: PARTIAL**

Repeated recipients, from the flash-loan `target` / recipient field. Share is of the slice logs, not of all arbitrage.

| Chain | Unique recipients | Top recipient | Top count | Top share |
|---|---:|---|---:|---:|
| Ethereum | 201 | `0x950fd558f47e234a2fde23b7d61f7ccdbcb4a86f` | 128 | `128 / 1,105` |
| Arbitrum | 20 | `0xdecc46a4b09162f5369c5c80383aaa9159bcf192` | 31 | `31 / 75` |
| Base | 137 | `0x5b4ea31806d25ad4a4657b1c5405f52ed7f4ef53` | 501 | `501 / 3,760` |
| Optimism | 5 | `0xe2b9a54fdbb7d46a6eb1b3a4f9488bc178ca4612` | 540 | `540 / 695` |

Optimism in this sample is one recipient on most Balancer flashes. That is repeated capture by one contract, on this log type, in these hours. It is not a measurement of how many searchers tried and lost.

Base and Ethereum have many recipients. The largest is about 12–13 percent. Combined with almost every log sitting after transaction index 0, the picture is many contracts landing inside the block, not one monopoly and not an empty tape.

| Chain, this sample | Concentration reading |
|---|---|
| Optimism | HIGH for this Balancer-heavy slice. One contract, `540 / 695`. |
| Arbitrum | MEDIUM. One contract, `31 / 75`, and the slice is small. |
| Ethereum, Base | Many contracts. Top share about 12 percent. Same-block index is the stronger fact. Not labeled EXTREME. |

No repeated pool-route was established. Receipt classification did not recover stable routes.

---

## Phase 12 — Opportunity TAM

**Classification: INSUFFICIENT_EVIDENCE** for dollars.

Flash-loan counts in the slices are observed. They are not a profit TAM. Scaling eight slices to 24 hours, or converting counts to USD, is not done.

What the counts do support:

- During the certified 30 minutes, Ethereum, Arbitrum, Base, and Optimism together emitted 457 Aave, Balancer, or Morpho flash-loan logs.
- Morpho Blue is the bulk on Ethereum (`903 / 1,105`) and Base (`3,581 / 3,760`).
- Optimism’s slice is almost entirely Balancer (`692 / 695`).
- The asset, when registered, is mostly WETH, then USDC or USDT.
- Dollar profit of that flow was not measured.

Polygon and BNB have no completed slice, so they are absent from this table on purpose.

---

## Phase 13 — Gap map

| Gap | Evidence | Impact | Confidence | Recommended future work |
|---|---|---|---|---|
| Morpho Blue not in the certified provider mix | `4,484 / 5,635` slice logs are Morpho. The 288 Gate-7 rows had zero Morpho. | The largest observed flash-loan source on Ethereum and Base is outside the run that was ranked. | HIGH | Read-only census of Morpho receivers. Do not enable it in production in this task. |
| Fee tiers `100` and `10000` off Base, and dynamic fees such as `12` | 14 receipt pools failed the searched fee set. Optimism USDC/USDT fee `12` was observed. | Same-pair fee-tier gaps are a standard arb surface and are not enumerated off Base. | HIGH | Research graph of the tiers that actually appear in receipts. |
| Tokens outside the registry | 10 receipts, plus 61 unregistered Ethereum borrow assets in the log census. | Those pools cannot enter the DFS. | HIGH | Measure which unregistered tokens repeat, before adding any. |
| Curve, Velodrome, and most Balancer pools are not in the pair DFS | Code: `solidly` and `curve` are omitted. Balancer quoting needs an explicit pool id. | Cross-protocol flow that uses those venues is invisible to route search. | HIGH | Keep them out until a quoter exists. Do not invent pools. |
| One notional, no size sweep | Verifier quotes `default_notional_usd` once. Checked borrow was `~$29.6k` and `~$11`. | A size the DFS never quotes cannot pass Gate 7. | HIGH as a code fact. LOW as a measured miss rate. | Historical size sweep on an archive node, research only. |
| Quote at `latest`, once a minute, 32 verifications | Code plus certified counters. `5,621 / 5,635` logs have index `> 0`. | Intra-block state is not what the scanner reads. | HIGH for the mechanism. MEDIUM that it explains the negative stored gross. | Pre-block and post-block quotes of a few same-pair cycles. |
| L1 data fee absent from Gate 7 | `compute_true_net_profit` is not on the verifier path. | L2 net can be mis-stated. It does not explain negative gross percent. The quote itself was negative. | HIGH | Compare Gate 7 gas with `evm_gas` on the same 180 bundles, read-only. |
| MEV penalty of 0.5 percent at MEDIUM | Code. Penalty dollars were not stored. Best gross `-0.091%`, best net `-$59.31`. | Decision net is harsher than quote gross. Gross was still `≤ 0` on all 180. | HIGH for the formula. MEDIUM for the dollar split. | Persist the penalty. Do not change the floor here. |
| Decision-only bundles | Sink exceptions are swallowed. 108 rows, including all BNB Gate-7 rows. | BNB economics cannot be audited from bundles. | HIGH for the code path. MEDIUM for the per-chain cause. | Log the sink exception. Do not backfill. |
| Unrecognized swap topics | 16 `OTHER`, 29 `UNKNOWN` in 46 receipts. | Family recall cannot be computed. | HIGH | Decode the other topic0 values before naming a family. |
| Polygon and BNB historical windows | Crawl stopped. BNB recent 800 blocks showed 0 Aave logs. | No TAM and no recall for those chains. | HIGH that the window is missing. | A 50-block Polygon design and a chunked BNB design, still read-only. |
| No archive replay | Arbitrum state unavailable on the public endpoint. No same-pair cycle was quoted at `N-1`. | Cannot yet split “search missed it” from “it existed only inside the block.” | HIGH | Ethereum or Base archive quote, a handful of transactions. |

---

## Phase 14 — Strategic diagnosis

Multiple labels apply. Ranked by how directly the evidence supports them.

| Rank | Class | Why |
|---|---|---|
| 1 | **C. COVERAGE** | Morpho dominates the observed flash-loan tape and was not in the certified mix. Inspected pools fall outside the registry or outside fees `{500, 3000}`. Curve and Velodrome are not in the pair graph. |
| 2 | **D. TIMING** | `5,621 / 5,635` flash logs are not first in the block. The scanner quotes `latest` on a 60-second tick and verifies 32 rows. Intra-block state is outside that loop. Pre-block survival was not proven. |
| 3 | **A. SEARCH** | DFS caps (64 cycles, 5 seconds), TVL floor, and the 32-row claim against 33,311 discoveries mean the engine never looks at most of what it already emits. Direction and size are single-pass. |
| 4 | **B. ECONOMICS** | On the routes that were quoted, stored gross percent was `≤ 0` on all 180 bundles. Gate 7 did not reject a positive quote. L1 data fees are omitted and the MEV penalty widens a negative. Those are real accounting gaps. They are not the source of the negative gross. |
| 5 | **E. COMPETITION** | Repeated contracts, especially Optimism `540 / 695`. Many recipients on Base and Ethereum. This is capture by existing searchers, not a count of failed attempts. |
| 6 | **F. MARKET OPPORTUNITY** | Rejected as “the 30 minutes were empty.” 457 singleton flash loans landed on four chains during the certified window. Not established as a dollar TAM. |
| 7 | **G. INSUFFICIENT EVIDENCE** | USD profit, size sweep, reverse-direction quotes, pre-block replay, Polygon, BNB, and pool-level Uniswap flashes. |

The certified conclusion `DEPRIORITIZE_CURRENT_STRATEGY_UNIVERSE` still matches the routes ArbiCore actually priced. This audit does not replace that with “the market has no atomic arbitrage.” It replaces “maybe the half hour was quiet” with a flash-loan tape that was not quiet, on a provider and a pool set the current search does not cover.

---

## Phase 15 — Decision gate

1. **Did we find real profitable atomic arbitrage?** We found executed flash-loan transactions. We did not establish USD profit. The largest stable inflow was paired with a 40,000-unit outflow of another token.

2. **How much?** Dollar profit: unknown. Flash-loan log count in the sample: **5,635** on four chains across eight slices, of which **457** fall in the certified 30 minutes.

3. **Which families?** Not established on chain. Receipts: `UNKNOWN` 29, `OTHER` 16, `CROSS_PROTOCOL` 1. The certified ArbiCore families remain the prior ranking, all with negative decision nets.

4. **Which chains?** Measured: Ethereum, Arbitrum, Base, Optimism. Base had the most slice logs (3,760), mostly Morpho. Polygon and BNB were not finished.

5. **Which protocols?** Morpho Blue, Balancer V2, Aave V3, in that order of log count. Swap protocols were not reliably named.

6. **Could current ArbiCore discover them?** `YES` on `0 / 46` receipts. `NO` on 24 because of token or fee tier. 19 unknown. 3 automated `PARTIAL` labels are not closed cycles.

7. **Why not?** The inspected pools and the Morpho provider are outside the current graph and the certified provider set. Separately, the scanner does not read intra-block state.

8. **What kind of problem?** Coverage first, then timing and search breadth. Economics of the routes that were quoted are negative before the debate about fees. Competition is visible. A missing market is not what the flash-loan logs show. Dollar alpha of those logs is still unproven.

9. **What to build next?** Not a live executor. The next research cut is a read-only archive replay of a few same-pair cycles on Ethereum or Base, plus a receipt decoder for the swap topics that are currently `OTHER`, plus a Morpho and fee-tier coverage count. No production change.

10. **Does this justify changing the roadmap?** It justifies keeping the current universe deprioritized. It does not justify a new strategy family, a Gate change, or live trading on the basis of this file.

---

## Recommended next experiment

**Classification of this recommendation: not implemented.**

Read-only, on a public or archive endpoint that is not a production RPC:

1. Take 10 Ethereum or Base receipts whose swap pools are the same pair at two fee tiers.
2. Quote both directions at block `N-1`, `N`, and `N+1` with QuoterV2, at the realized size and at `$10,000`.
3. Record gross in the borrow token. Price gas only if the native USD at that block is read from a pool, and label it `ESTIMATED`.
4. Decode every topic0 on the 16 `OTHER` receipts before naming a family.
5. Run the Polygon sample as 50-block windows. Run BNB in chunks small enough for the public node.

Stop conditions: if `N-1` is not quotable, write `INSUFFICIENT_EVIDENCE` again. Do not substitute `latest`.

---

## Data sources

- This worktree: flash-loan scanner, route search, discovery sources, verifier, economics, Gate 7, quoter registry, chain registries, Base venues, discovery queue, evidence sink.
- Certified image `arbicore-x-backend:phase0-823a79b`, read-only container, file `/app/arbicore/observability/taxonomy.py`. The image was not started as the production server.
- Prior documents listed below.
- Public RPCs listed in Phase 2. Production Network Config was not read and not modified.
- `/tmp/census2.json` on the operator machine holds the four-chain sample. It is not a production record.

## Limitations

- Singleton flash loans undercount atomic arbitrage that flashes from a Uniswap pool or uses its own inventory.
- Eight slices are not a full three days.
- Polygon and BNB are incomplete.
- `PARTIAL` route labels from the first automated pass over-called coverage. The report corrects them.
- Profit USD is not claimed.
- No code was changed.
