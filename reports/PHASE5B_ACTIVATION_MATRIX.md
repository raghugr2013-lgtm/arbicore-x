# ArbiCore X v2 — Phase-5b Runtime Activation Matrix + Blocked-Cell Report

Branch `takeover/limited-live-seam-cc8db95`. Read-only, fail-closed. Signing /
broadcast / auto-execution / Limited-Live / Full-Live / withdrawals OFF. No
fabricated quotes / liquidity / RPC / adapters. No `SUPPORTED_DEXES` change.

> Environment truth: this preview container has **no Docker, no anvil, no
> operator/archive RPC, no funded signer**. Discover→quote→liquidity→economics
> below are from a **public-RPC PROXY** (real heads/quotes, NOT operator-
> authoritative). SIMULATION and EXECUTION are VPS-only gates and are reported
> `requires_vps_runtime`, never asserted here.

## 1. Runtime certification standard (never collapsed)
`DISCOVER → CONFIGURE → RPC → LIQUIDITY/STATE → LIVE QUOTE → ECONOMICS →
PROFIT/LOSS GATE → ROUTE CONSTRUCTION → SIMULATION → EXECUTION CAPABILITY →
RUNTIME CERTIFICATION`. Registry/adapter/address/RPC presence is NOT activation.

## 2. Chains
| chain | RPC (proxy) | head block proven | discover→quote→liq→econ (proxy) | operator-authoritative |
|---|---|---|---|---|
| base | public 0x2105 | yes | canonical path (m3_0_real_candidate_scan) | VPS-only |
| ethereum | public | yes (25912921) | 9/9 pools · quotes real | VPS-only |
| arbitrum | public | yes | 14/15 pools · quotes real | VPS-only |
| optimism | public | yes | 6/6 pools · quotes real | VPS-only |
| polygon | public | yes | 12/12 pools · quotes real | VPS-only |
| bnb | public | yes | 15/20 pools · quotes real | VPS-only |

Evidence: `reports/PREFLIGHT_PUBLIC_PROXY_phase5_harnessfix.json`,
`reports/VPS_RUNTIME_CERT_public_phase5_harnessfix.json`.

## 3. Executor capability audit (static, from real registries)
Evidence: `reports/EXECUTOR_CAPABILITY_AUDIT.json`
(`scripts/executor_capability_audit.py`).

- Deployed executor DEX support (on-chain FlashLoanReceiver): **uniswap_v3 swap
  hops only**.
- Deployed executor flash-loan support: **balancer_v2 borrow only**.
- DEX calldata adapters implemented: `uniswap_v3`, `aerodrome`.
- Flash-loan calldata adapters implemented: `aave_v3`, `balancer_v2`, `uniswap_v3`.
- Venue cells: 15 · discoverable 13 · quotable 13 · route_constructable 7 ·
  execution_capable **6** (uniswap_v3 on base/eth/arb/op/poly/bnb).

### Per-venue gate matrix (D=discover Q=quote R=route-construct X=execution-capable)
| chain | venue | abi | D | Q | R | X | first blocker |
|---|---|---|:--:|:--:|:--:|:--:|---|
| base | uniswap_v3 | canonical_base | ✅ | ✅ | ✅ | ✅ | runtime SIM+EXEC (VPS) |
| base | aerodrome | canonical_base | ✅ | ✅ | ✅ | ❌ | on-chain receiver = UniV3 only |
| base | aerodrome_slipstream | canonical_base | ✅ | ✅ | ❌ | ❌ | no DEX calldata adapter |
| ethereum | uniswap_v3 | univ3 | ✅ | ✅ | ✅ | ✅ | runtime SIM+EXEC (VPS) |
| ethereum | sushiswap_v2 | univ2 | ✅ | ✅ | ❌ | ❌ | no DEX calldata adapter |
| ethereum | curve_stable | curve | ❌ | ❌ | ❌ | ❌ | curve_resolver_not_implemented |
| arbitrum | uniswap_v3 | univ3 | ✅ | ✅ | ✅ | ✅ | runtime SIM+EXEC (VPS) |
| arbitrum | sushiswap_v3 | univ3 | ✅ | ✅ | ❌ | ❌ | no DEX calldata adapter |
| arbitrum | camelot_v3 | algebra | ✅ | ✅ | ❌ | ❌ | no DEX calldata adapter |
| optimism | uniswap_v3 | univ3 | ✅ | ✅ | ✅ | ✅ | runtime SIM+EXEC (VPS) |
| optimism | velodrome_v2 | solidly | ❌ | ❌ | ❌ | ❌ | solidly_resolver_not_implemented |
| polygon | uniswap_v3 | univ3 | ✅ | ✅ | ✅ | ✅ | runtime SIM+EXEC (VPS) |
| polygon | quickswap_v3 | algebra | ✅ | ✅ | ❌ | ❌ | no DEX calldata adapter |
| bnb | uniswap_v3 | univ3 | ✅ | ✅ | ✅ | ✅ | runtime SIM+EXEC (VPS) |
| bnb | pancakeswap_v3 | univ3 | ✅ | ✅ | ❌ | ❌ | no DEX calldata adapter |

