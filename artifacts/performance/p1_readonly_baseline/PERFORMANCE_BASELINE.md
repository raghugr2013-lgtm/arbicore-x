# ArbiCore X — P1 Read-Only Performance Baseline

**Report generated (UTC):** 2026-10-09T01:14:00Z (approx.)  
**Method:** Read-only inspection of the deployed runtime, public/status APIs, MongoDB reads, and Docker metadata. No code, config, traffic, RPC probing, scanner enablement, or trading-state changes.

**Baseline quality:** **PARTIAL TELEMETRY** — identity and safety verified; flash-loan pipeline stages measurable for one early post-deploy window; continuous stage histograms and live throughput rates unavailable while the flash-loan scanner is disabled.

---

## 1. Runtime identity and safety state

| Field | Expected reference | Observed | Match |
|---|---|---|---|
| Container | `arbicore-x-backend-new` | `arbicore-x-backend-new` | yes |
| Image tag | `arbicore-x-backend:hybrid-e-rpc-9244ebd` | same | yes |
| Image digest | `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` | same (`docker inspect` Image ID) | yes |
| Combined commit (`BUILD_INFO.json` / `ARBICORE_GIT_SHA`) | `fff0d0eced5ce3783cff18fb976e55a2a6504504` | same | yes |
| Workers | 6 | `ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS=6` | yes |
| AUTOEXEC | false | `ARBICORE_AUTOEXEC_AUTOSTART=false`; auto-executor `running=false` | yes |
| RUNTIME_AUTOSTART | false | `ARBICORE_RUNTIME_AUTOSTART=false` | yes |
| Signing / broadcast | disabled | `SIGNING_ACTIVE_KEY_VERSION` unset; evidence `unsigned_reason=no active signing key`; flashloan journey `ready_for_signing=false`, `ready_for_broadcast=false` | yes |
| Execution mode | SHADOW | `ARBICORE_EXECUTION_MODE=SHADOW`; kill switch engaged (`boot_default`); `live_execution_enabled=false` | yes |

### Discrepancies / notes (non-blocking)

- Compose label `arbicore.gitsha=2a6fadb8…` is **stale** vs `BUILD_INFO.json` / `ARBICORE_GIT_SHA` (`fff0d0ec…`). Treat `BUILD_INFO.json` + env git sha as authoritative for this image.
- `ARBICORE_VERSION` / `ARBICORE_BUILD_TIME` env still show `99059c0` / `2026-09-14` (stale packaging metadata). Image content commit is `fff0d0ec…` built `2026-10-08T07:58:15Z`.
- `ARBICORE_SCANNER_AUTOSTART=true`, but wave/shadow scanner adapters and canonical flash-loan scanner report **`enabled=false` / not running**. Capacity rates `claims_per_min=0`, `verifies_per_min=0`, `fresh_eligible_depth=0` at measurement time.
- Uvicorn process: `--workers 1` (API process). The “6 workers” baseline refers to **flash-loan verification pool workers**, not uvicorn workers.
- Restart count: **0**. Health: **healthy**. Started: `2026-10-08T08:33:43Z` (~16.5 h uptime at measurement).

### Scanner / concurrency / RPC topology (redacted)

- DEX/CEX/FUNDING/LAUNCH family env flags: all `false`.
- Canonical flash-loan scanner: instantiated, SHADOW, detection-only, `quote_provider=live`, pool universe 30, **enabled=false**.
- Verification workers configured: **6** (ceiling 36 in code stats only; not changed).
- RPC topology (hosts only): Alchemy-backed endpoints for ethereum/arbitrum/polygon/optimism/bnb; Base primary host `mainnet.base.org` in runtime config. Endpoint secrets redacted in this report.
- HTTP hardening (config): timeout 8s, retries 2, backoff 200 ms, breaker open 60s.
- Quoter 429 safeguards observed in scanner capacity proxy: `max_retries_429=1`, `cooldown_s=60`, `cooldown_hosts_active=0` at snapshot.

### Resources (existing docker stats)

| Resource | Value |
|---|---|
| Backend CPU | ~1.1–1.5% |
| Backend memory | ~175 MiB |
| Backend PIDs | 17 |
| Mongo (`factory-mongo`) memory | ~9.3 GiB |
| Backend restarts | 0 |

---

## 2. Measurement windows

