# ArbiCore X — PRD / Working Memory

## Original directive
FINAL MASTER autonomous engineering pass on the EXISTING ArbiCore X v2 trading/
searcher system: audit → canonicalize → recover → fix → complete → test → verify →
document. Keep fail-closed; never enable live/broadcast; never request/expose
secrets; never fabricate data or readiness. Start with Git archaeology.

## Architecture
- Backend: FastAPI (`app/backend/server.py`, ~250 routes, 356KB) + routers
  (`routes/auth.py`, `arbicore/routes/scanners.py`); MongoDB (motor).
- Frontend: React 19 (CRA/craco) under `app/frontend/`, UI v2.
- Package `arbicore/`: economics, execution, flashloan, learning, providers,
  scanner(s), safety, validation, wallets, evidence, certification, etc.
- Auth: single-admin, httpOnly JWT cookies, bcrypt, session-version revocation.

## Canonical baseline
- `main`=43230f6; **canonical=c284183** (strict superset; FF recommended).
  Version 2.9.2 (image 2.9.2-c284183).

## Implemented / verified this pass (2026-09 pass)
- Git archaeology (all 9 branches, 20 tags) → canonical determined by ancestry.
- Fixed boot blocker: recreated missing `.env` files with fail-closed safety flags.
- **P0 first-admin fix**: `/api/auth/setup` fail-closed (server-side bootstrap
  token, constant-time compare), atomic single-admin lock (unique-indexed sentinel),
  permanent lock. Proven: 9/9 adversarial + 12-way race → exactly 1 admin.
- Verified fail-closed posture: kill switch engaged on boot, live disabled, approval
  + paper gates on, SHADOW/PAPER default modes.
- Updated auth regression tests to secure contract; added adversarial cases.
- Docs in `docs/`: GIT_BRANCH_ARCHAEOLOGY_REPORT, FIRST_ADMIN_SECURITY_AUDIT,
  BOOTSTRAP_SECURITY_DESIGN, AUTHORIZATION_ENDPOINT_MATRIX, SECURITY_TEST_RESULTS,
  ARBICORE_X_CURRENT_ARCHITECTURE_AUDIT, FINAL_READINESS_REPORT.

## Readiness verdict: READY FOR SHADOW (PAPER+ BLOCKED)

## Prioritized backlog (P0 done; P1/P2 remaining — require live RPC, honest gaps)
- P1: FF main→c284183; deep economics re-audit (null size/liquidity, slippage double-
  count, gas single-count, flash repayment); executor/signer on-chain re-verify +
  RPC-list parsing bug check; fork simulation suite.
- P1: learning loop end-to-end proof (observe→update→rollback, no future leakage).
- P2: quote provenance, historical-replay leakage, evidence completeness audits.
- P2: source frontend version from backend (remove hardcoded v2.9.3 label);
  prod cookie secure=True behind TLS.

## Phase 2 (2026-09 continuation) — HEAD 90b337a
- 2A: Canonical c284183 MERGED into main (non-destructive, recovery tag
  recovery/phase1-p0-security). 107 commits recovered; P0 preserved.
- 2B/2C: Economics proven (15 tests); fixed size_optimizer None-liquidity crash.
- 2D: RPC comma-separated parsing fixed via first_rpc_endpoint() across resolver,
  simulator, gas oracle, 5 TechnicalValidator sites (6 tests).
- P0 hardening: dead-lock removed (self-healing sparse-unique admin_singleton),
  verified 19/19 by testing agent (iter_3); brute-force + info-leak fixes retained.
- Safety: /safety/status now reports both kill-switch stores + effective union.
- Docs: ECONOMICS_AUDIT.md, EXECUTOR_READINESS_AUDIT.md, FINAL_CERTIFICATION_PHASE2.md.
- Verdict unchanged: SHADOW=READY; PAPER/LIMITED_LIVE/FULL_AUTOMATION=BLOCKED
  (fork validation + live/archive RPC not provisioned — honestly blocked, not faked).
- Remaining (need operator RPC): 2E fork validation, 2F flash on-chain verify,
  live-RPC economics, learning-loop end-to-end proof, kill-switch store unification.

## Phase 3 continuation (2026-06 fork) — HEAD a4039f0 preserved, AUDIT-ONLY pass
- Delivered READ-ONLY audit: docs/STRATEGY_IP_AND_PHASE3_GAP_AUDIT.md.
- P0 blockers re-derived (all env-dependent, honestly fail-closed): B1 chain-ID,
  B2 executor bytecode (eth_getCode + EXECUTOR_ADDRESS), B3 atomic eth_call sim,
  B4/B5 anvil fork (anvil binary NOT installed + no archive RPC), B6 flash on-chain,
  B7 learning-loop outcome data. Env needed: ARBICORE_RPC_URL, ARBICORE_ARCHIVE_RPC_URL,
  ARBICORE_EXECUTOR_ADDRESS_BASE, anvil (Foundry), signer in vault (not .env).
- Strategy IP audit (16 surfaces): NO critical live exposure. Alpha
  (parameters/constraints/route_hints/capabilities) is admin-only, never logged,
  zero frontend exposure; registry stores identity-only, candidate store holds alpha.
  Field classes: PUBLIC(type,source_class) / INTERNAL(id,version,provenance meta) /
  CONFIDENTIAL(fingerprint,lineage,source_ref) / EXECUTION-SENSITIVE(params,constraints,
  route_hints,capabilities). EXEC-SENSITIVE must cross SF->ArbiCore to evaluate; egress
  already blocked.
