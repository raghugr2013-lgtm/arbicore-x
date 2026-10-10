# Alchemy ↔ POST-FIX SHADOW Correlation Audit (READ ONLY) — 2026-10-02

- **Status:** READ ONLY — no restart, redeploy, config/credential change, Gate9 interference, or container modify
- **Audit UTC:** ~`2026-10-02T15:26Z` (campaign elapsed ~**17 min** since T0)
- **Container:** `arbicore-x-backend-new`
- **Campaign:** `docs/certification/POST_FIX_12H_SHADOW_CAMPAIGN_IN_PROGRESS_20261002.md`
- **PRE-FIX freeze:** `docs/certification/PRE_FIX_8H_BASELINE_FREEZE_20261002.md`
- **Operator dashboard (as stated; not re-fetched):** 525 req/24h · 0 avg CU/s / 5m · 97.1% success / 1h · 88.2% success / 24h · 0 concurrent · 0% throughput limited

---

## Identity / T0 (verified)

| Field | Observed |
|---|---|
| StartedAt | **`2026-10-02T15:08:52.884157323Z`** (matches campaign T0) |
| Image | `arbicore-x-backend:ws-a-befb14e-20261002` |
| Image Id | **`sha256:12759b11a783619ad25746a030c5bbcc71b83ed64ff05b3316153d6402a594ae`** |
| `ARBICORE_GIT_SHA` / `BUILD_INFO.json` | **`befb14e6aa77515daa038e142ff978822a4fab91`** |
| Label `arbicore.gitsha` | `2a6fadb8…` (base label; **not** product tip — tip is env/`BUILD_INFO`) |
| RestartCount | **0** · Health **healthy** · Status **running** |
| Alchemy key path `sha256[:8]` (all wired `*/v2/` URLs + `.env`) | **`5e5d5bb1`** (match) |
| Base primary | `mainnet.base.org` (not Alchemy) |
| Fix in image | `/app/arbicore/execution/quoter.py` has `_RPC_MAX_RETRIES_429` + `_RPC_HOST_COOLDOWN_UNTIL` |

---

## 1. Did post-fix container hit Alchemy fp `5e5d5bb1`?

**YES.**

- Env + `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env` (read-only): unique Alchemy fp **`5e5d5bb1`**.
- Logs since T0: httpx `POST https://base-mainnet.g.alchemy.com/v2/<REDACTED>` present from **`2026-10-02T15:09:01Z`** onward.
- No other `*.alchemy.com` hosts appeared in this window.

---

## 2. Alchemy requests during POST-FIX only (T0→audit)

| Metric | Count |
|---|---:|
| Alchemy POSTs (`base-mainnet.g.alchemy.com`) | **38** |
| HTTP 200 | **13** |
| HTTP 429 | **24** |
| HTTP 400 | **1** |
| Other Alchemy chains | **0** |
| Approx rate | **~2.2 req/min** overall; after ~15:09 burst, **~2 POSTs / ~1–2 min** (cooldown cadence) |
| Last 5m (at audit) | **6** Alchemy (all **429**) |

Public Base (not Alchemy): `mainnet.base.org` **233** (217×200, 16×429).

---

## 3. App-side signals since T0

| Signal | Evidence |
|---|---|
| Base→Alchemy quoter failover log lines | **327** total |
| Primary (`over rate limit`) | **9** |
| Cooldown-gated (`HTTP 429 host cooldown…`) | **318** (fail-fast; **no** Alchemy POST expected) |
| Alchemy POSTs / primary failover | **~4.2** naive (includes startup burst); **7/8** primaries in early window showed **exactly 2** POSTs in a 3s window |
| HTTP 429 (Alchemy) | **24** |
| Other RPC errors (logged httpx) | Alchemy **1×400**; base.org **16×429** |
| `eth_call` log mentions | **13** (mostly provider-registry warnings; not a full eth_call census — LOG_LEVEL limits) |
| Successful quotes (`status=ok`) | **0** observed in quoter status lines |
| Failed / fallback quotes | **327× `fallback:revert`** |
| Host cooldown activations | **Active** — first cooldown failovers at **`15:09:07Z`**; **318** cooldown messages |
| Fallback activations | Coincident with failover/revert path (**327** `fallback:revert`) |

Discovery (read-only GET): running; last_result `confirmed=0`, `rejected=1`. Paper analyses=0.

---

## 4. Dashboard “0 … last 5m” / 0 concurrent

**Not A (genuine zero Alchemy requests from this app).**

At audit, last 5m logs show **6 Alchemy POSTs (429)** and **~61** `mainnet.base.org` POSTs, with **~98** Base→Alchemy failover attempts (mostly cooldown-gated).

Best-fit with evidence:

