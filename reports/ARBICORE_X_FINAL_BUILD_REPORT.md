# ARBICORE X — FINAL BUILD REPORT
One production-ready build for a SINGLE VPS deployment. SHADOW-only; no broadcast,
no capital movement, no gate weakened. Reuse-first: the audit is the baseline.

Branch: `flashloan-live-shadow`. Verification: offline unit + focused regression
(this container has no RPC/WSS/anvil/Mongo — live steps are VPS-only, listed in §15).

---

## 1. Repository audit findings (recap, authoritative)
- 6 branches / 149 commits searched. The **only genuinely-absent capability** was
  **V3 on-chain state ingestion** (V3 WSS decode + `slot0()`/`liquidity()` bootstrap
  + `sqrtPriceX96→sqrt_p`). Everything else = built/tested; work was composition/wiring.
- Single incomplete composition point: `runtime.maybe_build_base_searcher()` built an
  empty `RouteGraph()` + `tvl_provider=None`. Now fixed by genuine wiring.
- Full audit: `reports/ARBICORE_X_REPO_AUDIT_AND_INVENTORY.md`.

## 2. Existing functionality REUSED (not rebuilt)
`PoolState`/`PoolStateCache` (V2/V3/stable + staleness), `amm_math` V3 kernels,
`RouteGraph`/cycle enumeration/`fast_filter`, `BaseSearcherRuntime` + Gate 7/Gate 8,
`BaseWssSubscriber` + `T2WssManager` (lifecycle/reconnect/telemetry), `OnChainReserveTVLProvider`
+ `CachedTVLProvider` + `make_base_price_fn`, `QuoterRegistry` (live quotes),
`EthJsonRpcProvider` (RPC), `candidate_to_canonical` bridge → existing verifier/paper/
certification/evidence, mode ladder + readiness + kill switch + broadcaster + auto-executor,
M1 `base_pool_registry`.

## 3. New functionality ADDED (only the genuinely absent)
- `arbicore/searcher/v3_state.py` (NEW):
  - `sqrtx96_to_sqrt_p` + `human_price_token1_per_token0` (raw-unit convention matching `amm_math`).
  - `decode_v3_log` — Swap/Mint/Burn/Initialize → cache log dicts (fail-closed).
  - `make_v3_state_initializer` — real `slot0()`/`liquidity()` bootstrap (injectable eth_call).
  - `make_base_v3_reserves_fn` — V3 reserves via ERC-20 `balanceOf(pool)` (NOT V2 getReserves).
  - `make_univ3_getpool_verifier` — VPS cross-check of CREATE2 addrs via factory getPool.
- `arbicore/discovery/base_pool_registry.py` (M1, prior) — canonical real addresses.

## 4. Integration / wiring changes (smallest-correct)
- `pool_cache.py`: added `PoolState.tick`; `apply_log` now handles V3 `tick`, in-range
  `liquidity_delta` (Mint/Burn), and `Initialize`; added `pools()`/`all_states()` accessors.
  (Additive — existing Sync/Swap absolute-value behavior preserved.)
- `live_base.py`: `BaseWssSubscriber` now decodes V3 first, V2 Sync fallback.
- `wss_ingest.py`: WSS `logs` subscription now includes V3 topic0 set; subscribes the
  runtime's REAL pool addresses; optional real-RPC V3 `bootstrap_v3_state()` on `start()`;
  telemetry adds `subscribed_pools` / `v3_pools_initialized` / `state_bootstrapped`.
- `runtime.py`: `maybe_build_base_searcher()` now performs the FULL composition —
  `populate_from_registry` (graph + cache skeletons from real addresses) + real fail-closed
  TVL provider when RPC + genuine price source are configured. Added `build_base_searcher_runtime`,
  `build_base_tvl_provider`, env adapters (`make_base_eth_call_from_env`,
  `make_base_price_source_from_env`, `make_base_v3_state_initializer_from_env`),
  and `BaseSearcherRuntime.pool_addresses()`.
