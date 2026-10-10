# 1 Executive Decision

**EVIDENCE_PARTIAL** (generated 2026-10-08 22:16 UTC; regenerate with `/workspace/g15/run_g15.sh`).

- Base: 18.0 h analysed from the running mev-census tracker (complete 6-h segments only). BSC: 30.0 h analysed (complete ~6-h segments only).
- 48-72 h target: Base reaches 48 h of complete 6-h segments at ~2026-10-10 00:05-01:00 UTC (tracker started 2026-10-08 00:00 UTC; runs to 2026-10-12 23:59:59 UTC). BSC: backfill (newest-first, 2026-10-08 ~17:16 UTC down to 2026-10-06 12:00 UTC; skips blocks already in global-census windows) at 15.3 blocks/s, <= 113,200 blocks left -> latest ETA 2026-10-09 00:19 UTC (state/BSC_BACKFILL_DONE marks completion); forward collector continues to 2026-10-11 00:00 UTC. 48 h of complete BSC segments exist once both are joined (backfill done). Re-run /workspace/g15/run_g15.sh to extend.
- BSC rows are mostly class C: public BSC endpoints do not serve historical debug traces, so in-contract BNB payments to builders/validators cannot be observed for backfilled blocks; only a small near-real-time traced sample (keyless nodeflare quota) can reach class A.

# 2 Collection Window

| chain | UTC start | UTC end | duration (h, sum of segments) | blocks | first block | last block | segments | gaps |
|---|---|---|---|---|---|---|---|---|
| base | 2026-10-08 00:00 | 2026-10-08 17:59 | 18.00 | 32,400 | 52314127 | 52346526 | 3 | 0  |
| bsc | 2026-10-07 12:00 | 2026-10-08 18:01 | 30.01 | 240,000 | 126248296 | 126488295 | 5 | 0  |

Segments (each analysed independently: own DefiLlama price snapshot, own trace pass):

| segment | blocks | UTC | h | traced rows |
|---|---|---|---|---|
| base:b00 | 52314127–52324926 | 2026-10-08 00:00 → 2026-10-08 05:59 | 6.0 | 2684 |
| base:b01 | 52324927–52335726 | 2026-10-08 06:00 → 2026-10-08 11:59 | 6.0 | 3246 |
| base:b02 | 52335727–52346526 | 2026-10-08 12:00 → 2026-10-08 17:59 | 6.0 | 1821 |
| bsc:s04 | 126248296–126296295 | 2026-10-07 12:00 → 2026-10-07 18:00 | 6.0 | 0 |
| bsc:s05 | 126296296–126344295 | 2026-10-07 18:00 → 2026-10-08 00:00 | 6.0 | 0 |
| bsc:s06 | 126344296–126392295 | 2026-10-08 00:00 → 2026-10-08 06:00 | 6.0 | 0 |
| bsc:s07 | 126392296–126440295 | 2026-10-08 06:00 → 2026-10-08 12:00 | 6.0 | 0 |
| bsc:s08 | 126440296–126488295 | 2026-10-08 12:00 → 2026-10-08 18:01 | 6.01 | 24 |
- Timestamps are block timestamps (UTC). Base block = 2 s; BSC block ≈ 0.45 s.
- Only complete segments are included; no extrapolation to per-day figures is made anywhere in this report.

# 3 Dataset

- File: `/workspace/g15/MEV_SCOUT_BASE_BSC_WINNERS_G1_5.jsonl` — **27307 rows** (deduped by tx_hash), Base **6287**, BSC **21020**.
- Inclusion rule: A/B rows with gross kept ≥ $0.10 (includes rows whose NET after gas is ≤ 0), plus C/D rows with gross or upper-bound ≥ $1.00.
- Full population (every classified A/B/C/D cycle, any size, compact columns): `/workspace/g15/out/population_all.csv.gz` — 328753 rows.
- Ledger: `/workspace/g15/BASE_SEARCHER_CONTRACT_LEDGER_G1_5.jsonl`; identity: `/workspace/g15/out/identity_base.json`; survival: `/workspace/g15/out/survival_base.json`; per-segment pipeline outputs: `/workspace/g15/gc/<chain>/<segment>/`.

# 4 Winner Quality

Class criteria (applied in `build_g15.py::classify`):
- **A CONFIRMED_SEARCHER_KEPT**: status=1; credible atomic cycle (pipeline classes cyclic_profit / _swept / _tipped / breakeven / loss); searcher = {tx.from, tx.to}, tx.to not a known router/aggregator; all net token deltas priced by DefiLlama (no implied prices); no native value sent in; native ETH/BNB flows reconciled by debug_traceTransaction (so builder/coinbase/tip payments and hidden native legs are observed and deducted).
- **B RECONSTRUCTABLE_SEARCHER_KEPT**: as A but not traced; allowed only on Base and only when the tx has no WETH wrap/unwrap by the searcher, no inferred native leg, no unresolved V4 pool, no external payouts (so receipt logs fully describe the flows; Base has no builder market, priority fee is inside gas).
- **C GROSS_ONLY**: a cycle whose gross is priced but kept NET is not established: BSC untraced (in-contract BNB builder payments invisible), untraced native legs, payouts to non-venue/non-owner addresses (cyclic_ext_payout), native value in, or gain valued only at in-window implied prices. `searcher_kept_net_usd=null`; `kept_net_upper_bound_usd` given.
- **D UNKNOWN**: unpriced profit token, unresolved V4/PCS-Infinity legs, unknown venue, or pool-unfunded cycles without trace. `searcher_kept_net_usd=null`.
- Excluded entirely (not atomic arbitrage): mint/bridge-involved, liquidations, LP activity, external input, single-pool 'cycles', mixed deltas valued at implied prices, directional native-in swaps, router/aggregator contracts.

