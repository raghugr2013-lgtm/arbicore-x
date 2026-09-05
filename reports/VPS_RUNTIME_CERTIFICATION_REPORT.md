# ArbiCore X — Read-only Runtime Certification (live RPC)

Generated from `scripts/vps_runtime_certify.py` against LIVE mainnet RPC
(operator/public, read-only). Safety: signing/broadcast/auto-exec/full-live/
withdrawals OFF, kill switch engaged. No signing, no broadcast, no execution, no
private keys. Nothing here asserts limited-live eligibility.

> IMPORTANT: this run used PUBLIC RPC endpoints from the preview container as a
> genuine proxy for the operator VPS run. Head blocks/latency/quotes are REAL.
> The authoritative operator run (archive nodes, higher rate limits) should be
> re-run on the VPS with `PROVIDER_RPC_URLS_<CHAIN>` set (see
> docs/VPS_MULTICHAIN_RUNTIME_CERTIFICATION.md).

## RPC health (this run)
| chain | head block | latency | error |
|---|---|---|---|
| base | 50918580 | 142ms | none (served by canonical path — skipped here) |
| arbitrum | 502061153 | 106ms | none |
| bnb | 120144369 | 167ms | none |
| ethereum | 25912394 | 127ms | none |
| optimism | 156513869 | 186ms | none |
| polygon | 93280990 | 142ms | none |

## Runtime state ladder (probe rows = chain×venue×pair×fee)
- probe_rows: 62 · discoverable: 56 · liquidity_verified: 56 · quotable: 49
- algebra_quote_gap: 7 · cross_venue_pairs: 11

### By ABI family [discoverable, liquidity_verified, quotable]
| family | disc | liq | quotable | verdict |
|---|---|---|---|---|
| univ3 (Uniswap V3 + Sushi V3 + Pancake V3) | 46 | 46 | **46** | QUOTABLE proven live |
| univ2 (Sushi V2) | 3 | 3 | **3** | QUOTABLE proven live |
| algebra (Camelot V3 + QuickSwap V3) | 7 | 7 | **0** | DISCOVERABLE only — no quoter adapter (`algebra_quoter_not_wired`) |

### By venue [discoverable, quotable]
uniswap_v3 [36,36] · pancakeswap_v3 [5,5] · sushiswap_v3 [5,5] · sushiswap_v2 [3,3]
· camelot_v3 [3,0] · quickswap_v3 [4,0]

## Mapping to the 65 discoverable matrix rows (chain×venue×strategy)
13 discoverable (chain,venue) cells × 5 strategies = 65. Non-Base cells (10):
- **Runtime-QUOTABLE (8 cells → 40 rows):** uniswap_v3 on arbitrum/ethereum/
  optimism/polygon/bnb, sushiswap_v3 (arbitrum), pancakeswap_v3 (bnb),
  sushiswap_v2 (ethereum). All liquidity-verified on-chain.
- **DISCOVERABLE-only (2 cells → 10 rows):** camelot_v3 (arbitrum),
  quickswap_v3 (polygon) — Algebra resolves via poolByPair + has positive
  liquidity, but NO quoter adapter yet.
- **Base (3 cells → 15 rows):** served by the canonical registry/QuoterRegistry
  (Base uniswap_v3/aerodrome/slipstream) — proven previously; not re-probed here.

## Economics / candidate readiness
- Cross-venue PRE-COST gross spreads observed (top): arbitrum USDC/USDT 1036%,
  arbitrum WETH/USDC 341% (uniswap_v3 vs sushiswap_v3); ethereum USDC/USDT 30%
  (uniswap_v3 vs sushiswap_v2). These are **illiquid-pool artifacts** (Sushi V3
  on Arbitrum / Sushi V2 stable pairs have tiny TVL → the probe notional causes
  massive price impact) and are exactly what the TVL/liquidity + slippage gate
  rejects. The plausible ones (bnb pancake-vs-uniswap 0.3–1.1%, ethereum
  uni-vs-sushiV2 0.05–0.15%) are BELOW realistic net cost (gas + flash-loan fee +
  slippage) and are not demonstrably net-positive.
- **NET economics: 0** valid (net requires the gas + flash-loan + slippage gate,
  not a raw quote). **Fork simulation: 0** here (anvil not present in this
  container — a VPS step). **Execution-ready candidate: NONE.**
- `LIMITED_LIVE_PROVEN = false` (unchanged; correct).

## Exact blockers observed
- `algebra_quoter_not_wired` (7) — Camelot/QuickSwap discoverable, not quotable.
- `pool_invalid_or_unreadable` (6) — specific (pair,fee) with no deployed pool
  (fail-closed exclusion, correct).
- Economic/simulation gates unmet for every candidate (illiquidity or sub-cost
  spread; no fork sim here).
- RPC: public endpoints (not operator archive nodes); healthy this run, but the
  authoritative certification must run on the VPS operator config.

## Recommendation (next step)
1. Re-run `scripts/vps_runtime_certify` + `scripts/vps_multichain_preflight` on
   the VPS with operator `PROVIDER_RPC_URLS_<CHAIN>` (archive/rate-limited nodes)
   to confirm these counts on the real operator surface.
2. Highest-value NEXT SEAM by evidence: an **Algebra QuoterV2 adapter**
   (Camelot/QuickSwap) — 7 discoverable+liquid pools are blocked ONLY by the
   missing quoter. This is the single change that converts genuinely-liquid
   discovered pools into quotable ones. (Solidly/Curve remain lower priority: no
   resolver AND no evidence of value yet.)
3. Wire the real NET economic gate (gas + flash-loan + slippage + TVL) into the
   multichain cross-venue path and run it read-only to see if ANY candidate is
   net-positive after cost — the true precondition for an execution proof.
4. Only after a genuine net-positive, gate-passing, fork-simulated candidate
   exists → prepare the operator-gated controlled execution proof (funded signer,
   caps, kill switch, explicit approval). Not before.
