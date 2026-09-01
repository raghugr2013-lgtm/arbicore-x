# ArbiCore X — PRD / Working Memory

## Original task
Audit the canonical ArbiCore X repo at immutable baseline `6de846f` (branch
`complete-Base-M1-M4-live-shadow-composition`), determine implemented vs
dormant/miswired/incomplete, then safely complete canonical integration toward a
controlled path to LIMITED LIVE. **SHADOW/PAPER only — execution must remain impossible.**

## Architecture (as-found, canonical)
- FastAPI backend (`app/backend`, symlinked `/app/backend`) + React v2 frontend (`app/frontend/src/v2`) + MongoDB.
- Canonical pipeline: SUPPORTED CHAINS → provider discovery → 6 scanner families →
  EmissionBus → canonical `arbicore_opportunities` repo → verifier/Gates 7/8/9 →
  M3 authority (`pre_broadcast.py`) → evidence → SHADOW/PAPER.
- Runtime composition root: `arbicore/runtime/composition.py`.
- 6 scanner families implemented + wired: cex_arb, funding_arb, dex_arb, launch_arb,
  cross_chain_arb, flash_loan_arb (deepest). All boot DORMANT (scanner_state.enabled=False).
- Universal Gates 2–5: `arbicore/scanners/gates/universal.py`. Gate 7/8/9 in flash-loan verifier.
- Economics: FlashLoanEconomicsAssessor + multichain_economics + chain gas models (6 chains) + Base L1 all-in cost.
- Price/TVL: OnChainUsdPriceFeed (M2.5, peg/freshness-guarded), CachedTVLProvider (M2.6, on-chain reserves). All fail-closed.
- Provider selection: `flash_loan_arbitrage/provider_selection.py` — fee-driven, fail-closed on unknown liquidity.

## Safety posture (unchanged, verified)
LIMITED_LIVE=0, FULL_LIVE=0, AUTOEXEC_AUTOSTART=0, RUNTIME_AUTOSTART=0, MIN_NET_PROFIT_USD=35.
No signer, no broadcast, SHADOW pipeline built with no broadcaster/mode_repo → broadcast structurally impossible.

## What was done (2026-06 audit session)
- Created local `.env` (backend SHADOW-safe values + auth) and frontend `.env` (REACT_APP_BACKEND_URL). `.env` is gitignored (not checkpointed).
- Installed backend deps; backend + frontend running under supervisor; auth + canonical `/api/arbicore/opportunities` verified (returns `source:"canonical"`, empty = fail-closed).
- MINIMAL SAFE CHANGE: legacy OBSERVE-mode pipelines (`live_market`, `cex_dex`, `dex_dex`) that feed the SEPARATE legacy MID store are now OPT-IN (default OFF) to stop duplicate/parallel opportunity generation vs the canonical EmissionBus feed.
  - `server.py`: `LIVE_MARKET_AUTOSTART` / `CROSS_AUTOSTART` default "1"→"0".
  - `arbicore/config/runtime.py`: matching informational defaults →False.
- Verified: canonical offline suites pass (M2/M3 110, Phase-2 95, regression 77). Full suite 2208 passed; remaining failures are xdist event-loop artifacts + requests-based integration tests (external routing/auth) + 3 STALE offline tests (base-only gas-model assertion; shadow-cert fake missing provenance) — NOT product regressions, NOT weakened.

## Full audit report
`/app/reports/CANONICAL_INTEGRATION_AUDIT_2026-06.md` (sections A–S).

## Known blockers before LIMITED LIVE (require real Base RPC on VPS; not reproducible in preview)
1. Aerodrome/Slipstream canonical address + TVL resolution discrepancy (real_address/TVL null despite successful quotes) — Gate 8 stays fail-closed. See `HANDOFF_NEXT_EMERGENT.md §4`.
2. Need a genuinely profitable real opportunity to reach GREEN end-to-end (fail-closed dry-run) before any evidence-gated LIMITED-LIVE plan.
(Note: the older MEV `congestion=None` TypeError from the handoff is ALREADY fixed at this baseline — `fresh_fn` DENYs before `mev.classify`.)

