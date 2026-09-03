# ArbiCore X — Phase 2 Final Certification

Evidence-backed. GREEN = independently proven here; YELLOW = implemented + partially
proven, needs live/archive RPC to fully certify; RED = not present/blocked.
**No live execution, no broadcast, no secrets requested/exposed, no fabrication.**

## 2M — Subsystem matrix

| Area | Status | Evidence |
|---|---|---|
| GIT | GREEN | Canonical `c284183` merged into `main` (HEAD `41cb9bb`), non-destructive; recovery tag `recovery/phase1-p0-security`; 107 canonical commits recovered without losing P0. |
| AUTH | GREEN | login/me/refresh/logout/change-pw + httpOnly cookies; brute-force proxy-aware + username-scoped (iteration_1/2/3). |
| BOOTSTRAP | GREEN | Fail-closed token gate; **self-healing** sparse-unique `admin_singleton` (dead-lock removed); 12-way race → exactly 1 admin (iteration_3, 19/19). |
| KILL SWITCH | YELLOW | Fail-closed on boot (both stores engaged). `/safety/status` now reports **both** stores + `effective_kill_engaged` (fail-closed union). Full unification of the two stores deferred (material execution-arch change → operator boundary). |
| SCANNER / DISCOVERY / ROUTE SEARCH | YELLOW | Present; autostart fail-closed OFF in `.env`. Live observation needs RPC. |
| QUOTES / FRESHNESS | YELLOW | `quote_status=="REAL"` gate in sim gate; provenance modeled. Live quotes need RPC. |
| LIQUIDITY | GREEN(model) / YELLOW(live) | Depth-aware impact; missing/zero/None liquidity → fully-impacted, fail-closed (crash fixed). |
| GAS | GREEN | Counted once; zero unless full (wei,units,price) triple; RPC gas oracle now comma-safe. |
| ECONOMICS | GREEN | 15 deterministic proofs; negative stays negative; unknown stays infeasible (`ECONOMICS_AUDIT.md`). |
| OPTIMIZER | GREEN | Grid + bisection, max-EV, never exceeds cap/liquidity; null=no-feasible-with-evidence. |
| FLASH LIQUIDITY | YELLOW | Providers modeled (aave_v3/balancer_v2 sim-gate allowlist), fee/premium/repayment in economics. On-chain availability needs RPC → unverified providers stay BLOCKED. |
| EXECUTOR | YELLOW | RPC comma-parse bug fixed across all consumers + 5 `TechnicalValidator` sites (`EXECUTOR_READINESS_AUDIT.md`, 6 tests). On-chain bytecode/ABI/chain-id verification needs RPC → BLOCKED. |
| CALLDATA | YELLOW | `calldata_present` sim-gate check enforced; on-chain calldata validity needs fork RPC. |
| SIMULATION | GREEN(gate) / YELLOW(on-chain) | 11 hard sim-gate checks proven; any false/unknown ⇒ not executable. On-chain eth_call/fork needs RPC. |
| FORK VALIDATION | BLOCKED | Requires archive/read-only RPC endpoint — **not provisioned** in this environment. Cannot be truthfully certified. |
| HISTORICAL REPLAY | YELLOW | Present; leakage re-audit deferred (needs data + time). |
| LEARNING | YELLOW | Advisory-only proven: confidence never flips a hard gate (`test_confidence_never_flips_execution`); learning reads outcomes, emits weights/recommendations, cannot touch kill/broadcast/execution. Full loop (observe→update→rollback) not end-to-end re-proven. |
| PROVENANCE | YELLOW | Evidence bundles + Ed25519 evidence signer present (audit signer, NOT a tx signer). |
| DATABASE | GREEN | Additive only; no drops/resets; existing collections preserved; merge did not touch data. |
| API SECURITY | GREEN | Endpoint matrix; auth-gated routers; 401/403 verified. |
| FRONTEND | YELLOW | Auth wired + bootstrap token field; version label still hardcoded (deferred, §5/§38). |
| DEPLOYMENT | GREEN | Services healthy on canonical code; `.env` fail-closed; recovery tag exists. |
| REGRESSION | GREEN(targeted) | 28 deterministic + 19 auth/safety = 47 targeted tests pass; full legacy suite has pre-existing env/RPC-dependent failures (documented, not caused here). |

## Mode verdicts (unchanged — evidence-gated)

- **SHADOW = READY** — fail-closed posture proven; economics/optimizer/RPC correct.
- **PAPER = BLOCKED** — needs live-RPC economics + fork validation + learning-loop proof.
- **LIMITED_LIVE = BLOCKED** — needs on-chain executor/signer/calldata/repayment/fork proof.
- **FULL_AUTOMATION = BLOCKED** — all higher prerequisites unproven.

## Genuinely-blocked items (require operator-provided archive/read-only RPC)
Fork validation (2E), on-chain executor/flash-provider verification (2D/2F live),
and live-quote/liquidity economics. These are marked BLOCKED, never faked GREEN.
