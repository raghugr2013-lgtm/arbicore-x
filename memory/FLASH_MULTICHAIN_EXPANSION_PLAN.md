# Flash-Loan-Only Multi-Chain / Multi-Strategy Expansion — REUSE INVENTORY (pre-architecture)

Status: REPORT ONLY. No new architecture/code written yet (per instruction).
Invariants (unchanged, enforced): SHADOW / read-only / `confirm=False` / no signing / no
broadcast / M3 fail-closed. Phase 1 requires NO pre-funded inventory (flash-loan atomic only).
Do NOT lower the net-profit threshold: it is `ARBICORE_MIN_NET_PROFIT_USD`
(`execution/pre_broadcast.py:95`, prod-set to $35). Reuse it as-is per chain.

Latest FE checkpoint for the isolated validator build: `6c907e43791cb4d4563eebb91e571b819849d111`
(backend still `f36d7c9`; FE-only refactor since).

--------------------------------------------------------------------------------
## A. Reuse map — existing components ⇒ the 14 planned items
Legend: ♻️ REUSE as-is · ➕ EXTEND (small, chain/strategy params) · 🆕 NEW thin layer

| # | Planned item | Existing component(s) to reuse | Action |
|---|---|---|---|
| — | **Canonical opportunity model** | `models/canonical.py::CanonicalOpportunity` (already chain-agnostic: `chain`, `route`, `spread_pct`, `capital_required_usd`, `expected_profit_usd`, `source_data_quality`), `models/enums.py::OpportunityType` (has FLASH_LOAN_ARBITRAGE, CROSS_CHAIN_ARBITRAGE), `DataProvenance` | ➕ add enum values (TRIANGULAR/STABLE/MULTI_HOP/LST_LRT/LIQUIDATION/COLLATERAL_DEBT as *subtypes* or a `strategy` field) — no schema break |
| 1 | Canonical flash-loan opp model | `scanners/flash_loan_arbitrage/profit_vector.py`, `sources.py`, `shadow_route.py` | ♻️/➕ generalize `route_pools` to carry `chain_id` |
| 2 | Flash-provider optimizer | `scanners/flash_loan_arbitrage/provider_selection.py::select_flash_loan_provider` (already chain-aware: `chain` arg, fail-closed `no_provider_supports_chain:{chain}`), `economics.py::FLASH_LOAN_PROVIDERS` (balancer_v2=0bps, aave_v3=5bps, uniswap_v3 tiers) + `provider_fee_bps` | ♻️ reuse; ➕ add per-chain provider liquidity entries |
| 3 | Chain-aware gas / L1/L2 optimizer | `searcher/base_all_in_cost.py` (L2 gas + Base L1 data-fee via GasPriceOracle, per-tx ceiling, fail-closed), `runtime/composition.py` congestion source (`eth_feeHistory.gasUsedRatio`) | ➕ parametrize by chain (Base/OP-stack L1 fee vs Arbitrum `NodeInterface`/`ArbGasInfo` vs L1 mainnet) behind a `ChainGasModel` seam |
| 4 | Generic DEX arb (Base/Arb/Eth) | `searcher/{v3_state.py, amm_math.py, aero_resolver.py, route.py, pool_cache.py, price_feed.py}`, `discovery/base_venues.py` (venue+token registry, pool graph, nominal fees, TVL provider) | ➕ per-chain venue/token registries via `chains/` adapters |
| 5 | Triangular | `searcher/route.py` (route graph) + `amm_math.py` | ➕ add 3-leg cycle enumerator on the existing pool graph |
| 6 | Stablecoin | `discovery/base_venues.py` token registry (USDC/USDbC/DAI...), `amm_math.py` | ➕ stable-pair filter + curve/stable-AMM math variant |
| 7 | Multi-hop | `searcher/route.py` route search, `flash_loan_arbitrage/route_search.py` | ➕ raise hop bound with per-hop slippage/TVL gate (reuse `tvl_provider.py`) |
| 8 | LST/LRT | token registry (cbETH/wstETH/weETH/rETH already resolved case-insensitively), `v3_state.py` | ➕ LST oracle/redemption-rate provider (read-only) |
| 9 | Atomic liquidation | flash-loan borrow path (item 2) + `economics/net_profit.py` | 🆕 lending-market reader (Aave/Comp health-factor) — read-only; still atomic, no inventory |
| 10 | Atomic collateral/debt swap | same borrow+repay atomic spine | 🆕 position-migration route builder (read-only) |
| 11 | Optimism/Polygon/BNB | `chains/adapter.py` (`ChainAdapter` Protocol, `ChainCapability`), `chains/base_adapter.py` (template), `providers/registry.py` (RPC/provider circuit-breaker) | ➕ add `{op,polygon,bnb}_adapter.py` implementing the Protocol |
| 12 | Avalanche/Gnosis | same `chains/` seam | ➕ two more adapters |
| 13 | Unified EV ranker | `economics/expected_value.py`, `flash_loan_arbitrage/ranking.py`, `intelligence/confidence_v2.py`, `intelligence/roi_probability.py` | ♻️/➕ feed multi-chain candidates into one EV ranker keyed by all-in net |
| 14 | Outcome-learning foundation | `learning/{outcomes.py, calibration.py, route_success.py, ledger.py, weights.py}`, `learning/concrete/`, `intel/scorer.py` | ♻️ already a learning spine; ➕ record chain/strategy dimensions |