## Backlog / next (SHADOW-safe)
- DONE (2026-08 observability-only, APPROVED): added precise fail-closed reasons — base_all_in_cost.py all-in DENY (eth_usd_unavailable/gas_units_invalid/gas_price_read_failed/gas_price_unavailable/gas_price_above_ceiling/l1_*); v3_state.py reserves tvl_error (pool_metadata_unresolved/balanceOf_token0_empty/balanceOf_token1_empty/decimals_or_balance_unparseable/nonpositive_reserves). Logging-only, return values/gates/thresholds/economics UNCHANGED. New test test_m3_observability_reasons.py (6). testing_agent iteration_6: 6/6 + 63/63 regression, 0 issues. Golden untouched. NEXT: user runs VPS diagnostic to read the exact reason on live RPC, then decide if a behavioral fix is needed.
- DONE (2026-08 opportunity-engine economics validation): audited OpportunityEngine (arbicore/economics/) — fee accounting CORRECT (marginal_spread_bps from real quote is net-of-DEX-fees; buy/sell_venue_fee_bps=0, no double-count; consistent with canonical FlashLoan fix). Added deterministic synthetic positive/negative control + reconciliation (8) and quote-failure classification (7) tests; executor capability matrix artifact (reports/ARBICORE_X_EXECUTION_CAPABILITY_MATRIX.json — executor is UniV3-only by design; Aerodrome=intelligence-only). testing_agent iteration_5: 120/120, 0 issues. CONCLUSION: deployed 0-executable opportunities is GENUINE market economics, not a broken engine. DEFERRED to VPS: full live-RPC E2E (discovery→quote→liquidity) needs a Base RPC. Golden image untouched.
- DONE (2026-08 economics fix, APPROVED + preview-verified, NOT yet on VPS): corrected DEX swap-fee double-count in the authoritative FlashLoan path — FlashLoanEconomicsAssessor.assess gains gross_is_quote_inclusive (default True; live quote path no longer re-deducts pool swap fees; observed fee kept as telemetry; estimated path unchanged). verifier.py + composition.py pass True. Shared aggregate_economics/DEX/triangular/gates/M3 untouched. testing_agent iteration_4: 8/8 new + 98/98 regression, spread-widener confirmed pre-existing order artifact (5/5 isolated), 0 issues. Manifests: reports/ARBICORE_X_CURRENT_STATE.md + ARBICORE_X_CERTIFICATION_MATRIX.md. Awaiting review before VPS Shadow promotion.
- DONE (2026-06 cbETH pricing P0 fix, APPROVED + preview-verified, NOT yet on VPS): fixed cbETH USD price returning None on Base. Root cause: `price_feed.py::_quote_usdc` returned None immediately when the DIRECT cbETH/USDC UniV3 quote failed (thin/absent liquidity on Base), never attempting the liquid two-hop cbETH→WETH→USDC route. WETH worked because its direct USDC pool is deep. Fix: on direct-quote failure, FALL THROUGH to the real two-hop T→WETH→USDC route; if BOTH real routes fail, still return None (fail-closed — no fabricated price/TVL, gates unchanged). Added 3 deterministic regression tests in `tests/test_m2_5_price_feed.py` (direct-fails→two-hop-succeeds; both-fail→None; direct-succeeds→direct-used); 16/16 in that file pass. Added read-only VPS evidence script `scripts/m2_5_cbeth_price_evidence.py` (prices WETH/cbETH via live QuoterRegistry, dumps provenance/block/head-freshness + acceptance verdict). testing_agent iteration_7: backend 100%, 0 issues; SHADOW/fail-closed intact, no signing-material leakage. Test-env note: cleared stale `login_attempts` + re-provisioned users from `.env` (admin/operator both login 200). NEXT (user request): on VPS run `python -m scripts.m2_5_cbeth_price_evidence` to capture real-RPC evidence (cbETH direct fails, two-hop succeeds, valid provenance/block freshness), then run the full read-only Shadow E2E before considering Limited Live.
- DONE (2026-06 D-3.6A, preview-verified incl. REAL Base RPC smoke, AWAITING operator approval before validator deploy): wired the single live path Base → Uniswap V3 → QuoterV2 → eth_call → real amountOut → DEXQuoteResult in `arbicore/scanners/dex_arbitrage/quoter.py::EVMV3Quoter`. `_quote_impl` now delegates the (uniswap_v3, base) case to `_quote_base_univ3`, which reuses the canonical `QuoterRegistry`/`UniV3QuoterV2` backend (no parallel RPC/ABI), resolves tokens + fee-tier candidates from the existing `base_venues`/`base_pool_registry` (no duplicate registry), sizes stable input as exact USD notional (non-stable → canonical probe notional), quotes each registry fee tier and keeps the best amountOut. Added `credentials_available` override so ONLY (uniswap_v3, base) becomes reachable when a Base RPC is configured via the existing `resolve_rpc_url_from_env`; every other (dex, chain) stays ALCHEMY-gated + `not_yet_wired`. Fail-closed on unknown token / no pool / all-tiers-revert (no fabricated price). Live proof vs public Base RPC: $1000 USDC → 0.40210 WETH, fee 5bps, pool 0xd0b53D9277642d899DF5C87A3966A349A798F224, block 50552030, implied WETH ≈ $2487. Tests: `tests/test_d3_6a_base_univ3_quote.py` (10 offline) + `tests/test_d3_6a_base_univ3_smoke.py` (real-network, auto-skips without Base RPC). Full D-3 suite 76 passed/7 pre-existing skips, 0 regressions. UNCHANGED: M3 authority, $35 gate, scanner enablement/emissions, signing/broadcast/autoexec (all still off). NOTE: DEXQuoteVerifier still needs ≥2 live venues → correctly stays DENIED_VENUE_UNREADABLE (D-3.6A wires only one venue by design).
- DONE (2026-06 D-3.6B deployed to preview + D-3.6 spread reconciliation + shadow two-venue E2E, preview-verified incl REAL Base RPC, AWAITING approval before validator/Limited-Live): (1) Deployed D-3.6B (service restart), D-3.6B validator tests 11/11 vs real Base RPC. (2) CORRECTNESS FIX — reconciled the verifier's cross-direction effective_price units: `EVMV3Quoter` now emits `effective_price` as normalized QUOTE-per-BASE for BOTH directions via `_quote_per_base` (buy=ask=quote_in/base_out, sell=bid=quote_out/base_in). Verifier's min-ask/max-bid spread is now mathematically correct (was reciprocal-mismatched); matches MockQuoter convention so D-3.2 tests unaffected. New `tests/test_d3_6_spread_reconciliation.py` proves the math. Updated D-3.6A/B tests for new units. (3) New READ-ONLY shadow E2E `scripts/d3_6_two_venue_shadow_e2e.py` runs discovery→UniV3+Aerodrome live quotes→DEXQuoteVerifier→cross-venue spread→all-in economics→$35 gate→decision with full block/quote/backend provenance. Real Base RPC run (block ~50552927): WETH/USDC UniV3 ask 2494.99 / bid 2492.44, Aerodrome ask 2494.94 (slipstream) / bid 2491.85; best ask 2494.94 (aerodrome) vs best bid 2492.44 (uniswap) → spread −10.0 bps (NO arb — efficient market), net −$2.30, $35 gate FAIL, verifier denied:venue_disagrees (spread≤0). Honest fail-closed, zero fabrication. NOTE: liquidity/TVL not fetched in the quote path (M2.6 provides it; Gate 2 fail-closed when absent); flash-loan fee + M3 authority apply only to the flash_loan strategy, NOT spot two-venue DEX arb (reported as N/A). Regression: full D-3 suite green, 0 regressions. UNCHANGED: signing/broadcast/autoexec/M3/$35 gate/scanner enablement. Limited Live NOT enabled.
- DONE (2026-06 D-3.6B, preview-verified incl. REAL Base RPC smoke, AWAITING operator approval before validator deploy): wired dex="aerodrome" (Base) LIVE across BOTH Aerodrome pool families via `_quote_base_aerodrome` in `dex_arbitrage/quoter.py::EVMV3Quoter` — classic AMM (Router.getAmountsOut) + SlipStream (QuoterV2), each delegated to the existing canonical `QuoterRegistry` backends (no parallel RPC/ABI/pool-address resolver). Enumerates Aerodrome candidates for the pair from `base_pool_registry`; neither backend needs a pre-resolved address so the unresolved-address blocker doesn't apply. Quotes both, keeps the best valid amountOut; fail-closed on no-pool / all-backends-fail / non-positive out (never synthesizes). Provenance: `raw.winning_backend`/`winning_dex`/`quoter_contract`/`block_number` + full `backend_attempts` list (both attempts w/ status). Added ("aerodrome","base") to `_WIRED_LIVE`. Verifier (`verifier.py`) now passes `raw.winning_backend` into LegEvidence.metadata as `quote_backend` (additive; no gate logic changed) so evidence distinguishes the pool family even though external venue stays dex="aerodrome". Live proof vs public Base RPC: classic 0.05 WETH→124.057 USDC (Router 0xcF77…4E43), SlipStream 0.05 WETH→124.181 USDC (Quoter 0x254c…15b0); wired best-of-both $1000 USDC→0.40234 WETH, winning=aerodrome_slipstream, implied WETH ≈ $2485, both attempts recorded, block 50552643. Tests: `tests/test_d3_6b_aerodrome_quote.py` (9 offline incl. verifier-integration proving gates run + backend in evidence) + `tests/test_d3_6b_aerodrome_smoke.py` (3 real-network, auto-skip). Regression: D-3 suite 81 passed/7 pre-existing skips, 0 regressions. Files changed: quoter.py, verifier.py (+2 test files). UNCHANGED: M3 authority, $35 gate, scanner enablement/emissions, signing/broadcast/autoexec (all still off). NOTE: with UniV3+Aerodrome both live, DEXQuoteVerifier now has 2 Base venues (venue-readable); economic realism of the verifier's cross-direction effective_price model is a separate future item.
- DONE (2026-06 readiness pass, option-b non-RPC work): added flash-loan optimizer offline test suite (8/8); audited per-chain RPC plumbing (consistent via resolve_rpc_url_from_env), 6-chain config (chain IDs + USDC/USDT/DAI stables; Base uses dedicated layer), triangular multi-fee-tier (500/3000/10000/100), FL provider catalog (Balancer/Aave/UniV3/Morpho). testing_agent iteration_3: 199/199. Cross-chain marked RED — OUT OF SCOPE for atomic Limited-Live. Final matrix: reports/READINESS_MATRIX_2026-06.md. Live 6-chain validation BLOCKED-BY-RPC → deferred to VPS.
- DONE (2026-06 Base SHADOW dry run): read-only dry run vs real Base RPC (public mainnet.base.org). Fixed QuoterRegistry RPC precedence (now honors ARBICORE_RPC_URL_BASE) → real quotes + genuine UniV3 Gate-8 TVL ($8.48M onchain_reserves) proven; MEV genuine (eth_feeHistory); Balancer vault 24.217 WETH; all candidates fail-closed DENIED, broadcast_sent=false. testing_agent iteration_2: 4/4 fix + 49/49 regression. Report: reports/BASE_SHADOW_DRYRUN_2026-06.md.
- DONE (2026-06 completion pass): repaired 3 stale tests (multi-chain gas-model + shadow-cert provenance fake) without weakening production; fixed `resolved_addresses()` to include genuinely on-chain-resolved (RUNTIME_RESOLVED) Aerodrome/Slipstream addresses (fail-closed) + new test; made canonical Opportunities view the default landing (`AppShell` index → Navigate to opportunities). testing_agent iteration_1: backend 76/76 + 3/3 curl, frontend 5/5, 0 issues. See `reports/COMPLETION_ADDENDUM_2026-06.md`.
- P1: Empirically validate Aerodrome/Slipstream address+TVL resolution on real Base RPC (Gate 8) — propagation code already present; needs live RPC (no fabrication).
- P1: Genuinely profitable real opportunity reaching GREEN end-to-end (fail-closed dry-run) before any evidence-gated LIMITED-LIVE plan.
- P2: Wire funding_arb order-book depth_fetcher; inject cross_chain transfer/liveness providers for verification.
- P2 (UX quirk from testing_agent): hard-reload of `/dashboard/ops` re-routes via `/initialization` back to default landing; in-app SPA nav works. Pre-existing init flow; review if it bothers operators.

