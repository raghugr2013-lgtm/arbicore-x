# Paper Broker Readiness Audit — 2026-10-02

- **Status:** `READY-WITH-MINOR-DELTA`
- **Date:** 2026-10-02
- **Workspace (primary):** `/home/raghu/projects/arbicore-x-cert`
- **Config reference only:** `/home/raghu/projects/arbicore-x-v2` (env inspect)
- **Scope:** Inspect-only discovery/audit. **No** app source changes. **No** gate/threshold changes. **No** AUTOEXEC/RUNTIME enable. **No** execution/live trading.
- **Context:** M6 POST-ALCHEMY-RESET SHADOW PASS (evidence-complete). Gate 7 = $25. SHADOW ON. AUTOEXEC/RUNTIME OFF.

---

## Executive verdict

There is **no class or module named `PaperBroker`**. What exists is a mature **Paper Validation Framework** (v2.11.8) plus a legacy **PaperEngine**, both wired into the unified `OpportunityPipeline`. PAPER and SHADOW are **behaviorally identical for non-broadcast** (terminate at `SHADOW_RECORDED` / evidence insert).

**Paper Validation (evidence-path) can proceed without source changes** by config/ops only — stay in SHADOW, keep AUTOEXEC/RUNTIME off, ensure the paper runner + evidence APIs are exercised.

**True Paper Broker accounting** (virtual wallet, paper fills ledger, cumulative paper P&L for Gates 9–10 as written in the handoff) **does not exist** and is a larger delta. That does **not** block a first Paper Validation evidence campaign if Gate 8 is interpreted as “immutable evidence bundles in `arbicore_paper_evidence`” (handoff wording).

**FINAL STATUS: `READY-WITH-MINOR-DELTA`**

---

## A–H answers (summary)

| Q | Answer |
|---|---|
| **A. What exists?** | Paper Validation Framework (`arbicore/paper/*`), legacy `PaperEngine`, pipeline stages (liquidity/gas/profit/policy/cert/simulate), evidence Mongo repo, validation + paper API endpoints, mode ladder, runners (PaperValidationRunner / AutoExecutor / optional flash-loan shadow route). No `PaperBroker` type. No paper wallet / fill ledger / aggregated paper P&L. |
| **B. Production-quality / reusable?** | Yes: evidence model, classifier, insert-only repo, runner idempotency, pipeline fail-closed mode/quote readiness, kill-switch + broadcast gate, Slice A/B/C tests, operator APIs. Reuse as-is for SHADOW-mode paper validation. |
| **C. Missing for Paper Broker Validation?** | (1) Dedicated paper wallet/balance/P&L surface. (2) Six-chain `eth_call` mapping in `SimulationRouter.from_env` (Base-only today). (3) PAPER≠SHADOW behavioral distinction (none). (4) Aggregated paper P&L metrics for Gate 9. (5) Explicit “paper fill” objects (evidence ≠ fills). |
| **D. Existing tests?** | Slice A/B/C (~57), pipeline glue / autoexec never-broadcast, phase 5–8 PaperEngine, mode ladder, shadow cert + live endpoint regressions. |
| **E. Missing tests?** | Six-chain sim RPC wiring; paper wallet/PnL; SHADOW→PAPER demotion/ops contract; Gate 9 aggregate P&L; end-to-end paper validation against live six-chain M6 evidence without AUTOEXEC. |
| **F. Smallest implementation delta?** | Prefer **zero source**: enable/confirm `ARBICORE_PAPER_VALIDATION_ENABLED`, keep SHADOW, collect evidence via existing APIs. Optional **XS source** later: extend `SimulationRouter.from_env` to `ARBICORE_RPC_URL_*` / all six chains (not required to start evidence campaign). |
| **G. Validation without source changes?** | **Yes** for Paper Validation Framework / Gate-8-as-evidence. **No** for Gate-9/10 paper-P&L / virtual-wallet broker validation. |
| **H. If source required — files + reason (DO NOT MODIFY now)** | See §H below. None required to start evidence-path validation. |

---

## 1. Existing capability inventory

### 1.1 Naming reality

