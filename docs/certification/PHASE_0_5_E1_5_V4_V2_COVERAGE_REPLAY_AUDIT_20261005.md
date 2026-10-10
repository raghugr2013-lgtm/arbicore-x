# E1.5 — Uniswap v4 / v2 coverage replay

Gate: `E1.5_V4_V2_COVERAGE_REPLAY_READ_ONLY`  
Date: 2026-10-05  
Mode: read-only. No production code, configuration, database, container, or execution change.

Evidence labels used below: **PROVEN**, **RECONSTRUCTED**, **OBSERVED**, **ESTIMATED**, **INFERRED**, **HYPOTHESIS**, **NOT_PROVABLE**, **NOT_AVAILABLE**.

---

## 1. Executive Summary

The nine Ethereum transactions in the E1 recall subset were re-read from receipts, internal value transfers, and historical `eth_call` quotes. The coverage gap is real. The large dollar figures in E1 are not net arbitrage profit.

**PROVEN:** Eight of the nine transactions touch the Uniswap v4 PoolManager at `0x000000000004444c5dc75cB358380D2e3dE08A90`. That venue is not in the ArbiCore route graph or quoter. One transaction, and one leg of a second transaction, uses Uniswap v2 pairs whose factory is `0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f`. The live v2 quoter is SushiSwap’s router only.

**PROVEN:** The E1 “WETH profit” on the v4 rows is the ERC-20 residual after a flash-loan borrow and repay. It does not subtract the native ETH paid into the v4 pool. That payment is a `WETH.withdraw`, which emits `Withdrawal` and an internal ETH transfer, and does not emit `Transfer`. The withdrawn ETH is forwarded to the PoolManager. Counting only `Transfer` logs therefore books the gross output of the last hop as if the input had been free.

After that correction, using the transaction’s own WETH/USDC spot:

| What was measured | Result |
|---|---|
| v4 round trips clearing $25 after venue costs and gas | **0** |
| v4 round trips profitable at a $10,000 quote | **0** of those quoted |
| Searcher-kept profit after the observed coinbase payment, any row | **none at or above $25** |
| Pre-block cycle above $25 before the builder payment | **1**, the Uniswap v2 TRUMP bridge, and only near 0.3 ETH, not at $10,000 |

That one v2 cell is about **$25.5 after gas and before the builder payment** at the previous block, conditional on the same 1% bridge used in the transaction. At $10,000 it is largely negative. In the realized transaction the builder was paid about $30 and the searcher kept about $3.

The separated 718.89 WETH credit is an Aave collateral withdrawal net of a 13,254.985 WETH Morpho flash loan. A paired transaction in the same block moves a matching WETH amount the other way. It is not an arbitrage profit and it is not a sizing target.

Uniswap v4 is a **demonstrated coverage gap**. It is **not** a demonstrated Gate 7 alpha candidate on this corpus. Uniswap v2 is a **demonstrated coverage gap** with **one narrow, size-sensitive, competition-captured cell** that is not an implementation case.

| Decision | Result |
|---|---|
| E1.5 v4 status | `INSUFFICIENT_EVIDENCE` for alpha. Exact replay of these rows rejects the large-profit reading. |
| E1.5 v2 status | `PROMISING_BUT_UNPROVEN` |
| Next gate | `ADDITIONAL_REPLAY` |
| Implement v4 or v2 now | **NO** |

---

## 2. E1 Evidence Used

Source: `docs/certification/PHASE_0_5_REALIZED_ARBITRAGE_RECALL_AUDIT_20261005.md`.

Used without substitution:

- The eight Ethereum rows with reconstructed ERC-20 WETH surplus at or above $25, plus the separated 718.89 WETH credit. That is the nine-row corpus.
- The window those rows sit in: Ethereum blocks 26,125,444 through 26,125,744, 2026-10-05T10:02:47Z through 2026-10-05T11:02:47Z.
- E1’s statement that in-universe recall on this subset was 0/9, and that the quoter has no Uniswap v4 backend and no Uniswap v2 factory.

Not re-derived here: the six-chain flash census, the 21,868 multi-pool count, and the 896 uncertain flash receipts. This gate does not convert those into a global recall rate. **NOT_PROVABLE**, same as E1.

E1 priced every row at one Uniswap v3 spot, $2,717.20 per WETH at block 26,125,650. This replay prices each row from the same pool, `0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640`, at that row’s own block. The spots fall between **$2,713.31 and $2,717.71**. **RECONSTRUCTED.** The gap versus E1 is under 0.2% and does not move a v4 row across $25. The one near-threshold v2 figure below uses the row’s own spot.

`debug_traceTransaction` is still rejected on this host (`-32600`, free tier). **PROVEN**, rechecked. Internal ETH was read with `alchemy_getAssetTransfers` on the same Alchemy Ethereum host. That call returned. It is not a trace, and it is not a new provider.

---

## 3. Exact 9-Row Corpus

All nine are Ethereum, status success. Sender is `tx.from`. The contract that holds the residual is `tx.to`, except the 718 WETH credit, which arrives at `tx.to` from helper `0x76f30e3f75437fb862b8d2c4d80a671bceba5b1a`.

E1 classification for every row: outside the current quoter universe. Joined stored ArbiCore candidates: 0. **PROVEN** by E1 and unchanged here, because this gate did not turn the scanner on.

