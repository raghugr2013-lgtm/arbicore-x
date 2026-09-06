# ArbiCore X v2 — NEXT ACTIONS (prioritized, with exact files)

> DO NOT modify these files during handoff. This is the plan for the next
> engineering session, respecting all constraints in `ARBICORE_X_DO_NOT_DRIFT.md`.

## FIRST — Reconcile backend capability to the DEPLOYED V1 ABI (no widening)
Goal: planner/certification can NEVER claim execution for a route the deployed
receiver cannot settle; reconcile the safe-direction Aave-V3 discrepancy.
Inspect / change:
- `app/backend/arbicore/scanners/flash_loan_arbitrage/executor_capability.py`
  — `SUPPORTED_DEXES` stays `{"uniswap_v3"}`; make the flash set reflect on-chain
  (Balancer V2 **and** Aave V3); ideally key capability to the deployed executor
  address/version per chain.
- `app/backend/arbicore/execution/planner.py` — ensure a route is marked
  executable only when the configured executor can settle its venue + flash.
- `app/backend/arbicore/runtime/composition.py` — execution restriction source.
- `app/backend/scripts/executor_capability_audit.py` — reconcile
  `EXECUTOR_SUPPORTED_FLASH` (add `aave_v3`); keep DEX execution = UniV3 only.
Proof: extend offline audit/regression tests; re-run the executor-capability
audit; execution_capable count must remain UniV3-only until V2 exists.

## SECOND — Executor V2 secure settlement dispatcher (V1 kept intact)
Design/build/test (NO deploy without approval). New Solidity:
- `contracts/contracts/core/ExecutorV2.sol` (per-hop `{venueId,router,…,minOut}`
  dispatch + owner-curated per-chain router allowlist; all V1 invariants).
- `contracts/contracts/core/UniswapV2Adapter.sol`
- `contracts/contracts/core/AlgebraAdapter.sol`
- `contracts/contracts/core/SlipstreamAdapter.sol`
- `contracts/contracts/core/IExecutor.sol` (V2 selectors; keep V1 stable)
- `contracts/script/Deploy.s.sol` + Foundry tests (extend the passing 8-test suite)
Reuse existing `contracts/contracts/adapters/UniswapV3Adapter.sol`. Then wire
backend encoders (`execution/adapters.py`) to the V2 `userData` schema behind the
per-executor capability map. Prove via fork simulation before any testnet deploy.

## THIRD — Parallel discovery expansion (independent of executor)
Implement genuine resolvers/quoters (fail-closed; do not mark activated before
proof):
- NEW `app/backend/arbicore/discovery/curve_resolver.py` (Curve registry + `get_dy`)
- NEW `app/backend/arbicore/discovery/solidly_resolver.py` (`poolFor` + `getAmountOut`)
Then re-run the six-chain read-only Opportunity Race over the broader surface.

## FOURTH — On first genuine positive opportunity (full proof chain)
fresh quote → liquidity → economics → flash liquidity → MEV/risk → execution
capability → fresh revalidation → fork/simulation → controlled real execution →
on-chain receipt → repayment verification → residual/profit verification.

## FIFTH — Controlled Limited Live (only after FOURTH + all gates + admin approval)
See `ARBICORE_X_LIMITED_LIVE_GATES.md`.

## SIXTH — Full Live (after sustained evidence + hardening + admin approval)
See `ARBICORE_X_FULL_LIVE_GATES.md`.

## Environment note for the new account
Preview containers may lack Docker / anvil / operator RPC / funded signer; the
six-chain race + operator cert are VPS-only. The RPC seam consumes
`PROVIDER_RPC_URLS_<CHAIN>` (economic) and `ARBICORE_RPC_URL_<CHAIN>` (discovery);
values are injected on the VPS only (template `deployment/cert/.env.example`,
real values git-ignored) — never commit real RPC URLs.
