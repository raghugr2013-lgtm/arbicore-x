# ArbiCore X v2 — Phase P1 Batch 1 Exit Report

**Date:** 2026-09-09 · **Branch:** `p1-batch1-m01-m06-m07-h06` (derived from P0 baseline `p0-remediation-h01-h10`)
**Scope (approved 1a/2a/3a):** M01, M06, M07, H06 chain-ID guard, + safe in-pod H07 correctness. H08/H09 runtime work DEFERRED (VPS/operator). No merge to main, no deploy, no real tx. Safety envelopes stayed OFF. Protected files untouched.

---

## 1. M01 — Evidence-tier model — DONE
New canonical module `arbicore/certification/evidence_tiers.py`: one strictly-ordered `EvidenceTier` ladder —
`UNKNOWN < SYMBOLIC < CONNECTED < DISCOVERED < QUOTED < ROUTE_CONSTRUCTABLE < EXECUTION_CAPABLE < CANDIDATE_CERTIFIED < SIMULATION_CERTIFIED < RUNTIME_CERTIFIED < LIMITED_LIVE_ELIGIBLE`.
- `NON_CERTIFYING_SIM_METHODS` (noop/symbolic/estimate_symbolic/paper/heuristic/capability/availability/…) and `CERTIFYING_SIM_METHODS` (atomic_exact/atomic_state_override/fork_exact/exact_call).
- `is_certifying_sim_method()` / `sim_evidence_tier()` fail closed on unknown methods.
- **Invariant enforced:** a NoopSimulator/symbolic/paper/heuristic result — even with `ok=True` — maps to at most `EXECUTION_CAPABLE`, never `SIMULATION_CERTIFIED`+.

## 2. M06 — One authoritative readiness flow — DONE (boundary enforced)
- Authoritative surface remains the existing `ShadowCertificationEngine` + `ExecutionCertifier` (`CertificationStatus`); **no parallel framework created.**
- `ExecutionCertifier` simulation stage rebound: a PASS now requires an EXACT candidate-bound method. A heuristic/mocked sim is emitted as `INFO` with `evidence_tier` + `simulation_certified:false` and adds a WARNING so the overall verdict is **capped at WAIT** — it can never reach PASS on infra/heuristic evidence.
- **Invariant enforced:** Component READY ≠ Candidate READY ≠ Simulation PASS ≠ Runtime Certified ≠ Limited-Live Eligible.

## 3. M07 — Remove false financial readiness — DONE
`server.py` vault/exchange surfaces no longer fabricate READY/CONNECTED custody or exchange rows:
- `GET /arbicore/settings/vaults`, `GET /arbicore/settings/exchanges`: every item `state=NOT_CONFIGURED`, `evidence_tier=MOCKED`, null address/api_key/timestamps; envelope `mocked:true`, `contributes_to_readiness:false`.
- `POST …/vaults/{v}/reconcile`, `POST …/exchanges/{k}/test`: `ok:false`, `NOT_CONFIGURED`, `mocked:true` (no fake success/latency/timestamp).
- **Invariant enforced:** mocked/unconfigured financial state is visibly MOCKED/NOT_CONFIGURED and excluded from readiness.

## 4. H06 — RPC chain-identity guard — DONE
`arbicore/execution/quoter.py`:
- `_EXPECTED_CHAIN_IDS` (base 8453, ethereum 1, arbitrum 42161, optimism 10, polygon 137, bnb 56).
- `_read_chain_id()` (READ-ONLY eth_chainId, fail-closed None), `_endpoint_serves_chain()`, `_verified_chain_endpoints()`; per-host cache (successful reads only ⇒ transient failure re-probes).
- Applied in `quote_route` to **endpoint selection AND failover** (not diagnostics): only endpoints that PROVE they serve the intended chain are used; wrong/ambiguous/unreadable ⇒ dropped; none verified ⇒ empty ⇒ fail-closed break_even.
- Guard is ON for production (default backends); OFF only when custom `backends=` are injected (unit stubs) or overridable via `verify_chain_identity=`.

## 5. H07 — Safe in-pod correctness — PARTIAL (safe fixes done; runtime deferred)
- `make_live_quote_provider` is now `tvl_provider_chain`-scoped (default `"base"`): a route on any other chain does **not** consume the Base-scoped TVL provider — depth is left absent ⇒ Gate 8 fails closed. **No cross-chain TVL leakage into Base-bound (or any-chain-bound) economics.**
- Combined with P0 H06 endpoint chain-scoping + this H06 chainId guard: non-Base composition fails closed wherever required per-chain evidence (RPC, depth) is unavailable.
- **Remaining (VPS):** full six-chain scanner→resolver→quote→liquidity→economics→route→execution wiring requires operator per-chain RPC + a per-chain TVL/price provider; not provable in-pod.

## 6. H08 — Versioned receiver / execution fabric — DEFERRED
No change this batch (per directive). Owner/provider authorization, repayment protections, and unsupported-venue checks left intact and un-weakened. Receiver deployment/production execution remains deferred to VPS.

## 7. H09 — Candidate-bound simulation — FOUNDATION (M01) only
M01 now guarantees Anvil availability / a boolean simulator result / infra readiness cannot be treated as a simulation PASS (see §2). The genuine candidate-bound exact simulator itself is deferred to VPS (needs fork/state-override against live chain state).