## Iteration 2 (2026-06) — Diagnostic-run evidence attribution
- Problem: authoritative branch exposed diagnostic provenance on evidence bundles but had no capability to isolate evidence for exactly one audit run; Codex could not run a clean attributable VPS audit.
- Implemented (observability only): arbicore/evidence/audit_provenance.py (build_audit_evidence_query / evidence_matches_audit / filter_evidence_for_audit / AuditProvenanceError), EvidenceBundlesRepo.find_for_audit + diagnostics.* index, env-driven fail-closed isolation in scripts/m3_0_vps_validate.py.
- Fail-closed rules enforced; NoSQL-injection safe; never mixes runs; never falls back to candidate-id/timestamp; pinned-but-unmatched -> empty plan.
- Tests: tests/test_flashloan_audit_evidence_filter.py (16). Prior partial-quote + Gate 7/8/9 suites still green (audit runner: 111 passed).
- No trading gate/threshold/economics/signing/broadcast/live-mode changed.
- Final SHA: fab3c1b4130588212b93f59f33d37e328ff87a92 (branch complete-Base-M1-M4-live-shadow-composition). local==remote confirmed.
- Verified by testing_agent iteration_1 (found 3 gaps) + iteration_2 (all 3 fixed, no regressions).

## Iteration 3 (2026-06) — Canonical VPS audit workflow fix
- Blocker: filter_evidence_for_audit required all 3 selectors; runner had only audit_run_id -> TypeError.
- Fix: candidate_id OPTIONAL (audit_run_id+scanner_tick_id mandatory/exact); new run_single_canonical_flash_loan_audit_tick() (one tick, captures ACTUAL ids); scripts/vps_canonical_audit.py runner (read-only, fail-closed, no secrets); run_vps_validator_audit.sh live phase; docs/LIMITED_LIVE_READINESS.md.
- testing_agent iteration_3: 133 targeted+new tests green; live phase proven end-to-end (real tick -> capture ids -> isolate run+tick -> ledger -> m3_eligible=false WAIT); strict isolation intact; no gate/economics/signing/broadcast/live change.
- START 2cab437 -> FINAL ff28c0e. local==remote confirmed.
- Classification: audit tooling + safety chain CODE READY; full Limited-Live BLOCKED — MISSING READINESS CONTROL (Balancer liquidity, borrow sizing, exact-tx atomic simulation not implemented offline).

