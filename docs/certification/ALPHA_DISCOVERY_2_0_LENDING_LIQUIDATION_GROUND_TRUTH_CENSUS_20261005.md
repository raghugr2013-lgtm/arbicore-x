# ALPHA_DISCOVERY_2.0 — Lending liquidation ground-truth census

Date: 2026-10-05
Mode: read-only historical census. No production strategy, scanner, Gate 7, RPC, database, or deployment change.
Coverage classification: **PARTIAL**

This is not a complete six-chain census. Ethereum, Base, and Polygon finished the windows that were opened. Optimism is missing one stratum. BNB is missing a slice tail, two unopened strata, and scattered rate-limit holes. Arbitrum was not scanned.

No strategy cell meets the rule for an engineering gate. The engine decision is not a GO.

## 1. Executive summary

Thirty-one liquidation events were logged in the windows that actually completed or partially completed. Thirty have an oracle gross price. All thirty-one received a pre-block visibility class. Twelve events have oracle gross of at least $25. Zero events have a reconstructable net of at least $25 after gas, observed builder payment, and unwind. Zero events are both pre-block visible and competition-surviving at the $25 net bar.

The twelve large gross figures are concentrated on Ethereum. Eleven of them were healthy at the end of block N−1 (`TRADE_BLOCK_ONLY`). On those transactions the internal transfer to the block producer is about the same size as the oracle surplus. One Ethereum Morpho Blue liquidation was already underwater at N−1, with oracle gross $99.78, gas $0.11, and no coinbase transfer. Its collateral is `CTOKEN1`, and the cost of selling that collateral was not quoted, so that $99.78 is an upper bound, not a net. It is a single observation.

Base contributed four priced events. The largest pre-block gross is $6.22. Polygon’s seven slices, Optimism’s six finished slices, and the BNB windows that returned logs contain zero liquidation events for the contracts that were queried. Those zeros are not a statement about blocks that were never read.

## 2. Scope

Question: do real lending liquidations on the six ArbiCore chains contain a repeated, pre-block-visible, addressable opportunity of at least $25 net after gas and observed competition.

What was done: historical `eth_getLogs` for known liquidation events, then one economics pass over every collected event. The economics pass had no profit filter.

What was not done: no detector, scanner, executor, route generator, strategy class, or Gate 7 change. No size sweep. No N+1 replay. Euler, Fluid, and Silo were not given verified addresses and were not scanned.

Evidence labels used below: **PROVEN** (returned by a node or computed directly from returned fields), **INFERRED** (a documented formula applied to those fields), **HYPOTHESIS** (not tested here), **NOT_PROVABLE** (private orderflow or an unobserved payment).

## 3. Chains covered

| Chain | Planned sample | What was actually read | Events |
| --- | --- | --- | --- |
| Ethereum | One contiguous 168h window | Finished, 0 gaps | 27 |
| Base | Seven 2h slices, 24h apart | Finished, 0 gaps | 4 |
| Polygon | Seven 2h slices, 24h apart | Finished, 0 gaps | 0 |
| Optimism | Seven 2h slices, 24h apart | Six slices finished, offset 120h never opened | 0 |
| BNB | Seven 2h slices, 24h apart | Four slices finished with internal gaps; offset 96h stopped at 55.5%; offsets 120h and 144h not started | 0 |
| Arbitrum | Seven 0.5h slices, 24h apart | Not started | none |

A finished slice with zero events is an observation of that contract set in that block range. A gap, an unopened stratum, or an unscanned tail is **INCOMPLETE**. It is not a zero.

## 4. Protocols covered

Queried, because the contract had code at the head used by the scanner:

| Chain | Protocol | Address | Result in the read windows |
| --- | --- | --- | --- |
| Ethereum | Aave V3 Pool | `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2` | 16 `LiquidationCall` |
| Ethereum | Spark Pool | `0xC13e21B648A5Ee794902342038FF3aDAB66BE987` | 0, and the Ethereum log scan recorded 0 errors |
| Ethereum | Morpho Blue | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` | 11 `Liquidate` |
| Ethereum | Compound III USDC comet | `0xc3d688B66703497DAA19211EEdff47f25384cdc3` | 0 `BuyCollateral`, 0 `AbsorbCollateral` |
| Base | Aave V3 Pool | `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5` | 1 `LiquidationCall` |
| Base | Morpho Blue | same singleton as Ethereum | 3 `Liquidate` |
| Base | Compound III USDC and WETH comets | `0xb125E6687d4313864e53df431d5425969c15Eb2F`, `0x46e6b214b524310239732D51387075E0e70970bf` | 0 |
| Polygon | Aave V3 Pool | `0x794a61358D6845594F94dc1DB02A252b5b4814aD` | 0 |
| Optimism | Aave V3 Pool | `0x794a61358D6845594F94dc1DB02A252b5b4814aD` | 0 on the six finished slices |
| Optimism | Compound III USDC and WETH comets | `0x2e44e174f7D53F0212823acC11C01A11d58c5bCB`, `0xE36A30D249f7761327fd973001A32010b521b6Fd` | 0 on the six finished slices |
| BNB | Aave V3 Pool | `0x6807dc923806fE8Fd134338EABCA509979a7e0cB` | 0 on windows that returned |
| BNB | Venus | Unitroller `0xfD36E2c2a6789Db23113685031d7F16329158384`, 55 markets from `getAllMarkets()` | 0 on windows that returned |

Not covered, so their liquidation count is **UNKNOWN**, not zero:

- Arbitrum Aave V3, Morpho (`0x6c247b1F6182318877311737bac0844bAa518F5e`), and the three Compound comets that had code. The scan never started.
- Ethereum WETH Compound comet. The previously recorded address had no code and was left out.
- Polygon Compound. The previously recorded address had no code and was left out.
- Optimism Morpho at the Ethereum singleton. An earlier code check returned empty code, and no other Optimism Morpho address was verified.
- Euler, Fluid, and Silo on every chain.

## 5. Historical windows

The provider rejects `eth_getLogs` ranges wider than 10 blocks. **PROVEN** in the probe that set the method, before any economics were computed. The census therefore uses 10-block windows, two windows per call. A 14-day contiguous pull was not feasible under that cap. Ethereum was given one 168-hour contiguous range. The other chains were given seven 2-hour slices at offsets 0, 24, 48, 72, 96, 120, and 144 hours before the head at the start of each slice. Arbitrum’s planned slice length was 30 minutes, for the same reason a 2-hour Arbitrum slice is on the order of 30,000 blocks. That plan was not executed.

Block timestamps below are **PROVEN** when they are a block’s own timestamp. Slice start times are **INFERRED** from the measured seconds-per-block at slice start (`spb` over 3,000 blocks) applied back from that head timestamp.

### Ethereum — complete

Inclusive blocks `26076517`–`26126633` (50,117 blocks). Head timestamp `2026-10-05T14:02:23Z`. Measured block time 12.068 seconds. Inferred start `2026-09-28T14:02:23Z`. Duration 168.0 hours. Progress file: `err = 0`, no gap lines, `done` logs 27. **PROVEN** that this range was walked and every query group returned a log list.

### Base — complete

| Offset | Inclusive blocks | Inferred start | Inferred end | Logs | Errors |
| --- | --- | --- | --- | --- | --- |
| 0h | 52206301–52209901 | 2026-10-05T12:05:49Z | 2026-10-05T14:05:49Z | 2 | 0 |
| 24h | 52163322–52166922 | 2026-10-04T12:13:11Z | 2026-10-04T14:13:11Z | 0 | 0 |
| 48h | 52120397–52123997 | 2026-10-03T12:22:21Z | 2026-10-03T14:22:21Z | 1 | 0 |
| 72h | 52077431–52081031 | 2026-10-02T12:30:09Z | 2026-10-02T14:30:09Z | 1 | 0 |
| 96h | 52034552–52038152 | 2026-10-01T12:40:51Z | 2026-10-01T14:40:51Z | 0 | 0 |
| 120h | 51991735–51995335 | 2026-09-30T12:53:37Z | 2026-09-30T14:53:37Z | 0 | 0 |
| 144h | 51948888–51952488 | 2026-09-29T13:05:23Z | 2026-09-29T15:05:23Z | 0 | 0 |

No gap lines. 14.0 hours of Base, sampled across six days. Block time used: 2.0 s.

### Polygon — complete

| Offset | Inclusive blocks | Inferred start | Inferred end | Logs | Errors |
| --- | --- | --- | --- | --- | --- |
| 0h | 94997869–95002669 | 2026-10-05T12:05:55Z | 2026-10-05T14:05:55Z | 0 | 0 |
| 24h | 94940627–94945427 | 2026-10-04T12:14:52Z | 2026-10-04T14:14:52Z | 0 | 0 |
| 48h | 94883461–94888261 | 2026-10-03T12:25:43Z | 2026-10-03T14:25:43Z | 0 | 0 |
| 72h | 94826340–94831140 | 2026-10-02T12:37:41Z | 2026-10-02T14:37:41Z | 0 | 0 |
| 96h | 94769058–94773858 | 2026-10-01T12:45:38Z | 2026-10-01T14:45:38Z | 0 | 0 |
| 120h | 94711959–94716759 | 2026-09-30T12:58:10Z | 2026-09-30T14:58:10Z | 0 | 0 |
| 144h | 94654740–94659540 | 2026-09-29T13:07:41Z | 2026-09-29T15:07:41Z | 0 | 0 |

No gap lines. 14.0 hours of Polygon Aave V3, sampled across six days. Block time used: 1.5 s.

### Optimism — six slices complete, one stratum not opened

| Offset | Inclusive blocks | Inferred start | Inferred end | Logs | Errors |
| --- | --- | --- | --- | --- | --- |
| 0h | 157804359–157807959 | 2026-10-05T13:38:15Z | 2026-10-05T15:38:15Z | 0 | 0 |
| 24h | 157761250–157764850 | 2026-10-04T13:41:17Z | 2026-10-04T15:41:17Z | 0 | 0 |
| 48h | 157718144–157721744 | 2026-10-03T13:44:25Z | 2026-10-03T15:44:25Z | 0 | 0 |
| 72h | 157675028–157678628 | 2026-10-02T13:47:13Z | 2026-10-02T15:47:13Z | 0 | 0 |
| 96h | 157631910–157635510 | 2026-10-01T13:49:57Z | 2026-10-01T15:49:57Z | 0 | 0 |
| 120h | not opened | — | — | — | exit 1 |
| 144h | 157545619–157549219 | 2026-09-29T13:53:35Z | 2026-09-29T15:53:35Z | 0 | 0 |

Finished slices: 12.0 hours, block time 2.0 s, no gap lines.

### BNB — partial

Block time used: 0.45 s. Each planned slice is 16,000 blocks (2.0 hours).

| Offset | Inclusive plan | Walked through | Logs | Gap blocks | Status |
| --- | --- | --- | --- | --- | --- |
| 0h | 125879781–125895781 (`2026-10-05T13:55:48Z`–`15:55:48Z`) | end | 0 | 0 | complete |
| 24h | 125690091–125706091 (`2026-10-04T14:13:08Z`–`16:13:08Z`) | end | 0 | 300 | finished with holes |
| 48h | 125500153–125516153 (`2026-10-03T14:28:36Z`–`16:28:36Z`) | end | 0 | 200 | finished with holes |
| 72h | 125310147–125326147 (`2026-10-02T14:43:33Z`–`16:43:33Z`) | end | 0 | 320 | finished with holes |
| 96h | 125120824–125136812 (`2026-10-01T14:59:17Z`–`16:59:17Z`) | 125129703 (`~2026-10-01T16:05:55Z`, frac 0.5554) | 0 | 40 inside the walked prefix | stopped |
| 120h | not opened | — | — | — | not started |
| 144h | not opened | — | — | — | not started |

### Arbitrum — not scanned

No head, no start block, no log file. The queue reached Arbitrum only after BNB.

## 6. Data sources

RPC reads used the process environment already present in the backend container. Ethereum, Optimism, BNB, and Arbitrum share one Alchemy host key, so those scans were serial. Base reads used `ARBICORE_RPC_URL` because `ARBICORE_RPC_URL_BASE` (`https://mainnet.base.org`) returned HTTP 403 from the container. Polygon used its own configured URL. No environment variable was changed.