| Name in docs / ops | Code reality |
|---|---|
| “Paper broker (SHADOW/PAPER)” (`deploy/ARBICORE_X_HANDOFF_AUDIT.md`) | Informal label for non-broadcast pipeline termination + paper evidence |
| `PaperBroker` / `paper_broker` | **Not found** as type, module, or endpoint |
| Paper Validation Framework (v2.11.8) | **Implemented** under `app/backend/arbicore/paper/` |
| Legacy Paper Opportunity Engine (Phase 6) | **Implemented** as `PaperEngine` |

### 1.2 Module inventory (`app/backend/arbicore/paper/`)

| File | Role | LOC (approx) |
|---|---|---|
| `__init__.py` | Dual surface exports (legacy + v2.11.8) | 55 |
| `paper_engine.py` | Legacy EV analysis; **never wallet / never sign** | 207 |
| `outcomes.py` | Closed 8-value `PaperOutcome` vocabulary | 72 |
| `evidence.py` | Immutable `EvidenceBundle` + `StageMetric` + `validation_id` | 146 |
| `classifier.py` | First-failure-wins terminal classification | 86 |
| `repo.py` | Insert-only Mongo `arbicore_paper_evidence` + in-memory test repo | 188 |
| `liquidity.py` | Fail-fast hop liquidity vs borrow×ratio | 146 |
| `simulator.py` | `EthCallSimulator` / `HeuristicSimulator` / `SimulationRouter` | 278 |
| `runner.py` | Continuous `PaperValidationRunner` (env-gated) | 302 |
| `stage_recorder.py` | Per-stage timing helper | 90 |

### 1.3 Opportunity → paper path (pipeline)

Canonical path is `OpportunityPipeline.evaluate` in
`app/backend/arbicore/execution/pipeline.py`:

```
DISCOVERED → quote/route → liquidity → gas → profit → policy → certification
  → simulate → SHADOW_RECORDED (PAPER/SHADOW/OBSERVE non-broadcast)
  → (LIMITED_LIVE+/FULL_LIVE only) broadcast
  → EvidenceBundle insert (if evidence_repo wired)
```

- `BROADCAST_MODES = {LIMITED_LIVE, FULL_LIVE}`
- `ANALYSIS_MODES = {PAPER, SHADOW, LIMITED_LIVE, FULL_LIVE}`
- PAPER and SHADOW both end at shadow record; reason: `"mode not promoted for automatic broadcast"`.

Drivers that can feed the pipeline:

| Driver | Gate | Notes |
|---|---|---|
| `PaperValidationRunner` | `ARBICORE_PAPER_VALIDATION_ENABLED` | Drains canonical opps (REAL/VERIFIED_REAL), idempotent, batch 25 |
| `AutoExecutor` | `ARBICORE_AUTOEXEC_AUTOSTART` | **Must stay OFF** for this campaign |
| Flash-loan shadow sink | `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` | Opt-in; avoid double-processing with global runner |
| Manual `POST /api/arbicore/paper/analyse` | auth | Legacy PaperEngine only (analysis, not full pipeline) |

### 1.4 Routes / endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/arbicore/validation/report` | Histogram + executable_rate |
| `GET /api/arbicore/validation/evidence` | Recent bundles |
| `GET /api/arbicore/validation/evidence/{id}` | Full stage trace |
| `GET /api/arbicore/validation/metrics` | Runner health |
| Pulse `paper_validation` block | Dashboard snapshot |
| Extended validation APIs (`/summary`, `/recurrence`, `/calibration`, `/venue_ranking`, `/regime`, `/daily_status`, …) | Present (post-v2.11.8) |
| `POST /api/arbicore/paper/analyse` | Legacy PaperEngine |
| `GET /api/arbicore/paper/stats` | Legacy PaperEngine stats |
| Mode / readiness | `execution/mode`, `control/readiness` (includes `PAPER_VALIDATION` check) |

**None** of these are order-placement / paper-fill / wallet-debit APIs.

### 1.5 Wallet / balance / accounting model

| Capability | Status |
|---|---|
| Paper virtual wallet | **MISSING** |
| Paper balance ledger | **MISSING** |
| Paper fill objects | **MISSING** (handoff “fills” = evidence rows by convention) |
| Live wallet registry / money-trail | Exists for **on-chain** capital intelligence (`capital/wallet_intelligence.py`) — not paper |
| CEX `BalanceService` | Documented as dormant / not imported for paper surface (`docs/ui_v2/23_OPERATOR_READINESS_AUDIT.md`) |