| chain | A (jsonl) | B (jsonl) | C (jsonl) | D (jsonl) | A (all sizes) | B (all sizes) | C (all sizes) | D (all sizes) | A/B with kept NET > 0 |
|---|---|---|---|---|---|---|---|---|---|
| base | 1418 | 4252 | 57 | 560 | 3617 | 69294 | 9894 | 29741 | 66798 |
| bnb | 1 | 0 | 12086 | 8933 | 12 | 0 | 190767 | 25428 | 3 |

# 5 Economics

All amounts are **searcher_kept_net_usd** (A/B rows only; proceeds − principal − gas(+L1) − flash fee − builder/coinbase payments; payouts to the operator/owner EOA payee set NOT subtracted). C/D rows are reported separately as upper bounds. No per-day extrapolation.

## 5.1 BASE (18.0 h)

| group | n | total kept NET | median | p75 | p90 | max | ≥$1 | ≥$5 | ≥$10 | ≥$25 | ≥$100 | ≥$1,000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all A/B rows (incl. ≤0) | 72911 | $15,923.96 | $0.00 | $0.01 | $0.03 | $1,805.05 | 749 | 248 | 147 | 74 | 22 | 4 |
| winners (kept NET > 0) | 66798 | $16,989.57 | $0.00 | $0.01 | $0.04 | $1,805.05 | 749 | 248 | 147 | 74 | 22 | 4 |
| winners excl. top-1 lumpy tx | 66797 | $15,184.52 | $0.00 | $0.01 | $0.04 | $1,670.25 | 748 | 247 | 146 | 73 | 21 | 3 |
| winners excl. top-2 lumpy tx | 66796 | $13,514.27 | $0.00 | $0.01 | $0.04 | $1,353.21 | 747 | 246 | 145 | 72 | 20 | 2 |
| winners excl. top-5 lumpy tx | 66793 | $10,574.73 | $0.00 | $0.01 | $0.04 | $373.79 | 744 | 243 | 142 | 69 | 17 | 0 |
| winners excl. e80f7fba lumpy (0xe5fe9b91, 0xeee1ff32) | 66796 | $14,210.74 | $0.00 | $0.01 | $0.04 | $1,805.05 | 747 | 246 | 145 | 72 | 20 | 2 |
| winners, VERIFIED-only operator payees | 62465 | $7,358.72 | $0.00 | $0.01 | $0.03 | $1,805.05 | 451 | 139 | 77 | 38 | 7 | 1 |
| winners, VERIFIED-only, excl. e80f lumpy | 62465 | $7,358.72 | $0.00 | $0.01 | $0.03 | $1,805.05 | 451 | 139 | 77 | 38 | 7 | 1 |
| winners, strict (no operator payouts) | 54326 | $7,260.78 | $0.00 | $0.01 | $0.03 | $1,805.05 | 444 | 138 | 76 | 37 | 7 | 1 |
| class A only (winners) | 3221 | $13,811.34 | $0.01 | $0.59 | $2.57 | $1,805.05 | 619 | 202 | 120 | 61 | 17 | 4 |
| class B only (winners) | 63577 | $3,178.24 | $0.00 | $0.01 | $0.03 | $373.79 | 130 | 46 | 27 | 13 | 5 | 0 |

Top-5 txs by kept NET: `0xc2ee42f8175ff7e814998d59974a62bd646ecd839e3fe2aed9f0f42c48ff1964` $1,805.05 (0x6cec8e95, A); `0xe5fe9b91215df11880c489707207aa2f23d679dcc28d9834edd51d37f0b9384f` $1,670.25 (0xe80f7fba, A); `0xc284007cca7a6025600600c1fdf829abefa6fff414b341fda8b20455b73b798e` $1,353.21 (0xe80f7fba, A); `0xeee1ff320233ccfc535a91fef4eb552547896168002a9aa6075730f45d93a918` $1,108.58 (0xe80f7fba, A); `0x126de9c9375c3d60bb69208b8f52dea05c3232e54bf30470cc3580bb2383bd62` $477.75 (0x2da3617d, A)

Buckets (A/B rows): <=0: 6113 ($-1,065.61) | 0-1: 66049 ($1,222.27) | 1-3: 387 ($660.08) | 3-5: 114 ($436.05) | 5-10: 101 ($687.40) | 10-25: 73 ($1,240.31) | 25-100: 52 ($2,325.61) | 100-1000: 18 ($4,480.75) | >1000: 4 ($5,937.10)

Negative/zero economics among successful A/B arbs: 6113 txs, total $-1,065.61.
Failed/no-op attempt gas (all registry searcher contracts, from per-segment searchers.csv): reverted $2,002.74, no-op $1,560.08, all-tx gas $11,688.36; NET of all searchers incl. these: $7,128.27.
C/D (not counted): 39635 rows, upper-bound NET sum $6,847.08 (positive part), gross sum $206,425.73.

By family (winners, top 12 by total):

| group | n | total kept NET | median | p75 | p90 | max | ≥$1 | ≥$5 | ≥$10 | ≥$25 | ≥$100 | ≥$1,000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| multi-hop | 7378 | $6,614.45 | $0.00 | $0.01 | $0.15 | $1,670.25 | 214 | 73 | 46 | 23 | 11 | 2 |
| DEX-DEX | 20949 | $6,042.50 | $0.00 | $0.01 | $0.05 | $1,805.05 | 347 | 116 | 65 | 32 | 5 | 1 |
| triangular | 27003 | $4,089.20 | $0.00 | $0.01 | $0.03 | $1,353.21 | 176 | 54 | 32 | 17 | 6 | 1 |
| cross-pool | 11210 | $142.49 | $0.00 | $0.00 | $0.01 | $36.36 | 10 | 4 | 3 | 1 | 0 | 0 |
| slow-dislocation(>60s) | 241 | $100.60 | $0.00 | $0.00 | $0.02 | $92.75 | 2 | 1 | 1 | 1 | 0 | 0 |
| unresolved-shape | 16 | $0.32 | $0.00 | $0.01 | $0.04 | $0.22 | 0 | 0 | 0 | 0 | 0 | 0 |
| oracle-PMM-refresh | 1 | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 | 0 | 0 | 0 | 0 | 0 | 0 |

