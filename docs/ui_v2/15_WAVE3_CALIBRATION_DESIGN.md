# ArbiCore X — Wave 3 · Confidence Calibration Design Proposal

**Generated:** 2026-07-31
**Status:** DESIGN PROPOSAL — awaiting approval. **No code has been
written for this wave.**
**Objective:** Fit an empirically calibrated mapping from raw confidence
→ realised probability, satisfying the existing
`ConfidenceCalibrator` ABC contract.
**Non-goal:** No new subsystem. No new collection. No new worker
process. No UI redesign. No LLM.

**Verification source.** All decisions in this proposal are grounded in
file-verified inspection of `arbicore-x-v1.0.2.bundle` (extracted to
`/tmp/cx/`).

---

## 0 · Executive summary

Wave 3 is smaller than expected. The canonical repo already provides
**five of the six moving parts**:

| Concern | Canonical status | Wave-3 action |
|---|---|---|
| ABC interface | **Exists** (`learning/calibration.py::ConfidenceCalibrator`) | Reuse |
| Sample-collection write path | **Exists** (`services/observation.py::_maybe_predict` writes to `db.calibration_log`) | Reuse |
| Sample-resolution write path | **Exists** (`services/observation.py::_resolve_due` writes `survived: bool`) | Reuse |
| Persistence collection | **Exists** (`db.calibration_log`, indexed, 365d TTL) | Reuse |
| Scheduler | **Exists** (`learning/concrete/evaluator_worker.py::OutcomeEvaluator._loop`) | Reuse pattern (add sibling worker) |
| Concrete calibrator | **INTERFACE ONLY** (`"Not implemented yet"`) | **New — the single Wave-3 deliverable** |
| Public read endpoint | **Frozen** (Wave-1 `/api/arbicore/intelligence/calibration`) | Reuse |
| UI panel | **Live** (Wave-1 Intelligence → Calibration) | Reuse |

**Net-new code footprint: one concrete class + one sibling worker + one
persisted-model row.** Everything else is reuse.

---

## 1 · Calibration algorithm

### 1.1 Choice: **Isotonic Regression** (primary), **Platt (sigmoid)** (fallback)

Rationale — every criterion the user asked for is met by isotonic:

- **Deterministic.** Given the same `(predicted, survived)` samples,
  isotonic returns the same monotone step-function every time.
- **Explainable.** The output is a piecewise-constant mapping —
  operators can read it as "predicted 0.65 was realised 0.62 based on
  148 samples". This is exactly the shape the Wave-1 endpoint
  already emits.
- **Non-parametric.** No hyper-parameter beyond `min_samples_per_bin`,
  so no operator tuning required.
- **Monotone-preserving.** Raw confidence → calibrated confidence
  never inverts order (a raw 0.9 will never be recalibrated below a
  raw 0.5). Preserves the intuition operators built during Slice 0.
- **Numerically stable.** No optimisation, no gradient descent, no
  divergence.

Platt scaling (a single-parameter sigmoid) is the **automatic fallback**
when the isotonic fit degrades (see §6). It:
- Requires only ~ 20 samples to fit reliably.
- Produces a smooth curve (no step artefacts) at small sample sizes.
- Falls out to identity when the sigmoid collapses (safe recovery).

### 1.2 Bucketing (for the UI reliability diagram)

Independent of the fit itself, the endpoint emits a 10-bucket reliability
diagram: `[0.0-0.1), [0.1-0.2), … , [0.9-1.0]`. Each bucket carries:
- `predicted` — mean of raw confidences that fell in the bucket.
- `realised` — win rate in the bucket (` survived / total `).
- `n` — sample count.

Bucketing is a **rendering aid**, not the calibrator itself. The
calibrator uses the raw samples directly (no binning loss).

### 1.3 Scalar quality metrics

Both computed at fit time and persisted alongside the fitted curve.

- **Brier score** — mean squared error between predicted probability
  and realised outcome:
  `Brier = (1/N) · Σ (predicted_i − survived_i)²`
  Range `[0, 1]`, lower is better, `0` = perfect, `0.25` = coin flip.
- **ECE (Expected Calibration Error)** — weighted average of
  |bucket_predicted − bucket_realised| across the 10 buckets, weighted
  by bucket sample counts:
  `ECE = Σ (n_i / N) · |predicted_i − realised_i|`
  Range `[0, 1]`, lower is better.
- Reported to 4 decimals to match the Wave-1 UI panel.

