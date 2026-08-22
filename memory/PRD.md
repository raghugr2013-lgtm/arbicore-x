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

## Done — 2026-08-20 (Settlement simulation + verified RPC capabilities + historical replay)
- VERIFIED (not assumed) public-RPC capabilities via probe: state_override=TRUE, archive_state=TRUE, trace=FALSE. Endpoint GET /engine/rpc-capabilities.
- NEW `arbicore/execution/settlement_simulator.py`: read-only E2E Aerodrome settlement simulation (borrow → swap(s) → repayment → net profit) via router `getAmountsOut` real eth_call, reusing the allowlisted encoder. Block-pinned `replay(block_number=…)` (archive verified). Failed sim = absolute rejection. signed/broadcast=false. Endpoint POST /engine/simulate-settlement (+ block_number for replay). Verified live: WETH→USDC→WETH at block 50218031 correctly REJECTED (loses to fees).
- Readiness upgrades (verified): SETTLEMENT_SIMULATION GREEN, RPC_STATE_OVERRIDE GREEN, HISTORICAL_REPLAY GREEN. FORK_VALIDATION now YELLOW (archive verified, but no controllable fork — needs anvil/dedicated). SIMULATION_ONCHAIN YELLOW (atomic executor sim needs executor contract). Overall YELLOW; LIMITED_LIVE.can_activate=false.
- Tests: NEW test_p0_settlement_simulator.py (5) + test_p0_aerodrome_settlement.py (7). testing_agent iteration_10 backend 100% (10/10 integration + 12/12 unit). Kill switch DISENGAGED, mode SHADOW, scanner RUNNING.

## PHASE A SIGN-OFF — 2026-08-21 (pre-VPS-deploy verification PASSED)
- Regression: 102/102 pytest PASS. Security: all `/api/arbicore/*` protected endpoints 401 to anon; no secret leaks (private_key/signed_tx/raw_tx/eth_send*/personal_sign) in any response. Mode/readiness: overall YELLOW, SHADOW active, LIMITED_LIVE=false + FULL_AUTOMATION=false (operator-gated); 24 GREEN / 1 YELLOW (SIMULATION_ONCHAIN) / 0 RED. Recent-block Anvil fork mechanics proof: ran=true/passed=true (Base @ 50258580; chainId+executor-code+state-override). BUILD DECLARED READY FOR VPS DEPLOYMENT.
- VPS NOTE: the `/usr/local/bin/anvil` symlink is NOT persistent in the ephemeral Emergent preview — on the VPS, Foundry/anvil must be installed and on the service PATH or FORK_VALIDATION won't be GREEN there. Secrets (signer vault key, ARBICORE_ARCHIVE_RPC_URL, ARBICORE_ETHERSCAN_API_KEY, VAULT_KEY) must be re-provisioned on the VPS — they never travel in code/chat.

## RESOLVED — 2026-08-21 (Execution alignment: engine route model ↔ deployed executor)
- Every opportunity now carries `execution_capability`: **EXECUTABLE_UNIV3** (all-Uniswap-V3 routes the deployed executor can run) or **NON_EXECUTABLE_BY_CURRENT_EXECUTOR** (any Aerodrome/slipstream/mixed route — discoverable for intelligence, NEVER marked executable). `_execution_capability()` + `_univ3_swaphops()` in opportunity_engine; evaluate_route hard-gates non-UniV3 routes to would_execute=False before the atomic gate.
- Atomic gate rewired: `_atomic_sim_runner` now encodes the executor's REAL `execute(address[],uint256[],bytes)` + `userData=abi.encode(SwapHop[],profitRecipient)` (Balancer flash → UniV3 swaps → repay) via `calldata.py` (was Aerodrome). Only EXECUTABLE_UNIV3 routes that pass all gates + a passing atomic sim can be would_execute=true.
- Live scan-once (current market): 7 EXECUTABLE_UNIV3 / 3 NON_EXECUTABLE; would_execute=0 (honest — no profitable route; decision/simulation gate fails on repayment). No fabricated profit.
- Controlled-fork validation (distinct from live profit): anvil forks Base, verifies chainId + executor-code + state-override → FORK_VALIDATION GREEN. Live atomic sim vs deployed executor executes end-to-end and reverts (economics; no arbitrage) → SIMULATION_ONCHAIN stays YELLOW.
- Executor-abi endpoint hardened with last-good getter cache (public-RPC cold-call flakiness). testing_agent iter18: **106/106 (99 regression + 7 endpoint) PASS**, no critical.
- FINAL matrix: **24 GREEN / 1 YELLOW (SIMULATION_ONCHAIN) / 0 RED**; overall YELLOW; SHADOW; scanner RUNNING; LIMITED_LIVE + FULL_AUTOMATION locked.
- REMAINING before LIMITED_LIVE (manual, operator-gated): a genuinely profitable EXECUTABLE_UNIV3 route must pass the full pipeline + atomic sim (needs real market spread ≥ costs, or a dedicated low-latency RPC to catch fleeting spreads). Everything else is verified GREEN.

