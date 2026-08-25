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

## M3.0 WIRING delivered (2026-06) — controlled-live broadcaster now receives the safety layer
- GAP found: server.py:243 built _LIMITED_LIVE_BROADCASTER WITHOUT pre_broadcast_validator/
  circuit_breaker/require_revalidation → M3.0 layer inert. FIXED (minimum wiring, no features).
- NEW composition.build_controlled_live_safety(quoter_registry, kill_switch=...) → (PreBroadcastValidator,
  CircuitBreaker) or (None,None) w/o Base RPC. fresh_fn reuses make_live_quote_provider (M2.1) +
  build_base_tvl_provider(price_feed.price_source) (M2.5 price + M2.6-resolved TVL) +
  FlashLoanEconomicsAssessor (economics) + MevRiskScorer + Balancer V2 Vault balanceOf liquidity
  (real-time flash-loan availability). on_trip → kill_switch.engage.
- server.py: _controlled_live_safety_or_none() (fail-closed try/except) feeds the app broadcaster with
  require_revalidation=True. Preview (no RPC) → (None,None) → broadcaster DENIES before signing.
- Tests: tests/test_m3_0_wiring.py (6) — preview fail-closed builder; missing/denying validator, stale,
  unprofitable, flashloan-unavailable, tripped-breaker all → broadcast_sent False. testing_agent
  iteration_7: 100% pass, no issues. server.py boots with require_revalidation=True, validator/breaker
  None in preview (fail-closed).
- Live flags remain OFF: no signing key, LIMITED_LIVE not enabled, production untouched.

## M3.0 delivered (2026-06) — Atomic Pre-Broadcast Revalidation & Circuit Breakers (fail-closed)
- NEW arbicore/execution/pre_broadcast.py: PreBroadcastValidator (fresh re-check: re-quote/
  re-TVL/re-price/re-economics + block/reorg/deadline + real-time flash-loan availability +
  duplicate-opportunity + conservative safety-buffer), SeenOpportunityGuard (TTL de-dupe),
  CircuitBreaker (daily/hourly realized-loss caps, consecutive-failure cap, health flags,
  on_trip→kill-switch, fires once). All injectable; None/stale/error/mismatch → fail-closed.
- broadcast.py: LimitedLiveBroadcaster gains pre_broadcast_validator, circuit_breaker,
  require_revalidation. Gate 0 (circuit breaker) before kill switch; Gate 5b (atomic
  pre-broadcast revalidation) after operator-confirm and before the sign+broadcast branch.
  Both append to `denied`, so `if not denied and preflight_ok and confirm and not force_broadcast`
  is structurally unreachable unless fresh validation passes. Backward-compatible: new gates
  only active when injected / require_revalidation=True (default False).
- Env knobs (defaults): ARBICORE_MIN_NET_PROFIT_USD=25, ARBICORE_SAFETY_BUFFER_USD=10,
  ARBICORE_MAX_DAILY_LOSS_USD=100, ARBICORE_MAX_HOURLY_LOSS_USD=50, ARBICORE_MAX_CONSEC_FAILURES=3,
  ARBICORE_DEDUPE_TTL_S=30, ARBICORE_PRICE_MAX_BLOCK_LAG=5.
- Tests: tests/test_m3_0_pre_broadcast.py (22). testing_agent iteration_6: 116/116 PASS
  (22 M3.0 + 77 M1-M2.6 + 17 wave7 broadcaster); no issues. Existing broadcaster suite green
  (backward-compatible). NOT wired to live: no signing key, LIMITED_LIVE off, production unchanged.
- NEXT: operator wiring on VPS of fresh_fn (real quoter/TVL/price/economics) + circuit_breaker
  into the LIMITED_LIVE broadcaster with require_revalidation=True — BEFORE any Limited-Live.
  Await explicit approval.

## M2.6 delivered (2026-06) — Aerodrome/Slipstream on-chain pool resolution (fail-closed)
- NEW arbicore/searcher/aero_resolver.py: AerodromePoolResolver resolves runtime_getpool
  Aerodrome (classic) + Aerodrome-Slipstream (CL) pools via the DEX factory getPool on-chain,
  then VALIDATES before accepting: non-zero address, on-chain token0()/token1() == canonical
  address-ordered pair, pool type (classic stable() / slipstream tickSpacing()) match, correct
  chain. Any RPC failure/zero/mismatch/missing → None (fail-closed). Selectors computed via
  function_signature_to_4byte_selector (no hardcoded selector strings).
- Factories: classic PoolFactory reused = 0x420DD381b31aEf6683db6B902084cB0FFECe40Da
  (env ARBICORE_AERO_POOL_FACTORY_BASE). Slipstream CLFactory default =
  0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A (env ARBICORE_AERO_CL_FACTORY_BASE). Both
  env-overridable. No individual pool address hardcoded — all resolved on-chain + validated.
