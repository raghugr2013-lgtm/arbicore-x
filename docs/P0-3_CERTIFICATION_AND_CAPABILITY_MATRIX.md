# ArbiCore X v2 — P0-3 Engineering Certification & Capability Matrix

**Scope of this document:** Emergent engineering/test session only. It records
a repository-wide audit, the safety posture, the P0-3 remediation performed,
and the deterministic proof produced **in this environment**. It is **NOT** a
limited-live certification. Real VPS/Base RPC + Mongo runtime proof is mandatory
and is performed separately (see §K, §M).

- Branch: `fix/p0-3-runtime-v3-liquidity-filter`
- Baseline commit audited: `01a8989`
- Release-candidate commit: _recorded at commit time (see git log; this doc is
  committed together with the code)._
- Docker was **not available** in the Emergent pod, so the disposable
  `docker-compose.validation.yml` stack was not run here; the identical pytest
  invocation from `scripts/run_vps_validator_audit.sh` was reproduced against a
  **dedicated ephemeral Mongo DB** (never production).

> Capability-state vocabulary (never collapsed):
> IMPLEMENTED · CONFIGURED · AVAILABLE · DISCOVERABLE · QUOTABLE ·
> ECONOMICALLY VALID · VERIFIABLE · SIMULATABLE · LIMITED-LIVE ELIGIBLE ·
> FULL-LIVE ENABLED.

---

## A. Capability matrix

### A.1 Networks
| Network | Status | Route universe source | Notes |
|---|---|---|---|
| Base | IMPLEMENTED · CONFIGURED · DISCOVERABLE | canonical `base_pool_registry` (30 pools: 19 deterministic UniV3 + 11 runtime Aerodrome/Slipstream) | Live quote/TVL/economics require VPS Base RPC. NOT limited-live certified. |
| Ethereum | IMPLEMENTED | `chains/registries.py` (8 tokens; uniswap_v3, sushiswap_v2, curve_stable) | Discovery via `multichain_venues`; needs configured RPC per chain. |
| Arbitrum | IMPLEMENTED | registries (8 tokens; uniswap_v3, sushiswap_v3, camelot_v3) | Same. |
| Optimism | IMPLEMENTED | registries (8 tokens; uniswap_v3, velodrome_v2) | Same. |
| Polygon | IMPLEMENTED | registries (7 tokens; uniswap_v3, quickswap_v3) | Same. |
| BNB | IMPLEMENTED | registries (6 tokens; pancakeswap_v3, uniswap_v3) | Same. |

Multichain discovery is **fail-closed**: a chain contributes venues only when it
has a registry entry **and** a configured RPC (`resolve_rpc_url_from_env`);
unknown/unconfigured chains yield an empty universe. `tvl_usd=0.0` is never
fabricated — real reserves/TVL are resolved on-chain downstream.

### A.2 Arbitrage strategies (`OpportunityType` + scanners)
| Strategy | Impl | Default mode | Emit gate |
|---|---|---|---|
| CEX_ARBITRAGE | IMPLEMENTED | PAPER | verifier gates |
| DEX_ARBITRAGE | IMPLEMENTED | PAPER | verifier gates |
| FUNDING_ARBITRAGE | IMPLEMENTED | PAPER | verifier gates |
| CROSS_CHAIN_ARBITRAGE | IMPLEMENTED | PAPER | transfer provider required (else `denied:venue_unreadable`) |
| LAUNCH_ARBITRAGE | IMPLEMENTED | PAPER | venue provider required (else `denied:venue_unreadable`) |
| FLASH_LOAN_ARBITRAGE | IMPLEMENTED · DISCOVERABLE | **SHADOW** | economic + atomic-profit + liquidity (Gate 8) + MEV gates |

No dormant strategy was removed. Each retains its implementation; the blocker
for live operation is provider wiring + certification, not code.

