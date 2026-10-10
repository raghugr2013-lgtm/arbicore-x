# Post-8h / 12h SHADOW Validation Package (Workstream A prepare-only)

- **Status:** PREPARE ONLY — **does not execute deploy**, does **not** restart Gate9, does **not** alter the current SHADOW campaign
- **Date (UTC authored):** 2026-10-02
- **Workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Production (read-only grounding):** `/home/raghu/projects/arbicore-x-v2`
- **Live Gate9 container:** `arbicore-x-backend-new`
- **Live Gate9 image (rollback target):** `arbicore-x-backend:g5.79-green-20260927`
- **Kind:** Post-patch SHADOW validation package — **NOT official Gate 9** — **NOT Gate 10**
- **Official Gate 9:** still **≥24h** continuous (unchanged; earliest `2026-10-03T06:19:43Z`)
- **Official Gate 10:** still **≥72h** continuous (unchanged)
- **Companion report template:** `docs/certification/POST_PATCH_12H_SHADOW_REPORT_TEMPLATE_20261002.md`
- **Workstream A cert:** `docs/certification/WORKSTREAM_A_QUOTER_429_BEFB14E_INDEPENDENT_CERT_20261002.md` §13 — tip `befb14e6aa77515daa038e142ff978822a4fab91` product-PASS; tip+fixture-followup `57f5365` → 33/33; deploy recommendation **READY WITH CONDITIONS** (residual fixture-only; Gate9 frozen)

---

## HARD RULES (this package)

1. **Do not deploy / restart / reconfigure / re-key Gate9 now.**
2. Current Gate9 SHADOW campaign **must continue untouched** until the **accelerated 8h checkpoint** is captured (`≥ 2026-10-02T14:19:43Z`).
3. This package **prepares** the later post-8h baseline capture + (separate window) deploy + 12h post-patch run.
4. The 12h post-patch run is **post-patch validation**, **not** official Gate 9 / Gate 10.
5. **Deploy recommendation (Workstream A §13):** **READY WITH CONDITIONS** — deploy product tip `befb14e` for the 429 amplification fix; land fixture hygiene `57f5365` (or equivalent) for CI co-run gate. Gate9 remains frozen until campaign owner authorizes cutover (§9).
6. Never print Alchemy `/v2/<secret>` path segments; redact to host + optional fp8 only.
7. Preserve cert workspace dirty tree; do not `git reset` / `clean`.

---

## 0. Live continuity baseline (read-only verify at package authoring)

| Field | Expected / observed 2026-10-02 (package authoring) |
|---|---|
| Container | `arbicore-x-backend-new` |
| Status / Health | `running` / `healthy` |
| `StartedAt` | `2026-10-02T06:19:33.513948555Z` |
| `RestartCount` | **0** |
| Image | `arbicore-x-backend:g5.79-green-20260927` |
| Compose working dir | `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose` |
| Compose files | `docker-compose.prod.yml` + `/tmp/arbicore-g579-prod-override.yml` |
| Paper runner `started_at` | `2026-10-02T06:19:43.018995+00:00` |
| 8h accelerated ETA | `2026-10-02T14:19:43Z` |
| Official Gate 9 ETA | `2026-10-03T06:19:43Z` |
| Mode | `ARBICORE_EXECUTION_MODE=SHADOW` |
| AUTOEXEC / RUNTIME | both `false` |
| Paper validation | `ARBICORE_PAPER_VALIDATION_ENABLED=true` |

**Re-verify ContinuityAtStamp before every package phase** with:

```bash
docker inspect arbicore-x-backend-new --format \
  'Status={{.State.Status}} Health={{if .State.Health}}{{.State.Health.Status}}{{end}} RestartCount={{.RestartCount}} StartedAt={{.State.StartedAt}} Image={{.Config.Image}}'
```

Any `RestartCount > 0` or `StartedAt` change vs campaign start **breaks** Gate9 continuity claims for the original campaign window (document honestly; do not invent unbroken duration).

---

## 1. Precise 12h post-patch SHADOW validation runbook

### 1.1 Timeline (do not compress)

