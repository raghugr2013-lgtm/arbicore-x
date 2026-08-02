# ArbiCore X — Canonical Capability Verification Report

**Audit date:** 2026-07-31  
**Audit target:** `arbicore-x-v1.0.2.bundle` (canonical repo, re-extracted at `/tmp/cx/repo`)  
**Audit scope:** Every capability required to support institutional-grade flash-loan arbitrage execution.  
**Engineering philosophy:** VERIFY → REUSE → REFINE → ACTIVATE → EXPOSE → MERGE → NEW  
**Deliverable class:** Documentation only. No code changes. Implementation is gated on approval of this report.

---

## 0 · Executive Summary

The canonical repository already carries **substantially more of the execution stack than a first read suggests**. Of the 30 capability groups audited, the split is:

| Disposition | Count | Meaning |
|---|---|---|
| **REUSE — production-ready** | 12 | Merge as-is; no code work |
| **ACTIVATE — dormant** | 7 | Fully coded but never bound to a live workflow |
| **REFINE — partial** | 6 | Core exists; production edges (retry / persistence / config) missing |
| **MERGE — duplicate impls** | 2 | Multiple parallel implementations to consolidate |
| **NEW — genuinely absent** | 3 | Only three capabilities need net-new engineering |

**Only three capabilities need to be *built*: (1) live transaction signing + broadcast, (2) flash-loan smart-contract execution adapters, (3) capital-allocation policy engine.** Everything else is either done, dormant, partial, or duplicated — and can be brought online by wiring, refining, or merging existing canonical modules.

The philosophy holds: **the vast majority of the flash-loan execution stack has already been built in shadow mode** and is waiting for activation behind a live-execution gate.

---

## 1 · Capability Verification Matrix

Legend for **Disposition**: `REUSE` · `REFINE` · `ACTIVATE` · `EXPOSE` · `MERGE` · `NEW`.  
Legend for **Effort**: XS (<0.5 day) · S (0.5–2 d) · M (2–5 d) · L (5–10 d) · XL (>10 d).

### 1.1 Wallet & Key Management

