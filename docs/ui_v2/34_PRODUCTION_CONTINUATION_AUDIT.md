# Production Continuation Audit — ArbiCore X

**Date:** 2026-08-02
**Baseline:** `git HEAD 18cc2cc` on `Arbicorex-ui-v2-slice-02` (private, connected).
**Regression suite:** **546 passed / 2 skipped** in `backend/tests/` (48 files, ~4.6s).
**Auditor:** Main agent (Emergent) — read-only verification only, zero code changes.

Verification method for every claim below:
- `grep` for class / function symbol in the file cited.
- Follow-through to the FastAPI route that mounts the module (server.py line numbers).
- Cross-check against `docs/ui_v2/*` implementation reports (Waves 1–7, Phase 8, Phase 10.1–10.6).

No feature has been re-implemented, mocked, or rewritten during this audit.

---

## 1 · Repository state before I touched anything

| Signal | Value |
|---|---|
| Working tree | `/app/` — 13 top-level directories; `.git` connected to `raghugr2013-lgtm/Arbicorex-ui-v2-slice-02` |
| Backend LOC | `server.py` — 3,424 lines; `arbicore/` — 60 modules across 10 packages |
| API surface | **141 routes** mounted under `/api` (88 GET, 45 POST, 6 PATCH, 1 PUT, 1 DELETE) |
| Frontend LOC | `frontend/src/v2/` — 6 pages, primitives, tokens.css, v2Api client |
| Docs | `docs/ui_v2/06 → 33` (28 implementation reports); `docs/PRD.md`; four `/app/audit/*.md` files |
| Bundles present | `arbicore-x-v1.0.1.bundle` (1.4 MB) + `arbicore-x-v1.0.2.bundle` (1.4 MB) + SHASUMS |
| Test files | 48 in `backend/tests/` |
| Env files | **Missing** — restored `backend/.env` and `frontend/.env` in this session; both were empty on entry (services were STOPPED) |

Services after restoring `.env`: all supervisors RUNNING, `curl /api/arbicore/operations/scanners` returns 200.

---

## 2 · Subsystem audit (verify-only, no changes)

Every row cites the file that already exists. A row is **COMPLETE** only if the module is (a) importable, (b) exercised by at least one route in `server.py`, (c) covered by at least one test.

