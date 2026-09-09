# ArbiCore X v2 — Phase P0 Exit Report (Post-Astra Remediation)

**Date:** 2026-09-09 · **Branch:** `takeover/limited-live-seam-cc8db95`
**Authority:** Astra audit at commit `2e6f253dd354248e0ad861b2011bdfbcef63eb97` (`/app/audit_report.md`)
**Scope executed:** Phase P0 ONLY — H01, H02, H03, H04, H05, H06, H10. P1/M01–M07 and H07–H09 NOT started.
**Safety:** signing / broadcast / auto-exec / Full-Live remained OFF throughout. No production deploy, no merge to main, no real transaction. Protected files untouched.

---

## 1. H01–H10 status (7 P0 items addressed)

| ID | Title | Priority | Status | Verified by |
|----|-------|----------|--------|-------------|
| H01 | Unauthenticated network config can redirect signer RPC/executor | P0 | **FIXED** | testing_agent (401 unauth / 200 auth on `/settings/network/apply`,`/rollback`) |
| H02 | Unauthenticated per-strategy mode changes + spoofable actor | P0 | **FIXED** | testing_agent (401 unauth; server-derived actor recorded, spoof ignored) |
| H03 | Missing auth across operational mutation endpoints | P0 | **FIXED** | testing_agent (13-endpoint sample all 401 unauth; deny-by-default applied to 42 routes) |
| H04 | `_throttle(scope)` called with no arg → TypeError breaks atomic sim + wallet reads | P0 | **FIXED** | unit check (`_throttle(scope)` reachable; both callers pass host scope) |
| H05 | Probe-size quote ratio extrapolated to a larger dollar notional | P0 | **FIXED** | new regression suite `test_h05_exact_size_binding.py` (5/5) |
| H06 | Quoter reintroduces cross-chain RPC leakage (global Base alias) | P0 | **FIXED** | unit check (non-Base never picks global Base endpoint; fail-closed empty) |
| H10 | Executor identity can be READY on missing getters / cross-chain address | P0 | **FIXED** | unit check (None getters → UNKNOWN; mismatch → BLOCKED; base addr not leaked to eth) |
| H07 | Six-chain canonical flash composition incomplete | P1 | NOT STARTED (out of P0 scope) | — |
| H08 | Versioned receiver / per-chain deployments | P1/P2 | NOT STARTED | — |
| H09 | Multichain certification positive-path/simulation | P1 | NOT STARTED | — |

---

## 2. Files / code areas changed

Source (9 files):
- `server.py` — added request-scoped `_CURRENT_ACTOR` ContextVar + `_audit_actor()`; `_require_operator_dep` now stamps the server-derived actor; added `dependencies=[Depends(_require_operator_dep)]` to **42** `/arbicore/*` POST/PUT/PATCH/DELETE routes; replaced **21** client-supplied `actor` reads (`b.get("actor")…` / `(body).get("actor")…`) with `_audit_actor()`. (H01/H02/H03)
- `arbicore/execution/quoter.py` — `_rpc_url` / `_rpc_url_candidates` chain-scoped; global `ARBICORE_RPC_URL` / `PROVIDER_RPC_URLS` now Base-only aliases (H06).
- `arbicore/execution/atomic_executor_sim.py` — `_throttle(_throttle_scope(target))` (H04).
- `arbicore/capital/wallet_intelligence.py` — `_throttle(_throttle_scope(self._rpc))` (H04).
- `arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py` — optional `borrow_sizer`; emits `size_basis`/`exact_size`/`quoted_amount_in_wei`/`quote_notional_usd`/`borrow_token` (H05).
- `arbicore/scanners/flash_loan_arbitrage/verifier.py` — fail-closed `DENIED_SIZE_NOT_QUOTED` on probe-sized quotes; binds economics notional to `quote_notional_usd` (H05).
- `arbicore/runtime/composition.py` — M3 broadcast-time revalidation fails closed on non-exact size; binds `borrow_usd` to the quote's own notional (H05).
- `arbicore/scanners/flash_loan_arbitrage/live_readiness_probes.py` — fail-closed executor identity (positive selector + expected identity + all getter reads present + exact match; else UNKNOWN/BLOCKED); `resolve_executor_address` chain-scoped (H10).
- `arbicore/models/discovery.py` — new `VerifiedOutcome.DENIED_SIZE_NOT_QUOTED` (H05).

Tooling (non-P0, allowed): `eslint.config.js` — ESM → CommonJS (fixes recurring "linter engine error" in the no-`package.json` `/app` root).

New tests (2): `tests/test_h05_exact_size_binding.py`, `tests/test_p0_security.py` (authored by testing_agent).

**Protected files UNTOUCHED:** `arbicore/scanners/dex_arbitrage/scanner.py`, `deployment/compose/docker-compose.yml`, `deployment/cert/.env.example`.

---

## 3. Tests run — exact results

