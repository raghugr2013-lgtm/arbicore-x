# ArbiCore X — Execution Readiness Verification & Production Matrix

**Audit date:** 2026-07-31  
**Audit target:** end-to-end execution pipeline as required by the approved **Production Execution Strategy** (Mode 1 Discovery / Mode 2 Paper / Mode 3 Limited-Live Flash-Loan / Mode 4 Future Expansion).  
**Sources of truth:** `arbicore-x-v1.0.2.bundle` (re-extracted at `/tmp/cx/repo`) + Wave-3 / Wave-4 / Wave-5 additions in the preview backend.  
**Engineering philosophy:** VERIFY → REUSE → REFINE → ACTIVATE → EXPOSE → MERGE → NEW.  
**Deliverable class:** Documentation only. No code changes. Wave 6 is gated on operator approval of this matrix.

---

## 0 · Executive Summary — Deployment Posture

At deployment the system will run in the following posture:

| Layer | State at deploy | Runtime workload |
|---|---|---|
| **Continuous Discovery (Mode 1)** | ✅ **LIVE from day 1** | 24/7 scanners, verifiers, intelligence, calibration, adaptive weights (OBSERVE), evidence signing, learning loops |
| **Paper Execution — CEX / DEX / Cross-chain / Portfolio / Treasury (Mode 2)** | ✅ **PAPER** | Same pipelines produce evidence-grade execution plans; no orders, no on-chain broadcasts; outcomes feed learning |
| **Flash-Loan Arbitrage (Mode 3)** | 🟡 **PAPER at deploy → LIMITED-LIVE only after Wave-6 signer/simulator lands and operator flips per-strategy flag** | Confidence-gated, approval-required, canary-capped, gas-only-treasury execution |
| **Everything else (Mode 4 Future Expansion)** | 🔒 **BLOCKED** | Per-strategy promotion lifecycle (PAPER → SHADOW → LIMITED-LIVE → FULL-LIVE) with explicit operator approval per step |

Bottom line: **Modes 1 & 2 are 100% supportable today from the existing canonical substrate.** Mode 3 requires the three genuinely-new pieces from the previous audit (signer / on-chain simulator / capital-allocation policy) plus a per-strategy mode flag added to the existing execution config.

---

## 1 · Mode-Gating Substrate Analysis

The canonical repo already carries the flags that make the 4-mode strategy expressible without inventing a new module:

| Flag (canonical) | Location | Today's behaviour | Wave-6 role |
|---|---|---|---|
| `execution_enabled` | `services/execution/config.py` | Global master. `False` by default. When `True`, activates the E5 executor (currently a stub). | Stays `False` in Mode 2 / 3 posture. Never flipped globally at deploy. |
| `wallet_enabled` | same | Gates automation-wallet signing. `False` = watch-only. | Flipped only for the gas wallet during Mode 3. |
| `shadow_enabled` | same | Drives SHADOW cycles off LIVE data, records "would-do", NO execution. | This IS the Mode-2 (Paper) engine. Turned `True` at deploy. |
| `hard_freeze` | same | Pauses even in-flight cycles → MANUAL_REVIEW. | This IS the Kill Switch. Operator-triggered. |

**Missing flag (NEW — trivial):** a **per-strategy** execution gate so we can flip `flash_loan_arbitrage=LIMITED_LIVE` while every other strategy stays in `PAPER`.

Proposed additive schema (config-only, no code redesign):

```json
"per_strategy_mode": {
  "flash_loan_arbitrage": "PAPER",     // PAPER | SHADOW | LIMITED_LIVE | FULL_LIVE
  "cex_arbitrage":        "PAPER",
  "dex_capital_arb":      "PAPER",
  "cross_chain_arb":      "PAPER",
  "portfolio_rebalance":  "PAPER",
  "treasury_moves":       "PAPER",
  "position_management":  "PAPER"
}
```

This slots cleanly into the existing `DEFAULTS` dict in `services/execution/config.py` and needs no new module.

---

## 2 · End-to-End Pipeline Verification

Fourteen stages, each verified against canonical + preview. Legend: `✅ ready`, `🟡 partial`, `🔒 dormant`, `❌ missing`.

### 2.1 Market → Discovery