| Window | Bounds (UTC) | What it covers |
|---|---|---|
| **W0 — container lifetime** | 2026-10-08T08:33:43Z → report time (~2026-10-09T01:14Z) | Identity, backlog, decision_history volume |
| **W1 — flash-loan active verify** | 2026-10-08T08:37:56Z → 2026-10-08T08:54:26Z (≈990.5 s) | 672 verified candidates; primary pipeline timings |
| **W2 — evidence-correlated subset** | same deploy; 383 evidence bundles with diagnostics | observe→claim→stamp breakdown |
| **W3 — continuous decision_history** | container start → report; last 6 h ≈456 decisions/h | Separate Base triangular/cross-dex decision writer (not flash-loan verifier) |

Flash-loan scanner capacity counters (`iterations=4`, `drain_batches=4`) are **in-memory since process start** and frozen after the early drain; they are not a live rolling window.

---

## 3. Pipeline latency breakdown

### Legend

- **Wall-clock:** end-to-end elapsed between persisted timestamps.
- **Processing:** active verification job duration inside the worker pool.
- **Queue wait:** time from discovery (`hint_observed_at`) to claim (`claimed_at` in evidence diagnostics).

Do **not** add unrelated percentiles across W1/W2/W3 to invent a single e2e number.

### A. Flash-loan discovery → decision (W1 / W2) — primary path

| Stage | Metric type | n | p50 | p95 | p99 | min | max | mean | Source |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Discovery → verify (observe→verify) | wall-clock | 672 | **379.2 s** | 716.2 s | 732.8 s | 44.7 s | 743.7 s | 423.7 s | Mongo `arbicore_discovery_candidates` (`hint_observed_at`→`verified_at`); field `verification_latency_ms` equals this wall-clock |
| Discovery → claim | queue wait | 383 | **375.1 s** | 716.8 s | 717.1 s | 43.0 s | 717.1 s | 408.7 s | Evidence `diagnostics.hint_observed_at`→`claimed_at` |
| Claim → stamp | processing+finalise wall | 383 | **6.54 s** | 12.73 s | 15.76 s | 0.67 s | 20.68 s | 6.98 s | Evidence `claimed_at`→`stamped_at` |
| Active verify job | processing | 672 | **1.64 s** (median) | *null* | *null* | 0.011 s | 11.07 s | 1.925 s | Scanner `verification_pool` (no p95/p99 exported) |
| Capacity “age at verify” | wall-clock | 512 | 663.8 s | 718.1 s | *null* | 94.3 s | 732.6 s | 532.1 s | Scanner `capacity.candidate_age_at_verify` (subset; differs from Mongo n=672) |
| Evidence persist | processing | 383 | 0.00027 s | 0.0014 s | 0.0050 s | 0.00012 s | 0.014 s | 0.00054 s | `created_at`→`persisted_at` |
| Event observation → decision | — | — | **null** | — | — | — | — | — | No mempool/block-event timestamps on this path |

**Interpretation:** queue wait (~6 minutes p50) dominates discovery→decision. Active verify (~1.6 s median) is secondary. Claim→stamp (~6.5 s p50) is larger than pool job duration, implying additional post-claim wait/finalisation outside the pure verify timer.

### B. Throughput and coverage (W1)

| Metric | Value | Source |
|---|---|---|
| Candidates observed (`hint_observed_at` ≥ start) | 14,108 | Mongo |
| Verified | 672 (4.76%) | Mongo |
| Unverified and expired | 13,436 (95.2%) | Mongo |
| Still-open unverified at report time | 0 (among since-start set) | Mongo |
| Verifies over W1 span | **40.7 / min** (672 / 16.51 min) | Mongo first/last `verified_at` |
| Last batch wall | 32 jobs / 25.82 s ≈ **74.4 / min** instantaneous | Scanner pool |
| Drain | 128 candidates / 65.66 s across 4 batches | Scanner stats |
| Worker utilisation (recorded) | 0.802 | Scanner capacity |
| Workers active peak / now | 6 / 0 | Scanner pool |
| Live claims/verifies per min (now) | **0 / 0** | Scanner disabled / idle |
| Queue depth (snapshot) | 7054 | Scanner capacity |
| Fresh eligible depth | **0** | Scanner capacity |
| Per-chain claims (fairness) | 112 each across 6 chains | Scanner capacity |
| Per-strategy backlog | route_search 5118; triangular 1584; generic_dex 352 | Scanner capacity |

### C. Continuous decision_history path (W3) — separate from flash-loan verifier

| Metric | Value |
|---|---|
| Decisions since container start | ~7,488+ |
| Recent rate | ~456 / hour (~7.6 / min), stable across last 6 hours |
| Chain (recent 2000) | Base 100% |
| Outcomes | `would_execute=true`: 0; `net_profit_usd>0`: 0 |
| Quote age | p50 0.095 s; p95 0.467 s; max 2.38 s (n=5000 sample) |
| Stage timing (quote/gas/MEV/persist) | **null** — documents lack stage durations |

