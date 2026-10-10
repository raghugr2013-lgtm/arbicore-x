# Gate 9 Official Evidence Checklist (prepare-only)

- **Status:** PREPARE ONLY — **not** Gate 9 PASS; **not** an 8h confidence claim
- **Date:** 2026-10-02
- **Workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Runtime:** `arbicore-x-backend-new` / image `arbicore-x-backend:g5.79-green-20260927`
- **Official Gate 9:** **≥24h continuous** SHADOW paper-validation window (unchanged)
- **Official Gate 10:** **≥72h continuous** (unchanged; listed for package completeness only)
- **Binding tip (freeze):** `9b196cde0c975d0efe94e94f49de05b4244bdbc6`
- **Reuse:** `docs/certification/24H_PARALLEL_READINESS_AUDIT_20261002.md`, `PAPER_GATE9_10_VALIDATION_20261002.md`, `PAPER_VALIDATION_MINIMAL_DELTA_PLAN_20261002.md`, M6 post-alchemy PASS
- **STOP:** No source/config/image/mode changes; no SHADOW restart/reset/shorten/promote; no Recommendation/AUTOEXEC/RUNTIME/signing/broadcast; no capability-matrix reclassification

---

## Binding criteria (do not relabel)

| Gate | Duration | Economic / continuity bar | Allowed early labels |
|---|---|---|---|
| **Gate 9** | **≥24h** continuous runner since `started_at` | Non-negative paper PnL (A=0 / EXECUTABLE=0 ⇒ **$0** honest); safety held | CONDITIONAL / not-yet |
| **Gate 10** | **≥72h** continuous | Drawdown within documented limits (A=0 ⇒ DD=$0 honest) | CONDITIONAL / not-yet |
| Accelerated 8h | ≥8h | Confidence only | **HEALTHY / HEALTHY WITH OBSERVATIONS / BLOCKED** — **never** Gate 9 PASS |

---

## Campaign anchors (re-verify live at stamp time)

| Field | Expected / known (Phase-1 live re-verify) |
|---|---|
| Container | `arbicore-x-backend-new` · `running` / `healthy` |
| Image | `arbicore-x-backend:g5.79-green-20260927` |
| Container `StartedAt` | `2026-10-02T06:19:33.513948555Z` |
| Paper runner `started_at` | `2026-10-02T06:19:43.018995+00:00` |
| `restart_count` | **0** (any >0 before Gate 9 ⇒ continuity break; do not claim Gate 9 on broken window) |
| Official Gate 9 ETA | `2026-10-03T06:19:43Z` (24h from runner start) |
| Official Gate 10 ETA | `2026-10-05T06:19:43Z` |
| 8h accelerated ETA | `2026-10-02T14:19:43Z` |

---

## Exact APIs / fields to collect for official Gate 9

Collect into `reports/paper_validation/gate9_*_<TS>Z.json` (and a human cert under `docs/certification/`). **No secrets** in artifacts (redact RPC paths, tokens, cookies).

### A. Continuity / runner

| Source | Fields required |
|---|---|
| `GET /api/arbicore/validation/metrics` | `runner.is_running`, `started_at`, `last_cycle_at`, `cycles_completed`, `exceptions`, `opportunities_seen`, `opportunities_processed`, `opportunities_skipped_dup`, `last_error`, `outcome_counts` |
| Derived | `span_hours` / `uptime_hours` from `started_at`→collection; must be **≥24.0** for Gate 9 |
| Docker inspect (read-only) | `State.Status`, `State.Health.Status`, `State.StartedAt`, `RestartCount`, `Config.Image` |
| `GET /api/arbicore/validation/daily_status` | `run_id`, `running`, `last_summary_at`, `last_anomalies` |

### B. Paper evidence / opportunity histogram