## RESOLVED — 2026-08-21 (Executor ↔ ArbiCore integration: real ABI recovered from source)
- Found the deployed executor SOURCE in-repo: `contracts/contracts/core/FlashLoanReceiver.sol` (+ `adapters/UniswapV3Adapter.sol`). Recovered the EXACT schema (not guessed):
  - **Entrypoint = `execute(address[] tokens, uint256[] amounts, bytes userData)`** selector `0x64ba4bc1` (Balancer V2 flash). Alt: `executeAave(address,uint256,bytes)`. `onlyOwner`; owner = `0x998d…ad25` = our vault signer.
  - **userData = `abi.encode(SwapHop[] hops, address profitRecipient)`**, `SwapHop=(address tokenIn,address tokenOut,uint24 feePpm,uint256 amountIn,uint256 amountOutMinimum,uint160 sqrtPriceLimitX96)`. amountIn=0 ⇒ forward prior hop output.
  - Venues: **Uniswap V3 SwapRouter02 swaps** (`exactInputSingle`) + flash from **Balancer V2 Vault** (0-fee) or **Aave V3** (5bps). NOT Aerodrome.
  - Earlier bytecode selector `5c38449e`=`flashLoan(...)` is the INTERNAL call to Balancer's Vault, not the entrypoint (corrected).
- Encoder already existed in-repo (`arbicore/execution/calldata.py`: `encode_executor_execute` + `build_user_data_from_hops`) — rewired `_run_live_atomic_sim` to use it (was wrongly using the Aerodrome `executeArbitrage` encoder). New `GET /api/arbicore/engine/executor-abi` documents the recovered ABI from on-chain inspection.
- Atomic sim now runs the REAL path (Balancer flash → UniV3 hops → repay) against the deployed executor: available=true, signed/broadcast=false, reverts (no live arbitrage → cannot repay; public RPC returns no revert-data). SIMULATION_ONCHAIN kept YELLOW (never GREEN on a revert).
- ANVIL installed (1.7.1, /usr/local/bin) + `ARBICORE_ARCHIVE_RPC_URL` set (public Base RPC, not a secret). Genuine fork validation runs at boot + on demand: forks Base, verifies chainId + executor-has-code + state-override on the fork → ran=true, passed=true. **FORK_VALIDATION now GREEN** (evidence-based).
- FINAL matrix: **24 GREEN / 1 YELLOW (SIMULATION_ONCHAIN) / 0 RED**; overall YELLOW; SHADOW; scanner RUNNING; LIMITED_LIVE + FULL_AUTOMATION can_activate=false. testing_agent iter17 + fix: 75/75 regression + endpoint suite pass.
- REMAINING BLOCKERS: (1) SIMULATION_ONCHAIN — needs a genuinely profitable UniV3 route (or controlled fork state) so the flash loan repays with profit; (2) ENGINE ROUTE MODEL — the live opportunity engine still emits Aerodrome-settlement routes, which THIS executor cannot run (UniV3-only). Aerodrome routes are NOT marked executable (atomic gate blocks them), but to actually execute, the engine's route encoding must be aligned to the executor's UniV3 `SwapHop[]` format.