This path is **not** the flash-loan verification pool. It continues while flash-loan scanner is disabled. Treat as a separate observe-only decision writer unless proven otherwise.

### D. RPC / Mongo (available proxies)

| Signal | n / window | Result | Caveat |
|---|---|---|---|
| Provider EWMA latency by chain | successes since process start; `last_ok_at` ≈ 2026-10-08T08:54Z | Base ewma ~186–442 ms; BNB ~73–728 ms; ETH ~59–100 ms; see `performance_metrics.json` | Appears dominated by early activity; not a continuous rolling histogram |
| Quoter 429 / rate-limit / cooldown (W1 proxy) | scanner capacity | http_429=0; rpc_rate_limit=2; cooldown_gate=1; retries=1; host `mainnet.base.org` count=3 | Proxy counters, not full RPC trace |
| Denied venue unreadable | 15 / 672 | 2.2% | May include RPC/read failures |
| Mongo op latency (scanner local) | 256 | p50 30.7 ms; p95 232.6 ms; max 34,785 ms | Tail outlier present; mean pulled up |

### E. Economics / gates (not performance bottlenecks)

| Gate / outcome | Count |
|---|---|
| Verifier confirmed | 0 |
| Verifier denied | 672 |
| Gate-7 atomic profit fails | 657 |
| Venue unreadable | 15 |
| Gate-7 positive net | 0 |
| Best / median / worst net (gate-7 evals) | −59.77 / −262.25 / −10,019.64 USD |

Negative economics are **Category 4**, not a speed finding.

### F. Evidence observability

| Item | Value |
|---|---|
| Verified candidates with evidence bundle | 383 / 672 (**43% missing**) |
| Evidence source | `flash_loan_arb_verifier` |
| Signing | unsigned (no active key) — expected under current safety |

---

## 4. Bottleneck findings (evidence-backed)

### Finding 1 — Queue wait dominates discovery→decision  
**Category 1 (general performance) + Category 2 (coverage/cadence interaction)**  
- Evidence: observe→claim p50 **375 s** (n=383); observe→verify p50 **379 s** (n=672); active verify median **1.64 s**.  
- Impact: ~99% of discovery→decision wall-clock is waiting, not verifying.  
- Confidence: **high**.

### Finding 2 — Most discovered candidates expire unverified  
**Category 2 (coverage / discovery volume vs verify capacity)**  
- Evidence: 14,108 observed vs 672 verified (4.76%); 13,436 expired unverified.  
- Impact: majority of enumerated routes never receive a decision; insertion/volume exceeds drain.  
- Confidence: **high** for this deploy window.  
- Note: faster workers alone do not prove better EV without route-quality filtering (Category 4 / 2).

### Finding 3 — Active verify is seconds-scale; claim→stamp gap suggests extra finalisation latency  
**Category 1**  
- Evidence: pool median 1.64 s / max 11.07 s; claim→stamp p50 6.54 s (n=383).  
- Impact: modest vs queue wait; material if strategy requires sub-second claim→decision.  
- Confidence: **medium** (missing per-stage split: quote vs RPC vs gate compute vs persist).

### Finding 4 — Mongo tail latency spike  
**Category 1**  
- Evidence: mongo latency max **34.8 s** (n=256); p95 233 ms.  
- Impact: can inflate individual job tails; not the median bottleneck.  
- Confidence: **medium** (local scanner timer; cause not isolated).

### Finding 5 — RPC rate-limit pressure small in W1; provider EWMA stale afterward  
**Category 1 (ops) / measurement gap**  
- Evidence: only 3 rate-limit/cooldown events on `mainnet.base.org` during recorded proxy counters; provider `last_ok_at` frozen near W1 end.  
- Impact: cannot claim RPC dominates e2e from current continuous metrics.  
- Confidence: **medium** for W1; **low** for “current” RPC health.

### Finding 6 — All measured flash-loan outcomes economically negative  
**Category 4**  
- Evidence: 0 confirmed; 657/657 gate-7 nets negative.  
- Impact: optimising latency cannot create profit from these samples.  
- Confidence: **high**.

### Finding 7 — Missing evidence bundles impair observability  
**Category 1 (observability)**  
- Evidence: 289/672 verified without bundle.  
- Impact: claim timestamps / gate detail unavailable for 43% of verifies.  
- Confidence: **high**.

