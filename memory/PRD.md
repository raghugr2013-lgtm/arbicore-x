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

## M3.0 fresh_fn DIAGNOSTICS + spec-passthrough FIX (2026-06)
- SYMPTOM (VPS): M3.0 final gate DENY "revalidation: fresh market read unavailable" for a
  genuine WETH route UniV3→Aerodrome→Slipstream. All constructions OK (eth_call, price_feed,
  tvl_provider, quote_provider, validator, breaker). fresh_fn returned None (not raised) so the
  exact blocking stage was invisible.
- ROOT-CAUSE class: fresh_fn (composition.build_controlled_live_safety) had a catch-all
  `except Exception: return None` + several bare `return None` paths (facts None, no hop_legs)
  with ZERO diagnostics. Additionally a REAL defect: make_live_quote_provider._provider copied
  only `fee` into each hop, DROPPING `tick_spacing` (Slipstream) and `stable` (Aerodrome-classic)
  → those backends degraded to a fabricated break-even passthrough (amount_out==amount_in),
  corrupting gross_profit and making non-UniV3 routes unpriceable.
- FIX (minimal, 3 files, fail-closed & gate-behaviour UNCHANGED):
  1. composition.py: added logger `arbicore.m3_0.fresh_fn`; fresh_fn now tracks a `stage` var and
     logs the EXACT stage + value/exception on every None/exception path (extract_plan,
     token_path_shape, live_quote, hop_legs, mev, economics, head_block, flashloan_available,
     assemble). _flashloan_available logs per-stage (provider_meta / token_registry /
     balanceOf_eth_call / balanceOf_empty / balanceOf_decode / borrow_token_price /
     insufficient_vault_liquidity). Return semantics identical — every failure still returns None.
  2. live_quote_provider.py: _provider now also copies spec['tick_spacing'] and spec['stable']
     into the hop so Slipstream/Aerodrome hops quote GENUINELY on-chain (values from
     build_pool_graph — nothing fabricated). UniV3 unchanged.
  3. scripts/m3_0_vps_validate.py: added read-only _probe_fresh_stages() step-by-step dependency
     probe (plan shape, per-pool spec+real-addr+TVL, head block, borrow price, raw per-hop route
     quote with status/error, live-quote facts, Balancer Vault balanceOf) + FIRST_BLOCKING_STAGE
     summary; enabled INFO logging to stderr; verdict.broadcast_sent normalized to explicit bool.
- Balancer V2 Vault default 0xBA12222222228d8Ba445958a75a0704d566BF2C8 CONFIRMED correct on Base
  (canonical, chain-agnostic) → unset BASE_BALANCER_V2_VAULT is NOT a problem; harness actually
  tests balanceOf so the operator sees the real read.
- Tests: tests/test_m2_1_live_quote_provider.py +1 (test_venue_specific_quote_params_passed_through:
  UniV3 gets fee only, Aerodrome gets stable, Slipstream gets tick_spacing; no cross-leak).
  testing_agent iteration_8: 80/80 PASS across M2.1-2.6 + M3.0 (pre_broadcast + wiring), harness
  exit 0, verdict.safe=true / signed_or_broadcast=false, no fabrication, no broadcast, no signing.
- VPS NEXT (operator, read-only): run `python -m scripts.m3_0_vps_validate '<plan>'` inside the
  M3.0 validator container — FIRST_BLOCKING_STAGE + per-hop stage_5_route_quote now name the exact
  culprit under real RPC. Slipstream/Aerodrome hops will price genuinely with the passthrough fix.
  STILL fail-closed: no LIMITED_LIVE, no signing key, production untouched.
- DEFERRED (unchanged, separate pass per operator): Mongo TTL reaping expires_at float→BSON Date.

## Session — M3.0 Real-Base GREEN prep (2026-08-25, continuation)
HEAD at start: cdd201f (parent 32d86e6). Branch: complete-Base-M1-M4-live-shadow-composition.
Preview container had NO Base RPC and .env was stripped by fork → restored (local Mongo,
DB_NAME=arbicore_x). All live/exec/signing flags kept OFF (AUTOEXEC/RUNTIME/DISCOVERY
autostart=false; no signing key; FLASH_LOAN_SHADOW_ROUTE unset). Production untouched.

### Fixes landed (offline, fail-closed preserved, testing_agent 88/88)
1. MEV `source_chain_congestion=None` blocker — real source added:
   `arbicore/searcher/runtime.py::make_base_congestion_source_from_env()` derives Base
   congestion (0..100) from `eth_feeHistory.gasUsedRatio`. Wired into `composition.py`
   fresh_fn stage=mev; **DENY if unreadable** (no fabricated value). Also fixed a latent
   crash: `mev_view["level"] <= 2` (str-enum vs int) → policy now `label != "HIGH"`
   (LOW/MEDIUM pass, HIGH denies; matches flash_loan filter._MEV_ORDER).
2. Stage-probe alignment — `scripts/m3_0_vps_validate.py`: added `stage_8_mev` + reordered
   `_first_blocking_stage` to mirror fresh_fn (shape→resolve→live_quote→hop_legs→mev→
   head→price→flashloan) + ERROR-string branch so a stage_6 exception is reported as
   live_quote (before mev), not misattributed to mev.
3. Aerodrome/Slipstream address/TVL propagation — `aero_resolver.py::resolve_and_propagate()`
   resolves+validates on-chain and writes REAL addresses into the ONE canonical registry via
   `set_runtime_resolved_address()`. Wired into fresh_fn (stage=resolve_pools) + the probe, so
   the TVL/address path now matches the quote path. Fail-closed if resolution fails.
