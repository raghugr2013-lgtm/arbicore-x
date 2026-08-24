# ArbiCore X — PRD / Working Memory

## Problem statement (continuation project)
Continue an existing production arbitrage engine. Move Base flash-loan searcher
from SHADOW/OBSERVE → Limited Live → Controlled Auto, evidence-gated, WITHOUT
bypassing safety gates, fabricating data, weakening verification, or enabling
unrestricted capital. Work in milestones; each needs runtime evidence; never
auto-enable the next risk level.

## Architecture (observed)
- FastAPI backend `app/backend/server.py` (huge) + `arbicore/` package; React frontend.
- Live quoting: `arbicore/execution/quoter.py` QuoterRegistry (UniV3 QuoterV2 eth_call,
  quotes by token+fee — no pool address needed).
- Searcher (SHADOW): `arbicore/searcher/{runtime,route,pool_cache,amm_math,live_base,wss_ingest}.py`.
- Flash-loan scanner: `arbicore/scanners/flash_loan_arbitrage/*`; Gates 7/8/9 in filter.py.
- Pool identity today: `arbicore/discovery/base_venues.py::build_pool_graph()` = SYNTHETIC ids.

## Core invariants (MUST preserve)
SHADOW broadcast=False; Gate7 $25 floor; Gate8 fail-closed on TVL<=0/None; REAL-only
provenance; LIMITED_LIVE/FULL_AUTOMATION hard-gated RED; no signing/broadcast in SHADOW.

## Milestones
- M1 Canonical Base pool registry + real addresses — **DONE (PASS)**
- M2 V3 state (slot0/liquidity bootstrap + WSS Swap/Mint/Burn/Initialize + sqrtX96 conv) — **DONE (PASS)**
- M3 Real TVL/price wired into T2 (OnChainReserveTVLProvider + V3 balanceOf reserves + price fn) — **DONE (PASS)**
- M4 Registry integration into T2 composition (graph+cache from real addrs; empty-graph/tvl=None blocker eliminated) — **DONE (PASS)**
- Base searcher composition COMPLETE (registry→V3 state→WSS→cache→routes→quotes→TVL→economics→sim→gates→cert→mode→exec) — **DONE**
- M5 Limited Live (hard risk limits) — infra REUSED/ready; operator-gated (NOT enabled)
- M6 Controlled Auto Mode — infra REUSED/ready; operator-gated (NOT enabled)

## Final build (2026-06)
- NEW: arbicore/searcher/v3_state.py (sqrtX96 conv, V3 decode, slot0/liquidity bootstrap,
  V3 balanceOf reserves, getPool verifier). Extended pool_cache (tick + delta + Initialize +
  accessors), live_base (V3 decode in subscriber), wss_ingest (V3 topics + real pool subs +
  bootstrap + telemetry), runtime (full registry-driven composition + env adapters).
- server.py UNCHANGED (self-wiring via maybe_build_base_searcher/maybe_build_t2_wss_manager).
- Tests: 52 new (M1-M4 + e2e), all PASS; 71 searcher-package unit regression PASS; no regression.
- Report: reports/ARBICORE_X_FINAL_BUILD_REPORT.md. Deploy/rollback via existing runbook.
- Genuinely absent (VPS/operator): multi-token price feed breadth, Aerodrome getPool resolution,
  live RPC/WSS/anvil + live Shadow cert. Dormant: Arbitrum/OP adapters, MEV/liquidation exec.
- Duplication: CONSOLIDATE build_pool_graph→registry (deferred); DEPRECATE dex_arbitrage/quoter.py (0 importers, not deleted).

## Backlog / next (VPS)
- Deploy ONCE per runbook; validate live (§15 of final report). Return to Emergent only on a real defect.

## Bugfix (2026-06): flash-loan candidates stuck in discovery (A->B blocker)
- ROOT CAUSE: DiscoveryCandidate.expires_at hardcoded hint_observed_at+60s; DiscoveryQueue.claim_batch
  filters expires_at>now; per-tick discover+upsert latency > 60s -> claim always returned [] ->
  verifier never ran -> ~4600 candidates stuck verified_outcome=None. (TTL index also broken: float vs BSON Date.)
