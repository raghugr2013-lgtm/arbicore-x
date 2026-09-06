# ArbiCore X v2 — AUTHORITATIVE CURRENT-STATE RECONCILIATION (audit only)

Generated: 2026-06 · AUDIT ONLY — no code/deploy/merge/broadcast/restart.
Local audit HEAD: `d9345da` (six-chain RPC seam). Operator/VPS session reports
HEAD `e5767d7` (ahead of local; the `reports/phase5-vps-authority-ad64a50/`
tree is a VPS-only artifact, empty in this container). Findings below are read
from the ACTUAL source tree; runtime figures are the operator's VPS numbers
(six-chain read-only race) which this container cannot re-produce (no operator
RPC / anvil / funded signer here).

Evidence: `contracts/contracts/core/FlashLoanReceiver.sol`,
`contracts/contracts/adapters/UniswapV3Adapter.sol`,
`contracts/contracts/interfaces/IExecutor.sol`,
`app/backend/arbicore/scanners/flash_loan_arbitrage/executor_capability.py`,
`app/backend/arbicore/execution/adapters.py`,
`app/backend/arbicore/runtime/multichain_readiness.py`,
`reports/EXECUTOR_CAPABILITY_AUDIT.json`.

---

## 1. COMPLETE SYSTEM STATE (reconciled)

| Layer | State | Authoritative detail |
|---|---|---|
| Discovery / pool resolution | LIVE-READABLE (VPS) | 6 chains; 62 non-Base resolver tasks + Base canonical M3.0. VPS race probe_rows=62, discoverable=56. Curve/Solidly resolvers NOT implemented (fail-closed). |
| Quoting | LIVE-READABLE (VPS) | quotable=56/56 discoverable. UniV3/forks + UniV2 + Algebra quote seams connected. |
| Liquidity/TVL | LIVE-READABLE (VPS) | liquidity_verified=56. |
| Economics (all-in-cost net gate) | WORKING, FAIL-CLOSED | candidates=15 → economically_valid=**0** (`NET_ECONOMICS: negative_gross_edge_all_sizes`). Base M3.0: 5 scanned, 0 green (rep. UniV3 WETH/USDC ≈ −0.145% gross edge). Real market result, not a bug. |
| Strategy coverage | flash-loan-arb DEX↔DEX / cross-DEX / multi-hop implemented & running; cross-chain / CEX-funding / launch = discovery/analytics only (no on-chain execution seam). |
| Flash-loan providers (backend adapters) | aave_v3, balancer_v2, uniswap_v3, morpho_blue (calldata) | `execution/adapters.py`. |
| DEX route adapters (backend) | uniswap_v3, aerodrome, aerodrome_slipstream, sushiswap_v2, sushiswap_v3, pancakeswap_v3, camelot_v3, quickswap_v3 (calldata) | `execution/adapters.py` (planner-wired). |
| **On-chain executor capability** | **UniV3 swaps via ONE immutable SwapRouter02, borrowed via Balancer V2 OR Aave V3** | `FlashLoanReceiver.sol` — see §Boundary. |
| Safety gates | signing OFF · broadcast OFF · full-live OFF · auto-exec OFF · runtime-autostart FALSE · scanner-autostart TRUE · fail-closed throughout. |
| Certification | economically_valid 0 · execution_ready 0 · limited_live_proven=FALSE. Solidity: 8 tests pass. Testnet receiver `0x99c0b64e8f24fc1aadb07daba938d9f11dcd1052` (Base Sepolia). |

### THE ON-CHAIN SETTLEMENT BOUNDARY (root architectural fact)
`FlashLoanReceiver` decodes `userData = abi.encode(SwapHop[], profitRecipient)`
where `SwapHop` is a **Uniswap V3 `exactInputSingle` leg** (`tokenIn, tokenOut,
feePpm, amountIn, amountOutMinimum, sqrtPriceLimitX96`) run through a **single
immutable `uniRouter` (SwapRouter02)**. Consequences:
- No per-hop router field → even UniV3 **forks** (Sushi V3, Pancake V3) are NOT
  settleable (different router address).