| Source | Fields required |
|---|---|
| `GET /api/arbicore/validation/report` | `total`, `histogram{EXECUTABLE,REJECTED,UNPROFITABLE,LIQUIDITY_FAILURE,GAS_FAILURE,ROUTE_FAILURE,RISK_FAILURE,SIMULATION_FAILURE}`, `rates`, `executable_rate` |
| `GET /api/arbicore/validation/evidence?limit=…` | `total`, sample `items[]` (ids only if present) |
| `GET /api/arbicore/validation/evidence?outcome=EXECUTABLE&limit=…` | EXECUTABLE rows for PnL spot-check |
| `GET /api/arbicore/paper/stats` | `analyses`, `policy_blocked`, `ev_positive`, `ev_negative`, `last_run_at`, `last_error` |
| `GET /api/arbicore/dashboard/pulse` → `paper_validation` | `total`, `executable_rate`, `runner_running`, `outcome_counts` |
| Mongo (read-only) | `arbicore_paper_evidence.count` + outcome histogram; `arbicore_opportunity_journal.count`; optional `evidence_bundles` since campaign start (verifier audit sink) |

### C. Economic evidence (A/B/C/E + Gate7)

| Source | Fields required |
|---|---|
| Reuse M6 JSON (no harness re-run required if image unchanged) | `reports/shadow_validation/m6_post_alchemy_reset_latest.json` → `economic_evidence` **A/B/C/D/E/F/G** |
| Paper PnL method (plan-canonical) | `paper_pnl_usd = Σ net_profit_usd` over `outcome=EXECUTABLE`; if EXECUTABLE=0 ⇒ **0.00** / DD **0.00** |
| Gate 7 confirmation | floor **$25.00**; rejects **$24.99**; accepts **$25.00** (from prior Gate9 preflight / M6; image must still be `g5.79-green-20260927`) |

### D. Safety / freeze posture

| Source | Fields required |
|---|---|
| Env (container) | `ARBICORE_EXECUTION_MODE=SHADOW`, `SHADOW_CERT_ENABLED=true`, `SCANNER_AUTOSTART=true`, `AUTOEXEC_AUTOSTART=false`, `RUNTIME_AUTOSTART=false`, `PAPER_VALIDATION_ENABLED=true` |
| H05 | `ARBICORE_PRICE_FEED_ENABLED` / `BORROW_SIZER_ENABLED` **UNSET/OFF** |
| `GET /api/arbicore/safety/status` | `live_execution_enabled=false`, `effective_kill_engaged=true`, kill reason, `require_paper_validation` |
| Pulse / execution counters | signing_reached=false; broadcasts=0; funds_moved=0 (as exposed) |
| Git | `rev-parse HEAD` + confirm **no** `app/` / image / gate config edits for the stamp |

### E. Six-chain RPC + infra errors

| Source | Fields required |
|---|---|
| Per-chain `eth_chainId` + `eth_blockNumber` | ethereum, arbitrum, optimism, polygon, bnb, base — host + redacted URL + ok/429 |
| Alchemy 429 | present/absent (monthly capacity) |
| Balancer notes | reuse M6: P0 / P1 subgraph unset / P1b getLogs range (do **not** restart campaign to “fix”) |

### F. Gate 8 / H05 (unchanged)

| Check | Required proof |
|---|---|
| Gate 8 | floor **$100,000**; fail-closed on unverifiable TVL (preflight/M6) |
| H05 | exact-size / price-feed / borrow-sizer **not enabled** |

### G. Optional joins (from 24h parallel audit — not blockers)

| Join key | Surfaces |
|---|---|
| `opportunity_id` / `candidate_id` / `validation_id` | verifier `m2.3` bundle ↔ paper `EvidenceBundle` |
| Soft gaps E1–E5 | Document only; do **not** invent fills |

---

## Acceptance checklist (official Gate 9 stamp)

### Must be true

- [ ] `runner.is_running == true` continuously from `2026-10-02T06:19:43Z` (or documented unbroken start)
- [ ] `RestartCount == 0` (or documented continuity still holds if container not recycled)
- [ ] Elapsed **≥ 24.0 h**
- [ ] Mode still **SHADOW**; AUTOEXEC/RUNTIME **false**; kill engaged; live execution **false**
- [ ] Gate7=$25 / Gate8 fail-closed / H05 OFF — **unchanged**
- [ ] Six-chain RPC probed at stamp (report any chain failure honestly)
- [ ] Paper PnL method applied; numeric result recorded (may be **0.00**)
- [ ] Histogram + evidence totals recorded (**0 is allowed**; do not fabricate EXECUTABLE)
- [ ] A/B/C/E referenced (M6 and/or live paper outcomes — label source)
- [ ] Artifacts written under `docs/certification/` + `reports/paper_validation/` **without secrets**
- [ ] Verdict is Gate 9 **PASS** only if duration+safety+PnL bars met; else **CONDITIONAL** / **BLOCKED**