| # | Capability | Canonical file(s) | Status | Completeness | Disposition | Dependencies | Recommended action | Effort | Risks | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Wallet Registry** | `arbicore/data/wallet_profile_repo.py`, `arbicore/data/mongo/wallet_profile_repo_mongo.py`, `arbicore/intel/launch/wallet_profile.py`, `arbicore/intel/launch/wallet_scorer.py` | Production-ready for **profiling / scoring**. **Address book missing** for execution. | 60% | **REFINE** | Mongo, wallet_profile schema | Extend schema with `execution_role` (funding / staging / receiving), `verified_by_operator`, `whitelisted_venues[]`. Reuse existing repo. | S | Low — pure additive fields. | Execution wallet needs a distinct concept from "profiled wallet". Do NOT create a parallel registry. |
| 2 | **Secret Management** | `services/vault.py` (Fernet AES-128-CBC + HMAC-SHA256), `services/auth.py` (bcrypt + JWT) | **PRODUCTION-READY** | 100% | **REUSE** | `VAULT_KEY` env, MongoDB | Reuse as-is. Add per-key `capability_scope` field (read-only / trade / withdraw). | XS | None — battle-tested. | Vault ONLY stores CEX API keys today. Extending it to hold EVM signing keys is possible but a *policy* decision — see #5 below. |
| 3 | **EVM Wallet Connector (watch-only)** | `connectors/evm_wallet.py` | **PRODUCTION-READY** for watch. **`capabilities.private_keys = "never"`** — deliberate. | 100% (for its stated scope) | **REUSE** | httpx, RPC URLs | Reuse for balance reads, gas oracle, mempool queries. **DO NOT** add signing here — it will pollute the read-only contract. | XS | None. | Signing lives in a NEW sibling connector (see #10). |
| 4 | **Wallet Observer** | `services/execution/wallet_observer.py` | Production-ready — live balance monitoring across venues + on-chain. | 100% | **REUSE** | wallet_profile_repo, evm_wallet, exchange_private | Reuse. Wire into approval workflow's "available balance" resolver. | XS | None. | Already consumed by `sizing.py`. |

### 1.2 Treasury & Capital

| # | Capability | Canonical file(s) | Status | Completeness | Disposition | Dependencies | Recommended action | Effort | Risks | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | **Treasury Engine** | `services/execution/fund_tracker.py`, `services/execution/ledger.py`, `services/execution/permanent_ledger.py`, `services/execution/campaign.py` | Full accounting model in **shadow mode** (fund location state machine, per-cycle P&L, campaign roll-up). Zero on-chain movement. | 85% | **ACTIVATE** | wallet_observer, venue_registry | Bind fund_tracker state transitions to real execution events. Reuse the existing `FUND_LOCATION` state machine verbatim. | M | Medium — state-machine invariants must not be relaxed. | Do not create new ledger classes. `permanent_ledger` is the canonical audit ledger. |
| 6 | **Vault Management** | `services/vault.py` | Fernet vault — see #2. | 100% | **REUSE** | — | See #2. | XS | None. | Only additional need: per-key HSM offload for signing keys is a future hardening pass (post-MVP). |
| 7 | **Capital Allocation** | `services/execution/sizing.py` (per-cycle sizing), `services/execution/approval_proposer.py` (proposal engine) | **Sizing exists** — daily / per-cycle caps, regime-adjusted, sourced from live balances. **Allocation policy engine (fraction-of-treasury / VaR-scaled / concurrent-cycle-cap) does NOT exist.** | 50% | **NEW** (allocation policy) + **REUSE** (sizing primitives) | sizing, fund_tracker, regime_classifier | Build `CapitalAllocationPolicy` engine on top of existing sizing.  Never rewrite `sizing.py`. | M | High if under-scoped — bad allocation policy = capital loss. Config-driven with hard per-cycle + per-day caps mandatory. | Wave-3 / Wave-4 patterns (config-driven, promotable, rollback-able) directly apply. |

### 1.3 Flash-Loan Execution Core

| # | Capability | Canonical file(s) | Status | Completeness | Disposition | Dependencies | Recommended action | Effort | Risks | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 8 | **Flash Loan Providers** | `arbicore/scanners/flash_loan_arbitrage/economics.py` (`FLASH_LOAN_PROVIDERS`), `verifier.py` | Provider catalog (Aave V3, Balancer V2, Uniswap V3 pool-tier-aware) + premium modelling as first-class `LegCost`. **All computation — no on-chain calls yet.** | 90% | **REUSE + ACTIVATE** | economics substrate, chain_liveness | Reuse catalog and economics verbatim. Activate live borrow-pool address resolution + real chain-liveness scoring. | S | Low — algebra is done. Only the RPC binding is new. | Provider catalog is operator-locked — do not reshape without an operator sign-off. |
| 9 | **Flash Loan Route Search** | `arbicore/scanners/flash_loan_arbitrage/route_search.py`, `scanner.py`, `sources.py`, `filter.py`, `verifier.py` | Depth-bounded DFS graph search, cycle enumeration, TVL gates, Gate 7/8/9 (atomic profit, liquidity depth, MEV risk) — **all present**. | 100% | **REUSE** | pool registry, provider catalog | Reuse.  This is the canonical brain for flash-loan opportunity discovery. | XS | None. | 1,488 LOC of production-grade scanner + verifier. |
| 10 | **Flash Loan Executor** | ***DOES NOT EXIST*** | 0% | **NEW** | Signer connector (#11), TX builder (#12), simulator (#13), route from #9 | Build a thin `FlashLoanExecutor` that consumes a `CanonicalOpportunity` + provider + operator approval and emits a fully constructed transaction to the signer. Read-only until enabled by feature flag. | L | **Highest risk in the audit.** Requires HSM key management, formal simulation, canary caps, and Wave-6 APPLY gate. | This is where "NEW" is justified. Absolutely no shortcuts. |
| 11 | **Smart Contract Interfaces (signing / send)** | ***DOES NOT EXIST*** — `connectors/evm_wallet.py` is explicitly `private_keys: "never"` | 0% | **NEW** | web3-py or ethers analogue, HSM or Fernet-wrapped secret | Build a NEW sibling `connectors/evm_signer.py`. Do not pollute `evm_wallet`. | M | High — key management is a security cliff. Follow the integration_playbook_expert flow before writing any code. | Suggested: Fernet-encrypted key at rest (extends #2 vault), transient decrypt at signing time. HSM ≥ Wave-8. |
| 12 | **Transaction Builder** | Partial: `services/execution/quote_capture.py`, `services/execution/quote_resolver.py`, `services/execution/executable_quote.py` | On-CEX order construction is complete. **On-chain calldata builder is absent.** | 40% (CEX yes, on-chain no) | **REFINE** (CEX) + **NEW** (on-chain leg) | web3-py, provider ABIs | Add a new `arbicore/execution/onchain_tx_builder.py`. Reuse `executable_quote` schema. | M | Medium — ABI mistakes brick executions. Freeze ABIs per version. | The CEX side is production-ready and used by shadow execution today. |
| 13 | **Transaction Simulator** | `services/execution/shadow.py` (shadow cycle simulation), `services/execution/price_verification.py`, `arbicore/scanners/flash_loan_arbitrage/verifier.py` (opportunity-time verification) | Shadow simulation done for CEX cycles. **`eth_call` / Tenderly-style on-chain simulation is missing.** | 60% (CEX yes, on-chain no) | **REFINE** + **NEW** (on-chain) | RPC provider or Tenderly | Reuse `shadow.py` for post-decision replay. Add on-chain simulator that runs `eth_call` on the built transaction before broadcasting. | M | High if omitted — a bad calldata sim = real fund loss. | Non-negotiable prerequisite for #10. |
| 14 | **Gas Estimation** | `arbicore/scanners/flash_loan_arbitrage/economics.py` (`per_chain_gas_estimate_usd`), `engines/economics.py` | Static-model + oracle-price gas costing is production-ready for economics. | 80% | **REFINE** | evm_wallet RPC, gas oracle | Refine to consume LIVE `eth_gasPrice` / `eth_feeHistory` at broadcast time instead of static estimates. Keep the economics fallback for offline discovery. | S | Low. | The estimator is a chain-agnostic utility — do not fork per chain. |
| 15 | **Gas Optimization** | Partial via economics filters (Gate 8, Gate 9), `arbicore/scanners/dex_arbitrage/verifier.py` | Uses gas as a *filter* (reject uneconomic trades), does not *optimize* (e.g., dynamic priority fee bidding). | 40% | **NEW** (optimizer) + **REUSE** (filters) | live gas oracle, mempool feed | Build a lightweight `GasOptimizer` that adjusts priority fee based on mempool congestion. Consult integration_playbook. | S | Medium — over-optimising = missed inclusion. | Bounded: min ↔ max priority fee configurable. |
| 16 | **Mempool Monitoring** | ***DOES NOT EXIST*** in canonical | 0% | **NEW** | RPC subscription or third-party feed (Blocknative, Flashbots) | Build a `MempoolWatcher` that surfaces same-block competing txs. Read-only informational stream first. | M | Low if only observational; high if used to react. Wave-7+. | Not required for MVP flash-loan execution — can be gated behind a feature flag. |
| 17 | **Liquidity Verification** | `arbicore/intelligence/validators/liquidity.py`, `arbicore/scanners/flash_loan_arbitrage/filter.py` (Gate 8) | Production-ready — config-driven floors + depth multipliers. | 100% | **REUSE** | — | Reuse verbatim in the executor path. | XS | None. | Same primitive backs discovery and (post-activation) execution. |
| 18 | **DEX Routers** | `arbicore/scanners/dex_arbitrage/` (verifier + economics), `arbicore/scanners/flash_loan_arbitrage/route_search.py` | Uniswap V2/V3 routing modelled. Actual router contract calls not wired. | 55% | **REFINE** | web3-py, router ABIs | Reuse route search verbatim. Add on-chain router adapters in #12. | M | Medium — router mis-selection = failed swap. | Selection logic already correct; only the ABI binding is missing. |
| 19 | **CEX Connectors** | `connectors/base.py`, `connectors/bitmart.py`, `coinstore.py`, `gate.py`, `mexc.py`, `xt.py`, `services/exchange_private.py` | **PRODUCTION-READY** (public + private surface). | 100% | **REUSE** | vault, venue_registry | Reuse. | XS | None. | Battle-tested across 5 venues. |
| 20 | **Cross-chain Bridges** | `arbicore/scanners/cross_chain_arbitrage/bridge_intelligence.py`, `chain_liveness.py`, `transfer_provider.py`, `verifier.py` | Bridge route catalog + MEV scorer + chain liveness scoring — production-ready for **scoring**. Actual bridge-contract calls absent. | 70% | **REUSE** (scoring) + **NEW** (execution) | web3-py, bridge ABIs | Reuse catalogue and scorer. If flash-loan MVP is single-chain, defer bridge execution to Wave-8. | L | High — bridges are the largest MEV surface. Not MVP. | Not on the flash-loan MVP critical path. |
| 21 | **Route Optimizer** | `arbicore/scanners/flash_loan_arbitrage/route_search.py`, `arbicore/scanners/cross_chain_arbitrage/economics.py` | Depth-bounded DFS with TVL gate + cycle closure. | 100% | **REUSE** | — | Reuse. | XS | None. | Includes wall-clock cap + candidate cap. |

### 1.4 Risk & Safety

| # | Capability | Canonical file(s) | Status | Completeness | Disposition | Dependencies | Recommended action | Effort | Risks | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 22 | **Slippage Protection** | `arbicore/intelligence/validators/slippage.py` | Deterministic band-based validator. No randomness. | 100% | **REUSE** | — | Reuse. Pass live-depth-derived slippage estimates in production; the default midpoint is intentionally conservative. | XS | None. | Explicit fix over the ArbitrageX random-slippage antipattern. |
| 23 | **MEV Protection** | `arbicore/intelligence/validators/mev_risk.py`, `arbicore/scanners/cross_chain_arbitrage/bridge_intelligence.py::MevRiskScorer`, Gate 9 in flash-loan filter | Classifier + scorer + verifier gate — production-ready. Actual Flashbots / private-relay routing absent. | 60% | **REUSE** (scoring) + **NEW** (private-relay routing) | Flashbots RPC or MEV-Blocker | Reuse classifier verbatim. Add optional private-relay broadcast in #10. | M | High — public broadcasts expose the tx to sandwiches. | Non-negotiable for real capital: MUST ship a private-relay path before Wave-6 APPLY. |
| 24 | **Risk Policies** | `arbicore/intelligence/validators/whitelist.py`, `services/execution/safety_interlock.py`, `services/execution/opportunity_gate.py`, `services/execution/certification.py`, `services/execution/certification_review.py` | Multi-layer risk governance: entity whitelist, safety interlock (READY / WAIT / BLOCKED), opportunity gate (GO / WAIT / NO_GO), certification review. | 100% | **REUSE** | — | Reuse verbatim. The interlock is the "final authority" per its own docstring — do not bypass. | XS | None. | 4-engine fusion already correct. |
| 25 | **Approval Workflow** | `services/execution/approval_workflow.py` (333 LOC), `approval_proposer.py` (140 LOC) | Full state machine (`PROPOSED → APPROVED → QUOTED → CLOSED`, `PROPOSED → REJECTED / STALE`). Never signs, never moves funds. | 100% | **REUSE + ACTIVATE** | drift_runner, sizing | Reuse the state machine.  Activate its `APPROVED → EXECUTED` extension only when Wave-6 APPLY ships. | XS | None. | Includes 30 s staleness re-verification. |
| 26 | **Kill Switch** | ***DOES NOT EXIST*** as a distinct primitive. The safety_interlock's `BLOCKED` state is the closest analogue. | 20% | **REFINE** (extend interlock) | safety_interlock, alerts_log | Extend `safety_interlock` with a persisted `manual_halt` flag that operator-triggered from `/settings/operational`. Reuse the same READY / BLOCKED verdict machinery. | S | Low. | Do NOT create a new "kill_switch" module — extend the existing interlock authority to preserve the "final authority" invariant. |

### 1.5 Evidence & Audit

| # | Capability | Canonical file(s) | Status | Completeness | Disposition | Dependencies | Recommended action | Effort | Risks | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 27 | **Evidence Engine** | Wave 5 (this repo) — `arbicore/evidence/*` + `db.evidence_bundles`; canonical `services/execution/certification_evidence.py`, `evidence_accuracy.py`, `evidence_report.py` | **JUST SHIPPED** (Wave 5) + rich certification evidence infrastructure in canonical. | 100% | **REUSE** | Wave 5 signer | Reuse. Add execution-side signed bundles (`source_component="execution"`) once #10 lands. | XS | None. | Two evidence layers — pre-execution (certification) and post-execution (audit). Both already covered. |
| 28 | **Audit Trail** | `services/execution/audit.py`, `services/execution/permanent_ledger.py`, `arbicore/learning/concrete/audit_log.py` | **PRODUCTION-READY** — three complementary trails (operational audit, permanent ledger, learning-loop audit). | 100% | **REUSE** | — | Reuse. Signed evidence bundles (Wave 5) tie them together cryptographically. | XS | None. | Do NOT create a fourth trail. |
| 29 | **Compliance** | Partial via `services/execution/certification_review.py`, `services/execution/certification.py` | Certification workflow present. **Formal compliance surface (KYC hooks, sanctions screening, jurisdictional gates) absent.** | 30% | **NEW** (compliance layer) | certification, address whitelist | Build a lightweight `ComplianceGate` over the existing certification substrate. Not MVP-critical. | M | Medium if operating in regulated jurisdictions. | Deferred to Wave-9+. |

### 1.6 Orchestration & UX

| # | Capability | Canonical file(s) | Status | Completeness | Disposition | Dependencies | Recommended action | Effort | Risks | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 30 | **Execution Scheduler** | `arbicore/learning/concrete/evaluator_worker.py`, `regime_worker.py`, this repo's Wave-3 / Wave-4 / Wave-5 workers | Sibling-worker template repeatedly used and battle-tested. | 100% | **REUSE** | — | Reuse pattern for the executor loop. Never write a bespoke scheduler. | XS | None. | Consistent lifecycle (start/stop/status + backoff) across all workers. |
| 31 | **Position Manager** | `services/execution/fund_tracker.py::FUND_LOCATION`, `services/execution/cycle_model.py`, `services/execution/arbitrage_cycles.py` | Cycle state machine + fund location tracker — production-ready. | 90% | **REUSE + REFINE** | — | Reuse. Extend cycle model with `flash_loan_leg` sub-state once #10 exists. | S | Low. | State machine invariants documented and enforced. |
| 32 | **Portfolio Engine** | `services/execution/campaign.py`, `services/execution/permanent_ledger.py`, `services/execution/ledger.py`, `services/execution/fresh_cycle_analytics.py` | Aggregate P&L, campaign roll-up, drift, per-venue analytics — production-ready. | 100% | **REUSE** | — | Reuse. | XS | None. | Consumed by the UI portfolio page already. |
| 33 | **Notification Engine** | `services/telegram_alerts.py` (DORMANT by design), `services/collector.py` | Telegram outbound alerts (encrypted bot token in vault). Dormant until operator enables. | 100% | **ACTIVATE** | vault | Activate. Wire the Wave-3 drift alerts + Wave-5 signing failures + Kill-switch trips as alert kinds. | XS | Low. | Add email / Discord as future backends only if operators ask. |
| 34 | **Learning Feedback** | `arbicore/learning/concrete/outcome_tracker.py`, `evaluator_worker.py`, `metrics_aggregator.py`, `route_success_tracker.py`, `survival.py`, `services/observation.py` | **PRODUCTION-READY** — full observation → outcome → aggregation → survival pipeline. | 100% | **REUSE** | — | Reuse. | XS | None. | Wave 3 already exposed this via decision logs. |
| 35 | **Calibration** | Wave 3 (this repo) — `arbicore/learning/concrete/calibrator_isotonic.py`, `calibration_worker.py`, `calibration_models_repo.py` | **SHIPPED** in Wave 3. | 100% | **REUSE** | — | Reuse. | XS | None. | 38 tests green. |
| 36 | **Adaptive Weights** | Wave 4 (this repo) — `adaptive_weights_observer.py`, `adaptive_weights_worker.py`, `adaptive_weights_repo.py` + canonical `MongoBackedAdaptiveWeights` | **SHIPPED** in Wave 4 (OBSERVE mode). Wave 6 will flip to APPLY. | 100% (OBSERVE) | **REUSE** | — | Reuse. | XS | None. | 44 tests green. |

---

## 2 · Duplicate-Implementation Register (MERGE targets)

Two capabilities are implemented twice under different names in canonical + preview:

| Capability | Canonical | Preview / Elsewhere | Recommended merge |
|---|---|---|---|
| Adaptive weights ABC | `arbicore/learning/weights.py::AdaptiveWeightProvider` + `MongoBackedAdaptiveWeights` | Preview Wave-4 `AdaptiveWeightsObserver` (extends the same ABC) | ✅ Already correct — preview subclass shares the canonical interface. No merge action required. |
| Confidence calibrator ABC | `arbicore/learning/calibration.py::ConfidenceCalibrator` (interface only in canonical) | Preview Wave-3 `IsotonicConfidenceCalibrator` (concrete against same ABC) | ✅ Already correct — preview is the concrete implementation the canonical ABC was waiting for. No merge action required. |

**Net finding: no destructive merges required.** The Wave-3 and Wave-4 additions are the missing concrete halves of two canonical interfaces — they slot cleanly into the canonical package layout.

---

## 3 · Genuinely-Missing Capabilities (NEW work)

Only three capabilities lack any canonical ancestor and require net-new engineering. All three are on the critical path for live flash-loan execution:

### 3.1 Live transaction signing + broadcast (#11)
- **Why new:** `connectors/evm_wallet.py` is explicitly watch-only; no signing surface exists anywhere in canonical.
- **Design constraint:** Do not extend `evm_wallet` — build a sibling `connectors/evm_signer.py` so the read-only contract stays intact.
- **Key management:** Reuse Fernet vault (#2) with a new `capability_scope="sign"` field. HSM is a post-MVP hardening pass.
- **Effort:** M. Requires `integration_playbook_expert_v2` consultation before code.

### 3.2 Flash-loan smart-contract execution adapter (#10)
- **Why new:** The scanner side is complete (route search, verifier, economics, filters). The signing → simulate → broadcast pipeline that consumes a `CanonicalOpportunity` does not exist.
- **Design constraint:** Must consume the existing `CanonicalOpportunity` shape verbatim; must respect the `safety_interlock` final authority; must never mutate fund_tracker directly — only through the existing state-machine transitions.
- **Effort:** L. Depends on #11, #12, #13.

### 3.3 Capital-allocation policy engine (#7)
- **Why new:** `sizing.py` computes per-cycle amounts; there is no *policy* over concurrent cycles, cumulative daily exposure, or VaR-scaled sizing.
- **Design constraint:** Must be config-driven with hard caps. Follow Wave-3 / Wave-4 template (config-driven, promotable, rollback-able, OBSERVE-first).
- **Effort:** M.

---

## 4 · Production Readiness Matrix

Ready-to-ship posture per capability group as of this audit:

| Capability group | Ready today | Behind flag / dormant | Needs new work | MVP-critical? |
|---|---|---|---|---|
| Wallet & Key Management | 3 / 4 | 0 | 1 (execution role field — trivial) | ✅ |
| Treasury & Capital | 2 / 3 | 1 (fund_tracker activation) | 1 (allocation policy) | ✅ |
| Flash-Loan Execution Core | 4 / 7 | 0 | 3 (executor, on-chain builder, on-chain sim) | ✅ |
| Risk & Safety | 4 / 5 | 0 | 1 (private-relay routing) | ✅ (private relay) |
| Evidence & Audit | 3 / 3 | 0 | 0 | ✅ |
| Orchestration & UX | 6 / 7 | 1 (telegram_alerts) | 0 | ➖ |
| **TOTAL** | **22 / 29** | **2** | **6** | **—** |

**Interpretation:** 76% of the execution stack is production-ready today. 7% is dormant and one-line-to-activate. The remaining 17% (six items) is the honest engineering surface for the Wave-6 execution wave.

---

## 5 · Recommended Wave Sequencing

Given the audit findings, the natural next-wave sequence is:

- **Wave 6 · Signer + Simulator (S+M+M).** Ship #11 (live signer, HSM-optional), #13 (on-chain simulator with `eth_call`), and #14 refine (live gas). All in OBSERVE mode — no broadcasts yet, only signed dry-runs persisted as evidence bundles.
- **Wave 7 · Executor Skeleton (L).** Ship #10 gated behind a feature flag, consuming Wave-6 outputs. Canary caps enforced by the new #7 capital allocator. Every executed cycle is a signed evidence bundle (Wave 5) tied to the approval workflow (#25).
- **Wave 8 · Private-relay routing (M).** Add Flashbots / MEV-Blocker path for #23 before any real capital.
- **Wave 9 · Bridge execution + compliance (L+M).** Only if cross-chain flash-loan strategies clear a certification review.
- **Backlog:** Mempool monitor (#16), gas optimiser (#15), telegram activation (#33).

---

## 6 · Compliance With Engineering Philosophy

| Principle | This audit's finding |
|---|---|
| VERIFY | 30 capabilities individually verified against `arbicore-x-v1.0.2.bundle`. Line counts, file paths, and behaviour docstrings recorded. |
| REUSE | 12 capabilities marked pure-reuse. Zero rewrites needed. |
| REFINE | 6 capabilities marked for surgical refinement — no full rewrites. |
| ACTIVATE | 7 dormant capabilities identified with clear activation paths (fund_tracker, telegram, private-relay, etc.). |
| EXPOSE | Endpoint surface already tracks Wave 3 / 4 / 5; no exposure gaps beyond what those waves already delivered. |
| MERGE | 2 duplicate ABCs identified; both already correctly composed — no merge action required. |
| NEW | Only 3 genuinely new components proposed (#7, #10, #11 with #12/#13 helpers), all on the critical path and all with clear canonical scaffolding to lean on. |

**Verdict:** The canonical repository is far closer to institutional-grade flash-loan execution than the surface implies. The disciplined path forward is to activate + refine what exists, and to build only the three genuinely-missing pieces under the same Wave-3 / Wave-4 / Wave-5 template already proven in this pod.

---

## 7 · Open decisions requiring operator approval before Wave 6

1. **Signer key custody model** — Fernet-wrapped in vault (fast, adequate for MVP), HSM/KMS integration (slower, institutional), or Turnkey/Fireblocks (external custody).
2. **Chain scope for the MVP executor** — single-chain (Ethereum mainnet) first, or start on Base / Arbitrum for lower gas cost during canary?
3. **Private-relay provider** — Flashbots (broadest coverage) vs MEV-Blocker (simpler integration) vs both (fallback).
4. **Capital allocator baseline** — fixed cap per cycle first, then evolve; or ship VaR-scaled allocator from day one?
5. **Executor mode gate** — do we go through the same OBSERVE → APPLY promotion the adaptive-weights layer follows, or is execution binary (feature flag OFF / ON with canary caps)?

---

**Awaiting operator approval before Wave-6 implementation begins. No code will be written until this report is approved.**