---

## 2 · Persistence model

### 2.1 Sample storage — reuse `db.calibration_log`

**Nothing to add.** The canonical collection already provides:

```
db.calibration_log document {
  "id": uuid,
  "ts": iso,
  "created_at": iso,             # TTL anchor (365d)
  "route_id": str,
  "exchange": str,
  "predicted_confidence": float, # in [0..100] per the ABC contract
  "hold_probability": float,
  "net_pct_at_prediction": float,
  "min_net": float,
  "horizon_min": int,
  "resolve_after": iso,
  "status": "pending" | "resolved" | "unresolved",
  "realized_net_pct": float,     # only on resolved
  "survived": bool,              # only on resolved — the outcome bit
  "resolved_at": iso,
}
```

Existing indexes: `(status, resolve_after)`, `(route_id, ts DESC)`,
`(created_at)` TTL 365d. Perfect for the fit query.

### 2.2 Fitted-model storage — reuse existing pattern

Add a small sibling collection `db.calibration_models` (2–3 rows steady
state) matching the shape of existing model-adjacent collections
(`readiness_snapshots`, `execution_config`). Not a new subsystem —
just a persistence row.

```
db.calibration_models document {
  "id": "confidence_calibrator@YYYY-MM-DD.HH",
  "kind": "confidence",
  "algorithm": "isotonic" | "platt" | "identity",
  "fitted_at": iso,
  "window_start": iso,
  "window_end": iso,
  "n_samples": int,
  "n_pending_dropped": int,
  "n_unresolved_dropped": int,
  "brier_score": float,
  "ece": float,
  "drift_alert": bool,
  "buckets": [ {bucket, predicted, realised, n} × 10 ],
  "curve": {
    # isotonic: sorted (x, y) pairs where x = raw confidence, y = calibrated
    "x": [float],
    "y": [float],
    # platt fallback:
    #   "a": float, "b": float   (sigmoid(a*x + b))
  },
  "supersedes": id | null,
  "state": "active" | "shadow" | "retired",
}
```

Two invariants:
- **Exactly one `state=active` row per `kind` at any time.** Promotion
  is an atomic two-write (activate new, retire old) inside the worker.
- **Retired rows are kept for audit** (30-day retention after retire —
  add a TTL on `retired_at` field).

### 2.3 Alternative rejected

"Store the curve as a NumPy pickle on disk" — rejected. The pickle
couples deployment/rollback to filesystem state; Mongo storage is
< 1 KB per model and audit-loggable.

---

## 3 · Rolling-window strategy

- **Window:** 30 days rolling. Matches operational recency-vs-stability
  balance already used by `MongoRouteSuccessTracker` and by
  `regime_history`.
- **Query:** `db.calibration_log.find({"status": "resolved", "resolved_at": {"$gte": now - 30d}})`
- **Pending / unresolved handling:**
  - `status=pending` — not yet due → excluded (no outcome).
  - `status=unresolved` — outcome window elapsed with no data → **treated
    as `survived=False`** (matches existing "safe no-op" pattern in
    `outcome_tracker.py::_mark_no_data`).
  - Counters `n_pending_dropped` / `n_unresolved_dropped` are stored
    on the fitted model for operator visibility.
- **Minimum-sample guard:** fit requires ≥ 200 resolved samples in the
  window. Below that:
  1. Fall back to Platt scaling if ≥ 30 samples.
  2. Fall back to identity mapping if < 30 samples.
  Every fallback is logged.

---

## 4 · Recalculation cadence

### 4.1 Where the job lives

**Reuse the existing worker pattern.** Add a sibling class
`CalibrationWorker(interval_s=3600)` in
`app/backend/arbicore/learning/concrete/calibration_worker.py`,
matching the shape of `OutcomeEvaluator` in the same directory. No new
process; wire it into whatever bootstrap composes `OutcomeEvaluator`
today (`arbicore/runtime/composition.py`).

Reuse pattern:
- Same `start() / stop() / status` shape as `OutcomeEvaluator`.
- Same `_loop()` structure with `asyncio.Event` stop.
- Same idle-safe semantics (each tick is a no-op if no new resolved
  samples).

### 4.2 Cadence

- **Default: 3600 s (hourly)**, matching what was proposed in Wave-1
  §5.
