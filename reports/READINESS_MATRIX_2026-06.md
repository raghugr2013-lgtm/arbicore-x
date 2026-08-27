# ArbiCore X — FINAL READINESS MATRIX (Atomic Flash-Loan Limited-Live scope) · 2026-06

Commit SHA: `066d641` (+ this turn's additions) · Branch `complete-Base-M1-M4-live-shadow-composition` · Baseline `6de846f` preserved as ancestor.
Scope (confirmed): SAME-CHAIN ATOMIC FLASH-LOAN ARBITRAGE ONLY. Cross-chain = OUT OF SCOPE.
Safety (verified): LIMITED_LIVE=0 · FULL_LIVE=0 · AUTOEXEC=0 · RUNTIME_AUTOSTART=0 · no signer · no RPC in preview `.env`.
Live validation deferred to VPS (option b): no six-chain RPC in preview; nothing fabricated.

Legend: GREEN=impl+wired+tested+genuine evidence · YELLOW=impl/wired/tested but proof/provider/live pending · RED=missing/out-of-scope · BLOCKED-BY-RPC=exists, needs live RPC (VPS).

| Capability | IMPLEMENTED | WIRED | TESTED (offline) | LIVE-VALIDATED | PROVEN | STATUS | BLOCKER | NEXT ACTION |
|---|---|---|---|---|---|---|---|---|
| Ethereum path | ✅ | ✅ | ✅ | ❌ | ❌ | BLOCKED-BY-RPC | no preview RPC | VPS live SHADOW validate |
| Arbitrum path | ✅ | ✅ | ✅ | ❌ | ❌ | BLOCKED-BY-RPC | no preview RPC | VPS live SHADOW validate |
| Base path | ✅ | ✅ | ✅ | ✅ (UniV3) / ⚠️ (aero) | ✅ (UniV3) | GREEN (UniV3) / YELLOW (aero) | public-RPC throttling on aero reads | dedicated Base RPC → finish Aerodrome |
| Optimism path | ✅ | ✅ | ✅ | ❌ | ❌ | BLOCKED-BY-RPC | no preview RPC | VPS live SHADOW validate |
| Polygon path | ✅ | ✅ | ✅ | ❌ | ❌ | BLOCKED-BY-RPC | no preview RPC | VPS live SHADOW validate |
| BNB path | ✅ | ✅ | ✅ | ❌ | ❌ | BLOCKED-BY-RPC | no preview RPC | VPS live SHADOW validate |
| DEX/DEX | ✅ | ✅ | ✅ | ✅ Base | ✅ Base | GREEN (Base) / BLOCKED (5) | RPC for 5 chains | VPS multi-chain validate |
| Multi-DEX route | ✅ | ✅ | ✅ | ✅ Base | ✅ Base | GREEN (Base) / BLOCKED (5) | RPC for 5 chains | VPS validate |
| Multi-hop | ✅ | ✅ | ✅ | ⚠️ Base | partial | YELLOW | broader live routes | VPS validate deeper routes |
| Triangular A→B→C→A | ✅ (multi fee-tier) | ✅ | ✅ (wide) | ⚠️ Base | partial | GREEN-offline / YELLOW-live | live cycle breadth | VPS validate cycles |
| Stablecoin (USDC/USDT/DAI) | ✅ (all 5 generic chains + Base) | ✅ | ✅ | ❌ | ❌ | YELLOW / BLOCKED-live | RPC | VPS validate stable routes |
| Fee-tier search (500/3000/10000/100) | ✅ | ✅ | ✅ | ✅ Base | ✅ Base | GREEN (Base) | — | VPS validate other chains |
| Flash-loan providers (Balancer V2, Aave V3, UniV3, Morpho) | ✅ | ✅ | ✅ | ⚠️ Balancer/Base only | partial | YELLOW | live liquidity reads per provider/chain | VPS validate vault/pool liquidity |
| Provider optimizer (cheapest-feasible) | ✅ | ✅ | ✅ (NEW 8/8) | ❌ | offline-proven | GREEN-offline / YELLOW-live | needs multi-provider live liquidity | VPS validate selection on-chain |
| Gas | ✅ (6 chains) | ✅ | ✅ | ✅ Base | ✅ Base | GREEN (Base) / BLOCKED (5) | RPC | VPS validate gas per chain |
| L1/security fee | ✅ | ✅ | ✅ | ✅ Base | ✅ Base | GREEN (Base) | — | VPS confirm on L2s |
| Slippage | ✅ | ✅ | ✅ | ✅ Base | ✅ Base | GREEN (Base) | — | VPS validate |
| Price | ✅ (M2.5 on-chain USD) | ✅ | ✅ | ✅ Base | ✅ Base | GREEN (Base) / BLOCKED (5) | RPC | VPS validate feeds |
| TVL | ✅ (on-chain reserves) | ✅ | ✅ | ✅ Base UniV3 | ✅ UniV3 | GREEN (UniV3) / YELLOW (aero) | aero reserves read (RPC) | dedicated RPC |
| Gate 7 ($35 net) | ✅ | ✅ | ✅ | ✅ Base | ✅ | GREEN | — | keep unchanged |
| Gate 8 (real TVL) | ✅ | ✅ | ✅ | ✅ Base UniV3 | ✅ UniV3 | GREEN (UniV3) / YELLOW (aero) | aero RPC | dedicated RPC |
| Gate 9 (MEV) | ✅ | ✅ | ✅ | ✅ Base | ✅ | GREEN | — | keep unchanged |
| M3 final authority | ✅ | ✅ | ✅ | ✅ Base | ✅ | GREEN | — | keep unchanged |
| Evidence / provenance | ✅ | ✅ | ✅ | ✅ Base | ✅ | GREEN | — | validate populated bundles on VPS |
| EmissionBus | ✅ | ✅ | ✅ | wiring only | wiring | GREEN (wiring) / YELLOW (populated) | live scanner run | VPS SHADOW activation |
| Opportunities UI (canonical) | ✅ | ✅ | ✅ | honest-empty | wiring | GREEN (wiring) / YELLOW (populated) | populated feed | VPS SHADOW activation |
| Cross-chain arbitrage | ✅ (discovery) | partial | ✅ | ❌ | ❌ | **RED — OUT OF SCOPE FOR ATOMIC LIMITED LIVE** | non-atomic bridge settlement | separate future phase |

## Exact remaining VPS validation checklist (read-only SHADOW; execution stays OFF)
1. **Per-chain RPC validation** — set existing `ARBICORE_RPC_URL_{ETHEREUM,ARBITRUM,BASE,OPTIMISM,POLYGON,BNB}`; confirm block number + chain_id per chain.
2. **Provider validation** — for each chain, confirm DEX factories/vaults on-chain; classify CONFIGURED→AVAILABLE→ON_CHAIN_CONFIRMED (fail-closed to UNAVAILABLE/UNKNOWN).
3. **Pool/TVL validation** — pool discovery + reserves + TVL (`onchain_reserves`); finish Base Aerodrome/Slipstream with the dedicated RPC; prune genuinely unresolved pools after factory verification.
4. **Quote validation** — live QuoterV2 quotes per chain (real gross%, fail-closed on incomplete).
5. **Flash-loan liquidity/fee validation** — Balancer V2 vault + Aave V3 + Morpho + UniV3 tier reads per chain; confirm optimizer picks cheapest feasible on real liquidity.
6. **Gas/L1 validation** — per-chain gas model + Base L1 oracle all-in cost.
7. **Gate 7/8/9 validation** — $35 net gate, genuine TVL, MEV/congestion per chain.
8. **M3 validation** — confirm DENY on non-profitable + `broadcast_sent=false`, `safe=true`.
9. **Canonical EmissionBus validation** — SHADOW-activate flash-loan scanner; confirm candidates flow into `arbicore_opportunities` with stable unique IDs, no duplicate producers.
10. **Evidence validation** — provenance + evidence hash + gate results + quote/liquidity/provider/economics provenance on emitted candidates.

## Requirements for Limited-Live certification (NOT met yet — do not enable)
- Live-validated GREEN on the target chain(s) for every row above (currently only Base UniV3 fully proven).
- Base Aerodrome/Slipstream TVL genuinely read (dedicated RPC).
- At least one full end-to-end SHADOW cycle emitting a genuine candidate through EmissionBus with complete evidence (profitable OR correctly-rejected with full provenance).
- UNSIGNED→SIGNING-READY plan reviewed (signer provisioning is a separate, gated, out-of-scope step).
- Operator sign-off + safety envelope unchanged until certification.
