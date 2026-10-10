# POST-PATCH 12h SHADOW Validation Report

> **POST-PATCH VALIDATION — NOT OFFICIAL GATE 9 — NOT GATE 10**
>
> This report closes the Workstream A (`befb14e`) post-cutover 12h SHADOW campaign.
> It is **not** official Gate 9 (≥24h) and **not** Gate 10 (≥72h).
> Do **not** claim profitability from zero opportunities / zero EXECUTABLE.

- **Status:** **CONDITIONAL**
- **Collected at (UTC):** `2026-10-03T04:03:26Z` (stamp `20261003T040326Z`)
- **Workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Container:** `arbicore-x-backend-new`
- **Post-patch image / tip:** `arbicore-x-backend:ws-a-befb14e-20261002` / `befb14e6aa77515daa038e142ff978822a4fab91`
- **Image digest (running):** `sha256:12759b11a783619ad25746a030c5bbcc71b83ed64ff05b3316153d6402a594ae` (**matches** expected)
- **Pre-patch baseline image:** `arbicore-x-backend:g5.79-green-20260927`
- **Workstream A cert gate:** **READY WITH CONDITIONS** — `WORKSTREAM_A_QUOTER_429_BEFB14E_INDEPENDENT_CERT_20261002.md` §13
- **Campaign doc (was IN_PROGRESS):** `POST_FIX_12H_SHADOW_CAMPAIGN_IN_PROGRESS_20261002.md` → **COMPLETE**
- **Machine evidence:** `reports/shadow_validation/post_patch_12h_20261003T040326Z.json`
- **API raw:** `reports/shadow_validation/post_patch_12h_api_raw_20261003T040326Z.json`
- **Failover metrics:** `reports/shadow_validation/post_patch_12h_failover_20261003T040326Z.json`
- **FP census:** `reports/shadow_validation/post_patch_12h_fp_census_20261003T040326Z.json`
- **Latest pointer:** `reports/shadow_validation/post_patch_12h_latest.json`
- **PRE-FIX 8h baseline:** `PRE_FIX_8H_BASELINE_FREEZE_20261002.md` + `accel_8h_checkpoint_20261002T142017Z.json`
- **STOP:** No LIMITED_LIVE / AUTOEXEC / RUNTIME / signing / broadcast; secrets redacted (fp8 OK)

---

## FINAL OUTPUT

| Field | Value |
|---|---|
| Label | POST-PATCH VALIDATION — NOT OFFICIAL GATE 9 — NOT GATE 10 |
| 8h baseline captured at | `2026-10-02T14:20:17Z` (freeze `2026-10-02T14:44:46Z`) |
| Deploy cutover / T0 StartedAt | `2026-10-02T15:08:52.884157323Z` |
| 12h ETA | `2026-10-03T03:08:52Z` |
| Post-patch window end (collect) | `2026-10-03T04:03:26Z` |
| Post-patch elapsed hours (≥12.0?) | **12.91 h** — **YES** |
| restart_count (post-patch window) | **0** |
| StartedAt unchanged vs T0 | **YES** |
| Post-patch verdict | **CONDITIONAL** |
| Product-fix layer | **PASS** (amplification bound + cooldown + continuous SHADOW safety) |
| RPC/Alchemy infra layer | **BLOCKED_OBSERVED** (base.org soft-RL; stale `ce00e63d`; 0 ok quotes) |
| Economic opportunity layer | **ABSENT** (opportunities=0, EXECUTABLE=0, paper=0) |
| Official Gate 9 status (separate) | **not-yet / not claimed** |
| Rollback available | `g5.79-green-20260927` **YES** (untouched) |

---

## Layered verdict (binding)

| Layer | Result | Why |
|---|---|---|
| **1. Product-fix validation** (`befb14e` 429 amplification / cooldown) | **PASS** | Primary-failover Alchemy POST median **2.0** (98.93% ≤2 within 3s); naive M2 all-failovers **0.067** (cooldown-gated); M7 cooldown **14,591**; no ~5× amplifier recurrence; continuity + SHADOW safety hold |
| **2. RPC / Alchemy infrastructure** | **BLOCKED_OBSERVED** | Persistent Network Config secondary fp **`ce00e63d`** after `env_sync` @ `15:09:08Z`; **996/996** Alchemy HTTP 429s on `ce00e63d`; docker tip fp **`5e5d5bb1`** only used at boot (13×200 + 1×400); primary `mainnet.base.org` soft `-32016` + cooldown drives failovers; **0** `status=ok` quotes |
| **3. Economic opportunity / paper** | **ABSENT** | Runner `opportunities_seen=0`, report `total=0`, EXECUTABLE=0, paper analyses=0 → PnL=$0 / DD=$0 honest |