`PaperEngine` docstring is explicit: *“Never executes anything. Never touches a wallet. Never signs.”*

### 1.6 P&L accounting

| Layer | What is computed | Persisted where |
|---|---|---|
| Economics `compute_net_profit` | Gross − gas − slippage − flash fee | Upstream opp / decision path |
| Pipeline `_extract_gas` + `_compute_profit` | Nominal family gas % or opp `gas_estimate`; after-gas profitability | Stage metrics on EvidenceBundle |
| Legacy PaperEngine | `net_profit_usd`, `expected_value_usd` | MID events `paper.engine.analysed` |
| Aggregated paper P&L (Gate 9) | **MISSING** — no cumulative paper PnL series / drawdown API |

### 1.7 Gas / fee / slippage in paper path

- **Gas:** pipeline uses explicit `gas_estimate` or **nominal** rates (CEX 0.20%, cross-chain 1.0%, on-chain/flash 0.60% of borrow). Not live `eth_gasPrice` by default.
- **Slippage / flash fee:** primary path is upstream economics / opp fields; PaperEngine also applies `flash_loan_fee_bps` + `slippage_bps` on capital.
- **Liquidity:** fail-fast when `pool_liquidity_usd` present; **permissive skip** when absent (no fabricated liquidity).
- **Simulation:** real `eth_call` only if RPC configured for chain in `SimulationRouter`; else **heuristic** shape check.

### 1.8 Flash-loan / provider handling

- Pipeline certification stage runs for flash-loan-shaped opps (`flash_loan_provider`, `swap_hops`, borrow fields).
- Evidence inputs capture `flash_loan_provider`, borrow token/amount, chain.
- Default strategy mode: `flash_loan_arbitrage=SHADOW` (`execution/mode.py`).
- Flash-loan operator journey wires `paper_validation_required=True` into safety approval story.
- Approval gate: `ARBICORE_SAFETY_REQUIRE_PAPER_VALIDATION` (default true) blocks live approval without `paper_validation_passed`.

### 1.9 Idempotency / duplicates

- Runner: in-process `_processed_ids` + Mongo `get_by_opportunity_id` skip.
- Optional reprocess: `ARBICORE_PAPER_RUNNER_REPROCESS_STALE_MIN` (minutes).
- Evidence: unique `validation_id`; insert-only; re-insert of same id raises (in-memory) / unique index (Mongo).
- AutoExecutor: skips terminals already `learning_consumed` (separate from paper runner).

### 1.10 Fail-closed vs fail-open

| Surface | Behavior |
|---|---|
| Broadcast without LIMITED_LIVE/FULL_LIVE | **Fail-closed** (never broadcasts) |
| Mode unresolved / read error (T0-3) | **Fail-closed** infra fault (not silent OBSERVE) |
| Noop quote provider in analysis mode (T0-1) | **Fail-closed** readiness error |
| Liquidity missing `pool_liquidity_usd` | **Permissive skip** (no fabricate) |
| Evidence insert failure | Logged; **not** raised (pipeline continues) |
| PaperValidationRunner per-opp exception | **Fail-open** (log, continue) — by design |
| Kill switch | Blocks PaperEngine + policy stage |

### 1.11 Six-chain support

| Layer | Six-chain? |
|---|---|
| H06 runtime seam / M6 SHADOW validation | Certified / evidence-complete (operator RPC) |
| `SimulationRouter.from_env` | **Base + base_sepolia only** (`BASE_RPC_URL`, `BASE_SEPOLIA_RPC_URL`) |
| `env_sync` | Exports `{CHAIN}_RPC_URL` for managed chains — **not consumed** by paper simulator for eth/arb/op/poly/bnb |
| Non-Base paper `eth_call` | Falls back to **heuristic** unless code/env mapping extended |

### 1.12 Audit / event logging

- Opportunity Journal stages (`ExecutionStatus` including `SHADOW_RECORDED`)
- Immutable `arbicore_paper_evidence`
- MID writer events from PaperEngine
- Mode transition audit (`execution_mode_audit`)
- Shadow certification engine can consume paper runner metrics

---

## 2. Test inventory

