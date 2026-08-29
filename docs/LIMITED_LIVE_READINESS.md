# ArbiCore X — Limited-Live Readiness & Runtime Configuration

Status: **CODE READY (audit tooling + safety chain) — VPS VALIDATION REQUIRED.**
This document is the single source of truth for what the *application* enforces
in code vs. what the *runtime* (VPS) must supply, and which readiness controls
are still MISSING before a genuine `LIMITED-LIVE READY` classification.

No signer secrets or private keys are documented here, by policy.

## 1. Attributable audit workflow (fixed)
The canonical VPS audit is driven by `scripts/run_vps_validator_audit.sh`
(hermetic guards) with an optional live phase (`ARBICORE_RUN_LIVE_AUDIT=1`,
requires `MONGO_URL`+`DB_NAME`) that runs `python -m scripts.vps_canonical_audit`:

1. wire the canonical scanner (live quote provider + fail-closed Gate-8 TVL +
   evidence sink) via `run_single_canonical_flash_loan_audit_tick()`;
2. execute **exactly one** `_tick()`;
3. capture the **actual** `audit_run_id` + `scanner_tick_id` (never guessed,
   never derived from timestamps);
4. read back every candidate of that exact run+tick via
   `EvidenceBundlesRepo.find_for_audit(audit_run_id, scanner_tick_id)`
   (`candidate_id` optional);
5. enforce candidate-level exact matching (`evidence_matches_audit`);
6. emit a candidate ledger (ids/status only, no secrets);
7. hand ONLY exact-run CONFIRMED evidence to M3 via env selectors;
8. stop. M3 fails closed if nothing matches (never borrows foreign evidence).

Isolation is fail-closed: `audit_run_id`+`scanner_tick_id` are mandatory and
exact; foreign runs, missing provenance, blank/typed-wrong selectors, Mongo
operator documents, timestamps, and candidate-id-alone can never select records.

## 2. Enforced in code (safety chain)
- Quote integrity: partial/reverted/missing/malformed/non-cyclic quotes can
  never produce gross/net profit, pass Gate 7, or become CONFIRMED.
- Gate 7 (atomic profit floor), Gate 8 (route TVL, fail-closed on unverifiable),
  Gate 9 (MEV cap, fail-closed without real congestion).
- Executor capability: M3 (`composition.fresh_fn`) DENIES any route whose pools
  are not `uniswap_v3` — **Aerodrome/Slipstream routes remain denied** until the
  executor supports them. Discovery never implies execution authority.
- M3 fail-closed: only `source_component=flash_loan_arb_verifier` +
  `verification_status=CONFIRMED` evidence; CONFIRMED != EXECUTABLE.
- No signing / no broadcasting anywhere in the audit path.

## 3. Required VPS runtime configuration
For a real live audit to progress past `denied:venue_unreadable`:
- `MONGO_URL`, `DB_NAME` — evidence store.
- Base RPC: `ARBICORE_RPC_URL_BASE` (or `ARBICORE_RPC_URL`) — live `eth_call`
  quoting + `eth_feeHistory` congestion + head block.
- `ARBICORE_USD_NUMERAIRE` (+ price feed env) — on-chain USD price provenance
  (Gate 8 TVL; absent ⇒ Gate 8 fails closed, never fabricated).
- Aerodrome/Slipstream factory config (venue factories) — only needed to
  *resolve* those pools' addresses for TVL; they remain execution-DENIED.

Executor-capability / exact-simulation controls (section 4) additionally need:
- `ARBICORE_EXECUTOR_BYTECODE` / executor address — to construct and simulate
  the exact executor calldata.
- `BASE_BALANCER_V2_VAULT` — Balancer V2 Vault address for flash-loan liquidity.

Do NOT copy the VPS `.env` wholesale; provide only the values above. Never add
signer secrets/private keys to the repo or to any audit output.

## 4. MISSING readiness controls (must exist before LIMITED-LIVE READY)
These are intentionally NOT faked in code — implementing them without live
validation would create false confidence (the explicit anti-goal). Each must be
implemented as a fail-closed prerequisite and validated on the VPS:

- **Balancer flash-loan liquidity evidence** — query the Balancer V2 Vault for
  the borrow token's available liquidity; persist {provider, token, available,
  requested, safety margin, sufficient?}. Route TVL is NOT a substitute; fail
  closed if the Vault cannot be queried.
- **Borrow-size sensitivity** — prove the chosen borrow amount is profitable AND
  supported by pool depth + flash-loan liquidity + executor + net-of-all-costs.
- **Exact-transaction atomic simulation** — build the exact executor calldata
  and simulate it against fresh state (route, repayment, resulting balances,
  gas, no revert, economic result) BEFORE any Limited-Live eligibility. Must be
  a hard prerequisite. No signing/broadcast.

Until these three controls exist and pass on the VPS, the correct classification
is **BLOCKED — MISSING READINESS CONTROL** for full Limited-Live, even though the
audit tooling and the discovery→quote→economics→gates→evidence→M3 safety chain
are code-ready.
