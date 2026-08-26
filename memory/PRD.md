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

## Session — Spread Widener Watch (2026-08-25, first-revenue support)
Per user's paused/refined instruction (competitive-research report DEFERRED; focus on
first-revenue path). Production untouched (2.9.2-78b2a8c); no signing/live/broadcast.

### Delivered: scripts/m3_0_spread_widener_watch.py (READ-ONLY monitor)
- Auto-enumerates every canonical Base route cycle (fee-tier + cross-DEX 2-hop) from the
  registry + freshest CONFIRMED evidence bundles from Mongo; computes each route's REAL
  gross_profit_pct (live quote + M2.6 TVL) and est_net_usd (FlashLoanEconomicsAssessor with
  MEV level from REAL eth_feeHistory congestion).
- FLAG semantics (signal separation, addresses testing_agent minor):
    worth_m3_validation = net computed AND net >= min_net (default 25+10=35)  → run full M3
    edge_positive       = gross >= min_gross (default 0.0)                    → informational
  Only FULLY-priced ("ok") routes with a plausible spread (|gross| <= 50% clamp) are ever
  flagged — partial/anomalous quotes (public-RPC rate-limit noise) are refused (net=None).
- Env: ARBICORE_RPC_URL(+_BASE), ARBICORE_USD_NUMERAIRE=USDC, optional
  ARBICORE_SPREAD_WATCH_{MIN_NET_USD,MIN_GROSS_PCT,BORROW_USD,MAX_ROUTES,INTERVAL_S,MAX_GROSS_PCT},
  ARBICORE_M3_AUDIT_FILE. NO broadcaster/signer is constructed anywhere in the script.
- Real-Base proof (public RPC): fully-priced WETH/USDC cycles show net −$46.6/−$62.2/−$82.6
  (gross −0.11%/−0.27%/−0.47%), flagged_count=0, safe=true. No profitable candidate exists.
- testing_agent iteration_4: 131 tests pass, no critical issues; regression green.

### VPS run recipe (dedicated RPC + prod Mongo)
    cd /app/backend
    export ARBICORE_RPC_URL=$BASE_RPC_DEDICATED ARBICORE_RPC_URL_BASE=$BASE_RPC_DEDICATED ARBICORE_USD_NUMERAIRE=USDC
    export MONGO_URL=$PROD_READONLY_MONGO_URL DB_NAME=$PROD_DB_NAME
    export ARBICORE_SPREAD_WATCH_INTERVAL_S=30            # loop; omit for single pass
    ARBICORE_M3_AUDIT_FILE=/tmp/spread.json python -m scripts.m3_0_spread_widener_watch 2> /tmp/spread.log
    # When flagged_count > 0 → take that route's route_pools and run full M3:
    ARBICORE_M3_AUDIT_FILE=/tmp/m3.json python -m scripts.m3_0_vps_validate '<plan-with-flagged-route>' 2> /tmp/m3.log
    python -m json.tool /tmp/m3.json    # require m3_final_gates.ok=true, broadcast_sent=false, safe=true

### DEFERRED (not started, per user): PART 1-11 competitive-research report, multi-agent
Foreman, competitor-intelligence layer, multi-chain workers. To be produced on request AFTER
the first genuine M3 GREEN candidate + Controlled-Live readiness.

## Session — Base all-in-fee M3 gate + Competitive Strategy Report (2026-08-25)
Production untouched (2.9.2-78b2a8c); no signing/live/broadcast.
### P0 code: true all-in transaction-fee gate (controlled-live economics)
- NEW arbicore/searcher/base_all_in_cost.py: all_in = L2 exec (real gas-price ceiling w/ buffer,
  DENY if real gp*(1+buf) exceeds ceiling — never silently caps) + Base L1 data fee via
  GasPriceOracle 0x420...0F getL1Fee + flash-loan fee + slippage allowance. Swap fees already in
  quoted gross (not double-counted). from_env() hard-clamps gas ceiling < 25M protocol max, floors bps>=0.
