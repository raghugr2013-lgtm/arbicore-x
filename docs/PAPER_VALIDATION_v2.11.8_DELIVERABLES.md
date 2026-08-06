# Paper Validation Framework — v2.11.8 Deliverables Summary

## Status: ✅ COMPLETE (Slices A + B + C, 2026-08-06)

Full canonical Paper Validation pipeline. Every opportunity that
transits the OpportunityPipeline now produces an **immutable
EvidenceBundle** with a canonical 8-value terminal outcome, joined
to the opportunity + journal via a unique `validation_id`.

## Regression evidence

| Iter | Slice | Tests    | Backend Issues | Verdict |
| ---- | ----- | -------- | -------------- | ------- |
| 13   | A     | 100%     | 0 / 0          | FULL GO |
| 14   | B     | 100%     | 0 / 0          | FULL GO |
| 15   | C     | 100%     | 0 / 0          | FULL GO |
| Foundry | executor package | 8/8 | — | Green |

## Architecture summary

```
CanonicalOpportunity  ──▶  ContinuousDiscovery / LiveMarketScanner
                                     │
                                     ▼
                       PaperValidationRunner (Slice C)
                                     │
                     validation_id ──┤
                                     ▼
                       OpportunityPipeline
                                     │
                    ┌──────┬─────────┴──────┬────────┬────────┬────────┬────────┬─────────┐
                    ▼      ▼                ▼        ▼        ▼        ▼        ▼         ▼
                observe  quote          liquidity  gas    profit   policy   cert    simulate (Slice B)
                            │                │                                        │
                            └──── StageMetric(started_at, ended_at, duration_ms) ─────┘
                                                     │
                                                     ▼
                                    classify_outcome() — exactly ONCE
                                                     │
                                                     ▼
                                        EvidenceBundle (immutable)
                                                     │
                                                     ▼
                              arbicore_paper_evidence (insert-only)
                                                     │
                          ┌──────────────────────────┼─────────────────────────────┐
                          ▼                          ▼                             ▼
        GET /validation/report      GET /validation/evidence   GET /validation/evidence/{id}
                                    GET /validation/metrics    /dashboard/pulse.paper_validation
```

## Canonical outcome vocabulary (closed set)

`EXECUTABLE`, `REJECTED`, `UNPROFITABLE`, `LIQUIDITY_FAILURE`,
`GAS_FAILURE`, `ROUTE_FAILURE`, `RISK_FAILURE`, `SIMULATION_FAILURE`.

Classification rules — data-driven (`_STAGE_FAILURE_TO_OUTCOME` in
`arbicore/paper/classifier.py`):

| Failed stage      | Outcome              |
| ----------------- | -------------------- |
| `quote` / `route` | `ROUTE_FAILURE`      |
| `gas`             | `GAS_FAILURE`        |
| `profit`          | `UNPROFITABLE`       |
| `policy`          | `RISK_FAILURE`       |
| `certification`   | `RISK_FAILURE`       |
| `liquidity`       | `LIQUIDITY_FAILURE`  |
| `simulate`/`broadcast` | `SIMULATION_FAILURE` |
| — (no failure)    | `EXECUTABLE` (shadow/broadcast) or `REJECTED` (observe) |

First-failure-wins ordering.

## New endpoints (Slice C · all auth-gated)

| Endpoint | Purpose |
| -------- | ------- |
| `GET /api/arbicore/validation/report`             | Aggregated report: `total`, `histogram`(8), `rates`(8), `executable_rate`. |
| `GET /api/arbicore/validation/evidence`           | Recent bundles list. Query: `outcome`, `strategy`, `limit`. |
| `GET /api/arbicore/validation/evidence/{id}`      | Full bundle with per-stage trace. |
| `GET /api/arbicore/validation/metrics`            | Runner health + throughput. `runner_enabled` reflects `ARBICORE_PAPER_VALIDATION_ENABLED`. |
| `GET /api/arbicore/dashboard/pulse.paper_validation` | Pulse snapshot: total, executable_rate, runner_running, outcome_counts. |

## Runner controls