| Suite | Path | Coverage |
|---|---|---|
| Slice A | `app/backend/tests/test_v2118_paper_validation_slice_a.py` | Vocabulary, evidence, classifier, repo, pipeline integration (~26) |
| Slice B | `…/test_v2118_paper_validation_slice_b.py` | Liquidity, heuristic/eth_call/router, pipeline sim (~21) |
| Slice C | `…/test_v2118_paper_validation_slice_c.py` | Env flag, run_once, lifecycle, metrics (~10–12) |
| Live Slice C | `…/test_iter15_slice_c_live.py` | Live validation endpoints + pulse |
| PaperEngine | `…/test_phases_5_6_7_8.py` | Analyse, kill, capital clip |
| Pipeline glue | `…/test_p0c_pipeline_glue.py` | Never broadcast without promotion; PAPER terminates at shadow |
| AutoExecutor | `…/test_p0d_auto_executor.py` | Default SHADOW/PAPER never broadcasts |
| Mode ladder | `…/test_wave6a_mode_unit.py` | OBSERVE→PAPER→SHADOW→…; broadcast rules |
| Shadow route | `…/test_m2_4_shadow_route.py` | CONFIRMED → paper/SHADOW pipeline |
| Shadow cert | `…/test_v2119_shadow_certification*.py`, `test_v2119_shadow_cert_live.py` | Cert + paper_runner metrics + validation endpoint regression |
| Readiness | `…/test_control_readiness.py` | Includes `PAPER_VALIDATION` check key |

**Gap tests (not found):** paper wallet; cumulative paper PnL; six-chain `SimulationRouter.from_env`; Gate 9 drawdown; SHADOW demotion-to-PAPER ops contract.

Deliverable doc: `docs/PAPER_VALIDATION_v2.11.8_DELIVERABLES.md` (COMPLETE Slices A–C, 2026-08-06).

---

## 3. Configuration inventory

### 3.1 Feature / safety flags (paper-relevant)

| Variable | Default / posture | Effect |
|---|---|---|
| `ARBICORE_PAPER_VALIDATION_ENABLED` | Off unless set | Starts `PaperValidationRunner` |
| `ARBICORE_PAPER_RUNNER_REPROCESS_STALE_MIN` | unset → strict one-evidence-per-opp | Allow stale re-eval |
| `ARBICORE_PAPER_LIQUIDITY_SAFETY_RATIO` | 5.0 | Liquidity stage threshold |
| `ARBICORE_SAFETY_REQUIRE_PAPER_VALIDATION` | true | Blocks live approval without paper pass |
| `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` | off | Per-scanner shadow sink (avoid dup with runner) |
| `ARBICORE_AUTOEXEC_AUTOSTART` | **false** (M6) | Keep OFF |
| `ARBICORE_RUNTIME_AUTOSTART` | **false** (M6) | Keep OFF |
| `ARBICORE_SHADOW_CERT_ENABLED` | true (observed) | Shadow certification |
| `ARBICORE_EXECUTION_MODE` | SHADOW | Global posture label |
| Per-strategy `execution_mode_state` | FL=`SHADOW`; others=`PAPER` | Ladder; broadcast only LIMITED_LIVE+ |
| `services/execution/config.py` `shadow_enabled` | false default | Separate E3 shadow runner (CEX/services path) |

### 3.2 Config observed under `arbicore-x-v2` (inspect-only)

`deployment/upgrade/backend/.env` (and `.env.pre-paper-…` backup) shows:

- `ARBICORE_SHADOW_CERT_ENABLED=true`
- `ARBICORE_PAPER_VALIDATION_ENABLED=true`
- `ARBICORE_PAPER_RUNNER_REPROCESS_STALE_MIN=1`

→ Paper validation runner is **already contemplated / enabled in that env tree**. Cert audit does **not** flip any flags.

### 3.3 Mode ladder vs ops language (“SHADOW → PAPER”)

Code ladder (`execution/mode.py`):

`OBSERVE → PAPER → SHADOW → LIMITED_LIVE → FULL_LIVE`

Forward one step only; rollback any. So **PAPER → SHADOW is promotion**; **SHADOW → PAPER is demotion/rollback** (allowed).