- Rationale:
  - `calibration_log` writes are 1–10 per minute in busy hours.
  - A 3600 s tick sees ~ 60–600 new samples — enough to detect drift.
  - Fit cost is O(n log n); 10k samples = ~ 10 ms; hourly is
    trivially cheap.
  - Faster cadences risk hysteresis in the calibrated curve (operator
    dashboard flapping); slower cadences risk delayed drift response.
- **Backoff on error:** exponential (60 s → 120 s → 300 s → 600 s cap)
  matching the existing worker family.

### 4.3 Trigger points beyond cadence

- **Manual refresh:** admin endpoint `POST /api/arbicore/intelligence/calibration/refresh`
  triggers a fit immediately (auth-gated). Optional Wave-3 extension.
- **No event-driven refresh** in Wave 3. The scheduler ownership stays
  singular.

---

## 5 · Confidence update policy

### 5.1 Read path (`ConfidenceCalibrator.calibrate`)

- **Pure function.** No side effects, no IO in the hot path.
- **In-memory cache** of the active curve. Refreshed on:
  - Worker tick (writes new active row → next `calibrate()` call
    reads it).
  - Explicit invalidation via the manual refresh endpoint.
- **Latency budget:** < 200 µs per call. Sub-millisecond by design.

### 5.2 Semantic contract

- Input: `raw_confidence` in `[0, 100]` (per ABC docstring).
- Output: `calibrated_confidence` in `[0, 100]`.
- **Identity fallback** when no active model exists (bootstrap
  behaviour + safe recovery).
- **Monotone-preserving guarantee** (isotonic + identity + platt all
  preserve).
- **Never emits NaN / Inf.** Explicit clamp to `[0, 100]`.

### 5.3 Wiring into existing consumers

Zero refactor. The existing `ConfidenceEngine` today emits raw
confidence directly. Post-Wave-3, insert one line at emission time:
```
calibrated = calibrator.calibrate(raw, context={"opportunity_type": …})
```
and record BOTH `raw` and `calibrated` on the opportunity model. The
decision-log versioning added in Wave 1 already carries
`model_version` — extend it with `calibrator_version` (a single
`str`). No decision-log schema break.

---

## 6 · Drift detection thresholds

### 6.1 Drift signal

Every fit tick computes ECE against the current window. A rolling
30-tick history (~ 30 hours) of ECE is retained in-memory.

- **Drift alert ON** when the latest ECE ≥ `mean(history) + 2 * stdev(history)`
  AND the latest ECE > `0.05` (absolute floor).
- **Drift alert OFF** when the latest ECE returns below
  `mean(history) + 1 * stdev(history)` for 3 consecutive ticks
  (hysteresis, prevents flapping).
- Absolute-floor threshold `0.05` chosen from the Wave-1 stub
  behaviour and from the well-calibrated regime typically observed in
  binary classifiers with n > 200.

### 6.2 What drift means operationally

- The flag surfaces on the Wave-1 UI panel (already implemented) and
  on the audit-log via a `calibration_drift` event.
- **No auto-action** on drift. Drift is a signal to the operator to
  investigate — matching the existing platform posture (interlock
  gates handle safety, calibration is telemetry).

### 6.3 Persistence

Every drift transition is logged to
`db.alerts_log` via the existing `AlertService`, tagged
`category="calibration"`.

---

## 7 · Recovery behaviour

Ordered from most-preferred to least-preferred:

1. **Warm fit succeeds** → new active row promoted, previous retired.
2. **Warm fit yields worse ECE** than the current active
   (`new_ece > current_ece + 0.02`) → keep current active; save new
   fit as `state="shadow"` for audit.
3. **Sample count below Platt threshold (< 30)** → keep current
   active if any; otherwise identity mapping.
4. **Fit raises exception** → log to `alerts_log`, keep current active.
5. **Mongo unavailable** → in-memory cached curve continues to serve
   `calibrate()`. Worker retries with backoff.
6. **First-run bootstrap, no active row** → identity mapping. Log a
   single INFO alert on startup.

Every recovery path is deterministic. Every fallback is auditable.

---

## 8 · Computational cost

| Path | Cost | Frequency |
|---|---|---|
| `calibrate(raw, ctx)` (hot path) | O(log n) binary-search on curve, ~ 200 µs | Every opportunity emission (~ 100/min peak) |
| Fit tick | O(n log n) isotonic; ~ 10 ms for n=10k | Once per hour |
| Mongo read (samples) | Indexed on `(created_at)` TTL + `(status, resolve_after)`; ~ 200 ms for 10k rows | Once per hour |
| Mongo write (active + retire) | Two writes, ~ 20 ms | Once per hour |
| Memory footprint | Active curve ≈ 200 (x,y) points × 8 bytes = 3.2 KB | Constant |