**Overall: CONDITIONAL** — product-fix objectives met with continuous SHADOW safety; infra + economic blockers dominate outcomes. **Not PASS** merely because the container stayed healthy. **Not FAIL** — amplification bug did not recur; safety/continuity intact.

---

## 1. Continuity (post-patch window)

| Field | Observed |
|---|---|
| Status / Health | `running` / `healthy` |
| StartedAt (T0) | `2026-10-02T15:08:52.884157323Z` (**unchanged**) |
| RestartCount | **0** |
| Elapsed T0→collect | **12.9094 h** (past ETA `2026-10-03T03:08:52Z`) |
| Runner `is_running` | **true** |
| Runner `started_at` | `2026-10-02T15:09:05.593316+00:00` |
| Runner `last_cycle_at` | `2026-10-03T04:03:28.617174+00:00` |
| Cycles completed | **9,229** |
| Exceptions | **0** |
| Interruptions | **none** (RestartCount=0; StartedAt stable; runner continuous) |

---

## 2. Safety (must hold) — HELD

| Control | Required | Observed |
|---|---|---|
| `ARBICORE_EXECUTION_MODE` | SHADOW | **SHADOW** |
| `ARBICORE_SHADOW_CERT_ENABLED` | true | **true** |
| `ARBICORE_AUTOEXEC_AUTOSTART` | false | **false** |
| `ARBICORE_RUNTIME_AUTOSTART` | false | **false** |
| `ARBICORE_SCANNER_AUTOSTART` | true | **true** |
| `live_execution_enabled` | false | **false** |
| kill engaged / effective | true | **true** (`boot_default`) |
| flash_loan strategy mode | SHADOW | **SHADOW** |
| signing | 0 / not reached | **0** (SHADOW no-broadcast) |
| broadcast | 0 | **0** |
| funds movement | 0 | **0** |
| H05 price feed / borrow sizer | OFF | **UNSET** (treated OFF) |

---

## 3. Before / after RPC metrics

| Metric | Pre-patch 8h (`g5.79`) | Post-patch ~12.9h (`befb14e`) | Δ / notes | PASS? |
|---|---:|---:|---|:---:|
| Window hours | 8.01 | **12.91** | — | — |
| Base→Alchemy failovers (M1) | 650 (root-cause window) | **15,059** | High primary RL load continues | — |
| Failovers / hour | — | **~1,170** | Mostly cooldown-gated | — |
| Alchemy Base POSTs | 3,266 | **1,010** | Cooldown suppresses most hits | — |
| Alchemy POSTs / failover (M2) | **~5.025** | **0.067** naive; **median 2.0** on primary hits | Target post ≤2.0 | **YES** |
| Primary-hit amplification (3s) | ~5 | **mean 2.026 / median 2.0**; 98.93% ≤2 | ~5× bug fixed | **YES** |
| Alchemy 429 count /hour | 3,255 (pre audit window) | **996 / 77.4/h** | All 429s on stale `ce00e63d` | infra |
| Alchemy 200 | 10 (pre) | **13** (boot `5e5d5bb1` only) | No sustained 200 recovery | — |
| Cooldown activations (M7) | ~0 (absent) | **14,591** | Fix engaged | **YES** |
| Public base.org | RL present | 9,491 POSTs (9,473×200 / **16×429** / 2×503) + soft `-32016` | Primary still RL-class | infra |
| Successful quoter `status=ok` | 0 (honest) | **0** | Fail-closed; no ok inflation | **YES (C4)** |

---

## 4. Quote metrics

| Metric | Pre (8h freeze) | Post (12h) | Notes |
|---|---:|---:|---|
| `status=ok` | 0 | **0** | Log census + no ok inflation |
| `fallback:revert` | (failover path) | **15,059** | Proxy for failed quote hops |
| `fallback:break_even` | — | **0** | — |
| Quote attempts (failover proxy) | — | **15,059** | Not successful quotes |
| Successful quotes | 0 | **0** | Infra-bound, not amplifier regression |

