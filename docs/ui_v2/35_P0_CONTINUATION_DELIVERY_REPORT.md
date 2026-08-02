# Phase 35 · P0 Continuation Report — Autonomous Loop Delivered

**Date:** 2026-08-02
**Session outcome:** All four P0 items from the continuation audit
(`docs/ui_v2/34_PRODUCTION_CONTINUATION_AUDIT.md`) delivered, tested,
committed, and pushed to `origin/main`.

**Regression:** baseline **546 passed / 2 skipped** →
**599 passed / 2 skipped** across 51 test files (~4.5 s). Zero
regressions across all four phases.

**Commits pushed (in delivery order):**

| Phase | Commit | Files | Tests |
|---|---|---|---|
| P0-A | `4f7e182` — Opportunity Journal | `arbicore/data/journal.py` · `tests/test_p0a_opportunity_journal.py` · `server.py` (3 routes) | +12 |
| P0-B | `62f095e` — Learning Ledger | `arbicore/learning/ledger.py` · `tests/test_p0b_learning_ledger.py` · `server.py` (2 routes) | +16 |
| P0-C | `66c9a21` — Pipeline Glue | `arbicore/execution/pipeline.py` · `tests/test_p0c_pipeline_glue.py` · `server.py` (1 route) | +13 |
| P0-D | *(this commit)* — Autonomous Executor | `arbicore/execution/auto_executor.py` · `tests/test_p0d_auto_executor.py` · `server.py` (4 routes + startup + shutdown) | +12 |

---

## 1 · What the deployed VPS now does out of the box

The `_seed_execution_substrate` startup hook is the single entry point.
On boot it:

1. Bootstraps every existing subsystem (mode registry seeds, wallet
   registry, secret registry, capital policy, kill switch, canonical
   opportunity repo, config repos, telegram, scanner config).
2. Bootstraps the new **Opportunity Journal** indexes.
3. Bootstraps the new **Learning Ledger** indexes (over the pre-existing
   `calibration_log` and `arbicore_signal_metrics` collections — no
   new collections beyond what the CalibrationWorker + AdaptiveWeightsWorker
   already read).
4. Starts **ContinuousDiscovery** (unchanged from Phase 7A).
5. Starts the new **Autonomous Executor**.

Once running, every 30 s (`ARBICORE_AUTOEXEC_INTERVAL_S`):

- Executor pulls up to 25 (`ARBICORE_AUTOEXEC_BATCH`) recent rows from
  `DiscoveryRepo`.
- Each row is walked through **OpportunityPipeline.evaluate()** — every
  stage journaled: `DISCOVERED → QUOTED → GAS_ESTIMATED → PROFITED →
  POLICY → CERTIFIED → SHADOW_RECORDED | POLICY_DENIED | REJECTED | BROADCAST_SENT`.
- Every 4th tick (`ARBICORE_AUTOEXEC_LEARN_EVERY`) drains the
  **Learning Ledger**, converting terminal journal rows into
  `{predicted_confidence, survived}` samples for CalibrationWorker and
  `{signal_id, win_rate, sample_count}` upserts for AdaptiveWeightsWorker.
- Rows already in a terminal state AND already `learning_consumed=True`
  are skipped — the loop is idempotent.

---

## 2 · Safety invariants (tested + enforced in code)

| Invariant | How it is enforced | Where it is tested |
|---|---|---|
| Executor **never** promotes mode | No code path in `auto_executor.py` writes to `ExecutionModeRepo`. Only the pre-existing `POST /api/arbicore/execution/mode/{strategy}` route can move the ladder. | Reviewed manually — the executor only ever reads mode through the pipeline. |
| Executor **never** broadcasts unless mode is `LIMITED_LIVE` or `FULL_LIVE` | `OpportunityPipeline.evaluate` gates broadcast on `mode in BROADCAST_MODES`. In SHADOW/PAPER/OBSERVE the pipeline terminates before touching the broadcaster. | `TestPipelineModes::test_never_broadcasts_without_promotion`, `TestAutoExecutorTick::test_default_shadow_never_broadcasts` |
| Kill switch engaged → no broadcast | Pipeline's `_policy_check` returns POLICY_DENIED with `engine=kill_switch`. Journal captures the denial with full detail. | `TestPipelineModes::test_kill_switch_engaged_denies` |
| Capital policy denial → no broadcast | Pipeline's `_policy_check` returns POLICY_DENIED with `engine=capital`. | `TestPipelineModes::test_capital_denial_denies` |
| Certification failure → no broadcast | Pipeline records the certification report and marks the row REJECTED before reaching the broadcaster. | `TestPipelineModes::test_certifier_fails_causes_reject` |
| Learning label NEUTRAL for policy-denied / rejected rows | `label_entry` returns NEUTRAL; the ledger still stamps `learning_consumed=True` so the row isn't re-processed forever. | `TestLabelEntry::test_policy_denied_and_rejected_are_neutral`, `TestLearningLedgerEmit::test_emit_rejected_row_is_neutral_but_marked_consumed` |
| Ledger emissions idempotent | `learning_consumed=True` stamped by the ledger; batch emitter filters on `learning_label=PENDING`. | `TestLearningLedgerEmit::test_emit_is_idempotent` |
| Executor tick idempotent | Terminal + consumed rows are skipped explicitly at the top of the tick loop. | `TestAutoExecutorTick::test_terminal_and_consumed_rows_are_skipped` |
| Learning ledger error does not crash the tick | Errors captured in the tick summary; loop continues. | `TestAutoExecutorTick::test_ledger_error_does_not_crash_tick` |