| # | Hash | Block | Time (UTC) | Index | From | To |
|---|---|---:|---|---:|---|---|
| 1 | `0x751d8e1256ba4cf835739dcb8e49c90c8cf1d573667adad49e832427df11c59b` | 26,125,602 | 10:34:23 | 91 | `0xdc6d1ddb5d4e165a2a40cc04575f808def85dfb6` | `0x824a78cd1c450e80f9d4744707fe29b8e0f7e0f5` |
| 2 | `0x502a3acf11a95159e17f624b04594eb6516ea92b0a2360fc112b3f1478bcfd78` | 26,125,593 | 10:32:35 | 21 | `0x30a1b724c9dfe2e12a19ed84878312d199d1519e` | `0x50d3865a63d52c0a54e4679949647ea752107390` |
| 3 | `0x5d81ec37acc4fb25301b7b7de27ef19a08ccb5341464008668df7e0210da61b7` | 26,125,702 | 10:54:23 | 16 | `0xa969ddb25b32075d9d1ab8ce5db418f995290207` | `0x950fd558f47e234a2fde23b7d61f7ccdbcb4a86f` |
| 4 | `0xa455f188ab15a190bacac1219e340fcc017f6a6269b2ea926e3131b8a1f6dd72` | 26,125,494 | 10:12:47 | 4 | `0x49efa792645b523ef3b47b27ede7c7469220ed1d` | `0x78dcc4a041eda70fa946458e98c7436f9e7fb25e` |
| 5 | `0x3a8abd0f8a75b37038b26328aa959259b03a0df3f031a65af90dec6b894814dc` | 26,125,610 | 10:35:59 | 82 | `0x6c14f56559d10bf2f6d59ae2ac06c09b37f203a7` | `0xd35804a63f13a1eccf0aeb6b5c403fbe3e22cd01` |
| 6 | `0x56aebfc40b80ea483c6129b1c01066964f5de9aeb81ceb4b2c1837ec41270127` | 26,125,683 | 10:50:35 | 122 | `0x6c14f56559d10bf2f6d59ae2ac06c09b37f203a7` | `0xd35804a63f13a1eccf0aeb6b5c403fbe3e22cd01` |
| 7 | `0x3f3987bdd1ffa138c2fe2cc5ed93a2457352f0bd21478e8c88f4a6a7ad7207ac` | 26,125,650 | 10:43:59 | 8 | `0x30a1b724c9dfe2e12a19ed84878312d199d1519e` | `0x50d3865a63d52c0a54e4679949647ea752107390` |
| 8 | `0x8bfecc1587d2419c27c12fbc6b8268ca1790828787da3b4886fd88e7072f2d6e` | 26,125,589 | 10:31:47 | 293 | `0x31189ef74cd427c846ed92014f113e5c2e074bb3` | `0x09903191782e111c5d1f16759eb671ba181ad710` |
| 9 | `0x082d6331aa0e454adf4a9740ec41a4ca711903e76039724fbe6b6de5f083593c` | 26,125,453 | 10:04:35 | 11 | `0x654fae4aa229d104cabead47e56703f58b174be4` | `0x000000000035b5e5ad9019092c665357240f594e` |

Rows 2 and 7 share the searcher EOA and the contract. Rows 5 and 6 share a different EOA and contract. **OBSERVED.**

E1 ERC-20 net, versus the corrected cycle surplus (native ETH in, flash fee, gas; builder payment shown separately). Corrected figures are **RECONSTRUCTED** from logs plus internal transfers. Spots are **RECONSTRUCTED**.

| # | E1 net USD | What E1 counted | Corrected surplus before builder tip, after gas | Searcher kept after tip and gas | WETH spot |
|---|---:|---|---:|---:|---:|
| 1 | 2,502.99 | 0.92187 WETH left on `tx.to` by `Transfer` logs | **+$0.10** | **−$0.19** (the $0.30 tip is larger than the after-gas spread) | 2,715.32 |
| 2 | 349.58 | 0.12876 WETH | **$32.97** (about $30 TRUMP v2, about $3 v4/v3) | **$2.97** | 2,716.30 |
| 3 | 142.01 | 0.05236 WETH | **$0.09** | **$0.05** | 2,715.81 |
| 4 | 86.23 | 0.03179 WETH | **$0.70** | **$0.24** | 2,717.39 |
| 5 | 62.50 | 0.02311 WETH | **$0.79** | **$0.60** | 2,715.15 |
| 6 | 43.08 | 0.01595 WETH | **$0.31** | **$0.26** | 2,715.96 |
| 7 | 37.59 | 0.01391 WETH | **$37.59** realized; **$12.02** at the previous block’s best size | **$3.39** realized | 2,713.31 |
| 8 | 34.60 | 0.01275 WETH | **$0.10** | **$0.04** | 2,717.71 |
| 9 | ~1.95M, separated | 718.88793 WETH | not an arb surplus | not an arb surplus | 2,717.20 |

Flash loans, all premium **OBSERVED** as zero on the decoded event:

| # | Protocol | Amount | Fee |
|---|---|---:|---:|
| 1 | Morpho Blue | 0.9217651462611579 WETH | 0 |
| 2 | Morpho Blue | 1 WETH exactly | 0 |
| 3 | Morpho Blue | 0.052256845187997864 WETH | 0 |
| 4 | Balancer v2 | 0.0314733333157761 WETH | 0 |
| 5 | Morpho Blue | 0.025211668919793475 WETH | 0 |
| 6 | Morpho Blue | 0.017486190162529225 WETH | 0 |
| 7 | Morpho Blue | 1 WETH exactly | 0 |
| 8 | Balancer v2 | 0.012691828385393917 WETH | 0 |
| 9 | Morpho Blue, to the helper, not to `tx.to` | 13,254.985100677534 WETH | 0 |

Gas is `gasUsed * effectiveGasPrice`. There is no L2 data fee on these Ethereum receipts. **OBSERVED.** Priority fee is `effectiveGasPrice - baseFee`. Seven of the nine have priority fee **0**. Two have about 640,000 wei. **OBSERVED.**

---

## 4. Uniswap v4 Forensics

PoolManager: `0x000000000004444c5dc75cB358380D2e3dE08A90`. **PROVEN** as the log emitter.

Pool keys were recovered where `keccak256(abi.encode(currency0, currency1, fee, tickSpacing, hooks))` equals the swap’s pool id. **PROVEN** for each key below. Hooks on every recovered key are `address(0)`. Hook logic was not required to explain these pools.

State was read from Uniswap v4 StateView `0x7ffe42c4a5deea5b0fec41c94c136cf115597227` at the previous block and at the transaction block. **PROVEN** that the call returns at those blocks.

The swap event’s `amount` signs match the caller’s delta on the pools where the token flow is unambiguous: negative means the caller pays that currency, positive means the caller receives it. **INFERRED** from matching PoolManager transfers, and **PROVEN** for the native-ETH leg by the internal ETH transfer of the same wei amount into the PoolManager.

| Row | Pool id | Pair | Fee (static) | Tick spacing | Hooks | Charged fee in the event |
|---|---|---|---:|---:|---|---:|
| 1, 6 | `0x3d8a4e3c8985f514808a901424724c9bc03b7a5b5ac3ca8b679d4681690d1e7f` | native ETH / WBTC | 100 (0.01%) | 1 | none | 125 |
| 3 | `0xb07d640fd9e2eb9dc81b953c8e4fd006bdfeaf276010fb5418eb763ca15abfb3` | native ETH / IMD | 10000 (1.00%) | 200 | none | 10990 |
| 4 | `0x90a64ed1c47392829a39df15ff25401c21818ea2db9e2538c9c25182f76b7c1e` | native ETH / FUSE | 11000 (1.10%) | 10 | none | 11989 |
| 4 | `0x9ce40419055bfc948663ef7438f1638676b49c8baeb845ac56f1e9dec1c1cb8e` | FUSE / USDC | 9000 (0.90%) | 90 | none | 9991 |
| 5 | `0x2287a9620adcbf6250dc71be9ee9b2d3a1ec85a464fc6f5c06669e8d07b61bba` | native ETH / USDT | 100 (0.01%) | 1 | none | 125 |
| 8 | `0x9ecc2b9b4171c12e89ea93ed63eb2b0b18048c51be2846e94be3d7c478354441` | native ETH / APE | 3000 (0.30%) | 60 | none | 3499 |
| 9 | `0x0fb0e40cec3bb23e13abc585958a93c796fbea56955e19a23727a716a0423239` | USDC / USDT | 7 (0.0007%) | 1 | none | 9 |

