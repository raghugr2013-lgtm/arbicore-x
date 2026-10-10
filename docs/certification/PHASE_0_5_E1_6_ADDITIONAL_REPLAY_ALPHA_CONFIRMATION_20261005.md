# E1.6 — Additional replay / alpha confirmation

Gate: `E1.6_ADDITIONAL_REPLAY_READ_ONLY`  
Date: 2026-10-05  
Mode: read-only. No production code, quoter, scanner, route, Gate 7, economics, RPC configuration, database, container, deploy, signing, or broadcast change.

Certified input: `docs/certification/PHASE_0_5_E1_5_V4_V2_COVERAGE_REPLAY_AUDIT_20261005.md`.

Window: Ethereum blocks 26,125,444–26,125,744 (2026-10-05T10:02:47Z–11:02:47Z). Same hour as E1.5.

Evidence labels: **PROVEN**, **INFERRED**, **HYPOTHESIS**, **NOT_PROVABLE**.

This gate supersedes one E1.5 figure. E1.5 priced the TRUMP path with a single 1% haircut and reported a previous-block surplus of about $25.5 on row 2. The mint-to-swap ratio on every closed cycle is 0.9801, which is two successive 1% haircuts. Replayed with that ratio, row 2’s previous-block peak is **$17.12**, under $25. The correction is in section 3.

---

## 1. Executive Summary

The TRUMP path is a two-token conversion, not a generic Uniswap v2 arbitrage. Both tokens are named MAGA and symbol TRUMP. Each has its own Uniswap v2 WETH pair. Token B pulls token A and mints itself one-for-one against the amount it actually receives. A second function burns B and sends A back.

**PROVEN:** In this hour the forward conversion (buy A, mint B, sell B) appears in **69** transactions, **68** of them a closed WETH cycle. The reverse conversion (buy B, redeem A, sell A) appears in **58** transactions. **55** of those sell about 98.01% of the redeemed A, which is the closed taxed cycle. **Three** sell about twice that amount, so their headline WETH surplus is not a closed cycle.

**PROVEN:** The forward cycle is positive before the block on many trades, and five distinct previous-block states have a size whose gross quote is at least $25. Two further previous-block states do the same in the reverse direction. The profitable size is about **0.4–0.8 ETH**. At a $10,000 quote every swept state is negative by roughly **$1,100–$1,700**.

**PROVEN:** No closed cycle, forward or reverse, left the searcher **$25 after the observed competitive payment**. Where the previous-block gross quote was $31–$119, the winner paid almost all of it to the builder, either as a coinbase transfer or as a priority fee, and kept about **$1–$7**. The largest kept residual in the hour is **$14.33**, and that trade was created by earlier swaps in the same block. It was negative at the previous block.

**PROVEN:** Among the 45 flash-loan transactions that also touched Uniswap v4, the only after-gas surplus above $25 is the Aave WETH migration already classified in E1.5, and the mixed TRUMP row. The next flash-loan/v4 surpluses are **$4.78, $2.97, and $1.47** before the builder is fully paid. None is a Gate 7 candidate on realized economics.

**PROVEN:** The two DEXTF rows are a basket deposit into the index token `0x39953e6429210c39d11688fa40219c811287caad`, followed by a sale of DEXTF for WETH. Corrected surplus after gas and before the builder payment is about **$0.79** and **$0.31**.

| Decision | Result |
|---|---|
| TRUMP bridge | `COMPETITION_ERASED` |
| Uniswap v4, this window | `INSUFFICIENT_EVIDENCE` for a repeatable pre-block Gate 7 opportunity |
| DEXTF index path | `NOT_PROFITABLE` at Gate 7 |
| E1.6 next gate | `DEPRIORITIZE` |
| Implement v4, v2, or the bridge | **NO** |

---

## 2. E1.5 Evidence Used

**PROVEN (carried forward, not re-derived):** The venue gap is real. Uniswap v4 PoolManager `0x000000000004444c5dc75cB358380D2e3dE08A90` is outside the ArbiCore route graph. The live v2 quoter is SushiSwap only. Eight v4 rows in the E1 subset do not clear $25 after native ETH and gas. The 718.89 WETH row is an Aave residual. The hour contained 7,703 v4 Swap logs, 5,422 transactions, 604 pools, and 45 flash-loan transactions that also touched v4.

