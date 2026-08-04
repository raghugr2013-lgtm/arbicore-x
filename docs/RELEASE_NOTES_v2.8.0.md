# ArbiCore X v2.8.0 — Post-Validation Review & Calibration Framework

**Release date:** 2026-08-04
**Milestone:** Post-Validation review tooling
**Mode:** OBSERVE / PAPER · Kill switch ENGAGED (unchanged)

---

## What ships

One new package (`arbicore.postvalidation`) with **zero runtime side
effects**. It analyses the MID data already accumulated during a
validation run and produces four artefacts.

### 4 new read-only endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/arbicore/postvalidation/report` | Full calibration report (17 categories) |
| `GET /api/arbicore/postvalidation/recommendations` | Advisory-only tuning suggestions |
| `GET /api/arbicore/postvalidation/readiness_score` | 7 subsystem scores + overall grade & verdict |
| `GET /api/arbicore/postvalidation/executive_summary` | Narrative + go/no-go verdict |

All 4 accept `?sample_limit=N` (default 2000).

### Calibration report contents

- Provider reliability + latency + ranking (with per-provider error rate)
- Exchange ranking (CEX venue appearances, avg gross / net USD, profitable rate)
- Scanner ranking (iterations, quotes, emissions, hit rate)
- Opportunity frequency (by type, by chain)
- Opportunity recurrence (top 20 routes)
- Opportunity lifetime (min/median/p90/max from `mid_opportunity_lifetime`)
- Confidence calibration (10 buckets: count / GO / BLOCK per bucket)
- Expected vs observed profitability (net USD stats, profitable %)
- Paper engine stats
- Validation anomalies (from the daily writer)
- Regime distribution
- System health (approx uptime, error counts, kill-switch state)

### Recommendations (advisory only)

Categories the framework surfaces automatically:

| Category | Trigger |
|---|---|
| `provider_disable` | error rate ≥ 50% on ≥ 30 calls, or breaker TRIPPED |
| `provider_priority_boost` | error < 5% AND latency < 200ms on ≥ 30 calls |
| `exchange_reconsider` | avg net profit < 0 on ≥ 20 appearances |
| `scanner_threshold` | 100+ iterations with 0 emissions, or hit rate > 50% |
| `confidence_threshold` | lowest bucket where GO ≥ 50% |
| `fee_tuning` | < 5% of live opps net-profitable |
| `polling_cadence` | very low sample volume |
| `retry_hardening` | ≥ 3 providers with > 10% error rate |
| `timeout_hardening` | avg ewma latency > 40% of configured timeout |

Every recommendation carries `{category, target, reason, severity, advisory}`. Nothing is auto-applied.

### Readiness score

7 subsystems + overall, each with `score ∈ [0,1]`, letter grade (A–F),
and one-line explanation:

| Subsystem | Weight | What it measures |
|---|---:|---|
| Market Intelligence | 20% | opportunity volume + type diversity |
| Provider Layer | 20% | HEALTHY % + latency |
| Scanner Layer | 15% | running % + avg hit rate |
| Paper Engine | 10% | traffic volume (analyses + blocks) |
| Validation Framework | 15% | daily writer bound + critical anomalies |
| Operations | 10% | approx uptime + zero criticals |
| Safety | 10% | kill switch engaged (binary; 0 = hard fail) |

Verdict thresholds: A ≥ 0.90, B ≥ 0.75, C ≥ 0.60, D ≥ 0.40, F otherwise.
If Safety is 0 the verdict is REJECT regardless of the arithmetic overall.

### Executive summary

Composes: overall_score · grade · verdict · recommendation counts ·
`worked_well[]` · `needs_improvement[]` · `should_tune[]` ·
`another_validation_run_recommended: bool` · `ready_for_next_phase: bool` ·
`next_phase_gate: str`.

## Live evidence (this build, after ~10 minutes of live scanning)

```
GET /api/arbicore/postvalidation/executive_summary
  overall_score: 0.79 (B)
  verdict: READY WITH MINOR TUNING
  worked_well:
    + 47/47 providers HEALTHY
    + Kill switch remained ENGAGED for the entire window
    + All 3 live scanners stayed running
    + Paper Engine correctly blocked every candidate while the kill
      switch was engaged (safety invariant held)
  should_tune (5 medium):
    ~ exchange_reconsider: coinbase (avg net -$77 on 490 appearances)
    ~ exchange_reconsider: okx      (avg net -$74 on 312)
    ~ exchange_reconsider: kucoin   (avg net -$74 on 103)
    ~ exchange_reconsider: kraken   (avg net -$90 on 75)
    ~ fee_tuning: 0.0% of live opps net-profitable → tune ECON_VENUE_FEE_BPS
```

This is exactly the calibration signal the framework is meant to
produce — the default fee ladders eliminate every 10–15 bps live
spread, so the operator now has an evidence-based prompt to verify
per-account fee assumptions before considering execution.

## Safety posture (unchanged)

Every runtime invariant held. Kill switch engaged. Live execution
disabled. No signing. No broadcasts. No wallet interaction.

## Files changed

New:
- `arbicore/postvalidation/{__init__.py, review.py}` — 550 LOC

Modified:
- `backend/server.py` — 4 new endpoints. No existing behaviour changed.

## Deliverables

- `arbicore-x-v2.8.0.bundle`
- `arbicore-x-v2.8.0.tar.gz`
- `arbicore-x-v2.8.0.SHASUMS`
- `RELEASE_NOTES_v2.8.0.md`
- Git tag `v2.8.0`

## How to use after the 7-day VPS run

1. `curl -s $BASE/api/arbicore/postvalidation/report > report.json`
2. `curl -s $BASE/api/arbicore/postvalidation/recommendations > recs.json`
3. `curl -s $BASE/api/arbicore/postvalidation/readiness_score > score.json`
4. `curl -s $BASE/api/arbicore/postvalidation/executive_summary > exec.json`

These four files plus the 7 archived `daily_summary` payloads
constitute the complete evidence pack for deciding whether to plan
Stage 6.
