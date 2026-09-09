# ArbiCore X v2 — Phase P1 Batch 2 Exit Report

**Date:** 2026-09-09 · **Branch:** `p1-batch2-h07-h08-h09` (off `p1-batch1-m01-m06-m07-h06`, itself off the P0 baseline)
**Scope:** safe/testable in-pod parts of H07, H08, H09; H05 preserved; M01/M06/M07 invariants preserved. Runtime proof for H07/H08/H09 remains VPS/operator-gated. No merge to main, no deploy, no signing/broadcast, no real tx. Protected files untouched.

**Additive-only:** Batch 2 modified NO production source files. It adds two authoritative modules + tests (and re-aligns one Batch-1 test to the intended contract). Live API behavior is unchanged from Batch 1, so the Batch-1 live verification (`iteration_2.json`) still holds.

---

## H07 — deeper six-chain canonical composition — PARTIAL (isolation proven in-pod)
Cross-contamination guards now proven across all six chains (base/ethereum/arbitrum/optimism/polygon/bnb):
- **RPC selection**: global `ARBICORE_RPC_URL`/`PROVIDER_RPC_URLS` are Base-only aliases (P0 H06) — never leak into the other five (test asserts per-chain).
- **RPC identity**: every endpoint must prove `eth_chainId` == the intended chain's id before use/failover (P1B1 H06); a node serving chain X is rejected for every other chain (6×6 matrix test).
- **TVL/liquidity**: `live_quote_provider` is `tvl_provider_chain`-scoped (P1B1 H07) — a Base-scoped depth provider is never consulted for another chain ⇒ Gate 8 fails closed.
- **Pricing/economics**: the certified composition (`build_controlled_live_safety`) is Base-only by construction (Base price feed + Base TVL); non-Base routes fail closed at quoting (no per-chain `eth_call` seam) and at M3 (H05 size guard). No non-Base data enters Base-bound economics.
- **Remaining (VPS):** real per-chain scanner→resolver→quote→liquidity→economics→route→execution requires operator per-chain RPC + per-chain TVL/price providers. Not provable in-pod; must NOT be claimed as runtime-certified here.

## H08 — execution/receiver fabric — DESIGN + SAFE CODE (no deploy)
New READ-ONLY, fail-closed capability/version layer `arbicore/execution/receiver_capability.py` over the committed `executor_registry`:
- `receiver_capability(chain)` → `deployed` only when `deploy_status==success` + valid address; surfaces `receiver_version`/`abi_version` (missing ⇒ `"unversioned"`, `version_verified=False`), `bytecode_verified` (from basescan), `supported_providers`, `constructor_args`.
- `receiver_supports(chain, provider)` → **False unless** a deployed receiver EXPLICITLY declares that provider (no capability inference from constructor args — never fabricates support).
- Preserved & un-weakened: owner/provider authorization, repayment enforcement, unsupported-venue rejection, deployment verification, fail-closed behavior (existing execution path untouched). No receiver deployed; current production receiver not replaced.
- **Remaining (VPS):** deploy a versioned receiver per chain, declare `supported_providers`, verify bytecode/immutables on-chain, then wire `receiver_supports` as an additional live gate.

## H09 — candidate-bound simulation — CONTRACT + FAIL-CLOSED EVALUATOR
New `arbicore/certification/candidate_simulation.py`:
- `CandidateSimulationBinding` binds **chain, block_number, token, token_decimals, exact_input_wei, route, calldata, liquidity_state, economics, executor_address, receiver_version** (all 11 required).
- `evaluate_candidate_simulation(binding, sim_result)` certifies (tier `SIMULATION_CERTIFIED`) ONLY when: binding complete + sim method is EXACT candidate-bound (M01) + `ok` + chain matches. Otherwise fail-closed with explicit `denied_reasons` (incomplete_binding / non_certifying_sim_method / simulation_not_ok / chain_mismatch).
- Infrastructure availability, Noop/symbolic/paper/heuristic results, or an env "GREEN" can NEVER certify (verified by test).
- **Remaining (VPS):** the exact fork/state-override simulator that emits a certifying `atomic_exact` result over live chain state. Current in-pod simulators (`estimate_symbolic`/`noop`) are non-certifying by design ⇒ evaluator denies, which is correct.

## H05 — exact-size economics — PRESERVED
Unchanged and still fail-closed; probe-size economics cannot be extrapolated. Operator price-feed / `borrow_sizer` remains the VPS evidence gate.

