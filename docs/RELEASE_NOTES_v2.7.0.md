# ArbiCore X v2.7.0 — Production Validation & Operational Readiness

**Release date:** 2026-08-04
**Milestone:** Phase 5 → 9 (Production Readiness · Configuration Layer · Deployment Validation · 7-Day Validation Framework · Operational Hardening)
**Mode:** OBSERVE / PAPER · Kill switch ENGAGED · Live execution DISABLED (unchanged)

---

## Objective

No new market features. Turn v2.6.0 into a **production-quality
operational validation platform** ready for the first continuous
7-day paper-validation run on the VPS.

## What ships

### Phase 5 — Production readiness

A live preflight endpoint (`GET /api/arbicore/preflight`) runs 10
category-tagged checks in a single request. Verified live: all 10 pass.

### Phase 6 — Configuration layer (`arbicore.config.runtime`)

Single source of truth for every operator-tunable value. Frozen at
startup; exposed via `GET /api/arbicore/config/runtime`. Zero
hardcoded values reach the runtime.

| Group | Env vars |
|---|---|
| RPC failover | `PROVIDER_RPC_URLS_<CHAIN>` (CSV) + fallback `PROVIDER_RPC_URL_<CHAIN>` for 7 chains |
| Scanner cadence | `LIVE_TICK_INTERVAL_SECONDS`, `LIVE_MIN_SPREAD_BPS`, `LIVE_QUOTE_NOTIONAL_USD`, `CROSS_TICK_INTERVAL_SECONDS`, `CROSS_MIN_NET_BPS`, `CROSS_NOTIONAL_USD`, `LIVE_MARKET_AUTOSTART`, `CROSS_AUTOSTART` |
| Economics | `ECON_VENUE_FEE_BPS` (JSON map), `ECON_WITHDRAWAL_FEE_USD` (JSON), `ECON_NATIVE_PRICE_USD` (JSON), `ECON_DEFAULT_SLIPPAGE_BPS`, `ECON_DEFAULT_LIQUIDITY_IMPACT_BPS`, `ECON_DEFAULT_GAS_GWEI` (JSON), `ECON_DEFAULT_GAS_UNITS` |
| Validation | `VALIDATION_WINDOW_HOURS`, `VALIDATION_DAILY_HOUR_UTC`, `VALIDATION_ANOMALY_MIN_SCANNER_OPS`, `VALIDATION_ANOMALY_MAX_ERR_RATE`, `VALIDATION_ANOMALY_MIN_HEALTHY_PCT`, `VALIDATION_RUN_ID_PREFIX`, `VALIDATION_AUTOSTART_DAILY_WRITER` |
| Hardening | `HARDEN_HTTP_TIMEOUT_S`, `HARDEN_HTTP_RETRIES`, `HARDEN_HTTP_BACKOFF_MS`, `HARDEN_BREAKER_FAILURE_THRESHOLD`, `HARDEN_BREAKER_OPEN_S`, `HARDEN_ENSURE_MONGO_INDEXES` |

### Phase 7 — Deployment validation

- `PreflightRunner` — 10 checks (`mongo_ping`, `mid_reader_query`,
  `provider_registry_bound`, `rpc_endpoints_configured`,
  `provider_health_pct`, `paper_engine_bound`, `kill_switch_engaged`,
  and one `scanner_<id>` per live scanner). Categorised as
  `database / providers / paper / safety / scanners`.
- The endpoint returns `ok: true/false`, per-category pass/fail counts,
  and each check's latency. Machine-parseable — the CI or an operator
  script can gate on `ok`.

### Phase 8 — Seven-Day validation framework

- `DailySummaryWriter` — background asyncio loop. On startup:
  1. Composes a full validation summary via `ValidationReporter`.
  2. Runs anomaly detection (4 rules: zero-emission scanners,
     provider-health floor, per-provider error rate, no-live-opps-in-window).
  3. Writes a `validation.daily_summary` event into MID via the
     existing `MidWriter.write_opportunity_event`.
  4. Repeats every `VALIDATION_WINDOW_HOURS` (default 24h).
- Endpoints:
  - `GET  /api/arbicore/validation/daily_status` — live status + last anomalies
  - `GET  /api/arbicore/validation/last_daily` — full last-summary payload
  - `POST /api/arbicore/validation/daily_run_now` (admin/operator) — trigger a summary immediately

### Phase 9 — Operational hardening

- Kept the v1.x MID index bootstrap (`ensure_indexes`) as-is — it is
  correct and comprehensive.
- Frozen HTTP timeouts & retry budgets in `HardeningConfig`
  (default 8 s, 2 retries, 200 ms backoff, breaker: 5 failures / 60 s open).
- Breaker thresholds exposed as env for VPS tuning.

## Live evidence (this build)

```
GET /api/arbicore/preflight
  → ok=True, 10/10 passed
      [PASS] mongo_ping                      ok
      [PASS] mid_reader_query                opportunities_last1=1
      [PASS] provider_registry_bound         providers=47 kinds=7
      [PASS] rpc_endpoints_configured        rpc_providers_registered=7
      [PASS] provider_health_pct             healthy=47/47 (100.0%)
      [PASS] paper_engine_bound              analyses=0
      [PASS] kill_switch_engaged             engaged=True
      [PASS] scanner_live_market             iterations=1
      [PASS] scanner_live_cex_dex            iterations=1
      [PASS] scanner_live_dex_dex            iterations=1

GET /api/arbicore/validation/daily_status
  → run_id=run_20260804_1104, running=true, last_anomalies=[]
```

## Safety posture (unchanged)

Every v2.5/2.6 guarantee holds. In particular the `PreflightRunner`
**fails** if `kill_switch.is_engaged()` returns False — v2.7.0
literally will not report `ok=true` unless the kill switch is engaged.

## New endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/arbicore/config/runtime` | Frozen runtime config snapshot |
| `GET /api/arbicore/preflight` | 10-check deployment readiness gate |
| `GET /api/arbicore/validation/daily_status` | Daily-writer state + last anomalies |
| `POST /api/arbicore/validation/daily_run_now` | Force a daily summary now |
| `GET /api/arbicore/validation/last_daily` | Last full daily summary payload |

## Files changed

New:
- `arbicore/config/runtime.py`
- `arbicore/validation/operations.py`

Modified:
- `backend/server.py` — 5 new endpoints, one background writer, one
  startup dependency chain.

Unchanged (no redesign):
- Every v2.5/2.6 provider, scanner, MID writer/reader, safety module.

## Files that operators will read

Ships alongside the bundle:
- `docs/PRODUCTION_READINESS_REPORT.md` — full evidence-backed audit.
- `docs/DEPLOYMENT_CHECKLIST.md` — pre-deploy / deploy / post-deploy steps.
- `docs/SEVEN_DAY_VALIDATION_GUIDE.md` — how to run the 7-day validation.
- `docs/OPERATIONS_MANUAL.md` — day-to-day operator handbook.

## Deliverables

- `arbicore-x-v2.7.0.bundle`
- `arbicore-x-v2.7.0.tar.gz`
- `arbicore-x-v2.7.0.SHASUMS`
- `RELEASE_NOTES_v2.7.0.md`
- Git tag `v2.7.0`