- Env flag: `ARBICORE_PAPER_VALIDATION_ENABLED=true`
- Default: **OFF** (preview / test environments stay clean).
- Idempotent: re-processed opps are skipped via in-memory set +
  Mongo lookup by `opportunity_id`.
- Fail-open: per-opp exceptions are logged and counted; the loop
  continues.
- Bounded: `batch_limit=25` opps per cycle keeps `stop()` responsive.

## Coverage report

| Layer                        | Tests | Location                                                          |
| ---------------------------- | ----- | ----------------------------------------------------------------- |
| Slice A (vocab + evidence)   | 26    | `tests/test_v2118_paper_validation_slice_a.py`                    |
| Slice B (liquidity + sim)    | 21    | `tests/test_v2118_paper_validation_slice_b.py`                    |
| Slice C (runner + API)       | 12    | `tests/test_v2118_paper_validation_slice_c.py`                    |
| Iter15 live e2e              | 8     | `/app/backend/tests/test_iter15_slice_c_live.py` (added by iter15 agent) |
| Foundry executor package     | 8/8   | `/app/contracts/tests/FlashLoanReceiver.t.sol`                    |

## Sample EvidenceBundle

See `/app/contracts/docs/evidence/sample_evidence_bundle.json` — an
EXECUTABLE bundle with all 7 stages (quote, liquidity, gas, profit,
policy, certification, simulate) and full per-stage timing.

Compact excerpt:

```json
{
  "validation_id": "db841369-d954-4936-92d9-737710e176eb",
  "opportunity_id": "sample-bundle-1",
  "strategy": "flash_loan_arbitrage",
  "mode": "SHADOW",
  "outcome": "EXECUTABLE",
  "outcome_reason": "mode not promoted for automatic broadcast",
  "simulation_backend": "heuristic",
  "stages": [
    {"stage":"quote","ok":true,"duration_ms":0.009,"started_at":"…","ended_at":"…"},
    {"stage":"liquidity","ok":true,"duration_ms":0.036,"detail":"all 1 hop(s) exceed borrow*5"},
    {"stage":"gas","ok":true,"duration_ms":0.009,"detail":"derived nominal gas estimate"},
    {"stage":"profit","ok":true,"duration_ms":?, "detail":"net=42.50 gas=30.00 after_gas=12.50"},
    …
  ]
}
```

## Validation metrics summary (as of 2026-08-06 pre-deploy)

Preview environment — Runner disabled by default; live opp flow not
yet enabled.  Baseline numbers will populate on the first VPS host
that flips `ARBICORE_PAPER_VALIDATION_ENABLED=true` and lets the
scanners emit into `arbicore_opportunities`.

## Readiness assessment for Shadow Certification

- ✅ **Outcome vocabulary frozen** (8 values, closed set).
- ✅ **Immutable evidence** (frozen dataclass + insert-only Mongo repo).
- ✅ **Validation ID linkage** (opp ↔ evidence ↔ journal joinable).
- ✅ **Per-stage metrics** (started_at, ended_at, duration_ms,
  failure_reason on every stage of every bundle).
- ✅ **Terminal classification once** (single `classify_outcome` call
  at pipeline completion; stage results feed the classifier but don't
  set the terminal value).
- ✅ **Simulation provider interface** (Protocol; two backends today,
  Anvil / Tenderly / forge-fork plug in without pipeline changes).
- ✅ **API + dashboard** wired for operator visibility.
- ✅ **Backward compatibility** — every existing test still green.
- ✅ **No fabricated data** — every empty state is a graceful empty,
  every stage result comes from real inputs.

**Green light for Shadow Certification design.**  The Framework is
ready to be extended into the 20-cycle certification loop:
* Add a `ShadowCertificationRun` collection linked by `validation_id`
  batches.
* Define pass/fail thresholds against the executable-rate,
  outcome-histogram, and per-stage timing stability.
* Gate LIMITED_LIVE promotion on N consecutive passes.

**Do NOT enable LIMITED_LIVE** until Shadow Certification exists,
passes 20 cycles, and an operator explicitly promotes the mode.