### Finding 8 — Continuous decision_history path has fresh quotes but zero executable EV  
**Category 4 (+ possible Category 2)**  
- Evidence: ~456 decisions/h, quote_age p50 ~95 ms, 0 positive net / 0 would_execute.  
- Impact: separate from flash-loan queue; not a worker-pool throughput proof.  
- Confidence: **high** on outcomes; **low** on whether this path shares RPC contention with flash-loan when both active.

---

## 5. Coverage vs speed vs economics

| Question | Answer from this baseline |
|---|---|
| Where is time spent? | **Queue wait** (minutes) ≫ claim→stamp (seconds) ≫ pure verify (~1–2 s) ≫ persist (sub-ms). |
| Architectural inefficiency? | Yes: discovery insertion volume vs 6-worker drain; missing `claimed_at` on candidate docs; incomplete evidence. |
| Strategy-specific latency need? | **Not justified yet** — no positive EV samples; no measured opportunity lifetime on this runtime for a hot-path SLO. |
| Economics-limited? | **Yes** for flash-loan W1 and continuous Base decisions. |
| Coverage-limited? | Likely yes in parallel workstreams (pool/venue/route inventory); this baseline confirms verify-rate ~5% and backlog skew to `flash_loan_route_search`, but does not inventory missing UniV4 pools. |

---

## 6. Ranked optimisation opportunities

| Rank | Finding | Measured impact | Confidence | Class | Expected benefit | Impl. risk | Reversibility | How to benchmark | Preconditions / acceptance | Next action |
|---:|---|---|---|---|---|---|---|---|---|---|
| 1 | Persist `claimed_at` on candidates + per-stage ms in evidence (`quote`,`rpc`,`gate7`,`persist`) | Unblocks valid claim→decision and RPC-dominance tests; 43% evidence gap | high | Cat 1 (measurement) | Enables trustworthy next baseline | low | high | Re-run this report’s Mongo/evidence queries | SHADOW only; no concurrency change | **measurement** |
| 2 | Discovery admission / TTL / priority so volume matches verify capacity | 95% expire unverified; p50 wait ~6 min | high | Cat 1+2 | Higher verify rate of *fresh* candidates; lower wait | medium | medium | verify_rate, observe→claim p50, fresh_eligible_depth | Fairness across chains preserved; no AUTOEXEC | implementation proposal |
| 3 | Investigate Mongo p95/max on scanner ops | max 34.8 s | medium | Cat 1 | Reduce verify tails | medium | high | mongo latency histogram under SHADOW | Identify query/index; no schema rewrite first | measurement |
| 4 | Reduce claim→stamp gap (finalisation path) | p50 6.5 s vs verify 1.6 s | medium | Cat 1 | Lower decision finalisation latency | medium | medium | claim→stamp p50/p95 after stage split | Stage split exists first | measurement then proposal |
| 5 | Worker-count increase | Utilisation 0.80 in W1; live rate now 0 | low–medium | Cat 1 | Unknown without controlled window | medium | high | verifies/min + observe→claim p50 A/B | Only after admission control; SHADOW; kill engaged | **no action** until #1–2 measured |
| 6 | Sub-200 ms / Flashblock hot path | No positive EV; no event timestamps | low | Cat 3 | Speculative | high | low | Requires strategy lifetime evidence | Not met | **no action** |
| 7 | RPC provider rewrite | W1 429s rare; EWMA stale | low | Cat 1/3 | Unclear | medium | medium | continuous RPC histograms | Need #1 instrumentation | measurement |

---

## 7. Limitations

1. Flash-loan scanner **disabled** at report time → live throughput rates are zero; W1 is a single early window.  
2. Pool stats lack p95/p99 for verify duration.  
3. Candidate documents have `claimed_at=null` even when verified; claim timing only from evidence (n=383).  
4. No event-time / block-arrival timestamps → event→decision unavailable.  
5. No continuous RPC latency histogram on the quoter hot path.  
6. Stale repo `reports/decision_analytics_*.json` (Aug 2026 sample) **excluded** as baseline-of-record.  
7. Prior conversation throughput figures used only as cross-check labels, not as substituted measurements.

---

## 8. Safety confirmation (this task)

- Source code: **unchanged**  
- Configuration / env / Compose: **unchanged**  
- Deployment / containers: **not restarted or rebuilt**  
- RPC: **no new benchmark probes**; only existing status endpoints and stored counters  
- Trading: AUTOEXEC remains false; kill engaged; signing/broadcast remain disabled; scanners not enabled  

Artifacts written only under `artifacts/performance/p1_readonly_baseline/`.