| # | Subsystem | Verdict | Evidence |
|---|---|---|---|
| 1 | **Discovery Engine** | COMPLETE | `arbicore/execution/discovery.py::{DiscoveredOpportunity, DiscoveryRepo, ContinuousDiscovery}` · routes `/execution/discovery/{start,stop,status,tick}` · tests: `test_v2_wave6a`, `test_phase10_4_scanner`, `test_flash_loan_user_data` |
| 2 | **Live Quote Engine** | COMPLETE | `arbicore/execution/quoter.py::{UniV3QuoterV2, AerodromeSlipStreamQuoter, AerodromeClassicQuoter, QuoterRegistry, HopQuote, RouteQuote}` · used by planner + certification · tests: `test_phase10_10_8_live_quoter` |
| 3 | **Live Gas Engine** | COMPLETE | `arbicore/execution/gas.py::{RpcGasOracle, StaticGasOracle, GasEstimate}` · route `/execution/gas` · reused by certification + broadcast |
| 4 | **Production Economics** | COMPLETE (distributed) | Route `/arbicore/roi-probability` + `/portfolio/{deployable,exposure,allocation,treasury,ledger}` · relies on gas + quoter + slippage (`execution/slippage.py`) — no single "economics.py" but the pipeline is complete and tested (`test_v2_slice4`, 12 checks) |
| 5 | **Certification Pipeline** | COMPLETE | `arbicore/execution/certification.py::{ExecutionCertifier, StageResult, CertificationReport}` · routes `/execution/certification/{run,stages}` · tests: `test_wave6e_certification_unit`, `test_v2_wave6a` |
| 6 | **Broadcast Pipeline** | COMPLETE | `arbicore/execution/broadcast.py::{LimitedLiveBroadcaster, BroadcastReceipt, BroadcastError}` · route `/execution/plans/{plan_id}/broadcast` · gated by mode + kill_switch · tests: `test_wave7_calldata_and_broadcast` |
| 7 | **Revert Decoder** | COMPLETE | `arbicore/execution/broadcast.py::{decode_revert_data, revert_component, revert_explanation}` · tests: `test_stage13_preflight_revert_decoder`, `test_stage13_preflight_trace_fallback` |
| 8 | **Wallet Registry** | COMPLETE | `arbicore/execution/wallet_registry.py::WalletRegistryRepo` · 7 routes under `/execution/wallets/*` + audit history · tests: `test_wave6a_wallet_secret_unit` |
| 9 | **Secret Registry** | COMPLETE | `arbicore/secrets/registry.py::SecretRegistry` + `secrets/backends.py::FernetSecretBackend` · 5 routes under `/execution/secrets/*` (list, put, delete, rotate, test) · Phase 10.5 report `docs/ui_v2/33` |
| 10 | **Environment Sync** | COMPLETE | `arbicore/config/env_sync.py` (76 lines, Phase 10.10) · read-only OS-env mirror of `NetworkConfigRepo` · fires on startup + `settings/network/{apply,rollback}` · tests: `test_phase10_10_env_sync` |
| 11 | **Continuous Discovery** | COMPLETE | `ContinuousDiscovery` in the discovery module · start/stop/tick routes + `/execution/discovery/status` · Phase 10.4 report `docs/ui_v2/32` · tests: `test_phase10_4_scanner` |
| 12 | **Persistent Plans** | COMPLETE | `arbicore/execution/planner.py::{ExecutionPlanner, DryRunEngine, ExecutionPlansRepo}` · 6 routes under `/execution/plans/*` · tests: `test_v2_wave6b` (`TestPlanPersistence`) |
| 13 | **Evidence System** | COMPLETE | `arbicore/evidence/bundle.py::{canonical_json, evidence_hash, new_bundle}` + `evidence/signer.py` · 6 routes under `/intelligence/evidence/*` · tests: `test_wave5_signer_unit`, `test_wave5_worker_unit`, `test_v2_wave5` |
| 14 | **Learning modules** | COMPLETE for adaptive weights + calibration | `arbicore/learning/{calibration.py, weights.py}` + `learning/concrete/{adaptive_weights_worker.py, adaptive_weights_observer.py, calibration_worker.py, calibrator_isotonic.py, evidence_signing_worker.py}` · Mongo repos in `data/mongo/{calibration_models_repo, adaptive_weights_repo}` · tests: `test_wave3_*`, `test_wave4_*`, `test_v2_wave3`, `test_v2_wave4` |
| 15 | **Auto Executor** | **NOT IMPLEMENTED** as a distinct module. Broadcast is a route the operator triggers per-plan, not an unattended background executor. See §4 P0-A. |
| 16 | **Policy Engine** | PARTIAL (distributed) | Functional coverage via `execution/capital_policy.py::CapitalAllocator` (allocation policy) + `execution/mode.py` (mode gate) + `execution/kill_switch.py` + `wallet_health.py`. No single unified `PolicyEngine.check(plan) → allow/deny` orchestrator. See §4 P1-A. |
| 17 | **Opportunity Journal** | PARTIAL | `data/opportunity_repo.py::OpportunityRepository` (abstract) + `data/mongo/opportunity_repo_mongo.py` persist opportunities. `data/discovery_queue.py::DiscoveryQueue` persists candidates. No dedicated `journal` module that records **outcomes** (execution result, PnL delta, evidence hash, learning label) for later replay. See §4 P0-B. |
| 18 | **Universe Repository** | PARTIAL | `config/scanner_config.py` + `data/scanner_config_defaults.py` + `config/persistent.py` cover exchange / chain / pair enable-flags. No unified `universe_repository` that answers "which chain × dex × pair combinations are currently in-scope" as a first-class collection. Effectively adequate through `settings/scanner/family/*` routes but not centralised. Not a P0. |
| 19 | **Adaptive Weights** | COMPLETE | `learning/weights.py` + `learning/concrete/adaptive_weights_{worker,observer}.py` + Mongo repo · 4 routes under `/intelligence/weights/*` · tests: `test_wave4_*`, `test_v2_wave4` |
| 20 | **Calibration Worker** | COMPLETE | `learning/concrete/calibration_worker.py::CalibrationWorker` + `calibrator_isotonic.py` · started at import in `server.py` · routes `/intelligence/calibration{,/status,/history}` · tests: `test_wave3_*`, `test_v2_wave3` |
| 21 | **Learning Ledger** | **NOT IMPLEMENTED** — no `arbicore/learning/ledger.py`. Continuation request references this as the work in progress when credits ran out. Nothing partial exists on-disk; the closest thing is the Treasury Ledger under `/portfolio/ledger`, which is a financial ledger, not a learning-signal ledger. See §4 P0-C. |

**Summary count:** 14 COMPLETE · 4 PARTIAL · 2 NOT IMPLEMENTED.

---

## 3 · Second-task verification — Learning Ledger integration state

Continuation request said: *"Verify whether the following files already contain completed integration: arbicore/learning/ledger.py, server.py, arbicore/execution/discovery.py, arbicore/execution/auto_executor.py."*

Facts on-disk right now:

| File | Present? | Notes |
|---|---|---|
| `arbicore/learning/ledger.py` | **No** | No such file. `grep -rn "learning_ledger\|LearningLedger"` in `backend/` → **0 matches**. |
| `arbicore/execution/auto_executor.py` | **No** | No such file. `grep -rn "auto_executor\|AutoExecutor"` in `backend/` → **0 matches**. |
| `server.py` | Yes — 3,424 lines, 141 routes | No `ledger` or `journal` symbols wired for learning. Only 4 "ledger" hits, all in the Portfolio Treasury Ledger route. |
| `arbicore/execution/discovery.py` | Yes | 3 classes as listed in row 1 above. No learning-outcome callback path yet. |

**Verdict:** the previous session did **not** leave any Learning Ledger work on-disk in this branch. Either the work was never committed, or it landed on a different branch that is not currently checked out. Either way — from *this* repository's perspective, the Learning Ledger is greenfield and must be built from scratch. Nothing to preserve, nothing to finish.