**Superseded:** E1.5’s previous-block TRUMP quote used one 1% haircut. Section 3 replaces that with the ratio measured on all 68 forward cycles. Row 2 is no longer a previous-block $25 cell. Row 7’s previous-block peak falls from about $12 to **$5.96**.

The production $50 medium haircut was not used. Gate 7 remains `atomic_profit_usd >= $25` as an external reference only. It was not modified.

---

## 3. TRUMP Bridge Mechanism

This is not Uniswap v2 arbitrage. The two tokens are different contracts. The link is a mint/redeem on token B, not a shared-pool hop.

| Piece | Value | Label |
|---|---|---|
| Token A | `0x576e2bed8f7b46d34016198911cdf9886f78bea7`, name MAGA, symbol TRUMP, 9 decimals | **PROVEN** (`name`, `symbol`, `decimals` at block 26,125,650) |
| Token B | `0x6aa56e1d98b3805921c170eb4b3fe7d4fda6d89b`, same name and symbol, 9 decimals | **PROVEN** |
| Pair A / WETH | `0xe4b8583ccb95b25737c016ac88e539d0605949e8`, token0 = A, token1 = WETH, Uniswap v2 pair code | **PROVEN** |
| Pair B / WETH | `0x56bc8f3293f53825c9fbd6ddfe0cafefa82820d0`, token0 = B, token1 = WETH | **PROVEN** |
| Forward entry | Token B selector `0x24a29d50` | **PROVEN** (dispatcher jump, and the selector is embedded in the row 7 calldata) |
| Reverse entry | Token B selector `0x41477451` | **PROVEN** (dispatcher) |

**PROVEN from the bytecode of `0x24a29d50`:** the function reads token A’s balance of token B, `transferFrom`s the caller’s token A to token B, reads the balance again, and passes the difference into an internal routine whose failure path uses the standard ERC-20 mint error selector `0xec442f05`. The mint is therefore the amount token B actually received, not the nominal argument.

**PROVEN from the bytecode of `0x41477451`:** the function takes one `uint256`, calls an internal burn-shaped helper with the caller and that amount, then `transfer`s token A to the caller.

**PROVEN from logs, all 68 forward cycles:** B minted / pair-A `amount0Out` lies in **[0.980099984, 0.980100000]**. Minted B equals the B sold into pair B within 1 wei on 66 of 68 cycles, and within 1 wei on the other two. **INFERRED:** the 0.9801 factor is two successive 1% transfer taxes on token A (pair to searcher, then searcher to token B). Token A’s code contains the constant 100. The exact fee expression inside `transfer` was not line-decompiled; the ratio itself does not depend on that decompilation.

**PROVEN:** a constant-product quote with the 0.3% pair fee and that 0.9801 factor reproduces realized WETH out. Median absolute error **26,152 wei** (about $0.00007). Ten of 67 comparable cycles miss by more than 0.001 ETH, maximum about 0.003 ETH, consistent with an earlier reserve change inside the same transaction that the previous-Sync snapshot does not see.

Forward direction, as executed:

1. Pay WETH into pair A, receive token A.
2. Call `0x24a29d50` on token B. Token B pulls A and mints B one-for-one with what arrived.
3. Sell that B to pair B for WETH.

Reverse direction, as executed on the closed subset:

1. Pay WETH into pair B, receive token B.
2. Burn B through `0x41477451`. The Transfer of A out of token B equals the burned B (**ratio 1.000** on all 58 redeems).
3. Sell A to pair A. On the closed subset the pair’s `amount0In` is **0.9801** of the redeemed A.

**INFERRED:** the reverse sale is taxed on the way into pair A even though the redeem Transfer logs the full amount. The two-tax reverse quote at the previous block matches the largest closed reverse fill: block 26,125,620, 0.70 ETH, quote **$88.73**, realized spread **$88.69**.