USD prices are Aave V3 `getPriceOracle().getAssetPrice`, 8 decimals. **PROVEN** call path. Ethereum oracle `0x54586be62e3c3580375ae3723c145253060ca0c2`. Base oracle `0x2cc0fc26ed4563a5ce5e8bdcfe1a2878676ae156`. Morpho USD is that Aave price applied to the loan token. **INFERRED** cross-oracle conversion, not Morpho’s own USD.

Gas USD uses the same oracle on the chain’s wrapped native token (WETH on Ethereum and Base). Priority fee is `gasUsed * max(0, effectiveGasPrice - baseFeePerGas)` and is already inside `gasUsed * effectiveGasPrice`. Coinbase payment is `alchemy_getAssetTransfers` category `internal`, to the block’s `miner`. A payment to some other builder address is **NOT_PROVABLE** from this method. Private orderflow is **NOT_PROVABLE**.

The production $50 haircut was not applied.

Raw outputs kept under `/tmp/liq/` on the host and `/tmp/liq_*.jsonl` / `/tmp/liq_*.prog` in the container. Nothing in that set was deleted.

## 7. Liquidation event census

| Chain | Protocol | Events | Oracle gross priced | Visibility class assigned |
| --- | --- | --- | --- | --- |
| Ethereum | Aave V3 | 16 | 16 | 16 |
| Ethereum | Morpho Blue | 11 | 10 | 11 |
| Ethereum | Spark, Compound III | 0 | — | — |
| Base | Morpho Blue | 3 | 3 | 3 |
| Base | Aave V3 | 1 | 1 | 1 |
| Base | Compound III | 0 | — | — |
| Polygon | Aave V3 | 0 | — | — |
| Optimism | Aave V3, Compound III | 0 in finished slices | — | — |
| BNB | Aave V3, Venus | 0 in windows that returned | — | — |
| Arbitrum | — | not scanned | — | — |

