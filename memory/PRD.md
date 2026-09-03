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