| Phase | When | Action | Touches Gate9? |
|---|---|---|---|
| **P0 — Package ready** | Now | This document + report template | **No** (read-only inspect only) |
| **P1 — Accelerated 8h checkpoint** | ≥ `2026-10-02T14:19:43Z` | Fill `SHADOW_ACCELERATED_8H_CHECKPOINT_*` per template; leave campaign running | **Read-only collect only** |
| **P2 — 8h baseline freeze for before/after** | Immediately after P1 artifacts written | Capture metric snapshot as **8h baseline (pre-patch)** into `reports/shadow_validation/post_patch_baseline_8h_<TS>Z.json` | **Read-only** |
| **P3 — Optional official Gate 9** | ≥ `2026-10-03T06:19:43Z` | Separate official Gate9 stamp per `GATE9_EVIDENCE_CHECKLIST_*` | **Read-only** (prefer complete Gate9 before deploy) |
| **P4 — Deploy gate check** | Post-P1 (prefer after P3) | Confirm Workstream A §13 **READY WITH CONDITIONS** (or tip+fixture **READY**); operator GO; Gate9 still frozen until GO | Still **no** deploy until GO |
| **P5 — Deploy Workstream A** | Separate change window **after** P1 (+ prefer P3) | Build/tag/activate `befb14e` image per §9 | **Yes** — ends original Gate9 continuity |
| **P6 — Post-patch 12h SHADOW** | Continuous ≥12.0 h after post-deploy runner healthy | Collect APIs + logs; fill report template | Observe new campaign only |
| **P7 — Compare + verdict** | After ≥12h | Before/after schema (§2); fill `POST_PATCH_12H_*` report | Read-only |

> **STOP at P0–P2 for this prepare task.** P4–P7 are documented for later operators — **not executed by this package**.

### 1.2 P1 — Capture accelerated 8h checkpoint (campaign continues)

Follow `docs/certification/SHADOW_ACCELERATED_8H_CHECKPOINT_TEMPLATE_20261002.md` and APIs in `GATE9_EVIDENCE_CHECKLIST_20261002.md` §A–E.

Allowed verdicts only: `HEALTHY` | `HEALTHY WITH OBSERVATIONS` | `BLOCKED` — **never** “Gate 9 PASS”.

Artifacts:

- `docs/certification/SHADOW_ACCELERATED_8H_CHECKPOINT_20261002.md`
- `reports/shadow_validation/accel_8h_checkpoint_<TS>Z.json`
- Optional: `accel_8h_checkpoint_api_raw_<TS>Z.json`, `accel_8h_checkpoint_latest.json`

### 1.3 P2 — Freeze 8h baseline for post-patch comparison