## RCA — 2026-08-20 (Deployed executor ABI inspected; SIMULATION_ONCHAIN root cause)
- Inspected deployed executor `0x91c0bf28…4f3DE3` bytecode (6664 bytes) via `inspect_executor()` (READ-ONLY: eth_getCode + getter eth_calls). New endpoint `GET /api/arbicore/engine/executor-abi`.
- VERIFIED entrypoint (from bytecode selectors, NOT guessed): **`flashLoan(address,address[],uint256[],bytes)`** (selector 5c38449e). Architecture: **Balancer V2 flash loans** (`receiveFlashLoan` f04f2707) + **Uniswap V3 SwapRouter02 swaps** (`exactInputSingle` 04e45aaf); `owner()`-gated (owner = `0x998d…ad25` = our signer/gas wallet); admin `sweep(address,address,uint256)`. Getters read live: owner/ROUTER(UniV3 SwapRouter02)/VAULT(Balancer).
- ROOT CAUSE of SIMULATION_ONCHAIN revert = **calldata/ABI mismatch**: the engine builds an Aerodrome-router settlement wrapped in a guessed `executeArbitrage(address,uint256,address,bytes)` (selector NOT present on the contract), whereas the real executor is Balancer+UniV3 with a `bytes userData` route schema decoded internally. Owner-gate is satisfied; it is NOT an economics failure. The public Base RPC DOES return Error(string) data (verified via USDC), so the executor's bare/no-data revert = require/custom-error inside the userData decode.
- `bytes userData` layout is NOT recoverable from bytecode/ABI alone → a genuinely valid end-to-end tx cannot be constructed without the executor's SOURCE/ABI (userData struct). SIMULATION_ONCHAIN kept YELLOW (no GREEN on a revert). Did NOT change the gate to obtain GREEN, did NOT set ARBICORE_EXECUTOR_ENTRYPOINT_SIG to a value the engine can't yet encode args for.
- REMAINING to pass SIMULATION_ONCHAIN (ENGINEERING, needs operator input): provide the executor source/ABI (the `userData` route encoding for `flashLoan`/`receiveFlashLoan`) so the engine can build a valid flashLoan(...) tx; then re-run `POST /engine/run-atomic-sim`.

## Done — 2026-08-20 (Signer activated: SIGNER GREEN, atomic sim run vs deployed executor)
- Operator stored the execution signer in the vault (via generic secrets path → doc lacked `derived_address`). Added self-healing `ensure_signer_address()` (startup hook + GET settings/signer) that derives + backfills the PUBLIC address WITHOUT exposing the key.
- Signer verified end-to-end: derived address = `0x998d6efF2b28b72c44f7a334c42678eb4cCaad25` = configured gas/execution wallet, matches_expected=true, key never leaked (testing_agent iter16 confirmed no 64-hex/private_key/signed_tx/raw_tx in any payload).
- Readiness updated & consistent across BOTH surfaces: SIGNER/WALLET_SIGNER GREEN, WALLET_GAS GREEN, ATOMIC_EXECUTOR_SIM GREEN. Aligned control `_wallet` green-logic with the matrix (requires address match). Capped control `overall_status` at YELLOW while LIMITED_LIVE is locked (fixes control=GREEN vs matrix=YELLOW discrepancy).
- NEW `POST /api/arbicore/engine/run-atomic-sim` + `_run_live_atomic_sim`: runs the atomic executor state-override sim against the DEPLOYED executor with the vault signer (representative WETH→USDC→WETH). Result: available=true (deterministic eth_call executed), passed=false ("executor reverted" — route unprofitable and/or executor entrypoint ABI unconfirmed); signed=false, broadcast=false. `atomic-sim-status` now signer-aware (atomic_sim_ready=true) + returns live_run.
- SIMULATION_ONCHAIN honesty: GREEN only on a PASSING sim; currently YELLOW (executed-but-reverted) — no fake GREEN. Matrix now 23 GREEN / 2 YELLOW (SIMULATION_ONCHAIN, FORK_VALIDATION) / 0 RED.
- Anvil fork validation run: `POST /engine/run-fork-validation` → ran=false, "anvil binary not installed" (honest). FORK_VALIDATION stays YELLOW.
- SHADOW running; LIMITED_LIVE + FULL_AUTOMATION remain can_activate=false (NOT auto-activated). testing_agent iter16 + regression 64/65 (1 flaky RPC test) PASS.
- REMAINING BLOCKERS: (1) SIMULATION_ONCHAIN — confirm the deployed executor's entrypoint ABI (env `ARBICORE_EXECUTOR_ENTRYPOINT_SIG`) and/or supply a profitable route so the atomic sim PASSES; (2) FORK_VALIDATION — install `anvil` (Foundry) + provide `ARBICORE_ARCHIVE_RPC_URL`.