### A.3 Flash-loan / liquidity providers (`FLASH_LOAN_PROVIDERS`)
| Provider | Fee (bps default) | Chains | Executable by current head? |
|---|---|---|---|
| aave_v3 | 5 | ethereum, arbitrum, base, optimism, polygon, bnb | Cataloged; **not** current executor head |
| balancer_v2 | 0 | ethereum, arbitrum, base, optimism, polygon | **Yes** (current executor head) |
| uniswap_v3 | 30 (tier-resolved) | ethereum, arbitrum, base, optimism, polygon | Swap hops only (current head) |
| morpho_blue | 0 | ethereum, base | Cataloged |

The deployed executor head supports **Balancer V2 borrow + Uniswap V3 swap hops**
only; other cataloged providers are retained (AVAILABLE) but rejected before
economics/gas so an unsupported route can never be mistaken for a live candidate
(`composition._flashloan_available`, `fresh_fn` executor-capability gate).

### A.4 Route discovery / quotes / TVL / economics / simulation / evidence
- **Route discovery:** `RouteSearchEngine` over the canonical resolved pool
  graph (synchronous, pure, fail-closed on unresolved/address-less pools).
- **Quote:** live QuoterV2-backed provider (`make_live_quote_provider`) consuming
  `canonical_pool_specs` (single source; legacy `build_pool_graph` removed).
- **TVL / Gate 8:** on-chain reserves (`build_base_tvl_provider`); absent
  RPC/price ⇒ `tvl_provider=None` ⇒ Gate 8 fails closed (never fabricated).
- **Economics:** `FlashLoanEconomicsAssessor` + `ROIProbabilityEngine`; true
  all-in Base cost via chain gas model (L2 + L1 GasPriceOracle + flash fee +
  slippage). DENY if all-in cost cannot be determined.
- **Simulation/fork:** executor fork validation + atomic-sim
  (`execution/settlement_simulator.py`, fork validation routes) — SIMULATABLE.
- **Evidence/provenance:** `EvidenceBundlesRepo` (append-only) + per-token USD
  price provenance; `find_for_audit(audit_run_id=…, scanner_tick_id=…)`.

### A.5 Config gates currently preventing activation
- Per-provider / per-chain enable flags in `scanner_config.flash_loan_arb`
  (repo default ships `False`; canonical activation keeps detection on unless an
  operator explicitly sets `enabled=False`).
- Execution mode ladder (below) — broadcast only in LIMITED_LIVE/FULL_LIVE.
- T0-1 quote-provider readiness gate (`flash_loan_quote_readiness`) refuses to
  run the noop quote provider in any analysis mode.

---

## B. Safety audit (fail-closed proofs)

Execution mode ladder (`execution/mode.py`):
`OBSERVE → PAPER → SHADOW → LIMITED_LIVE → FULL_LIVE`.
Defaults: flash-loan **SHADOW**, all other trading strategies **PAPER**.
`may_broadcast(mode)` returns True **only** for `LIMITED_LIVE`/`FULL_LIVE`.

| Surface | Fail-closed mechanism |
|---|---|
| Signer / private key / signing / broadcast | Gated by mode ladder; `may_broadcast` False for OBSERVE/PAPER/SHADOW. No signing/broadcast enabled in this session. |
| Pre-broadcast validation | `PreBroadcastValidator.validate` — any error/None ⇒ DENY; `build_controlled_live_safety` returns `(None, None)` without Base RPC ⇒ `require_revalidation=True` ⇒ DENY before signing. |
| Executor / AutoExecutor | Records only in SHADOW/PAPER; never broadcasts unless strategy mode is LIMITED_LIVE/FULL_LIVE. |
| Withdrawal | Not enabled; no withdrawal capability introduced. |
| Kill switch | `KillSwitchRepo.engage/disengage`; circuit-breaker trip engages kill switch. |
| Economic / simulation / route / quote integrity | DENY on missing inputs; no fabricated fallback quote; unresolved pools excluded from the live universe. |
| Liquidity validation (P0-3) | Runtime UniV3 `liquidity()` eligibility — **fail-closed** (see §H). |
| RPC / rate-limit handling | `make_base_eth_call_from_env` returns None on failure (fail-closed); provider registry does health tracking + failover. |

Invariants upheld: no fabricated opportunity becomes confirmed; no simulation is
represented as live execution; no shadow result is authoritative live execution.