By venue combination (winners, top 12 by total):

| group | n | total kept NET | median | p75 | p90 | max | ≥$1 | ≥$5 | ≥$10 | ≥$25 | ≥$100 | ≥$1,000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Aerodrome-Slipstream3+UniswapV3 | 2053 | $3,677.70 | $0.01 | $0.06 | $0.44 | $1,353.21 | 132 | 54 | 33 | 16 | 6 | 1 |
| Aerodrome-Slipstream+Aerodrome-V2+UniswapV3 | 179 | $2,790.97 | $0.00 | $0.01 | $0.05 | $1,670.25 | 4 | 3 | 2 | 2 | 2 | 2 |
| Aerodrome-Slipstream3+Aerodrome-V2 | 106 | $2,207.76 | $0.00 | $0.02 | $1.34 | $1,805.05 | 12 | 8 | 7 | 6 | 2 | 1 |
| Aerodrome-Slipstream+Aerodrome-Slipstream3 | 465 | $1,091.94 | $0.01 | $0.05 | $0.55 | $311.13 | 42 | 20 | 14 | 8 | 3 | 0 |
| Aerodrome-Slipstream3+PancakeV3 | 1122 | $969.93 | $0.01 | $0.05 | $0.37 | $219.90 | 68 | 23 | 14 | 8 | 1 | 0 |
| Aerodrome-Slipstream3+UniswapV3+UniswapV4 | 299 | $733.07 | $0.01 | $0.19 | $1.75 | $215.13 | 41 | 12 | 10 | 6 | 2 | 0 |
| Aerodrome-Slipstream+Aerodrome-Slipstream3+UniswapV3 | 139 | $621.09 | $0.01 | $0.06 | $0.45 | $477.75 | 11 | 6 | 3 | 3 | 1 | 0 |
| UniswapV3+UniswapV4 | 12813 | $525.91 | $0.00 | $0.01 | $0.05 | $49.96 | 67 | 13 | 3 | 1 | 0 | 0 |
| Aerodrome-Slipstream+Aerodrome-V2 | 334 | $469.67 | $0.00 | $0.01 | $0.13 | $251.93 | 17 | 8 | 5 | 3 | 1 | 0 |
| Aerodrome-V2+PancakeV3 | 458 | $452.41 | $0.00 | $0.01 | $0.02 | $373.79 | 7 | 5 | 4 | 2 | 1 | 0 |
| Aerodrome-Slipstream3+PancakeV3+UniswapV3 | 626 | $381.92 | $0.01 | $0.03 | $0.11 | $284.22 | 12 | 3 | 3 | 2 | 1 | 0 |
| Aerodrome-Slipstream+PancakeV3 | 1448 | $265.43 | $0.01 | $0.02 | $0.10 | $35.30 | 36 | 11 | 7 | 2 | 0 | 0 |

By searcher contract (winners, top 12 by total):

| group | n | total kept NET | median | p75 | p90 | max | ≥$1 | ≥$5 | ≥$10 | ≥$25 | ≥$100 | ≥$1,000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0xe80f7fba79a55f165314fee20f05d66efda10524 | 534 | $6,636.05 | $0.46 | $1.55 | $7.09 | $1,670.25 | 176 | 65 | 43 | 25 | 8 | 3 |
| 0x6cec8e95595a91d669a7c051b9c89780f9e6b886 | 372 | $2,266.25 | $0.10 | $0.52 | $2.20 | $1,805.05 | 55 | 19 | 9 | 5 | 1 | 1 |
| 0xf99881ccd8d80298e4e89da77ea3017ac072b9d1 | 116 | $1,660.45 | $1.70 | $3.88 | $13.68 | $373.79 | 72 | 25 | 13 | 5 | 5 | 0 |
| 0x4d23a3ba8a3847671382e707810a926a43d2a156 | 1269 | $841.42 | $0.03 | $0.08 | $0.19 | $261.82 | 33 | 17 | 12 | 5 | 2 | 0 |
| 0xb4216537d51576ccdc5df66c9addf7dca0176667 | 1315 | $791.38 | $0.01 | $0.05 | $0.11 | $311.13 | 32 | 14 | 10 | 6 | 1 | 0 |
| 0x2da3617d82ad665be7a085f69c8403575c15e4df | 11 | $728.04 | $1.47 | $13.17 | $215.13 | $477.75 | 7 | 4 | 3 | 2 | 2 | 0 |
| 0x14a556d2a9e1ddfdba3f42e509f0b8accd809112 | 122 | $586.69 | $1.83 | $4.85 | $11.71 | $76.40 | 79 | 30 | 14 | 4 | 0 | 0 |
| 0x4d4454cfaaa011cc3a8c3527a4d59430860c70e6 | 13167 | $297.34 | $0.00 | $0.00 | $0.01 | $68.01 | 17 | 8 | 4 | 3 | 0 | 0 |
| 0xb09084a6a1f5d9b16e67cb906ba3bf8b09b87df1 | 103 | $291.68 | $0.01 | $0.02 | $0.06 | $251.93 | 4 | 2 | 2 | 2 | 1 | 0 |
| 0x465d94b20ff3e2eb948a157f5318e3ac42c6c4ab | 73 | $259.46 | $0.15 | $0.27 | $0.60 | $236.77 | 2 | 2 | 1 | 1 | 1 | 0 |
| 0xcdd6953666a3780105b62672387e82029cdcd827 | 1547 | $242.04 | $0.02 | $0.04 | $0.09 | $29.64 | 43 | 9 | 6 | 1 | 0 | 0 |
| 0x6c4df46f2e9cb6bd856dac4960138123ba19c94b | 30 | $241.67 | $0.12 | $1.23 | $5.25 | $195.10 | 9 | 4 | 2 | 1 | 1 | 0 |