- Wired into composition.fresh_fn stage='all_in_cost': RevalidationInputs.net_profit_usd is now the
  STRICTER (gross - all_in); fresh_fn DENIES if all-in cannot be determined (fail-closed). Requires
  (gross - all_in) >= ARBICORE_MIN_NET_PROFIT_USD(25) + ARBICORE_SAFETY_BUFFER_USD(10).
- Config env: ARBICORE_GAS_PRICE_BUFFER_PCT(0.25), ARBICORE_MAX_GAS_PRICE_WEI(5e9),
  ARBICORE_GAS_LIMIT_CEILING(3e6), ARBICORE_FLASH_LOAN_FEE_BPS(0), ARBICORE_SLIPPAGE_BPS(30),
  ARBICORE_BASE_L1_TX_BYTES(1200).
- Real-Base proof: reads real gas price (7.5 gwei ceiling) + real L1 GasPriceOracle fee; fail-closed.
- testing_agent iterations 5→6: HIGH gas-cap defect + MINOR env-clamp fixed; 88/88 in-scope tests green.
### Deliverable: memory/COMPETITIVE_STRATEGY_REPORT.md (PART 1-12, evidence/inference/proposed tagged)
- Thesis: compete on fail-closed all-in-honest safety + outcome-learning targeted search +
  multi-chain×multi-strategy breadth (M3-gated), NOT raw latency. P0/P1/P2/P3 roadmap + 30-day plan.
- NOT implemented (deferred per instruction): WSS/Flashblocks discovery, learning ranker, multi-chain
  workers, liquidation/stablecoin/LST strategies, competitor-intel layer, Foreman, Strategy Factory.

## Session — Near-threshold signal (read-only) in Spread Widener Watch (2026-08-25)
Production untouched; no signing/live/broadcast; M3 + min_net UNCHANGED.
- scripts/m3_0_spread_widener_watch.py: added READ-ONLY near-threshold signal.
  _net_gap(net,min_net)=min_net-net; _near_threshold(rows,min_net,band,top) → priced routes with
  0<gap<=band ranked nearest-first (tag near_threshold=True). Snapshot adds near_threshold_count,
  near_threshold[], focus_route_pools (flagged ∪ near). _scan_once(focus_route_pools=...) restricts
  evaluation to those routes; main() optionally re-samples them every
  ARBICORE_SPREAD_WATCH_FOCUS_INTERVAL_S between full passes. New env:
  ARBICORE_SPREAD_WATCH_NEAR_BAND_USD(25), ARBICORE_SPREAD_WATCH_NEAR_TOP(10),
  ARBICORE_SPREAD_WATCH_FOCUS_INTERVAL_S(0). Never lowers min_net, never signs/broadcasts.
- Real-Base proof (band=100 demo): near_threshold=2 ranked nearest-first (gap $79.79 net -$44.79;
  gap $80.99 net -$45.99), min_net=35 unchanged, safe=true, signed_or_broadcast=false.
- testing_agent iteration_7: 88/88 in-scope tests green, no critical issues.

## Session — Frontend Data-Truth / Operator-Trust Audit (2026-06) — REPORT ONLY, no code changed
Delivered `/app/memory/FRONTEND_DATA_TRUTH_AUDIT.md` (full field→API→backend→Mongo/on-chain
trace + classification + P0-P3). No code changed; M3 fail-closed untouched; no live/signing.
- Active UI = `src/v2/*` at `/dashboard`. Data-truth defects concentrated in ONE translator
  `server.py::_canonical_opp_to_contract` (1013-1049) + `v2/components/Primitives.jsx`.
- P0-1 fake 100% safety (risk_score default 0.0 → safety 1.0). P0-2 implausible return %
  (USD expected_profit_usd in return_low/high rendered ×100% by fmtPct). P0-3 verdict=GO from
  lifecycle status, not economics.
- P1: spread None→0.0bps + unit assumption; "Depth"=capital_required_usd (mislabel, None→$0);
  confidence/score None→0; provenance never rendered; drawer reasoning/verification DEMO;
  roi-probability hardcoded+unauth; /arbicore/version unknown/unset in prod (build env not injected).
