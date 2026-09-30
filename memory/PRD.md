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

## Engineering Handoff (2026-06 fork) — multi-chain arbitrage completion
- Source: GitHub branch emergent/arbitrage-engineering-handoff-20260930 (commit
  5bd9525), handoff doc VPS_CURRENT_STATE_HANDOFF.md (read in full).
- Base lineage decision (user-confirmed): build on /app main (H05/H06 lineage,
  HEAD 14d0c9e). Handoff baseline 4fec11f is NOT an ancestor of /app main → do
  NOT merge production baseline; keep isolated from production. No push from /app
  (Save to GitHub only). No live RPC/VPS here → live evidence is Codex/VPS-side.
- Priority order P0..P7 (see handoff). Deliver in controlled, tested slices.
- Machine-readable matrix: /app/capability_matrix.json (states: IMPLEMENTED_AND_
  VALIDATED / IMPLEMENTED_BUT_AUTH_REQUIRED / IMPLEMENTED_BUT_LIQUIDITY_UNPROVEN /
  ADAPTER_INCOMPLETE / UNSUPPORTED / VALIDATION_REQUIRED). implementation_status
  kept separate from live_validation_status (NONE until Codex validates).

### P0 — Balancer V2 quote adapter (DONE, VALIDATION_REQUIRED) — 2026-06
- New: arbicore/discovery/balancer_v2_pool_discovery.py — read-only on-chain pool
  discovery (getPoolId/getPoolTokens/getSwapFeePercentage/decimals) + Vault
  queryBatchSwap single-swap quote. Fail-closed vocabulary; UNKNOWN never→0.
  Injected eth_call → offline-testable. Chains: ETH/BASE/ARB/OP/POLYGON; BNB
  UNSUPPORTED (Vault not deployed). Pool ENUMERATION-by-pair NOT done (needs
  events/subgraph) → VALIDATION_REQUIRED limitation.
- Modified: arbicore/execution/quoter.py — added BalancerV2Quoter backend
  (dex="balancer_v2"), registered in QuoterRegistry default_backends. gas=None.
- Tests: tests/test_p0_balancer_v2_quote.py — 40 passed (registration, happy path,
  provenance, fee→bps, decimals, ordering, pool_id derivation+mismatch, unknown
  pool, rpc/rate-limit, malformed, unknown fee/decimals, HTTP 401/403/404/5xx,
  token-not-in-pool, zero/insufficient liquidity, quote revert, no-output, stale,
  never-positive-on-error). Quoter regression 66 passed. git diff --check clean.
- Evidence is Emergent mocked/offline only. NO live six-chain proof.
- STOP after P0 for user review before P1 (Sushi/Pancake/Curve).

### P1 — Balancer V2 automatic pool enumeration (DONE, review-pending) — 2026-06
- User froze P0 (commit f27da21, branch emergent/p0-balancer-v2-20260930); P0
  Ethereum now LIVE VALIDATED read-only on VPS ($1k USDC exact-size + UniV3<->Bal
  cycles, both gross-negative → no execution eligibility). P0 files NOT modified.
- New: arbicore/discovery/balancer_v2_pool_enumeration.py — enumeration layer
  AROUND P0. Injectable BalancerV2PoolSource; default SubgraphBalancerV2PoolSource
  (env-configured per chain ARBICORE_BALANCER_SUBGRAPH_URL_<CHAIN> + optional
  ARBICORE_BALANCER_SUBGRAPH_API_KEY; no hardcoded endpoint/creds; fail-closed to
  DISCOVERY_UNAVAILABLE). Discovery is CANDIDATE-ONLY → every candidate re-validated
  on-chain via P0 discover_and_quote() before quoting. Dedupe, wrong-vault +
  token-pair filtering, ranking (best output first). discovery_unavailable is a
  distinct state, never collapsed to zero. Chains ETH/BASE/ARB/OP/POLYGON; BNB out.
- Reuses P0 symbols only (discover_and_quote / BalancerV2Quote / vault map / OK);
  no second quote path. P0 module byte-for-byte unchanged.
- Tests: tests/test_p1_balancer_v2_enumeration.py — 36 passed (single/multiple/
  duplicate/token-pair/unsupported-chain/discovery-unavailable/malformed-discovery/
  invalid-address/pool-id-mismatch/wrong-vault/missing-identity/unknown-decimals/
  zero-liquidity/stale/unknown-fee/quote-revert/malformed-quote/zero-output/
  negative-output/selection+ranking/max-candidates/all-5-chains/P0-preserved/
  subgraph missing-url+unsupported+transport+non200+malformed+ok+e2e).
- Combined regression (P0+P1+quoter+discovery) 173 passed; git diff --check clean.
- Matrix: capability_matrix.json → balancer_v2 split into p0_pool_scoped_quote
  (ethereum IMPLEMENTED_AND_VALIDATED/VALIDATED; others VALIDATION_REQUIRED/NONE)
  + p1_auto_enumeration (5 chains IMPLEMENTED_BUT_AUTH_REQUIRED / live NONE).