---

## 3 · Historical Intelligence Dataset — every field the SHADOW loop captures

Confirmed by inspection of `curl /api/arbicore/journal?limit=3` after the
executor's first live tick on the deployed VPS. Fields captured on every
opportunity, whether it was traded or not:

- `opportunity_id`, `opportunity_type`, `chain`, `asset`, `buy_venue`, `sell_venue`, `scanner_family`
- `first_seen`, `last_seen`, `lifetime_ms`, `observation_count`
- `expected_profit_usd`, `capital_required_usd`, `spread_pct`, `gas_estimate {gwei, units, usd}`
- `confidence_score`, `risk_score`, `mev_risk_level`
- `certification_result {status, report}`, `policy_decision {decision, engine, reasons}`, `rejection_reason`
- `execution_status` (10-state enum including `SHADOW_RECORDED`)
- `mode` (whichever ladder rung the strategy was on at evaluation)
- `expected_result` (what the pipeline predicted would happen)
- `actual_result` (what actually happened after broadcast — populated only in LIMITED_LIVE/FULL_LIVE)
- `plan_id`
- `learning_label` (`POSITIVE | NEGATIVE | NEUTRAL | PENDING`)
- `learning_consumed` (idempotency flag)
- `events[]` (append-only trail — every state change is preserved)
- `created_at`, `updated_at`

**Nothing is discarded.** Rejections, kill-switch trips, policy denials,
below-threshold opps — all are journaled with full context so future
learning has the complete signal.

---

## 4 · New endpoints (10)

```
GET   /api/arbicore/journal
GET   /api/arbicore/journal/summary
GET   /api/arbicore/journal/{opportunity_id}
GET   /api/arbicore/learning/ledger/status
POST  /api/arbicore/learning/ledger/emit
POST  /api/arbicore/pipeline/evaluate
GET   /api/arbicore/auto-executor/status
POST  /api/arbicore/auto-executor/start
POST  /api/arbicore/auto-executor/stop
POST  /api/arbicore/auto-executor/tick
```

Server route surface: **141 → 151 routes** under `/api`.

---

## 5 · Configuration surface (all optional, all env-driven)

| Env var | Default | Purpose |
|---|---|---|
| `ARBICORE_AUTOEXEC_AUTOSTART` | `true` | Start the executor on backend startup. |
| `ARBICORE_AUTOEXEC_INTERVAL_S` | `30` | Seconds between executor ticks. |
| `ARBICORE_AUTOEXEC_BATCH` | `25` | Max opps per tick. |
| `ARBICORE_AUTOEXEC_MIN_CONF` | `0.0` | Confidence floor to gate opps entering the pipeline. |
| `ARBICORE_AUTOEXEC_LEARN_EVERY` | `4` | Fire the Learning Ledger every N ticks. |
| `ARBICORE_DISCOVERY_AUTOSTART` | `true` (pre-existing) | Start ContinuousDiscovery on backend startup. |

All existing operator surfaces (mode ladder, kill switch, capital policy,
wallet registry, secret registry, evidence signing) are unchanged.

---

## 6 · Deployment ladder — post-VPS-boot flow

The operator uses only the pre-existing operator UI + APIs:

1. **VPS starts →** all workers boot; executor + discovery in SHADOW/PAPER.
2. **Operator promotes flash_loan_arbitrage to LIMITED_LIVE** via
   `POST /api/arbicore/execution/mode/flash_loan_arbitrage` when they are
   satisfied with the shadow analysis. Broadcast is now authorised for
   that strategy only.
3. **First live broadcast fires** on the next executor tick — journalled
   as `BROADCAST_SENT`, actual result post-trade → `COMPLETED`.
4. **Learning Ledger converts** the COMPLETED row into a
   `(predicted_confidence, survived=pnl>0)` sample.
5. **CalibrationWorker's next tick** picks up the new sample from
   `calibration_log` and re-fits the isotonic calibrator.
6. **AdaptiveWeightsWorker's next tick** picks up the new
   `arbicore_signal_metrics` row and republishes the recommended weights.
7. **Improvement compounds** — every subsequent opportunity is scored by
   an increasingly better-calibrated confidence model with
   route-level-adjusted weights.

**No architectural rewrite required for any of the deferred P1 / P2
items** — every one of them is either an ergonomic refactor (unified
PolicyEngine class), a config action (signing key activation), a UI
surface (Ops page tab for the auto-executor), or a data addition
(more scanners, more chains). The autonomous loop itself is now
production-frozen.
