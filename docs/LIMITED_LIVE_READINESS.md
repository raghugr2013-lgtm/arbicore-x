# ArbiCore X — Limited-Live Readiness & Runtime Configuration

Status: **CODE READY (audit tooling + safety chain) — VPS VALIDATION REQUIRED.**
This document is the single source of truth for what the *application* enforces
in code vs. what the *runtime* (VPS) must supply, and which readiness controls
are still MISSING before a genuine `LIMITED-LIVE READY` classification.

No signer secrets or private keys are documented here, by policy.

## 1. Attributable audit workflow (fixed)
The canonical VPS audit is driven by `scripts/run_vps_validator_audit.sh`
(hermetic guards) with an optional live phase (`ARBICORE_RUN_LIVE_AUDIT=1`,
requires `MONGO_URL`+`DB_NAME`) that runs `python3 -m scripts.vps_canonical_audit`:

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

## 2a. Disposable validation image — test tooling (fail-closed)
The runner executes the deterministic regression suite with `python3 -m pytest`.
`pytest.ini` declares `required_plugins = pytest-xdist`, runs `-n 2`, and sets
`asyncio_mode = auto`, so the disposable validation image MUST expose, to its
`python3`: `pytest`, `pytest-xdist`, `pytest-asyncio` (import names `pytest`,
`xdist`, `pytest_asyncio`). Production images deliberately exclude these
(`requirements.prod.txt` is the sole prod source; repo philosophy forbids pytest
in prod). Provisioning options (neither touches the VPS host or a production
container):

1. **PREFERRED — build the disposable validation image** (explicit, pinned,
   build-time):
   ```
   docker build -f deployment/docker/backend/Dockerfile.validation \
                -t arbicore-x-validator:$(git rev-parse --short HEAD) .
   ```
   then run the runner inside it with the detached worktree mounted
   (`-v "$PWD":/src -w /src`). Test deps come from the explicit pinned
   `deployment/docker/backend/requirements.test.txt`.
2. **Or** opt into a per-run isolated venv bootstrap (pinned, `--system-site-packages`,
   torn down with the container):
   ```
   ARBICORE_VALIDATOR_BOOTSTRAP=1 bash scripts/run_vps_validator_audit.sh
   ```

Fail-closed contract: if the tooling is missing and no bootstrap is requested,
the runner prints `TEST TOOLING UNAVAILABLE` and exits non-zero (exit 3). It
NEVER reports PASS when the suite could not run — a missing test dependency can
never be mistaken for a green audit.

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

## 4. Limited-Live eligibility controls (implemented as fail-closed decision layer)
`CONFIRMED != EXECUTABLE`. A single explicit decision,
`arbicore.execution.limited_live_eligibility.evaluate_limited_live_eligibility`,
requires **every** mandatory control below to be an explicit PASS; any missing /
unknown / unverifiable / insufficient / stale / mismatched value ⇒ **DENY**.
Assembled per exact-run CONFIRMED candidate by
`scanners.flash_loan_arbitrage.readiness_assessment.assess_candidate_readiness`
and surfaced by the audit runner. Nothing signs/broadcasts/enables Limited-Live.

| Control | Proves | DENY when |
|---|---|---|
| quote_complete | closed-cycle, all hops ok | partial/reverted/missing/malformed |
| economics_ok / gate_7 | atomic profit ≥ floor | net ≤ 0 or Gate 7 ≠ PASS |
| liquidity_verified / gate_8 | route TVL verified | Gate 8 ≠ PASS / unverifiable |
| executor_capability | route venues are executor-supported (**proven**, `evaluate_executor_capability`) | any Aerodrome/unsupported venue (UNSUPPORTED) or missing venue metadata (UNVERIFIABLE) |
| gate_9 | MEV within policy | Gate 9 ≠ PASS |
| balancer_liquidity | candidate-level Balancer V2 Vault flash-loan liquidity ≥ borrow (`read_balancer_liquidity`, status ladder) | not ON_CHAIN_CONFIRMED (UNKNOWN/UNAVAILABLE/INSUFFICIENT) |
| borrow_size_feasible | a size that is profitable **and** executable (`select_borrow_size`) | no feasible size |
| atomic_simulation | exact executor calldata simulated against fresh state (`AtomicExecutorSimulator.simulate_atomic`) | unavailable / revert / missing executor/signer/calldata |
| freshness_ok | quote/block/state within policy | stale / unproven |
| provenance_complete | exact audit_run_id + scanner_tick_id + candidate_id | any missing |
| verification_confirmed | source=flash_loan_arb_verifier, status=CONFIRMED | otherwise |
| mode_allows / kill_switch_ok | operator mode ladder permits + kill switch clear | Limited-Live not enabled / kill switch engaged |