Immediately after P1, write a **comparison baseline** (may reuse P1 JSON fields; stamp distinctly):

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
# After collecting APIs + docker inspect + redacted log metrics into the JSON schema (§2),
# write:
# reports/shadow_validation/post_patch_baseline_8h_${TS}.json
# docs/certification/POST_PATCH_BASELINE_8H_${TS}.md   # optional human summary
```

Baseline label in schema: `"arm": "pre_patch_8h_gate9_image"`, `"image": "arbicore-x-backend:g5.79-green-20260927"`.

### 1.4 P5–P6 — Later deploy + 12h (execute only after GO)

1. Complete §9 deployment checklist (pre-flight → build → activate → safety re-check).
2. Record new `StartedAt`, set `RestartCount` expectation to **0** for the **new** post-patch campaign.
3. Run SHADOW continuously **≥12.0 hours** with AUTOEXEC/RUNTIME off.
4. At end: collect same schema as baseline (`"arm": "post_patch_12h"`).
5. Fill `docs/certification/POST_PATCH_12H_SHADOW_REPORT_TEMPLATE_20261002.md` → stamped final report.
6. Machine: `reports/shadow_validation/post_patch_12h_<TS>Z.json`.

### 1.5 Explicit non-goals of the 12h window

- Not a substitute for official Gate 9 (24h) or Gate 10 (72h)
- Not LIMITED_LIVE / Recommendation / signing / broadcast enablement
- Not capability-matrix reclassification
- Not CU dashboard reconciliation unless separately tasked

---

## 2. Before/after metric schema

### 2.1 Arms

| Arm ID | Window | Image / tip | Duration bar |
|---|---|---|---|
| `pre_patch_8h_gate9_image` | Current Gate9 campaign through ≥8h stamp | `g5.79-green-20260927` | ≥8.0 h elapsed from runner start |
| `post_patch_12h` | New campaign after Workstream A deploy | tip `befb14e…` (or certified successor PASS tip) | ≥12.0 h continuous post-deploy |

### 2.2 Common JSON envelope

```json
{
  "cert": "POST_PATCH_SHADOW_COMPARE",
  "not_official_gate9": true,
  "not_official_gate10": true,
  "arm": "pre_patch_8h_gate9_image | post_patch_12h",
  "ts": "<YYYYMMDDTHHMMSSZ>",
  "collected_at": "<ISO-UTC>",
  "window": {
    "start_utc": "<ISO>",
    "end_utc": "<ISO>",
    "hours": null,
    "warm_up_discard_minutes": 0
  },
  "container": {
    "name": "arbicore-x-backend-new",
    "status": null,
    "health": null,
    "started_at": null,
    "restart_count": null,
    "image": null
  },
  "git_or_tip": null,
  "safety": {},
  "rpc": {},
  "quotes": {},
  "opportunities": {},
  "six_chain": {},
  "infra": {},
  "pnl": {
    "method": "A=0 / EXECUTABLE=0 => PnL=$0 drawdown=$0",
    "paper_pnl_usd": null,
    "max_drawdown_usd": null
  },
  "derived": {},
  "evidence_gaps": [],
  "STOP": "Secrets redacted; no invented EXECUTABLE fills"
}
```

### 2.3 Comparison formulas (fill in final report)

| ID | Metric | Formula / rule |
|---|---|---|
| ΔM2 | Alchemy POSTs / Base→Alchemy failover | `M2_post - M2_pre`; **PASS target post ≤ 2.0** (pre ≈ 4.5–5.5 on Gate9 image) |
| ΔM3 | Alchemy HTTP 429 / hour | `(M3_pre - M3_post) / M3_pre` if `M3_pre > 0`; target ≥ **70%** reduction **or** `M3_post ≤ 0.3 × M3_pre` |
| ΔM7 | Cooldown activations / hour | post should be **> 0** if sustained 429s present; pre expected **0** (no cooldown in Gate9 image) |
| Quote honesty | ok vs fallback | Fail-closed: rate-limit/cooldown must remain **non-ok**; no ok-rate inflation |
| Continuity | restart / StartedAt | pre: RestartCount=0 & StartedAt fixed; post: new StartedAt, RestartCount=0 for **its** 12h window |
| PnL | paper | EXECUTABLE=0 ⇒ PnL=$0 / DD=$0 honest on both arms |

Normalize count metrics to **/hour** using `window.hours` (exclude documented warm-up if used).

### 2.4 Collection commands (both arms; redact secrets)

**Docker / continuity**

```bash
docker inspect arbicore-x-backend-new --format \
  '{{json .State}}' | python3 -c 'import json,sys; s=json.load(sys.stdin); print({k:s.get(k) for k in ("Status","StartedAt","FinishedAt","Health")})'
docker inspect arbicore-x-backend-new --format 'RestartCount={{.RestartCount}} Image={{.Config.Image}}'
```

**Env safety (redact values that look like keys)**

```bash
docker inspect arbicore-x-backend-new --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^ARBICORE_(EXECUTION_MODE|SHADOW_CERT_ENABLED|AUTOEXEC_AUTOSTART|RUNTIME_AUTOSTART|SCANNER_AUTOSTART|PAPER_VALIDATION_ENABLED|PRICE_FEED|BORROW)=' 
```

**API set** (session auth via admin env; **do not persist cookies/secrets** in reports) — same as Gate9 checklist:

| Endpoint | Purpose |
|---|---|
| `GET /api/arbicore/validation/metrics` | runner continuity + opportunity counters |
| `GET /api/arbicore/validation/report` | paper histogram |
| `GET /api/arbicore/validation/evidence?limit=…` | evidence totals |
| `GET /api/arbicore/validation/daily_status` | daily run continuity |
| `GET /api/arbicore/paper/stats` | paper engine stats |
| `GET /api/arbicore/dashboard/pulse` | pulse + paper_validation + safety counters |
| `GET /api/arbicore/safety/status` | kill / live_execution |

**Log metrics (redacted capture)**

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT=reports/shadow_validation/post_patch_logs_${ARM}_${TS}.log
# Prefer --since aligned to window.start_utc (example: 8h / 12h)
docker logs --since 8h arbicore-x-backend-new 2>&1 \
  | sed -E 's#(g\.alchemy\.com/v2/)[^"[:space:]]+#\1REDACTED#g' \
  > "$OUT"
```

