# ARBICORE X — MILESTONE 1 REPORT
**Canonical Base pool registry + real addresses.** SHADOW-safe, additive, offline-proven.
Status: **PASS** (software + deterministic tests). No higher risk level enabled.

## Files changed
- **ADDED** `app/backend/arbicore/discovery/base_pool_registry.py` — canonical registry.
  Derived 1:1 from existing `base_venues.VENUES`/`TOKENS` (no duplicated metadata).
  Uniswap-V3 addresses computed via CREATE2 (factory `0x33128a8f…6FDfD` + canonical
  `POOL_INIT_CODE_HASH 0xe34f199b…8b54`). Exposes `CanonicalPool`, `compute_univ3_pool_address`,
  `get_canonical_pools`, `canonical_pool_by_id/address`, `resolved_addresses`,
  `unresolved_pools`, `registry_summary`.
- **ADDED** `app/backend/tests/test_m1_base_pool_registry.py` — 20 deterministic offline tests.
- **UNCHANGED (preserved):** `base_venues.py`, `build_pool_graph()`, flash-loan scanner,
  T2 runtime, composition. Registry is not yet wired into consumers (by design — M1 only
  proves the registry; migration is a later milestone).

## Tests added (20) — all offline/deterministic, no RPC
- CREATE2 **known-answer** vs publicly-deployed Base pools:
  - WETH/USDC 0.05% → `0xd0b53D9277642d899DF5C87A3966A349A798F224`
  - WETH/USDC 0.01% → `0xb4CB800910B228ED3d0834cF79D697127BBB00e5`
- Symmetry (token arg order), distinct fee tiers, valid checksummed 20-byte output.
- Token ordering (on-chain `token0 < token1` by address) + symbol→address/decimals mapping.
- Fee-tier handling (ppm↔bps; SlipStream tick_spacing; classic stable flag/kind).
- Resolution provenance contract (UniV3=`deterministic_verified`+address;
  Aerodrome=`runtime_getpool`+no address; **0 `unresolved`**).
- `canonical_id` == existing `base_venues` synthetic id (1:1 migration bridge).
- Determinism (build twice identical), summary counts, address-lookup roundtrip.
- Guard test: `build_pool_graph()` behavior unchanged (synthetic ids + tvl sentinel).

## Commands run
```
pytest tests/test_m1_base_pool_registry.py -q            # 20 passed
pytest tests/test_t2_wss_ingest.py tests/test_t2_runtime.py \
       tests/test_t2_searcher.py tests/test_t2_live_base.py \
       tests/test_d6_1_route_search.py -q                # 43 passed (regression)
```

## PASS/FAIL
- **PASS** — 20/20 new tests; 43 passed in regression batch.
- 2 pre-existing errors in `tests/test_stage1_canonical_flash_loan_scanner.py` are
  ENVIRONMENTAL (module-level `open("/app/frontend/.env")`; that file is absent in this
  preview container). **Not caused by M1** — the file imports fail before any registry code runs.

## Unresolved / runtime_getpool pools (11 — resolve on VPS via factory getPool)
Aerodrome SlipStream (4): USDC/WETH ts100, WETH/cbETH ts1, WETH/wstETH ts1, AERO/WETH ts200.
Aerodrome classic (7): USDC/USDbC(s), USDC/USDT(s), DAI/USDC(s), USDC/WETH(v), AERO/WETH(v),
DEGEN/WETH(v), AERO/USDC(v).
Reason: Aerodrome CL/classic factory+init-code derivation is NOT established from this repo →
we refuse to guess an unverified init-code hash (per your condition). Each carries a
`resolver` hint for the VPS getPool/poolFor call.

## Remaining blockers (for M2+, NOT touched this milestone)
- No live RPC/WSS/anvil in this preview container → live V3 state init + WSS sync +
  Aerodrome address resolution must run on the VPS.
- V3 WSS decode (Swap/Mint/Burn/Initialize), `slot0()`/`liquidity()` bootstrap, and
  `sqrtPriceX96 → sqrt_p` conversion are M2 (not started).
- T2 `BaseSearcherRuntime` still built with empty `RouteGraph()` + `tvl_provider=None`
  (M3 wiring — intentionally untouched to preserve existing behavior).

## Migration / integration implications (for later milestones — NOT applied now)
- `canonical_id` deliberately equals the existing synthetic venue id, so consumers
  (`live_quote_provider.py`, `composition._base_pool_loader`, T2 `RouteGraph`, WSS
  subscription list) can be migrated to `resolved_addresses()` 1:1 with no parallel list.
- Live quoting is unaffected (QuoterV2 quotes by token+fee, not pool address), so migrating
  identity is low-risk; the real addresses unlock WSS subscription + V3 state reads in M2/M3.
- Aerodrome pools will need a VPS getPool resolution pass before they can join the WSS/state
  path; until resolved they remain quote-only (as today).

## Safety
No broadcasting, no signing, no Limited Live, no Auto Mode. Gates 7/8 untouched.
Existing discovery/FlashLoan behavior preserved. **STOP after Milestone 1 — awaiting review.**
