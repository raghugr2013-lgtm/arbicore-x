# P0 #3 — Real Base Flash-Loan / DEX Discovery Activation (READ-ONLY)

Date: 2026-09-04
Branch: `phase3/final-proof-completion`
Envelope: Base (8453) + Aave V3 flash liquidity + Uniswap V3 swap legs (flash_loan_arb only)
Scope: DISCOVERY / VALIDATION ONLY. No signer, signing, broadcast, withdrawal, automation, live mode.

## A. Base network enablement result
Approved mechanism used (no direct Mongo writes): `POST /api/arbicore/settings/network/apply`
with patch `{"rpc_urls":{"base":["https://mainnet.base.org"]},"chains_enabled":{"base":true}}`.
Result: `ok=true`, `env_synced=[ARBICORE_RPC_URL, ARBICORE_RPC_URL_BASE, BASE_RPC_URL]`,
`rpc_urls.base=["https://mainnet.base.org"]`.
`flash-loan-prereqs.base_network_enabled` flipped **BLOCKED → READY** ("chain 'base' enabled and RPC configured").
`rpc_healthy = READY` (chain_id=8453, live block 50867868).

## B. Scanner / source enablement result
Via existing authenticated APIs (no direct Mongo):
- `providers/aave_v3/enable` → aave_v3=True
- `providers/uniswap_v3/enable` → uniswap_v3=True (balancer_v2 left False per envelope)
- `chains/base/enable` → base=True (all other chains False)
- `flash_loan_arb/resume` → scanner_state.enabled=True
dex_arb NOT enabled (deferred per operator). CEX/funding NOT enabled. No other chains enabled.

## C. Real opportunities discovered
0 canonical FLASH_LOAN_ARBITRAGE opportunities persisted. Honest zero — see §L.

## D. Candidate count
32 genuine route candidates generated from the canonical Base pool-registry graph in the
first post-resume tick (`candidates_claimed=32`), from 94 real routes explored
(`route_engine.last_explored=94`). These are real graph routes, not synthetic.

## E. Verified count
0. All 32 candidates were denied at `venue_unreadable` because the running server scanner is
fail-closed on the **noop quote provider** (T0-1). The boot-time live-quote wiring
(`activate_canonical_flash_loan_scanner`) did not complete because it performs on-chain
Aerodrome pool resolution (many eth_calls) inside the 8s boot budget, which the rate-limited
public RPC (`mainnet.base.org`, HTTP 429) cannot satisfy. Refusing to emit on noop is correct
fail-closed behavior — not a defect.

## F. Canonical opportunity count
0 (gate-analysis totals: observed=0, validated=0, rejected=0).

## G. Economics / EV results
Not reached in the automated pipeline (0 verified candidates). The economics/EV/gate engines
are present and unit-tested (see §N). The live economic inputs require a completed live-quote
sweep, which is RPC-bound (see §L).

## H. Size-optimization results
Borrow-size optimization present (`scanners/flash_loan_arbitrage/borrow_sizing.py`); not
exercised end-to-end in-pod for the same RPC reason.

## I. Dynamic-capital results (P0 #1 verification)
CONFIRMED wired and fail-closed; NO fixed initial-capital assumption:
- `execution/live_signer.py` calls `resolve_operating_capital(wallet_balance_usd, gas_cost_usd)`
  → `reference_capital_usd` feeds the capital allocator; `balance_delta_ok(...)` revalidation gate.
- `execution/pipeline.py` derives `reference_capital_usd` from the LIVE wallet-balance provider
  (`_capital_balance_provider()`); when no provider is wired it fails closed to informational
  (`capital_info:wallet_balance_unavailable`) — never a fixed amount.
- `execution/capital_policy.py` sizes `wallet_limit = reference_capital_usd * wallet_pct`.
- grep for `5000` / `5_000` / fixed initial-capital in live_signer/pipeline/capital_policy: NONE.
- `dynamic_capital.gas_reserve_usd()` protected reserve gate active; liquidity/optimal-sizing gates active.
- Tests: `tests/test_phase3_dynamic_capital.py` PASS.
In the pod there is no gas wallet/signer, so the pipeline capital stage correctly reports
`wallet_balance_unavailable` (fail-closed) rather than assuming capital.