- FIX (minimal, 1 file): arbicore/models/discovery.py -> configurable ARBICORE_DISCOVERY_CANDIDATE_TTL_S
  (default 900s, fail-safe). No gate/economics/mode/execution change.
- Verifier path confirmed SEPARATE from searcher/runtime.py stablecoin patch; ARBICORE_NATIVE_PRICE_USD
  not on this path. Verification runs in OBSERVE (gated only by is_enabled, not detection_only).
- Tests: tests/test_flashloan_candidate_progression.py (7, real Mongo queue+tick). testing_agent iteration_1:
  38/38 PASS, acceptance A-I met, no broadcast, retest_needed=false.
- Existing replay harness reused: tests/_pending_scanner_activation/test_d6_1_verifier_scanner_sources.py,
  tests/test_d6_1_economics_and_gates.py, tests/test_d6_1_route_search.py.
- NEXT (per user): M2 real-live-quote -> real TVL -> net profit -> Gate 7/8/9 -> verified evidence -> shadow/paper.
  Limited live NOT enabled.

## M1 delivered (2026-06)
- ADDED arbicore/discovery/base_pool_registry.py (CanonicalPool + CREATE2 UniV3 derivation,
  KAT-proven). Derived 1:1 from base_venues (no duplicate metadata). canonical_id == synthetic id.
- 30 pools: 19 deterministic_verified (real UniV3 addrs), 11 runtime_getpool (Aerodrome), 0 unresolved.
- ADDED tests/test_m1_base_pool_registry.py (20 offline tests, PASS).
- Reports: reports/ARBICORE_X_CURRENT_STATE_REPORT.md, reports/ARBICORE_X_MILESTONE_1_REPORT.md
- Constants: UniV3 factory 0x33128a8fC17869897dcE68Ed026d694621f6FDfD;
  POOL_INIT_CODE_HASH 0xe34f199b19b2b4f47f68442619d555527d244f78a3297ea89325f843f87b8b54.

## Environment notes
- Preview container has NO .env, NO Base RPC/WSS, NO anvil → live validation (M3+) runs on VPS.
- Pre-existing test env issue: tests/test_stage1_canonical_flash_loan_scanner.py imports
  /app/frontend/.env (absent here) — unrelated to M1.

## Repo audit (2026-06) — reuse map
- Full 6-branch + 149-commit audit done → reports/ARBICORE_X_REPO_AUDIT_AND_INVENTORY.md
- KEY: only GENUINELY ABSENT capability = V3 on-chain state ingestion (V3 WSS decode +
  slot0/liquidity bootstrap + sqrtPriceX96->sqrt_p). Verified 0 matches on all branches.
  Everything else on roadmap = built+tested; work is composition/wiring + operator provisioning.
- Single incomplete composition point: server.py:6986 -> runtime.maybe_build_base_searcher()
  builds BaseSearcherRuntime with EMPTY RouteGraph + tvl_provider=None. This is where M2/M3 land.
- Reuse verdicts: M2=NEW(min, extend BaseWssSubscriber/PoolState/amm_math); M3=INTEGRATE existing
  OnChainReserveTVLProvider+price fn; M4=REUSE certification/*; M5=REUSE LimitedLiveBroadcaster+
  mode ladder+kill switch; M6=REUSE auto_executor.
- Duplication: dex_arbitrage/quoter.py = REMOVE AFTER VERIFICATION (0 importers); pool identity =
  CONSOLIDATE onto base_pool_registry; execution/quoter.py = CANONICAL quoter.

## Backlog / next
- M2 next (only on operator go) as pure EXTENSION: V3 event decoder + sqrtX96 util + slot0 bootstrap
  + offline tests. Then M3 wiring at maybe_build_base_searcher + resolve Aerodrome getPool on VPS.