Parse with `scripts/measure_base_failover_logs.py` **only** for throwaway/isolated arms historically; for Gate9/post-patch **live** campaign, either:

- parse the **already-exported** `$OUT` file offline (script `--log-file`), or
- use the grep recipes in §3 (script deny-lists Gate9 container name for `--container` mode).

```bash
python3 scripts/measure_base_failover_logs.py \
  --log-file "$OUT" \
  --arm "$ARM" \
  --window-minutes 480 \
  --out "reports/shadow_validation/failover_metrics_${ARM}_${TS}.json"
```

---

## 3. RPC / provider metrics

| ID | Field | Unit | Source / grep |
|---|---|---|---|
| M1 | Base→Alchemy failover events | count (/h) | `quoter: hop .* failing over from mainnet.base.org to base-mainnet.g.alchemy.com` |
| M2 | Alchemy requests / failover | ratio | Alchemy Base POSTs ÷ M1 |
| M3 | Alchemy HTTP 429 | count (/h) | `HTTP Request: POST https://base-mainnet.g.alchemy.com/` + `"HTTP/1.1 429` |
| M3b | Alchemy HTTP 200 | count (/h) | same host + `"HTTP/1.1 200` |
| M3c | Public Base HTTP 429 | count (/h) | `POST https://mainnet.base.org` + 429 |
| M3d | Public Base HTTP 200 | count (/h) | `mainnet.base.org` + 200 |
| M4 | Soft primary RL (−32016) failovers | count | failover lines with `err=code=-32016` |
| M6 | Avg / peak Alchemy req rate | req/s | 10s avg / 1s peak bins on Alchemy Base POSTs |
| M7 | Host cooldown activations | count (/h) | log text `host cooldown` (post-patch expected; pre-patch Gate9 ≈ 0) |
| M9 | Retries implied | derived | pre-patch ≈ **5** POSTs/failover (observed **5.025**); post-patch target **≤2** |
| M10 | Fail-closed all-rate-limited | count | quote/hop outcomes `fallback:break_even` under sustained 429 (honest non-ok) |
| M11 | Timeouts / transport errors | count | httpx timeout / connect errors on RPC hosts (document pattern if present) |
| M12 | Successful RPC calls | count | HTTP 200 POSTs per host (not equal to economic success) |

**Grounded pre-patch expectation (Gate9 image):** Alchemy POSTs/failover ≈ **5** (`BASE_ALCHEMY_429_ROOT_CAUSE_20261002.md`); live logs still show multi-POST 429 bursts after Base `-32016` failover.

**Post-patch expectation (`befb14e` `_eth_call`):** `ARBICORE_RPC_MAX_RETRIES_429` default **1** → ≤**2** POSTs on 429; `ARBICORE_RPC_RATE_LIMIT_COOLDOWN_S` default **60**; cooldown gate returns fail-fast (no POST).

Optional host list for six Alchemy domains + Base public:

```
eth-mainnet.g.alchemy.com
arb-mainnet.g.alchemy.com
opt-mainnet.g.alchemy.com
polygon-mainnet.g.alchemy.com
bnb-mainnet.g.alchemy.com
base-mainnet.g.alchemy.com
mainnet.base.org
```

---

## 4. Quote metrics

| Field | Unit | How to collect |
|---|---|---|
| Successful quotes (`status=ok`) | count (/h) | App counters if exposed; else hop/route logs / validation proxies — **label source** |
| Failed / non-ok quotes | count (/h) | `fallback:*`, revert, rate-limit, cooldown |
| `fallback:break_even` | count (/h) | Explicit fail-closed economic placeholder (must **not** count as ok) |
| `fallback:revert` / other fallbacks | count (/h) | Log `status=fallback:…` on quoter failover / hop errors |
| Quote latency | ms p50/p95 if available | Prefer API/metrics histogram; else omit with `evidence_gaps` |
| Provider usage mix | % or counts by host | POSTs by host from httpx lines; optional fp8 `5e5d5bb1` for Alchemy key identity (never print secret) |
| Amplification honesty | ratio | M2; post must not “succeed” by fabricating ok quotes under RL |

Integrity rule: cooldown / 429 / all-rate-limited paths remain **non-ok**. PASS on Alchemy volume with inflated ok rates = automatic **FAIL**.

---

## 5. Opportunity / economic metrics

### 5.1 Paper validation histogram

From `GET /api/arbicore/validation/report`:

| Field | Notes |
|---|---|
| `total` | May be 0 — honest |
| `histogram.EXECUTABLE` | Spot-check evidence IDs if >0 |
| `histogram.REJECTED` | + other buckets: `UNPROFITABLE`, `LIQUIDITY_FAILURE`, `GAS_FAILURE`, `ROUTE_FAILURE`, `RISK_FAILURE`, `SIMULATION_FAILURE` |
| `executable_rate` | Record as-is |

From `GET /api/arbicore/validation/metrics` runner:

| Field | Notes |
|---|---|
| `opportunities_seen` / `processed` / `skipped_dup` | Detection vs processed |
| `outcome_counts` | If present |
| `cycles_completed` / `exceptions` / `last_error` | Continuity |

### 5.2 A / B / C / E economic buckets

Prefer live paper outcomes when present. If thin, **reuse M6** with explicit source label (do not invent):

| Bucket | Meaning | Pre-patch M6 reference |
|---|---|---|
| **A** | Real profitable (Gate 7 $25) | 0 (`m6_post_alchemy_reset_latest.json`) |
| **B** | Real economically rejected | 10 |
| **C** | Quote failures | 8 |
| **D** | Liquidity failures | 0 |
| **E** | Gas failures | 14 |

PnL method (canonical): `paper_pnl_usd = Σ net_profit_usd` over `outcome=EXECUTABLE`; if EXECUTABLE=0 ⇒ **0.00** / DD **0.00**.

### 5.3 Rejection reasons to capture

- Paper histogram reject buckets (names above)
- Gate 7 floor **$25.00** (reject $24.99 / accept $25.00) — confirm still in force
- Gate 8 TVL floor **$100,000** fail-closed on unverifiable TVL
- H05 price-feed / borrow-sizer **OFF**
- Quoter fail-closed: `fallback:break_even` under all-rate-limited

---

## 6. Six-chain coverage evidence

Chains (capability matrix / Gate9 checklist): `ethereum`, `arbitrum`, `optimism`, `polygon`, `bnb`, `base`.

### 6.1 Required probe table (both arms at stamp)

| Chain | Expected host (Gate9 env shape) | Collect |
|---|---|---|
| ethereum | `eth-mainnet.g.alchemy.com` | `eth_chainId` + `eth_blockNumber` ok/fail; any 429 |
| arbitrum | `arb-mainnet.g.alchemy.com` | same |
| optimism | `opt-mainnet.g.alchemy.com` | same |
| polygon | `polygon-mainnet.g.alchemy.com` | same |
| bnb | `bnb-mainnet.g.alchemy.com` | same |
| base | `mainnet.base.org` (primary); Alchemy Base secondary | same + failover notes |

Env grounding (redacted): `ARBICORE_RPC_URL_ETHEREUM|ARBITRUM|OPTIMISM|POLYGON|BNB`, `ARBICORE_RPC_URL_BASE=https://mainnet.base.org`, `ARBICORE_RPC_URL` → Alchemy Base.

### 6.2 Evidence that “all six covered”

Minimum for package PASS on coverage:

1. Probe table: **6/6** `eth_chainId`+`eth_blockNumber` success at stamp (or honest failure documented).
2. Log or metrics showing quote/scan activity is not single-chain-only (if opportunity journal thin, state gap honestly).
3. Optional: Mongo `evidence_bundles` / opportunity journal counts by chain if available — **do not invent**.

Balancer notes: reuse M6 P0/P1/P1b unless re-probed; do not restart campaign to “fix” Balancer.

---

## 7. Safety evidence checklist

| Control | Required | Exact check |
|---|---|---|
| SHADOW ON | `ARBICORE_EXECUTION_MODE=SHADOW` | `docker inspect … Env` grep |
| Shadow cert | `ARBICORE_SHADOW_CERT_ENABLED=true` | Env |
| AUTOEXEC OFF | `ARBICORE_AUTOEXEC_AUTOSTART=false` | Env |
| RUNTIME OFF | `ARBICORE_RUNTIME_AUTOSTART=false` | Env |
| Scanner | `ARBICORE_SCANNER_AUTOSTART=true` (campaign posture) | Env |
| Paper runner | `ARBICORE_PAPER_VALIDATION_ENABLED=true` | Env |
| Live execution | `live_execution_enabled=false` | `GET /api/arbicore/safety/status` |
| Kill engaged | `effective_kill_engaged=true` (typical `boot_default`) | safety/status + pulse |
| Signing | **0** / not reached | pulse / safety counters `signing_reached=false` |
| Broadcast | **0** | pulse / pipeline; no LIMITED_LIVE promotion |
| Funds movement | **0** | pulse / safety `funds_moved=0` |
| H05 | price-feed / borrow-sizer **UNSET/OFF** | Env absence or false |
| Gate 7 / 8 | $25 / $100k fail-closed unchanged | M6 reuse or in-image confirm — label source |