- No non-UniV3 ABI → Aerodrome, Slipstream, Algebra (Camelot/QuickSwap), UniV2
  (Sushi V2), Curve, Solidly are NOT settleable.
- Flash entries: Balancer V2 (`execute`) + Aave V3 (`executeAave`) only; no
  Morpho/UniV3-flash entry.
- Contract is **owner-immutable, non-upgradeable** (redeploy for schema change).

### RECONCILIATION DISCREPANCY (flag for fix)
On-chain settles flash via **Balancer V2 AND Aave V3**, but the backend
capability constants declare flash execution as **Balancer V2 only**
(`executor_capability_audit.EXECUTOR_SUPPORTED_FLASH={"balancer_v2"}`;
`composition` "balancer_v2 only"). Backend is NARROWER than on-chain for flash →
Aave V3 execution capability is under-reported, not over-reported (safe
direction, but inaccurate). `SUPPORTED_DEXES={"uniswap_v3"}` correctly matches
on-chain for swaps.

---

## 2. CAPABILITY CLASSIFICATION

- **A. Implemented & live-readable:** 6-chain RPC config; discovery/pool
  resolution; quoting; liquidity/TVL; net-economics gate. (56 quotable cells.)
- **B. Implemented but not activated:** Aave V3 flash on-chain path (deployed +
  tested, not surfaced by backend execution capability); Morpho Blue flash
  adapter (backend calldata only, no on-chain entry).
- **C. Discoverable/quotable only:** the non-UniV3 venue cells — aerodrome,
  aerodrome_slipstream, sushiswap_v3, pancakeswap_v3, camelot_v3, quickswap_v3,
  sushiswap_v2 (discover+quote+liquidity, no on-chain settlement).
- **D. Backend route-construction only:** all 8 backend DEX adapters build
  correct calldata + wire into `ExecutionPlanner`, but only UniV3 maps to the
  on-chain receiver. route_constructable=13, execution_capable=6 (UniV3×6).
- **E. Executable on-chain TODAY:** UniV3 `exactInputSingle` hops via the one
  configured SwapRouter02, borrowed via Balancer V2 or Aave V3 — on Base
  (testnet receiver deployed); mainnet per-chain receivers not yet deployed.
- **F. Blocked by executor architecture:** every non-UniV3 venue + UniV3 forks +
  Morpho flash + multi-router routes — blocked by the fixed single-router
  UniV3-only `SwapHop` schema and the 2-provider flash entry set.
- **G. Missing implementation:** Curve resolver/quoter; Solidly `poolFor`
  resolver/quoter; Solidity swap adapters for UniV2 / Algebra / Slipstream /
  UniV3-fork-router; a versioned executor that can settle them; cross-chain /
  CEX-funding / launch execution seams.

---

## 3. NEXT ARCHITECTURE — RECOMMENDATION: **B, a versioned Executor V2 settlement dispatcher** (fresh per-chain deploy)

- **Not A (extend existing receiver):** it is explicitly immutable / non-
  upgradeable; "extending" still means a redeploy, and bolting many venue ABIs
  onto the monolith inflates the hot-path attack surface and risks the current
  clean security proof (8/8 tests).
- **Not an upgradeable proxy/diamond:** the current model deliberately has **no
  governance/timelock/upgradeability** (owner EOA, immutables). A proxy would
  add upgrade-key governance risk the design intentionally avoids.
- **B — Executor V2 dispatcher (recommended):** a NEW, still-immutable receiver,
  deployed fresh per chain (V1 keeps running), that:
  - keeps Balancer V2 + Aave V3 flash entries (add Morpho later only if worth it),
  - generalizes `SwapHop` to `{ venueId, router, tokenIn, tokenOut, minOut,
    extra }` and dispatches each hop to a **small set of vetted adapter
    libraries** (UniV3, UniV2, Algebra, Slipstream) selected by `venueId`,
  - enforces an **owner-curated router/venue allowlist** (per chain) so only
    audited routers can be called,
  - preserves every V1 invariant (see §5).
  This makes the already-implemented backend venues genuinely settleable without
  weakening security, and versioning (V1 alongside V2) is fail-safe.