Total events found: **31**. Oracle-gross priced: **30**. The unpriced event is Ethereum Morpho block `26086740`, collateral `USP`, loan `frxUSD`: the Aave oracle did not return a usable price for those tokens. **PROVEN** that the event exists; gross is **NOT_RECONSTRUCTABLE**.

## 8. Economic reconstruction method

Components were kept separate.

- Aave gross = oracle USD of `liquidatedCollateralAmount` minus oracle USD of `debtToCover`. The event’s collateral amount is what the liquidator received. Treating the protocol fee as already removed is **INFERRED** from Aave’s event definition; the fee was not re-read from Pool source in this pass.
- Morpho gross = `seizedAssets * oracle.price() / 1e36 - repaidAssets`, then converted with the Aave loan-token price. `price()` is collateral per loan token scaled by `1e36`. **PROVEN** from `idToMarketParams` and `price()` at the liquidation block.
- Same asset (collateral equals debt): unwind `NOT_REQUIRED`. Net can be gross minus gas minus coinbase.
- Different assets: unwind `NOT_RECONSTRUCTABLE`. Gross minus gas minus coinbase is an upper bound. It is not a net.
- Searcher residual is the net ERC-20 balance change of `{tx.from, tx.to, liquidator}`, priced with the same oracle. An empty residual is stored as missing, not as zero. A residual that includes unrelated tokens in the same transaction is not the liquidation edge.
- Visibility, Aave: `getUserAccountData` at block N−1. Health factor below `1e18` is `PRE_BLOCK_VISIBLE`. Health factor at or above `1e18` is `TRADE_BLOCK_ONLY`. **PROVEN** return value. The in-block transaction that moved the account was not identified.
- Visibility, Morpho: at N−1, `position` and `market`, borrow assets via Morpho’s virtual-share conversion (`VIRTUAL_SHARES = 1e6`, `VIRTUAL_ASSETS = 1`, round up), liquidatable when borrowed assets exceed `collateral * price / 1e36 * lltv / 1e18`. The bytecode of the singleton contains `PUSH3 0x0f4240` (the 1e6 constant). **PROVEN** that the constant is in the code. The inequality is **INFERRED** as the matching Morpho Blue share math. The one pre-block Morpho case of economic size is far from the boundary, so the class does not depend on the virtual-asset unit.