---

## 5. Opportunity / economic

| Metric | Pre 8h | Post 12h |
|---|---:|---:|
| Runner cycles | 5,740 | **9,229** |
| Exceptions | 0 | **0** |
| opportunities_seen / processed | 0 / 0 | **0 / 0** |
| paper report.total | 0 | **0** |
| EXECUTABLE | 0 | **0** |
| REJECTED (+ buckets) | 0 | **0** (empty histogram) |
| paper analyses | 0 | **0** |
| paper_pnl_usd | 0 | **0** |
| max_drawdown_usd | 0 | **0** |

PnL method: A=0 / EXECUTABLE=0 ⇒ $0 / DD=$0 honest. **No invented fills.**

---

## 6. Six-chain coverage (probe at collect)

| Chain | Host | path_fp | chainId+blockNumber | 429 |
|---|---|---|---|---|
| ethereum | eth-mainnet.g.alchemy.com | `5e5d5bb1` | OK | no |
| arbitrum | arb-mainnet.g.alchemy.com | `5e5d5bb1` | OK | no |
| optimism | opt-mainnet.g.alchemy.com | `5e5d5bb1` | OK | no |
| polygon | polygon-mainnet.g.alchemy.com | `5e5d5bb1` | OK | no |
| bnb | bnb-mainnet.g.alchemy.com | `5e5d5bb1` | OK | no |
| base | mainnet.base.org | n/a | OK | no |

Coverage verdict: **6/6 YES** (health probes). Quoter Base path still infra-stressed (separate from probe OK).

---

## 7. Alchemy key identity (campaign window)

| Key fp | POSTs | Status mix | When |
|---|---:|---|---|
| **`5e5d5bb1`** (docker-wired tip) | **14** | 13×200 + 1×400 | Boot / pre-`env_sync` only |
| **`ce00e63d`** (stale Network Config secondary) | **996** | **996×429** | After `env_sync` `2026-10-02T15:09:08Z` through campaign |

Persistent Network Config (read-only GET, no APPLY):

- `rpc_urls.base = [mainnet.base.org, base-mainnet.g.alchemy.com/v2/<fp:ce00e63d>]`
- `updated_at=2026-09-27T09:31:23Z` · `revision_id=rev-615fa528…`

**Q17:** Stale `ce00e63d` **YES — appeared and dominated** Alchemy 429s.  
**Q18:** `5e5d5bb1` **YES — used** at boot only; not the post-sync failover key.

---

## 8. Infrastructure / image

| Field | Observed |
|---|---|
| Image tag | `arbicore-x-backend:ws-a-befb14e-20261002` |
| Image Id | `sha256:12759b11a783619ad25746a030c5bbcc71b83ed64ff05b3316153d6402a594ae` |
| `ARBICORE_GIT_SHA` / BUILD_INFO | `befb14e6aa77515daa038e142ff978822a4fab91` |
| Fix present in image | `_RPC_MAX_RETRIES_429` + `_RPC_HOST_COOLDOWN_UNTIL` in `/app/arbicore/execution/quoter.py` |
| Override | `artifacts/deploy_staging/workstream-a-befb14e/POST_PATCH_OVERRIDE_ws-a-befb14e_20261002T150827Z.yml` |
| Rollback image present | `g5.79-green-20260927` Id `sha256:aaadc3a9…993a` |
| Tracebacks / ERROR lines (T0→collect logs) | **0** |

---

## 9. Pass criteria cheat-sheet

| # | Criterion | Result |
|---|---|---|
| C1 | ≥12.0 h continuous post-deploy | **PASS** (12.91 h; RestartCount=0; StartedAt stable) |
| C2 | M2 Alchemy POSTs/failover ≤2.0 | **PASS** (naive 0.067; primary median 2.0) |
| C3 | 429/hour meaningful drop vs pre | **WEAK / infra-skewed** — absolute 429s still present on stale `ce00e63d`; amplifier removed so load ≠ pre ~5× path |
| C4 | Fail-closed honesty (no ok inflation) | **PASS** (`status=ok=0`) |
| C5 | SHADOW safety; signing/broadcast/funds 0 | **PASS** |
| C6 | RestartCount 0 | **PASS** |
| C7 | Six-chain probes | **PASS** (6/6) |
| C8 | Workstream A deploy gate | **READY WITH CONDITIONS** (product tip) |

