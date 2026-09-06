# ArbiCore X v2 — Phase-5c Broad Opportunity-Surface Activation Report

Branch `takeover/limited-live-seam-cc8db95`. Read-only, fail-closed. Signing /
broadcast / auto-execution / Limited-Live / Full-Live / withdrawals OFF. No
fabricated quotes/liquidity/RPC/adapters. `SUPPORTED_DEXES` unchanged (execution
capability NOT widened — no fabrication). Evidence:
`reports/EXECUTOR_CAPABILITY_AUDIT.json`, `reports/VPS_RUNTIME_CERT_public_phase5_harnessfix.json`.

> Environment truth: no Docker / anvil / operator RPC / funded signer here.
> Discover→quote→liquidity→economics = public-RPC PROXY (real heads/quotes, NOT
> operator-authoritative). SIMULATION + EXECUTION + operator numbers are VPS-only
> (`requires_runtime`), never asserted here.

## CHAINS
| chain | configured | RPC-verified (proxy) | operator-authoritative | runtime-certified |
|---|:--:|:--:|:--:|:--:|
| base | ✅ | ✅ 0x2105 | ❌ VPS | ❌ |
| ethereum | ✅ | ✅ blk 25912921 | ❌ VPS | ❌ |
| arbitrum | ✅ | ✅ | ❌ VPS | ❌ |
| optimism | ✅ | ✅ | ❌ VPS | ❌ |
| polygon | ✅ | ✅ | ❌ VPS | ❌ |
| bnb | ✅ | ✅ | ❌ VPS | ❌ |

Blocker for operator-authoritative/runtime-certified on ALL six: no operator RPC
(`PROVIDER_RPC_URLS_<CHAIN>`) + no VPS in this container. Remediation: run the
cert on the VPS with per-chain operator RPC (chains are independent — Base is NOT
a prerequisite).

## VENUES (15 cells) — Phase-5c
| metric | 5b | **5c** |
|---|:--:|:--:|
| implemented | 15 | 15 |
| discoverable | 13 | 13 |
| quotable | 13 | 13 |
| route-constructable | 7 | **13** |
| execution-capable | 6 | 6 |
| simulatable / runtime-certified | 0 (VPS) | 0 (VPS) |

Route-construction advanced 7→13 via REAL calldata adapters wired into
`ExecutionPlanner`: Sushi V2 (UniV2), Sushi V3 / Pancake V3 (UniV3-fork),
Camelot V3 / QuickSwap V3 (Algebra), Aerodrome Slipstream (CL/tickSpacing).
Execution-capable stays 6 (uniswap_v3 × 6 chains) — the deployed on-chain
FlashLoanReceiver executes UniV3 swaps only; adding venues to `SUPPORTED_DEXES`
would fabricate capability, so it was NOT done.

## STRATEGIES
| strategy | implemented | runtime-capable | execution-capable |
|---|:--:|:--:|:--:|
| flash-loan arbitrage (DEX-to-DEX, cross-DEX, multi-hop, triangular) | ✅ | proxy discover→quote→econ | UniV3+Balancer V2 route only |
| cross-chain | ✅ (discovery) | discovery/quote | ❌ execution seam not proven |
| CEX/funding arbitrage | ✅ (discovery/analytics) | discovery only | ❌ no on-chain executor path |
| launch arbitrage | ✅ (discovery) | discovery only | ❌ execution seam not proven |
None removed or narrowed; each classified honestly. Execution-capable is limited
to the flash-loan-arb route the deployed receiver supports.

## FLASH-LOAN / LIQUIDITY PROVIDERS
| provider | implemented | adapter (calldata) | on-chain verified | execution-capable |
|---|:--:|:--:|:--:|:--:|
| balancer_v2 | ✅ | ✅ | VPS | ✅ |
| aave_v3 | ✅ | ✅ | VPS | ❌ receiver=Balancer V2 only |
| uniswap_v3 (flash) | ✅ | ✅ | VPS | ❌ receiver=Balancer V2 only |
| morpho_blue | ✅ | ✅ (NEW) | VPS | ❌ receiver=Balancer V2 only |
Morpho Blue flash adapter added (0-fee `flashLoan(address,uint256,bytes)`,
env-configured singleton, fail-closed). Execution still gated by the deployed
receiver (Balancer V2 borrow only).

## ECONOMICS (public-RPC PROXY race)
- candidates scanned: 7 · economically valid: **0** · rejected: 7
- exact rejection reason: `NET_ECONOMICS: negative_gross_edge_all_sizes` (real,
  thresholds NOT lowered) · 5 pools `pool_invalid_or_unreadable` (fail-closed)

## OPPORTUNITY RACE (broad, read-only)
- chains searched: 6 (base canonical + eth/arb/op/poly/bnb) · venues searched:
  UniV3 + forks + UniV2 + Algebra · providers: balancer_v2 · candidates found: 7
  · best candidate: none passed all gates · any candidate passed: **NO**
- LIMITED_LIVE_PROVEN=false. Not Base-only, not UniV3-only.

## CERTIFICATION STATE MODEL (never collapsed)
`IMPLEMENTED · CONFIGURED · RPC_VERIFIED · STATE_VERIFIED · QUOTABLE ·
ECONOMICALLY_VALID · ROUTE_CONSTRUCTABLE · SIMULATABLE · EXECUTION_CAPABLE ·
RUNTIME_CERTIFIED · LIMITED_LIVE_ELIGIBLE`. Offline-provable here: IMPLEMENTED,
QUOTABLE, ROUTE_CONSTRUCTABLE, EXECUTION_CAPABLE. Runtime-only (VPS):
CONFIGURED, RPC_VERIFIED, STATE_VERIFIED, ECONOMICALLY_VALID, SIMULATABLE,
RUNTIME_CERTIFIED, LIMITED_LIVE_ELIGIBLE — reported `requires_runtime`, per cell
in the audit JSON `venues[].states`.

## BLOCKED CELLS (chain → venue/provider → strategy → failed gate → reason → remediation)
- all 6 chains → uniswap_v3 → flash-loan arb → **SIMULATION+EXECUTION** →
  requires VPS (anvil + operator RPC + funded signer + Limited-Live approval) →
  run cert on VPS with operator config.
- base → aerodrome / aerodrome_slipstream → cross-DEX arb → **EXECUTION_CAPABILITY**
  → route-constructable (adapter added) but deployed receiver executes UniV3 only
  → upgrade/redeploy FlashLoanReceiver to execute these venues, then re-audit.
- arb/bnb/poly → sushiswap_v3 / pancakeswap_v3 / camelot_v3 / quickswap_v3 →
  cross-DEX arb → **EXECUTION_CAPABILITY** (route now constructable) → same
  receiver upgrade + verify env router addresses live.
- eth → sushiswap_v2 → cross-DEX arb → **EXECUTION_CAPABILITY** (route now
  constructable) → receiver upgrade + verify router.
- eth/op → curve_stable / velodrome_v2 → **DISCOVERY** → Curve/Solidly resolver
  not implemented (fail-closed, preserved not dropped) → add Curve registry +
  Solidly `poolFor` resolver/quoter, verify live.
- aave_v3 / uniswap_v3 / morpho_blue → any → **EXECUTION_CAPABILITY** → receiver
  borrows Balancer V2 only → upgraded receiver.

## SAFETY
production untouched · main untouched · protected files untouched · signing OFF ·
broadcast OFF · auto-execution OFF · Full-Live OFF · Limited-Live OFF ·
withdrawals OFF · no fabricated data · no thresholds lowered · no
`SUPPORTED_DEXES` widening.