Evidence persisted per candidate (exact provenance preserved): executor
capability (status + pool classification), Balancer liquidity (provider, token,
available, requested, margin, sufficient, source), borrow-size analysis
(evaluated sizes + selection rationale), atomic-simulation result (available,
passed, block_tag, reason, `signed=false`, `broadcast=false`), and the full
control ledger + decision. Missing/mismatched field ⇒ fail closed.

## 5. Required VPS runtime configuration
For the eligibility controls to reach anything other than DENY on the VPS:
- `MONGO_URL`, `DB_NAME` — evidence store.
- `ARBICORE_RPC_URL_BASE` (or `ARBICORE_RPC_URL`) — live quoting / congestion /
  head block / Balancer balanceOf / atomic-sim eth_call.
- `ARBICORE_USD_NUMERAIRE` (+ price feed env) — Gate 8 TVL + Balancer USD sizing.
- `ARBICORE_EXECUTOR_ADDRESS_BASE` + `ARBICORE_EXECUTOR_BYTECODE`
  (`contracts/artifacts/FlashLoanReceiver.bytecode.txt`) — atomic simulation of
  the exact executor calldata.
- `BASE_BALANCER_V2_VAULT` — override only if different from the canonical
  singleton `0xBA12222222228d8Ba445958a75a0704d566BF2C8`.
- `ARBICORE_AERO_CL_FACTORY_BASE` / `ARBICORE_AERO_POOL_FACTORY_BASE` — only to
  resolve Aerodrome pool addresses for TVL; those routes stay execution-DENIED.
- `ARBICORE_WSS_URL_BASE` — optional streaming head.

Provide ONLY these non-secret values through the protected config mechanism.
NEVER add signer keys / private keys / API secrets to Git or to audit output.

## 6. What Codex must independently verify on the VPS
Run `ARBICORE_RUN_LIVE_AUDIT=1 bash scripts/run_vps_validator_audit.sh` and
confirm, from the JSON report (ids/status only, no secrets):
- exact `audit_run_id` + `scanner_tick_id` captured from one real tick;
- candidate ledger isolated to that exact run+tick;
- per-CONFIRMED-candidate `readiness`: executor_capability, balancer_liquidity,
  borrow_size, atomic_simulation, and the `limited_live` decision;
- `limited_live_eligible_candidates` — expected EMPTY until an executor+signer
  are provisioned and atomic simulation passes (fail-closed is correct);
- `signed=false`, `broadcast=false`, `limited_live_enabled=false` everywhere.

## 7. Intentionally still disabled / remaining VPS prerequisites
The decision layer + evaluators are implemented and fail-closed. Reaching an
ELIGIBLE verdict additionally requires, on the VPS (NOT done here):
- a deployed/allowlisted executor + a present execution signer so the exact-tx
  atomic simulation can actually run (today it fails closed);
- live Balancer Vault reads returning ON_CHAIN_CONFIRMED for the borrow token;
- a freshness policy proof and an operator mode/kill-switch state that permits a
  Limited-Live attempt.

Until Codex proves all of the above live on the exact SHA, the classification is
**CODE READY — VPS VALIDATION REQUIRED** (never Limited-Live ready on unit tests
alone). Limited-Live / Full-Live / signing / broadcasting remain disabled.
