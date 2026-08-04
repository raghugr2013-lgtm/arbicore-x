# ArbiCore X — Operations Manual (v2.7.0)

## Daily commands

```bash
# health
curl -s $BASE/api/arbicore/preflight | jq

# quick state
curl -s $BASE/api/arbicore/observability | jq

# current live data
curl -s $BASE/api/arbicore/live/status  | jq
curl -s $BASE/api/arbicore/live/prices  | jq
curl -s $BASE/api/arbicore/scanners/cross/status | jq

# daily summary
curl -s $BASE/api/arbicore/validation/daily_status | jq
```

## Common operations

**Start / stop a live scanner** (admin/operator token):

```bash
curl -sX POST $BASE/api/arbicore/live/stop  -H "Authorization: Bearer $T"
curl -sX POST $BASE/api/arbicore/live/start -H "Authorization: Bearer $T"
```

**Trigger a daily summary immediately:**

```bash
curl -sX POST $BASE/api/arbicore/validation/daily_run_now \
     -H "Authorization: Bearer $T" | jq
```

**Engage / disengage the kill switch:**

```bash
curl -sX POST $BASE/api/arbicore/safety/kill/engage    -H "Authorization: Bearer $T"
curl -sX POST $BASE/api/arbicore/safety/kill/disengage -H "Authorization: Bearer $T"    # admin ONLY
```

## Symptom → likely cause

| Symptom | First check |
|---|---|
| `preflight.ok=false, scanner_* FAIL` | `curl live/status`, look at `stats.last_error` |
| `preflight.ok=false, rpc_endpoints FAIL` | You have zero RPC providers — set `PROVIDER_RPC_URL_ETHEREUM` |
| `preflight.ok=false, kill_switch FAIL` | Kill switch got disengaged. **Do not proceed with the run** until it's re-engaged. |
| `live/status.stats.opportunities_emitted=0` after 5 min | Real spreads are below `LIVE_MIN_SPREAD_BPS` (default 5). This is normal in calm markets. |
| Cross scanners keep reporting `dex_quote: HTTP 521` | Free RPC returning 5xx. Switch to Alchemy/Infura. |
| Ops Center KPI counters stuck at zero | Frontend `REACT_APP_BACKEND_URL` mis-set, or backend not restarted after a rebuild. |
| `validation/daily_status.running=false` | `sudo supervisorctl restart backend`, then `POST validation/daily_run_now`. |

## Log locations

- Backend: `/var/log/supervisor/backend.err.log`
- Frontend: `/var/log/supervisor/frontend.err.log`
- Live scanner traces: grep `live_market`, `live_cex_dex`, `live_dex_dex` in the backend log.
- MID writes: grep `mid.` in the backend log.

## When to page

Any of the following:

1. Preflight `ok=false` and `retry` still fails after 60 s.
2. Provider health drops below 50%.
3. Kill switch reports `engaged=false` outside a scheduled admin operation.
4. Live-execution flag flips to `true` unexpectedly.
5. Daily summary writer stops (`running=false`) unexpectedly.

Everything else is a warning — the daily summary will surface it.

## What you should *never* do during v2.7.0 validation

- Never `POST /safety/kill/disengage` "just to see what happens" —
  the paper engine's `policy_blocked` guarantee is the observable
  invariant of the run.
- Never modify `ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED`. It must be
  `false` for the entire run.
- Never disable the `NoOpWalletProvider` — it is the last line of
  defence that guarantees signing is impossible.
