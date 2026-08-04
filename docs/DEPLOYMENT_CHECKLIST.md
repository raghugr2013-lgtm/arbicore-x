# ArbiCore X — Deployment Checklist (v2.7.0)

## Pre-deploy

- [ ] Confirm VPS has: Python 3.11+, Node 18+, MongoDB 6+, supervisor.
- [ ] Pull `v2.7.0` (git tag) or extract `arbicore-x-v2.7.0.tar.gz`.
- [ ] Verify checksums against `arbicore-x-v2.7.0.SHASUMS`.
- [ ] Set every **REQUIRED** env var in `.env.shared`:

  ```
  MONGO_URL=mongodb://...
  DB_NAME=arbicore
  CORS_ORIGINS=https://your.domain

  ARBICORE_JWT_SECRET=<32+ random>
  ARBICORE_ADMIN_PASS=<long random>
  ARBICORE_OPERATOR_PASSWORD=<long random>
  ```

- [ ] Set at minimum one **paid RPC** for cross-scanner emission:

  ```
  PROVIDER_RPC_URL_ETHEREUM=https://eth-mainnet.g.alchemy.com/v2/<KEY>
  # Optional multi-endpoint failover:
  PROVIDER_RPC_URLS_ETHEREUM=https://.../<K1>,https://.../<K2>
  ```

- [ ] Optional CEX gating (if your VPS egress is geo-blocked from
  Binance/Bybit):

  ```
  PROVIDER_CEX_ENABLED=okx,coinbase,kraken,kucoin
  ```

- [ ] Confirm safety defaults remain **explicit** (belt + braces):

  ```
  ARBICORE_SAFETY_KILL_DEFAULT=true
  ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED=false
  ```

## Deploy

- [ ] `pip install -r backend/requirements.txt`
- [ ] `yarn --cwd frontend install --frozen-lockfile`
- [ ] `yarn --cwd frontend build`
- [ ] `sudo supervisorctl restart backend`
- [ ] `sudo supervisorctl restart frontend`
- [ ] Wait 15 seconds for the live scanner autostart.

## Post-deploy — gate on preflight

- [ ] `curl -s $BASE_URL/api/arbicore/preflight | jq .ok` → must return
  `true`.
- [ ] Every category should report zero failures. Inspect the JSON
  if `ok=false` and re-run once dependencies are fixed.

## Post-deploy — smoke tests

- [ ] `curl -s $BASE_URL/api/arbicore/providers/status | jq .provider_count`
  → expect **≥ 30** (Binance/Bybit may be blocked; that's OK).
- [ ] `curl -s $BASE_URL/api/arbicore/live/status | jq '.stats.iterations'`
  → should be **> 0** within 30 s.
- [ ] `curl -s $BASE_URL/api/arbicore/live/prices | jq '.prices | keys'`
  → should list `BTC/USDT` and `ETH/USDT`.
- [ ] `curl -s $BASE_URL/api/arbicore/scanners/cross/status | jq`
  → both `cex_dex` and `dex_dex` must show `running=true`.
- [ ] `curl -s $BASE_URL/api/arbicore/safety/status | jq '.kill.engaged'`
  → **must be `true`**.
- [ ] `curl -s $BASE_URL/api/arbicore/validation/daily_status | jq`
  → should show a `run_id`, `running=true`, `last_summary_at != null`.

## Post-deploy — UI

- [ ] Open `$BASE_URL/login`, log in with admin credentials.
- [ ] Land on `/dashboard` — Ops Center should render within 6 seconds.
- [ ] Verify:
  - KPI row shows 30+ providers and > 0 iterations.
  - Live prices show at least 3 CEX venues per symbol.
  - Safety chip shows `ENGAGED`, `PAPER-ONLY`.

## Rollback

If preflight fails or the Ops Center is empty after 60 seconds:

1. `sudo supervisorctl restart backend`
2. Tail `/var/log/supervisor/backend.err.log` for the first exception.
3. If unrecoverable, `git checkout v2.6.0 && sudo supervisorctl restart backend`.

v2.7.0 is fully backward-compatible with v2.5/v2.6 data in MID.