- Registry single source: base_pool_registry adds RUNTIME_RESOLVED + set_runtime_resolved_address()
  (dataclasses.replace fills address, sets RUNTIME_RESOLVED, updates by-id/by-address; refuses
  zero/unknown → fail-closed). unresolved_pools() filters runtime_getpool|unresolved;
  registry_summary adds runtime_resolved. No parallel pool list / routing engine.
- Composition: activate_canonical_flash_loan_scanner runs resolver.resolve_all(unresolved_pools())
  AFTER eth_call and BEFORE build_base_tvl_provider, applying validated addresses to the registry
  so the EXISTING v3_state reserves path (make_base_v3_reserves_fn/build_pool_meta_for_reserves)
  and live_quote_provider._resolve_pool_tvls pick them up unchanged. Activation dict adds
  aero_pools_resolved count. Preview (no RPC) → nothing resolves → Gate 8 stays fail-closed.
- Gate 7/8/9 semantics, signing, broadcast, LIMITED/FULL_LIVE, SHADOW no-broadcast, price
  provenance: ALL untouched. M2.5 pricing still UniV3-only (Slipstream RUNTIME_RESOLVED excluded
  from pricing routes, used only for TVL/reserves).
- Tests: tests/test_m2_6_aero_resolution.py (17) — valid classic/slipstream resolution; zero/none/
  RPC-fail/token-mismatch/wrong-tickSpacing/wrong-stable/tick-read-none/CL-unset/wrong-chain all
  fail closed; registry round-trip+guards; integration unresolved→Gate 8 FAIL then resolved+depth→
  Gate 8 PASS; resolve_all skips failures. testing_agent iteration_5: 17/17 + 77/77 regression +
  44/44 leakage check PASS; no critical/minor issues. Pre-existing broad-selector FAIL/ERROR are
  preview-env/HTTP artifacts (frontend/.env, MONGO_URL, HTTP auth) — not M2.6 regressions.
- Env for VPS (M2.6): ARBICORE_AERO_POOL_FACTORY_BASE (default classic), ARBICORE_AERO_CL_FACTORY_BASE
  (default 0x5e7BB104…). STOPPED for VPS live validation before any Limited-Live proposal. No
  execution/broadcast enabled.

## M2.5 delivered (2026-06) — multi-token USD price feed (on-chain, fail-closed)
- NEW arbicore/searcher/price_feed.py: OnChainUsdPriceFeed + PricePoint +
  build_base_price_feed_from_env + m2_5_enabled. USDC-denominated pricing via the
  existing QuoterRegistry (PRIMARY, genuine on-chain quotes). USDC = configured
  numéraire (ARBICORE_USD_NUMERAIRE, peg ARBICORE_STABLE_PEG_USD=1.0) — a valuation
  anchor, never quoted. Non-anchor tokens priced direct T→USDC or two-hop T→WETH→USDC
  over deterministic-verified UniV3 pools only. Stablecoins (ARBICORE_STABLES) peg-guarded
  (±ARBICORE_STABLE_PEG_BAND_BPS); freshness enforced (ARBICORE_PRICE_TTL_S cache +
  ARBICORE_PRICE_MAX_BLOCK_LAG vs head). Any missing/stale/unverifiable/out-of-band/no-path/
  quote-failure → None → Gate 8 fails closed. ZERO fabricated prices.
- Provenance: per-token PricePoint {token, price_usd, source, status, path, pools, quoter,
  block, head_block, stale, ts}. Surfaced in evidence bundle liquidity.price_provenance via
  verifier.price_provenance_fn (new optional) ← scanner.set_price_provenance_fn ←
  composition wires feed.provenance_for. Audit-only; gate semantics unchanged.
- composition.activate_canonical_flash_loan_scanner now prefers the M2.5 feed
  (build_base_price_feed_from_env) and falls back to native-only source when
  ARBICORE_USD_NUMERAIRE/RPC absent (fail-closed). Activation dict adds price_source kind.
- Tests: tests/test_m2_5_price_feed.py (13) — numéraire-no-quote, direct WETH, two-hop weETH,
  in/out-of-band peg guard, stale block-lag, unverifiable head, no_path, quote_failed,
  not_evaluated provenance, Gate 8 pass/fail via feed integration. testing_agent iteration_4:
  40/40 targeted (13 M2.5 + 21 M2.1-4 + 6 M3) PASS; invariants verified; no regressions.
  Pre-existing 7 FAIL + 58 ERROR are preview-env artifacts (frontend/.env, MONGO_URL, HTTP auth).