## Iteration 4 (2026-06) — Limited-Live eligibility decision layer
- Added fail-closed DECISION LAYER (CONFIRMED != EXECUTABLE): executor_capability.py (SUPPORTED/UNSUPPORTED/UNVERIFIABLE, Aerodrome denied, dex normalised), borrow_sizing.py (profitable AND executable else INFEASIBLE), limited_live_eligibility.py (15 mandatory controls, any missing/unknown/failed => DENY), readiness_assessment.py (bundle->decision, exact provenance), reused provider_liquidity.read_balancer_liquidity + AtomicExecutorSimulator.
- vps_canonical_audit.py emits per-CONFIRMED readiness + eligibility; docs/LIMITED_LIVE_READINESS.md updated (control table, DENY causes, VPS config, Codex steps).
- Decision layer consumed ONLY by read-only audit runner; NO gate/threshold/economics/verifier/mode/kill-switch/signing/broadcast changed.
- testing_agent iteration_4: 473 passed 0 failed; independently confirmed fail-closed (perfect CONFIRMED bundle still DENIED in read-only audit); no secrets in output; signed/broadcast/limited_live_enabled=false.
- START 5a5cafb -> FINAL 9609830. local==remote confirmed.
- Classification: CODE READY — VPS VALIDATION REQUIRED. Reaching ELIGIBLE needs VPS RPC + deployed executor + present signer + live Balancer confirm + freshness/mode/kill-switch — all fail closed today.

## Iteration 5 (2026-06) — VPS validator runner: python3 alias + test-tooling (fail-closed)
- Part A (SHA e74b1fa): fixed `python: command not found` in scripts/run_vps_validator_audit.sh via dynamic interpreter detection (ARBICORE_PYTHON -> python3 -> python) + python3 docstrings across backend scripts. 138 deterministic tests green.
- Part B (this session, START e74b1fa -> FINAL 0cd1cf1): made the DISPOSABLE VPS validation image test-capable (VPS reported `/usr/bin/python3: No module named pytest`). Additive/validation-only; production untouched:
  * NEW deployment/docker/backend/requirements.test.txt — explicit pinned test deps (prod superset + pytest==9.1.1, pytest-xdist==3.8.0, pytest-asyncio==1.4.0, execnet==2.1.2, iniconfig==2.3.0, pluggy==1.6.0). Import names asserted: pytest, xdist, pytest_asyncio.
  * NEW deployment/docker/backend/Dockerfile.validation — dedicated disposable test-capable image (build-time install of requirements.test.txt; source MOUNTED at runtime, not baked; git+curl present for SHA stamping). Production Dockerfile/compose/requirements.prod.txt verified byte-identical (no default-target drift).
  * FIX requirements.dev.txt (was missing xdist/asyncio/execnet) -> now `-r requirements.test.txt`.
  * HARDEN run_vps_validator_audit.sh: fail-closed test-tooling preflight. present -> run + report REAL result; absent -> `TEST TOOLING UNAVAILABLE` + exit 3 (NEVER a fake PASS); opt-in isolated pinned bootstrap via ARBICORE_VALIDATOR_BOOTSTRAP=1 (--system-site-packages venv, no host/global/prod mutation).
  * DOCS: LIMITED_LIVE_READINESS.md §2a + deployment/README tree.
