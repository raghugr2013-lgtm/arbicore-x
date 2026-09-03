# ArbiCore X — TIER-1 (Base Profitability) Implementation Report

**Phase gate:** T1 kernels implemented + unit/regression tested in the Emergent workspace. No deploy, no live trading, no T2. T0 reconciled (19/19 still green). `main@43230f6` remains the architectural baseline.
**Tags:** `[FACT]` verified here · `[VPS?]` needs live RPC/VPS · `[REC]`.

## Honored global rules
Base-first; flash-loan-first; no live trading; SHADOW/PAPER preserved; no auto-promotion; **no gate lowered** ($25 Gate 7 intact); **no fabricated liquidity/quotes/profitability** (all new paths fail closed on missing data); REAL/SIMULATED provenance preserved; signing untouched; no evidence deleted; no experimental/archive merges; no unrelated product areas; no low-value UI.

## A. What was implemented (additive, DRY — reuses existing kernels)
1. **Real cached TVL / liquidity verification** — `scanners/flash_loan_arbitrage/tvl_provider.py`:
   - `OnChainReserveTVLProvider` — TVL = Σ(reserveᵢ × priceᵢ) from injected `reserves_fn`/`price_fn`; returns **None** (→ Gate 8 fail-closed) if reserves or any token price is missing (no fabrication).
   - `CachedTVLProvider` — TTL cache (hit + short miss TTL) with injectable clock; keeps failing closed on cached None.
2. **Flash-loan provider selection** — `provider_selection.py`: `select_flash_loan_provider()` picks the **cheapest feasible** provider (0-fee Balancer/Morpho → Aave 5bps → Uni tier); **feasible only if liquidity for the borrow is KNOWN and ≥ borrow** (unknown ⇒ not feasible). Added **Morpho Blue** (0 bps, Ethereum+Base) to `FLASH_LOAN_PROVIDERS`.
3. **Full canonical profit vector (§19)** — `profit_vector.py`: `build_profit_vector()` projects the single canonical `EconomicAssessment` (T0-4 source of truth) into `{gross_profit_usd, total_cost_usd, expected_net_profit_usd, worst_case_net_profit_usd, profit_margin_bps, confidence, execution_probability}`. `expected_net == EconomicAssessment.expected_profit_usd` (no second calc); worst-case applies a slippage stress multiplier. **Gate 7 semantics unchanged.**
4. **Opportunity ranking** — `ranking.py`: `score_opportunity()`/`rank_opportunities()` rank by risk-adjusted executable value (expected_net × execution_prob × confidence × freshness × liquidity, minus negative worst-case). Proven that a large apparent spread with poor execution ranks **below** a smaller high-probability opportunity (§20 contract).
5. **Optimal sizing / gas-aware economics / DEX fees / slippage / net-profit / execution probability** — reused existing `economics/size_optimizer.optimize_size` (EV-maximising ternary+grid), `economics/expected_value` (evidence-based success probability), `economics/net_profit`, and the canonical `scanners/economics.aggregate_economics`. T1 validates and unifies them; no duplicate economics introduced.

## B. Exact files changed
- New: `scanners/flash_loan_arbitrage/provider_selection.py`, `ranking.py`, `profit_vector.py`; `tests/test_t1_profitability.py`.
- Modified: `scanners/flash_loan_arbitrage/tvl_provider.py` (+CachedTVLProvider, +OnChainReserveTVLProvider), `scanners/flash_loan_arbitrage/economics.py` (+morpho_blue), `tests/test_t0_correctness.py` (env-sync test → async, no logic change).

## C. Tests / results `[FACT]`
- `tests/test_t1_profitability.py` → **7 passed** (Morpho catalog; provider selection incl. fail-closed & unsupported-chain; on-chain TVL + missing-price/reserve fail-closed; cached TVL TTL + miss caching; EV-maximising sizing; profit-vector canonical consistency; ranking §20 contract).
- Combined T0+T1 → **26 passed**. Regression (`d6_1_economics_and_gates`, `wave6a_mode_unit`, `d3_3_economics`, `provenance`) → **53 passed**. **Total 79, 0 regressions.**

## D. Performance benchmarks
N/A for T1 — all T1 additions are pure/deterministic in-process logic with negligible cost. Latency/throughput/CPU-RAM benchmarks belong to **T2 (searcher performance)**.

## E. Known limitations (explicit)
1. **Live wiring pending:** the T1 kernels (TVL providers, provider selection, profit vector, ranking) are implemented + unit-tested but **not yet wired into the runtime verifier/scanner hot path**. Wiring `OnChainReserveTVLProvider`→Gate 8, `select_flash_loan_provider`→verifier, and surfacing `profit_vector`/ranking in the opportunity payload is the next integration step. Until then Gate 8 remains fail-closed (honest).
2. **Real data sources are `[VPS?]`:** `reserves_fn`/`price_fn` and per-provider liquidity probes must be backed by a live Base RPC / price feed on the VPS. Tested here with deterministic fixtures only — no live quotes fabricated.
3. **No new DEX venues added:** UniV4/Pancake on Base deferred to avoid fake integrations; the curated real venue list is unchanged. Add only when a real quoter/pool source is available (`[REC]`).
4. **Paper/shadow of T1 economics** will be exercised once the kernels are wired to the runtime and a real Base RPC is present (VPS); not runnable end-to-end in this preview.

## F. Provenance / security
No change to provenance or signing. New paths never fabricate liquidity/quotes; missing data ⇒ None/not-feasible (fail-closed). $25 Gate 7 floor unchanged; Gate 8 fail-closed preserved.

## G. Remaining T1 work before T2
- Wire TVL provider → verifier/Gate 8; provider selection → verifier; profit vector + ranking → opportunity payload + operator reporting.
- Provide live `reserves_fn`/`price_fn` + provider-liquidity probe on the VPS.
- Exercise paper/shadow with real Base quotes.

## Checkpoint
Workspace tests green (79). Awaiting your review before proceeding to **T2 (Searcher performance)**. No deploy performed.

**STOP — phase gate. Report and wait for authorization before T2.**