- Evidence is Emergent mocked/offline only. NO live enumeration proof.
- STOP after P1. Do not merge/deploy/enable execution. P2 (Sushi/Pancake/Curve)
  NOT approved.

### P1b — On-chain Balancer V2 PoolRegistered discovery source (DONE) — 2026-06
- Context: VPS confirmed all ARBICORE_BALANCER_SUBGRAPH_URL_* + API_KEY NOT_SET →
  live P1 enumeration blocked on subgraph. P1 commit 334385e (P0 f27da21). Added
  the previously-proposed no-credential on-chain source.
- New: arbicore/discovery/balancer_v2_onchain_source.py — OnChainPoolRegisteredSource
  implements existing BalancerV2PoolSource protocol via bounded/chunked read-only
  eth_getLogs of Vault PoolRegistered(bytes32,address,uint8). Guards: canonical
  Vault emitter, poolId-embeds-address (no fabrication), left-padded addr topic,
  topic0 match. Candidate-only → token membership NOT inferred from event; every
  candidate re-validated via FROZEN P0 discover_and_quote() in unchanged
  enumerate_and_quote. No API key (canonical RPC). Env: WINDOW_BLOCKS/CHUNK_SIZE/
  FROM_BLOCK_<CHAIN>. Fail-closed: DISCOVERY_UNAVAILABLE (no fetcher/unresolved
  range/RPC/rate-limit) distinct from OK+zero; MALFORMED on bad log; UNSUPPORTED
  chain; BNB out. Public discover_candidates(chain, from_block, to_block) = the
  deterministic live API for Codex.
- P0 discovery, P1 enumeration, quoter.py ALL byte-for-byte unchanged (git diff
  empty). No second quote path.
- Tests: tests/test_p1b_balancer_v2_onchain_source.py — 19 passed (decoding,
  multiple/duplicate/empty, malformed/too-few-topics/wrong-vault/poolid-mismatch/
  wrong-topic0, rpc-failure/rate-limit/non-list, chunking+aggregation, invalid
  range, unsupported chain, no-fetcher, window resolution, provenance-no-URL-leak,
  token-pair filtering through P0 e2e). Combined regression 192 passed. diff-check
  clean.
- Matrix: capability_matrix.json p1_auto_enumeration.discovery_sources adds
  balancer_v2_onchain_pool_registered (status IMPLEMENTED / live NONE).
- Mocked/offline only. NO live eth_getLogs evidence. STOP. No merge/deploy/exec.

### GENERIC_DEX route engine (DONE, review-pending) — 2026-06
- P1b frozen/accepted (on-chain source implementation-complete; historical
  eth_getLogs constrained by current RPC providers — accepted, do not change
  chunk defaults). Next package = DEX-to-DEX GENERIC_DEX route engine.
- New: arbicore/scanners/generic_dex_route_engine.py — GenericDexRouteEngine.
  Buy venue A / sell venue B, same-token atomic cycle. Read-only orchestrator
  composing ONLY validated blocks: QuoterRegistry (UniV3 + Balancer V2) exact-size
  quotes; H05 MultichainPriceSource + registry decimals for exact-size borrow;
  flash-fee catalog + FlashLoanEconomicsAssessor (aggregate_economics) for the
  net-profit gate. NO new quote path, NO new economics math.
- Immutable $25 floor (constructor may only RAISE it, never lower — clamped).
  Fail-closed: UNKNOWN_PRICE/UNKNOWN_DECIMALS/LEG1|LEG2_QUOTE_FAILED (unknown/
  insufficient liquidity surfaces here)/UNKNOWN_GAS (never silent default)/
  UNSUPPORTED_FLASH_PROVIDER/SAME_TOKEN_VIOLATION/INVALID_ROUTE; non-positive→
  NON_POSITIVE_NET, below floor→BELOW_PROFIT_FLOOR; optional pool-TVL gate
  (UNKNOWN_LIQUIDITY/INSUFFICIENT_LIQUIDITY). Quote-inclusive (no double swap
  fee). Six-chain preserved (flash provider supports_chains gate). No exec/sign/
  broadcast.
- Tests: tests/test_generic_dex_route_engine.py — 30 passed (real economics math;
  eligible/below/non-positive/negative-gross, same-token, invalid addr, flash
  provider unknown/unsupported-chain, unknown price/decimals, leg1/leg2 fail,
  unknown gas + estimator, TVL gate, immutable floor cannot lower / can raise,
  flash fee applied, quote-inclusive no-double-fee, provenance/pipe, six-chain
  parametrized). Regression 151 passed (generic_dex + balancer P0/P1/P1b + quoter).
- KNOWN pre-existing UNRELATED failure: protected test_flashloan_partial_quote_
  economics.py fake backend lacks quote_route's max_retries kwarg (present in
  parent 14d0c9e, before all my work). NOT caused by / NOT modified by this
  package (protected file).
- Existing code untouched (only new module + new test + matrix). Mocked/offline
  only — NO live evidence. STOP for VPS validation. Other route families
  (TRIANGULAR/STABLECOIN/MULTI_HOP/LST_LRT/CROSS_CHAIN) subsequent.