M6 posture keeps strategies at SHADOW for flash-loan. Paper validation **does not require demoting to PAPER** — pipeline treats both as non-broadcast analysis modes. Prefer **stay SHADOW** + enable evidence runner.

---

## 4. Comparison vs roadmap & prior certification

| Artifact | Implication for paper |
|---|---|
| M6 POST-ALCHEMY-RESET SHADOW PASS (`docs/certification/M6_POST_ALCHEMY_RESET_SHADOW_20261002.md`) | Six-chain SHADOW evidence-complete; **explicitly forbids** paper execution / AUTOEXEC / RUNTIME / mode promotion in that pass |
| M6 plan / other M6 docs | SHADOW-only; paper deferred |
| H06 SIXCHAIN PASS | Six-chain seam certified; FL default SHADOW; AUTOEXEC/RUNTIME false |
| H05 | Opt-in fail-closed sizing; remains off in M6 posture |
| Handoff Gates 8–10 | Gate 8 = paper evidence; Gate 9–10 = duration + **paper P&L** |
| `docs/PAPER_VALIDATION_v2.11.8_DELIVERABLES.md` | Framework ready for Shadow Certification design; LIMITED_LIVE still gated |
| `docs/ui_v2/17_EXECUTION_READINESS_MATRIX.md` | Mode 2 Paper = plans/evidence, no broadcasts |
| `docs/ARBICORE_X_PRODUCTION_ACTIVATION_RUNBOOK.md` | PAPER = same as SHADOW + paper evidence flag; still non-broadcast |

**Reconcile:** M6 completed the SHADOW evidence bar. Next **safe** step is Paper Validation **evidence campaign** on the existing framework without LIVE/AUTOEXEC. Gate 9-style P&L remains a separate readiness item.

---

## 5. Gaps

1. **No PaperBroker / paper wallet / fill ledger / cumulative paper P&L.**
2. **PAPER vs SHADOW:** no semantic difference in pipeline terminal behavior.
3. **Six-chain paper `eth_call`:** simulator env map is Base-centric; non-Base → heuristic.
4. **Gas realism:** nominal % gas unless opp carries `gas_estimate`.
5. **Liquidity:** silent skip when reserves not annotated (honest, but weak for gate rigor).
6. **Runner fail-open** on per-opp errors (throughput over hard stop).
7. **Evidence insert failure** does not fail the pipeline result.
8. **Double-path risk** if both PaperValidationRunner and `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` + AutoExecutor run together.
9. **Handoff “paper fills”** language overstates evidence bundles as fills.
10. **Gate 6–7 market scarcity** (profitable route / atomic sim) still limits EXECUTABLE rate — orthogonal to paper plumbing but caps validation signal quality.

---

## 6. Blockers

### Blockers for evidence-path Paper Validation (Gate 8-as-evidence)

| Item | Severity | Notes |
|---|---|---|
| AUTOEXEC / RUNTIME / LIMITED_LIVE enable | Policy | Must remain OFF |
| Demotion/promotion confusion | Ops | Do not “promote to PAPER”; stay SHADOW |
| Duplicate drivers | Ops | Prefer single feeder (PaperValidationRunner) |
| Zero EXECUTABLE if no profitable REAL opps | Market | Expected; still collect UNPROFITABLE / other outcomes |

**No source blocker** for starting evidence-path validation.

### Blockers for true Paper Broker / Gate 9–10 P&L

| Item | Severity |
|---|---|
| Missing virtual wallet + balance model | **Hard** |
| Missing paper fill ledger + aggregated PnL / drawdown | **Hard** |
| Six-chain eth_call for non-Base paper sim | Medium (quality) |
| Nominal gas vs live gas | Medium (calibration) |

---

## 7. Minimal remediation plan

### Tier 0 — no source (preferred now)

1. Keep Gate 7 = $25, Gate 8 liquidity fail-closed, H05 off, AUTOEXEC/RUNTIME off, no signing/broadcast.
2. Confirm `ARBICORE_PAPER_VALIDATION_ENABLED=true` on the target validation host only (do not enable LIVE).
3. Keep flash-loan strategy mode **SHADOW** (do not demote unless explicitly desired for isolation).
4. Leave `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` off if global paper runner is on (avoid dup).
5. Collect: `validation/report`, `validation/metrics`, sample `EXECUTABLE`/`UNPROFITABLE` evidence IDs, Mongo `arbicore_paper_evidence` counts.
6. Document outcomes histogram over a fixed window; treat as Paper Validation evidence pass — **not** LIMITED_LIVE unlock.