### Explicitly forbidden on Gate 9 package

- Calling 8h (or any &lt;24h) result “Gate 9 PASS”
- Restarting/resetting/shortening the campaign to manufacture duration
- Activating Recommendation / PAPER promotion / AUTOEXEC / RUNTIME / signing / broadcast
- Reclassifying capability-matrix cells
- Inventing paper fills or non-zero PnL when EXECUTABLE=0

---

## Continuously captured outputs (Phase-1 live, ~2026-10-02T08:27Z)

| Surface | Receiving data? | Notes / gaps |
|---|---|---|
| Paper validation runner | **Yes** | `is_running=true`; cycles advancing; exceptions=0 |
| `/validation/report` histogram | **Thin** | `total=0`; all outcome buckets 0 |
| `/validation/evidence` (paper) | **Thin** | `total=0` |
| Mongo `arbicore_paper_evidence` | **Thin** | count **0** |
| Mongo `arbicore_opportunity_journal` | **Thin** | count **0** |
| Mongo `evidence_bundles` (verifier audit) | **Yes** | continuously appending; **~275** since campaign start (string `created_at`); outcomes **null** (not paper EXECUTABLE) |
| `/paper/stats` | **Idle** | analyses=0 |
| Daily validation run | **Yes** | `run_20261002_0619` running |
| Pulse `paper_validation` | **Yes** | runner_running=true; total=0 |
| Pulse `shadow_certification` engine | **Inactive** | `active=false` (SHADOW mode + paper runner is the continuity path; do not start cert engine) |
| Six-chain RPC | **Yes** (retry-confirmed) | Alchemy chains OK; Base public RPC briefly 403 then recovered — document if recurs at stamp |
| M6 economic A/B/C/E | **Static reuse** | A=0,B=10,C=8,E=14 from post-alchemy PASS |

**Gap honesty (P0 ops, not code):** paper opportunity pipeline empty (`opportunities_seen/processed=0`). Gate 9 may still stamp CONDITIONAL/PASS on duration+safety+honest $0 PnL per plan — **do not invent evidence**.

---

## Artifact map (reuse existing; extend at ≥24h)

| Kind | Path pattern |
|---|---|
| Prior CONDITIONAL Gate9–10 | `docs/certification/PAPER_GATE9_10_VALIDATION_20261002.md` + `reports/paper_validation/gate9_10_*_20261002T072116Z.json` |
| Parallel readiness | `docs/certification/24H_PARALLEL_READINESS_AUDIT_20261002.md` |
| M6 economics | `docs/certification/M6_POST_ALCHEMY_RESET_SHADOW_20261002.md` + `reports/shadow_validation/m6_post_alchemy_reset_latest.json` |
| Pre-8h status | `docs/certification/SHADOW_ACCELERATED_STATUS_SNAPSHOT_20261002T080658Z.md` |
| 8h template | `docs/certification/SHADOW_ACCELERATED_8H_CHECKPOINT_TEMPLATE_20261002.md` |
| 8h official confidence (after ≥8h) | `docs/certification/SHADOW_ACCELERATED_8H_CHECKPOINT_20261002.md` + `reports/shadow_validation/accel_8h_checkpoint_*.json` |
| Official Gate 9 (after ≥24h only) | `docs/certification/PAPER_GATE9_*` + `reports/paper_validation/gate9_*` |

---

## Freeze confirmation (this prepare task)

| Check | Result |
|---|---|
| App / contracts / Docker image modified? | **No** (docs/reports only) |
| Campaign restarted/reset? | **No** |
| Mode / Gate7 / Gate8 / H05 / AUTOEXEC / RUNTIME changed? | **No** |
| Recommendation Mode created/activated? | **No** |