Protocol fee sits in StateView `slot0` as a packed uint24. Where it was decoded, it accounts for the gap between the stored LP fee and the charged fee (ETH/WBTC: LP 100 + protocol 25 = charged 125, exact). **PROVEN** for that pool. A few other pools are off by 1 to 11 fee units. **OBSERVED**, not explained. The official quoter was used for round trips, so the replay does not depend on adding those units by hand.

Two pool ids in row 2 were not recovered: `0xc8c4ec62ee9aed213a68d3c49b2b64b630a26873c5b003f40db4d357834bfd96` and `0xb7883cc2f8a52360a97aecce173c5bac58b4f41bfac96b77bf7cce555b3ae98e`. Both have LP fee 3000 in StateView. The intermediate currency cancels inside the unlock and does not appear as an ERC-20 transfer, so the pair was not brute-forced. Hook address **NOT_AVAILABLE**. The swap sender on those logs is `0x66a9893cc07d91d95644aedd05d03f95e1dba8af`, the canonical Uniswap Universal Router. **PROVEN** as the indexed sender.

A third id, `0xf6f2314ac16a878e2bf8ef01ef0a3487e714d397d87f702b9a08603eb3252e92`, appears in rows 5 and 6 with zero amounts, zero liquidity, and tick 0. It is not a traded pool. **PROVEN** from StateView.

### Route shape, not forced when the path is only partly identified

| # | Shape | Route, in order |
|---|---|---|
| 1 | v4 then custom contracts | Pay 0.9217651462611579 ETH into ETH/WBTC, receive 0.02909491 WBTC. Sell that WBTC to `0x585d44727129b9c69791b10238ca605932938b4f` for 2,504.9081 USDT. Swap USDT for 2,504.541467 USDC at `0x00000000000014aa86c5d3c41765bb24e11bd701`. Sell the USDC back to `0x585d4472…` for 0.9220599506733332 WETH. |
| 2 | two routes in one transaction | (A) Uniswap v2 TRUMP bridge, section 5. (B) v4 two-hop, currencies not fully recovered, USDC out 319.509588, then Uniswap v3 USDC/WETH 0.01% pool `0xe0554a476a092703abdb3ef35c80e0d76d32939f` pays 0.11766108999182248 WETH. ETH paid on the v4 leg: 0.11655935872029322. |
| 3 | v4 / v3 multi-hop | Pay 0.052256845187997864 ETH, receive 12.200636304377241 IMD. Uniswap v3 IMD/USDC 0.30% pays 142.250228 USDC. A 1:1 USDC to DAI hop (USDC sent to an EOA, DAI from `0xf6e72db5454dd049d0788e411b06cfaf16853042`). Uniswap v3 DAI/USDT 0.01%, then USDT/WETH 0.01%, out 0.0523614449419877 WETH. |
| 4 | v4 / v4 / v3 | Pay 0.0314733333157761 ETH into ETH/FUSE, FUSE through FUSE/USDC, USDC through the canonical Uniswap v3 USDC/WETH 0.05% pool, out 0.031794624942921264 WETH. |
| 5 | cross-protocol, index token | SushiSwap v2 DEXTF/WETH, v4 ETH/USDT, Uniswap v3 WBTC/USDT 0.05%, then DEXTF + WBTC + WETH delivered to `0x39953e6429210c39d11688fa40219c811287caad` (`name()` = “DEXTF Opportunities - v2”), then Uniswap v2 XTF/DEXTF and DEXTF/WETH. |
| 6 | same family as 5 | Sushi v2 DEXTF/WETH, v4 ETH/WBTC directly, same index token, same two Uniswap v2 exits. |
| 8 | v4 / v2 | Pay 0.012691828385393917 ETH into ETH/APE, receive 202.20266312455172 APE, sell APE on Uniswap v2 for 0.012754622012972765 WETH. |
| 9 | not an arb route | USDC/USDT v4 swap of about $2.28M, plus a liquidity decrease on ticks 305 and 306, inside an Aave repayment. Section 7. |

`0x585d4472…` and `0x00000000000014aa86…` have code and no `token0`, `factory`, or `name` return. They are not Uniswap v3 pools. Protocol name **NOT_AVAILABLE**.

IMD is the `symbol()` of `0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7`. The transfer indexer labeled the same units FP. The report uses the on-chain symbol. **OBSERVED.**

---

## 5. Uniswap v2 Forensics

Factory on every v2 pair below, read with `factory()` at the transaction block: `0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f`, except the DEXTF/WETH pair `0xd3c41c080a73181e108e0526475a690f3616a859`, whose factory is SushiSwap `0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac`. **PROVEN.**

The pure v2 row is row 7. Row 2 repeats the same two pairs inside a larger transaction.

| Pair | token0 | token1 | Role |
|---|---|---|---|
| `0xe4b8583ccb95b25737c016ac88e539d0605949e8` | TRUMP `0x576e2BeD8F7B46D34016198911Cdf9886f78bea7` (9 decimals) | WETH | buy TRUMP-A with WETH |
| `0x56bc8f3293f53825c9fbd6ddfe0cafefa82820d0` | TRUMP `0x6aa56e1d98b3805921c170eb4b3fe7d4fda6d89b` (9 decimals) | WETH | sell TRUMP-B for WETH |

The two non-WETH tokens are different. E1’s statement that they do not form a WETH → token → WETH cycle on a shared intermediate is **confirmed**. The link is not a third pool.

Observed bridge, both transactions, exact to float noise:

- 1.000% of the TRUMP-A received from the first pair is transferred to the TRUMP-A contract.
- The other 99.000% is transferred to the TRUMP-B contract.
- TRUMP-B is minted from `address(0)` in the same raw amount.

**OBSERVED** twice. It was not re-simulated as a token function at the previous block, so using that rate in a pre-block quote is conditional. **INFERRED** that the rate is a property of the token rather than a one-off choice, because both executions match to the last digits.

Row 7, realized size, **OBSERVED** flow:

- Flash 1 WETH, fee 0. Only 0.18783691096579036 WETH is swapped.
- First pair returns 14,550.818322134 TRUMP-A.
- After the 1% transfer, 14,405.310138913 TRUMP-B is minted and sold.
- Second pair returns 0.20174455886768974 WETH.
- Spread 0.01390764790189937 WETH, **$37.74** before gas at this row’s spot. Gas is $0.15. Surplus after gas, before the builder payment: **$37.59**.