- **New H05 regression** `tests/test_h05_exact_size_binding.py`: **5 passed** (provider probe/exact stamping; verifier fail-closed on probe; notional bound to exact quote; backward-compat when `size_basis` absent).
- **Targeted offline suites** (live-quote/verifier/readiness/economics/pipeline): **131 passed** (3 live-RPC/E2E setup errors were credential/RPC-environmental).
- **Full offline unit sweep** (215 files, no live server): with-changes vs. baseline (my changes git-stashed) failure sets are **byte-identical** → **0 regressions** introduced. The 59 pre-existing offline failures are environmental (no operator RPC, empty Mongo, no anvil, harness needs a seeded CONFIRMED evidence bundle) and fail identically without my changes.
- **Focused unit verifications:** H04 `_throttle(scope)` callable; H06 no cross-chain leakage (ethereum/arbitrum fail-closed empty while base keeps global alias); H10 four identity cases (None-getters→UNKNOWN, missing-expected→UNKNOWN, all-match→READY, mismatch→BLOCKED) + address chain-scoping.

## 4. testing_agent live-backend results (`/app/test_reports/iteration_1.json`)

**19/20 passed (95%).** All 13 sampled state-changing endpoints returned **401 unauthenticated**; authenticated operator got **200** on `pipeline/evaluate` and `scanner/pause|resume`; invalid bearer → 401. The single failure was **admin seed drift** (a live-E2E test had bootstrapped a single-admin doc via `/api/auth/setup` with a different password; INSERT-ONLY `.env` seed could not overwrite it) — an environmental issue, since **resolved** by a clean reseed. Admin (`admin/ArbiCore2026!`) and operator (`operator/ShadowOperator!2026`) now both log in 200.

## 5. Authorization negative tests
- Unauthenticated mutation → **401** (13/13 sampled).
- Invalid bearer token → **401**.
- `/status` (Emergent template) intentionally left public — out of security scope.

## 6. H04 throttle verification
`quoter._throttle(scope)` requires a scope; both regressed consumers now compute `_throttle_scope(rpc_url)` and pass it. Direct call `await _throttle(_throttle_scope(url))` succeeds with no `TypeError`. RPC controls (per-host serialization, min-interval, retry) unchanged.

## 7. H05 exact-size / economic binding verification
Provider stamps `size_basis`; a probe-sized quote (Base `probe_amount` / non-Base `borrow_amount_wei`) is `"probe"` and the verifier **and** the M3 broadcast-time revalidation both **DENY** (`denied:size_not_quoted`) — it can never reach economics/Gate 7/CONFIRMED. When a `borrow_sizer` supplies an exact size, `quote_notional_usd` binds the economics notional to the SAME size the ratio was measured at. Regression test proves a `$250`-bound quote is evaluated at `$250`, not extrapolated to `$10,000`.

## 8. H06 chain-scoped RPC identity verification
Global `ARBICORE_RPC_URL` / `PROVIDER_RPC_URLS` are Base-only aliases. With a global set, `base` candidates include it; `ethereum`/`arbitrum` candidates are **empty (fail-closed)** — no cross-chain leakage. A chain-specific `ARBICORE_RPC_URL_ETHEREUM` is used only for ethereum.

## 9. H10 executor identity verification
READY now requires: positive entrypoint selector, KNOWN expected identity (registry vault+router), all getter reads (owner+router+vault) present, and exact vault/router match. Missing/unknown/unreadable → UNKNOWN; mismatch → BLOCKED; never READY. `resolve_executor_address` returns the Base env address only for Base mainnet; a non-Base chain resolves solely from the per-chain registry (else None).

## 10. Safety confirmation
`.env`: `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false`, `ARBICORE_DISCOVERY_AUTOSTART=false`. No signer/broadcast enabled; mode ladder unchanged; broadcast still requires LIMITED_LIVE (blocked). No real transaction attempted.

## 11. Git diff / commit status
Working-tree modifications only (NOT committed): 9 source files + `eslint.config.js`; 2 new untracked test files. `.env` files are pod-local and git-ignored (no secrets committed). Protected files show no modification. Push only via the "Save to Github" feature when the operator chooses.

## 12. Remaining P0 risk / VPS-only evidence
- H05 **exact-size** proof requires an operator price feed / `borrow_sizer` on the VPS. In this pod (no operator RPC, no price feed) the honest, fail-closed outcome is probe→DENY; exact-size CONFIRM is a VPS/operator runtime proof, not fabricated here.
- H06 endpoint **chain-identity assertion** (eth_chainId challenge before use/failover) is recommended defense-in-depth for a follow-up; the P0 leakage root cause (endpoint selection) is fixed and fails closed.
- H10 on-chain READY still requires a real deployment + archive RPC on the VPS to exercise the positive path; the fail-open classification defect is fixed here.

**STOP — P0 complete. Not proceeding to P1 per directive.**