Row 7 (`0x3f3987bd…ad7207ac`, block 26,125,650, index 8) is this forward path and nothing else. Input selector `0x00000000`, length 418 bytes, which is a searcher-specific encoder, not an ABI call. The row contains pair A, token A, selector `0x24a29d50`, token B, and pair B. No v4 swap.

Row 2 (`0x502a3acf…78bcfd78`, block 26,125,593, index 21) uses the same bridge and also a v4 two-hop plus the v3 USDC/WETH 0.01% pool. Its bridge leg is the mechanism above. Its extra legs are not.

---

## 4. TRUMP Repeatability

Search was not limited to flash loans. Filters over the full hour:

- Swap logs on both pairs
- Token B mints (`Transfer` from `address(0)`)
- Token A transfers to token B
- Token B transfers to `address(0)` (redeems)

**PROVEN counts:**

| Set | Transactions |
|---|---|
| Swaps on pair A | 131 |
| Swaps on pair B | 1,390 |
| Both pairs, no mint | 127 including the 69 below |
| Forward mechanism: mint B, A sent to B, and both pairs swapped | **69** |
| Of those, buy A / mint / sell B | **68** |
| Forward but not that direction | **1** (`0x9005a352…4c00e09d`, buys A, no B sale, one v3 swap) |
| Reverse: burn B, A returned from B, buy B, sell A | **58** |
| Reverse with sale ≈ 0.98 of the redeem (closed) | **55** |
| Reverse with sale ≈ 1.96 of the redeem (not closed) | **3** |

The 69 forward transactions span blocks 26,125,557–26,125,679 (**10:25:23Z–10:49:47Z**), 32 blocks, 25 distinct `tx.from` addresses, 10 `tx.to` contracts. The 58 reverse transactions span blocks 26,125,576–26,125,736, 28 blocks. The pattern is absent in the first ~22 minutes of the hour and, on the forward side, absent in the last ~13 minutes.

**PROVEN:** every mint of B in the hour is inside a transaction that also swaps both pairs. The bridge was not used as a standalone wrap in this window.

**PROVEN economic buckets, forward closed cycles (68):**

| Bucket | Count |
|---|---|
| Gross swap surplus > $0 | 68 |
| After gas, before builder payment > $0 | 68 |
| After gas, before builder payment ≥ $25 | **8** |
| After gas and observed builder/priority payment > $0 | 67 |
| After gas and that payment ≥ $25 | **0** |
| Previous-block quote at the traded size > $0 | 45 |
| Previous-block quote at the traded size ≥ $25 | **6** (5 blocks; block 26,125,588 counted twice) |
| Previous-block best size on a 0.01 ETH grid ≥ $25 | **5 distinct blocks** |

**PROVEN, reverse closed cycles (55):** gross surplus > $0 on all 55. Gross surplus ≥ $25 on **2**. After the observed payment, neither of those two remains above $25 ($4.98 and $4.01). The three non-closed reverses show gross WETH gaps of about $456, $157, and $47 only because they sold roughly twice the redeemed A. Those three are excluded from the cycle counts above.

Pair B’s 1,390 swaps are mostly not this mechanism. A swap on either pair is not treated as arbitrage.

---

## 5. TRUMP Size Sweep

Quote: Uniswap v2 `amountOut` with fee 997/1000, then two 99/100 round-downs, then the other pair. Spot is the Uniswap v3 USDC/WETH 0.05% pool `0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640` at the relevant block. Previous-block reserves are `getReserves` at block N−1.

**PROVEN** where the same quote matches a fill that had no earlier same-block sync (error at the median above). **INFERRED** for the 10 fills whose intra-transaction reserves the snapshot misses, by at most a few dollars.

### Forward, previous block, gross surplus before gas and before any builder payment

