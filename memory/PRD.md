# ArbiCore X — PRD / Working Memory

## Origin
External GitHub clone (raghugr2013-lgtm/arbicore-x). FastAPI backend `/app/app/backend`,
Solidity `/app/contracts`. Objective: controlled, capital-light Base flash-loan arbitrage.
System MUST remain SHADOW/PAPER until explicit operator approval. No deploy/broadcast/sign.

## Canonical baseline (Phase 0 repo reconciliation)
- `main` is canonical & newest (v2.9.2 + 69 commits ≈ v2.11.x).
- `hotfix/auth-routing` fully merged; `archive-v1` + `feature/ui-v2-slices-0-2` are stale archives.
- No execution/contract code exists off-main. No merge/cherry-pick required.

## Architecture (verified)
- On-chain executor `FlashLoanReceiver.sol`: Aave V3 + Balancer V2 flash; Uniswap V3 SwapRouter02 settlement ONLY.
- Off-chain quoting is multi-venue & real (`eth_call`): UniV3, UniV2, Aerodrome (SlipStream+classic), Curve, Balancer, Jupiter.
- Route graph: `route_search.py` DFS cycle enumerator (max_hops cfg).
- Broadcast: single site `broadcast.py` behind 6-gate ladder. Mode default SHADOW.

## Done — 2026-08-20 (Phase 0 security blockers, verified by testing_agent)
- S1: remediation documented (rotate leaked GitHub token; platform "Save to Github"). NOT auto-modified.
- S2: pipeline kill-switch now uses authoritative `KillSwitchRepo.state()` (was broken `.get()`), denies when engaged.
- S3: `OpportunityPipeline.auto_confirm` default False; auto-executor no longer autonomously confirms broadcasts.
- S4: `/api/arbicore/wizard/technical-validation` now requires operator auth + enforces kill-switch, approved executor, dedicated signer, chain allowlist (Base Sepolia default; mainnet blocked), token allowlist on execute=true.
- S5: `LimitedLiveBroadcaster` binds capital sizing to real gas-wallet balance via injected `WalletBalanceReader`.
- S6: broadcaster `slippage_guard` gate rejects zero/absent `amountOutMinimum` / empty userData on live-capable path.
- Tests: 32/32 (wave7 + new tests/test_phase0_s2_s6_security.py); full regression 96/97 → 97/97 after test update.
- Env bootstrap: created backend/.env (local Mongo, DB_NAME=arbicore_x) + frontend/.env; seeded single admin.

## Executable coverage: still ~30% (unchanged by Phase 0 — safety only).

## Backlog (approved plan, NOT yet implemented — need operator go + live Base RPC infra)
- P0.1 Aerodrome on-chain adapter (SlipStream+classic) + userData/calldata venue tagging + tests.
- P0.2 Adaptive flash-loan size optimizer (grid → max risk-adjusted EV, with max_loss).
- P0.3 Wire live Base pool inventory into route_search.pool_loader + live QuoteProvider into flash-loan verifier (replace noop).
- P0.4 Confidence v2 (multi-factor, explainable) + EV = P(success)*net − P(failure)*max_loss.
- P0.5 Base fork test + historical replay + shadow certification harness.
- Discovery layer (research-only): broad Base venue/token/opportunity indexing (parallel workers, bounded concurrency).
- P1: UniV4, UniV2, Curve, Balancer-swap, safe 0x adapters. P2: cross-chain, CEX/DEX, liquidations, MEV.

## Done — 2026-08-20 (Control/Readiness layer — Phases B, C, F)
- NEW `arbicore/control/readiness.py`: `ExecutionReadinessEngine` (16 component checks → GREEN/YELLOW/RED + per-mode `can_activate`), `ControlStateRepo` (operator mode persistence), operator modes SHADOW/PAPER/PROFIT_ENGINE/LIMITED_LIVE/FULL_AUTOMATION.
- Backend-authoritative mode guard: SHADOW/PAPER/PROFIT_ENGINE allowed (non-broadcast); LIMITED_LIVE + FULL_AUTOMATION HARD-BLOCKED (always refused this build).
- API (all `Depends(_require_operator_dep)`): GET `/api/arbicore/control/readiness`, GET/POST `/api/arbicore/control/mode`. Frontend can only REQUEST; backend decides.
- Tests: NEW `tests/test_control_readiness.py` (9) + `test_phase0_s2_s6_security.py` (15) + wave7 (17) = 41/41. Live curl verified: 401 unauth, LIMITED_LIVE refused, SHADOW applied, overall YELLOW.
- Phase 0 (S2–S6) preserved — no regression.