## Done — 2026-08-20 (Wallet & Capital Intelligence Engine — READ-ONLY, verified)
- NEW `arbicore/capital/wallet_intelligence.py` (`WalletIntelligenceEngine`) + `/api/arbicore/capital/*` endpoints (operator-auth, SHADOW-safe, public addresses only — NEVER reads/logs/returns private keys):
  - `GET /capital/balances` — live native ETH + ERC-20 (Base universe, parallelized `balanceOf`), gas balance, USD, block, last_sync. Reuses `WalletBalanceReader` + `TOKENS`.
  - `GET /capital/statement` — transaction statement (ts, block, hash, direction, token, amount, gas, fee, P/L, status) with DEX venue/method classification (router allowlist + flash-loan providers). Source = Etherscan V2 (Base chainid 8453) via optional `ARBICORE_ETHERSCAN_API_KEY`; degrades gracefully (honest `source_ok=false` + note) when key absent.
  - `GET /capital/money-trail?tx_hash=` — reconstructs borrow→swaps→repay from ERC-20 legs; net-by-token + realized P/L.
  - `GET /capital/reconciliation` — start + inflows − outflows − fees = end (native ETH identity); reports `residual` + `reconciled` + `statement_complete`.
  - `GET /capital/venue-stats`, `GET /capital/wallets`, `GET /capital/overview` (composite).
  - Perf: 45s TTL cache (`_cached`) + concurrent ERC-20 reads → overview ~6s, balances ~11s (was ~46s).
- NEW frontend `v2/pages/CapitalIntelligencePage.jsx` at `/dashboard/capital` (+ nav 'Capital' entry, AppShell route). Panels: live balances, capital reconciliation, transaction statement (filters: type/venue/status), flash-loan money trail, per-venue/pair stats. Parallel `Promise.allSettled` fetches, 90s timeouts, independent panel state, full data-testid coverage.
- Tests: `tests/test_p0_capital_intelligence.py` (5 — reconciliation identity, classification, money-trail net) PASS. testing_agent iter14 (backend + UI) + iter15 (frontend retest) → 100% frontend, no leaks, balance 0.00417963 ETH ($10.45) reconciled residual 0.
- OPERATOR ACTION (optional, improves coverage): set `ARBICORE_ETHERSCAN_API_KEY` (free Etherscan V2 key, Base chainid 8453) to populate the full transaction statement + money trail. Balances + reconciliation work without it.