- **No change to `server.py`**: it calls the same `maybe_build_base_searcher()` /
  `maybe_build_t2_wss_manager()` — now self-wiring. Zero new broadcast path.

## 5. V3 state architecture
`slot0()`+`liquidity()` bootstrap seeds authoritative V3 state at start → WSS `Swap`
carries the NEW `sqrtPriceX96`+`liquidity`+`tick` (authoritative per swap) → `Mint`/`Burn`
apply signed liquidity deltas only when the pool's current tick is in the position range →
`Initialize` seeds pre-first-swap price. `sqrtPriceX96/2^96` feeds `amm_math` directly
(decimals cancel across closed cycles; USD/decimals handled by the TVL layer). Stale state
(> `max_staleness_blocks`) is refused (honest None) — never a fabricated quote.

## 6. Base canonical pool architecture
`base_pool_registry` is the source of truth for the T2 path: 30 pools → 19
`deterministic_verified` UniV3 (real CREATE2 addresses, KAT-proven) + 11 `runtime_getpool`
Aerodrome (resolve on VPS, not guessed). `canonical_id` == existing synthetic id (1:1 bridge);
`build_pool_graph()` left UNCHANGED (working FlashLoan path preserved).

## 7. TVL / price architecture
`OnChainReserveTVLProvider` (reused) fed by the V3 `balanceOf` reserves fn + a genuine
USD price source, wrapped in `CachedTVLProvider`. Gate 8 = min route TVL; unknown price OR
unknown reserves → None → **fail-closed** (verified by tests). No hardcoded price:
`ARBICORE_NATIVE_PRICE_USD` is operator config; a broad multi-token feed is wired on the VPS.

## 8. Opportunity-family architecture
Convergent pipeline preserved: every family emits the canonical model through the existing
`OpportunitySource`/`OpportunityPipeline` seam (`arbicore/scanner/base.py`) into the SAME
validation→economics→simulation→gates→certification→mode→execution path. Implemented families
(arbitrage: two-pool/multi-hop/triangular/stablecoin/cross-DEX/CL) reused; MEV/liquidation
seams exist as discovery only and remain **dormant** (economic prioritization; not built).
No per-family execution/risk/certification systems were created.

## 9. Multi-chain architecture
Universal core preserved via `ChainAdapter` (Protocol) + `BaseChainAdapter` (chain_id 8453).
New V3 code is chain-agnostic (accepts pools/eth_call; no hardcoded network). Base is the
first candidate; Arbitrum/Optimism adapters are future work (seam ready, not implemented).

## 10. Readiness architecture
Existing `readiness.py` ladder unchanged; per-network progression NETWORK_CONFIGURED→…→
AUTO_READY is expressed through the existing gate checks + `live_base.base_live_shadow_audit`
(SOFTWARE/CONFIG/VALIDATION/MARKET/SAFETY). GREEN never bypasses execution authorization.

## 11. Shadow / Limited / Auto architecture
Single existing mode ladder OBSERVE→PAPER→SHADOW→LIMITED_LIVE→FULL_LIVE; flash-loan defaults
SHADOW; only LIMITED_LIVE/FULL may broadcast and both are hard-gated (`can_activate=false`).
Kill switch, capital caps, allowlists, simulation + $25 floor, evidence trail — all enforced.

## 12. Safety verification
- SHADOW invariant asserted in `scan_block` and `BaseWssSubscriber.run` (`broadcast=False`).
- Gate 7 ($25) and Gate 8 (fail-closed) untouched; TVL None → deny (tested).
- No signing/broadcast code path added. Registry addresses are deterministic (KAT-proven), never fabricated.
- Unknown price / missing pool / malformed log / stale block → None (all tested).

## 13. Tests executed and results
- `test_m1_base_pool_registry.py` (20) · `test_m2_v3_state.py` (16) · `test_m2_wss_e2e.py` (2)
  · `test_m3_tvl_composition.py` (7) · `test_m4_registry_integration.py` (7) → **52 new, all PASS**.