No row was dropped because the gross was small or large.

## 9. Pre-block visibility

| Class | Ethereum | Base | Total |
| --- | --- | --- | --- |
| `PRE_BLOCK_VISIBLE` | 6 | 2 | 8 |
| `TRADE_BLOCK_ONLY` | 21 | 2 | 23 |
| `NOT_RECONSTRUCTABLE` | 0 | 0 | 0 |
| `POST_STATE_ONLY` | 0 | 0 | 0 |

Every large Aave gross (the rows at or above $25) has health factor at or above 1 at the end of N−1. Examples, **PROVEN**: block `26077167` health `1.0046`, block `26084021` health `1.0035`, block `26080638` health `1.00035`, block `26106490` health `1.0251`. Those surpluses were not available to an external liquidator who could see only the previous block.

The pre-block events are small, except one:

| Chain | Block | Protocol | Pair | Gross | Health or shortfall evidence |
| --- | --- | --- | --- | --- | --- |
| Ethereum | 26076672 | Aave | WETH / wstETH | $0.00 | health 0.908 |
| Ethereum | 26079704 | Aave | USDC / wstETH | $0.02 | health 0.963 |
| Ethereum | 26080959 | Aave | PT-sUSDE-27NOV2025 / USDT | $0.66 | health 1.0000 just under 1 |
| Ethereum | 26095959 | Aave | WETH / USDe | $0.33 | health 0.9998 |
| Ethereum | 26112137 | Aave | PT-USDe-27NOV2025 / USDe | $0.28 | health 1.0000 just under 1 |
| Ethereum | 26117092 | Morpho | CTOKEN1 / USDC | $99.78 | borrowed raw 2,524,786,854 vs max 2,043,088,306 at LLTV 86% |
| Base | 52121149 | Morpho | mBASIS / USDC | $6.22 | borrowed above the LLTV cap |
| Base | 52078753 | Aave | USDC / WETH | $0.00 | health 0.808 |

N+1 was not queried. **PROVEN** absence of that comparison.

## 10. Size analysis

No size sweep was run. Close-factor headroom above the observed repay amount was not tested. The figures in this report are the observed liquidation sizes.

The pre-block Morpho event repaid about $2,275.84 of USDC and seized collateral the loan-token oracle marked at about $2,375.61. That is one observed size. Whether a smaller repay would have cleared $25 after a real sale of `CTOKEN1` was not measured.

## 11. Competition analysis

On the large `TRADE_BLOCK_ONLY` Ethereum liquidations, the observed internal transfer to `block.miner` is the same order of magnitude as the oracle gross. Priority fee on those same transactions is often about zero, so the competitive payment is the coinbase transfer, not the priority fee. **PROVEN** from the receipt and the internal-transfer query.

Illustrative pairs (oracle gross, coinbase):

- Aave WBTC/LINK, block `26077167`: gross $286.33, coinbase $310.14
- Aave AAVE/USDT, block `26084021`: gross $786.96, coinbase $778.57
- Aave WETH/USDT, block `26080638`: gross $205.45, coinbase $203.51
- Aave LINK/USDT, block `26106490`: gross $155.94, coinbase $155.68
- Morpho PT-cUSD-29JAN2026/USDC, block `26079628`: gross $167.47, coinbase $147.31
- Morpho pufETH/WETH, block `26104570`: gross $71.23, coinbase $66.98

Two Aave events in transaction `0x82ce4f35a117c54e` share one coinbase transfer of $255.34 and one gas cost of $1.84. Their oracle grosses are $176.45 and $86.88. Charging the full tip to each row overstates the cost. Charging it once, the combined remainder is about $6.15, and both rows are `TRADE_BLOCK_ONLY`.

The pre-block Morpho event at block `26117092` has coinbase $0 and priority about $0.01. No builder payment was observed on that transaction. That does not establish a public mempool path. Private orderflow remains **NOT_PROVABLE**.

Liquidator addresses repeat (one address on three events, several on two) and also include many single-use addresses. Repetition is not a single winner of the week, and it is not evidence of exclusive orderflow.

