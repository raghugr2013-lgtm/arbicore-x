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