**Total ambient CPU:** << 0.1% of one core. No new network IO. No LLM
tokens. No external dependencies beyond `numpy` and `scipy.stats` for
the isotonic fit (both already in `requirements.txt` implicitly via
existing scientific-Python usage — will re-verify in implementation).

Fallback: if `scipy` is not present, implement PAV (Pool-Adjacent-
Violators) manually — 30 lines of pure Python, same complexity.

---

## 9 · Expected operator-visible metrics

These metrics already have their contract frozen by the Wave-1
endpoint and rendered in the Intelligence → Calibration UI panel:

| Metric | Where surfaced | Data source (post-Wave-3) |
|---|---|---|
| `brier_score` | Metric tile | Fresh from active `calibration_models` row |
| `ece` | Metric tile | Fresh |
| `n_samples` | Metric tile | Fresh (window-scoped count) |
| `drift_alert` | Chip (OK / DRIFT) | Fresh |
| `buckets[]` | Reliability diagram (10 rows) | Fresh |
| `model` | Diagram header | `id` of active row |
| `window_days` | Diagram header | 30 |

**Additional metrics newly available** (not surfaced in UI yet — that
comes in a later refinement, not Wave 3):
- `n_pending_dropped`, `n_unresolved_dropped`
- `algorithm` (isotonic / platt / identity)
- `supersedes` — link to previous active for audit
- `curve` inspection endpoint (already-frozen shape)

---

## 10 · Data flow diagram (proposed post-Wave-3)

```
┌────────────────────────────────────────────────────────────────┐
│  Opportunity emitter (existing)                                │
│    ├─ raw_confidence  ─────────────────────────────────────┐   │
│    └─ opportunity → written to db.opportunities             │  │
└────────────────────────────────────────────────────────────┼───┘
                                                              ▼
┌────────────────────────────────────────────────────────────────┐
│  ConfidenceCalibrator.calibrate() (NEW – Wave 3)               │
│    ├─ reads active curve from in-memory cache                  │
│    └─ returns calibrated_confidence                            │
└────────────────────────────────────────────────────────────────┘
                                                              │
                                                              ▼
┌────────────────────────────────────────────────────────────────┐
│  services/observation.py::_maybe_predict (existing)            │
│    └─ writes {predicted_confidence, resolve_after, status:      │
│        pending} → db.calibration_log                            │
└────────────────────────────────────────────────────────────────┘
                                                              │
                          (wait horizon_min)                  │
                                                              ▼
┌────────────────────────────────────────────────────────────────┐
│  services/observation.py::_resolve_due (existing)              │
│    └─ writes {survived: bool, realized_net_pct, status:         │
│        resolved} → db.calibration_log                           │
└────────────────────────────────────────────────────────────────┘
                                                              │
                       (hourly worker tick)                   │
                                                              ▼
┌────────────────────────────────────────────────────────────────┐
│  CalibrationWorker._loop (NEW – Wave 3, sibling to             │
│  OutcomeEvaluator)                                              │
│    ├─ read window of resolved samples from db.calibration_log   │
│    ├─ compute buckets, brier, ece, drift                        │
│    ├─ fit isotonic (or platt / identity per §7)                 │
│    ├─ write new row to db.calibration_models (state=active)     │
│    ├─ retire prior row                                          │
│    └─ refresh in-memory cache                                   │
└────────────────────────────────────────────────────────────────┘
                                                              │
                                                              ▼
┌────────────────────────────────────────────────────────────────┐
│  GET /api/arbicore/intelligence/calibration                    │
│    └─ reads latest state=active row from db.calibration_models  │
│       (previously served the Wave-1 stub)                       │
└────────────────────────────────────────────────────────────────┘
                                                              │
                                                              ▼
┌────────────────────────────────────────────────────────────────┐
│  UI · Intelligence → Calibration (existing Wave-1 panel)       │
│    └─ renders reliability diagram + Brier + ECE + drift chip   │
└────────────────────────────────────────────────────────────────┘
```

---

## 11 · Scheduler integration

The worker follows the exact template of `OutcomeEvaluator`:

- **File:** `app/backend/arbicore/learning/concrete/calibration_worker.py`
- **Class:** `CalibrationWorker`
- **Interval:** `DEFAULT_INTERVAL_S = 3600`
- **Status shape:** identical to `OutcomeEvaluator.status` (running,
  interval_s, iterations, last_run_at, last_result, last_error) so
  the same read surface can serve both.
- **Startup:** one line in `arbicore/runtime/composition.py` (or
  wherever `OutcomeEvaluator` is composed today).
- **Shutdown:** same 5 s timeout pattern.

The worker **does not** run at process startup. It runs once per hour.
On startup, if no active model exists, `calibrate()` falls back to
identity (see §7 case 6).

---

## 12 · Performance impact

Compared to the current runtime:

| Metric | Before Wave 3 | After Wave 3 | Delta |
|---|---|---|---|
| Opportunity emission latency | X µs | X + 200 µs | negligible (< 0.5%) |
| Mongo query volume | Y queries/s | Y + ~ 1 query/hour | negligible |
| Mongo write volume | Z writes/s | Z + ~ 2 writes/hour | negligible |
| Memory footprint (backend proc) | M MB | M + 4 KB | negligible |
| CPU load (backend proc) | C% | C + ~ 0.05% | negligible |
| Network egress | N MB/s | N + 0 | zero |

**No LLM calls. No external HTTP calls. No new dependencies expected**
(NumPy + SciPy already-in-tree; if SciPy is absent we ship a 30-line
PAV implementation).

---

## 13 · Test coverage plan

Every deliverable will be covered by contract + unit tests.

- **Unit — algorithm**
  - Isotonic PAV correctness against known fixture.
  - Platt fallback correctness.
  - Identity fallback on empty input.
  - Monotone preservation across 1000 random inputs.
  - `calibrate()` clamps to `[0, 100]`.
  - Brier + ECE closed-form correctness against hand-computed
    fixtures.
- **Unit — persistence**
  - Active-model uniqueness invariant across concurrent worker ticks.
  - Retirement TTL correctness.
  - Sample-window bounds respected.
- **Unit — recovery paths (§7 items 1–6)**
- **Unit — drift-detection state machine** (transitions + hysteresis).
- **Integration — worker end-to-end**
  - Seed samples in `db.calibration_log` → tick worker → assert new
    `state=active` row + populated buckets.
  - Assert `GET /intelligence/calibration` returns fresh data.
- **Contract — Wave-1 tests still green** (`test_v2_wave1.py`,
  currently 8 pass — must remain 8 pass unchanged).
- **Performance — micro-benchmark**
  - `calibrate()` p99 < 500 µs on 5k random inputs.
  - Fit tick p99 < 100 ms for 10k samples.

Target: **≥ 15 new tests** covering the surfaces above.

---

## 14 · Calibration quality metrics (targets)

Steady-state targets for a healthy Wave-3 deployment (subject to real
data behaviour):

| Metric | Target | Alert threshold |
|---|---|---|
| `brier_score` | < 0.15 | > 0.20 |
| `ece` | < 0.05 | > 0.08 |
| Reliability gap per bucket | < 5 pp | > 10 pp on any bucket with n ≥ 30 |
| n_samples per fit | ≥ 500 | < 200 (falls back to Platt) |
| Drift-alert transitions | ≤ 2 / week | > 5 / week (indicates fit instability) |

These are *targets*, not guarantees — the actual bar is the operator's
review of the Wave-1 UI panel. Numbers here inform the alert thresholds
only.

---

## 15 · Existing code reused (proposed)

| Source | What is reused |
|---|---|
| `arbicore/learning/calibration.py::ConfidenceCalibrator` (ABC) | Full contract |
| `services/db.py::calibration_log` | Sample persistence + indexes + TTL |
| `services/observation.py::_maybe_predict` + `_resolve_due` | Sample write path (no change) |
| `arbicore/learning/concrete/evaluator_worker.py::OutcomeEvaluator` | Worker template (start/stop/status) |
| `arbicore/learning/concrete/audit_log.py` | Fit-tick audit records |
| `services/alerts_log.py` (via existing AlertService) | Drift alerts |
| Wave-1 endpoint contract (frozen) | Public read shape |
| Wave-1 UI panel (Intelligence → Calibration) | Rendering |

---

## 16 · Existing code refined (proposed)