4. Audit JSON cleanup — `ARBICORE_M3_AUDIT_FILE` writes pure JSON; logs→stderr, JSON→stdout.
5. BONUS (was HIGH): mixed-case Base token KeyError — `base_venues.py` now has
   `canonical_symbol()`, case-insensitive `token_address()`/`is_stable()` (None on unknown),
   and `probe_amount()`. Prevented cbETH/USDbC/cbBTC/rETH/wstETH/weETH routes from
   permanently DENYing on the VPS. `live_quote_provider.py` uses `probe_amount()`.

Regression: tests/test_m3_0_mev_congestion.py (22 new tests) + existing M3 suites pass.

### Definition of done for M3.0 REAL BASE GREEN (still pending — needs VPS real RPC)
On an isolated VPS validator with real Base RPC + a genuinely profitable candidate, the audit
must show m3_final_gates.ok=true while signed_or_broadcast=false / broadcast_sent=false / safe=true.
Offline (no RPC) the correct result is DENY/fail-closed (verified).

### VPS validator / stage-confirm commands (run on isolated validator, NOT production)
    # env required (isolated validator only):
    #   ARBICORE_RPC_URL_BASE=<real Base RPC>   (precedence: ARBICORE_RPC_URL_BASE > ARBICORE_RPC_URL > BASE_RPC_URL)
    #   ARBICORE_NATIVE_PRICE_USD / ARBICORE_USD_NUMERAIRE  (M2.5 price feed)
    #   (Aero factories + Balancer vault have canonical defaults; override via
    #    ARBICORE_AERO_CL_FACTORY_BASE / ARBICORE_AERO_POOL_FACTORY_BASE / BASE_BALANCER_V2_VAULT)
    #   KEEP OFF: no signing key, ARBICORE_FLASH_LOAN_SHADOW_ROUTE unset,
    #            ARBICORE_AUTOEXEC_AUTOSTART=false, ARBICORE_RUNTIME_AUTOSTART=false
    cd /app/backend
    ARBICORE_M3_AUDIT_FILE=/tmp/m3_audit.json \
      python -m scripts.m3_0_vps_validate 2> /tmp/m3_run.log            # latest CONFIRMED bundle
    # or with an explicit plan:
    ARBICORE_M3_AUDIT_FILE=/tmp/m3_audit.json \
      python -m scripts.m3_0_vps_validate '<plan-json>' 2> /tmp/m3_run.log
    python -m json.tool /tmp/m3_audit.json      # pure JSON (logs are in /tmp/m3_run.log)
    # read: .verdict.safe, .verdict.signed_or_broadcast, .m3_final_gates.ok,
    #       .fresh_stage_probe.FIRST_BLOCKING_STAGE

## Session — Real-Base M3.0 candidate validation (2026-08-25, next phase)
Ran the IDENTICAL read-only M3.0 validator against REAL public Base RPC (mainnet.base.org)
from inside the Emergent container (no VPS access available to the agent; container has
outbound internet). Source commit cdd201f + this session's fixes. NO signing key, NO
broadcast, NO live flags; the running preview backend .env still has NO RPC (fail-closed).

### Real-Base findings (head block ~50,429,4xx)
- Validator + CircuitBreaker CONSTRUCT against real RPC (ARBICORE_RPC_URL + _BASE + USD_NUMERAIRE=USDC).
- MEV congestion source WORKS on real chain: eth_feeHistory gasUsedRatio ≈ 6.67% → LOW, mev_ok=True.
- Quotes WORK on real chain (real gross % per route). Balancer V2 Vault balanceOf real: ~24.4 WETH.
- UniV3 route TVL measured real (min route TVL ≈ $8.20M, provenance=onchain_reserves).
- 5 genuine canonical cycles scanned (fee-tier, cross-DEX, stable, triangular). GREEN=0.
  DECISIVE blocker = profit_buffer (economics): all real gross profits NEGATIVE
  (−0.017% … −0.571%; candidate WETH/USDC univ3 500→3000 = −0.571%, net ≈ −$92 vs required $35).
  → NO genuinely profitable candidate currently exists. Correct result = DENY / fail-closed.
  verdict.safe=true, broadcast_sent=false throughout.

### Additional fix landed this phase (TVL source-of-truth completion)
- `v3_state.make_base_v3_reserves_fn`: on a pool_meta miss it now falls back to
  `base_pool_registry.canonical_pool_by_address()` so RUNTIME-RESOLVED Aerodrome/Slipstream
  addresses (written by `resolve_and_propagate`) become TVL-measurable. Proven on real chain:
  `aerodrome_slipstream:USDC:WETH:100` resolved to 0xb2cc…DC59 (runtime_resolved) and holds
  ~1647 WETH + 6.03M USDC (~$10M). (Intermittent None here is the FREE public RPC rate-limiting
  consecutive balanceOf calls — NOT a code bug; a dedicated VPS RPC returns both reads.)
- New harness: `scripts/m3_0_real_candidate_scan.py` (read-only) scans candidate cycles and emits
  per-gate + real-economics JSON. testing_agent iteration_3: 68/68 + 3/3 integration, all green.

### NEXT STEP toward controlled-live (blocked on a genuinely profitable candidate)
1. Commit fixes; build a fresh VPS validator image from the new HEAD.
2. On the VPS, point at a DEDICATED (non-rate-limited) Base RPC and run
   `scripts.m3_0_real_candidate_scan` / `scripts.m3_0_vps_validate` against REAL CONFIRMED
   evidence bundles from the production Mongo to hunt a candidate that clears profit_buffer.
3. M3 GREEN only when a real arb nets ≥ $35 (min $25 + $10 buffer) with all other gates PASS.
   Do NOT lower thresholds. Until then the system correctly stays fail-closed.