| Block | 0.1 ETH | 0.3 ETH | 0.5 ETH | 1 ETH | Peak | $10,000 |
|---|---:|---:|---:|---:|---|---:|
| 26,125,588 | $14.71 | $33.01 | $36.98 | −$12.34 | $37.30 at 0.46 ETH | −$1,460 |
| 26,125,592 | $15.63 | $35.80 | $41.66 | −$2.84 | $41.71 at 0.48 ETH | −$1,424 |
| 26,125,610 | $27.94 | $72.24 | $101.58 | $113.12 | **$118.81 at 0.82 ETH** | −$1,063 |
| 26,125,635 | $20.06 | $49.13 | $63.94 | $41.95 | $66.20 at 0.62 ETH | −$1,265 |
| 26,125,647 | $13.13 | $28.76 | $30.64 | −$21.57 | $31.52 at 0.43 ETH | −$1,451 |

The realized 0.8217 ETH fill in block 26,125,610 matches that previous-block quote to the cent ($118.81). **PROVEN.**

Gross surplus drops below $25 past about **0.63–1.58 ETH** on these states, and the last positive 0.01 ETH step is about **0.86–1.67 ETH**. Pair B’s WETH reserve is about **17–19 ETH**, so a $10,000 input (~3.7 ETH) walks deep into that reserve. **PROVEN** for the tabulated states: the $10,000 quote is largely negative.

### Reverse, previous block, two-tax sale, same definition

| Block | 0.1 | 0.3 | 0.5 | 0.7 | 1 ETH | $10,000 |
|---|---:|---:|---:|---:|---:|---:|
| 26,125,620 | $23.90 | $60.19 | $81.61 | $88.73 | $73.76 | −$1,197 |
| 26,125,638 | $20.16 | $49.16 | $63.56 | $63.91 | $39.24 | −$1,301 |

The 0.704 ETH reverse fill in block 26,125,620 realized **$88.69**, against the 0.70 ETH quote of **$88.73**. **PROVEN.**

On the forward-opportunity blocks, the reverse quote at 0.3 ETH is about **−$58 to −$105**. The spread faces one way at a time. **PROVEN** for those states.

Classification of the size curve: the gross edge is real and repeats at sub-ETH size, and it is not a $10,000 strategy. It is also not a one-trade artifact. After the auction it is not a Gate 7 strategy. That is `COMPETITION_ERASED`, not a scalable alpha.

---

## 6. TRUMP Pre-Block Replay

For each forward cycle the quote was evaluated at:

- end of block N−1 (`getReserves`)
- immediately before the transaction (last `Sync` on each pair before the transaction’s first log; block N−1 reserves if that pair had not yet synced in the window)
- end of block N
- end of block N+1

Classification uses the **traded size**, not the best size.

| Class | Forward cycles | Meaning |
|---|---:|---|
| `PRE_BLOCK_POSITIVE` | 45 | Quote at block N−1 > $0 |
| `TRADE_BLOCK_ONLY` | 22 | Block N−1 ≤ $0, and an earlier same-block `Sync` makes the pre-transaction quote > $0 |
| `POST_STATE_ONLY` | 0 | |
| `NEGATIVE` | 1 | See below |
| `NOT_RECONSTRUCTABLE` | 1 | The non-cycle in section 4 |

The one `NEGATIVE` label is `0x31b510c8…9273c272`, block 26,125,557, index 325, the first forward fill. Block N−1 at its 0.341 ETH size is about **−$40**. Three earlier transactions in that block bought B (0.198, 0.099, and 0.297 ETH). Pair A had no `Sync` yet in the window, so the pre-transaction combiner skipped the row. The realized gross surplus is **+$20.29**. **PROVEN:** the edge was not on the previous block. **INFERRED:** the three B buys created it. Kept profit **$14.33** after $5.96 of gas and no coinbase transfer. This is the hour’s largest kept residual, and it is `TRADE_BLOCK_ONLY` in substance.

Fills whose previous-block quote at the traded size is ≥ $25:

| Tx | Block / idx | Block N−1 | Realized before builder | Kept | Note |
|---|---|---:|---:|---:|---|
| `0x8ad28cf3…b3ffe145` | 26,125,610 / 1 | $118.81 | $7.28 | $7.28 | Priority fee is the bid. No earlier sync. |
| `0x7732fcde…5cb467da` | 26,125,635 / 41 | $66.20 | $95.74 | $5.35 | Earlier same-block flow raised the realized number above the previous-block quote. |
| `0xa50d0967…b7724247` | 26,125,592 / 1 | $41.71 | $41.63 | $1.71 | No earlier sync. Quote equals the fill. |
| `0x9386a4f1…f321dd6c` | 26,125,588 / 18 | $37.31 | $110.11 | $4.66 | Earlier same-block flow. |
| `0xf1dfd369…1b1ff77b` | 26,125,588 / 28 | $37.30 | $31.08 | $1.26 | Same previous-block state, second fill, after the first searcher. |
| `0x5c9ed76f…6ecc4031` | 26,125,647 / 0 | $30.95 | $30.81 | $0.96 | No earlier sync. |

E1.5 row 7 is previous-block positive but small: **$5.96** at 0.19 ETH. Its realized $37.59 before the builder existed only after earlier pair-B swaps in block 26,125,650. Kept **$3.39**. **PROVEN.**

E1.5 row 2 is previous-block positive at **$17.12** peak, under $25. Realized bridge-leg surplus before the builder is **$29.98** only after earlier same-block swaps. The v4/v3 legs are extra. Coinbase payment consumes the bridge leg; v2-only net is about **−$0.02**. E1.5’s combined kept figure of about $2.97 still stands for the whole transaction and is under $25. **PROVEN.**

The $46.35 before-builder fill `0x13495863…8a793229` (block 26,125,609, kept $13.45) is `TRADE_BLOCK_ONLY`. Previous-block peak is **−$0.46**.

---

## 7. Builder Payment / Competition

Identity used:

`searcher net = swap surplus − gas − coinbase payment`

Gas is `gasUsed × effectiveGasPrice` and therefore already includes the priority fee. The coinbase payment is the sum of internal ETH to `block.miner` on that transaction (`alchemy_getAssetTransfers`, category `internal`). Protocol and bridge fees sit inside the swap surplus, because the measured quantity is WETH out minus WETH in. The production $50 haircut was not applied.

**PROVEN:** of the 8 forward fills with (surplus − gas) ≥ $25, coinbase tips were about $105, $90, $40, $34, $33, $30, $30, and $30. Kept amounts: $13.45, $5.35, $4.66, $3.39, $2.23, $1.71, $1.26, $0.96, and **−$0.02** on the mixed row’s bridge leg. The $13.45 and the row-7 $3.39 were not previous-block $25 opportunities.

**PROVEN, the $118.81 previous-block opportunity:** `0x8ad28cf3…b3ffe145`, gas used 215,954, effective gas price 190.20 gwei, block base fee 0.143 gwei. Base-fee cost is about **$0.08**. About **$111.44** is priority fee, paid to the builder through the gas price, with **zero** coinbase transfer. A later transaction in the same block (`0x89ccdc77…132805f7`) found only $5.19 left, paid a $4.39 coinbase tip at priority 0, and kept $0.71.

**PROVEN, reverse:** the $88.69 closed cycle paid an $83.62 coinbase tip and kept $4.98. The $65.46 closed cycle paid about $61 through gas (coinbase tip $0) and kept $4.01.

Private relay payloads were not observed. **NOT_PROVABLE** whether any of these transactions were submitted through a private relay. A zero priority fee plus a coinbase transfer is the usual pattern here. It is not proof of a private relay.

No closed cycle cleared $25 after these payments.

---

## 8. Reverse Direction

The reverse function exists and was used. It is not a hypothetical.

**PROVEN:** 58 redeems. Redeemed A logged from token B equals burned B (ratio 1). On 55 transactions the A that entered pair A is 0.9801 of that redeem, and both pairs move. On 3 transactions the A that entered pair A is 1.9602 of the redeem (exactly two taxed lots). Those three are `0xd4dfeb57…65d1ecf1` (apparent WETH gap ~$456, kept ~$446), `0x7af6c7cc…114360d8` (~$157), and `0xc79dd34f…ef945027` (~$47). The extra lot is not explained by the redeem. They are not counted as arbitrage profit. **NOT_PROVABLE** where the second lot of A came from (inventory, a mint, or another venue) without a further token-flow pass. The ratio is enough to reject a closed-cycle reading.

