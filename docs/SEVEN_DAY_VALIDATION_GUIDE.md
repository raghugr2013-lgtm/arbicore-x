# Seven-Day Validation Guide — ArbiCore X v2.7.0

## Purpose

Run ArbiCore X in **OBSERVE + PAPER** mode continuously for 7 days on
the VPS. Collect enough data to (a) validate the net-profit engine
against real market conditions, (b) rank venues and providers, (c)
calibrate confidence, (d) produce anomaly-free stability data.

Nothing during the 7-day run signs, broadcasts, or moves capital. The
kill switch stays engaged. `ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED`
stays `false`.

---

## Day 0 — deploy

Follow `DEPLOYMENT_CHECKLIST.md`. When the post-deploy checklist
passes, note down:

- `run_id` reported by `GET /api/arbicore/validation/daily_status`.
- Preflight `elapsed_ms` and pass count.
- Provider count.

Archive that JSON as `day0_manifest.json`.

## Days 1-7 — daily discipline

The `DailySummaryWriter` writes a validation summary to MID every
`VALIDATION_WINDOW_HOURS` (default 24 h). Nothing manual is required.
But do the following daily 5-minute check:

1. `curl -s $BASE_URL/api/arbicore/validation/daily_status | jq '.last_summary_at, .last_anomalies'`
   → confirm `last_summary_at` is within the last 25 hours.
   → note any `last_anomalies` entries with severity `critical`.
2. `curl -s $BASE_URL/api/arbicore/validation/last_daily > day_${N}.json`
   → archive.
3. `curl -s $BASE_URL/api/arbicore/preflight | jq '.ok, .failed'`
   → must remain `ok=true, failed=0`.

Each daily payload contains:
- **Recurrence** — top 20 routes and how often each was observed.
- **Calibration** — confidence-bucketed decision distribution.
- **Venue ranking** — buy / sell counts and avg net profit per venue.
- **Scanner ranking** — iterations, opportunities emitted, hit-rate.
- **Provider ranking** — score, health, latency.
- **Regime** — regime slot distribution.
- **Execution probability** — profitable vs unprofitable histogram
  with median confidence.
- **Historical** — shadow vs live, by opportunity type.
- **Anomalies** — the 4-rule anomaly-detection output.

## Anomaly response

| Anomaly `kind` | Severity | Action |
|---|---|---|
| `scanner_zero_emissions` | warning | Investigate the scanner's `last_error`. Usually a provider issue — check `providers/status` for tripped breakers. |
| `provider_health_below_floor` | critical if <50% | Add a failover RPC (`PROVIDER_RPC_URLS_<CHAIN>=url1,url2`) and restart. |
| `provider_error_rate_high` | warning | Inspect the provider row; if it's Binance/Bybit and you're datacentre-egressed, disable them via `PROVIDER_CEX_ENABLED`. |
| `no_live_opportunities_in_window` | warning | Confirm `live/prices` is populating. If yes, the net-profit engine is filtering everything — this may be the correct outcome. |

## Final validation report

At the end of Day 7, run:

```bash
curl -s $BASE_URL/api/arbicore/validation/summary > final_summary.json
curl -s $BASE_URL/api/arbicore/memory/summary   > final_memory.json
curl -s $BASE_URL/api/arbicore/providers/status > final_providers.json
```

Combined with the 7 daily archives, this is the **complete dataset**
for the post-run review.

## Success criteria

- ✅ Preflight `ok=true` for at least 6/7 days.
- ✅ At least one live scanner emits ≥ 500 opportunities across the 7 days.
- ✅ At least 3 venues rank in the venue-ranking table.
- ✅ Anomaly count = 0 critical, ≤ 3 warnings.
- ✅ Kill switch remained engaged and paper engine remained gated
  the entire run.
- ✅ No process restarts triggered by internal exceptions.

If all criteria are met the platform is validated for the next stage.
If any criterion fails the daily payload tells you exactly which
subsystem to inspect.

## Do not

- ❌ Do not disengage the kill switch during the run.
- ❌ Do not change `PROVIDER_*` env values mid-run — start a new
  `run_id` if you must reconfigure.
- ❌ Do not manually tamper with the MID `validation.daily_summary`
  events.