| Option | Fit |
|---|---|
| **A** genuine zero requests | **REJECT** — 6 Alchemy + 61 base.org in last 5m |
| **B** other RPC carrying load | **PARTIAL** — majority of traffic is `mainnet.base.org`, not Alchemy |
| **C** no Base failover | **REJECT** — failovers continue; cooldown suppresses most Alchemy POSTs |
| **D** dashboard delay | **POSSIBLE** — cannot prove from server |
| **E** other | **STRONG for 0 CU/s:** requests exist but are mostly **429**; CU may not accrue on rejects. **0 concurrent** is compatible with sparse ~2 POST bursts. Prior audits: dashboard app identity vs fp `5e5d5bb1` still **operator-unverified**. |

---

## 5. POST-FIX vs frozen PRE-FIX 8h baseline (429 amplification)

| | PRE-FIX (documented live, same key fp, pre-`befb14e` image) | POST-FIX (~17 min, `befb14e`) |
|---|---|---|
| Image | `g5.79-green-20260927` | `ws-a-befb14e-20261002` |
| Alchemy POSTs / quoter failover | **~5.025** (`BASE_ALCHEMY_429_ROOT_CAUSE_20261002.md`) | **Steady-state ≤2** POSTs when Alchemy is actually hit; **318/327** failovers cooldown-gated (**~0 POST**) |
| Host cooldown | Absent on quoter path | **Present** (messages + cadence) |
| 8h freeze JSON `alchemy_429_present` | `false` on **health probes only** (not quoter amplification census) | N/A — this audit uses httpx/quoter logs |

**Conclusion:** 429 **amplification collapsed** vs PRE-FIX ~5× retry storm. Residual Alchemy 429s remain when cooldown expires (~2 POSTs), then cooldown re-arms.

---

## 6. Did old ~5 Alchemy POSTs per failover recur after `befb14e`?

**No as sustained behaviour.**

- Steady pattern after first minute: **2** Alchemy POSTs per cooldown window (matches `_RPC_MAX_RETRIES_429=1` → ≤2 attempts).
- **318/327** failover lines are cooldown short-circuits (explicitly “host cooldown”), i.e. **not** the old 5-POST last-candidate burn.
- One early multi-POST burst (~18 in 15:09, one 3s window hist max 11) is concurrent multi-hop / startup — **not** the sustained ~5.025 ratio.

---

## 7. Dashboard 24h success 88.2%

**Cannot attribute from app-side evidence alone.**

- POST-FIX window Alchemy success ≈ **13/38 ≈ 34%** over ~17 min — incompatible with explaining a **24h 88.2%** figure by itself.
- PRE-FIX same-fp storm was Alchemy-dominated **429** (prior recon: thousands of 429s) — also incompatible with high 24h success **if** the viewed dashboard app is fp `5e5d5bb1`.
- Dashboard identity vs wired fp remains **operator-unconfirmed** (see prior `ALCHEMY_IDENTITY_FINAL_20261002.md`).
- **Do not speculate** which mix of wrong-app / metric definition / pre-campaign traffic produces 88.2%.

---

## 8. Git SHA, digest, SHADOW safety posture

| Control | Observed now |
|---|---|
| Product SHA | **`befb14e6aa77515daa038e142ff978822a4fab91`** (`ARBICORE_GIT_SHA`, `BUILD_INFO.json`) |
| Image digest | **`sha256:12759b11a783619ad25746a030c5bbcc71b83ed64ff05b3316153d6402a594ae`** |
| `ARBICORE_EXECUTION_MODE` | **SHADOW** |
| `ARBICORE_AUTOEXEC_AUTOSTART` | **false** |
| `ARBICORE_RUNTIME_AUTOSTART` | **false** |
| `ARBICORE_SHADOW_CERT_ENABLED` | **true** |
| `live_execution_enabled` | **false** |
| `effective_kill_engaged` | **true** (`kill.engaged=true`, reason `boot_default`) |
| flash_loan strategy mode | **SHADOW** |

Matches cutover post record `reports/shadow_validation/ws_a_cutover_post_20261002T150827Z.json`.

---

## Verdict card

| # | Question | Conclusion |
|---|---|---|
| 1 | Requests to Alchemy fp `5e5d5bb1` in post-fix? | **YES** |
| 2 | Alchemy volume post-fix | **38** POSTs (~13/24/1 = 200/429/400); ~2.2/min |
| 3 | Failover / 429 / quotes | Failovers **327** (9 primary / 318 cooldown); Alchemy 429 **24**; quotes **0 ok / 327 revert** |
| 4 | 0 last-5m | **Not genuine zero** — prefer **E** (+ **B** partial); CU/s can be 0 while 429s fire |
| 5 | vs PRE-FIX | Amplification **down** from ~5× to ≤2 + cooldown |
| 6 | ~5 POSTs/failover after fix? | **No** (sustained) |
| 7 | 88.2% / 24h | **Cannot attribute** |
| 8 | SHA / digest / safety | **Confirmed** SHADOW / AUTOEXEC off / RUNTIME off / kill engaged |

**STOP:** No deploy/restart performed. Not Gate9 PASS. Campaign still IN_PROGRESS until ≥ `2026-10-03T03:08:52Z`.