**PROVEN:** the two closed reverses above $25 were previous-block positive under the same two-tax model that matches the fill, and both were paid down to about $5. Reverse at $10,000 on those two states is about **−$1,197** and **−$1,301**.

**PROVEN:** on the five forward states in section 5, reverse at 0.3 ETH is negative by tens of dollars. Gate 7 fails in the reverse direction after the observed payment, and it also fails as a simultaneous two-way quote.

---

## 9. Additional V4 Sample

v4 was not implemented and not quoted as a new production path. The sample is the **census of all 45 flash-loan transactions that also emitted a v4 Swap** in the hour, wealth-accounted in E1.5 with native ETH included, and re-read here. That census is not a pick of winners. A receipt pass was added for seven hashes: the two DEXTF rows, the three largest non-migration positive residuals, and two large negative residuals.

**PROVEN, the 45:**

| After gas, before coinbase | What it is |
|---|---|
| +$1,952,499 and −$1,952,424 | The paired Aave WETH migration. Not arbitrage. |
| +$32.97, kept $2.97 | Mixed TRUMP row 2. Classified in sections 3–7. The v4 leg is not the $25. |
| +$4.78, kept $0.24 | `0xdb589055…0a676867`, 6 v4 pools and 1 v3 pool, 3 tokens |
| +$2.97, kept $0.04 | `0x20a4db10…716c5342`, 1 v4 pool |
| +$1.47, kept $1.47 | `0x16875ad7…b109926e`, 4 v4 pools and 1 v3 pool |
| Seven more between $0.27 and $1.04 after gas | Includes the two DEXTF rows ($0.79 and $0.70 on this flat $2,716 pricing; E1.5’s own-spot figures are $0.79 and $0.31) |
| Large negatives, about −$100 to −$595 | Same executors as other rows in the nine (`0x950fd558…`, `0x78dcc4a0…`). Several carry unpriced non-ETH residuals. **NOT_PROVABLE** as a loss distribution. |

**PROVEN:** aside from the migration pair and the mixed TRUMP row, **zero** flash-loan/v4 transactions clear $25 after gas, and **zero** leave the searcher $25 after the coinbase payment.

Pre-block and $10,000 quotes for `0xdb589055`, `0x20a4db10`, and `0x16875ad7` were **not** rebuilt. Their pool keys were not recovered in this pass. **NOT_PROVABLE** whether some other size would have cleared $25. Their realized sizes did not. E1.5 already size-swept the decoded v4 routes from the original nine (ETH/WBTC, ETH/IMD, ETH/FUSE, ETH/APE, ETH/USDT) and none cleared $25 at the previous block or at $10,000.

The other ~5,377 v4 transactions in the hour were not individually priced. **NOT_PROVABLE** that none of them is a pre-block $25 cycle. What this window does show is that the flash-loan intersection, which is where an atomic searcher cycle would appear, does not contain one that survives Gate 7.

---

## 10. DEXTF Analysis

Both rows are from `0x6c14f565…37f203a7` to `0xd35804a63f…3e22cd01`, selector `0x0cf5c02a`. Index token `0x39953e6429210c39d11688fa40219c811287caad` returns the name “DEXTF Opportunities - v2”.

**PROVEN flow, row 5** `0x3a8abd0f…894814dc`, block 26,125,610, index 82. Morpho flash 0.025212 WETH, fee 0.

1. Sushi pair `0xd3c41c08…` : 0.002485 WETH in, 145.94 DEXTF out.
2. v4 and the v3 WBTC/USDT pool `0x56534741…` produce 0.000566 WBTC and 0.004792 WETH.
3. Those three amounts (DEXTF, WBTC, WETH) are transferred into the index token.
4. Pair `0x284e590d…` (XTF / DEXTF) emits `amount0In` of 0.212 XTF and `amount1Out` of 1,513.26 DEXTF. No ERC-20 transfer of XTF from the searcher is in the receipt. The index is the party that causes that pair to release DEXTF.
5. Pair `0xa1444ac5…` (DEXTF / WETH): 1,513.26 DEXTF in, 0.025593 WETH out.
6. Flash repaid.