Reserves immediately before each swap were rebuilt from the `Sync` log and the swap amounts. The constant-product formula with a 0.30% fee reproduces the first pair exactly and the second pair to within 2,996 wei. **RECONSTRUCTED.** That wei gap is under $0.00001.

Why the current quoter cannot cover it, from the code, not from the receipt:

- Ethereum’s registry DEX list is Uniswap v3, SushiSwap v2, and Curve. The Sushi factory is `0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac`. The Uniswap v2 factory is absent. **PROVEN** in `app/backend/arbicore/chains/registries.py`.
- `UniV2RouterQuoter` is bound to `sushiswap_v2` and to the Sushi router `0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F` only. **PROVEN** in `app/backend/arbicore/execution/quoter.py`.
- `hop_quote_capable` drops a hop whose DEX has no backend. A Uniswap v2 pair never enters. **PROVEN** in `live_quote_provider.py`, as E1 already recorded.
- Even a Uniswap v2 `getAmountsOut` on these two pairs would not emit the route. They do not share a token. The 1% bridge is not a pool hop, and a fee-on-transfer split is not what `getAmountsOut` models.

There is a separate `UniswapV2Router` under `app/backend/arbicore/providers/dex.py` pointed at the Uniswap v2 router. It is not the flash-loan quote backend. Wiring that router would still not price this bridge.

Other v2 pairs in the corpus, for completeness: APE/WETH `0xb011eeaab8bf0c6de75510128da95498e4b7e67f` (row 8); DEXTF/WETH `0xa1444ac5b8ac4f20f748558fe4e848087f528e00` and XTF/DEXTF `0x284e590de09e82b6706e4dff386fc678a01250e7` (rows 5 and 6), both Uniswap v2; DEXTF/WETH `0xd3c41c08…` is Sushi and is inside the current factory map. The Sushi leg is not the reason those rows were missed. The v4 leg and the index token are.

---

## 6. Pre-Block Visibility

Method. `eth_call` at block N−1 is the state at the end of the previous block. It is the state immediately before the transaction only when no earlier transaction in the same block touched the pool. Same-block swaps were counted with `eth_getLogs` on that block. For v2, `Sync` plus the swap amounts also rebuild reserves immediately before that swap. **PROVEN** as a method. `debug_trace` remains **NOT_AVAILABLE**, so a v4 pool that was touched earlier in the block cannot be re-quoted at the exact pre-transaction tick.

| # | Earlier swaps in the block on the route’s pools | Previous-block round trip | Label |
|---|---|---|---|
| 1 | no earlier swap on the ETH/WBTC pool | v4 output matches the realized 2,909,491 WBTC raw exactly. Public Uniswap v3 WBTC→WETH 0.05% then returns 0.92087 WETH against 0.92177 ETH in, **−$2.43**. The custom filler paid 0.92206 WETH. Whether that filler price existed before the transaction is **NOT_AVAILABLE**. | Public round trip not profitable. Full route **NOT_RECONSTRUCTABLE** as a public quote. |
| 2 | five earlier swaps on the TRUMP-B pair; one earlier swap on one v4 pool; one on the v3 pool | TRUMP bridge at the traded size: **+$25.69** before gas, conditional on the 1% / 1:1 bridge. Best size about 0.39 ETH: **+$26.70**. The v4/v3 leg’s previous-block quote was not built (pool key missing). Its realized spread is +$2.99 and may include the earlier in-block swap. | TRUMP leg **PRE_BLOCK_VISIBLE**, conditional. v4 leg **NOT_RECONSTRUCTABLE**. |
| 3 | no earlier swap on the ETH/IMD pool or the IMD/USDC pool | Official quotes plus the observed 1:1 stable hop reproduce the realized WETH out exactly. Surplus **+$0.284** before gas. | **PRE_BLOCK_VISIBLE** |
| 4 | one earlier swap on ETH/FUSE; two earlier swaps on USDC/WETH 0.05%, including that same prior transaction | Round trip at the traded size: **−$2.69**. Realized surplus was +$0.87. | **ONLY_BLOCK_BOUNDARY_VISIBLE** for the realized penny surplus. Exact pre-swap v4 tick **NOT_RECONSTRUCTABLE**. |
| 5, 6 | index mint not re-quoted | Realized surplus under $1. Previous-block index quote **NOT_RECONSTRUCTABLE**. | **NOT_RECONSTRUCTABLE** |
| 7 | no earlier swap on TRUMP-A; four earlier swaps on TRUMP-B | Best previous-block size, about 0.26 ETH: **+$12.17**. The realized $37.74 uses TRUMP-B reserves after those four swaps. | The $37 edge is **ONLY_BLOCK_BOUNDARY_VISIBLE**. A smaller positive cycle is **PRE_BLOCK_VISIBLE** and does not clear $25. |
| 8 | two earlier v4 swaps and one earlier v2 swap on APE/WETH | Every tested size from 0.001 ETH to $50,000 is negative. Realized surplus was +$0.17. | **ONLY_BLOCK_BOUNDARY_VISIBLE** |
| 9 | not an opportunity | — | not classified |

A positive previous-block quote is not the same statement as “the realized profit was available at the previous block.” Row 7 is the example. The pools were mispriced by about $12 before the block. The $37 print required four earlier swaps in the block.

---

## 7. Exact Economic Replay

Components, and how each was obtained:

| Component | Treatment |
|---|---|
| Notional | The native ETH or WETH actually paid into the first hop. **OBSERVED.** |
| Gross cycle surplus | Value out minus value in, after the pool’s own fee (the fee is inside the fill). **RECONSTRUCTED.** |
| Venue fee | Embedded in the swap. Not added again. The charged v4 fee is **OBSERVED** on the event. |
| Flash-loan fee | 0 on every decoded Morpho and Balancer event. **OBSERVED.** |
| Gas | Receipt `gasUsed * effectiveGasPrice`, priced at the row spot. **OBSERVED** wei, **RECONSTRUCTED** USD. |
| L2 data fee | Not present. Ethereum. **OBSERVED** absence. |
| Builder / coinbase payment | Internal ETH to `block.miner`. **OBSERVED.** This is not the gas payment. Gas is paid by `tx.from` through the protocol. |
| Private relay, builder identity beyond `extraData` and coinbase | **NOT_AVAILABLE** |
| $50 MEDIUM haircut | Not applied. Production is unchanged. |

The production Gate 7 number is `atomic_profit_usd`, defined as `EconomicAssessment.expected_profit_usd`, which is after the MEV penalty inside `aggregate_economics`. This replay does not run that function and does not insert the haircut. The comparison to $25 in section 15 is the exact surplus, not the haircut-adjusted production number.

### Worked pattern, row 8

**OBSERVED** internal and ERC-20 legs:

1. Balancer sends 0.012691828385393917 WETH.
2. WETH contract sends that same wei amount of ETH to the executor (`withdraw`).
3. Executor sends that ETH to the PoolManager.
4. PoolManager sends 202.20266312455172 APE.
5. Uniswap v2 sends 0.012754622012972765 WETH for that APE.
6. Executor repays Balancer the flash amount.
7. Executor sends 0.000022705870745425 ETH to the Eureka coinbase.

Spread before the tip: 0.000062793627578848 ETH, about **$0.171**. Tip about **$0.062**. Gas about **$0.067**. Kept about **$0.042**.

The E1 figure of $34.60 is step 5 priced as profit, with step 2 invisible because it is not a `Transfer`.

### Row 9, the 718.89 WETH credit

**OBSERVED** on the helper `0x76f30e3f75437fb862b8d2c4d80a671bceba5b1a`:

- Morpho flash in and out: 13,254.985100677534 WETH.
- Aave aWETH withdraw: 13,973.845 WETH scale (the transfer amount that, with the 0.028233253 WETH from the Uniswap v3 WETH/USDT 0.05% pool, funds the residual).
- 718.8879272893713 WETH forwarded to `tx.to`.
- `tx.to` pays 0.020288213220578052 ETH to the Titan coinbase.

The same EOA and the same `tx.to` have another transaction in this block, `0x8fbb95ec109093c7d11d5ba85d2d334fd04018500a52b28810928d73dab18c80`, whose ETH/WETH balance change is about **−$1,952,423**. The inbound and outbound legs are a position move, not two arbitrages. **PROVEN** that both transactions exist and that the signs are opposite. A full joint decoding of the outbound transaction was not done. The inbound leg alone is enough to reject the 718 WETH credit as alpha. **PROVEN.**

The v4 activity inside it is a USDC/USDT swap of about 2.28 million tokens and a liquidity decrease. It does not source the 718 WETH.

### Corrected scoreboard

Surplus here is after venue fills, flash fee, and gas, before the coinbase tip. Kept is after the tip as well.

| # | Notional into the priced hop | Surplus before tip | Tip (USD) | Kept | Clears $25 before tip | Clears $25 after tip |
|---|---:|---:|---:|---:|---|---|
| 1 | 0.922 ETH, about $2,503 | +$0.10 | $0.30 | −$0.19 | no | no |
| 2 | 0.312 WETH on the v2 leg plus 0.117 ETH on the v4 leg | $32.97 | $30.00 | $2.97 | yes | no |
| 3 | 0.0523 ETH, about $142 | $0.09 | $0.04 | $0.05 | no | no |
| 4 | 0.0315 ETH, about $86 | $0.70 | $0.47 | $0.24 | no | no |
| 5 | mixed; gross cycle about $1.03 before gas | $0.79 | $0.20 | $0.60 | no | no |
| 6 | mixed; gross cycle about $0.54 before gas | $0.31 | $0.05 | $0.26 | no | no |
| 7 | 0.188 WETH, about $510 | $37.59 realized; $12.02 best previous-block | $34.20 | $3.39 | realized yes; previous block no | no |
| 8 | 0.0127 ETH, about $34 | $0.10 | $0.06 | $0.04 | no | no |
| 9 | n/a | n/a | $55 tip on the migration | n/a | no | no |

Rows 5 and 6 are closed in WETH and in the basket tokens (DEXTF, WBTC, USDT net to zero on the searcher). The surplus is the cycle, not a leftover inventory token. The index mint itself was not re-quoted, so the **size** of that cycle at another notional is **NOT_RECONSTRUCTABLE**. The realized size is **RECONSTRUCTED** and is under $1 before the tip.

Hypothetical ArbiCore economics, meaning a quote the current code could emit: **none of these cycles**. The missing hop is v4 or Uniswap v2 or the TRUMP bridge or the index token. There is no current-quoter number to put beside the replay. That absence is the coverage result, not a zero profit inside the current universe.

---

## 8. Size Sweep

Production size was not changed. Grids are offline quotes at the previous block.

Tools: Uniswap v4 quoter `0x52f0e24d1c21c8a0cb1e5a5dd6198556bd9e1203`, function `quoteExactInputSingle` with the nested PoolKey tuple (selector `0xaa9d21cb`); Uniswap v3 QuoterV2; constant-product math for v2. A quote that reverts or returns a nonsensical amount is recorded as not completed.

USD below uses $2,717 only as a label for the bucket. The sign does not depend on that rounding.

### ETH → APE (v4) → WETH (Uniswap v2), block 26,125,588

Previous-block state. All negative. The realized +$0.17 does not appear here because earlier transactions in the block had already moved both pools.

| Bucket | Spread |
|---|---:|
| 0.001 ETH | −$0.02 |
| 0.05 ETH (probe scale) | −$3.57 |
| realized 0.0127 ETH | −$0.38 |
| about $200 | −$7.16 |
| about $2,000 | −$486 |
| about $10,000 | −$6,131 |
| about $50,000 | −$44,385 |

Highly size-sensitive, and unprofitable at the previous block at every tested size. **RECONSTRUCTED.**

### TRUMP bridge, block 26,125,649 (row 7’s previous block)

Reserves: TRUMP-B pool holds 18.77 WETH. A $10,000 buy is a large fraction of that pool.

| Bucket | Spread |
|---|---:|
| 0.01 ETH | +$0.90 |
| 0.05 ETH | +$4.16 |
| 0.188 ETH (realized) | +$11.13 |
| about $200 | +$5.82 |
| about $1,000 | +$10.50 |
| best, about 0.26 ETH | **+$12.17** |
| about $2,000 | −$23.66 |
| about $10,000 | −$1,603 |

**RECONSTRUCTED**, conditional on the 1% bridge.

### TRUMP bridge, block 26,125,592 (row 2’s previous block)

| Bucket | Spread |
|---|---:|
| realized v2 input, 0.312 ETH | **+$25.69** before gas |
| best, about 0.39 ETH | **+$26.70** before gas |
| about $10,000 | negative, same shape as the grid above |

After a gas cost equal to the observed TRUMP-only transaction ($0.15), the traded size is about **$25.54** and the best size is about **$26.55**. The margin over $25 is about half a dollar. It is conditional on the bridge rate. It is not a $10,000 quote.

### FUSE v4/v4/v3, block 26,125,493

| Bucket | Spread |
|---|---:|
| realized | −$2.69 |
| about $200 | −$8.77 |
| about $2,000 | −$409 |
| about $10,000 | not completed; the v4 quoter returned an FUSE amount that did not form a sane round trip |

### Public ETH/WBTC v4 then Uniswap v3 WBTC/WETH 0.05%

The v4 leg at the realized size matches the transaction exactly (2,909,491 WBTC raw). The public exit does not pay for the ETH.