## 12. Net addressable profit

Net is counted only when unwind is `NOT_REQUIRED`, or when a swap quote was actually taken. Neither holds for any row at or above $25. Cross-asset rows therefore stay at an upper bound.

| Count | Value | Meaning |
| --- | --- | --- |
| Events found | 31 | Logged `LiquidationCall` or `Liquidate` |
| Economically priced | 30 | Oracle gross computed |
| Pre-block class assigned | 31 | `PRE_BLOCK_VISIBLE` or `TRADE_BLOCK_ONLY` |
| `PRE_BLOCK_VISIBLE` | 8 | Unhealthy at end of N−1 |
| Oracle gross ≥ $25 | 12 | Before gas, builder payment, and unwind |
| Upper bound (gross − gas − coinbase) ≥ $25 | 1 | The Morpho `CTOKEN1`/USDC row, unwind still open |
| Reconstructable net ≥ $25 | **0** | Same-asset net, or quoted unwind, after gas and coinbase |
| Competition-surviving net ≥ $25 | **0** | Same bar, and the builder payment did not erase it |

The twelve gross rows:

| Block | Protocol | Pair | Visibility | Gross | Gas | Coinbase | Gross − gas − coinbase |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 26077167 | Aave | WBTC/LINK | trade block | 286.33 | 3.32 | 310.14 | −27.12 |
| 26079567 | Aave | WBTC/LINK | trade block | 176.45 | 1.84 | 255.34 | −80.73 |
| 26079567 | Aave | WETH/WETH | trade block | 86.88 | 1.84 | 255.34 | −170.29 |
| 26079628 | Morpho | PT-cUSD/USDC | trade block | 167.47 | 1.34 | 147.31 | 18.82 |
| 26080638 | Aave | WETH/USDT | trade block | 205.45 | 0.99 | 203.51 | 0.95 |
| 26084021 | Aave | AAVE/USDT | trade block | 786.96 | 12.18 | 778.57 | −3.79 |
| 26098187 | Aave | WETH/WBTC | trade block | 93.37 | 1.16 | 101.66 | −9.45 |
| 26103141 | Aave | LINK/USDC | trade block | 123.41 | 0.19 | 119.84 | 3.37 |
| 26104570 | Morpho | pufETH/WETH | trade block | 71.23 | 0.22 | 66.98 | 4.03 |
| 26106270 | Aave | LINK/USDC | trade block | 123.41 | 0.49 | 121.06 | 1.86 |
| 26106490 | Aave | LINK/USDT | trade block | 155.94 | 21.10 | 155.68 | −20.84 |
| 26117092 | Morpho | CTOKEN1/USDC | **pre-block** | 99.78 | 0.11 | 0.00 | 99.67 |

The WETH/WETH row is the only same-asset row in that set. Its own gas and the shared coinbase leave a negative remainder. The other same-asset Ethereum row is Aave USDT/USDT at block `26085027`: gross $14.25, coinbase $12.08, remainder about $0.35, and it is `TRADE_BLOCK_ONLY`. That $0.35 is the best fully reconstructable net in the census. It is under $25 and it was not visible at N−1.

Base’s best pre-block row, Morpho mBASIS/USDC, gross $6.22, gas $2.32 of which priority is $2.31, coinbase $0, searcher residual about $5.48 USDC. Under $25. Unwind of mBASIS was not quoted; the residual is what that searcher kept.

Searcher residuals of hundreds of dollars appear on several rows because the address set also moved WETH that matches the coinbase transfer, or because the transaction did other business. Block `26117092` shows a WETH residual of about $857 against a liquidation gross of $99.78. That residual is not the liquidation net.

## 13. Repeatability

A cell is a repeated chain × protocol × collateral × debt pattern, not one transaction.

Patterns with more than one event in this census:

- Ethereum Aave LINK debt against USDC, twice (blocks `26103141` and `26106270`). Both `TRADE_BLOCK_ONLY`. Both paid a coinbase transfer within a few dollars of the gross.
- Ethereum Aave WBTC/LINK, twice, including two legs of one transaction. Both `TRADE_BLOCK_ONLY`. Coinbase consumed the combined surplus.
- Base Morpho cbADA/WETH, twice. Both `TRADE_BLOCK_ONLY`. Gross $0.15 and about $0.00.