## 4. Flash-loan / liquidity providers
| provider | adapter | exec-capable | chains | blocker / remediation |
|---|:--:|:--:|---|---|
| balancer_v2 | ✅ | ✅ | eth,arb,base,op,poly | runtime vault liquidity proven on VPS |
| aave_v3 | ✅ | ❌ | eth,arb,base,op,poly,bnb | receiver borrows Balancer V2 only → upgraded receiver |
| uniswap_v3 | ✅ | ❌ | eth,arb,base,op,poly | receiver borrows Balancer V2 only → upgraded receiver |
| morpho_blue | ❌ | ❌ | eth,base | no FlashLoanAdapter → implement borrow/repay calldata |

## 5. Blocked-cell report (chain → venue/provider → strategy → failed gate → reason → remediation)
- eth/arb/op/poly/base/bnb → uniswap_v3 → flash-loan arb → **SIMULATION+EXECUTION**
  → requires VPS (anvil fork + operator RPC + funded signer + Limited-Live
  approval) → run on VPS with operator config.
- base → aerodrome / aerodrome_slipstream → cross-DEX arb → **EXECUTION_CAPABILITY**
  → deployed FlashLoanReceiver encodes UniV3 swaps only (aerodrome swap adapter
  exists for calldata but the on-chain receiver cannot execute it; slipstream has
  no DEX adapter) → upgrade/redeploy receiver to support Aerodrome (+ add
  slipstream DexAdapter), then re-audit.
- arb/bnb/poly → sushiswap_v3 / pancakeswap_v3 / camelot_v3 / quickswap_v3 →
  cross-DEX arb → **ROUTE_CONSTRUCTION** → no DEX calldata adapter in
  `execution.adapters` → implement `DexAdapter` per family (UniV3-fork forks
  reuse `exactInputSingle`; Algebra uses dynamic-fee swap ABI).
- eth → sushiswap_v2 → cross-DEX arb → **ROUTE_CONSTRUCTION** → no UniV2 DexAdapter
  → implement `swapExactTokensForTokens` adapter.
- eth/op → curve_stable / velodrome_v2 → **DISCOVERY** → resolver not implemented
  → add Curve registry / Solidly `poolFor` resolver + quoter (currently
  fail-closed, honestly not discoverable — NOT dropped from the surface).
- all providers except balancer_v2 → **EXECUTION_CAPABILITY** → deployed receiver
  borrows Balancer V2 only (aave_v3/uniswap_v3 adapters exist; morpho_blue has no
  adapter) → upgraded receiver (+ morpho adapter) then re-audit.

## 6. Activation summary (honest)
- Chains RPC-reachable (proxy): 6/6. Operator-authoritative: 0 here (VPS).
- Venues discoverable+quotable: 13/15. Route-constructable: 7. **Execution-capable
  (construction level): 6 (uniswap_v3 × 6 chains).**
- Flash providers execution-capable: 1 (balancer_v2).
- Economically-valid cells (proxy race): **0** (all candidates
  `negative_gross_edge_all_sizes` at probed blocks — real, not lowered).
- **Limited-Live-eligible cells: 0.** `LIMITED_LIVE_PROVEN=false`.
- Opportunity Race searches the full activated surface (all chains/venues via
  `vps_runtime_certify`), selects the first cell passing every gate; none did.

## 7. Safety
production untouched · main untouched · protected files untouched · signing OFF ·
broadcast OFF · auto-execution OFF · Full-Live OFF · Limited-Live OFF ·
withdrawals OFF · kill switch engaged.