---

## 4. WHY NOT JUST WIDEN `SUPPORTED_DEXES`

`SUPPORTED_DEXES={"uniswap_v3"}` is the backend's honest mirror of the on-chain
settlement boundary. Adding venues there WITHOUT a receiver that can settle them
would let the planner construct + mark "executable" routes the deployed contract
**physically cannot run** — they would revert at broadcast (best case) or, if an
encoder mismatch slipped through, mis-settle funds (worst case). Capability must
be driven BY the deployed executor's real ABI/allowlist, not asserted ahead of
it. `SUPPORTED_DEXES` must only widen in lockstep with a deployed V2 that settles
those venues, ideally keyed to the executor address/version actually configured
per chain.

---

## 5. MINIMUM SECURE ARCHITECTURE (invariants that MUST hold in V2)

- **Owner authorization:** owner-gated entry points, owner set at construction
  (or explicit, tested transfer path); no unauthenticated entry.
- **Callback authorization:** `_authorized` re-entry window + `_pendingProvider`
  so a callback only fires inside an owner-initiated flash; direct callback
  calls revert.
- **Caller check:** callback `msg.sender` verified against the exact Vault/Pool
  wired at construction (`CallerNotVault`/`CallerNotPool`); initiator==self for Aave.
- **Flash repayment:** exact `amount+premium` repaid/approved before return;
  `InsufficientBalance` revert otherwise; no standing balances.
- **Reentrancy protection:** single-window gate (+ consider a nonReentrant guard
  on V2 entries given the larger dispatch surface).
- **Token/profit recipient controls:** residual forwarded only to an explicit
  `profitRecipient`; no implicit sweeps.
- **Venue/router allowlisting (NEW, critical for V2):** per-hop `router` MUST be
  in an owner-curated, per-chain allowlist; unknown router → revert.
- **Slippage/minOut:** per-hop `amountOutMinimum` enforced by each adapter (never
  0-defaulted at the contract).
- **Chain-specific deployment controls:** one receiver per chain with that
  chain's Vault/Pool/router allowlist baked/curated; no cross-chain reuse.
- **Emergency rescue:** owner-only `rescue`, post-mortem only, off the hot path.
- **Fail-closed:** any unknown venueId / router / empty hops / decode mismatch →
  revert; never a silent fallback.

---

## 6. DO FIRST / SECOND / THIRD

1. **FIRST (backend truth-lock, no widening):** make backend execution-capability
   a data-driven mirror of the DEPLOYED executor per chain/version (venues +
   flash providers + router allowlist keyed to the executor address). Reconcile
   the Aave-V3 flash gap. This removes the backend-vs-onchain drift without
   claiming anything new.
2. **SECOND (Executor V2 + Solidity adapters):** design/implement the versioned
   dispatcher + UniV2/Algebra/Slipstream(+UniV3-fork-router) adapter libraries
   with the §5 invariants; full Foundry test suite + fork simulation; deploy to
   testnet per chain. (Also: implement Curve/Solidly resolvers in parallel — they
   are discovery blockers, independent of the executor.)
3. **THIRD (broaden + race + prove):** point the backend calldata/planner at the
   V2 ABI behind the per-executor capability map; widen the executable surface as
   each venue is settleable; re-run the six-chain READ-ONLY Opportunity Race over
   the broader surface; on the first genuine green candidate, run full execution
   proof (fork → disarmed harness); only then controlled Limited Live.

---

## 7. PRESERVED CAPABILITY
Nothing is narrowed: all 6 chains, all discovery/quote/liquidity/economics seams,
all backend route adapters, and both flash providers remain intact. This audit
recommends ADDITIVE work (V2 alongside V1), never removal.

---

## 8. BLOCKER SEPARATION

- **Architectural:** single immutable UniV3 SwapRouter02 + UniV3-only `SwapHop`
  schema + 2-provider flash set + non-upgradeable receiver ⇒ non-UniV3 venues,
  UniV3 forks, multi-router routes and Morpho flash are unexecutable. (Dominant.)