---

## H. P0-3 remediation performed (this session)

**Problem (Phase 4):** the runtime Base UniV3 `liquidity()` eligibility refresh
(`composition._refresh_base_v3_eligibility`) issued ~19 **sequential** `eth_call`
RPC round-trips during canonical scanner startup, risking the ~8s startup budget.
Two latent fail-open/robustness hazards were found in the surrounding wiring.

**Fix (performance + hardening; classification unchanged, strictly more fail-closed):**
1. **Bounded concurrency** — per-pool `liquidity()` reads now run under an
   `asyncio.Semaphore` (default `max_concurrency=8`) via `asyncio.gather`
   (~3 waves instead of 19 serial round-trips). The deny-list is rebuilt
   **atomically** from verified results after all reads complete.
2. **Fail-closed baseline (pre-seed)** — every resolved UniV3 pool is excluded
   **before any await**, so a mid-flight exception or a startup-deadline
   `CancelledError` leaves the universe fail-closed; a pool is re-admitted only
   after its genuine `liquidity()>0` read completes.
3. **Per-call timeout** — each read is bounded by `per_call_timeout_s`
   (default 2.0s); a stalled RPC is classified **EXCLUDED** (never allowed to
   consume the startup budget).
4. **Caller fallback** — `_wire_canonical_flash_loan_scanner`'s except branch
   now re-asserts the fail-closed baseline (`_failclosed_exclude_all_base_univ3`).

**Preserved (unchanged):** canonical registry purity/determinism (never
mutated/deleted by runtime filtering); Aerodrome/Slipstream are **never** subject
to the UniV3 `liquidity()` rule; `RouteSearchEngine`/pool loader remains
synchronous. The USDC/cbETH 500ppm pool
(`0xFdebEDc97D56EDd31AbdcB887570546B257964f2`) stays canonical while
runtime-ineligible at zero liquidity.

**Files changed:** `app/backend/arbicore/runtime/composition.py`;
tests `app/backend/tests/test_z9_base_v3_liquidity_eligibility.py` (certified)
and `app/backend/tests/t1_verify/test_t1_z9_independent_verification.py`
(independent). Validator module list already includes z9.

---

## F. Test / proof results (in this environment)

- Disposable validator (`scripts/run_vps_validator_audit.sh`, 13 certified
  deterministic modules): **158 passed / 0 failed** → `AUDIT RESULT: PASS`
  (baseline was 138; +20 from the z9 module).
- Focused `test_z9_base_v3_liquidity_eligibility.py`: **20 passed** (zero,
  positive, registry-preservation, missing/empty/malformed/unreadable
  fail-closed, absent-provider, Aerodrome exemption, bounded concurrency,
  per-call timeout, escaping-cancellation fail-closed, all-stalled-within-budget).
- Independent `t1_verify/test_t1_z9_independent_verification.py`: **17 passed**
  (peak-saturation at cap, boundary liquidity, recovery clears stale exclusions,
  Aerodrome never receives a liquidity call, hardened fail-closed).
- Verified by the testing agent (report `test_reports/iteration_1.json`):
  no critical issues; the two hazards it found were then fixed and re-covered.

---

## G. Remaining blockers (honest)

1. **P0-3 not certified** — requires the real VPS/Base proof: canonical scanner
   instantiated, live quote provider wired, real routes discovered, ≥1 genuinely
   verified candidate, evidence persisted, evidence readback for the actual
   `audit_run_id`/`scanner_tick_id`, fail-closed intact. Cannot be produced in
   Emergent.
2. **Live quote/TVL/economics** need configured Base RPC + USD price feed on the
   VPS. Absent ⇒ Gate 8 fails closed (correct, but no candidate can confirm).
3. **Non-Base networks** are IMPLEMENTED but require per-chain RPC config +
   discovery/quote/economics/evidence health before limited-live eligibility.
4. **Pre-existing, out-of-scope failure** (NOT caused by this change; fails
   identically at `01a8989`):
   `tests/test_t1_multichain_foundation_adversarial.py::TestGasModelSeam::test_from_env_no_rpc_is_fail_closed`
   — environment-driven (Base gas env present in the pod). Left untouched.
