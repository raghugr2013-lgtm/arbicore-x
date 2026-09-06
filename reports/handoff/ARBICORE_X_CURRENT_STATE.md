# ArbiCore X v2 — CURRENT STATE (concise reference)

Labels: **[PROVEN] [INFERRED] [PROPOSED] [NOT YET PROVEN]**

## Git / images **[PROVEN]**
- Branch: `takeover/limited-live-seam-cc8db95`
- HEAD (operator/VPS): `e5767d7ca85dc6812dc2bf6284307ada981fe965`
- Tracked tree: clean. Untracked: `reports/phase5-vps-authority-ad64a50/`,
  `reports/ARBICORE_X_CURRENT_STATE_RECONCILIATION.md`, `reports/handoff/`.
- Production: commit `bd969ee507bcf9b37311814aeae25556c951e86d`, image
  `arbicore-x-backend:p0-3-bd969ee`.
- Cert image: `arbicore-x-backend:cert-e5767d7ca85dc6812dc2bf6284307ada981fe965`
  (provenance matched HEAD).

## Chains (six) **[PROVEN]**
Base, Ethereum, Arbitrum, Optimism, Polygon, BNB — RPC connectivity PASS.

## Runtime race (read-only) **[PROVEN]**
probe_rows=62 · discoverable=56 · liquidity_verified=56 · quotable=56 ·
candidates=15 · economically_valid=0 · execution_ready=0 · limited_live_proven=false.
All candidates: `NET_ECONOMICS:negative_gross_edge_all_sizes` (real market result).

Per-chain: Arbitrum 15/14/14/14 · BNB 20/15/15/15 · Ethereum 9/9/9/9 ·
Optimism 6/6/6/6 · Polygon 12/12/12/12 · Base = canonical M3.0.

## Base M3.0 **[PROVEN]**
5 candidates scanned, 0 green; rep. UniV3 WETH/USDC ≈ −0.145% gross edge; no broadcast.

## Safety **[PROVEN]**
signing OFF · broadcast OFF · full-live OFF · auto-exec OFF · runtime-autostart
FALSE · scanner-autostart TRUE. Do not weaken.

## Executor **[PROVEN]**
Base Sepolia `FlashLoanReceiver` `0x99c0b64e8f24fc1aadb07daba938d9f11dcd1052`,
non-upgradeable. Flash: Balancer V2 + Aave V3. Swap: UniV3 SwapRouter02 only, via
`SwapHop[]` (no per-hop router). `SUPPORTED_DEXES={"uniswap_v3"}` matches on-chain.
Solidity 8/8 tests pass.

## Backend breadth (NOT executable beyond UniV3) **[PROVEN]**
DEX adapters: uniswap_v3, aerodrome, aerodrome_slipstream, sushiswap_v2,
sushiswap_v3, pancakeswap_v3, camelot_v3, quickswap_v3. Flash adapters: aave_v3,
balancer_v2, uniswap_v3, morpho_blue. Audit counts: 15 venue cells · discoverable
13 · quotable 13 · route_constructable 13 · execution_capable 6 (UniV3×6).

## Known discrepancy **[PROVEN]**
On-chain supports Balancer V2 + Aave V3 flash; backend constants report Balancer
V2 only (under-report, safe direction; reconcile before authoritative).

## Discovery gaps **[PROVEN]**
No generic Curve resolver; no Solidly `poolFor` resolver (both fail-closed, not
activated).

## Limited Live **[PROVEN]**
LIMITED_LIVE_PROVEN=false. See `ARBICORE_X_LIMITED_LIVE_GATES.md`.