- **Missing implementation:** Curve/Solidly resolvers+quoters; Executor V2 +
  non-UniV3 Solidity adapters; V2-aware backend encoders; cross-chain/CEX/launch
  execution seams.
- **Configuration:** real operator RPC values injected on VPS (seam ready, values
  not in Git); per-chain mainnet V2 executor addresses + router allowlists.
- **Market/economic:** all 15 candidates negative gross edge (`negative_gross_
  edge_all_sizes`); 0 economically valid — a real, time-dependent market state.
- **Certification:** no VPS runtime proof yet (needs anvil + operator RPC +
  funded signer); execution_ready 0; limited_live_proven=false.

---

## 9. NEXT-ACTION LIST — files to INSPECT/CHANGE (DO NOT change yet)

Backend:
- `app/backend/arbicore/scanners/flash_loan_arbitrage/executor_capability.py`
  — turn `SUPPORTED_DEXES` + flash set into a per-executor-version/address
  capability map; add `aave_v3` to executable flash.
- `app/backend/arbicore/execution/adapters.py` — encoders must target the V2
  `userData`/`SwapHop`-V2 schema incl. per-hop router (env-first already present).
- `app/backend/arbicore/execution/planner.py` — emit V2 userData; enforce
  router-allowlist awareness before marking route-constructable→executable.
- `app/backend/arbicore/runtime/composition.py` — execution restriction source.
- `app/backend/scripts/executor_capability_audit.py` — reconcile
  `EXECUTOR_SUPPORTED_FLASH` with the on-chain (add aave_v3).
- `app/backend/arbicore/discovery/multichain_venues.py`,
  `algebra_pool_resolver.py` + NEW `curve_resolver.py` / `solidly_resolver.py`.

Solidity (contracts/):
- `contracts/contracts/core/FlashLoanReceiver.sol` (V1 reference; DO NOT edit),
  NEW `core/ExecutorV2.sol` (dispatcher), NEW
  `adapters/{UniswapV2Adapter,AlgebraAdapter,SlipstreamAdapter}.sol`,
  `interfaces/IExecutor.sol` (V2 selectors), `adapters/UniswapV3Adapter.sol`
  (reuse), `script/Deploy.s.sol`, `contracts/tests/*` (extend suite).

---

## 10. CURRENT ARBICORE X STATUS (authoritative handoff)

> ArbiCore X v2 is a fail-closed, six-chain (Base, Ethereum, Arbitrum, Optimism,
> Polygon, BNB) read-only arbitrage searcher. RPC config, discovery, pool
> resolution, quoting, liquidity and net-economics are LIVE-READABLE on all six
> chains (VPS race: 62 probe rows, 56 quotable, 15 candidates, **0 economically
> valid** — real negative gross edge, not a defect). The backend implements 8 DEX
> route adapters + 4 flash adapters, but the **deployed on-chain executor
> (`FlashLoanReceiver`, Base Sepolia `0x99c0b64e…1052`) can settle ONLY Uniswap V3
> `exactInputSingle` hops through one immutable SwapRouter02, borrowed via
> Balancer V2 or Aave V3, and is non-upgradeable.** Therefore only UniV3 cells are
> execution-capable today; all other genuinely-implemented venues are
> discoverable/quotable/route-constructable but blocked at on-chain settlement.
> All execution is OFF (signing/broadcast/full-live/auto-exec disabled;
> limited_live_proven=false). Solidity 8/8 tests pass. **The next architectural
> move is a versioned Executor V2 settlement dispatcher with per-hop venue
> dispatch + owner-curated router allowlist (preserving every V1 security
> invariant) — NOT widening `SUPPORTED_DEXES` ahead of the on-chain boundary.**
> Order of work: (1) lock backend capability to the deployed executor's real ABI
> and reconcile the Aave-V3 gap; (2) build/test/deploy Executor V2 + non-UniV3
> Solidity adapters (and Curve/Solidly resolvers in parallel); (3) broaden the
> executable surface, re-run the read-only Opportunity Race, prove execution on
> the first genuine edge, then controlled Limited Live.

Safety confirmation: no code changed · no deploy · no merge · no broadcast · no
production restart · signing/broadcast/auto-exec/full-live OFF.