- Source-of-truth map: opportunities/discovery/confidence/spread/depth/return/verdict ←
  `arbicore_opportunities`; mode ← `control_state`(default SHADOW); config (scanner/execution/
  operational/network/account/notifications) consolidated in `arbicore_config` by `_id:kind`
  (explains "missing" arbicore_*-prefixed collections); capital_policy/wallet_registry/
  execution_mode_state real. Control Center + Live Ops are HONEST (backend-authoritative, "—").
- Prod 2.9.2-78b2a8c vs validator ce041c8 gap: MEV congestion source, aero resolve+TVL propagate,
  case-insensitive token lookup, all-in L1/L2 cost gate, spread-widener watch — all validator-only.
- NEXT (await user approval): Phase 2 P0/P1 display-truth fixes in controlled batches + tests +
  screenshots. Backend: stop `or 0` coercion, split USD vs %, add economic_state/verdict, surface
  provenance, drop DEMO blocks, guard roi-probability. Frontend: UNAVAILABLE pill states, fmtUsd
  for USD, % only for real fractions, provenance chip, no fake GREEN/SAFE/GO.

## Session — Data-Truth Phase 2 fixes (2026-06) — DONE, tested
Implemented + verified P0-1/P0-2/P0-3 and P1 truth fixes. No execution/signing/broadcast/mode/M3
files touched; LIMITED_LIVE/FULL_LIVE remain OFF. Changed files: `backend/server.py` (display
handlers only), `frontend/src/v2/components/Primitives.jsx`, `.../components/OpportunityDrawer.jsx`,
`.../pages/OpportunitiesPage.jsx`; new `backend/BUILD_INFO.json`, `backend/scripts/gen_build_info.py`,
`backend/tests/test_data_truth_contract.py`.
- P0-1 SAFE: `safety`/`confidence` numeric ONLY when assessed (score>0 OR REAL/VERIFIED_REAL
  provenance); else `null` + `*_assessed=False` (UI "—"). Genuine REAL zero stays real.
- P0-2 RETURN: removed fabricated ±10% band + `return_low/high`; USD stays USD
  (`expected_profit_usd`, `capital_required_usd`); `return_pct` = real fraction profit/capital or null.
  Frontend renders USD via fmtUsd, % only for real fractions. Killed the "$X → X0000%" unit bug.
- P0-3 VERDICT: GO only when APPROVED **and** ECONOMICALLY_VALID; added `economic_state`
  (DISCOVERED/LIVE_QUOTED/VERIFIED/ECONOMICALLY_VALID) + new UNVERIFIED verdict. Raw/validated-
  but-unpriced rows never GO. M3 remains final execution authority (display-advisory only).
- P1: no zero-coercion (spread/capital/confidence/score None→"—"); ProvenanceChip
  SIMULATED/REAL/VERIFIED_REAL on table+drawer; "Depth" column relabelled "Capital req."
  (real TVL not on canonical rows → depth_usd=null); drawer Reasoning/Verification DEMO/HARDCODED
  removed (honest economic-state block, quote_source=null); roi-probability now reads
  `arbicore_opportunity_journal` realized outcomes (available=false when no samples) + auth-gated;
  FreshnessBadge null→"—"; build metadata via BUILD_INFO.json fallback (preview reports real
  git_sha/tag/build_time; CI/Docker should run scripts/gen_build_info.py or set ARBICORE_* env).
- Tests: 18 new contract regressions PASS; M3 safety 52 PASS; live API + UI screenshots verified
  (raw SIMULATED→UNVERIFIED/"—"; REAL approved→GO, $120/1.20%). Pre-existing legacy live-HTTP
  tests still fail on stale password `ShadowOperator!2026` (out of scope).
- NOT deployed (per instruction). Build/validate image separately; run gen_build_info in build.

## Session — Data-Truth Phase 2b: Portfolio/Capital/Legend/BuildStamp (2026-06) — DONE, tested
Remaining P1 truth fixes. No execution/signing/broadcast/mode/M3 files touched; LIMITED_LIVE/FULL_LIVE
still hard-gated (verified refused). Not deployed. Docker not available in sandbox → image build
must run in CI/host; Dockerfile wiring validated via gen_build_info + /arbicore/version.
- Portfolio Truth: 8 stub endpoints (positions/balances/transfers/deployable/treasury/ledger/
  exposure/allocation) now return available:false + null USD totals + unavailable_reason instead
  of $0.0. Frontend UnavailableNote banner + counts "—". (server.py, PortfolioPage.jsx)