## J. Simulation results
11-check / atomic + settlement simulation is gated on a deployed executor address
(`ARBICORE_EXECUTOR_ADDRESS_BASE`) and a signer — both absent by design in the pod, so the
atomic gate returns `available=False` ("executor not set" / "signer not present"). Fail-closed.

## K. Evidence generated
No verified-candidate evidence bundles (0 verified). Genuine artifacts captured:
- Live UniV3 quote proof (real eth_call): 0.1 WETH → 246.076812 USDC @ fee 500ppm and
  246.015462 USDC @ 3000ppm at Base block 50868098, QuoterV2 `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a`
  (`POST /api/arbicore/wizard/opportunity-probe`, chain=base).
- 32 genuine route candidates from 94 explored routes (first tick stats).

## L. Zero-opportunity explanation
The public endpoint `https://mainnet.base.org` is aggressively rate-limited (HTTP 429). Two
consequences, both RPC-bound (not code):
1. Boot-time live-quote wiring stalls on on-chain Aerodrome pool resolution → scanner stays on
   the fail-closed noop provider → candidates denied `venue_unreadable`.
2. A standalone, live-wired single tick (`run_single_canonical_flash_loan_audit_tick`) times out
   on the 429 storm even at candidate_cap=2.
The live-quote PATH itself is proven working via the bounded single-pair probe (§K). A dedicated
Base RPC (Alchemy / Infura / QuickNode) is required for a complete multi-candidate discovery
sweep. Per directive §8: **INFRASTRUCTURE / DISCOVERY NOT YET SUFFICIENT FOR GENUINE
CERTIFICATION**. Shadow NOT started.

## M. Safety-state verification (post-activation)
- kill_switch: **ENGAGED**
- executor_verified: BLOCKED (no executor address)
- wallet_registered / secret_available: BLOCKED (no gas wallet, no signer)
- flash_loan strategy mode: **SHADOW**; quote_provider readiness: active=False, provider=noop
- auto-executor: not running; post-trade receipts: count=0 (no broadcast ever)
- No transaction signed or broadcast.

## N. Tests
`pytest` (9 suites incl. dynamic capital, cert grading, D-6 economics/gates, flash candidate
progression, m2.1 live quote provider, provider optimizer, control readiness):
**88 passed, 1 failed, 8 errors**.
- FAIL `test_flashloan_partial_quote_economics::...intermediate_unit_output`: PRE-EXISTING —
  a test-fake `_RevertFinalHopBackend.quote_hop()` lacks the `max_retries` kwarg that
  `quoter.py:810` (commit 7aea7c0, pre-existing) passes. No code changed by this task.
- 8 ERRORS `test_capital_api_endpoints`: PRE-EXISTING env/auth (need running server + login).
No NEW failures introduced (no application code was modified in this task).

## O. Remaining blockers to genuine Paper
- A completed live-quote discovery sweep producing ≥1 verified candidate (needs a dedicated
  non-rate-limited Base RPC so boot-time live-quote wiring completes within budget).

## P. Remaining blockers to genuine Shadow
- Same dedicated RPC; then a run with opportunities_processed > 0 and a real (non-infra-only)
  executable-evidence grade.

## Q. Remaining blockers to Limited Live
- Deployed FlashLoanReceiver executor + `ARBICORE_EXECUTOR_ADDRESS_BASE`, ingested signer whose
  derived address matches the gas wallet, genuine Shadow + Paper certification, anvil fork
  validation, explicit operator regime authorization. Kill switch remains authoritative.

## R. Exact next recommended step
Point the runtime (pod and/or VPS) at a dedicated Base RPC and re-run boot-time live-quote
activation, then confirm the flash-loan scanner reports `quote_provider=live` and produces
verified candidates before considering Paper. STOP here for operator approval.