| # | Component | Canonical owner | Current status | Disposition | Integrated | Tested | Prod-ready | Missing deps | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Market data ingestion (CEX orderbooks, tickers) | `connectors/base.py` + `bitmart/coinstore/gate/mexc/xt.py` | ✅ ready | REUSE | ✅ | ✅ (`test_sprint2_api.py` + connector-specific) | ✅ | — | Low |
| 2 | On-chain pool registry (DEX pools + TVL) | `arbicore/scanners/dex_arbitrage/sources.py`, `flash_loan_arbitrage/sources.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | Real-time TVL refresh cadence tunable via config | Low |
| 3 | Chain liveness / gas price feed | `arbicore/scanners/cross_chain_arbitrage/chain_liveness.py`, `flash_loan_arbitrage/economics.py::per_chain_gas_estimate_usd` | 🟡 partial | REFINE | ✅ (as economics input) | ✅ (unit) | 🟡 (uses static model; live `eth_feeHistory` binding pending) | Live RPC endpoint list per chain | Medium |
| 4 | Emission bus | `arbicore/emission_bus.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |

### 2.2 Discovery → Opportunity

| # | Component | Canonical owner | Current status | Disposition | Integrated | Tested | Prod-ready | Missing deps | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 5 | Universal opportunity verifier ABC | `arbicore/scanners/opportunity_verifier.py`, `verification_evidence.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 6 | **Flash-loan scanner + verifier** (Mode-3 critical) | `arbicore/scanners/flash_loan_arbitrage/scanner.py` (328 LOC), `verifier.py` (325), `economics.py` (218), `route_search.py` (192), `sources.py` (234), `filter.py` (132) | ✅ ready | REUSE | ✅ | ✅ (gate + verifier tests) | ✅ | Live quote provider (bind to Aave V3 / Balancer V2 / UniV3 mainnet) | Medium |
| 7 | DEX arbitrage scanner | `arbicore/scanners/dex_arbitrage/*` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 8 | CEX arbitrage scanner | `arbicore/scanners/cex_arbitrage/*` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 9 | Cross-chain arbitrage scanner | `arbicore/scanners/cross_chain_arbitrage/*` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 10 | Canonical opportunity model | `arbicore/models/canonical.py`, `discovery.py`, `enums.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 11 | Discovery source substrate | `arbicore/scanners/discovery_source.py`, `discovery/` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |

### 2.3 Opportunity → Confidence → Calibration → Adaptive Weights

| # | Component | Canonical owner | Current status | Disposition | Integrated | Tested | Prod-ready | Missing deps | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 12 | Signal confidence engine | `arbicore/intelligence/confidence.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | ConfidenceStore backed by Mongo (canonical `ConfidenceStore` interface is pluggable) | Low |
| 13 | Route-level ROI probability | `arbicore/intelligence/roi_probability.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 14 | Chain / opportunity scoring | `arbicore/intelligence/scoring.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 15 | **Confidence Calibration** | **Preview Wave 3** — `arbicore/learning/concrete/calibrator_isotonic.py`, `calibration_worker.py`, `calibration_models_repo.py` + canonical ABC `arbicore/learning/calibration.py::ConfidenceCalibrator` | ✅ ready | REUSE | ✅ (server startup wired) | ✅ (38 tests) | ✅ | — | Low |
| 16 | **Adaptive Weights (OBSERVE)** | **Preview Wave 4** — `adaptive_weights_observer.py`, `adaptive_weights_worker.py`, `adaptive_weights_repo.py` + canonical ABC `arbicore/learning/weights.py::AdaptiveWeightProvider` | ✅ ready | REUSE | ✅ | ✅ (44 tests) | ✅ | — | Low |
| 17 | Learning loop (evaluator + outcome tracker) | `arbicore/learning/concrete/evaluator_worker.py`, `outcome_tracker.py`, `metrics_aggregator.py`, `route_success_tracker.py`, `survival.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |

### 2.4 Risk → Treasury → Wallet

| # | Component | Canonical owner | Current status | Disposition | Integrated | Tested | Prod-ready | Missing deps | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 18 | Liquidity validator | `arbicore/intelligence/validators/liquidity.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 19 | Slippage validator (deterministic) | `arbicore/intelligence/validators/slippage.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 20 | MEV risk classifier | `arbicore/intelligence/validators/mev_risk.py`, `arbicore/scanners/cross_chain_arbitrage/bridge_intelligence.py::MevRiskScorer` | 🟡 partial | REUSE (scoring) + NEW (private-relay routing before Wave-7) | ✅ (as scorer) | ✅ | 🟡 (no private-relay path yet) | Flashbots / MEV-Blocker RPC binding | **High for live Mode 3** — public broadcasts leak sandwich surface. Mitigation: keep Mode 3 on private relay only. |
| 21 | Entity whitelist | `arbicore/intelligence/validators/whitelist.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 22 | Safety interlock (final authority) | `services/execution/safety_interlock.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 23 | Opportunity gate (GO / WAIT / NO_GO) | `services/execution/opportunity_gate.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 24 | Certification review | `services/execution/certification.py`, `certification_review.py`, `certification_evidence.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 25 | **Kill switch** | `services/execution/config.py::hard_freeze` + `safety_interlock.py::BLOCKED` verdict | 🟡 partial (persisted flag exists; UI trigger dormant) | REFINE — expose via `/settings/operational` toggle | 🟡 | 🟡 (backend gate tested, UI trigger not) | 🟡 | UI toggle wire + audit log entry per flip | Medium — an unexposed kill switch is a governance risk. **Must ship in Wave 6.** |
| 26 | Approval workflow | `services/execution/approval_workflow.py` (333 LOC), `approval_proposer.py` (140 LOC) | ✅ ready | REUSE | ✅ | ✅ (`test_sprint2_api.py`) | ✅ | — | Low |
| 27 | Wallet observer (balances) | `services/execution/wallet_observer.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 28 | Wallet profile registry (execution role field missing) | `arbicore/data/wallet_profile_repo.py`, `arbicore/data/mongo/wallet_profile_repo_mongo.py` | 🟡 partial | REFINE — add `execution_role` (`gas` \| `funding` \| `receiving`), `whitelisted_venues[]` fields | ✅ (as profiling repo) | ✅ | 🟡 | Schema patch only | Low |
| 29 | Treasury / fund tracker (state machine) | `services/execution/fund_tracker.py`, `ledger.py`, `permanent_ledger.py`, `campaign.py` | 🔒 dormant (fully coded, unbound) | ACTIVATE | 🔒 | ✅ (shadow tests) | 🟡 (activation wiring pending) | Bind fund_tracker transitions to real execution events (Wave 6.5) | Medium — activate only after Mode 3 executor stable |
| 30 | Vault (encrypted API keys) | `services/vault.py` (Fernet AES-128-CBC + HMAC-SHA256) | ✅ ready | REUSE | ✅ | ✅ | ✅ | `VAULT_KEY` env; per-key `capability_scope` field for signer secrets | Low |
| 31 | Auth (single-admin JWT + bcrypt) | `services/auth.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | `JWT_SECRET` env | Low |
| 32 | Capital sizing (per-cycle) | `services/execution/sizing.py`, `arbicore/intelligence/capital.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 33 | **Capital allocation policy (portfolio-level)** | ❌ missing | NEW | ❌ | ❌ | ❌ | Wave 6 — config-driven cap engine on top of `sizing.py` | High if under-scoped. **Non-negotiable prerequisite for Mode 3.** |