By profit bucket (winners):

| group | n | total kept NET | median | p75 | p90 | max | ≥$1 | ≥$5 | ≥$10 | ≥$25 | ≥$100 | ≥$1,000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0-1 | 66049 | $1,222.27 | $0.00 | $0.01 | $0.03 | $1.00 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1-3 | 387 | $660.08 | $1.61 | $2.09 | $2.51 | $2.98 | 387 | 0 | 0 | 0 | 0 | 0 |
| 3-5 | 114 | $436.05 | $3.74 | $4.35 | $4.72 | $4.94 | 114 | 0 | 0 | 0 | 0 | 0 |
| 5-10 | 101 | $687.40 | $6.60 | $7.58 | $8.71 | $9.79 | 101 | 101 | 0 | 0 | 0 | 0 |
| 10-25 | 73 | $1,240.31 | $16.99 | $20.62 | $23.25 | $24.86 | 73 | 73 | 73 | 0 | 0 | 0 |
| 25-100 | 52 | $2,325.61 | $40.91 | $56.76 | $70.92 | $92.75 | 52 | 52 | 52 | 52 | 0 | 0 |
| 100-1000 | 18 | $4,480.75 | $240.60 | $278.62 | $329.93 | $477.75 | 18 | 18 | 18 | 18 | 18 | 0 |
| >1000 | 4 | $5,937.10 | $1,511.73 | $1,703.95 | $1,764.61 | $1,805.05 | 4 | 4 | 4 | 4 | 4 | 4 |

## 5.2 BNB (30.0 h)

| group | n | total kept NET | median | p75 | p90 | max | ≥$1 | ≥$5 | ≥$10 | ≥$25 | ≥$100 | ≥$1,000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all A/B rows (incl. ≤0) | 12 | $0.21 | $0.00 | $0.00 | $0.00 | $0.21 | 0 | 0 | 0 | 0 | 0 | 0 |
| winners (kept NET > 0) | 3 | $0.21 | $0.00 | $0.11 | $0.17 | $0.21 | 0 | 0 | 0 | 0 | 0 | 0 |
| winners excl. top-1 lumpy tx | 2 | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 | 0 | 0 | 0 | 0 | 0 | 0 |
| winners excl. top-2 lumpy tx | 1 | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 | 0 | 0 | 0 | 0 | 0 | 0 |
| winners excl. top-5 lumpy tx | 0 | — | — | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 |
| winners excl. e80f7fba lumpy (0xe5fe9b91, 0xeee1ff32) | 3 | $0.21 | $0.00 | $0.11 | $0.17 | $0.21 | 0 | 0 | 0 | 0 | 0 | 0 |
| winners, VERIFIED-only operator payees | 3 | $0.21 | $0.00 | $0.11 | $0.17 | $0.21 | 0 | 0 | 0 | 0 | 0 | 0 |
| winners, VERIFIED-only, excl. e80f lumpy | 3 | $0.21 | $0.00 | $0.11 | $0.17 | $0.21 | 0 | 0 | 0 | 0 | 0 | 0 |
| winners, strict (no operator payouts) | 3 | $0.21 | $0.00 | $0.11 | $0.17 | $0.21 | 0 | 0 | 0 | 0 | 0 | 0 |
| class A only (winners) | 3 | $0.21 | $0.00 | $0.11 | $0.17 | $0.21 | 0 | 0 | 0 | 0 | 0 | 0 |
| class B only (winners) | 0 | — | — | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 |

Top-5 txs by kept NET: `0xa8e326a0e09dc10423760ceb58723ce19a3e2499eb8dc3976aa34737b70aa0f6` $0.21 (0xa9a5afc0, A); `0x1204d037310ae01ef29c0d792f781656eacb500e33dadb19ab891d75db1f440b` $0.00 (0x45f260ad, A); `0xccd392a0d250382a3c1a2d9fe5b6ddf7f300a20542196687b81504f92a109e34` $0.00 (0x5260f8ed, A)

Buckets (A/B rows): <=0: 9 ($0.00) | 0-1: 3 ($0.21) | 1-3: 0 ($0.00) | 3-5: 0 ($0.00) | 5-10: 0 ($0.00) | 10-25: 0 ($0.00) | 25-100: 0 ($0.00) | 100-1000: 0 ($0.00) | >1000: 0 ($0.00)

Negative/zero economics among successful A/B arbs: 9 txs, total $0.00.
Failed/no-op attempt gas (all registry searcher contracts, from per-segment searchers.csv): reverted $138.26, no-op $279.78, all-tx gas $2,399.29; NET of all searchers incl. these: $26,055.41.
C/D (not counted): 216195 rows, upper-bound NET sum $580,622.46 (positive part), gross sum $1,406,921.97.

By family (winners, top 12 by total):

| group | n | total kept NET | median | p75 | p90 | max | ≥$1 | ≥$5 | ≥$10 | ≥$25 | ≥$100 | ≥$1,000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| unresolved-shape | 3 | $0.21 | $0.00 | $0.11 | $0.17 | $0.21 | 0 | 0 | 0 | 0 | 0 | 0 |