Row 6 `0x56aebfc4…41270127`, block 26,125,683, index 122, is the same shape without the v3 USDT leg: v4 supplies the WBTC and the WETH that go into the index. Flash 0.017486 WETH. DEXTF out of the index pair 1,028.62. WETH out of the DEXTF/WETH pair 0.017686.

**INFERRED:** the index mints its share token into its own pool and takes DEXTF out, after being delivered a basket. That is a vault-versus-pool conversion. It is not a plain multi-DEX hop, and it is not the TRUMP bridge.

**PROVEN:** corrected searcher surplus after gas and before the builder payment is about **$0.79** (row 5) and **$0.31** (row 6). Neither clears Gate 7. The E1 dollar labels ($62.50 and $43.08) are the uncorrected WETH-transfer residual.

**NOT_PROVABLE:** previous-block positivity. The index mint was not re-simulated. A previous-block quote could not raise a realized sub-dollar cycle to $25 unless a much larger size works, and that size was not quoted. **HYPOTHESIS:** the discrepancy is a small basket/pool gap, not a family ArbiCore already routes. No current quoter path covers an index mint. That is a new mechanism in the descriptive sense. It is not an alpha candidate on this evidence.

---

## 11. Alpha Classification

| Mechanism | Label | Why |
|---|---|---|
| TRUMP forward and reverse bridge | `COMPETITION_ERASED` | Repeated, previous-block gross quotes of $31–$119 at 0.4–0.8 ETH, and every observed winner kept ≤ $7.28 on those pre-block $25 states. Zero closed cycles kept $25. |
| The $14.33 first fill | `TRADE_BLOCK_ONLY` | Positive only after three same-block buys of B. Under $25 even then. |
| The three double-lot reverse transactions | Not arbitrage on the measured ratio | Sale is 1.96× the redeem. Surplus is not a closed cycle. |
| Uniswap v4 flash-loan intersection | `INSUFFICIENT_EVIDENCE` | No repeatable previous-block $25 cycle found. Realized non-migration residuals are a few dollars or less. Undecoded routes and the 5,377 non-flash transactions were not fully replayed. |
| DEXTF index basket | `NOT_PROFITABLE` | Realized surplus under $1. Previous-block mint rate not reconstructed. |
| Aave 718 WETH migration | Not an alpha candidate | Already classified. Residual collateral movement. |

One profitable transaction is not an alpha candidate. The TRUMP bridge clears the “repeated” and “previous-block visible” tests and fails the Gate 7 test after competition, at every size that was swept.

---

## 12. Opportunity Cells

Distinct previous-block states whose best gross quote is ≥ $25. Kept is the best observed execution of that state, after gas and the observed builder or priority payment.

| Cell | Direction | Peak gross, previous block | Size | Best kept | After payment ≥ $25 |
|---|---|---:|---:|---:|---|
| Block 26,125,610 | Forward | $118.81 | 0.82 ETH | $7.28 | No |
| Block 26,125,620 | Reverse | $88.73 | 0.70 ETH | $4.98 | No |
| Block 26,125,635 | Forward | $66.20 | 0.62 ETH | $5.35 | No |
| Block 26,125,638 | Reverse | $63.91 | 0.70 ETH | $4.01 | No |
| Block 26,125,592 | Forward | $41.71 | 0.48 ETH | $1.71 | No |
| Block 26,125,588 | Forward | $37.30 | 0.46 ETH | $4.66 | No |
| Block 26,125,647 | Forward | $31.52 | 0.43 ETH | $0.96 | No |

All seven are negative at $10,000 by more than $1,000. **PROVEN.**

---

## 13. Root Cause / Coverage Implications

**PROVEN:** ArbiCore does not route Uniswap v2 factory `0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f`, and it does not route token B’s mint/redeem. The live v2 quoter remains SushiSwap-only. That gap is why these cycles are invisible to the scanner.

**PROVEN:** closing the gap with a generic Uniswap v2 hop would not represent this path. The two TRUMP tokens do not share a pool. The conversion is `0x24a29d50` / `0x41477451`, and token A’s transfer tax is part of the price.