## 8. Exact-size economics (H05) — PRESERVED
H05 fail-closed behavior unchanged; probe-size economics still cannot be extrapolated. The exact-size `borrow_sizer` remains the VPS/operator wiring point (price feed) — tracked, not fabricated.

## 9. Six-chain capability matrix (pod)
| Chain | chainId | endpoint chainId guard | RPC configured (pod) | TVL provider (pod) | Composition status in pod |
|-------|---------|------------------------|----------------------|--------------------|---------------------------|
| Base | 8453 | ✅ enforced | ❌ none (ARBICORE_RPC_URL unset) | base-scoped (not wired here) | fail-closed (no RPC) |
| Ethereum | 1 | ✅ enforced | ❌ | none | fail-closed |
| Arbitrum | 42161 | ✅ enforced | ❌ | none | fail-closed |
| Optimism | 10 | ✅ enforced | ❌ | none | fail-closed |
| Polygon | 137 | ✅ enforced | ❌ | none | fail-closed |
| BNB | 56 | ✅ enforced | ❌ | none | fail-closed |
All six are chain-identity-guarded and fail closed in-pod (no operator RPC). Real per-chain operation is a VPS/operator runtime proof.

## 10. Evidence / readiness state model
See §1. Every readiness/certification result must map to exactly one `EvidenceTier` and may not claim a tier above its strongest positive, candidate-bound evidence. Infra/heuristic/mocked → never SIMULATION_CERTIFIED+.

## 11. Tests & exact results
New regression suites (all green):
- `tests/test_m01_evidence_tiers.py` — **6/6** (tier ordering; noop/symbolic/paper non-certifying; only exact methods certify; ok+noop ↛ certified; NoopSimulator result non-certifying).
- `tests/test_h06_h07_chain_isolation.py` — **6/6** (six-chain expected ids; endpoint must match chainId; unreadable fail-closed + re-probe; failover filters to verified in order; guard on default-backend / off injected-backend; base-scoped TVL not consulted off-chain).
- `tests/test_m07_truthfulness.py` (testing_agent) — **10/12** (all 4 truthfulness contracts + all 4 POST authz-401 + 2 authorized-200; the 2 "fails" are the two settings GETs returning 200 unauth — see §13).
- `tests/test_h05_exact_size_binding.py` (P0) still **5/5**; `tests/test_p0_security.py` still **20/20**.
Regression deltas (with-P1 vs P1-stashed baseline): certification suites IDENTICAL; per-area quoter/live-quote suites — 2 fixtures updated to the new chain-scoped contract (multichain TVL declares its chain; live-quoter RPC stub answers eth_chainId), and 2 error-message/`test_unsupported_chain` items confirmed pre-existing (fail identically with P1 stashed). **No new regressions attributable to P1.**

## 12. testing_agent results
`/app/test_reports/iteration_2.json` — backend 10/12 (83%). All M07 truthfulness + all state-changing authz intact. Two minor deviations = read-side authz on 2 GET settings endpoints (see §13). `/app/test_reports/iteration_1.json` = P0 (19/20).

## 13. Negative / fail-closed results
- H06: eth-node for a base request, wrong/unknown chainId, unreadable endpoint, unknown target chain → all fail closed (endpoint dropped; empty ⇒ break_even).
- H07: base-scoped TVL provider never consulted for a non-base route.
- M06: heuristic/noop sim → verdict capped at WAIT (never PASS).
- M07: reconcile/test return ok:false; all four state-changing POSTs 401 unauth.

## 14. Git branch / commit / diff status
Branch `p1-batch1-m01-m06-m07-h06` (off P0 baseline). Working-tree changes (NOT committed): modified `server.py`, `arbicore/execution/quoter.py`, `arbicore/execution/certification.py`, `arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py`, and 2 test fixtures; new `arbicore/certification/evidence_tiers.py` + 3 test files. `.env` git-ignored (no secrets committed). Push via "Save to GitHub" at operator discretion.

## 15. Safety confirmation
signing / broadcast / auto-exec / Full-Live remained OFF (`ARBICORE_*_AUTOSTART=false`). No receiver deployed, no real transaction. Protected files (`dex_arbitrage/scanner.py`, `deployment/compose/docker-compose.yml`, `deployment/cert/.env.example`) untouched.

## 16. Remaining blockers / required VPS-operator evidence
- Per-chain operator RPC + per-chain TVL/price providers (H07 real six-chain proof; H05 exact-size sizer).
- Genuine candidate-bound exact simulator against live/forked state (H09) and versioned receiver deployment (H08) — VPS only.
- Optional/out-of-scope: read-side authz on the two settings GETs (`/arbicore/settings/vaults`, `/arbicore/settings/exchanges`) — currently 200 unauth, consistent with the app's existing public-GET posture; bodies are truthful with no secrets. Adding read authz would be a separate, app-wide decision beyond Batch 1.

**STOP — P1 Batch 1 complete. Awaiting explicit approval before Batch 2. No further P1 workstreams, no H08 receiver deployment, no Limited Live.**