## Done — 2026-08-20 (Readiness reconciliation — two surfaces now agree, evidence-based)
- Root cause: Control Center (`/arbicore/control/readiness`, `ExecutionReadinessEngine`) and Live Ops (`/engine/readiness-matrix`) were independent; Control had stale/divergent checks.
- `control/readiness.py` fixes: `_wallet` (WALLET_SIGNER) now requires gas wallet (registry OR env) AND vault signer (evm_sign handle + address match) → honest YELLOW with exact missing requirement; `_contracts` (CONTRACTS) now checks the real Aerodrome adapter `self_test` (stale "not implemented" warning removed → GREEN); `_shadow_validation` is status-aware from the cert repo (RUNNING→YELLOW progress, PASS→GREEN, infra-only labeled); LIMITED_LIVE blocker text corrected.
- Gas wallet `0x998d6efF2b28b72c44f7a334c42678eb4cCaad25` (funded 0.00418 ETH, verified on-chain) auto-registered in WalletRegistry with `gas` role (`_register_env_gas_wallet` startup hook, wallet_id `base-gas-primary`).
- `VAULT_KEY` rotated to a VALID Fernet key (was an invalid dev placeholder that would have broken signer ingestion; `arbicore_secrets` was empty so no orphaned ciphertext).
- Shadow-cert runner ENABLED (`ARBICORE_SHADOW_CERT_ENABLED=true`, 15s cycle); a canonical 20-cycle infrastructure-only certification completed PASS → SHADOW_VALIDATION GREEN with genuine evidence.
- **WALLET_SIGNER remains YELLOW** — exact missing requirement = the execution signer key in the vault (gas wallet IS registered ✓). Both surfaces now consistent: WALLET_GAS/DEX_ADAPTERS_SETTLE/CONTRACTS GREEN, SIGNER/WALLET_SIGNER YELLOW, overall YELLOW, LIMITED_LIVE + FULL_AUTOMATION locked. testing_agent iter13: 71/71 PASS.

## Done — 2026-08-20 (Secure signer ingestion + mandatory atomic gate + real Anvil fork body)
- NEW `arbicore/execution/signer_vault.py`: operator-only signer ingestion — derives address (eth_account), verifies vs gas wallet, stores Fernet ciphertext + handle ONLY (never echoes/logs the key). Endpoints `POST/GET/DELETE /api/arbicore/engine/settings/signer`. Single active signer.
- Opportunity chain now MANDATORY end-to-end: discovery → quote → economics → confidence → EV → size → settlement calldata → settlement sim → **atomic executor sim** → net profit → decision (`_atomic_sim_runner` wired as `_OPPORTUNITY_ENGINE._atomic_runner`; unavailable signer → not executable, honest).
- `AnvilForkHarness.run_fork_validation` = real anvil subprocess orchestration (spawn `--fork-url`, poll, run read-only checks, teardown); `ran=false` when anvil/archive-RPC absent (no fake GREEN). Endpoint `POST /api/arbicore/engine/run-fork-validation`.
- testing_agent iter12: 13/13; full P0 regression 39/39.

## Done — 2026-08-20 (Executor entrypoint calldata + atomic sim + Anvil fork harness — verified)
- NEW `arbicore/execution/executor_entrypoint.py`: `build_executor_entrypoint_calldata()` encodes UNSIGNED `executeArbitrage(address,uint256,address,bytes)` entrypoint wrapping the allowlisted Aerodrome settlement calldata (flash borrow→swaps→repay); selector = keccak(sig)[:4]; signed/broadcast always false. `AnvilForkHarness` = ready-to-run fork validator, gated on `anvil` binary + `ARBICORE_ARCHIVE_RPC_URL`; NEVER returns passed=True without a real run (no fake GREEN).
- `atomic_executor_sim.AtomicExecutorSimulator.simulate_atomic` triple-gated (rpc→executor address→signer_present) BEFORE any eth_call → stays available=false while signer absent, regardless of bytecode. code-injection self-test verified true on public Base RPC.
- NEW endpoints (operator-auth): GET `/engine/fork-status`, POST `/engine/build-executor-calldata`; existing GET `/engine/atomic-sim-status`. Server wires `_ATOMIC_SIM` at module load.
- Tests: NEW `tests/test_p0_executor_entrypoint.py` (3) + testing_agent `tests/test_p0_iter12_executor_endpoints.py` (10 live). testing_agent iteration_12: 13/13 new (100%), no critical/high, no signing/broadcast leaks. Fixed 3 STALE env-drift assertions (executor address now set → executor_address_set=true; atomic sim signer-gated first). Full P0 regression 39/39 green.
- FINAL readiness snapshot: 20 GREEN / 5 YELLOW / 0 RED; overall YELLOW; mode SHADOW; scanner RUNNING; LIMITED_LIVE + FULL_AUTOMATION can_activate=false (correct lock).
- YELLOW (honest, no fake GREEN): SIGNER (USER: no vault handle), ATOMIC_EXECUTOR_SIM (USER: needs signer+entrypoint; executor deployed + state-override verified), SIMULATION_ONCHAIN (USER: same signer gate), FORK_VALIDATION (USER: archive verified but no controllable fork — needs anvil + archive/trace RPC). SCANNER auto-restarts when running.
- Remaining USER secrets (NOT chat): (1) execution signer key → encrypted vault → unblocks SIGNER+ATOMIC_EXECUTOR_SIM+SIMULATION_ONCHAIN; (2) dedicated Alchemy Base RPC → removes rate-limit fragility, lifts REAL quote coverage; (3) archive/fork RPC + anvil → unblocks FORK_VALIDATION.
- Remaining ENGINEERING (post-secrets): wire real fork exec in `AnvilForkHarness.run_fork_validation` once anvil+archive RPC land; run full `simulate_atomic` through deployed executor once signer present.

