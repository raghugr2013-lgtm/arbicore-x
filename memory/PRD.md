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