| Bucket | Spread |
|---|---:|
| realized, about $2,503 | −$2.43 |
| about $10,000 | −$19.11 |
| about $50,000 | −$346 |

The custom filler, not the public v3 pool, is what made row 1’s $0.30 gross spread. That filler was not size-swept. **NOT_AVAILABLE.**

### IMD

Only the realized size was chained, because the middle hop is an observed 1:1 rather than a pool quote. It matches the transaction at **+$0.284** before gas. A $10,000 IMD sweep was not run. Given a 0.2% spread on $142, a linear scale would still be under $25, and linear scale is not evidence. **NOT_PROVABLE** at $10,000. The realized size does not clear $25. **RECONSTRUCTED.**

Minimum profitable size, where a previous-block quote was positive:

- TRUMP: between 0.01 ETH and the peak near 0.3–0.4 ETH. Profit is gone by about $2,000 of WETH in, on these reserves.
- APE, FUSE, public WBTC: no profitable size in the tested grid at the previous block.
- IMD: profitable at the realized size by $0.28, not swept.

ArbiCore’s complete-bundle size is $10,000. The discovery probe is about 0.05 WETH or 200 USDC. On the TRUMP reserves, 0.05 ETH is about +$4, and $10,000 is about −$1,600. A scanner that only keeps the $10,000 quote would reject the only cell that clears $25 at a small size. **RECONSTRUCTED** for this pair. That does not mean size is why the row was missed. The factory is not in the graph at any size.

---

## 9. Both-Direction Analysis

APE, both directions, previous block: the reverse (WETH → APE on v2, APE → ETH on v4) is negative at every tested size, from −$0.02 to tens of thousands of dollars. **RECONSTRUCTED.** Direction matters. The realized direction was the one that was slightly profitable after the in-block trades, and it was still not profitable at the previous block.

TRUMP marginal prices at block 26,125,649, selling one whole token for WETH: TRUMP-A returns 0.000012685 WETH; TRUMP-B returns 0.000013327 WETH. About 5.1% before fees. **RECONSTRUCTED.** The profitable direction is buy A, bridge to B, sell B. The reverse bridge (B minted back into A) was not observed and was not simulated. **NOT_AVAILABLE.** A forward-only walk of DEX edges would still miss this route, because the bridge is not an edge.

Public WBTC: only ETH → WBTC → WETH was quoted. The reverse was not required to see that the forward public round trip loses money.

IMD and FUSE reverse were not swept. The forward realized sizes are already under $1 of true surplus, or negative at the previous block.

ArbiCore walks both directions of a graph edge and then stops at 64 cycles. That code path was not modified and was not executed against these pools. Whether a reverse cycle would have been dropped by the cap is **NOT_PROVABLE** here, because these pools are not in the graph.

---

## 10. Quote / Routing Gap

| Route | Currently covered? | Missing capability |
|---|---|---|
| Any recovered v4 pool | **NO** | Venue unsupported. No pool discovery, no pool-key state, no quote adapter. Native ETH (`address(0)`) is not a registry token. |
| v4 hooks on these recovered pools | not the blocker | Hooks are `address(0)`. **PROVEN.** Hook support is still missing for pools that have hooks; these rows do not demonstrate that bug. |
| Row 2’s two unidentified v4 pools | **NO** | Same venue gap, plus the pool key was not recovered, so a future quoter would also need the currencies. |
| Uniswap v2 factory pairs | **NO** | Pool discovery and the quote adapter are SushiSwap v2 only. |
| TRUMP bridge | **NO** | Even with Uniswap v2 quotes, the two tokens and the 1% mint are not a generated hop. Tokens are not in the registry. |
| Sushi DEXTF/WETH | factory is in the map | Not sufficient. The cycle also uses v4 and the index token. |
| Uniswap v3 legs (USDC/WETH, USDT/WETH, WBTC/USDT, and the others) | **YES**, those fee tiers and tokens are in the current universe | They do not form a closed profitable cycle without the v4 or v2 leg. |
| Custom filler `0x585d4472…` | **NO** | Not a known pool. Quote adapter **NOT_AVAILABLE**. |
| Index token `0x39953e…` | **NO** | Token and mint/redeem path unsupported. |
| Direction | graph walks both ways, then caps | Not why these rows were missed. |
| Size | one exact notional, default $10,000 | Secondary. The TRUMP cell is positive near 0.3 ETH and negative at $10,000. The v4 rows are not positive at $10,000 on the public quotes either. |
| Historical state | `eth_call` at the previous block works for these pools | Intra-block v4 state does not, without a trace. |

No adapter was added.

---

## 11. Repeatability Evidence

The E1 sample is one Ethereum hour. This gate stayed inside that hour.

**OBSERVED** from `eth_getLogs` on the PoolManager, 31 chunks of at most 10 blocks, zero log errors:

| Count | Value |
|---|---:|
| v4 `Swap` logs | 7,703 |
| Transactions with at least one v4 swap | 5,422 |
| Distinct pool ids | 604 |
| Distinct swap senders | 214 |
| Morpho `FlashLoan` transactions | 67 |
| Balancer v2 `FlashLoan` transactions | 9 |
| v4 and Morpho in the same transaction | 40 |
| v4 and Balancer in the same transaction | 5 |

The busiest sender, 396 of the v4 swaps, is the Universal Router. That count is user flow and router flow together. It is not an arbitrage census. **PROVEN** as a log count. **NOT** a count of profitable cycles.

The 45 flash-loan transactions that also touch v4 were priced with the same ETH/WETH method as the nine-row corpus, using $2,716 as a flat spot for the distribution only. **ESTIMATED** spot, **RECONSTRUCTED** wei.

| Threshold | Count |
|---|---:|
| Gross ETH/WETH surplus ≥ $0, before tip | 33 of 45 |
| ≥ $1 | 9 |
| ≥ $25 after gas, before tip | 2 |
| Searcher-kept ≥ $25 after tip and gas | 1 |

The two at or above $25 after gas are the paired 718 WETH legs (about +$1.95M and about −$1.95M). The one “kept” above $25 is the inbound leg of that pair. Removing them, **one** transaction remains at or above $25 before the tip: row 2, $32.97, of which the kept amount is $2.97. **RECONSTRUCTED.**

Eight other flash+v4 transactions have a gross surplus between $1 and $6. After the tip, the largest of those kept results is about $1.47. Median gross surplus of the 45 is about **$0.22**. Twelve are negative, including four between about −$100 and −$595 on executor contracts that also appear in the nine-row set. Those negatives were not route-decoded. They are consistent with inventory movement. They are not a fitted loss distribution. **OBSERVED** as balance changes. Cause **NOT_PROVABLE** except for the paired 718 WETH legs.