By venue combination (winners, top 12 by total):

| group | n | total kept NET | median | p75 | p90 | max | ≥$1 | ≥$5 | ≥$10 | ≥$25 | ≥$100 | ≥$1,000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PCS-Infinity-CL+PancakeV3 | 2 | $0.21 | $0.11 | $0.16 | $0.19 | $0.21 | 0 | 0 | 0 | 0 | 0 | 0 |
| PCS-Infinity-CL+PancakeV3+UniswapV4+V2-type@0x8fdedcab | 1 | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 | 0 | 0 | 0 | 0 | 0 | 0 |

By searcher contract (winners, top 12 by total):

| group | n | total kept NET | median | p75 | p90 | max | ≥$1 | ≥$5 | ≥$10 | ≥$25 | ≥$100 | ≥$1,000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0xa9a5afc022e06f2b19ff7fcb4885f2d8c5d40ec3 | 1 | $0.21 | $0.21 | $0.21 | $0.21 | $0.21 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0x45f260ad278a96c7b6d3c9831a476c2bb6aa6d5d | 1 | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0x5260f8edb4c383cd69ceb8afc042e290c1ff490a | 1 | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 | 0 | 0 | 0 | 0 | 0 | 0 |

By profit bucket (winners):

| group | n | total kept NET | median | p75 | p90 | max | ≥$1 | ≥$5 | ≥$10 | ≥$25 | ≥$100 | ≥$1,000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0-1 | 3 | $0.21 | $0.00 | $0.11 | $0.17 | $0.21 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1-3 | 0 | — | — | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 |
| 3-5 | 0 | — | — | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 |
| 5-10 | 0 | — | — | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 |
| 10-25 | 0 | — | — | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 |
| 25-100 | 0 | — | — | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 |
| 100-1000 | 0 | — | — | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 |
| >1000 | 0 | — | — | — | — | — | 0 | 0 | 0 | 0 | 0 | 0 |

# 6 Competition

## BASE

- Distinct winning searcher contracts: **147**; top-1 / top-3 / top-5 share of kept NET (VERIFIED+INFERRED payees): **0.391 / 0.622 / 0.718**.
- top-1 / top-3 / top-5 share, excl. e80f7fba lumpy txs: 0.271 / 0.548 / 0.663 (147 contracts; top-1 `0xe80f7fba79a55f165314fee20f05d66efda10524`).
- top-1 / top-3 / top-5 share, VERIFIED-only payees: 0.308 / 0.530 / 0.650 (111 contracts; top-1 `0x6cec8e95595a91d669a7c051b9c89780f9e6b886`).
- Incumbent (definition: wins in ≥75% of the 3 segments): 72 contracts, $15,255.89 (0.898); non-incumbent $1,733.68.
- Winners in jsonl (gross ≥ $0.10): 5596; with ≥1 other successful arb on the same pools in the same block: 4283 (0.77); with ≥1 reverted tx to another known searcher contract in the same block (pool attribution unverified): 5368 (0.96); with another searcher's arb on the same pools in the previous block: 2525.
- Trigger relation: {'same_block': 5314, 'no_identifiable_trigger': 282}; shape: {'backrun': 2311, 'atomic_same_block_trigger': 3003, 'atomic_no_adjacent_trigger': 282}; median block position fraction 0.474.

Wins by searcher (top 15):

| contract | wins | kept NET | share | segments active | incumbent |
|---|---|---|---|---|---|
| `0xe80f7fba79a55f165314fee20f05d66efda10524` | 534 | $6,636.05 | 0.391 | 3/3 | yes |
| `0x6cec8e95595a91d669a7c051b9c89780f9e6b886` | 372 | $2,266.25 | 0.133 | 3/3 | yes |
| `0xf99881ccd8d80298e4e89da77ea3017ac072b9d1` | 116 | $1,660.45 | 0.098 | 3/3 | yes |
| `0x4d23a3ba8a3847671382e707810a926a43d2a156` | 1269 | $841.42 | 0.050 | 3/3 | yes |
| `0xb4216537d51576ccdc5df66c9addf7dca0176667` | 1315 | $791.38 | 0.047 | 3/3 | yes |
| `0x2da3617d82ad665be7a085f69c8403575c15e4df` | 11 | $728.04 | 0.043 | 2/3 | no |
| `0x14a556d2a9e1ddfdba3f42e509f0b8accd809112` | 122 | $586.69 | 0.035 | 3/3 | yes |
| `0x4d4454cfaaa011cc3a8c3527a4d59430860c70e6` | 13167 | $297.34 | 0.018 | 3/3 | yes |
| `0xb09084a6a1f5d9b16e67cb906ba3bf8b09b87df1` | 103 | $291.68 | 0.017 | 3/3 | yes |
| `0x465d94b20ff3e2eb948a157f5318e3ac42c6c4ab` | 73 | $259.46 | 0.015 | 1/3 | no |
| `0xcdd6953666a3780105b62672387e82029cdcd827` | 1547 | $242.04 | 0.014 | 3/3 | yes |
| `0x6c4df46f2e9cb6bd856dac4960138123ba19c94b` | 30 | $241.67 | 0.014 | 2/3 | no |
| `0x50f7b42c2ad00ab86ed83f830d6f10bc87e5302c` | 667 | $185.45 | 0.011 | 3/3 | yes |
| `0x86631c20314a54e6409c9fc61406f6a86780e4cd` | 6 | $183.34 | 0.011 | 1/3 | no |
| `0x9ece562ccf9b9f5b83f44cd50285a9658b55d096` | 822 | $175.14 | 0.010 | 3/3 | yes |

## BNB