## Done — 2026-06 (Atomic-sim diagnostics A + B — diagnosis/parity only, NO execution changes)
- **B**: `POST /engine/run-atomic-sim` returns full replay `artifact` (executor, entrypoint, selector, from, borrow token/amount, flash_vault, settlement_target, tokens, amounts, hops w/ fee_ppm+amountOutMin+sqrtLimit, userData, profit_recipient, calldata_hex) + `execution_context`. Never echoes private key / vault material / RPC URL.
- **A**: `POST /engine/run-atomic-sim` accepts optional `{block_number, fork_rpc}`. `block_number` prefers a LOCAL anvil fork (new `anvil_fork()` async ctx mgr in executor_entrypoint.py), falls back to archive-RPC historical eth_call `hex(block)`. `fork_rpc` runs against an operator fork endpoint. All READ-ONLY; signed/broadcast always false.
- Honest semantics preserved: only `live_rpc_latest` PASS updates `_ATOMIC_LIVE_RUN`/SIMULATION_ONCHAIN. Block-pinned/fork runs stored in `_ATOMIC_DIAG_RUN` (`diagnostic=true`) and NEVER flip the live matrix (rule 6/7 honored).
- Verified live: B artifact returns correct calldata (selector 0x64ba4bc1, settlement UniV3 SwapRouter02, flash Balancer V2 Vault, no secret leak); A local-anvil-fork path `mode=block_pinned_anvil_fork fork_block=50218031`; archive fallback `mode=block_pinned_archive_rpc`. Tests: A/B + calldata + execution-capability + atomic-gate 75/75 PASS.
- TRUTH re-confirmed from tests+history: atomic sim NEVER passed in Emergent (iter16/17/18 assert passed=False, SIMULATION_ONCHAIN=YELLOW). VPS reproduces Emergent exactly — no parity bug. Revert = deterministic economics (same-tier round trip loses fees, cannot repay 0-fee Balancer loan). 0 profitable fixtures in evidence (alerts=0, executable=0).
- Preview-only test contradiction documented in `/app/memory/atomic_sim_diagnostics.md`: older tests assume anvil ABSENT, newer assume PRESENT; VPS has anvil so iter17/18 are authoritative. Not a code regression.