Log greps (expect **no** live submit):

```bash
docker logs --since 12h arbicore-x-backend-new 2>&1 \
  | grep -EEi 'broadcast|submitTransaction|signing_reached|LIMITED_LIVE|FULL_LIVE' \
  | sed -E 's#(g\.alchemy\.com/v2/)[^"[:space:]]+#\1REDACTED#g' \
  | head
```

Any signing/broadcast/funds >0 ⇒ **FAIL** safety for this package.

---

## 8. Infrastructure continuity

| Check | Pre-patch 8h baseline | Post-patch 12h |
|---|---|---|
| Container name | `arbicore-x-backend-new` | same name expected after recreate |
| `RestartCount` | **0** vs campaign start | **0** for post-deploy window (any mid-window restart = continuity break for **that** 12h claim) |
| `StartedAt` continuity | Must equal `2026-10-02T06:19:33.513948555Z` until deliberate post-8h deploy | **New** StartedAt recorded at deploy; freeze that as post-patch T0 |
| Health | `healthy` | `healthy` throughout |
| Image | `arbicore-x-backend:g5.79-green-20260927` | Workstream A image tag (record exact tag/digest) |
| Compose | `docker-compose.prod.yml` + `/tmp/arbicore-g579-prod-override.yml` | Document override change if image tag swapped |
| Runner | `is_running=true`; cycles advancing; exceptions tracked | same |

```bash
# Continuity one-liner (record into JSON)
docker inspect arbicore-x-backend-new --format \
  'RestartCount={{.RestartCount}} StartedAt={{.State.StartedAt}} Health={{.State.Health.Status}} Image={{.Config.Image}}'
```

---

## 9. Exact deployment checklist — Workstream A (`befb14e`) — **post-8h only / no execute now**

### 9.1 Deploy gate (mandatory)

| Gate | Requirement |
|---|---|
| G0 | Accelerated **8h checkpoint captured** and campaign notes frozen (P1/P2) |
| G1 | Prefer official Gate 9 (≥24h) stamped **or** explicit operator waiver that 12h post-patch proceeds without waiting for Gate9 official |
| G2 | Workstream A cert tip `befb14e6aa77515daa038e142ff978822a4fab91` (product) |
| G3 | Authoritative artifact: `artifacts/workstream-a-quoter-429-befb14e-selfcontained.bundle` (SHA256 `b7f3952e29a5664bb6c7a144e7a76c9df7ba207b3f2ee6a430bb84a3a4dff964`, **8199151** bytes) |
| G4 | **Deploy recommendation (Workstream A §13):** **READY WITH CONDITIONS** — residual resolved as **fixture-only**; tip product-PASS; tip+fixture-followup `57f5365` → 33/33 **PASS** / **READY** for combined tree |
| G5 | Safety posture file ready: SHADOW on, AUTOEXEC/RUNTIME false (do not flip live) |
| G6 | Rollback image present locally: `arbicore-x-backend:g5.79-green-20260927` (§10) |
| G7 | Gate9 campaign remains **frozen** until separate campaign-owner authorize (no restart/image swap in this prepare package) |

**§13 residual resolution (supersedes §12 CONDITIONAL gate-only wording):**

> Amplification fix on QuoterRegistry `_eth_call` path is independently certified GREEN (RED→GREEN ≤2 POSTs, cooldown, failover, fail-closed). Prior co-run **CONDITIONAL** on `test_quoter_scoped_throttle.py` is **fixture-only** (module-level `_RPC_HOST_COOLDOWN_UNTIL` leak; tip-as-shipped co-run 10/11). Fixture follow-up `57f53651d8c7638d0a5f3d2cd8eb2c083fd97f44` restores scoped_throttle 11/11 and full relevant suites **33/33 PASS**.

**Authoritative deploy recommendation (exact — Workstream A §13.6):**

