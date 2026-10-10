# Measurement Gaps — P1 Read-Only Baseline

This baseline is **PARTIAL TELEMETRY**. The items below are the minimum instrumentation (or observation conditions) required for a future **sufficient** baseline. Nothing listed here was implemented in this task.

---

## Blockers for a sufficient baseline

### 1. Live flash-loan observation window
**Gap:** Scanner `enabled=false`; `claims_per_min=0`, `verifies_min=0`, `fresh_eligible_depth=0`.  
**Need:** A bounded SHADOW observation window (existing safety flags unchanged) so capacity rates and rolling histograms refresh.  
**Why:** W1 metrics are a single early ~17-minute post-deploy drain, not current steady state.

### 2. `claimed_at` on candidate documents
**Gap:** All 672 verified Mongo candidates have `claimed_at=null`; claim timing only recoverable from evidence diagnostics (n=383).  
**Need:** Persist `claimed_at` / `claimed_by` on `arbicore_discovery_candidates` at claim time.  
**Why:** Enables queue-wait vs processing split for 100% of verifies without joining evidence.

### 3. Per-stage duration fields (correlated by `candidate_id`)
**Gap:** No timers for route match, RPC quote, fallback, MEV/gate-9, gas, profit gate, or finalise.  
**Minimum fields (ms, int):**
- `stage_route_match_ms`
- `stage_rpc_quote_ms` (sum) + `stage_rpc_quote_attempts`
- `stage_rpc_fallback_ms`
- `stage_gate7_economics_ms`
- `stage_gate8_liquidity_ms`
- `stage_gate9_mev_ms`
- `stage_evidence_persist_ms`
- `stage_total_claim_to_decision_ms`

**Attach to:** evidence `diagnostics` and/or candidate doc.  
**Why:** Required to prove or refute “RPC dominates e2e” without adding percentiles from unrelated samples.

### 4. Verification pool percentile export
**Gap:** Pool exposes min/mean/median/max only (`verify_duration_*`).  
**Need:** p95 and p99 (and sample window start/end) on `/api/arbicore/scanners/status` capacity/pool block.  
**Why:** Tail latency governance for processing time.

### 5. Event / block observation timestamps
**Gap:** No mempool or block-arrival time → `event_to_decision` is null.  
**Need:** `event_observed_at` (or `block_timestamp` + receive time) on candidates when event-driven sources exist.  
**Why:** Strategy-specific hot-path justification requires opportunity lifetime evidence.

### 6. Continuous RPC / quoter histograms
**Gap:** Provider EWMA appears tied to early activity (`last_ok_at` ~ W1); no per-candidate quoter latency.  
**Need:** Rolling histograms (p50/p95/p99) by chain/host from existing traffic only — no synthetic probes.  
**Why:** Separate provider delay from queue wait.

### 7. Evidence completeness
**Gap:** 289/672 verified candidates lack evidence bundles.  
**Need:** Counter + reason enum for skipped/failed finalisation (`evidence_persist_error`, `swallowed_exception`).  
**Why:** 43% missing blocks correlated analysis and hides finalisation failures.

### 8. Path tagging for `decision_history` writer
**Gap:** Continuous ~456 decisions/h on Base with no stage timings and unclear relation to flash-loan pool.  
**Need:** Stable `pipeline_id` / `writer_component` field on decision rows.  
**Why:** Prevent mixing unrelated pipelines when computing e2e latency.

### 9. Discovery tick staging
**Gap:** TVL / queue-status / static enumeration / upsert durations not separately timed in retained telemetry.  
**Need:** Per-tick timers: `tvl_ms`, `queue_status_ms`, `enumerate_ms`, `upsert_ms`, `tick_total_ms`, `candidates_emitted`.  
**Why:** Previously reported “work before discovery” cannot be quantified on this runtime from stored data alone.

---

## Explicitly unavailable values (represented as null in JSON)

| Metric | Reason |
|---|---|
| `event_to_decision_s` | No event timestamps |
| `rpc_quote_retrieval_s` (per candidate) | Not instrumented |
| `mev_classification_s` | Gate-9 not evaluated / no duration |
| `economics_gas_profit_gate_s` | Outcomes only |
| `active_verify_job_s.p95/p99` | Pool export incomplete |
| Live steady-state verifies/min | Scanner disabled |

---

## Minimum next measurement package (do not implement here)

1. Persist candidate `claimed_at` + stage ms fields on evidence diagnostics.  
2. Export verify-duration p95/p99 + window bounds on status API.  
3. Run one bounded SHADOW flash-loan observation (≤30–60 min) under current safety posture.  
4. Re-run this report’s Mongo/API queries; require sample_count ≥ 1 000 verifies for processing percentiles and non-zero live claims/verifies rates.

Until (1)–(3) exist, any claim of “RPC-dominated hot path” or “sub-second SLO” remains **INSUFFICIENT TELEMETRY**.