| File | Refinement | Justification |
|---|---|---|
| `arbicore/learning/concrete/confidence_engine.py` | One-line integration: call `calibrator.calibrate(raw, ctx)` at emission | Wires the ABC into the hot path |
| `arbicore/routes/arbicore.py` (or `server.py` preview) | Read active row from `db.calibration_models` instead of Wave-1 stub | Endpoint promotion from PREVIEW → PROD |
| `arbicore/runtime/composition.py` | Add `CalibrationWorker` composition (1 line) | Standard worker registration |
| Decision-log payload (Wave-1 refinement) | Add `calibrator_version` field | Full audit traceability |

---

## 17 · Net-new code (expected minimal)

| File | Purpose | Est. LOC |
|---|---|---|
| `arbicore/learning/concrete/calibrator_isotonic.py` | Concrete `ConfidenceCalibrator` (isotonic + platt + identity) | ~ 150 |
| `arbicore/learning/concrete/calibration_worker.py` | Sibling worker to `OutcomeEvaluator` | ~ 120 |
| `arbicore/data/mongo/calibration_models_repo.py` | Small repo over `db.calibration_models` | ~ 60 |
| Contract tests (`test_v2_wave3.py`) + unit tests | ~ 15 tests | ~ 250 |
| **Total** | | **≈ 580 LOC** |

No new engines. No new subsystems. No new collections beyond the tiny
`calibration_models` sibling (which is a persistence row, not a
subsystem).

---

## 18 · Wave 3 success criteria (as agreed)

At completion of Wave 3, the deliverable will include:

- [ ] Before-vs-after architecture diagram (§10 is the plan; live
      version to follow).
- [ ] Calibration algorithm documentation (§1).
- [ ] Data flow diagram (§10).
- [ ] Persistence design (§2).
- [ ] Scheduler integration (§11).
- [ ] Performance impact (§12).
- [ ] Test coverage (§13, ≥ 15 new tests).
- [ ] Calibration quality metrics on real data (§14 targets).
- [ ] Existing code reused (§15).
- [ ] Existing code refined (§16).
- [ ] Net-new code introduced (§17, ~ 580 LOC total).

---

## 19 · Open decisions (require user approval)

Before implementation begins, please confirm the following:

1. **Algorithm — Isotonic + Platt + Identity ladder** (§1)? Alternative
   would be beta-calibration; less well-known in ops audits.
2. **30-day rolling window** (§3)? Alternatives: 14 days (faster
   drift response, noisier) or 60 days (steadier, slower to drift).
3. **1-hour cadence** (§4)? Alternative: 15 min (faster) or 6 hours
   (steadier).
4. **Fitted-model collection: `db.calibration_models`** (§2.2)?
   Alternative: store as an in-memory-only artefact with startup
   fallback to Wave-1 stub — rejected as design, but flagging in case
   operator prefers no new collection.
5. **Manual refresh endpoint** (§4.3)? Nice-to-have; can be deferred.
6. **`calibrator_version` field on decision log** (§16)? Extends the
   Wave-1 versioning refinement.
7. **Drift alerts routed via `alerts_log`** (§6.3)? Yes/no.

---

## 20 · What Wave 3 will NOT do

Explicit non-goals to remain aligned with the engineering rule set:

- Will **not** introduce a new subsystem.
- Will **not** replace or refactor `ConfidenceEngine`.
- Will **not** modify any UI (Wave-1 panel already renders the shape).
- Will **not** perform preview → production integration of any other
  endpoint.
- Will **not** touch scanners, execution, treasury, settings.
- Will **not** wire in an external LLM. Anywhere.
- Will **not** build SPATIAL / STATISTICAL scanners (deferred).
- Will **not** ship Evidence Bundle signing (deferred to later
  hardening pass, per user direction).

---

## 21 · Ready-to-implement checklist

- [x] Canonical source verified in-pod against
      `arbicore-x-v1.0.2.bundle`.
- [x] ABC contract confirmed (`ConfidenceCalibrator`).
- [x] Sample-write path confirmed (`_maybe_predict`).
- [x] Sample-resolve path confirmed (`_resolve_due`).
- [x] Persistence collection confirmed (`db.calibration_log`).
- [x] Scheduler template confirmed (`OutcomeEvaluator`).
- [x] Endpoint contract frozen (Wave 1).
- [x] UI panel live (Wave 1).
- [x] Algorithm choice justified (isotonic primary, platt fallback,
      identity safety net).
- [x] Persistence design fits existing patterns.
- [x] Recovery paths deterministic.
- [x] Test plan sized (≥ 15 tests).
- [ ] User approval on the 7 open decisions in §19.

Awaiting approval before writing a single line of code.
