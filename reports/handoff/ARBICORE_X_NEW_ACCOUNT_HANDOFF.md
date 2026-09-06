# ArbiCore X v2 — NEW ACCOUNT ENGINEERING HANDOFF (PRIMARY)

> Self-contained handoff for a brand-new Emergent account with ZERO conversational
> history. Read this file first, then the sibling files in `reports/handoff/`.
> Labels used throughout: **[PROVEN]** verifiable from repo/tests/operator VPS
> evidence · **[INFERRED]** reasoned from code · **[PROPOSED]** recommended, not
> built · **[NOT YET PROVEN]** explicitly unproven.

## 0. Fast facts (source of truth)
- Repository: `~/projects/arbicore-x-v2`
- Branch: `takeover/limited-live-seam-cc8db95`
- HEAD (operator/VPS): `e5767d7ca85dc6812dc2bf6284307ada981fe965`
- Tracked working tree: clean. Untracked artifacts (do not delete):
  `reports/phase5-vps-authority-ad64a50/`, `reports/ARBICORE_X_CURRENT_STATE_RECONCILIATION.md`, `reports/handoff/`.
- Production commit: `bd969ee507bcf9b37311814aeae25556c951e86d` · image `arbicore-x-backend:p0-3-bd969ee`.
- Isolated cert image: `arbicore-x-backend:cert-e5767d7ca85dc6812dc2bf6284307ada981fe965` (provenance matched HEAD). **[PROVEN via operator]**

## 1. What ArbiCore X v2 is
A fail-closed, read-only-first, six-chain (Base, Ethereum, Arbitrum, Optimism,
Polygon, BNB) DEX flash-loan arbitrage searcher + executor. Operating model
(North Star): **broad parallel activation → multi-chain Opportunity Race → first
genuine qualifying edge → complete execution proof → controlled Limited Live →
production hardening → Full Live.** It must NOT become a Base-only / UniV3-only
demo. See `ARBICORE_X_DO_NOT_DRIFT.md`.

## 2. What has actually been implemented **[PROVEN from repo]**
- Six-chain RPC config seam (per-chain, fail-closed, no cross-chain leakage).
- Discovery / pool resolution / quoting / liquidity-TVL / net-economics gate for
  all six chains (Base via canonical M3.0; 62 non-Base resolver tasks).
- Backend route adapters (calldata, planner-wired): uniswap_v3, aerodrome,
  aerodrome_slipstream, sushiswap_v2, sushiswap_v3, pancakeswap_v3, camelot_v3,
  quickswap_v3. Flash adapters: aave_v3, balancer_v2, uniswap_v3, morpho_blue.
- Read-only executor-capability audit + 11-state certification model.
- Solidity V1 executor `FlashLoanReceiver` (Balancer V2 + Aave V3 flash; UniV3
  SwapRouter02 settlement) — 8/8 Foundry tests pass.

## 3. What has actually been proven **[PROVEN]**
- Six-chain RPC connectivity PASS (correct chain IDs from VPS).
- Six-chain read-only race: probe_rows=62, discoverable=56, liquidity_verified=56,
  quotable=56, candidates=15, **economically_valid=0**, execution_ready=0,
  limited_live_proven=false. All 15 candidates: `NET_ECONOMICS:negative_gross_edge_all_sizes`.
- Base M3.0: 5 real candidates scanned, 0 green (rep. UniV3 WETH/USDC ≈ −0.145%
  gross edge, failed profit buffer). No broadcast occurred.
- Solidity 8/8 tests pass. Testnet receiver deployed on Base Sepolia
  `0x99c0b64e8f24fc1aadb07daba938d9f11dcd1052`.
- See `ARBICORE_X_VERIFIED_EVIDENCE.md` for the strict evidence list.

## 4. What has NOT been proven **[NOT YET PROVEN]**
- Any economically-positive opportunity (0 valid — a real, time-dependent market
  result, NOT a defect; DO NOT lower thresholds to force green).
- Any real on-chain arbitrage execution / receipt / repayment / profit.
- Mainnet execution on any chain (only a Base **Sepolia** testnet receiver exists).
- Execution of any non-UniV3 venue (blocked on-chain — see §7).
- Fork/simulation execution proof of a green candidate.

