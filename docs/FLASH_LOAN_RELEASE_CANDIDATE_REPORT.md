# ArbiCore X — Flash-Loan Searcher Release-Candidate Report (consolidated)

Baseline `main@43230f6`. Emergent workspace only — **no VPS deploy, no live trading**. All work additive/tested; T0/T1 safety architecture preserved.

## 1. What was already present (reused, not rebuilt)
Canonical `FlashLoanArbitrageScanner` + `RouteSearchEngine`; canonical economics kernel `aggregate_economics`/`EconomicAssessment`; `optimize_size` (EV-max sizing), `expected_value` (success probability), `net_profit`; governance mode-ladder, capital policy, kill-switch; provenance (5-tier) + evidence bundles + Ed25519 signing; certification/paper/shadow engines; Base venue list (`base_venues`); flash-loan provider catalog.

## 2. Everything added / changed (this program)
**T0 correctness (done, deployed-config rehearsed):** canonical-scanner noop readiness gate; thin_activator quarantine + canonical write-gate + PaperRunner provenance filter; OBSERVE→explicit readiness/infra fault; RPC precedence resolver + legacy alias; TVL sentinel removed + Gate 8 fail-closed; certification REAL-vs-synthetic partition; `BaseChainAdapter`; additive backfill script; live endpoints `/engine/flash-loan/readiness`, `/certification/provenance-split`.

**T1 profitability (kernels done, tested):** `OnChainReserveTVLProvider` + `CachedTVLProvider` (fail-closed); `select_flash_loan_provider` (cheapest feasible; +Morpho Blue); `build_profit_vector` (§19, single canonical source); `rank_opportunities` (risk-adjusted, §20).

**Universal architecture (new):** `chains/adapter.py` (`ChainAdapter`+`ChainCapability`), `chains/base_adapter.py`, `chains/dex_adapter.py` (`DEXAdapter`,`FlashLoanProviderAdapter` + Base impls). Base-specific data stays inside adapters.

**T2 searcher core (new, benchmarked):** `searcher/amm_math.py` (V2 exact, V3 single-tick, Curve StableSwap-Newton); `searcher/pool_cache.py` (log-synced state + block-staleness refusal); `searcher/route.py` (graph, closed-cycle enum, cheap spot fast-filter); `searcher/simulation.py` (`SimulationBackend` iface + `LocalMathSimulationBackend` + **honest `RevmForkBackend` stub that refuses to fabricate**; `two_stage_pipeline`).

## 3. Architecture (target pipeline realized as testable kernels)
DISCOVER (route graph/enum) → REAL QUOTE (local AMM math from log-synced cache) → REAL LIQUIDITY (TVL providers, fail-closed) → OPTIMAL SIZE (`optimize_size`) → ECONOMICS (`aggregate_economics` + `build_profit_vector`) → FAST FILTER (stage-1 spot) → SIMULATION (stage-2 local math now; REVM/fork = VPS backend behind the same interface) → RISK/GOVERNANCE (mode-ladder/gates unchanged) → PAPER/SHADOW → LEARNING (provenance/certification). Chain-agnostic: adding a network = new ChainAdapter + verified DEX/FL adapters + config.

## 4. Supported chains / venues / providers
- **Chains:** Base (only production-wired). `ChainAdapter` interface + `BaseChainAdapter` prove the abstraction; Arbitrum/ETH/OP/Polygon are add-an-adapter (not yet wired — no fabricated readiness; `capability().active_ready` stays False without real health).
- **Venues:** Base curated (Uniswap V3, Aerodrome + Slipstream) via `BaseAerodromeUniAdapter`. Uni V4 / Pancake V3 **not added** (await real pool/quoter source — no fake integrations).
- **Flash-loan providers:** Balancer V2 (0), Aave V3 (5bps), Uniswap V3 (tier), **Morpho Blue (0, ETH+Base)** — selection prefers cheapest *feasible* by known liquidity.