5. `composition.py` is ~1.9k lines (> guideline). Not refactored — out of scope
   for P0-3; noted for a future dedicated task.

---

## I. Regression analysis

- Certified suite: 138 → 158, **0 failed** (additive only).
- Classification of the eligibility function is byte-for-byte identical for all
  IN-SCOPE outcomes; the change is performance + strictly-more-fail-closed.
- Broader offline collection failures observed are `ConnectionRefusedError`
  endpoint/integration tests that require a running FastAPI server — unrelated
  to this change and not part of the disposable validator scope.
- Forbidden/VPS-local files untouched: `scanners/dex_arbitrage/scanner.py`,
  `deployment/compose/docker-compose.yml`, `scripts/p0_3_flash_discovery_proof.py`.

---

## K. Deployment procedure (VPS; reproducible by exact SHA)

1. `git fetch` and check out the exact release-candidate SHA on
   `fix/p0-3-runtime-v3-liquidity-filter` (do NOT merge to main).
2. Disposable validation (Docker present on VPS):
   ```
   VALIDATION_GIT_SHA=$(git rev-parse HEAD) \
   VALIDATION_GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD) \
   docker compose -f deployment/compose/docker-compose.validation.yml \
     run --rm --build validator
   ```
   Do **not** use `--remove-orphans`. Expect `AUDIT RESULT: PASS`.
3. Build the immutable backend image; backend-only recreate (do not restart
   frontend/opportunity-center/nginx or unrelated services). Preserve the local
   compose mapping `127.0.0.1:18001:8001`.
4. Run a single canonical P0-3 audit tick (read-only) with real Base RPC + Mongo;
   capture `audit_run_id`/`scanner_tick_id`; verify quote, liquidity, economics,
   evidence persistence + readback.

No signing / broadcast / AutoExecutor / limited-live / full-live is enabled by
this release. SHADOW / detection-only / fail-closed is preserved.

---

## L. Rollback procedure

- The feature branch is not merged; production remains on its current ref.
- Safety branch `backup/vps-before-p0-3-sync` and stash `stash@{0}`
  ("VPS-local changes before P0-3 sync") are **preserved** — do not pop/delete
  until certification completes.
- To revert: redeploy the previous immutable backend image / previous SHA.
  Use the platform **rollback** to return the codebase to any prior checkpoint;
  do not `git reset`/force-push.

---

## M. Limited-live readiness checklist (all must be genuinely proven on VPS)

- [ ] Genuine live discovery over the real Base universe
- [ ] Genuine live quote (QuoterV2, correct token order / pool / fee-tick / block)
- [ ] Genuine liquidity verification (UniV3 `liquidity()` > 0; Gate 8 TVL)
- [ ] Genuine economics (true all-in Base cost; positive atomic profit)
- [ ] Route integrity (complete verifiable facts; no fabricated fallback)
- [ ] Evidence persistence **and** readback for the actual run/tick ids
- [ ] Simulation / fork proof (atomic settlement sim passes)
- [ ] Execution feasibility (executor-capability gate: Balancer V2 + UniV3)
- [ ] Safety-gate verification (mode ladder, pre-broadcast DENY, kill switch)
- [ ] **Explicit administrator approval** (no automatic discovery→live transition)

---

## N. Capabilities preserved (explicit)
All networks (Base + 5 multichain), all cataloged flash-loan providers
(aave_v3, balancer_v2, uniswap_v3, morpho_blue), all 6 arbitrage scanners, route
discovery, live quote provider, on-chain TVL/Gate 8, economics/ROI, simulation/
fork, evidence/provenance, readiness/T0-1 gate, kill switch, mode ladder.
Nothing was removed to ease certification.

## O. Capabilities NOT yet limited-live certified (explicit)
Every strategy and network above is detection/SHADOW/PAPER only. FLASH_LOAN on
Base is DISCOVERABLE but **not** verified/limited-live certified pending the VPS
proof (§M). No signing, no broadcast, no live/limited-live, no withdrawals.