- Token universe (12 across 30 canonical pools): WETH, USDC, USDT, DAI, USDbC, cbETH,
  wstETH, rETH, weETH, cbBTC, AERO, DEGEN. UniV3 deterministic pools give a genuine USDC
  pricing graph for all 12.
- Env required (VPS): ARBICORE_USD_NUMERAIRE=USDC, ARBICORE_STABLE_PEG_USD=1.0,
  ARBICORE_STABLES=USDC,USDT,DAI,USDbC, ARBICORE_STABLE_PEG_BAND_BPS=200,
  ARBICORE_PRICE_TTL_S=12, ARBICORE_PRICE_MAX_BLOCK_LAG=5, plus ARBICORE_RPC_URL(_BASE),
  ARBICORE_WSS_URL_BASE, ARBICORE_NATIVE_PRICE_USD, ARBICORE_T2_SEARCHER_ENABLED=true.
  ARBICORE_FLASH_LOAN_SHADOW_ROUTE stays OFF. No LIMITED_LIVE/FULL_LIVE.
- Production stays on 9bd3ea5 pending VPS live validation. No execution/broadcast enabled.

## M2.2 / M2.3 / M2.4 delivered (2026-06) — offline, fail-closed, NO execution
- M2.2 REAL TVL→Gate8: make_live_quote_provider(quoter, *, tvl_provider=None). New
  _resolve_pool_tvls (synthetic route id == canonical registry id → REAL address →
  tvl_provider.get_pool_tvl_usd) + _route_min_tvl (fail-closed 0.0 unless EVERY route
  pool has positive verified depth). tvl_provenance flag on facts. Wired in
  composition.activate_canonical_flash_loan_scanner from env (make_base_eth_call_from_env
  + make_base_price_source_from_env + build_base_tvl_provider); absent env → None →
  Gate 8 fails closed. Preview stays fail-closed; VPS gets real depth.
- M2.3 evidence for EVERY verified candidate (CONFIRMED + DENIED): verifier.verify()
  refactored to a single _finalize() exit + per-gate ledger. _build_evidence_bundle emits
  verification_status (CONFIRMED|DENIED), gates.{gate_7,gate_8,gate_9}={status
  PASS|FAIL|NOT_EVALUATED, reason} (short-circuit 7→8→9 preserved), route+real pool
  addresses, input amount, quotes/hop_legs, fees, gas, economics, liquidity(min TVL +
  tvl_provenance), mev, block_context, provenance=REAL, broadcast=False. Persisted via new
  optional evidence_sink → EvidenceBundlesRepo/db.evidence_bundles
  (composition.make_flash_loan_evidence_sink + get_evidence_bundles_repo). Sink is
  side-effect only; a sink exception NEVER changes the (canonical, outcome) verdict.
- M2.4 CONFIRMED → SHADOW/PAPER: new shadow_route.py (canonical_to_pipeline_opp +
  route_to_shadow) drives the existing arbicore/execution OpportunityPipeline in SHADOW
  (no mode_repo → mode=SHADOW; no broadcaster → cannot broadcast; asserts action!='broadcast').
  Wired via verifier.shadow_sink (scanner.set_shadow_sink) + composition.make_flash_loan_shadow_sink,
  OPT-IN behind ARBICORE_FLASH_LOAN_SHADOW_ROUTE (default OFF to avoid double-processing
  with the global PaperValidationRunner). No signing, no broadcast.
- SIDE FIX (on the M2.4 confirm path): live_quote_provider now emits REGISTERED REAL
  quoter source ids per DEX (_dex_source_id: uniswap_v3→uniswap_v3_quoter_base,
  aerodrome*→aerodrome_quoter_base) instead of the previously-unregistered *_quote_real
  strings, which classified as DEAD in provenance.get_classification and structurally
  blocked derive_provenance → every confirm became denied:venue_unreadable. This unblocks
  the CONFIRMED path without weakening provenance (still fail-closed on unknown DEX).
  Updated test_m2_1_live_quote_provider assertion to check REAL classification.
- Tests: test_m2_2_real_tvl_gate8.py, test_m2_3_evidence_bundle.py, test_m2_4_shadow_route.py
  (+ m2_1 kept green) = 21/21 PASS. testing_agent iteration_3: 21/21 green, invariants
  verified (broadcast=False, route_to_shadow tripwire, no broadcaster/mode_repo wired),
  7 HTTP failures + 58 collection errors classified PRE-EXISTING preview-env artifacts.
- NEXT (per user): STOP; await VPS live validation (real Base RPC/WSS/price) of
  M2.1–M2.4 before any Limited-Live execution proposal. VPS backlog unchanged: resolve
  11 Aerodrome runtime_getpool pools; wire multi-token USD price feed (Gate 8 non-native);
  fix Mongo TTL reaping (expires_at BSON Date vs float epoch). Execution NOT enabled.

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