## Done — 2026-08-20 (P0 profit engines + Control Center UI + Emergency Stop)
- NEW pure engines (deterministic, no RPC): `economics/expected_value.py` (EV=P(s)*net−P(f)*max_loss, evidence-based prob, penalizes missing evidence, caps failed-sim ≤0.10), `economics/size_optimizer.py` (adaptive size grid+refine → max risk-adjusted EV, depth-aware slippage, hard caps), `intelligence/confidence_v2.py` (12-factor explainable 0-100, advisory only — never a gate).
- Readiness integration: CONFIDENCE_ENGINE/EV_ENGINE/SIZE_OPTIMIZER now GREEN components; LIMITED_LIVE/FULL_AUTOMATION stay hard-RED.
- NEW endpoint `GET /api/arbicore/control/profit-preview` (data_source=SAMPLE_PARAMETERS, shadow-safe). Mode POST now returns 400 for unknown mode.
- NEW frontend `v2/pages/ControlCenterPage.jsx` (+route `control/*`, nav 'CONTROL'): overall + per-component GREEN/YELLOW/RED, mode cards with blockers/warnings/requirements, LIMITED_LIVE/FULL_AUTOMATION visibly LOCKED, persistent Emergency Stop wired to authoritative kill switch. Frontend cannot bypass backend.
- Fixed stale `REACT_APP_BACKEND_URL` (undefined/api 404s) via frontend restart.
- Tests: NEW `tests/test_p0_profit_engines.py` (12). testing_agent iteration_2: 53/53 backend, frontend 100%, no critical/high; kill-switch broadcast Gate-1 denial verified; Phase-0 preserved. Left kill switch DISENGAGED.

## Still NOT built (need live Base RPC / Solidity toolchain — honest backlog)
- P0-3 Aerodrome on-chain adapter; P0-4 real Base liquidity/quote wiring (verifier still noop-capable); P0-5 live route-graph data; P0-10 full on-chain sim gate; P0-11 fork tests + historical replay; shadow certification RUN.

## Done — 2026-08-20 (P0 decision layer + read-only Base live quotes)
- NEW endpoint `POST /api/arbicore/control/decide-opportunity` (auth, SHADOW/PAPER-safe): composes net_profit → confidence v2 → expected value → adaptive size optimizer behind a HARD simulation gate; returns advisory decision only (execution_performed=false). Kill switch engaged OR non-shadow-safe mode force would_execute=false (safety overrides can only make a decision LESS executable). Confidence/EV can NEVER bypass a failed gate.
- NEW `economics/opportunity_decision.py` wiring finalized + exposed. Accepts operator `opportunity` OR live `route`+`economics`.
- P0-4 read-only Base quotes WIRED via public RPC `ARBICORE_RPC_URL=https://mainnet.base.org` (read-only eth_call only; no signer/broadcast). NEW `POST /api/arbicore/control/live-quote` wraps existing `QuoterRegistry` (UniV3 + Aerodrome SlipStream/classic) with authoritative freshness: REAL/STALE/UNAVAILABLE.
- NEW pure seam `economics/quote_provider.py`: turns a live cyclic RouteQuote into the decision opportunity (realized on-chain gross-spread only when quote REAL + cyclic — never fabricated), maps dex→router, builds genuine UNSIGNED userData via existing calldata encoder so the sim-gate calldata check is real. Verified live: WETH→USDC→WETH round-trip = -9 bps (no arb right now) → correctly rejected.
- Readiness now: CONFIGURATION 'ARBICORE_RPC_URL set' (YELLOW: no executor addr — correct), SIMULATION GREEN (eth_call preflight). LIMITED_LIVE/FULL_AUTOMATION STILL can_activate=false (RPC alone does NOT unlock live modes); overall YELLOW.
- Tests: NEW `tests/test_p0_decide_opportunity.py` (19) + `tests/test_p0_live_quote_provider.py` (12). Combined P0/control regression 67/67. testing_agent iteration_3 (19/19) + iteration_4 (31/31) — 100%, no critical/high. Kill switch left DISENGAGED, mode SHADOW.
- Aerodrome on-chain SOLIDITY adapter (P0-3) + fork tests (P0-11): still BLOCKED — public RPC insufficient for fork harness; no signing/deploy permitted this build. Off-chain Aerodrome QUOTING already works via QuoterRegistry.