## Done — 2026-06 (VPS non-destructive deployment runbook — operator-confirmed facts)
- Operator confirmed authoritative prod DB: `factory-mongo` (Mongo 7.0.39) → `arbicore_x`, volume `factory-mongo_factory_mongo_data`, target `factory-mongo:27017`. `arbicore-x-mongo` (Mongo 4.4) is NON-authoritative — never switch/migrate to it.
- Preserve exactly (no rotation/change): `VAULT_KEY`, `MONGO_URL`, `DB_NAME=arbicore_x`. Untouched: factory-mongo, its volume, Caddy, backups.
- Additive deploy ONLY: `docker compose build backend frontend opportunity-center` then `up -d --no-deps backend frontend opportunity-center`. Forbidden: `down -v`, volume/DB delete, drop/truncate, factory-mongo recreation.
- Continuity baseline to defend (post ≥ pre): mid_opportunities 416, mid_decisions 208, mid_opportunity_lifetime 208, mid_routes 20, arbicore_paper_evidence 214, calibration_models 2, adaptive_weight_recommendations 2, evidence_bundles 2 (+ all others present).
- Produced `/app/deploy/VPS_CONTINUITY_RUNBOOK.md`: read-only pre/post inventory + SHA256, pre/post diff script, additive deploy commands, app read/write/signer/safety/leak checks, 17-rule GO/NO-GO checklist, non-destructive rollback. No app/feature changes; SHADOW preserved; LIMITED_LIVE + FULL_AUTOMATION locked. AWAITING operator GO + inventory output.

## LIMITED_LIVE readiness snapshot (2026-08-20) — overall YELLOW, can_activate=false
GREEN (evidence): CONFIGURATION_RPC, FLASH_PROVIDERS, DEX_ADAPTERS_QUOTE, DEX_ADAPTERS_SETTLE (encoder self-test), DISCOVERY_ENGINE, ROUTE_ENGINE, OPP_TYPES, QUOTES_LIVE, PROFITABILITY, CONFIDENCE_V2, EXPECTED_VALUE, SIZE_OPTIMIZER, LIQUIDITY_DEPTH, SCANNER, SIMULATION_GATE, SETTLEMENT_SIMULATION (real getAmountsOut), RPC_STATE_OVERRIDE (verified), HISTORICAL_REPLAY (archive verified), DECISION_HISTORY.
Remaining blockers:
- WALLET_GAS (USER): fund+register Base gas wallet.
- SIGNER (USER): isolated KMS signer.
- EXECUTOR_CONTRACT (USER): deploy+allowlist executor, set ARBICORE_EXECUTOR_ADDRESS_BASE.
- SIMULATION_ONCHAIN (ENGINEERING): atomic executor sim via state-override code injection — unblocks once EXECUTOR_CONTRACT set (state-override already verified supported).
- FORK_VALIDATION (USER): local anvil --fork-url <archive rpc> for a controllable fork (public RPC lacks trace/fork).

## Done — 2026-08-20 (Executor + gas wallet configured; readiness 21/25 GREEN)
- Configured PUBLIC values in backend .env: ARBICORE_GAS_WALLET_ADDRESS=0x998d…ad25 (verified on-chain balance 0.00418 ETH) and ARBICORE_EXECUTOR_ADDRESS_BASE=0x91c0…3DE3 (verified on-chain: 6664 bytes of deployed code). WALLET_GAS + EXECUTOR_CONTRACT now GREEN.
- Matrix logic hardened: WALLET_GAS accepts env gas address; SIGNER now keyed off encrypted-vault handle count (arbicore_secrets) NOT env; ATOMIC/SIMULATION_ONCHAIN blocker text corrected (executor deployed + state-override verified; remaining = signer + entrypoint calldata).
- Verified live capabilities (dedicated-RPC still pending): state_override=true, archive_state=true, trace=false.
- Readiness: 21/25 GREEN, overall YELLOW, LIMITED_LIVE.can_activate=false, mode SHADOW, scanner running.
- Remaining 4 YELLOW trace to TWO secret injections only Emergent/USER can do: (1) execution signer key → encrypted vault (arbicore_secrets currently 0 handles) — unblocks SIGNER + ATOMIC_EXECUTOR_SIM + SIMULATION_ONCHAIN; (2) Alchemy archive RPC URL → ARBICORE_RPC_URL_BASE/ARBICORE_ARCHIVE_RPC_URL — unblocks FORK_VALIDATION + removes rate-limit fragility. These values are NOT in runtime; cannot be invented.