No pair repeats as `PRE_BLOCK_VISIBLE` with gross at or above $25. The `CTOKEN1`/USDC Morpho case occurs once.

Two Morpho `srNUSD`/USDC legs share transaction `0x5af6cc4bcec812d6` at block `26096417`. Combined oracle gross is about $25.17. Gas once is $0.18. Coinbase is $0. Remainder about $24.99. Both legs are `TRADE_BLOCK_ONLY`, and the `srNUSD` residual could not be priced. That is one in-block transaction sitting just under the gross bar, not a pre-block cell.

## 14. Strategy-cell candidates

A cell needs all of: repeated real liquidations, pre-block visibility, reconstructable economics, a realistic size, positive net, at least $25 net on repeated observations, competition that does not erase the edge, a defensible mechanism, and enough evidence to design a detector.

No cell meets that list.

| Chain | Protocol | Markets in the sample | Liquidations | Priced | Pre-block | ≥ $25 gross | ≥ $25 net | Competition-surviving | Best figure | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Ethereum | Aave V3 | mixed, see §12 | 16 | 16 | 5 | 9 | 0 | 0 | same-asset remainder $0.35, trade-block | no cell |
| Ethereum | Morpho Blue | mixed, see §12 | 11 | 10 | 1 | 3 | 0 | 0 | upper bound $99.67, unwind open, one event | no cell |
| Ethereum | Spark, Compound III | queried | 0 | — | — | — | — | — | — | no events in a complete window |
| Base | Morpho Blue | cbADA/WETH, mBASIS/USDC | 3 | 3 | 1 | 0 | 0 | 0 | pre-block gross $6.22 | no cell |
| Base | Aave V3 | USDC/WETH | 1 | 1 | 1 | 0 | 0 | 0 | gross ~ $0 | no cell |
| Polygon | Aave V3 | pool only | 0 | — | — | — | — | — | — | no events in a complete sample |
| Optimism | Aave V3, Compound III | queried on 6 slices | 0 | — | — | — | — | — | — | sample incomplete |
| BNB | Aave V3, Venus | 55 Venus markets | 0 in read windows | — | — | — | — | — | — | sample incomplete |
| Arbitrum | — | not read | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | not scanned |

The nearest observation is one pre-block Morpho liquidation. It is not a cell. Designing a detector from it would treat a single unrecovered unwind as a strategy.

## 15. False positives and non-actionable events

- Trade-block liquidations whose health factor was at least 1 at N−1. The large oracle bonus is real as an accounting identity of the fill. It was not a previous-block opportunity.
- Coinbase transfers that match the surplus. The gross survives only until the builder payment is subtracted.
- Searcher-set residuals that equal the coinbase amount, or that dwarf the liquidation gross. They record other token flow in the same transaction.
- Dust pre-block Aave liquidations (gross from a fraction of a cent to $0.66) whose gas is larger than the gross.
- The unpriced USP/frxUSD Morpho event. It is a real liquidation and an unpriced one.
- Empty Base, Polygon, Optimism, and BNB query results. They are actionable only as “no log in this range.” They are not a market-wide absence of liquidations.

## 16. Data gaps and limitations

### Incomplete ranges and why

Optimism offset 120h. **Reason:** `eth_blockNumber` did not return a hex string. The process raised `TypeError: int() can't convert non-string with explicit base` at startup, before any block range was written. Exit code 1. A one-shot retry was queued and had not started when the census was stopped. No from-block and no to-block exist. This stratum is **INCOMPLETE**. It is not a zero-liquidation observation.

BNB offset 24h, HTTP 429 after the per-batch retries (`retries_exhausted`). 15 windows, 300 blocks, all four query groups failed together on each window. The rest of `125690091`–`125706091` returned empty log lists.

- 125692471–125692490
- 125692511–125692530
- 125692591–125692610
- 125693291–125693310
- 125694791–125694810
- 125695531–125695550
- 125695771–125695790
- 125695911–125695930
- 125698371–125698390
- 125700751–125700770
- 125702831–125702850
- 125703011–125703030
- 125703251–125703270
- 125704531–125704550
- 125705571–125705590