## Done — 2026-08-20 (Autonomous Opportunity Engine + dynamic sizing + continuous scanner)
- NEW `arbicore/discovery/base_venues.py`: verified Base token universe (WETH,USDC,cbETH,DAI,USDbC,cbBTC,AERO — all on-chain `symbol()`-checked) + venue graph feeding the existing `RouteSearchEngine`.
- NEW `arbicore/economics/opportunity_engine.py`: `OpportunityEngine` (discovery→live quote→full decision chain, REUSING RouteSearchEngine + QuoterRegistry + decision engines) covering cross-DEX, same-DEX fee-tier, triangular, stablecoin-triangular, multi-hop cycles. `ContinuousScanner` = always-on read-only loop (auto-starts on boot, 90s interval), operator can stop/start.
- DYNAMIC size optimizer: `_measure_liquidity` derives EFFECTIVE pool depth LIVE from the multi-size quote curve (slope→liquidity), fed to the size optimizer. Depth probe runs only for competitive routes (marginal spread ≥ threshold); conservative default otherwise. LIQUIDITY_DEPTH matrix row now GREEN.
- NEW `arbicore/data/decision_history.py`: `DecisionHistoryRepo` (evidence: quote/freshness/route/liquidity/provider/size/gross-net/costs/confidence/EV/sim/decision/reason + `checkpoint()` aggregation) + `RouteRecurrenceRepo` (recurring-route signal).
- NEW endpoints (all operator-auth): POST `/engine/scan-once`, GET `/engine/opportunities`, GET `/engine/history`, GET `/engine/recurring`, GET `/engine/checkpoint`, POST `/engine/scanner/start|stop`, GET `/engine/scanner/status`, GET `/engine/readiness-matrix`. Startup hook `_autostart_opportunity_scanner` (gated on ARBICORE_RPC_URL + ARBICORE_SCANNER_AUTOSTART!=0).
- Modes backend-authoritative (NOT hardcoded): SHADOW/PAPER/PROFIT_ENGINE can_activate=true; LIMITED_LIVE/FULL_AUTOMATION can_activate=false. Overall RED due to genuine LIMITED_LIVE prerequisites.
- Honest state: NO profitable arbitrage on Base at this time → every route correctly rejected (`positive_after_costs`=0); engine never fabricates. Evidence accumulating (270+ records, 37 REAL quotes across 3 auto-scans).
- Tests: NEW `tests/test_p0_opportunity_engine.py` (12). Combined P0/control regression 79/79. testing_agent iteration_6 100% (22/22), no critical/high. Kill switch DISENGAGED, mode SHADOW, scanner RUNNING.

## Remaining exact blockers for LIMITED_LIVE (from readiness matrix)
- WALLET_GAS (USER): register a funded Base gas/execution wallet (operator wizard).
- SIGNER (USER): provision an isolated execution signer key (never hardcoded).
- EXECUTOR_CONTRACT (USER): deploy/allowlist FlashLoanReceiver, set ARBICORE_EXECUTOR_ADDRESS_BASE.
- DEX_ADAPTERS_SETTLE (ENGINEERING): complete allowlisted Aerodrome on-chain settlement adapter + tests.
- SIMULATION_ONCHAIN (ENGINEERING): add state-override sim (tenderly/anvil) for exact revert modelling.
- FORK_VALIDATION (USER): provision archive/trace RPC or local anvil --fork-url (public RPC cannot host a fork).
- HISTORICAL_REPLAY (ENGINEERING): block-pinned replay over Decision History once archive RPC exists.

## Done — 2026-08-20 (Opportunity Factory: widened coverage + funnel + Live Ops UI + alerts)
- WIDENED universe: 12 verified Base tokens (WETH,USDC,cbETH,DAI,USDbC,cbBTC,AERO,USDT,rETH,wstETH,weETH,DEGEN — all on-chain checked), 31 venues (UniV3 fee tiers, Aerodrome SlipStream+classic), ~134-route candidate universe; borrow tokens WETH/USDC/cbETH/USDbC.
- MARKET-COVERAGE FUNNEL on every scan + cumulative: candidate_universe → routes_quoted → real_quotes → quote_failures/stale → liquidity_measured(live) → negative_economics → positive_net → positive_ev → simulation_candidates → simulation_passes → executable. ContinuousScanner rotates the scan window across the universe.
- PROFIT ALERTS (`ProfitAlertRepo`, GET /engine/alerts): fire ONLY on full-chain pass (real quote→net→confidence→EV→size→simulation→would_execute), never on raw spread.
- SECURE ONBOARDING (GET /engine/onboarding): checklist for gas wallet / signer / executor / archive RPC — reports PRESENCE only, never accepts or echoes secrets.
- NEW Live Ops Control Center UI `/dashboard/live-ops` (`v2/pages/LiveOpsPage.jsx`, nav 'Live Ops'): scanner status, funnel, top opportunities, rejection reasons, alerts, RED/YELLOW/GREEN matrix, LIMITED_LIVE blockers, onboarding; Scan-Now / Start / Stop controls. Backend-authoritative; SHADOW-safe.
- Tests: test_p0_opportunity_engine.py now 16. testing_agent iteration_7: backend 100% (10/10), frontend 100% (all testids + Scan-Now flow). Only OPTIONAL cosmetic note (funnel key naming). Scanner RUNNING, kill switch DISENGAGED, mode SHADOW.
- Live checkpoint: universe 134; 642 evidence records, 123 REAL quotes; positive=0/executable=0/alerts=0 (NO real arb currently — honest). Overall readiness RED (genuine LIMITED_LIVE prerequisites outstanding).