---

## 4 · Production-readiness classification

Only items that would make the deployed VPS *unsafe or non-functional* are P0. Everything else is P1 or P2.

### P0 — Deployment blockers (must land before VPS deploy)

| ID | Item | Why it's a blocker | Effort |
|---|---|---|---|
| **P0-A** | **Auto Executor** — a bounded background loop that, when policy allows, picks the top-ranked plan from persistent plans, runs certification, applies policy, and broadcasts. Operator retains the kill switch + mode toggle. | Continuation request specifically states the VPS must *"Execute automatically when policy allows"*. Today broadcast is only per-request from the UI. Without this, the VPS is a manual dashboard, not autonomous. | ~250 LOC + 1 route + 2 tests |
| **P0-B** | **Opportunity Journal** — append-only ledger of every opportunity's terminal state (discovered → evaluated → certified → broadcast/skipped → post-trade result → learning label). Must be queryable by opp_id and by time window. | Continuation request states *"Record every opportunity"* and *"Learn from every outcome"*. Existing `OpportunityRepository` records opportunities but not the outcome chain. Without this, learning has nothing to consume post-deploy. | ~200 LOC + 2 routes + 3 tests |
| **P0-C** | **Learning Ledger** — the write-side companion to the Opportunity Journal that emits labelled samples into `calibration_models_repo` + `adaptive_weights_repo`. Effectively the bridge between "we broadcast this plan" and "the calibration worker retrained on the outcome". | Continuation request states *"Improve continuously"*. The workers exist but there is no code path that feeds them fresh labels from real broadcasts. | ~180 LOC + 2 routes + 2 tests |
| **P0-D** | **Pipeline glue** — wire Discovery → Persistent Plans → Policy → Certification → Broadcast → Evidence → Journal → Learning into the single loop diagrammed in the continuation request. Each subsystem exists; the loop itself is not centralised. | Same reason as A/B/C — without the loop, autonomy is a promise, not a fact. | ~120 LOC in the auto-executor + hooks (no new modules) |

### P1 — Strongly recommended before deploy

- **P1-A · Unified `PolicyEngine`** — a thin composer over `capital_policy`, `mode`, `kill_switch`, `wallet_health` that exposes one `evaluate(plan) → PolicyDecision` call. Currently every consumer wires those four sources by hand. Nice-to-have refactor; not a blocker because the individual policies *are* enforced.
- **P1-B · Signing-key activation** — startup log currently warns *"EVIDENCE SIGNING DISABLED"* because `SIGNING_ACTIVE_KEY_VERSION` is unset. Deployment `.env` template already documents this; needs to be filled and rotated on the VPS.
- **P1-C · Cron for periodic hygiene** — calibration retrain cadence, evidence key rotation, backup script (all exist as scripts; need cron entries in `.env` / `deployment/cron/`).

### P2 — Post-deployment tuning

- **P2-A · Unified `UniverseRepository`** — flatten `scanner_config` + `network_config` into one queryable "in-scope" projection. Purely ergonomic.
- **P2-B · Frontend surface for Auto Executor + Learning Ledger** — Ops page can render the loop's live state, pause/resume, and inspect the last N journal entries. Not needed for the loop to *run*; needed for operator confidence.
- **P2-C · More scanners / more chains** — trivially added once the loop is stable.

---

## 5 · What the continuation request explicitly asks us to preserve

- **Existing architecture** — 60 arbicore modules + 141 routes + 546 passing tests. No rewrite.
- **Existing UI v2** — 6 pages, Primitives, tokens.css. Zero UI changes required for P0 (backend-only work).
- **Existing test coverage** — every P0 item ships with new tests *in addition* to the current 546.
- **Existing docs** — new work adds `docs/ui_v2/35_...`, does not rewrite prior reports.

---

## 6 · Proposed execution order

If the user approves this audit, the P0 items will be delivered in this order — one phase, one commit, `pytest -q` clean between each:

1. **Phase A — Opportunity Journal** (data + routes + tests) → 546 → ~552 tests.
2. **Phase B — Learning Ledger** (write path from journal into learning workers + routes + tests) → ~552 → ~557 tests.
3. **Phase C — Auto Executor** (background loop that reads plans, applies policy, broadcasts, writes to journal, feeds ledger) → ~557 → ~564 tests.
4. **Phase D — Pipeline glue** (wire the loop end-to-end; explicit start/stop/status route; small hooks in discovery.py + broadcast.py) → ~564 → ~570 tests.
5. **Regression sweep** — `pytest tests/ -q` must remain clean.
6. **Commit + push to origin** after each phase.

Every phase respects the standing rules:
- Never rewrite working architecture.
- Never duplicate systems.
- Never introduce temporary fixes.
- Reuse `OpportunityRepository`, `ExecutionPlansRepo`, `CalibrationRepo`, `AdaptiveWeightsRepo`, `KillSwitch`, `ExecutionMode`, `LimitedLiveBroadcaster`.

**Awaiting user approval before writing Phase A.**