Template note: **CONDITIONAL** when C1+C2+C4+C5+C6 hold but infra/economic blockers dominate — **this case**.

---

## 10. Evidence gaps (exact; no invented fills)

- Full `eth_call` body census not available at default LOG_LEVEL; success inferred from `status=ok` / `fallback:*` lines.
- Alchemy dashboard CU not re-fetched at this stamp (prior audits remain correlative).
- Official Gate 9 (≥24h) / Gate 10 (≥72h) **not** started or claimed by this campaign.

---

## 11. Answers 1–20 (evidence bullets)

1. **Elapsed:** **12.9094 h** from T0 `2026-10-02T15:08:52.884157323Z` → collect `2026-10-03T04:03:26Z` (past 12h ETA).
2. **Continuous 12h:** **YES** — StartedAt unchanged; RestartCount=0; runner continuous.
3. **RestartCount:** **0**.
4. **Exceptions/errors:** Runner exceptions **0**; log Traceback/ERROR **0**.
5. **Scanner cycles:** Runner **9,229** cycles completed.
6. **Opportunities detected:** **0** seen / **0** processed.
7. **Quotes:** Attempts (failover proxy) **15,059**; successful `status=ok` **0**; `fallback:revert` **15,059**.
8. **Alchemy HTTP (POST-FIX window):** **13×200** + **1×400** + **996×429** (total POSTs **1,010**).
9. **Base public RPC:** **9,491** POSTs — 9,473×200 / **16×429** / 2×503; plus soft `-32016` failover triggers (**468** primary non-cooldown).
10. **Failover count:** **15,059** Base→Alchemy (14,591 cooldown-gated + 468 soft-RL).
11. **Cooldown activations (M7):** **14,591**.
12. **Retry amplification fixed:** **YES** — primary-hit median **2** POSTs/3s (98.93% ≤2); naive M2 **0.067**; no sustained ~5× recurrence.
13. **Paper / fills / P&L / DD:** report total **0**; EXECUTABLE **0**; analyses **0**; PnL **$0**; DD **$0**.
14. **SHADOW / AUTOEXEC / RUNTIME:** SHADOW / **false** / **false** (held).
15. **Signing / broadcast / funds:** **0 / 0 / 0**; kill engaged; live_execution **false**.
16. **Running image/digest:** `ws-a-befb14e-20261002` / `sha256:12759b11a783619ad25746a030c5bbcc71b83ed64ff05b3316153d6402a594ae`.
17. **Stale `ce00e63d` during campaign:** **YES** — 996 Alchemy POSTs, all 429, after `env_sync`.
18. **`5e5d5bb1` used:** **YES** — boot only (14 POSTs); six-chain probe URLs also fp `5e5d5bb1`.
19. **vs PRE-FIX 8h / T0:** Continuity/safety comparable (0 exceptions, 0 opps); M2 **5.025 → ≤2**; cooldown **absent → 14,591**; image `g5.79` → `befb14e`; economic still zero.
20. **Official 12h report + verdict:** this document — **CONDITIONAL**.

---

## 12. Verdict rationale (post-patch only)

Product tip `befb14e` delivered the intended quoter bound: when Alchemy is actually hit after a primary failover, POSTs cluster at **≤2**, and host cooldown suppresses the vast majority of failover storms (M2 naive ≪ 2). SHADOW safety and ≥12h continuity are solid.

However, persistent Network Config still injects stale Alchemy secondary **`ce00e63d`**, which absorbed **all** campaign 429s; public Base soft rate-limits continue to initiate failovers; and the economic layer produced **zero** opportunities / EXECUTABLE / paper evidence. Those are **infrastructure and market/opportunity** blockers, not a reappearance of the ~5× retry amplifier.

Therefore the honest post-patch verdict is **CONDITIONAL**, not PASS and not FAIL.

**Next operator action (out of scope for this read-only close):** separate GO required before any Network Config APPLY, further deploy, mode promotion, or official Gate 9 start.