- Distinct winning searcher contracts: **3**; top-1 / top-3 / top-5 share of kept NET (VERIFIED+INFERRED payees): **0.990 / 1.000 / 1.000**.
- top-1 / top-3 / top-5 share, excl. e80f7fba lumpy txs: 0.990 / 1.000 / 1.000 (3 contracts; top-1 `0xa9a5afc022e06f2b19ff7fcb4885f2d8c5d40ec3`).
- top-1 / top-3 / top-5 share, VERIFIED-only payees: 0.990 / 1.000 / 1.000 (3 contracts; top-1 `0xa9a5afc022e06f2b19ff7fcb4885f2d8c5d40ec3`).
- Incumbent (definition: wins in ≥75% of the 5 segments): 0 contracts, $0.00 (0.000); non-incumbent $0.21.
- Winners in jsonl (gross ≥ $0.10): 1; with ≥1 other successful arb on the same pools in the same block: 1 (1.00); with ≥1 reverted tx to another known searcher contract in the same block (pool attribution unverified): 1 (1.00); with another searcher's arb on the same pools in the previous block: 1.
- Trigger relation: {'next_block': 1}; shape: {'atomic_no_adjacent_trigger': 1}; median block position fraction 0.097.

Wins by searcher (top 15):

| contract | wins | kept NET | share | segments active | incumbent |
|---|---|---|---|---|---|
| `0xa9a5afc022e06f2b19ff7fcb4885f2d8c5d40ec3` | 1 | $0.21 | 0.990 | 1/5 | no |
| `0x45f260ad278a96c7b6d3c9831a476c2bb6aa6d5d` | 1 | $0.00 | 0.007 | 1/5 | no |
| `0x5260f8edb4c383cd69ceb8afc042e290c1ff490a` | 1 | $0.00 | 0.003 | 1/5 | no |

BSC block validators (header `miner`) of jsonl rows, top 8: `0x7b501c7944185130dd4ad73293e8aa84effdcee7` 956 (0.05), `0xb4647b856cb9c3856d559c885bed8b43e0846a47` 943 (0.04), `0x460a252b4feefa821d3351731220627d7b7d1f3d` 926 (0.04), `0x75b851a27d7101438f45fce31816501193239a83` 918 (0.04), `0xf8b99643fafc79d9404de68e48c4d49a3936f787` 917 (0.04), `0x8a239732871adc8829ea2f47e94087c5fbad47b6` 913 (0.04), `0x4e5acf9684652bea56f2f01b7101a225ee33d23f` 912 (0.04), `0x9bb56c2b4dbe5a06d79911c9899b6f817696acfc` 911 (0.04)
- Traced BSC rows (A): 1; with native payments to non-venue addresses (builder/validator/other): 0; payees: . Builder identities are NOT labelled (no on-chain label source used).
- Near-real-time BSC tracer: 273 traced, 53 errors/quota-skips; forward collector stats: {'queued': 26646, 'ok': 287, 'stale': 0, 'err': 38, 'not_traced_budget': 26295, 'quota_pauses': 16}.
- Candidate selection for tracing is a ranking by major-token (WBNB/USDT/USDC/BUSD/BTCB/ETH) delta of the searcher set, one trace per 10.5 s, paused 15 min on quota (403). The traced sample is therefore biased toward larger candidates.

# 7 Base Survival Ledger

Ledger covers 109 Base contracts with ≥1 A/B winner (kept NET > 0); all their txs in the window: individual rows for every reverted tx and every tx with swap/flash/LP logs; successful txs without such logs (no-op bail-outs, admin, sweeps) are present only as per-block aggregates (count, gas, priority fee) because the collector does not retain their hashes.

| item | USD |
|---|---|
| W_kept | $16,951.22 |
| W_strict | $5,823.18 |
| operator_payouts_in_wins | $11,128.04 |
| L_loss | $-171.54 |
| gas_reverted | $1,978.33 |
| gas_nonlogged_noop_admin | $993.34 |
| gas_other_nonwin | $1,926.16 |

- `s_high` = (W_kept + L_loss - gas_reverted) / W_kept
- `s_central` = (W_kept + L_loss - gas_reverted - gas_nonlogged_noop_admin - gas_other_nonwin) / W_kept
- `s_low` = (W_strict + L_loss - gas_reverted - gas_nonlogged_noop_admin - gas_other_nonwin) / W_kept
- `W_kept` = sum of searcher_kept_net_usd (A/B rows, >0); operator/owner-EOA payouts are NOT subtracted (counted as kept); winners' own gas+L1 already deducted
- `W_strict` = same rows, operator/owner payouts NOT counted as kept (treated as if lost) - conservative bound
- `L_loss` = sum of kept NET of A/B rows with NET<=0 (negative)
- `gas_other_nonwin` = gas of successful logged txs to the contract that are not A/B arbs (C/D arbs, excluded classes, unclassified swaps)
- `clip` = reported raw and clipped to [0,1]

Survival by operator-payee attribution (same contract set, same cost pools; s_low always uses strict NET = no payouts counted):

| variant | winners | W_kept | W_strict | payouts VERIFIED in W | payouts INFERRED in W | L_loss | s_low | s_central | s_high |
|---|---|---|---|---|---|---|---|---|---|
| VERIFIED_ONLY | 45884 | $7,321.17 | $7,089.61 | $231.56 | $0.00 | $-1,507.10 | 0.093 | 0.125 | 0.524 |
| VERIFIED_PLUS_INFERRED | 50185 | $16,951.22 | $5,823.18 | $231.56 | $10,896.48 | $-171.54 | 0.044 | 0.701 | 0.873 |
| VERIFIED_ONLY_excl_e80f_lumpy | 45884 | $7,321.17 | $7,089.61 | $231.56 | $0.00 | $-1,290.90 | 0.123 | 0.155 | 0.553 |
| VERIFIED_PLUS_INFERRED_excl_e80f_lumpy | 50183 | $14,172.38 | $6,039.38 | $231.56 | $7,901.45 | $-171.54 | 0.068 | 0.642 | 0.848 |

