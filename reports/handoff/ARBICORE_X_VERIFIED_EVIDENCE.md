# ArbiCore X v2 — VERIFIED EVIDENCE (facts only, no assumptions)

Every line here is verifiable from the repository, the Foundry test run, or the
operator VPS runtime evidence. No inferences, no proposals.

## Git / images
- Branch `takeover/limited-live-seam-cc8db95`; HEAD `e5767d7ca85dc6812dc2bf6284307ada981fe965`.
- Production commit `bd969ee507bcf9b37311814aeae25556c951e86d`, image `arbicore-x-backend:p0-3-bd969ee`.
- Cert image `arbicore-x-backend:cert-e5767d7ca85dc6812dc2bf6284307ada981fe965`; provenance matched HEAD.

## Six-chain RPC
- Connectivity PASS for Base, Ethereum, Arbitrum, Optimism, Polygon, BNB (correct chain IDs returned from VPS).

## Read-only six-chain race (62 resolver tasks non-Base + Base M3.0)
- probe_rows = 62
- discoverable = 56
- liquidity_verified = 56
- quotable = 56
- candidates = 15
- economically_valid = 0
- execution_ready = 0
- limited_live_proven = false
- All 15 candidates rejected: `NET_ECONOMICS:negative_gross_edge_all_sizes`.

### Per-chain
- Arbitrum: 15 rows / 14 discoverable / 14 liquidity / 14 quotable
- BNB: 20 / 15 / 15 / 15
- Ethereum: 9 / 9 / 9 / 9
- Optimism: 6 / 6 / 6 / 6
- Polygon: 12 / 12 / 12 / 12
- Base: canonical M3.0 real candidate scan

## Base M3.0
- 5 canonical Base candidates scanned on real read-only market data; 0 green.
- Representative real UniV3 WETH/USDC candidate ≈ −0.145% gross edge; failed profit buffer.
- Other candidates rejected: negative economics / unavailable fresh revalidation data / incomplete route quoteability.
- No broadcast occurred.

## Safety state
- signing DISABLED · broadcast DISABLED · full live DISABLED · auto execution DISABLED · runtime autostart FALSE · scanner autostart TRUE.

## Deployed executor
- Base Sepolia `FlashLoanReceiver` at `0x99c0b64e8f24fc1aadb07daba938d9f11dcd1052`.
- Non-upgradeable. Flash providers: Balancer V2 + Aave V3. Swap settlement:
  Uniswap V3 SwapRouter02 via `UniswapV3Adapter.SwapHop[]` (no per-hop router field).
- Solidity test suite: 8 passed, 0 failed.

## Backend capability constants (as in repo)
- `SUPPORTED_DEXES = frozenset({"uniswap_v3"})`.
- Backend DEX route adapters registered: uniswap_v3, aerodrome, aerodrome_slipstream,
  sushiswap_v2, sushiswap_v3, pancakeswap_v3, camelot_v3, quickswap_v3.
- Backend flash adapters registered: aave_v3, balancer_v2, uniswap_v3, morpho_blue.
- Executor-capability audit (offline): 15 venue cells · discoverable 13 · quotable 13
  · route_constructable 13 · execution_capable 6 (uniswap_v3 × 6 chains);
  executor_supported_flash reported = balancer_v2 only.

## Known discrepancy (fact)
- On-chain receiver supports Balancer V2 AND Aave V3 flash; backend capability
  constants currently represent Balancer V2 only (safe-direction under-report).