**PROVEN:** even a correct quote of this path, in this hour, does not produce a cycle that a searcher kept at ≥ $25. The previous-block gross edge was real. The auction took it. The size that works is under 1 ETH, and the production $10,000 quote is the wrong size.

v4 remains a coverage gap and, on the flash-loan intersection in this hour, not a Gate 7 gap. The DEXTF index is a third mechanism, economically negligible here.

---

## 14. E1.6 Decision

The decision rule required previous-block visibility, reproducible positive economics, a defensible mechanism, repeated observations, and a path to the existing $25 Gate 7.

The TRUMP bridge has the first four, at sub-ETH size, for about twenty-five minutes of this hour. It does not have the fifth. After the observed builder payment or priority fee, the kept amount on every pre-block $25 cell is **$7.28 or less**.

Do not implement Uniswap v4. Do not implement generic Uniswap v2. Do not implement this bridge.

---

## 15. Recommended Next Gate

**E. `DEPRIORITIZE`**

Not `IMPLEMENTATION_DESIGN`: the coverage gap is real, and the economics after competition are not a Gate 7 strategy.

Not `MORE_REPLAY` as the next use of this gate: 68 forward cycles and 55 closed reverse cycles in one hour already show the same auction outcome. A second hour could differ. **HYPOTHESIS:** it would differ in the number of episodes, not in the tendency of the winner to sell the surplus to the builder. That hypothesis is not required for the decision.

Not `NEW_MECHANISM_RESEARCH` on DEXTF: the realized surplus is under a dollar.

Not `CURRENT_UNIVERSE_REFINEMENT` as a way to capture this cell: Sushi, v3, and Curve do not contain the mint.

---

## 16. Limitations

- One Ethereum hour. **PROVEN** counts are for blocks 26,125,444–26,125,744 only.
- `debug_traceTransaction` is not available on this endpoint. Internal ETH to the miner was taken from `alchemy_getAssetTransfers`. A tip to an address that is not `block.miner` would be missed. The priority-fee case does not depend on that API.
- Private orderflow is **NOT_PROVABLE**.
- Ten forward quotes miss realized output by up to ~0.003 ETH because a same-transaction reserve change is earlier than the swap that was priced. The previous-block $25 cells that had no earlier `Sync` match the fill to the cent.
- The three double-lot reverse transactions were not fully sourced.
- v4 pool keys for the sub-$5 flash-loan residuals were not recovered. Their $10,000 replay is **NOT_PROVABLE**. Realized size is **PROVEN** under $5 after gas.
- About 5,377 v4 transactions without a flash loan were not priced one by one.
- The DEXTF index mint was not re-simulated at block N−1.
- Spot differs from E1.5’s flat $2,716 by less than 0.2% on these blocks. Dollar figures use the block’s own pool spot unless a section says otherwise.

---

## 17. Evidence Appendix

Method, all read-only against the existing Ethereum RPC:

- Token A and token B: `eth_getCode`, dispatcher selectors, disassembly of `0x24a29d50` and `0x41477451`, `name` / `symbol` / `decimals`.
- Hour logs in 10-block chunks: v2 `Swap`, v2 `Sync`, token B mints, token B burns, token A transfers to token B.
- Receipts and transactions for all 69 forward hashes and all 58 reverse hashes.
- `getReserves` at N−1, N, and N+1. USDC/WETH `slot0` for spot.
- Builder payment: internal transfers to `block.miner`. Gas: receipt `gasUsed` and `effectiveGasPrice`, compared with `baseFeePerGas` on the priority-fee outliers.
- Forward quote checked against realized WETH out on 67 cycles (median error 26,152 wei).
- v4/flash figures reused from the E1.5 45-transaction wealth pass, which includes native ETH. Seven receipts re-fetched for venue counts.
- DEXTF token flow taken from the E1.5 receipt decode of the two hashes, with the corrected surplus from that audit.

No production file, quoter, scanner, route table, Gate 7 constant, economics module, RPC setting, or database row was modified. No transaction was signed or broadcast.

Artifacts outside the repository (not part of the certification record): analysis scripts and JSON under `/tmp/e16` on the host that ran the replay.