**Headline (VERIFIED-only payees, conservative): s_low = 0.093, s_central = 0.125, s_high = 0.524.**  **VERIFIED+INFERRED payees: s_low = 0.044, s_central = 0.701, s_high = 0.873.**

**Change vs the previous estimates (0.051 / 0.406 / 0.749, global census, 16.9 h over windows w1/w2/w3/wb):**
- Definitions differ. Previously the central s used strict arb-attributable NET (operator-EOA payouts *not* counted as kept), s_low additionally charged the contracts' non-arb gas ($1,142), and s_up added the operator-EOA payouts ($1,101). Here, per the G1.5 rule "do NOT subtract profit distributions to the operator EOA as costs", operator payouts are counted as kept in W and in s_central/s_high; s_central here charges all non-win gas (reverted + non-logged + other), i.e. it is closer to the previous s_low cost basis but with payouts added back.
- The jump to 0.044 / 0.701 / 0.873 comes from reclassifying $11,128.04 of in-tx payouts as kept, of which only $231.56 goes to VERIFIED operator payees (payee is itself a sender EOA of the contract) and $10,896.48 to INFERRED payees (an EOA that receives in >=90% of that contract's payout txs). 0xe80f7fba alone accounts for most of the INFERRED amount (its two fixed EOA payees 0x743be0db… / 0x432bdb9d… receive ~75%/25% of every profit as native ETH; neither has sent a tx to the contract in the window, so the operator link is not VERIFIED).
- With VERIFIED-only attribution (closest analogue to the previous central treatment) s = 0.093 / 0.125 / 0.524: payouts to INFERRED payees are treated as not kept, so e80f7fba's wins become losses of their own gas and move from W to L. Excluding the two lumpy e80f7fba txs (VERIFIED+INFERRED) gives 0.642 central.
- The window also differs (2026-10-08 Base segments only vs the earlier four census windows), and the contract set is re-derived; the numbers are therefore not directly comparable and no daily extrapolation is made. Use VERIFIED-only as the decision basis unless the INFERRED payees are confirmed to be the operator's wallets.

Legacy single-row figures (VERIFIED+INFERRED, s_low with signed strict NET): s_low = 0.044, s_central = 0.701, s_high = 0.873 (raw: 0.044 / 0.701 / 0.873).
- Non-logged successful txs (no swap/flash/LP logs) are charged as cost in s_central/s_low; they include no-op bail-outs, but may also include admin/withdraw txs; their hashes are not retained (aggregate per block).
- Operator/owner payouts (in-tx transfers of profit to the contract's sender EOAs [VERIFIED] or to a fixed EOA payee set receiving >=90% of that contract's payouts [INFERRED]): counted as kept (not a cost) in W_kept per the task rule; W_strict (used by s_low) does not count them — this is the main swing item together with non-logged gas.
- Coverage: only contracts with ≥1 A/B winner; reverted txs sent by their EOAs to OTHER addresses are not included.

Per-contract (top 10 by W_kept):

| contract | W_kept | L_loss | reverted gas | non-logged gas | other gas | s_low | s_central | s_high | EOAs |
|---|---|---|---|---|---|---|---|---|---|
| `0xe80f7fba79a55f165314fee20f05d66efda10524` | $6,636.05 | $-0.72 | $265.14 | $0.00 | $44.62 | 0.000 | 0.953 | 0.960 | 4 |
| `0x6cec8e95595a91d669a7c051b9c89780f9e6b886` | $2,266.25 | $-0.62 | $20.90 | $1.97 | $5.38 | 0.987 | 0.987 | 0.991 | 460 |
| `0xf99881ccd8d80298e4e89da77ea3017ac072b9d1` | $1,660.45 | $-32.91 | $0.00 | $433.19 | $76.29 | 0.000 | 0.673 | 0.980 | 119 |
| `0x4d23a3ba8a3847671382e707810a926a43d2a156` | $841.42 | $-0.92 | $11.96 | $54.80 | $1.88 | 0.917 | 0.917 | 0.985 | 19 |
| `0xb4216537d51576ccdc5df66c9addf7dca0176667` | $791.38 | $-0.23 | $2.02 | $0.00 | $0.00 | 0.997 | 0.997 | 0.997 | 87 |
| `0x2da3617d82ad665be7a085f69c8403575c15e4df` | $728.04 | $0.00 | $0.95 | $0.00 | $0.28 | 0.000 | 0.998 | 0.999 | 26 |
| `0x14a556d2a9e1ddfdba3f42e509f0b8accd809112` | $586.69 | $-2.53 | $13.21 | $0.01 | $8.71 | 0.958 | 0.958 | 0.973 | 94 |
| `0x4d4454cfaaa011cc3a8c3527a4d59430860c70e6` | $297.34 | $-0.34 | $1.23 | $86.48 | $15.96 | 0.650 | 0.650 | 0.995 | 96 |
| `0xb09084a6a1f5d9b16e67cb906ba3bf8b09b87df1` | $291.68 | $0.00 | $0.00 | $0.05 | $7.74 | 0.973 | 0.973 | 1.000 | 1 |
| `0x465d94b20ff3e2eb948a157f5318e3ac42c6c4ab` | $259.46 | $-0.86 | $2.54 | $0.03 | $3.11 | 0.975 | 0.975 | 0.987 | 4 |

Searcher identity (Base): contracts grouped when the same EOA sent txs to both (VERIFIED co-use); identical runtime bytecode listed separately (INFERRED same author). No explorer/off-chain labels used; deployer lookup not available (Blockscout behind Cloudflare challenge, Basescan needs API key).

- Ledger contracts: 109; contracts in multi-contract shared-EOA groups: 48; groups: 18.
- Contracts sharing identical runtime bytecode with another ledger contract: 6.

# 8 Data Limitations

- RPC: Base blocks/receipts from base.drpc.org / base-rpc.publicnode.com / mainnet.base.org (mev-census collector, read-only reuse). Base traces: debug_traceTransaction (callTracer) on base.drpc.org (free tier) with rpc.nodeflare.app fallback; trace selection = |prelim value| ranking capped at 1500 per 6-h segment; untraced rows can only reach class B (or C if they have native legs).
- BSC blocks/receipts: bsc-dataseed*.bnbchain.org / defibit / ninicoin / publicnode / meowrpc / blxrbdn / blockrazor / 48club public endpoints (modest rate: ≤20 rps backfill, ≤8 rps forward). BSC traces: only rpc.nodeflare.app keyless, state retained <~100 blocks, 1 req/10 s and ~20 heavy calls per quota period → tiny sample.
- Chain blind spots: reverted txs carry no logs, so competitor reverts are attributed to pools only when traced (here: counted per block for known searcher contracts, UNVERIFIED pool overlap). Private orderflow / bundles that never landed are invisible. Base Flashblock (200 ms) membership is not observable; only block index position is reported. BSC builder identity is not labelled.
- Collector format: Base successful txs without swap/flash/LP logs are kept only as per-block aggregates (count, gas, priority fee) — no per-tx hashes for no-op/admin/sweep txs.
- Prices: DefiLlama historical snapshot per segment (timestamp = segment midpoint, searchWidth 6 h) for tokens; native ETH/BNB hourly (coingecko id via DefiLlama chart) for gas; WETH/WBNB-denominated deltas valued at the segment snapshot. Tokens without a DefiLlama price → class C (implied price) or D (unpriced).
- Operator-payee attribution: VERIFIED = payee is a sender EOA of the contract (on-chain co-use); INFERRED = fixed EOA payee (no code) present in >=90% of that contract's payout txs, not coinbase/fee vault (Base only). Survival is reported under both (section 7); INFERRED payees could be revenue-share/fee wallets rather than the operator.
- VERIFIED: tx status, gasUsed, effectiveGasPrice, l1Fee (Base), token transfer deltas from receipts, traced native flows (A rows). INFERRED: USD values (price snapshots), operator-payee payee rule, trigger tx (heuristic), family labels, incumbent definition. UNKNOWN: kept NET for C/D rows; builder payments on untraced BSC rows.
- Searcher set = {tx.from, tx.to}; profits forwarded inside the tx to other addresses are treated as payouts (kept if the payee is in the operator/owner payee set; Base: other payees -> C; BSC: non-operator payees treated as builder/validator payments = cost).
- Flash-loan principal is excluded by construction (borrow and repay cancel in the searcher-set deltas); flash fees are inside the deltas (reported separately for information, not subtracted twice).

# 9 G1.5 Handoff

- Per-row replay inputs present: chain/chain_id, block, tx_index, tx_hash, searcher_contract, operator_eoa, arbitrage_method_selector, ordered legs (venue, pool, token_in, token_out, raw in/out amounts), tokens (address/symbol/decimals), trade_size_input (raw + human), gross/gas/kept economics, trigger tx + trigger block + tx-index gap, same-block competitors.
- Pre-state for replay: state at block-1 plus all txs with index < tx_index in the same block (the trigger, when identified, is one of them). Rows with timing.trigger_relation = next_block / k_blocks_later had the opportunity visible at the end of block-1 (or earlier: route_state_age_s).
- A/B/C/D/E test mapping: (A unavailable economically) – replay the winner calldata/route at pre-state with ArbiCore's cost model; (B not discovered) – check whether ArbiCore's pool/token universe contains every leg pool; (C discovered but too slow) – compare ArbiCore discovery timestamps with block timestamp; with ~379 s median discovery-to-decision latency vs 0 s same-block triggers, rows with route_state_age_s < 379 are unreachable by construction; (D/E) need ArbiCore-side logs, which are out of scope here.
- BASE verdict: **SUFFICIENT_FOR_REPLAY (partial window)** — 18.0 h analysed, A/B winners in jsonl 5596 (A 1405), with kept NET >= $1: 749; winners with route_state_age_s < 379 s (unreachable at ArbiCore's median discovery-to-decision latency): 5586/5596 (1.00).
- BNB verdict: **PARTIAL: replay possible on the traced A rows; untraced rows (class C) need a trace-capable BSC archive RPC for kept NET** — 30.0 h analysed, A/B winners in jsonl 1 (A 1), with kept NET >= $1: 0; winners with route_state_age_s < 379 s (unreachable at ArbiCore's median discovery-to-decision latency): 1/1 (1.00).
- BSC builder-payment vs WBNB-unwrap check on traced cycles: n=22, crosstab {'paid=True,wrap=True': 20, 'paid=True,wrap=False': 0, 'paid=False,wrap=True': 2, 'paid=False,wrap=False': 0}, rule_supported=False (B eligibility for untraced BSC rows only if supported; currently NOT applied).
- Multi-day re-run: Base 48 h of complete segments at ~2026-10-10 00:05-01:00 UTC, 72 h at ~2026-10-11 00:05-01:00 UTC; BSC 48 h once the backfill completes (see section 1 ETA). `/workspace/g15/run_g15.sh` regenerates every artifact and this report (completed segments are skipped).