```text
READY WITH CONDITIONS — safe to deploy the quoter `_eth_call` 429 bound+cooldown for the measured
amplification bug; land fixture follow-up `57f5365` (or equivalent) before treating scoped_throttle
co-run as a hard merge gate. Gate9 campaign remains untouched / NOT READY to modify until campaign
owner authorizes.
```

**Combined-tree alternate (tip + fixture `57f5365`):** **READY** for that combined tree — still do not restart/deploy into the frozen Gate9 campaign without a separate campaign decision.

Without G4 **READY WITH CONDITIONS** (product tip) or tip+fixture **READY**, plus operator GO → **NO-GO deploy**.

### 9.2 Pre-deploy inventory (read-only)

```bash
# Bundle integrity
sha256sum artifacts/workstream-a-quoter-429-befb14e-selfcontained.bundle
# Expected: b7f3952e29a5664bb6c7a144e7a76c9df7ba207b3f2ee6a430bb84a3a4dff964

# Gate9 still on certified runtime (must match until you deliberately cut over)
docker inspect arbicore-x-backend-new --format \
  'RestartCount={{.RestartCount}} StartedAt={{.State.StartedAt}} Image={{.Config.Image}}'

# Rollback image available
docker image inspect arbicore-x-backend:g5.79-green-20260927 --format '{{.Id}} {{.RepoTags}}'
```

### 9.3 Build path (later — outline only)

1. Import self-contained bundle into a **throwaway** git dir (not Gate9; not dirty cert tree as deploy source of truth unless operator chooses).
2. Verify tip `befb14e…` + tree `fdd6f799…`.
3. Build backend image tagged e.g. `arbicore-x-backend:ws-a-befb14e-20261002` from tip `app/backend` context (same Dockerfile path as prod compose).
4. **Do not** retag over `g5.79-green-20260927` (preserve rollback tag immutably).
5. Prepare compose override that sets `image: arbicore-x-backend:ws-a-befb14e-20261002` **and** keeps SHADOW / AUTOEXEC=false / RUNTIME=false (mirror `/tmp/arbicore-g579-prod-override.yml` safety block).
6. Record override path + image digest in the 12h report.

### 9.4 Activate (later — outline only)

Working dir: `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose`

```bash
# ILLUSTRATIVE — do NOT run during prepare / during pre-8h Gate9 window
# cd /home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose
# docker compose -f docker-compose.prod.yml -f <POST_PATCH_OVERRIDE.yml> up -d backend
```

Post-activate immediate checks:

- New `StartedAt`; `RestartCount=0`; health=healthy
- Env: SHADOW / AUTOEXEC false / RUNTIME false
- Safety API: live_execution false; kill engaged; signing/broadcast/funds 0
- Quoter path shows cooldown / ≤2 POST behaviour under Base→Alchemy failover (log sample)

### 9.5 Forbidden during deploy window

- Enabling AUTOEXEC / RUNTIME / LIMITED_LIVE / signing / broadcast
- Changing Gate 7/8 thresholds
- Hot-mounting dirty cert `quoter.py` into Gate9 without an image build
- Deploying the **thin** bundle (`…befb14e.bundle` / 45892 bytes) — use **self-contained** only
- Claiming the 12h result is official Gate 9

---

## 10. Exact rollback procedure → `g5.79-green-20260927` / current Gate9 certified runtime

**Goal:** restore backend to image `arbicore-x-backend:g5.79-green-20260927` with the same safety posture as the Gate9 freeze.

### 10.1 Preconditions

```bash
docker image inspect arbicore-x-backend:g5.79-green-20260927 --format '{{.Id}}'
# Override file that pinned Gate9 (authoritative at campaign freeze):
# /tmp/arbicore-g579-prod-override.yml
#   image: arbicore-x-backend:g5.79-green-20260927
#   ARBICORE_EXECUTION_MODE=SHADOW
#   ARBICORE_AUTOEXEC_AUTOSTART=false
#   ARBICORE_RUNTIME_AUTOSTART=false
#   ARBICORE_SCANNER_AUTOSTART=true
#   ARBICORE_SHADOW_CERT_ENABLED=true
```

Compose project labels observed on live container:

- Project working dir: `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose`
- Config: `docker-compose.prod.yml` + `/tmp/arbicore-g579-prod-override.yml`
- Service: `backend` · container_name: `arbicore-x-backend-new`

### 10.2 Rollback steps (later — only if post-patch must be reverted)