## Done — 2026-08-20 (Quote-failure categorization + RPC throttle/retry — coverage fix)
- ROOT-CAUSE of low REAL-quote coverage identified: the FREE public RPC (mainnet.base.org) returns `-32016 over rate limit` for the majority of hops — NOT missing pools. Corrected the market-coverage narrative accordingly (we only prove "no profitable opp among REAL-quoted routes", never a universal "no arbitrage").
- FIX: `quoter._eth_call` now has a global client-side throttle (min-interval, env ARBICORE_RPC_MIN_INTERVAL_MS=140) + retry-with-exponential-backoff on rate-limit (-32016 / HTTP 429). Dropped the wasteful per-hop extra round-trip risk; `getattr(r,'status_code',200)` keeps test stubs working.
- CATEGORIZATION: `categorize_quote_failure()` buckets every non-REAL route into rate_limited / revert_no_pool / no_adapter / rpc_error / other. Surfaced in `scan_once` funnel `quote_failure_reasons` and cumulatively in scanner `funnel_cumulative.quote_failure_reasons`. Per-opportunity `quote_failure_category` added.
- Verified: testing_agent iteration_8 backend 100% (11/11), no critical/high. Quoter unit tests 18/18. Kill switch DISENGAGED, mode SHADOW, scanner RUNNING.
- HONEST LIMITED_LIVE readiness (still RED): rate_limited dominates failures → real fix is a dedicated RPC (USER). weETH/500 = genuine revert_no_pool.

## LIMITED_LIVE blocker matrix (2026-08-20, authoritative)
- LIQUIDITY_DEPTH: GREEN (live quote-curve-derived effective depth into size optimizer).
- QUOTE_FAILURE_CATEGORIZATION: GREEN (rate_limited/revert_no_pool/rpc_error buckets live).
- WALLET_GAS: RED/YELLOW — USER: register+fund Base gas wallet.
- SIGNER: YELLOW — USER: provision isolated signer/KMS (never pasted/stored in app).
- EXECUTOR_CONTRACT: YELLOW — USER: deploy+allowlist FlashLoanReceiver, set ARBICORE_EXECUTOR_ADDRESS_BASE.
- DEX_ADAPTERS_SETTLE (Aerodrome on-chain settlement): YELLOW — ENGINEERING: build allowlisted settlement encoder (not started; honestly not claimed).
- SIMULATION_ONCHAIN (state-override sim): YELLOW — ENGINEERING: add tenderly/anvil state-override (public RPC lacks reliable override support).
- FORK_VALIDATION: RED — USER: archive/trace RPC or local anvil --fork-url (public RPC cannot host a fork).
- HISTORICAL_REPLAY: YELLOW — ENGINEERING: block-pinned replay (needs archive RPC first).
- RPC_THROUGHPUT: YELLOW — USER: dedicated RPC (Alchemy/QuickNode) to eliminate rate_limited failures and lift REAL coverage.

## Done — 2026-08-20 (Aerodrome on-chain settlement adapter — DEX_ADAPTERS_SETTLE GREEN)
- NEW `arbicore/execution/aerodrome_settlement.py`: `AerodromeSettlementAdapter` produces REAL ABI-encoded `swapExactTokensForTokens(uint256,uint256,(address,address,bool,address)[],address,uint256)` calldata for later simulation. Verified constants: AERODROME_ROUTER 0xcF77…4E43 + AERODROME_POOL_FACTORY 0x420D…40Da (both confirmed to carry on-chain bytecode).
- STRICT allowlisting: only the allowlisted Aerodrome router is a permitted target (no arbitrary contract execution); every hop token must be allowlisted; multi-hop chaining enforced; stable/volatile per hop. Returns signed=false/broadcast=false — NEVER signs or broadcasts.
- Readiness: DEX_ADAPTERS_SETTLE now keyed off `AerodromeSettlementAdapter().self_test()` — flips GREEN only after the encoder genuinely produces well-formed calldata (selector + payload validated). Verified GREEN live.
- Tests: NEW `tests/test_p0_aerodrome_settlement.py` (7): real calldata, multi-hop, allowlist + arbitrary-target rejection, self_test. testing_agent iteration_9 backend 100%, no critical/high. Kill switch DISENGAGED, mode SHADOW, scanner RUNNING, LIMITED_LIVE locked, overall RED.
- NOT done this turn (honest, blocked/needs infra): SIMULATION_ONCHAIN state-override (needs anvil/tenderly), FORK_VALIDATION (needs archive/anvil fork RPC), HISTORICAL_REPLAY (needs archive RPC), dedicated RPC (awaiting USER). Reported YELLOW/RED — not faked.