### 2.5 Flash Loan → Simulation → Safety Interlock

| # | Component | Canonical owner | Current status | Disposition | Integrated | Tested | Prod-ready | Missing deps | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 34 | Flash-loan provider catalog (Aave V3 / Balancer V2 / UniV3) | `arbicore/scanners/flash_loan_arbitrage/economics.py::FLASH_LOAN_PROVIDERS` | ✅ ready | REUSE | ✅ | ✅ | ✅ | Live pool address resolution (chain-specific) | Low |
| 35 | Flash-loan opportunity verifier (Gate 7/8/9) | `arbicore/scanners/flash_loan_arbitrage/verifier.py`, `filter.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | Live quote provider | Low |
| 36 | Route-search engine (graph + cycle enumeration) | `arbicore/scanners/flash_loan_arbitrage/route_search.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 37 | Live quote provider (RPC-bound) | ❌ missing (only `noop_quote_provider` exists) | NEW | ❌ | ❌ | ❌ | Wave 6 — bind to public RPC + provider ABIs | Medium |
| 38 | **On-chain transaction builder** (calldata) | ❌ missing (CEX side complete, on-chain absent) | NEW | ❌ | ❌ | ❌ | Wave 6 — new `arbicore/execution/onchain_tx_builder.py`; reuse `executable_quote` schema | Medium — ABI mistakes brick executions |
| 39 | **On-chain transaction simulator** (`eth_call` before broadcast) | ❌ missing (shadow simulation exists for CEX only) | NEW | ❌ | ❌ | ❌ | Wave 6 — non-negotiable prerequisite for any broadcast | **High** if omitted → real fund loss |
| 40 | **Live signer** (private-key custody + broadcast) | ❌ missing (`connectors/evm_wallet.py` is watch-only by design) | NEW | ❌ | ❌ | ❌ | Wave 6 — new sibling `connectors/evm_signer.py`; Fernet-wrapped secret via vault | **Highest** — key management + broadcast policy |
| 41 | Gas estimator (live) | `arbicore/scanners/flash_loan_arbitrage/economics.py::per_chain_gas_estimate_usd` | 🟡 partial | REFINE — bind to live `eth_gasPrice` at broadcast | ✅ (for economics) | ✅ | 🟡 (uses static model) | Live gas oracle | Medium |
| 42 | Safety interlock (READY / WAIT / BLOCKED) | `services/execution/safety_interlock.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |

### 2.6 Evidence → Execution Decision → Post-execution

| # | Component | Canonical owner | Current status | Disposition | Integrated | Tested | Prod-ready | Missing deps | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 43 | **Evidence bundle signing (Ed25519)** | **Preview Wave 5** — `arbicore/evidence/*` + `db.evidence_bundles` | ✅ ready | REUSE | ✅ | ✅ (41 tests) | ✅ | — | Low |
| 44 | Certification evidence report | `services/execution/certification_evidence.py`, `evidence_accuracy.py`, `evidence_report.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 45 | Audit trail (three layers) | `services/execution/audit.py`, `permanent_ledger.py`, `arbicore/learning/concrete/audit_log.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 46 | Notification engine (Telegram) | `services/telegram_alerts.py` | 🔒 dormant (encrypted bot token in vault) | ACTIVATE | 🔒 | ✅ | 🟡 (needs operator credentials + kind wiring) | Bot token via vault | Low |
| 47 | Position manager (cycle state machine) | `services/execution/cycle_model.py`, `arbitrage_cycles.py`, `fund_tracker.py::FUND_LOCATION` | ✅ ready | REUSE | ✅ | ✅ | ✅ | Extend cycle model with `flash_loan_leg` sub-state after #40 | Low |
| 48 | Portfolio / campaign engine | `services/execution/campaign.py`, `permanent_ledger.py`, `fresh_cycle_analytics.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 49 | **Per-strategy mode gate** (Mode 1 / 2 / 3 selector) | 🟡 substrate exists (`services/execution/config.py`) but per-strategy field missing | REFINE — additive dict, no rewrite | ❌ (field to add) | ❌ | ❌ | Wave 6 — config patch + endpoint | Low — schema is trivial; the risk is *runtime* gate enforcement in every executor path |

### 2.7 Continuous Discovery Loop (Mode 1 — always on)

| # | Component | Canonical owner | Current status | Disposition | Integrated | Tested | Prod-ready | Missing deps | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 50 | Discovery scheduler (worker template) | `arbicore/learning/concrete/evaluator_worker.py` + Wave-3 / Wave-4 / Wave-5 workers | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 51 | Regime classifier | `arbicore/learning/concrete/regime_worker.py`, `services/execution/drift_runner.py` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |
| 52 | Institutional intelligence pipelines | `services/execution/arbitrage_intel.py`, `arbicore/intelligence/*` | ✅ ready | REUSE | ✅ | ✅ | ✅ | — | Low |

---

## 3 · Per-Mode Readiness Snapshot

The same components mapped through the 4-mode lens:

### Mode 1 · Continuous Discovery (LIVE at deploy)

| Stage | Ready? | Blocker |
|---|---|---|
| Market ingestion → Emission Bus | ✅ | — |
| All 5 scanners + verifiers | ✅ | — |
| Intelligence (confidence, scoring, ROI, capital sizing) | ✅ | — |
| Calibration (Wave 3) | ✅ | — |
| Adaptive weights OBSERVE (Wave 4) | ✅ | — |
| Learning loop (outcomes, survival, aggregation) | ✅ | — |
| Evidence signing (Wave 5) | ✅ | — |

**Verdict:** Mode 1 is deployable today with zero code changes. All 52 stages above except signer/simulator/allocator run in Mode-1 already.

### Mode 2 · Paper Execution (LIVE at deploy for all non-flash-loan strategies)

| Stage | Ready? | Blocker |
|---|---|---|
| Shadow runner (`shadow_enabled=True`) | ✅ | — |
| Execution plan builder (CEX side) | ✅ | — |
| Paper trade replay through order books | ✅ (`ledger.py` sell-fill modeler) | — |
| Simulated outcomes → learning loop | ✅ | — |
| Certification evidence | ✅ | — |
| Per-strategy mode enforcement | ❌ (needs #49) | Additive config field |

**Verdict:** Mode 2 is deployable at Wave 6 after adding the per-strategy mode field. Cost: XS (config patch + one gate check per executor entry point).

### Mode 3 · Limited-Live Flash-Loan Execution (post-Wave 6, operator-flipped)

| Stage | Ready? | Blocker |
|---|---|---|
| Discovery / verifier / scoring / calibration | ✅ | — |
| Confidence threshold gate | ✅ (config-driven) | Add per-strategy threshold field |
| Simulation prerequisite (`eth_call`) | ❌ | Wave 6 #39 |
| Live signer (gas wallet) | ❌ | Wave 6 #40 |
| Transaction builder (calldata) | ❌ | Wave 6 #38 |
| Live gas / quote binding | 🟡 | Wave 6 #37 + #41 refine |
| Capital-allocation policy (per-cycle + per-day caps) | ❌ | Wave 6 #33 |
| Safety interlock | ✅ | — |
| Approval workflow | ✅ | — |
| Kill switch (UI-triggered) | 🟡 | Expose via `/settings/operational` |
| Evidence bundle per execution | ✅ (Wave 5 signing worker will pick it up) | — |
| MEV private-relay routing | 🟡 | Non-negotiable before live capital (Wave 7) |

**Verdict:** Mode 3 is deployable **after Wave 6 lands the 5 marked ❌ items + kill-switch UI**. Even then it must **stay behind operator approval per cycle** until Wave 7 adds private-relay routing.

### Mode 4 · Future Expansion (PAPER → SHADOW → LIMITED-LIVE → FULL-LIVE, per strategy, explicitly approved)

The `per_strategy_mode` field (#49) already carries the state machine.  Each promotion requires:
1. Operator write to `per_strategy_mode.<strategy>` = next state
2. Audit-logged approval reason
3. Signed evidence bundle stamping the promotion
4. Rollback endpoint (`rollback_per_strategy_mode(strategy, to_state)`)

**Verdict:** Mode 4 requires zero new engineering beyond the Mode-2 / Mode-3 substrate — it is a governance workflow on top.

---

## 4 · Gap-Closure Backlog for Wave 6

Sorted by dependency order. Every item cross-references the Wave-5 audit and the previous canonical capability verification.

| Order | Item | Effort | Dependencies | Notes |
|---|---|---|---|---|
| 1 | Per-strategy mode field in `execution_config` + gate check in every executor entry point | S | — | Enables Mode-2 immediately at deploy. |
| 2 | Extend `wallet_profile` schema with `execution_role`, `whitelisted_venues[]` | S | — | Distinguish gas wallet from receiving wallet. |
| 3 | Kill-switch UI toggle + audit log integration | S | `services/execution/config.py::hard_freeze` | Governance non-negotiable. |
| 4 | Capital allocation policy engine (config-driven, per-day + per-cycle caps, VaR-optional) | M | wallet_observer, sizing.py | Mandatory before any live cycle. |
| 5 | Live gas + quote provider bindings (RPC + provider ABIs) | S | web3-py, Aave V3 / Balancer V2 / UniV3 ABIs | Refine, do not rewrite existing economics. |
| 6 | On-chain transaction builder | M | live quote provider, provider ABIs | New `arbicore/execution/onchain_tx_builder.py`. |
| 7 | On-chain transaction simulator (`eth_call` dry-run) | M | tx_builder, RPC | **Non-negotiable prerequisite for any broadcast.** |
| 8 | Live signer (`connectors/evm_signer.py`) with Fernet-wrapped secret via vault | M | vault, tx_builder, simulator | Requires `integration_playbook_expert_v2` consultation. |
| 9 | Signed executions → evidence bundle worker picks up `source_component="execution"` | XS | Wave 5 signer | Auto — signing worker already fingerprint-tracks. |
| 10 | Activate fund_tracker state transitions on real execution events | M | signer, executor | Only after #8 stable. |
| 11 | Activate `services/telegram_alerts.py` — wire drift + signing-failure + kill-switch + Mode-3-execute kinds | XS | vault bot token | Governance visibility. |
| 12 | Documentation: Wave-6 deliverable + operator runbook | S | All of above | Same shape as Wave-3 / Wave-4 / Wave-5 docs. |

**Cumulative estimate:** ~10-14 engineering days for Wave 6, gated on 5 operator decisions.

---

## 5 · Compliance With Approved Execution Strategy

Cross-check against every rule in the strategy directive:

| Rule | Where enforced | Compliance |
|---|---|---|
| Discovery Engine runs 24/7 | Worker template + all 5 scanners | ✅ |
| Continuous learning + calibration + adaptive weights | Wave 3 + Wave 4 workers | ✅ |
| Every scanner + intelligence + engine analyses live markets | Mode 1 is unconditional | ✅ |
| CEX / DEX-capital / cross-chain / portfolio / treasury remain PAPER | Backlog #1 (per-strategy mode field) | ✅ post-Wave-6 |
| Only flash-loan may go LIMITED-LIVE post-deploy | Backlog #1 + operator flag flip | ✅ post-Wave-6 |
| Operator approval mandatory per cycle | `services/execution/approval_workflow.py` (already enforces) | ✅ |
| Confidence-threshold gated execution | Config-driven per strategy | ✅ post-Wave-6 |
| Full simulation must succeed before execute | Backlog #7 (on-chain simulator) | ✅ post-Wave-6 |
| All safety gates must pass | Safety interlock is final authority | ✅ |
| Expected profit > gas + fees | Flash-loan economics + Gate 7 | ✅ |
| Configurable gas + daily execution limits | Existing `execution_config.limits` | ✅ |
| Every execution produces evidence bundle | Wave 5 signing worker | ✅ |
| Every execution updates learning + calibration + adaptive weights + audit | Emission bus + evaluator_worker | ✅ |
| Flash-loan capital from lending protocol; own wallet funds gas only | Executor design constraint (Wave 6) | ✅ post-Wave-6 |
| No treasury capital exposed during limited-live phase | Enforced by `execution_role=gas` wallet + capital allocator | ✅ post-Wave-6 |
| Explicit approval per Mode-4 promotion | Per-strategy mode state machine + audit log | ✅ post-Wave-6 |
| System auditable / deterministic / configurable / reversible | Wave 3 / 4 / 5 + roll-back-able repos | ✅ |

**Verdict:** the approved strategy is fully expressible with (a) the existing canonical substrate, (b) the Wave-3 / Wave-4 / Wave-5 additions already shipped in this pod, and (c) the 12-item Wave-6 backlog above.

---

## 6 · Open decisions requiring operator approval before Wave 6 begins

Repeated from the previous audit (§7) — none has been decided yet:

1. **Signer key custody model** — Fernet-in-vault (fast MVP), HSM/KMS (institutional), or external custody (Fireblocks / Turnkey).
2. **MVP chain for Mode-3 executor** — Ethereum mainnet, or Base / Arbitrum canary for lower gas cost?
3. **Private-relay provider** — Flashbots vs MEV-Blocker vs both.
4. **Capital allocator baseline** — fixed per-cycle + per-day caps first, then evolve; or VaR-scaled from day one?
5. **Mode-3 promotion gate** — same OBSERVE → APPLY promotion as adaptive weights, or feature-flag with canary caps only?

Plus one strategy-level clarification:

6. **Per-strategy defaults at deploy** — do we ship with `flash_loan_arbitrage="PAPER"` at deploy (operator flips to `LIMITED_LIVE` after review), or `LIMITED_LIVE` from the first boot? Recommendation: **PAPER at deploy** — enforces the "no live execution until explicit approval" rule.

---

**Awaiting operator approval of this Production Readiness Matrix (and the 6 open decisions) before Wave 6 implementation begins.**