1. Freeze evidence: export current logs/API snapshot **before** cutback (redacted).
2. Ensure override points at `arbicore-x-backend:g5.79-green-20260927` (restore `/tmp/arbicore-g579-prod-override.yml` content or equivalent).
3. Recreate backend only:

```bash
# ILLUSTRATIVE — execute only for real rollback
cd /home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose
docker compose -f docker-compose.prod.yml -f /tmp/arbicore-g579-prod-override.yml up -d backend
```

4. Verify:

```bash
docker inspect arbicore-x-backend-new --format \
  'Image={{.Config.Image}} RestartCount={{.RestartCount}} StartedAt={{.State.StartedAt}} Health={{.State.Health.Status}}'
docker inspect arbicore-x-backend-new --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E 'ARBICORE_(EXECUTION_MODE|AUTOEXEC_AUTOSTART|RUNTIME_AUTOSTART|SHADOW_CERT_ENABLED)='
```

Expect: Image `…:g5.79-green-20260927`; SHADOW; AUTOEXEC/RUNTIME false; healthy.

5. Re-check safety API + signing/broadcast/funds = 0.
6. Document that **post-patch 12h continuity is voided** by rollback; start a new observation window if still validating.

### 10.3 Rollback PASS criteria

| Check | Required |
|---|---|
| Image | `arbicore-x-backend:g5.79-green-20260927` |
| SHADOW / AUTOEXEC / RUNTIME | ON / OFF / OFF |
| Signing / broadcast / funds | 0 / 0 / 0 |
| Health | healthy |
| Note | New StartedAt expected; do not claim pre-rollback duration |

---

## 11. Final 12h report

Use: `docs/certification/POST_PATCH_12H_SHADOW_REPORT_TEMPLATE_20261002.md`

Label on every page / JSON:

> **POST-PATCH VALIDATION — NOT OFFICIAL GATE 9 — NOT GATE 10**

Machine artifact pattern:

- `reports/shadow_validation/post_patch_12h_<TS>Z.json`
- `reports/shadow_validation/post_patch_12h_latest.json` (optional pointer)
- Baseline: `reports/shadow_validation/post_patch_baseline_8h_<TS>Z.json`

Allowed verdicts for 12h post-patch package: `PASS` | `CONDITIONAL` | `FAIL` / `BLOCKED` — scoped to **post-patch validation criteria** (M2≤2, 429 reduction, safety, continuity of the **new** 12h window, fail-closed honesty). Never relabel as Gate 9 PASS.

---

## 12. Artifact / reference map

| Doc / artifact | Role |
|---|---|
| This file | Coherent prepare package (runbook + schema + checklists) |
| `POST_PATCH_12H_SHADOW_REPORT_TEMPLATE_20261002.md` | Final report template |
| `SHADOW_ACCELERATED_8H_CHECKPOINT_TEMPLATE_20261002.md` | P1 8h confidence |
| `GATE9_EVIDENCE_CHECKLIST_20261002.md` | Official Gate9 API field list |
| `WORKSTREAM_A_QUOTER_429_BEFB14E_INDEPENDENT_CERT_20261002.md` | Deploy gate / tip / §13 **READY WITH CONDITIONS** (fixture residual resolved) |
| `BASE_ALCHEMY_429_ROOT_CAUSE_20261002.md` | Pre-patch M2≈5.025 |
| `BASE_FAILOVER_FIX_VALIDATION_PROCEDURE_20261002.md` | Isolated A/B metric IDs |
| `PAPER_GATE9_10_VALIDATION_20261002.md` | Paper/safety field precedents |
| `ARBITRAGE_CAPABILITY_MATRIX_AUDIT_20261002.md` | Six-chain scope |
| `scripts/measure_base_failover_logs.py` | Offline log parse (Gate9 `--container` denied) |
| `artifacts/workstream-a-quoter-429-befb14e-selfcontained.bundle` | Deployable tip source |

---

## 13. Package authoring freeze confirmation

| Check | Result |
|---|---|
| Gate9 restarted / redeployed / env changed by this package? | **No** |
| Credentials modified? | **No** |
| Production source `/home/raghu/projects/arbicore-x-v2` modified? | **No** |
| Cert dirty tree reset/cleaned? | **No** |
| Continuity at authoring | `StartedAt=2026-10-02T06:19:33.513948555Z`, `RestartCount=0`, image `g5.79-green-20260927` |
| Deploy executed? | **No** — prepare only |