Fourteen of the 45 also move a non-ETH token that does not net to zero. Those USD figures are incomplete. **NOT_AVAILABLE** for those residuals.

The other 5,377 v4 transactions were not economically classified. Own-capital v4 arbitrage, which E1 already excluded from the flash filter, remains **NOT_PROVABLE**.

Repeatability of a Gate 7 v4 cycle: **NOT_PROVABLE**. What this hour does show is that the flash+v4 transactions whose ERC-20 WETH residual looked large do not, after native ETH, form a set of $25 net cycles.

Repeatability of the TRUMP cell: two executions in this hour, same searcher, same two pairs. That is a repeated route inside one hour. It is not a multi-day result. **OBSERVED** twice. A broader rate is **NOT_PROVABLE**.

---

## 12. Competition Evidence

| # | Searcher EOA | Contract | Index | Priority fee | Builder `extraData` | Coinbase tip |
|---|---|---|---:|---:|---|---:|
| 1 | `0xdc6d1ddb…` | `0x824a78cd…` | 91 | 0 | BuilderNet | $0.30, the entire spread |
| 2 | `0x30a1b724…` | `0x50d3865a…` | 21 | 0 | BuilderNet | $30.00 |
| 3 | `0xa969ddb2…` | `0x950fd558…` | 16 | 0 | BuilderNet | $0.04, plus $0.24 forwarded to the EOA |
| 4 | `0x49efa792…` | `0x78dcc4a0…` | 4 | 640,532 wei | Titan | $0.47 |
| 5 | `0x6c14f565…` | `0xd35804a6…` | 82 | 0 | Titan | $0.20 |
| 6 | `0x6c14f565…` | `0xd35804a6…` | 122 | 0 | Titan | $0.05 |
| 7 | `0x30a1b724…` | `0x50d3865a…` | 8 | 0 | Titan | $34.20 |
| 8 | `0x31189ef7…` | `0x09903191…` | 293 | 640,766 wei | Eureka | $0.06 |
| 9 | `0x654fae4a…` | `0x000000000035b5…` | 11 | 0 | Titan | $55, on the migration |

Coinbase addresses match `block.miner`. **PROVEN.** Private order flow, bundle identity, and relay name are **NOT_AVAILABLE**. A zero priority fee is consistent with a private bid paid by the coinbase transfer. It is not, by itself, proof of a private relay. **OBSERVED** fee. Relay **NOT_AVAILABLE**.

Repeated winners inside the nine: one searcher takes both TRUMP transactions; another takes both DEXTF transactions. **OBSERVED.** Not a market-share number.

Competing transactions that touched the same pool earlier in the block are listed in section 6. They are public receipts. They are not a full picture of failed bids. Reverted transactions were not enumerated.

---

## 13. Candidate Opportunity Cells

These are research cells. They are not qualified strategies. None is approved for paper, shadow, or live.

| Cell | Chain | Protocol | Pool | Tokens | Direction | Size | Condition | Replay result |
|---|---|---|---|---|---|---|---|---|
| TRUMP bridge | Ethereum | Uniswap v2 factory | the two pairs in section 5 | TRUMP-A, TRUMP-B, WETH | A → bridge → B | about 0.3–0.4 ETH | previous-block reserves in this hour, 1% bridge | about $25–$27 before gas and before the builder; negative near $2,000 and at $10,000; realized kept profit about $3 |
| ETH/APE vs v2 | Ethereum | v4 PoolManager and Uniswap v2 | ETH/APE fee 3000, spacing 60; APE/WETH v2 | ETH, APE, WETH | ETH → APE → WETH | realized about $34 | previous block | negative; the +$0.17 print is in-block only |
| ETH/FUSE/USDC vs v3 | Ethereum | v4 and Uniswap v3 | the two FUSE pools; USDC/WETH 0.05% | ETH, FUSE, USDC, WETH | ETH → FUSE → USDC → WETH | realized about $86 | previous block | −$2.69; realized +$0.87 is in-block |
| ETH/IMD then stables then WETH | Ethereum | v4 and Uniswap v3 | ETH/IMD fee 10000, spacing 200 | ETH, IMD, USDC, DAI, USDT, WETH | as executed | about $142 | previous block, 1:1 middle hop | +$0.28, matches the transaction, under $25 |
| ETH/WBTC v4 vs public v3 | Ethereum | v4 and Uniswap v3 | ETH/WBTC fee 100, spacing 1; WBTC/WETH 0.05% | ETH, WBTC, WETH | ETH → WBTC → WETH | $2,500 and $10,000 | previous block | negative at both |
| DEXTF index | Ethereum | v4, Sushi v2, Uniswap v2, index token | several | DEXTF, WBTC, WETH, XTF | as executed | realized | this hour | realized surplus under $1; other sizes not quoted |

The 718 WETH migration is not a cell.

---

## 14. Evidence Classification

| Claim | Label |
|---|---|
| Uniswap v4 PoolManager is touched by eight of the nine rows and is absent from the quoter | **PROVEN** |
| Uniswap v2 factory pairs are touched and the quoter is Sushi-only | **PROVEN** |
| E1’s large WETH residuals omit `WETH.withdraw` / native ETH paid to the PoolManager | **PROVEN** |
| Corrected surplus of each of the eight arb rows | **RECONSTRUCTED** |
| 718.89 WETH is an Aave residual, not a cycle profit | **PROVEN** |
| Previous-block IMD round trip equals the realized fill, at +$0.28 | **RECONSTRUCTED** |
| Previous-block TRUMP surplus near $26, if the 1% bridge holds | **RECONSTRUCTED**, bridge rate **OBSERVED** in-transaction and **INFERRED** at the previous block |
| APE and FUSE realized pennies exist only after earlier swaps in the block | **INFERRED** as **ONLY_BLOCK_BOUNDARY_VISIBLE**; exact pre-swap v4 tick **NOT_RECONSTRUCTABLE** |
| No tested public v4 round trip is profitable at $10,000 | **RECONSTRUCTED** for APE, FUSE (incomplete at $10k), and WBTC/v3 |
| v4 Gate 7 alpha is repeatable | **NOT_PROVABLE** |
| Builder payment beyond the coinbase transfer | **NOT_AVAILABLE** |
| These rows are an executable ArbiCore opportunity | **not claimed** |

---

## 15. E1.5 Decision

A. **Is Uniswap v4 a demonstrated coverage gap?**  
Yes. **PROVEN.** The PoolManager is on the receipts. The quoter has no v4 backend.

B. **Is Uniswap v2 a demonstrated coverage gap?**  
Yes. **PROVEN.** The factory on the TRUMP and APE pairs is Uniswap v2. The quote backend is SushiSwap v2.

