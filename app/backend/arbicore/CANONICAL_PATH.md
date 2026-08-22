# ArbiCore X — Canonical Production Path (FROZEN)

This is the ONE authoritative runtime path. Anything not listed as **CANONICAL**
is KEEP-FROZEN / DEPRECATED / NON-AUTHORITATIVE and must not become active in
production without an explicit, approved change.

## Canonical pipeline
```
Opportunity Discovery      → OpportunityEngine (economics/opportunity_engine.py)
  ↓ Fresh live quotes       → execution/quoter.py + execution/adapters.py
  ↓ Economic calculation    → OpportunityEngine economics (gas + fees + impact + EV)
  ↓ Opportunity scoring     → OpportunityEngine / opportunity_decision.py
  ↓ Risk / policy           → execution/capital_policy.py + mode ladder + kill-switch
  ↓ Route construction      → execution/calldata.py (Balancer V2 flash + UniV3 SwapHop[])
  ↓ Calldata generation     → execution/calldata.py (entrypoint execute(address[],uint256[],bytes))
  ↓ Atomic simulation       → execution/atomic_executor_sim.py (eth_call / Anvil fork)
  ↓ Execution eligibility   → execution/pipeline.py (OpportunityPipeline.evaluate)
  ↓ Autonomous execution    → execution/auto_executor.py (AutoExecutor) — policy-gated, mode-gated
  ↓ Tx verification         → execution/broadcast.py + post-trade
  ↓ P&L / reconciliation    → paper/outcomes.py, learning/ledger.py
  ↓ Evidence / learning     → calibration + adaptive weights
  ↓ Continuous discovery    → loops back to OpportunityEngine
```

## Canonical executor interface (SINGLE SOURCE OF TRUTH)
`execution/executor_interface.py` — the deployed FlashLoanReceiver exposes
`VAULT()` / `ROUTER()` / `owner()` getters and entrypoint
`execute(address[],uint256[],bytes)` with `userData=abi.encode(SwapHop[],profitRecipient)`.
It is Balancer V2 + Uniswap V3; there is **no aavePool()**. The operator wizard,
fork validation and atomic sim all read this module. Do NOT re-declare selectors.

## Active discovery plane
- **CANONICAL / ACTIVE:** `ContinuousScanner` → `OpportunityEngine` (server.py `_CONTINUOUS_SCANNER`).
- **CANONICAL / ACTIVE (policy-gated):** `AutoExecutor` — drains discovered
  opportunities through `OpportunityPipeline`; NEVER promotes mode; NEVER
  broadcasts unless the strategy mode is LIMITED_LIVE/FULL_LIVE (pipeline-enforced).

## NON-authoritative / frozen (must not silently activate)
| Component | Status | Guard |
|---|---|---|
| `scanners/wave1b` ShadowScannerAdapter (dex/flash) | KEEP-FROZEN (dormant harness) | never autostart; operator POST /start only |
| `runtime/composition.py` real family scanners (DEX/Flash/CEX/Funding/Launch/CrossChain) | DEPRECATED-until-wired | gated behind `ARBICORE_RUNTIME_AUTOSTART` (unset = OFF) |
| `scanners/live/*` (Live/CexDex/DexDex) | NON-AUTHORITATIVE | conditional; not part of canonical path |
| `execution/aerodrome_settlement.py` | DEPRECATED (not a live head) | not wired into canonical calldata |
| Legacy Aave-Sepolia executor verification | REMOVED | replaced by `executor_interface.py` (Balancer+UniV3) |

## Mode ladder (operator authorization layer)
`SHADOW` (discover/quote/score/simulate/observe/learn — no live) →
`PAPER` (full decision pipeline + simulated execution + reconciliation + learning) →
`LIMITED_LIVE` (autonomous live within strict caps) →
`FULL_LIVE / FULL_AUTOMATION` (autonomous within hard operator policy).
Only the operator promotes modes. AutoExecutor never self-promotes and never
broadcasts below LIMITED_LIVE.