## 5. Current Git / VPS / deployment state
- Branch `takeover/limited-live-seam-cc8db95`, HEAD `e5767d7` (operator).
- This preview container has NO Docker / anvil / operator RPC / funded signer;
  runtime numbers above come from the operator VPS. **[INFERRED for container limits]**
- Production untouched on `arbicore-x-backend:p0-3-bd969ee` (commit `bd969ee`).

## 6. Current six-chain capability (per-chain race breakdown) **[PROVEN]**
| chain | rows | discoverable | liquidity | quotable |
|---|---|---|---|---|
| Arbitrum | 15 | 14 | 14 | 14 |
| BNB | 20 | 15 | 15 | 15 |
| Ethereum | 9 | 9 | 9 | 9 |
| Optimism | 6 | 6 | 6 | 6 |
| Polygon | 12 | 12 | 12 | 12 |
| Base | canonical M3.0 real candidate scan |

## 7. Current execution architecture (the dominant boundary) **[PROVEN]**
`FlashLoanReceiver` (Base Sepolia `0x99c0b64e…1052`, non-upgradeable):
- Flash entries: Balancer V2 (`execute`) + Aave V3 (`executeAave`).
- Settlement: `userData = abi.encode(SwapHop[], profitRecipient)` where SwapHop is
  a **Uniswap V3 `exactInputSingle` leg** through a **single immutable SwapRouter02**.
- No per-hop `router` field; no non-UniV3 ABI; no generic venue dispatcher.
- Therefore it CANNOT settle Aerodrome, Slipstream, Sushi V2/V3, Pancake V3,
  Camelot V3, QuickSwap V3, or any non-UniV3 venue — even where backend
  discovery/quote/route-construction exists.
- `SUPPORTED_DEXES={"uniswap_v3"}` correctly mirrors on-chain swap capability.
  **DO NOT widen it** ahead of a deployed V2. See `ARBICORE_X_DO_NOT_DRIFT.md`.

### Known backend/on-chain discrepancy (safe-direction) **[PROVEN]**
On-chain supports Balancer V2 **and** Aave V3 flash, but backend capability
constants report **Balancer V2 only**. Backend UNDER-reports (safe), but must be
reconciled before the capability model is called authoritative. This is NOT
permission to enable execution.

## 8. Why Limited Live is NOT enabled **[PROVEN]**
`limited_live_proven=false`. Not a single Limited-Live gate chain is complete: 0
economically-valid candidates, no execution proof, no fork sim of a green
candidate, no on-chain receipt/repayment/profit verification, no admin approval.
Full gate list: `ARBICORE_X_LIMITED_LIVE_GATES.md`.

## 9. Next engineering action **[PROPOSED — see NEXT_ACTIONS]**
FIRST: reconcile backend capability to the deployed V1 ABI (incl. Aave V3) so the
planner/certification can never claim execution the receiver cannot settle.
SECOND: design/build/test a versioned **Executor V2 secure settlement dispatcher**
(V1 kept intact). THIRD: parallel discovery expansion (Curve/Solidly). Then rerun
the race; prove execution on the first genuine edge; then Limited Live. Exact
files in `ARBICORE_X_NEXT_ACTIONS.md`.

## 10. What must NEVER be changed accidentally
See `ARBICORE_X_DO_NOT_DRIFT.md`. Summary: don't weaken safety gates; don't widen
`SUPPORTED_DEXES` before V2; don't modify V1 into a generic arbitrary-call
executor; don't touch production/protected files; never `--remove-orphans`; never
invoke full-stack Compose as a cert shortcut (REACT_APP_BACKEND_URL issue); never
fabricate quotes/liquidity/opportunities/receipts.

## 11. Roadmap
Current → Limited Live: `ARBICORE_X_LIMITED_LIVE_GATES.md`.
Limited Live → Full Live: `ARBICORE_X_FULL_LIVE_GATES.md`.
Architecture detail: `ARBICORE_X_ARCHITECTURE_STATE.md`.

## 12. First message for the new account
Paste `ARBICORE_X_NEW_SESSION_PROMPT.md` as the FIRST message in the new Emergent
account.
