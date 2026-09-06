# ArbiCore X v2 — ARCHITECTURE STATE

Labels: **[PROVEN] [INFERRED] [PROPOSED] [NOT YET PROVEN]**

## Discovery layer **[PROVEN]**
Per-chain resolver universe (62 non-Base tasks + Base canonical M3.0) builds a
pool graph from real chain reads. Fail-closed: an un-configured chain / missing
resolver yields an empty universe, never a fabricated pool. Files:
`app/backend/arbicore/discovery/multichain_venues.py`,
`arbicore/discovery/algebra_pool_resolver.py`, Base
`arbicore/discovery/base_pool_registry.py`. **Gaps [PROVEN]:** no generic Curve
resolver, no Solidly `poolFor` resolver.

## Quote layer **[PROVEN]**
`QuoterRegistry` (`arbicore/execution/quoter.py`) provides live quotes for
UniV3 + UniV3 forks + UniV2 + Algebra via real QuoterV2/pool reads. Quoteability
≠ profitability. quotable=56/56 discoverable at last race.

## Liquidity / TVL layer **[PROVEN]**
liquidity_verified=56 from real pool state. Used as an economic input, not a
standalone activation signal.

## Economics layer **[PROVEN]**
`compute_true_net_profit` / all-in-cost net gate (gross edge − gas − slippage −
flash-loan cost) in `arbicore/scanners/`. Fail-closed. Last race: 15 candidates,
0 valid, all `negative_gross_edge_all_sizes`. Thresholds are real; DO NOT lower.

## Execution layer (backend) **[PROVEN]**
`arbicore/execution/adapters.py` (AdapterRegistry) → consumed by
`arbicore/execution/planner.py` (`swap_step`/`borrow_step`). Route construction
is genuine, but execution capability is gated by the DEPLOYED on-chain executor,
mirrored (currently) by `SUPPORTED_DEXES` in
`arbicore/scanners/flash_loan_arbitrage/executor_capability.py`.

## V1 executor boundary (on-chain, authoritative) **[PROVEN]**
`contracts/contracts/core/FlashLoanReceiver.sol` (Base Sepolia
`0x99c0b64e…1052`, non-upgradeable):
- Flash entries: Balancer V2 `execute(address[],uint256[],bytes)` + Aave V3
  `executeAave(address,uint256,bytes)`.
- Settlement schema: `userData = abi.encode(SwapHop[], profitRecipient)`;
  `SwapHop{tokenIn,tokenOut,feePpm,amountIn,amountOutMinimum,sqrtPriceLimitX96}`
  run via `UniswapV3Adapter.runHops(uniRouter, hops)` against ONE immutable
  SwapRouter02.
- Security: owner-immutable; `_authorized` re-entry window + `_pendingProvider`
  cross-provider guard; callback caller checked vs Vault/Pool; Aave
  `initiator==address(this)`; exact `amount+premium` repay/approve; per-hop
  `amountOutMinimum`; owner-only `rescue`.
- **Hard limits:** no per-hop router, no non-UniV3 ABI, no generic dispatcher, no
  upgradeability → non-UniV3 venues + UniV3 forks (different router) are NOT
  settleable. Backend Aave-V3 flash capability is under-reported vs on-chain.

## Proposed V2 executor boundary **[PROPOSED — not built]**
A NEW, still-immutable `ExecutorV2` deployed FRESH per chain (V1 kept intact):
- Keep Balancer V2 + Aave V3 flash entries.
- Generalize the hop to `{ venueId, router, tokenIn, tokenOut, amountIn, minOut,
  venueParams }` dispatched to a small set of VETTED adapter libraries
  (Uniswap V3, Uniswap V2, Algebra, Slipstream) selected by `venueId`.
- Enforce an owner-curated, per-chain ROUTER/VENUE ALLOWLIST; unknown router →
  revert.
- Preserve ALL V1 invariants: owner auth, callback auth, reentrancy protection,
  provider gating, exact flash repayment, minOut/slippage, profit-recipient
  controls, chain-specific controls, owner-only rescue, fail-closed.
- NOT an upgradeable proxy (design intentionally has no upgrade governance). NOT
  a generic arbitrary-call executor.
Candidate Solidity files: `contracts/contracts/core/ExecutorV2.sol`,
`.../UniswapV2Adapter.sol`, `.../AlgebraAdapter.sol`, `.../SlipstreamAdapter.sol`,
`.../IExecutor.sol` (V2 selectors), `contracts/script/Deploy.s.sol`, tests.

## Capability rule (must hold) **[PROPOSED]**
Backend "executable" must be DRIVEN by the deployed executor's real ABI +
allowlist (ideally keyed to the executor address/version per chain), never
asserted ahead of it.