- Verified locally (preview, no Docker/RPC/Mongo): TEST1 deps present -> 138 passed exit 0; TEST2 clean interpreter w/o pytest -> exit 3 + clear UNAVAILABLE (never PASS); TEST3 opt-in bootstrap -> isolated venv provisioned from pinned file -> 138 passed exit 0.
- NO trading logic / Gate 7-8-9 / thresholds / signer / live-mode / broadcast changed. LIMITED_LIVE + FULL_LIVE still 0.
- NOTE: preview container is NOT the VPS (no Docker/RPC/Mongo) — full live A-L VPS audit still pending on real VPS by Codex against SHA 0cd1cf1.

## Iteration 5c (2026-06) — Validation image dependency-layout fix
- VPS build reached Dockerfile.validation but failed: `Could not open requirements file: /app/requirements.prod.txt`. Cause: it COPYed only requirements.test.txt, which starts with `-r requirements.prod.txt` (resolved relative to the file's in-image dir).
- Smallest fix: Dockerfile.validation now `COPY requirements.prod.txt /app/requirements.prod.txt` before `COPY requirements.test.txt` and the pip install. Same in-image dir, basename preserved.
- Added deterministic guard tests/test_validation_image_requirements_layout.py (3 tests): asserts Dockerfile.validation COPYs every local `-r` include of requirements.test.txt into the pip-install dir. NOT in the 12-module runner list -> the 138 count is unchanged; collected by full `pytest tests/`.
- Verified in preview (no Docker): pip-parse repro reproduced the exact VPS error with only the test file, and resolved cleanly with both files colocated; guard 3/3 passed and provably fails on the pre-fix Dockerfile; full runner 138 passed exit 0.
- UNCHANGED: requirements.prod.txt, production Dockerfile/compose, run_vps_validator_audit.sh, gates/economics/thresholds/executor/signer/broadcast/live-mode.
- START 587b0cb -> FINAL bd01ae9 (branch complete-Base-M1-M4-live-shadow-composition). local==remote confirmed. Not VPS-live-ready; this only unblocks the validation-image build.

## Iteration 5d (2026-06) — Validator Mongo networking/env + git provenance
- Problem on VPS: 4 Mongo-backed deterministic tests (2 in test_flashloan_canonical_audit_runner.py, 2 in test_flashloan_audit_evidence_filter.py) connected to localhost:27017 -> Connection refused, because MONGO_URL was not reaching the pytest process; also git_sha/git_branch reported "unknown" (mounted worktree's .git unresolvable inside the container + dubious-ownership).
- Fix (START c5aa0c8 -> FINAL cf7a2f2):
  * run_vps_validator_audit.sh: explicitly `export MONGO_URL`/`DB_NAME` so xdist workers inherit the dedicated validator endpoint; print `mongo_target host:port` (no creds) or a clear WARNING when unset. Provenance now env-first: ARBICORE_VALIDATION_GIT_SHA/_BRANCH -> git (with `safe.directory` best-effort) -> unknown.
  * NEW deployment/compose/docker-compose.validation.yml: disposable stack = ephemeral tmpfs `arbicore-x-validator-mongo` + Dockerfile.validation runner on one bridge net, MONGO_URL=mongodb://arbicore-x-validator-mongo:27017 + DB_NAME injected, worktree bind-mounted :ro, VALIDATION_GIT_SHA/_BRANCH passthrough. Never touches production Mongo/compose.
- Verified in preview: bash -n OK; compose YAML valid; RUN A (MONGO_URL unset) -> warning + real git_sha + 138 passed; RUN B (MONGO_URL set + explicit provenance) -> mongo_target localhost:27017, git_sha/branch overridden, 138 passed; cred-stripping parse confirmed.
- UNCHANGED: production Mongo/compose, requirements.prod.txt, gates/economics/thresholds/executor/signer/broadcast/live-mode. Fail-closed preserved.
- NOT run on real VPS by me (Emergent preview has no Docker/RPC and is not the VPS). Codex must re-run the 138 suite on the VPS at cf7a2f2 and report exact pass/fail BEFORE the live A-L audit. No live readiness claimed.

## Iteration 5e (2026-06) — Safe Limited-Live readiness provisioning (items 2-4)
- START f787950 -> FINAL a13bebc. Additive, fail-closed only. No executor deploy, no compose/live-mode change, no threshold/gate/signer/broadcast change.
- NEW arbicore/scanners/flash_loan_arbitrage/live_readiness_probes.py (4 read-only probes):
  1. probe_atomic_simulation: AtomicExecutorSimulator exact-tx read-only eth_call + state override; UNKNOWN w/o RPC, DENY w/o executor/calldata/signer; never signs/broadcasts.
  2. probe_balancer_liquidity: real Balancer V2 Vault balanceOf, AVAILABLE vs REQUESTED; None/UNKNOWN/UNAVAILABLE fail-closed; never fabricates.
  3. probe_freshness: documented quote-age<=12s + block-lag<=ARBICORE_PRICE_MAX_BLOCK_LAG(5); fail closed on missing/stale/reorg; threshold unchanged.
  4. probe_mode_and_kill_switch: honest ControlStateRepo mode + KillSwitchRepo; mode_allows only LIMITED_LIVE/FULL_AUTOMATION; engaged/unknown => DENY; never enables anything.
- WIRED into scripts/vps_canonical_audit.py _assess_confirmed_readiness (replaced hardcoded stubs) + report["operator_state"]. Signature backward-compatible (kw defaults).
- TESTS NEW tests/test_flashloan_live_readiness_probes.py (25 passed): missing RPC/executor/calldata/signer, passing sim, balancer confirmed/insufficient/unknown/unresolved, freshness fresh/missing/stale/reorg/lag, disabled mode, engaged kill-switch, eligibility integration (all-pass eligible; disabled-mode/kill/stale => DENY).
- Verified: 138-module runner green; 25 new tests green; audit script imports OK; safety files (limited_live_eligibility, pre_broadcast, executor_capability, readiness_assessment) UNCHANGED. Broad `pytest tests/` failures are PRE-EXISTING/environmental (need live server:8001/RPC/DB) — not caused by this change.
- Eligibility posture now HONEST: DENY via real reads (SHADOW mode => mode_allows False; no deployed executor => atomic_sim/executor DENY). A genuine ELIGIBLE is reachable only after operator deploys+verifies executor, provisions signer, confirms Balancer liquidity, a profitable UniV3 closed cycle clears $25 floor, and mode is enabled. signed=false/broadcast=false everywhere.
- STOPPED per instruction: awaiting explicit approval before any on-chain executor deployment.

## Iteration 5f (2026-06) — Complete Limited-Live readiness track (software)
- START 42a4397 -> FINAL f7443d2. Additive, fail-closed, non-broadcast. No deploy/sign/broadcast/mode/gate/floor/compose change.
- Executor: FlashLoanReceiver already deployed on Base Sepolia (84532) 0x99c0b64e...1052 (success); NO mainnet (8453). Registry (deploy/executor_deployments.json) + read-only loader added earlier.
- NEW resolve_executor_address (env ARBICORE_EXECUTOR_ADDRESS_BASE -> registry[ARBICORE_CHAIN_ID|8453]); probe_signer_readiness (PUBLIC addr vs executor owner; no keys).
- NEW limited_live_readiness_matrix.py: classifies every prereq READY/BLOCKED/UNKNOWN/MARKET-DEPENDENT (categories software/onchain_operator/operator/market). Wired into vps_canonical_audit report (+ operator_state, signer_state, executor_address_resolved).
- Executor capability: UniV3-only SUPPORTED, Aerodrome DENIED, unknown UNVERIFIABLE (tested). Atomic sim BLOCKED until signer authorized. Balancer AVAILABLE>=REQUESTED. Freshness <=12s + block-lag<=5 (unchanged). SHADOW stays SHADOW; kill switch honest.
- Tests: +13 (test_limited_live_readiness_matrix.py); 55 across new suites; 138-runner green. signed=false/broadcast=false.
- REMAINING (operator/on-chain boundary): deploy+verify Base MAINNET executor; provision signer (ARBICORE_EXECUTOR_SIGNER_ADDRESS public == owner + vault key out-of-band); set ARBICORE_EXECUTOR_ADDRESS_BASE; enable mode; then wait for a genuine CONFIRMED+profitable(>=$25) UniV3 candidate. STOP at irreversible boundary.

## Iteration 5g (2026-06) — Executor identity probe + readiness API (software complete)
- START e3b790e -> FINAL 610a617. Additive, fail-closed, non-broadcast. No deploy/sign/key/mode/gate/floor/prod-compose change.
- probe_executor_identity (read-only inspect_executor): bytecode present, owner/ROUTER/VAULT, entrypoint selector, router/vault vs registry ctor args. absent->BLOCKED, no-rpc->UNKNOWN, mismatch->BLOCKED, match->READY. Feeds owner to signer probe.
- gather_and_build: SINGLE canonical readiness assembler reused by VPS audit + API (no competing impl).
- NEW GET /api/arbicore/limited-live/readiness -> canonical matrix + operator/signer/executor-identity/atomic-sim; signed/broadcast/limited_live_enabled all false. Verified in-process (ASGI) HTTP 200: mode=SHADOW, mode_allows False, kill_ok True, executor(mainnet) BLOCKED, signer BLOCKED, atomic BLOCKED, market items MARKET-DEPENDENT.
- Atomic sim confirmed fail-closed. Docs: full matrix + provisioning + owner/signer + boundary + identity + atomic + freshness + mode ladder + exact enable conditions.
- Tests: +9 (test_executor_identity_probe.py); 54 combined readiness; 138-runner green.
- NOTE: preview backend cannot boot (no MONGO_URL — VPS app, not preview scaffold); endpoint validated via in-process ASGI. Real VPS live audit is Codex's step.
- Remaining = operator/on-chain only: mainnet executor deploy+verify, signer provisioning, mode enable, + natural market eligibility.

## Iteration 5h (2026-06) — Final software pass: RPC reliability (429) + full gap audit
- Local commit e930a10 (on 64b8b57). RPC reliability: EthJsonRpcProvider._call bounded-backoff retry for 429(+Retry-After)/5xx/network/malformed; non-retryable 4xx/rpc-error/missing-result; exhaustion->ProviderError (fail closed); verify_chain_id fail-closed; no secret logging. +tests/test_rpc_reliability.py (11). Env: ARBICORE_RPC_MAX_RETRIES/BACKOFF_BASE_MS/BACKOFF_CAP_MS.
- Validated: 11 RPC + 65 readiness/RPC combined + 138-runner all green; existing RPC callers 14 passed. No mode/gate/floor/signer/broadcast/compose change.
- PUSH BLOCKED: direct-push token invalid ("Password authentication not supported"). Commit e930a10 is LOCAL; needs Save-to-GitHub or platform auto-sync to reach remote (remote tip still 64b8b57).
- Software pipeline classification: all software-dependent readiness items COMPLETE. Remaining = VPS config (RPC url/rate-limit, MONGO/env), on-chain operator (mainnet executor deploy+verify, signer provisioning), operator (mode enable), market (genuine CONFIRMED+profitable UniV3 candidate).

## Iteration 5i (2026-06) — Pre-push re-verification of HEAD e930a10 (RE-VERIFY HEALTH FIRST)
- HEAD confirmed e930a10 on branch complete-Base-M1-M4-live-shadow-composition; worktree clean except this memory doc (no tracked source changes from verification).
- 429 FIX PRESENT: YES (verified via `git show HEAD:.../providers/rpc.py` — bounded-backoff 429/5xx/network + verify_chain_id fail-closed).
- Authoritative deterministic audit runner (scripts/run_vps_validator_audit.sh): 138 passed, AUDIT RESULT: PASS, exit 0.
- Targeted readiness/RPC unit suites: 83 passed (rpc_reliability, limited_live_readiness_matrix, live_readiness_probes, flashloan_limited_live_readiness, d5_2 rpc chain liveness, quoter rpc precedence). 
- test_p0_iter13_signer_readiness.py = 13 live-HTTP integration tests requiring a fully-provisioned/seeded live server (preview backend cannot boot: VPS app has no local MONGO_URL/.env) — environment-dependent, NOT part of deterministic runner, NOT a 429 regression.
- In-process readiness matrix validation: PASS. signed/broadcast/limited_live_enabled all False in every state; SHADOW denies (mode_allows False); rpc-missing->SOFTWARE_INCOMPLETE; fully-provisioned hypothetical->SOFTWARE_READY_MARKET_AND_OPERATOR_PENDING (never enabled).
- REGRESSION STATUS: none. SIGNED=NO, BROADCAST=NO, LIMITED_LIVE_ENABLED=NO, MODE=SHADOW. No irreversible/on-chain action performed. Repository ready for Save-to-GitHub of e930a10.

## Iteration 5j (2026-06) — VPS/validation drift reconciliation + read-only on-chain verification (SAFE, fail-closed)
Base commit e930a10 (+5340960 PRD). All changes additive, read-only, fail-closed. No deploy/sign/broadcast/key/mode/gate/floor/prod-compose change.

### Validation infrastructure (Codex-transition drift fix)
- deployment/compose/docker-compose.validation.yml: REMOVED fixed `container_name: arbicore-x-validator-mongo` (collided with a pre-existing standalone container) and the fixed network `name:`. Now project-scoped -> repeatable, isolated runs. MONGO_URL uses SERVICE name `mongodb://validator-mongo:27017`. Production compose (docker-compose.yml/.shared.yml) intentionally keep fixed container names — left UNTOUCHED (correct reconciliation: prod=stable identity, validator=ephemeral).
- NEW scripts/run_validation_stack.sh: deterministic self-cleaning wrapper — unique per-run compose project + pre/post `down -v --remove-orphans` so no stale validator container can block the next run. (Docker absent in preview; wrapper is for the VPS.)
- Confirmed Dockerfile.validation + requirements.test.txt (`-r requirements.prod.txt` + pytest/xdist/asyncio pins) + requirements.prod.txt ALL present/correct — validation image is test-capable.

### RPC reliability (verified on real backend path)
- 429 handling present on BOTH read paths: providers/rpc.py EthJsonRpcProvider._call (readiness reads; bounded backoff, honors Retry-After, fail-closed on exhaustion) AND execution/quoter.py _eth_call (quoting; global throttle + bounded exp backoff, fails closed on exhaustion). Neither is an uncontrolled loop.
- NEW: probe_executor_identity surfaces `RPC_PROVIDER_RATE_LIMITED` reason code + `rpc_rate_limited=True` on 429 while status stays UNKNOWN (fail-closed; no fabricated READY).

### Provenance drift observability (env vs registry)
- NEW executor_registry.executor_provenance(chain, env_address): READ-ONLY reconciliation of ARBICORE_EXECUTOR_ADDRESS_BASE vs deploy/executor_deployments.json. Observability ONLY — never changes classification, never writes env, never fabricates a deployment. Wired into gather_and_build + GET /api/arbicore/limited-live/readiness response (`executor_provenance`).
- Registry 8453 entry remains `not_deployed`/address null by design; NOT auto-written (lacks canonical deploy_tx/block; writing success would alter the fallback resolution path — operator boundary).

### READ-ONLY on-chain verification (via public Base RPC; eth_call/eth_getCode only)
- Base mainnet executor 0x91c0bf28E32b76889BB2B61E1A2dDE9F7e4f3DE3: chainId 8453 OK, bytecode present (6664B), owner 0x998d6efF2b28b72c44f7a334c42678eb4cCaad25, router 0x2626664c... (== expected uniRouter), vault 0xBA1222...2C8 (== expected Balancer V2), entrypoint selector present, no mismatches -> identity READY (executor_identity_confirmed_onchain). => registry `not_deployed` is STALE drift; the executor IS deployed+identity-matched on-chain.
- Base Sepolia executor 0x99c0b64e8F24fc1aADb07dAbA938d9f11dCD1052 (registry-recorded): chainId 84532 OK, bytecode present (4987B), owner 0x65afB0a65Fd22F88022915F53eD48DA34fb02003, entrypoint present -> identity READY.
- Limited-Live signer PUBLIC address must equal the Base-mainnet executor owner EOA 0x998d6efF...; VPS ARBICORE_EXECUTOR_SIGNER_ADDRESS is MISSING -> signer BLOCKED (correct fail-closed).

### Tests
- Authoritative 138-module runner: PASS (re-run at HEAD after all edits). Touched-module regression sweep: 142 passed. +6 new tests (3 provenance, 3 identity/rate-limit). In-process readiness matrix + /api readiness endpoint: PASS, signed/broadcast/limited_live_enabled all False, SHADOW denies.

### Exact remaining blockers (operator/on-chain/market only — NOT software)
- VPS RPC endpoint returns 429 (RPC_PROVIDER_RATE_LIMITED): operator to raise rate limit / use authed provider. Software already retries+fails closed.
- ARBICORE_EXECUTOR_SIGNER_ADDRESS MISSING on VPS: operator to set signer PUBLIC address == executor owner 0x998d6efF... (private key stays in operator vault, never repo/env/logs).
- Operator to record canonical Base-mainnet deploy_tx/block in deploy/executor_deployments.json (optional provenance completion; on-chain identity already independently verified READY).
- Mode remains SHADOW; enabling LIMITED_LIVE is an explicit operator action.
- Market: a genuine CONFIRMED + profitable (>= $25 floor) UniV3 candidate must appear naturally.

---

## 2026-06 — Application readiness proven on free RPC (P0/P1/P2 PASS)
Branch `fix/canonical-scanner-pool-loader-integration` @ `f9f6c90` aligned into `/app`.
Ran the in-image `verify_readiness.py` against a **free public Base RPC failover set**
(publicnode + drpc + meowrpc + 1rpc + mainnet.base.org) to separate app-readiness from
RPC capacity. Results: **P0 PASS** (30/30 real, 11 Aerodrome resolved, 0 leaks),
**P1 PASS** (live UniV3 quote 100 WETH→245,943 USDC @ blk 50716840) + **P1_BADFEE PASS**
(fail-closed fallback), **P2 PASS** (Balancer vault `0xBA12222222228d8Ba445958a75a0704d566BF2C8`
depth read), **P3 BLOCKED** (no executor deployed on Base 8453 — registry `not_deployed`).
Negative control (unreachable RPC) → P0 FAIL loader_nodes=19/real=19/leaks=0 (no fabrication),
P1 fallback:break_even. Conclusion: earlier "5/11" was **Alchemy free-tier 429 (RPC capacity)**,
not code. No code changed. Signer/broadcast/Limited-Live remain DISABLED by design.
Full matrix: `/app/memory/READINESS_MATRIX.md`. Repro + go-live steps:
`/app/memory/VPS_PROOF_PLAYBOOK.md`.


## 2026-06 — P1 root cause resolved (config) + quoter error-surfacing fix
VPS P1 `fallback:break_even` root-caused to a **dead keyless RPC**: `https://rpc.ankr.com/base`
now returns `-32000 Unauthorized: API key required`. The quote path (`execution/quoter.py`)
uses a single `ARBICORE_RPC_URL_BASE` (no failover by design), so that dead endpoint forced
fallback. Fix = point `ARBICORE_RPC_URL_BASE` at a working endpoint (free Ankr WITH key, or
keyless publicnode/drpc/mainnet.base.org). Verified: full verifier with Ankr-primary +
public-fallback → **P0/P1/P1_BADFEE/P2 PASS**, P3 BLOCKED (executor not deployed).
Code change: `_eth_call` batch parser now surfaces a provider's single top-level error
(null `id`) instead of mis-reporting a downstream "decode error" — accurate operator
diagnostics, fail-closed preserved, no fabrication. Dedicated quoter tests 12 passed.
Backlog: optionally give the quote path multi-endpoint failover (deferred — broadcast-adjacent).


## 2026-06 — P1 with Alchemy: batch-handling root cause + auto single-request fallback
After a healthy Alchemy Base RPC was set as `ARBICORE_RPC_URL_BASE`, P1 still FAILed
(`block=None`, passthrough out_wei). Proved the URL IS used by the quote path (P3 hits
the same var and got a real `eth_getCode`; verifier line 65-70 wires
`QuoterRegistry(rpc_url_env="ARBICORE_RPC_URL_BASE")`). Root cause: provider rejects the
quoter's JSON-RPC **batch** (`eth_call`+`eth_blockNumber`); public nodes honour it, some
Alchemy plans don't. Fix: `_eth_call` auto-detects a mishandled batch per host and retries
as single requests (+ separate best-effort blockNumber) — batch-friendly hosts keep
batching. Also added verifier P1 diagnostics (`rpc_env/rpc_host/hop_status/hop_error`).
Verified: batch and forced-single return identical result+block on 3 endpoints; verifier
P1 PASS; quoter tests 12 passed. Files: `execution/quoter.py`, `verify_readiness.py`.
P2 value confirmed from project config (`contracts/script/Deploy.s.sol:31`,
`docs/EXECUTOR_PROVISIONING_READINESS.md:32`, `deploy/executor_deployments.json`):
`BASE_BALANCER_V2_VAULT=0xBA12222222228d8Ba445958a75a0704d566BF2C8`. Signer/broadcast/
executor/live-mode gates untouched.