- Genuine gap: enforced external provenance/originality. Recommended (NOT implemented,
  awaiting approval): F1 extend SourceClass (PUBLIC_RESEARCH/GENERATED/PROPRIETARY_EXTERNAL)
  + require source_ref + quarantine RESTRICTED (~40-60 LOC); F2 identity-only projection +
  confidential tag (~25-40); F3 fingerprint log->DEBUG (~2); F4 generic 422 (~6-10);
  F5 provenance tests (~60-90). None touch execution/safety.
- STOPPED after report per directive. Safety unchanged: SHADOW=READY; PAPER/LIMITED_LIVE/
  FULL_AUTOMATION=BLOCKED. main/execution/signer/kill-switch/Mongo/learning/Strategy IR untouched.

## Provenance governance F1-F4 + F5 tests (2026-06) — commit aaafbd1 (APPROVED, DONE)
- F1: SourceClass extended (PUBLIC_RESEARCH/INTERNAL/GENERATED/MUTATED/HYBRID/
  PROPRIETARY_EXTERNAL,RESTRICTED); external-origin classes require provenance.source_ref
  (fail-closed 422); restricted/proprietary quarantined on ingest (lifecycle=QUARANTINED)
  and refused by adapter/preview (409). schema.validate_provenance_policy()/is_restricted().
- F2: StrategyIR.public_view() identity-only projection (no params/constraints/route_hints/
  capabilities); candidate rows tagged confidential=true; adapter output tagged confidential.
- F3: fingerprint ingest log INFO->DEBUG. F4: forbidden-content route returns generic 422
  (no echoed key/path); detail to server log only.
- F5: tests/test_phase3_strategy_ir_provenance.py (16 cases). Additive only; NO change to
  execution/signer/broadcast/kill-switch/allowlists/profitability/simulation gates/learning/
  existing Mongo data. Two additive collections unchanged in shape (added lifecycle_state/
  restricted/confidential fields only).
- Tests: provenance 16 + IR unit 21 = 37 pass; Strategy IR API 65 pass; economics/RPC/optimizer
  29 pass; control_readiness + limited_live matrix pass. (P0 auth EmptyDbFailClosed tests fail
  ONLY due to dev DB already having a provisioned admin — pre-existing env state, unrelated.)
- Live re-verified: kill engaged, live_execution_enabled=false, effective_kill_engaged=true;
  readiness matrix SHADOW=GREEN(READY), LIMITED_LIVE/FULL_AUTOMATION=RED (readiness.py untouched).
- P0 RPC/fork/on-chain proofs remain honestly BLOCKED (no RPC/archive/anvil) — not attempted.

## MEV Intelligence pre-deployment READ-ONLY test (2026-09-03 chain UTC)
- READ-ONLY research; NO code/Mongo/gate/kill/execution changes. Safety unchanged
  (kill engaged, live_exec=false). Report: docs/MEV_INTELLIGENCE_PREDEPLOYMENT_TEST.md;
  evidence docs/mev_evidence/*.json; isolated probe scripts/mev_intel_readonly.py.
- Real Base mainnet (8453) data via public RPC mainnet.base.org. Window blocks
  50,831,821-50,833,821 (~67min, 16:32-17:38 UTC). 65 flash-loan txs, 40 reconstructed,
  7 arb-shaped (Balancer V2 flash + 2 Uniswap V3 legs, tiny gas ~2.5e-6 ETH, small notionals).
- BLOCKER (honest, not faked): public RPC has NO debug_trace*/trace_block -> searcher
  gross/net profit + builder bribe NOT reconstructable. ArbiCore quantitative replay also
  blocked: ARBICORE_RPC_URL unset -> economics/EV/sim need live quotes/liquidity.
- ArbiCore replay = qualitative: detectable YES, routes/DEX YES (UniV3/V2, Balancer modelled),
  executor PARTIAL (proven path Aave V3; today's arbs Balancer V2 = unverified path),
  economics/liquidity/EV/sim = DATA INSUFFICIENT. 0 proven capturable; nothing fabricated.
- To get monetised result: trace-enabled archive Base RPC (Alchemy/QuickNode debug_traceTransaction)
  + wire ARBICORE_RPC_URL. STOPPED after report per directive.

## P0#2 Base read-only RPC wiring (2026-06) — VERIFIED (no code change)
- Resolver already correct/fail-closed: ARBICORE_RPC_URL_BASE > ARBICORE_RPC_URL > BASE_RPC_URL
  (resolve_rpc_url_from_env/first_rpc_endpoint); None when unset -> callers fail fast.
- Wired ARBICORE_RPC_URL_BASE in THIS pod to public https://mainnet.base.org (read-only, no secret)
  purely to verify the mechanism; VPS uses its own RPC URL via the same key.
- Verified: /arbicore/rpc/check READY chain_id=8453 is_base=true block~50866421 (URL masked);
  eth_getCode reachable for UniV3 QuoterV2 / Aerodrome Router / Aave V3 Pool / Balancer Vault;
  WalletBalanceReader.read(base, public addr) returned real balance @block; resolver None when
  RPC env removed (fail-closed). flash-loan-prereqs: rpc_healthy READY, all other gates BLOCKED/WAIT.
- Safety unchanged: kill engaged, live_exec false; runtime autostart OFF; flash_loan_arb/dex_arb OFF;
  no signer/broadcast/execution; PAPER/LIMITED_LIVE/FULL_AUTOMATION blocked. No commit (env-only).
