# Reproduction — P1 Read-Only Performance Baseline

Read-only analysis steps used to produce this baseline. Commands inspect the running system and MongoDB; they do **not** mutate config, enable scanners, probe RPCs for benchmarks, or trade.

**Host workspace:** `/home/raghu/projects/arbicore-x-cert`  
**Target container:** `arbicore-x-backend-new`  
**Report dir:** `artifacts/performance/p1_readonly_baseline/`

---

## 1. Runtime identity

```bash
docker ps --filter name=arbicore-x-backend-new --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
docker inspect arbicore-x-backend-new --format 'Image={{.Image}} Started={{.State.StartedAt}} Restarts={{.RestartCount}} Health={{.State.Health.Status}}'
docker image inspect arbicore-x-backend:hybrid-e-rpc-9244ebd --format '{{.Id}}'
docker exec arbicore-x-backend-new cat /app/BUILD_INFO.json
docker exec arbicore-x-backend-new python3 -c 'import os; keys=["ARBICORE_GIT_SHA","ARBICORE_GIT_TAG","ARBICORE_AUTOEXEC_AUTOSTART","ARBICORE_RUNTIME_AUTOSTART","ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS","ARBICORE_EXECUTION_MODE","ARBICORE_FLASH_LOAN_SHADOW_ROUTE","ARBICORE_SCANNER_AUTOSTART","ARBICORE_SCANNER_DEX_ARB","ARBICORE_SCANNER_CEX_ARB","SIGNING_ACTIVE_KEY_VERSION"];
print({k:os.environ.get(k) for k in keys})'
docker stats arbicore-x-backend-new factory-mongo --no-stream
```

**Verified:** image digest `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52`, commit `fff0d0eced5ce3783cff18fb976e55a2a6504504`, workers=6, AUTOEXEC=false, RUNTIME_AUTOSTART=false.

---

## 2. Status APIs (no auth where public)

```bash
BASE=http://127.0.0.1:8001
curl -sS "$BASE/api/arbicore/scanners/status" | python3 -m json.tool > /tmp/scanners_status.json
curl -sS "$BASE/api/arbicore/providers/status" -o /tmp/providers_status.json
curl -sS "$BASE/api/arbicore/safety/status"
curl -sS "$BASE/api/arbicore/flashloan/journey/status"
curl -sS "$BASE/api/arbicore/auto-executor/status"
curl -sS "$BASE/api/arbicore/config/runtime"   # REDACT any /v2/<key> before saving artifacts
curl -sS "$BASE/api/arbicore/execution/discovery/status"
```

**Do not call:** live-quote, scan-once, discovery tick/start, scanner start/enable, RPC check endpoints that issue new provider calls for benchmarking.

**Primary in-memory metrics path:**  
`canonical_flash_loan_arbitrage.stats` → `verification_pool`, `capacity`, `gate7_profit_distribution`.

---

## 3. Mongo read-only queries

Executed inside the backend container with `pymongo` against `MONGO_URL` / `DB_NAME=arbicore_x` (read-only `find` / `count_documents` / `aggregate`).

**Container start epoch used:** `2026-10-08T08:33:43Z` → `1791448423.0`.

### 3a. Discovery candidates (W1)

```python
# Pseudocode of analysis performed
started_ts = 1791448423.0
col = db.arbicore_discovery_candidates
hint_n = col.count_documents({"hint_observed_at": {"$gte": started_ts}})
verified = list(col.find(
  {"hint_observed_at": {"$gte": started_ts}, "verified_at": {"$ne": None}},
  projection={"hint_observed_at":1,"verified_at":1,"verification_latency_ms":1,
              "verified_outcome":1,"chain":1,"hint_source":1,"claimed_at":1}
))
# observe_to_verify_s = verified_at - hint_observed_at
# verification_latency_ms/1000 equals observe_to_verify wall-clock in this dataset
```

**Results captured:** n_hint=14108, n_verified=672, claimed_at always null on candidate docs, observe→verify percentiles in `performance_metrics.json`.

### 3b. Evidence bundles (W2)

```python
eb = db.evidence_bundles.find({
  "source_component": "flash_loan_arb_verifier",
  "created_at": {"$gte": "2026-10-08T08:33:43"}
}, projection={"diagnostics":1,"created_at":1,"persisted_at":1,"candidate_id":1})
# observe_to_claim = claimed_at - hint_observed_at
# claim_to_stamp = stamped_at - claimed_at
```

**Results:** n=383; observe→claim / claim→stamp percentiles in metrics JSON; missing evidence = 289/672.

### 3c. Decision history (W3)

```python
db.decision_history.count_documents({"recorded_at": {"$gte": "2026-10-08T08:33:43"}})
# hourly counts; sample last 5000 for quote_age / net_profit / would_execute
```

**Results:** ~7488+ since start; ~456/hour recent; 0 positive net / 0 would_execute in samples.

---

## 4. Exact measurement windows

| ID | Start (UTC) | End (UTC) | Notes |
|---|---|---|---|
| W0 | 2026-10-08T08:33:43Z | ~2026-10-09T01:14Z | Container lifetime |
| W1 | 2026-10-08T08:37:56.153Z | 2026-10-08T08:54:26.682Z | First/last `verified_at` |
| W2 | same deploy | evidence created ≥ start | 383 bundles |
| W3 | ≥ start | report time | decision_history continuous |

---

## 5. Assumptions

1. `BUILD_INFO.json` / `ARBICORE_GIT_SHA` supersede stale compose labels / `ARBICORE_VERSION` env.  
2. “6 workers” means flash-loan verification pool workers, not uvicorn `--workers`.  
3. Mongo `verification_latency_ms` is **wall-clock discovery→verify**, not pool processing time (confirmed equal to `verified_at - hint_observed_at`).  
4. Scanner capacity block is process-lifetime in-memory state from early drain; live rates at report time are zero because scanner disabled.  
5. Stale on-disk `reports/decision_analytics_*.json` (Aug 2026) excluded from baseline-of-record.  
6. RPC URLs in `config/runtime` contain secrets — artifacts store **hosts only**.

---

## 6. Exclusions / data-quality issues

- No authenticated analytics endpoints used successfully (login response lacked bearer token in this environment); public `scanners/status` + Mongo sufficed.  
- Capacity `candidate_age_at_verify` n=512 vs Mongo n=672 — do not merge percentiles.  
- Provider EWMA `last_ok_at` clustered at end of W1 — not a continuous RPC health series.  
- `decision_history` writer path not fully attributed to a scanner component.  
- Docker logs (6–17 h) lacked structured stage timers (mostly access/httpx lines).

---

## 7. Safety / non-modification check

After analysis:

```bash
docker inspect arbicore-x-backend-new --format 'RestartCount={{.RestartCount}} Started={{.State.StartedAt}} Image={{.Image}} Health={{.State.Health.Status}}'
# Expect: RestartCount=0, same StartedAt, same Image digest, healthy
```

Temporary analysis scripts were copied to container `/tmp` and removed afterward. No source, env, compose, or image changes. No scanner enable/start. No AUTOEXEC/signing/broadcast changes. No synthetic RPC load tests.

---

## 8. Artifact outputs

| File | Purpose |
|---|---|
| `PERFORMANCE_BASELINE.md` | Narrative baseline |
| `performance_metrics.json` | Machine-readable metrics (nulls for gaps) |
| `bottleneck_register.csv` | Ranked findings |
| `measurement_gaps.md` | Instrumentation blockers |
| `reproduction.md` | This file |