- Capital/Wallet: WalletIntelligenceEngine.live_balances → total_value_usd=None + available:false
  + unavailable_reason when on-chain source down (ok=False); genuine confirmed zero (ok=True) stays 0.
  Frontend UNAVAILABLE banner in Live Balances panel. (wallet_intelligence.py, CapitalIntelligencePage.jsx)
- Verdict Legend: economic-state ladder on Opportunities — DISCOVERED → LIVE_QUOTED → VERIFIED →
  ECONOMICALLY_VALID → M3_GREEN. (OpportunitiesPage.jsx)
- CI Build Stamp: both backend Dockerfiles (deployment/docker/backend, deployment/upgrade/backend)
  add IMAGE_DIGEST/IMAGE_REF ARGs+ENV and `RUN python -m scripts.gen_build_info` so /arbicore/version
  reports git SHA/tag/build time/version/image/env even without .git. BUILD_INFO.json refreshed.
- Tests: 23 data-truth + 28 M3 wiring/pre-broadcast = 51 PASS. Live API verified (portfolio
  available:false/null; capital live RPC read works + unavailable path unit-tested). Screenshots
  confirm legend + Portfolio UNAVAILABLE banner ("—" not $0).
- Commit SHA at report time: 6142487 (platform auto-commits this step's edits as the next checkpoint).

## Session — Branding / UI identity integration (2026-06) — DONE, verified (UI-only)
Frontend + public assets ONLY; no backend/execution/M3/API/scanner/wallet touched; no safety flags.
- Assets from uploaded artwork → processed transparent PNGs in frontend/public: arbicore-emblem.png
  (+16/32/64/180/192/512), favicon.ico (multi-res), arbicore-logo.png (full lockup).
- Login (LoginPage.jsx/.css): clean emblem centered above "ARBICORE X" wordmark (gold X) + tagline.
- Header (Header.jsx): compact emblem + "ARBICORE X" (gold X), consistent across all sections.
- Browser title: index.html <title> "Emergent | Fullstack App" → "ArbiCore X"; meta description →
  ArbiCore X; favicon/apple-touch links added. AppShell sets per-page "ArbiCore X — {Section}";
  LoginPage sets "ArbiCore X". No "Emergent | Fullstack App" remains (vendor scripts kept).
- QA: Playwright screenshots (login + header) + page.title() assertions ("ArbiCore X",
  "ArbiCore X — Live Ops") + asset 200 checks. No jest suite in project.

## Session — VPS validator handoff (2026-06)
Branch complete-Base-M1-M4-live-shadow-composition HEAD = ffbd7f0a506ebc78b121cae089985ab5684ec3c9
contains all 4 workstreams (Phase2 data-truth 6142487 → Portfolio/Capital+build-metadata 3e765f9 →
branding ffbd7f0). User pushes via Save to Github. I cannot push or reach the VPS.
Delivered /app/memory/VPS_VALIDATOR_RUNBOOK.md — isolated, READ-ONLY validator build+verify+hunt
runbook (fetch exact HEAD → build fresh image w/ GITSHA/GITTAG/BUILD_TIME/APP_VERSION →
loopback container w/ .env.validator (LIMITED_LIVE/FULL_LIVE/AUTOEXEC=0, no signer) →
/api/arbicore/version identity check → mode-refusal safety check → frontend title/favicon/data-truth
check → m3_0_spread_widener_watch on dedicated RPC → on flagged route run m3_0_vps_validate
(confirm=False, never signs/broadcasts) → assert m3_final_gates.ok, verdict.signed_or_broadcast=false,
broadcast_ladder.broadcast_sent=false, verdict.safe=true). No prod deploy, no proxy switch.
Objective: FIRST GENUINE BASE M3 GREEN → controlled-live readiness → first small human-confirmed trade.

## Session — Isolated frontend+backend verification of f36d7c9 (2026-06)
Verified the ArbiCore X frontend (branding + data-truth) against the running preview (isolated,
non-production, = branch HEAD f36d7c9). Testing agent iteration_8: 8/9 PASS; found 1 MEDIUM defect —
per-page document.title + header breadcrumb wrong for 9/12 sections (nav.js used legacy /v2/* while
app routes /dashboard/*). FIXED frontend/src/v2/lib/nav.js → all paths /dashboard/* (home=/dashboard/home).
Re-test iteration_9: 6/6 PASS (100%) — titles, breadcrumb, rail active-state correct for all sections;
branding + Opportunities/Portfolio data-truth regression all green.
- Production still shows OLD frontend = deployment gap only (frontend image not rebuilt); code is correct.
- FRONTEND SHA CAVEAT: nav fix landed AFTER f36d7c9 → frontend must be built from the new checkpoint SHA
  (re-push via Save to Github). Backend f36d7c9 image unaffected (nav fix is frontend-only).
- Non-blocking (deferred): React duplicate-key console warning on Live Ops scanner feed; optional
  capital-balances-unavailable testid; /dashboard index → Control fallback breadcrumb.
- No LIMITED_LIVE/FULL_LIVE/signing/broadcast touched. No production deploy/switch.

## Session — API-base normalization layer (2026-06) — DONE, testing-agent verified
Fixes same-origin validator wiring without exposing backend or using empty base.
- NEW frontend/src/lib/apiBase.js: computeApiBase/computeOrigin + API_BASE/BACKEND_ORIGIN/apiUrl.
  Rules: ''/'api'->'/api'; absolute->'<base>/api'; trailing '/api' or slash tolerated; never '/api/api'.
- Refactored shared helper (v2/lib/api.js), AuthContext, and ALL active v2 direct-callers
  (LiveOps, ControlCenter, Capital, FlashLoanJourney, LimitedLiveWizard, ExecutorVerify,
  FlashLoanOperator, Initialization, PostTrade -> const API=API_BASE; OpsCenter -> BACKEND_ORIGIN).
- Regression tests frontend/src/lib/apiBase.test.js: 8/8 PASS (prod absolute, same-origin /api,
  empty, trailing slash, already-/api, no /api/api duplication, origin+own-/api).
- Validator-only nginx: deployment/validator/nginx.validator.conf (proxies /api -> backend
  container 'arbicore-validator:8001' on private net; backend never public). Production nginx untouched.
- Runbook step 7a updated: build FE from latest HEAD with REACT_APP_BACKEND_URL=/api, run on
  shared docker net 'arbicore-validator-net', mount validator nginx, prove /api proxy hits backend.
- Testing agent iteration_10: 7/7 PASS (100% frontend), ZERO /api/api or undefined/api requests;
  branding + data-truth + titles all intact. No backend code changed (backend stays f36d7c9).
- Known pre-existing (NOT this task, deferred): intermittent ~20% login bounce login->/initialization
  ->/login (client init-gate race; backend /auth/login 200 reliably); Live Ops duplicate React keys.
- No LIMITED_LIVE/FULL_LIVE/signing/broadcast touched. No production deploy/switch.

## Session — Flash multi-chain expansion Steps 1-3 FOUNDATION (2026-06) — DONE, testing-agent verified
Additive, fail-closed, SHADOW/read-only. No signing/broadcast/mode/M3-gate touched;
ARBICORE_MIN_NET_PROFIT_USD stays $35; production untouched. Sandbox has NO EVM RPC (no live claims).
Scope = reusable foundation ONLY (NOT the full multi-strategy universe); Arbitrum strategy work deferred.
- Step 1 (canonical model): NEW `StrategyType` enum (GENERIC_DEX/TRIANGULAR/STABLECOIN/MULTI_HOP/
  LST_LRT/LIQUIDATION/COLLATERAL_DEBT) in models/enums.py; CanonicalOpportunity gains additive
  Optional fields `strategy` + `chain_id` (default None). extra="forbid" intact; legacy rows/round-trip
  unaffected — no schema/API break. Exported from models/__init__.py.
- Step 2 (flash-provider optimizer): NEW scanners/flash_loan_arbitrage/flash_provider_optimizer.py
  (`optimize_flash_provider` + `FLASH_PROVIDER_CONSTRAINTS`). Reuses FLASH_LOAN_PROVIDERS catalog +
  provider_fee_bps. Compares all chain-supported providers, picks cheapest FEASIBLE (fee then deepest
  liquidity). Fail-closed: unknown/unreadable fee, unresolved uniswap_v3 tier, unknown/insufficient
  liquidity, unknown borrow, unsupported chain → DENY. NEVER assumes 0% fee for an unknown-fee provider
  (real 0-bps balancer/morpho allowed). Carries per-provider callback_extra_gas_units. Not yet wired
  into a scanner (foundation only). select_flash_loan_provider left intact.
- Step 3 (ChainGasModel seam): NEW chains/gas_model.py (`ChainGasModel` Protocol + `BaseGasModel`
  pass-through + `get_chain_gas_model` registry). BaseGasModel wraps make_base_all_in_cost_estimator_
  from_env EXACTLY (all 7 kwargs forwarded; None estimator → None DENY). get_chain_gas_model('base')→
  model; arbitrum/ethereum/'' → None (caller fail-closes; NO Base fallback for non-Base). composition.py
  fresh_fn rewired to price Base all-in via the seam — behaviour regression-identical.
- Tests: tests/test_flash_multichain_foundation.py (20) + testing-agent's independent
  tests/test_t1_multichain_foundation_adversarial.py (28) + 111 named Base regression = 159/159 PASS
  (iteration_11). No signing/broadcast in new modules; safety envelope re-confirmed (SHADOW, kill switch
  off, arbicore_secrets empty, no LIMITED_LIVE/FULL_LIVE, $35 gate unchanged).
- Remaining for Arbitrum (next batch, do NOT start until approved): ArbitrumGasModel implementing
  ChainGasModel (NodeInterface/ArbGasInfo L1 security fee) + register in _GAS_MODEL_FACTORIES;
  Arbitrum ChainAdapter (venue/token registry); per-chain provider liquidity reads feeding the
  optimizer; producers that SET strategy/chain_id at emit time; wire optimizer callback_extra_gas_units
  into the gas budget.
- Pre-existing/out-of-scope (deferred): stale admin creds (401) + missing operator user block API-level
  HTTP regression; _worth_m3 signature drift (5 tests in test_spread_widener_watch_edge_t1.py); pytest
  xdist 'no current event loop' cross-file pollution. None touch the new modules.

## PHASE 2 delivered (2026-06) — multi-chain flash-loan expansion (SHADOW, fail-closed)
Safety envelope preserved: SHADOW/read-only, M3 final authority, no signing/broadcast/execution,
ARBICORE_MIN_NET_PROFIT_USD untouched ($35 prod), production untouched. Testing agent iteration_1:
142/142 targeted PASS, 0 critical/minor, retest_needed=false.

### Part A — Opportunity Truth Contract fixed END-TO-END (single boundary)
- NEW arbicore/models/opportunity_contract.py = THE authoritative canonical->display translator.
  server.py `_canonical_opp_to_contract`/`_canonical_opp_to_discovery`/`_opp_economic_state` +
  dashboard deck `_row` now DELEGATE (no drift). ROOT-CAUSE fix: provenance==REAL was used as
  proof of risk/confidence ASSESSMENT -> SAFE 100 / CONF 0 on unassessed REAL rows. Now assessment
  requires a positive score OR an explicit metadata marker (risk_assessed/confidence_assessed) so a
  GENUINE zero survives while an init-default 0.0 renders UNAVAILABLE (null). Economics gained a
  plausibility guard: absurd return (>500%) or uncontextualized large profit (>$100k w/o capital) or
  negative capital are REJECTED to null and SURFACED via `data_quality_flags` (never clamped). USD
  stays USD, return_pct is a real fraction, negatives preserved. Verified live: seeding the exact
  reported symptom (REAL, risk0, conf0, no capital, $48M profit) now yields verdict=UNVERIFIED,
  confidence/safety/profit=null, flags=["uncontextualized_large_profit"].
- Frontend v2/components/Primitives.jsx was ALREADY contract-faithful (null->"—"); no FE change needed.
- Tests: test_phase2_opportunity_truth.py (17) + updated test_data_truth_contract.py.

### Parts B/C/F — chains + gas (Arbitrum, Optimism, Ethereum, Polygon, BNB)
- NEW arbicore/chains/evm_gas.py: reusable EVM all-in gas layer (EvmGasModel + pure helpers
  l2_fee_usd / op_stack_l1_fee_usd / arbitrum_l1_fee_usd). L1 mechanism per chain: op_stack
  (GasPriceOracle 0x42..0F) for Optimism, arbitrum (ArbGasInfo 0x..6C getL1BaseFeeEstimate over
  calldata) for Arbitrum, none for Ethereum/Polygon/BNB. Gas priced in the chain's NATIVE token USD
  (POL/BNB not ETH). Fail-closed: no RPC / missing gas/price/L1/native-USD / gas over safety ceiling
  -> None (DENY). Registered in gas_model.py `_GAS_MODEL_FACTORIES`. BASE UNCHANGED (keeps its own
  BaseGasModel/base_all_in_cost.py; asserted by regression test).
- NEW arbicore/chains/registries.py (verified public token + DEX-factory addresses; NO fabricated
  pools) + evm_adapter.py (one data-driven EvmChainAdapter for all 5 chains; capability() never
  active_ready offline — identity/quote/simulation probed live on VPS). make_chain_adapter dispatch.
- persistent.SUPPORTED_CHAINS += "bnb"; FLASH_LOAN_PROVIDERS aave_v3 += "bnb" (Aave V3 live on BNB).
- Tests: test_phase2_multichain.py (24) incl. fail-closed, pure math, injected-provider estimator,
  Base-regression.

### Parts D/E/G/H — strategy, true economics, provider optimizer, EV ranking
- NEW flash_loan_arbitrage/strategy_tagging.py: classify_strategy (STABLECOIN/LST_LRT/TRIANGULAR/
  MULTI_HOP/GENERIC_DEX) + emit_flash_candidate (sets StrategyType + chain_id at emit; detection-only,
  never fabricates economics). NEW multichain_economics.py: compute_true_net_profit = gross − provider
  fee (actual, via existing optimize_flash_provider) − gas − L1 − slippage; total_gas_units adds
  provider callback_extra_gas_units to route gas (Part B item 6). Fail-closed at every unknown.
- Part H: reused ranking.py (rank_opportunities) + economics/expected_value.py — advisory only, never
  emits GO/executable/broadcast; high-spread/low-execution ranks below modest/high-execution.
- Part I: economic-state ladder (DISCOVERED->LIVE_QUOTED->VERIFIED->ECONOMICALLY_VALID; M3_GREEN = M3
  authority) single-sourced in opportunity_contract. Tests: test_phase2_strategy_economics.py (15).

### Reused (NOT rebuilt): CanonicalOpportunity (StrategyType/chain_id already present),
flash_provider_optimizer, provider_selection, ChainGasModel seam, BaseGasModel, ranking, expected_value,
profit_vector, providers/registry, M3 pre_broadcast (frozen — untouched).

### Env added for validator (were missing on import): backend/.env (MONGO_URL, DB_NAME=arbicore_x,
JWT_SECRET, ARBICORE_ADMIN/OPERATOR creds) + frontend/.env (REACT_APP_BACKEND_URL). See
memory/test_credentials.md. VPS chain-by-chain live validation appended to VPS_VALIDATOR_RUNBOOK.md.

### NOT DONE (requires VPS, genuinely absent offline): live RPC connectivity/route discovery/provider
liquidity/gas/net-profit per new chain; live capability().active_ready. NO live-chain validation was
performed or claimed. Deeper strategy route-builders (triangular/multi-hop enumerators over live pool
graphs) and lending/LST state readers remain thin/deferred (tagging spine + economics in place).

## PHASE 2 · LIVE-VALIDATION + HARDENING STAGE (2026-06) — SHADOW, fail-closed
Public EVM RPCs (publicnode.com) are reachable from the sandbox, so this stage performed GENUINE
live-chain validation (not offline-only). Testing agent iteration_2: 136/136 offline PASS + frontend
anomaly-chip flow verified; 0 issues; retest_needed=false. Safety envelope unchanged (SHADOW, no
signing/broadcast/execution, $35 gate, M3 authority, production untouched).

### Step 1+5 — LIVE-VALIDATED all 5 chains (evidence: /app/reports/phase2_live_validation/*.json)
Harness scripts/phase2_validate_chain.py runs RPC→chainId→token registry(code+decimals)→DEX factory
code→real route discovery (factory.getPool)→real pool depth→provider on-chain liquidity→provider
fee→gas price→L1/security fee→slippage→all-in cost→$35 gate→readiness(executable=false).
  - arbitrum 42161: pools live (WETH/USDC 0.05% = 7378 WETH/$19.3M), Balancer $225k + Aave $47M ON_CHAIN_CONFIRMED, L1 fee via ArbGasInfo, chose Balancer 0bps.
  - optimism 10: Balancer $65k + Aave $5.3M, OP-stack L1 fee.
  - ethereum 1: Balancer $2.9M + Aave $770M, no L1 fee (correct for L1).
  - polygon 137: Balancer $639k + Aave $24M, gas priced in POL; when CoinGecko POL price transiently
    unavailable the gas model correctly FAILED CLOSED (all_in_cost_denied) instead of fabricating.
  - bnb 56: no Balancer (correctly absent) → optimizer chose Aave 5bps ($25 real fee), gas in BNB.

### Step 2 — provider liquidity is REAL (provider_liquidity.py)
On-chain reads: Balancer V2 Vault ERC20.balanceOf; Aave V3 Pool.getReserveData→aToken→balanceOf.
Status ladder CONFIGURED/AVAILABLE/ON_CHAIN_CONFIRMED/UNAVAILABLE/UNKNOWN; feasible_usd is non-None
ONLY when ON_CHAIN_CONFIRMED (≥ borrow). Optimizer minimises total cost (fee+callback+gas); a 0-bps
provider is used only when config-verified (Balancer). 13 offline tests + live confirmation.

### Step 3 — triangular is REAL (triangular.py)
enumerate_cycles + evaluate_cycle (skips any unquotable leg, fail-closed) + discover_triangular
(true net via compute_true_net_profit; emits StrategyType.TRIANGULAR only when net ≥ $35). Live
UniV3QuoteClient (QuoterV2 quoteExactInputSingle) proven on Arbitrum: 12 real cycles priced from live
quotes (1 WETH=2461.8 USDC), all correctly gated out (no fabricated profit).

### Step 4 — data_quality_flags in operator UI (Primitives.AnomalyChips)
Compact amber chip on the opportunities profit cell + drawer header + Overview 'Data quality' section,
with human-readable labels. Backend canonical contract stays authoritative; UI only surfaces its
verdict. Verified: seeded REAL/48M/no-capital row renders UNVERIFIED · CONF — · SAFE — · CAPITAL — ·
PROFIT — + '⚠ UNCONTEXTUALIZED LARGE PROFIT'. Also fixed a pre-existing React key collision on live rows.

### Files added/changed this stage
NEW: scanners/flash_loan_arbitrage/provider_liquidity.py, triangular.py; scripts/phase2_validate_chain.py;
tests/test_phase2_liquidity_triangular.py; reports/phase2_live_validation/*.json. CHANGED:
providers/rpc.py (working public RPC defaults), frontend Primitives.jsx + OpportunitiesPage.jsx +
OpportunityDrawer.jsx (anomaly chip). Base model + M3 + $35 gate UNCHANGED.

### Remaining (VPS): swap public RPCs for private archival RPCs; live triangular over more fee-tiers/pairs;
optional per-chain price oracle so Polygon/BNB gas never fails closed on a transient price outage.