C. **Can the observed v4 opportunities be reconstructed pre-block?**  
Some of the routes, not as $25 opportunities. The IMD route reconstructs exactly, at $0.28. The public ETH/WBTC to v3 WETH route reconstructs and loses money. APE and FUSE are negative at the previous block; the small realized profits show up only after earlier transactions in the block, and the exact pre-swap v4 state was not rebuilt. Two v4 pools in row 2 were not keyed.

D. **Can they remain profitable after exact-size economics?**  
The E1 dollar figures do not. Exact economics leave sub-dollar surpluses on the pure v4 routes, and a loss on the public WBTC round trip. The mixed row 2 surplus that remains is mostly the v2 TRUMP leg.

E. **Do they clear the existing $25 Gate 7?**  
No v4 route does. One previous-block route does, narrowly, before the builder payment and not at the production size: the TRUMP bridge, about $25.5 after gas at 0.31 ETH, about $26.6 at 0.39 ETH, negative at $10,000. After the observed coinbase payment, that searcher kept about $3. Gate 7’s production haircut was not applied and was not needed to reach this conclusion.

F. **Are they repeatable enough to justify paper or shadow research?**  
No. One hour, one conditional v2 cell, size far from the production notional, competition taking the surplus, and 5,422 unclassified v4 swap transactions beside it. Paper trading this cell would require a bridge the scanner cannot represent.

G. **Is the current evidence sufficient to implement v4 or v2 support?**  
**No.** Coverage is demonstrated. A Gate 7 opportunity inside that coverage is not. Implementation stays a separate gate.

---

## 16. Recommended Next Gate

`ADDITIONAL_REPLAY`

Not `IMPLEMENTATION_DESIGN`. Not paper. Not a live flag.

The next measurement, still read-only, if it is done at all:

1. Keep the native-ETH correction. Do not rank opportunities by ERC-20 WETH `Transfer` net alone.
2. Replay the TRUMP pairs over more than one hour before treating the bridge as a stable rate. Simulate the mint at the previous block instead of copying the in-transaction 1%.
3. Do not treat 7,703 v4 swap logs as alpha. If a wider v4 pass is run, restrict it to closed cycles and price native ETH.
4. Do not lower Gate 7, Gate 8, or Gate 9. Do not enable the scanner, signing, or broadcast as part of the measurement.

Until a quoted route, on a venue the code can actually call, clears $25 after gas at a size the sizer will use, and still clears it after a realistic builder payment, LIVE 1 stays NO-GO. That was E1’s bar. This replay does not move it.

---

## 17. Limitations

- One chain hour. Not 14 days. Not the other five chains. Base, Arbitrum, Optimism, Polygon, and BNB v4 activity was not measured.
- Free-tier `eth_getLogs` is 10 blocks. The hour was readable. A longer census was not started.
- No transaction trace. Intra-block v4 ticks after an earlier swap are **NOT_RECONSTRUCTABLE**.
- `alchemy_getAssetTransfers` covers the internal ETH that the receipts omit. It is not a full call trace. A token that moved only inside a delegate call without a log would still be missed. On these nine rows the basket tokens net to about zero, which is the check that was available.
- The v4 quoter fee and the event fee differ by 1 to 11 units on some pools. Round trips that match the realized output (IMD, the WBTC v4 leg) do not depend on hand-adding that gap.
- Row 2’s v4 currencies were not recovered. The leg’s realized ETH-in versus WETH-out is known. Its previous-block quote is not.
- The TRUMP pre-block dollar figure is conditional on the bridge.
- Fourteen flash+v4 transactions have an unpriced residual token. They are not in the “under $25” claim as closed cycles.
- The 5,377 v4 transactions without a flash loan were counted and not priced.
- WETH spots differ from E1’s single $2,717.20 by less than 0.2%.
- No production quote was executed. “Hypothetical ArbiCore” means “the current adapter map cannot emit this hop,” which was checked in source, not by running the scanner.

---

## 18. Appendices

### 18.1 What was not done

No source edit. No scanner change. No quoter change. No RPC change. No database write. No container restart. No image build. No flash-loan flag. No signing. No broadcast.

### 18.2 Code anchors for the gap

| Fact | Where |
|---|---|
| Ethereum DEX list: Uniswap v3, Sushi v2, Curve. No v4. No Uniswap v2 factory. | `app/backend/arbicore/chains/registries.py` |
| v2 quote backend is `sushiswap_v2` and the Sushi router only | `app/backend/arbicore/execution/quoter.py`, `UniV2RouterQuoter` |
| Hops without a backend are dropped | `app/backend/arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py` |
| Gate 7 reads `expected_profit_usd` | `app/backend/arbicore/scanners/economics.py`, `canonical_net_profit_usd` |
| Default atomic floor $25 | `app/backend/arbicore/data/scanner_config_repo.py` |

### 18.3 Contracts used for reads

| Role | Address |
|---|---|
| Uniswap v4 PoolManager | `0x000000000004444c5dc75cB358380D2e3dE08A90` |
| Uniswap v4 StateView | `0x7ffe42c4a5deea5b0fec41c94c136cf115597227` |
| Uniswap v4 Quoter | `0x52f0e24d1c21c8a0cb1e5a5dd6198556bd9e1203` |
| Uniswap v3 QuoterV2 | `0x61fFE014bA17989E743c5F6cB21bF9697530B21e` |
| Uniswap v3 USDC/WETH 0.05% (spot and row 4 exit) | `0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640` |
| Uniswap v2 factory | `0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f` |
| SushiSwap v2 factory | `0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac` |
| Morpho Blue | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` |
| Balancer v2 Vault | `0xBA12222222228d8Ba445958a75a0704d566BF2C8` |
| WETH | `0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2` |

### 18.4 Same-block prior swaps that changed the label

| Row | Earlier transaction | What it touched |
|---|---|---|
| 4 | `0x55fe87a94866184aa4e7137f902391446494b2ad8c98363e7def3ffee6aa876a` | ETH/FUSE v4 pool and USDC/WETH v3 |
| 7 | four swaps on TRUMP-B before index 8, including `0xd2bbf5bd737a95f2d88955a46a1c6380f11bf4ada5273fd49b0a36f48689a0b4` at index 7 | the rich TRUMP pool |
| 8 | `0xb173f455309fa7b43684318e44ecd5a788b19ed2d49be239806c6330cea47891` | both the ETH/APE v4 pool and the APE/WETH v2 pair |
| 2 | five earlier swaps on TRUMP-B in that block | the same rich pool, before the mixed transaction |

### 18.5 Statements this report does not make

- It does not say Uniswap v4 is profitable.
- It does not say the 718.89 WETH credit is an executable size.
- It does not say ArbiCore would have captured the TRUMP cell by adding a Uniswap v2 router. The bridge is not a pool, and the profitable size is not $10,000.
- It does not say to implement v4 or v2 on this evidence.
- It does not say LIVE 1 is justified.