### Tier 1 — XS source (only if six-chain eth_call quality required)

| File | Reason |
|---|---|
| `app/backend/arbicore/paper/simulator.py` | Extend `SimulationRouter.from_env` to map all six chains via `ARBICORE_RPC_URL_<CHAIN>` / `{CHAIN}_RPC_URL` already exported by `env_sync` |
| Matching tests under `tests/test_v2118_paper_validation_slice_b.py` | Prove eth_call selection for eth/arb/op/poly/bnb/base |

**Do not implement in this audit.**

### Tier 2 — larger (true Paper Broker / Gate 9)

New paper ledger module + APIs + tests for virtual balances, fills, cumulative PnL/drawdown; wire from EXECUTABLE evidence expected_net fields. Out of scope for “minor delta.”

---

## 8. Proposed validation sequence (ops-only)

1. **Preflight:** reaffirm M6 posture (SHADOW, AUTOEXEC=false, RUNTIME=false, Gate 7 $25, no signing).
2. **Confirm runner:** `GET …/validation/metrics` → `runner_enabled` / `is_running`.
3. **Confirm feed:** REAL/VERIFIED_REAL opps present in canonical repo (M6 six-chain shadow path).
4. **Windowed observe:** N hours or M cycles; snapshot report histogram + executable_rate.
5. **Spot-check:** pull 3–5 evidence IDs; verify stages + `simulation_backend` (`eth_call` vs `heuristic`).
6. **Fail-closed spot checks:** kill-switch engage → RISK_FAILURE / policy blocked; mode still non-broadcast.
7. **Stop criteria for “Paper Validation evidence-complete”:** runner healthy; evidence count > 0; no broadcast; AUTOEXEC/RUNTIME still false; honest empty EXECUTABLE allowed if market yields none.
8. **Explicit non-goals:** no LIMITED_LIVE, no signer unlock, no Gate 7/8 weaken, no paper wallet invent, no source patches in this phase.

---

## H. Exact files if source changes become required

**Not required for Tier 0 validation.** Listed only for completeness:

| File | Why |
|---|---|
| `app/backend/arbicore/paper/simulator.py` | Six-chain RPC env mapping for real eth_call |
| `app/backend/tests/test_v2118_paper_validation_slice_b.py` | Tests for that mapping |
| *New* `app/backend/arbicore/paper/wallet.py` (or similar) | Virtual paper balances — **only if Gate 9 P&L mandated** |
| *New* paper PnL aggregator + API in `server.py` | Gate 9–10 metrics — **only if mandated** |
| `app/backend/arbicore/execution/pipeline.py` | Only if PAPER must differ from SHADOW semantically |

**Do not modify any of the above in this audit pass.**

---

## Inspected artifacts (non-exhaustive)

- `app/backend/arbicore/paper/*`
- `app/backend/arbicore/execution/pipeline.py`, `mode.py`, `auto_executor.py`
- `app/backend/arbicore/runtime/composition.py` (shadow route / quote readiness)
- `app/backend/server.py` (validation + paper endpoints, runner lifecycle)
- `app/backend/arbicore/safety/approval.py`, `safety/config.py`
- `docs/PAPER_VALIDATION_v2.11.8_DELIVERABLES.md`
- `docs/certification/M6_*`, `H06_SIXCHAIN_PASS_20261001.md`
- `deploy/ARBICORE_X_HANDOFF_AUDIT.md` Gates 8–10
- `docs/ARBICORE_X_PRODUCTION_ACTIVATION_RUNBOOK.md`
- v2 env: `ARBICORE_PAPER_VALIDATION_ENABLED` present

---

## FINAL STATUS

**READY-WITH-MINOR-DELTA**

- **Ready now (no source):** Paper Validation Framework evidence campaign under current SHADOW / Gate 7 / AUTOEXEC-OFF posture.
- **Minor delta (optional, later):** six-chain paper `eth_call` env wiring.
- **Not ready (separate work):** true Paper Broker wallet + fill + cumulative P&L (Gate 9–10 as strict P&L).