BNB offset 48h, same 429 reason. 10 windows, 200 blocks, inside `125500153`–`125516153`.

- 125503233–125503252
- 125503693–125503712
- 125504353–125504372
- 125504393–125504412
- 125504533–125504552
- 125505193–125505212
- 125509033–125509052
- 125509953–125509972
- 125512673–125512692
- 125513813–125513832

BNB offset 72h, same 429 reason. 16 windows, 320 blocks, inside `125310147`–`125326147`.

- 125313387–125313406
- 125314167–125314186
- 125314927–125314946
- 125315207–125315226
- 125317747–125317766
- 125318927–125318946
- 125319907–125319926
- 125320047–125320066
- 125320147–125320166
- 125320827–125320846
- 125320867–125320886
- 125321127–125321146
- 125321947–125321966
- 125322007–125322026
- 125324727–125324746
- 125325647–125325666

BNB offset 96h. Walked `125120824`–`125129703` (fraction 0.5554). **Reason for the tail:** the census was stopped by instruction during this slice. Unscanned tail `125129704`–`125136812` (7,109 blocks). Inside the walked prefix, two windows failed with HTTP 429: `125122664`–`125122683` and `125127984`–`125128003`.

BNB offsets 120h and 144h. **Reason:** not started. The queue was stopped during offset 96h. No block numbers were assigned.

Arbitrum, all seven planned 30-minute slices. **Reason:** not started. No request was sent.

### Other limits

- The ideal window was about 14 days on every chain. Ethereum covered 7 contiguous days. Base, Polygon, and Optimism covered 2 hours per day on the slices that finished. That is a stratified sample forced by the 10-block log cap, chosen before the economics, and not shortened because early rows looked profitable.
- Unwind quotes were not taken. Every cross-asset “net” is withheld.
- No size sweep and no N+1 state.
- Builder payments that do not go to `block.miner`, and private relay traffic, are **NOT_PROVABLE**.
- Aave protocol-fee treatment is **INFERRED**.
- Morpho health uses the virtual-share formula. The economically large pre-block case is not near the boundary. Two Base Morpho rows classified `TRADE_BLOCK_ONLY` sit within a few parts per ten-thousand of the cap; those two classes are formula-sensitive. Their gross is $0.15 and about $0.
- One Ethereum Aave health factor sits at `1.00000000152` (USDT/USDT, block `26085027`) and is classified `TRADE_BLOCK_ONLY` by the same rule as every other row.
- Base RPC was the existing `ARBICORE_RPC_URL`, not the per-chain variable that returned HTTP 403.
- Polygon gas was not an issue because Polygon produced no events to price. The pricer’s native token for Polygon is WMATIC/POL, and it was not exercised.

## 17. Recommended next gate

Do not open an implementation or liquidation-engine design gate.

The completed Ethereum week is enough to reject a specific claim: the large Aave and Morpho fills in blocks `26076517`–`26126633` were not a repeated pre-block $25 net. It is not enough to close the family. Arbitrum was never read, BNB and one Optimism stratum are incomplete, and the single pre-block upper bound of $99.67 has no swap quote.

A later research pass, if one is commissioned, would be a bounded finish of the missing ranges plus one unwind quote on Morpho market collateral `0x387d46494f6dc5c6b26abc20ae40623ac041dd92` / loan USDC at block `26117092`. That quote is still research. It is not a reason to write a strategy module from this file.

## 18. Classification

**PARTIAL.**

Ethereum, Base, and Polygon completed the windows they opened, with explicit block bounds and zero silent gaps. Optimism, BNB, and Arbitrum did not. Full six-chain coverage is not claimed.

Engine answer, separate from the coverage label: **INSUFFICIENT_EVIDENCE** to build a liquidation strategy. The missing evidence is the unscanned ranges in §16 and a real unwind cost on the one pre-block row whose oracle gross exceeds $25. The rows that already have a full net are under $25, and the large gross rows were either invisible at N−1 or paid to the block producer.