## 5. Supported flash-loan opportunity families
Infrastructure supports (via universal route/economics/sim): **cross-DEX, multi-hop/triangular, cross-pool** (closed-cycle enumeration + local math). **Stablecoin** math is present (Curve StableSwap). **Liquidation/backrun** families: **not implemented** (require protocol adapters + live oracle/mempool-equivalent feeds — VPS). Sandwich/L1-bundles: out of scope by design.

## 6. Actual test results
`python -m pytest -p no:xdist` on the relevant suite: **105 passed, 0 failures, 0 regressions** (T0 19 + T1 7 + T2 8 + regression 71: economics/gates/mode/provenance/canonical). Deterministic, offline.

## 7. Actual performance benchmarks (this pod, single core, CPython 3.11)
| Kernel | Throughput | Latency |
|---|---|---|
| V2 `amount_out` | **2.71M ops/sec** | 0.368 µs |
| V3 `amount_out` (single-tick) | **2.01M ops/sec** | 0.498 µs |
| StableSwap `amount_out` (Newton) | **389K ops/sec** | 2.57 µs |
| Route `fast_filter` (full local quote/hop) | **~357K cycles/sec** | — |
Implication: screening 100K candidate cycles ≈ **0.28 s** on one core → full-graph per-block rescans fit Base's ~2 s block time and the <340 ms opportunity window with headroom (before adding bounded concurrency across the 12 vCPU). Confirms the T2 premise with measured data.

## 8. Known limitations
1. **Runtime hot-path wiring pending:** T1/T2 kernels are unit-tested but not yet spliced into the live verifier/scanner loop or the operator opportunity payload (avoided risky refactor of the 8k-line `server.py`/verifier within scope/budget). Gate 8 stays honestly fail-closed until real TVL is wired.
2. **Live-infra backends are VPS-only:** REVM/Anvil fork sim (`RevmForkBackend` is an honest stub), WSS/log ingestion feeding `PoolStateCache`, real `reserves_fn`/`price_fn`, and provider-liquidity probes need a real Base RPC/node.
3. **Second chain not activated:** architecture proven via adapters; an actual Arbitrum adapter with verified venues is not built (needs verified data sources).
4. **Families:** liquidation/backrun infra not built (protocol/feed dependencies).

## 9. Remaining VPS-only requirements
Tier-1 private co-located Base RPC + **WSS**; REVM/Anvil binary (Dockerfile already adds Foundry/Anvil v1.7.1); real price feed; provider-liquidity probe; `SIGNING_ACTIVE_KEY_VERSION` (separate controlled task; evidence stays explicitly unsigned meanwhile).

## 10. Deployment sequence (unchanged, in `FLASH_LOAN_T0_DEPLOYMENT_REPORT.md`)
Backup → branch `t0/flash-loan-correctness` off `43230f6` with separated commits (app vs Dockerfile) → rotate PAT (SSH remote) → build/up backend → `ARBICORE_CANONICAL_STRICT_PROVENANCE=true` → verify endpoints/gates → flag-guarded rollback. T1/T2 kernels ship inert (import-only) until wired, so this remains a safe correctness-first rollout.

## 11. Rollback plan
Redeploy previous image tag; toggles `ARBICORE_CANONICAL_STRICT_PROVENANCE=false`, `ARBICORE_TVL_PROVIDER=sentinel`; new searcher modules are additive/unimported by the runtime, so reverting is dropping the files/commit. No DB restore needed unless the optional backfill `--apply` was run.

## 12. Exact recommended next step
**Wire T2 into the runtime behind a feature flag on Base only:** feed `PoolStateCache` from a real Base WSS log stream, resolve pools via `BaseAerodromeUniAdapter`, run `fast_filter → LocalMathSimulationBackend` per block, hand survivors to the existing verifier (Gate 7 $25 + Gate 8 real TVL + economics + provenance), keep mode SHADOW. Add `RevmForkBackend` (Anvil) as the stage-2b confirmation. Measure real candidate/quote/sim latency on the VPS before considering a second chain.

**STOP — release-candidate core implemented, tested (105 pass) and benchmarked. No deploy/live trading. Awaiting your direction on runtime wiring vs. next chain/family.**