## B. Cross-cutting spines to reuse UNCHANGED (do not fork)
- **Provider registry / resilience:** `providers/registry.py` (`ProviderRegistry`, `CircuitBreaker`, health, `call()`), `providers/bootstrap.py` — reuse for every chain's RPC/DEX/flash/gas providers.
- **Chain abstraction seam:** `chains/adapter.py` (`ChainAdapter`, `ChainCapability`, `DEXAdapter`, `FlashLoanProviderAdapter`, `CatalogFlashLoanAdapter`) — the multi-chain scaffolding ALREADY EXISTS; only concrete per-chain adapters are new.
- **All-in economics:** `economics/{net_profit.py, size_optimizer.py, opportunity_decision.py, quote_provider.py, expected_value.py}` — reuse the net/EV/sizing math; gas model is the only chain-specific extension.
- **M3 safety spine (do NOT modify):** `execution/pre_broadcast.py` (final gates + `ARBICORE_MIN_NET_PROFIT_USD`), broadcaster ladder (`confirm=False`), `safety/{kill_switch,approval,capital,config,audit}.py`, `postvalidation/review.py`, `validation/operations.py`, `certification/`. All new strategies terminate at this same read-only gate.
- **Runtime/congestion:** `runtime/composition.py` congestion + freshness/fail-closed source pattern.
- **Intelligence/learning:** `intelligence/{confidence_v2,roi_probability,scoring}.py`, `learning/*` — reuse for ranking + outcome learning.
- **Scripts:** `scripts/m3_0_spread_widener_watch.py` (Base watch, `worth_m3_validation`), `m3_0_real_candidate_scan.py`, `m3_0_vps_validate.py` (confirm=False) — the multi-chain watchers should mirror these.

## C. Genuinely NEW (thin) work only
1. Per-chain concrete adapters implementing existing `ChainAdapter`/`DEXAdapter`/`FlashLoanProviderAdapter` Protocols (Arb, Eth, OP, Polygon, BNB, Avax, Gnosis) — data/config, not new architecture.
2. `ChainGasModel` seam so item-3 gas math dispatches Base(OP-stack)/Arbitrum/L1 correctly.
3. Strategy route-builders that emit the SAME `CanonicalOpportunity` (triangular, stable, multi-hop, LST, liquidation, collateral/debt) — all atomic, flash-funded, no inventory.
4. Read-only lending/LST state readers for items 8–10.
5. `strategy` + `chain_id` dimensions on the canonical model + learning ledger (additive).

## D. Sequencing (incremental, each stays SHADOW/read-only)
Item 1 → 2 → 3 (Base first, reuse `base_all_in_cost`) → 4 (Base generic DEX) →
then chains 11/12 via adapters → strategies 5–10 → 13 unified ranker → 14 learning.
Each increment: emit CanonicalOpportunity → all-in economics → M3 read-only gate → watcher →
`worth_m3_validation=true` → `m3_0_vps_validate confirm=False`. Threshold stays $35 per chain.

## E. What is NOT reusable / needs care
- `base_all_in_cost.py` L1 fee is Base(OP-stack)-specific → must branch for Arbitrum/L1 (item 3).
- `discovery/base_venues.py` is Base-only (venues/tokens/TVL sentinel) → needs sibling per-chain registries; do NOT surface its `tvl_usd=0.0` sentinel as real depth (see data-truth audit).
- Legacy `src/pages/*` frontend + any per-chain UI is OUT OF SCOPE for Phase 1 (backend detection only).