- Searcher-package unit regression (all tests importing `arbicore.searcher`, server-free): **71 passed**.
- Targeted domain regression (t2/gates/economics/route/readiness/discovery unit): **94 passed**
  (+2 pre-existing env errors: `test_iter11`/`test_stage1` `open('/app/frontend/.env')`).
- Import integrity: all modified modules + boot functions import cleanly; `build_base_searcher_runtime()`
  → 19 pools, `tvl_provider=None` without env (fail-closed).

## 14. Known blockers
- Pre-existing: several HTTP/Mongo integration tests require a running backend + `frontend/.env`
  (absent here) — environmental, not caused by this build.
- Gate 8 will fail-closed on non-native pairs until the VPS wires a multi-token price feed.

## 15. VPS-only validation requirements
1. Set `ARBICORE_T2_SEARCHER_ENABLED=true`, `ARBICORE_RPC_URL_BASE`, `ARBICORE_WSS_URL_BASE`,
   and a genuine multi-token USD price source (or `ARBICORE_NATIVE_PRICE_USD` at minimum).
2. Confirm `wss-status`: `running=true`, `connected=true`, `subscribed_pools=19`,
   `v3_pools_initialized>0`, `blocks_scanned` rising, `broadcast=false`.
3. Cross-check CREATE2 addresses via `make_univ3_getpool_verifier` against factory `getPool`.
4. Resolve the 11 Aerodrome `runtime_getpool` pools via operator-supplied Aerodrome factories.
5. Run anvil fork simulation + Shadow certification against the LIVE feed; confirm evidence bundle,
   unsigned/unbroadcast, no stale state, no missing price for any accepted candidate.

## 16. Deployment procedure (reuse existing runbook)
Follow `docs/ARBICORE_X_PRODUCTION_ACTIVATION_RUNBOOK.md` §8: Save-to-GitHub →
`git checkout flashloan-live-shadow && git pull` on VPS → set env (§15) →
`00_detect_env.sh` → `01_preflight.sh` → `02_backup.sh` → `05_build.sh` → `06_cutover.sh`
(additive; never `down -v`) → health `GET /api/arbicore/version` → verify `wss-status`.

## 17. Rollback procedure
Kill switch engage → return mode SHADOW → `ARBICORE_T2_SEARCHER_ENABLED=false` (disables the
new path) → rollback Docker image to previous immutable tag, or Emergent Rollback checkpoint
(never `git reset`). All changes additive; DB/evidence preserved.

## 18. Explicitly still genuinely absent (honest)
1. Multi-token USD price-feed breadth (VPS operator config; code path complete).
2. Aerodrome (11) real address resolution — VPS getPool with operator factory addresses (not guessed).
3. Live RPC/WSS/anvil validation + live Shadow certification — VPS-only.
4. FlashLoan-scanner path consolidation onto the registry — deferred (working path preserved;
   T2 path fully migrated) to avoid destabilizing before the single deploy. **CLASSIFY: CONSOLIDATE.**
5. Multi-tick V3 crossing math — single-tick conservative under-quote is the existing design.
6. Arbitrum/Optimism chain adapters — seams ready; not implemented (future networks, dormant).
7. MEV/liquidation execution families — discovery seams only; dormant by economic prioritization.
8. `scanners/dex_arbitrage/quoter.py` — 0 importers. **CLASSIFY: DEPRECATE** (not deleted — removal
   requires reference verification + tests, per rules).

## Duplication final classification
CANONICAL kept: `execution/quoter.py` (quotes), `base_pool_registry` (Base pool identity),
`pool_cache` (state), `T2WssManager`+`BaseWssSubscriber` (WSS), `OnChainReserveTVLProvider` (TVL),
mode ladder / readiness / broadcaster / auto-executor. CONSOLIDATE (later): `build_pool_graph`→registry
for the FlashLoan path. DEPRECATE (pending verification): `scanners/dex_arbitrage/quoter.py`.
KEEP (complementary, not duplicates): `providers/dex.py` quoter (provider seam),
`scanner/` (contracts) vs `scanners/` (impls), `intel/` vs `intelligence/`.