## M01 / M06 / M07 invariants — PRESERVED
EvidenceTier ladder + certifying/non-certifying sim methods intact; ShadowCertificationEngine/ExecutionCertifier remains the sole readiness authority (no new framework); vault/exchange surfaces remain truthfully MOCKED/NOT_CONFIGURED and excluded from readiness.

## Six-chain matrix (pod)
| Chain | chainId guard | RPC (pod) | TVL scope | Receiver deployed | Composition (pod) |
|-------|---------------|-----------|-----------|-------------------|-------------------|
| Base (8453) | ✅ | ❌ none | base-scoped | ❌ not_deployed | fail-closed (no RPC) |
| Ethereum (1) | ✅ | ❌ | isolated | ❌ absent | fail-closed |
| Arbitrum (42161) | ✅ | ❌ | isolated | ❌ absent | fail-closed |
| Optimism (10) | ✅ | ❌ | isolated | ❌ absent | fail-closed |
| Polygon (137) | ✅ | ❌ | isolated | ❌ absent | fail-closed |
| BNB (56) | ✅ | ❌ | isolated | ❌ absent | fail-closed |
(Base Sepolia 84532 is the only `success` deployment in the registry, with no declared `supported_providers` ⇒ all venues rejected.)

## Venue/provider execution matrix (pod, fail-closed)
| Chain | Receiver | Declared providers | balancer_v2 | aave_v3 | uniswap_v3 | aerodrome |
|-------|----------|--------------------|-------------|---------|------------|-----------|
| base_sepolia (84532) | deployed (unversioned) | none | ❌ | ❌ | ❌ | ❌ |
| base_mainnet (8453) | not_deployed | — | ❌ | ❌ | ❌ | ❌ |
| ethereum/arbitrum/optimism/polygon/bnb | absent | — | ❌ | ❌ | ❌ | ❌ |
All rejected ⇒ no venue is execution-capable in-pod (correct fail-closed).

## Candidate-bound simulation evidence
No candidate reaches `SIMULATION_CERTIFIED` in-pod: the only available simulators emit non-certifying methods (`estimate_symbolic`/`noop`), and no complete binding with an exact method + live chain match can be produced without operator RPC/fork. The evaluator DENIES — the honest, required outcome.

## Tests & exact results
- `tests/test_p1b2_h07_h08_h09.py` — **13/13** (six-chain expected ids; 6×6 no-cross-accept; global-alias no-leak; undeployed/absent chains incapable; deployed-without-declared-providers rejects all; unknown chain incapable; required-fields set; incomplete binding / unversioned receiver / heuristic method / chain mismatch / failed sim all fail closed; exact+ok+match certifies).
- `tests/test_m01_evidence_tiers.py` 6/6, `tests/test_h06_h07_chain_isolation.py` 6/6, `tests/test_h05_exact_size_binding.py` 5/5, `tests/test_m07_truthfulness.py` **12/12** (2 GET tests re-aligned to the intended public-read + truthful-body contract), `tests/test_p0_security.py` 20/20. Combined P0+P1 regression: **62 passed**.
- Regression isolation: Batch 2 modified no production source (git shows only new modules + 1 test re-alignment) ⇒ no risk to existing behavior; prior offline delta (P1B1) already showed 0 regressions.

## testing_agent results
Batch 2 added no new live endpoints (H08/H09 are internal modules), so a fresh live run is N/A; Batch-1 live verification `/app/test_reports/iteration_2.json` (M07 truthfulness + P0 authz) remains valid because no production code changed. `/app/test_reports/iteration_1.json` = P0 (19/20).

## Remaining VPS/operator blockers
Operator per-chain RPC; deployed+versioned receiver per chain with declared `supported_providers`; real bytecode/immutable verification; real liquidity/TVL/price providers; funded signer (still OFF); Anvil/fork state + exact candidate simulator. None substitutable by pod evidence.

## Git branch / commit / diff
Branch `p1-batch2-h07-h08-h09`. Working-tree: new `arbicore/execution/receiver_capability.py`, `arbicore/certification/candidate_simulation.py`, `tests/test_p1b2_h07_h08_h09.py`; modified `tests/test_m07_truthfulness.py` (test contract re-alignment). No production source modified. `.env` git-ignored. Push via "Save to GitHub".

## Safety confirmation
signing OFF · broadcast OFF · auto-exec OFF · Full-Live OFF · no real tx · no production deploy · no merge to main · protected files untouched · no secrets/.env committed.

**STOP — P1 Batch 2 complete. Awaiting explicit approval before any further batch or Limited Live.**
