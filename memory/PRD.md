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
- M1 Canonical Base pool registry + real addresses — **DONE (2026-06, software+offline tests, PASS)**
- M2 V3 initial state (slot0/liquidity) + WSS sync (Swap/Mint/Burn/Initialize) + sqrtX96 conv — NOT STARTED
- M3 Real TVL provider wired into T2 (OnChainReserve + price fn) — NOT STARTED
- M4 Shadow validation certification (VPS) — NOT STARTED
- M5 Limited Live (hard risk limits) — NOT STARTED
- M6 Controlled Auto Mode — NOT STARTED

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
