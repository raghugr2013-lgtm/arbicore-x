# SHADOW Accelerated Status Snapshot (pre-8h)

- **Status:** **HEALTHY WITH OBSERVATIONS**
- **Kind:** STATUS snapshot only — **NOT** an 8h accelerated confidence checkpoint — **NOT** Gate 9 PASS
- **Collected at:** `2026-10-02T08:06:58Z` (API stamp); campaign still continuous
- **Workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Runtime:** `arbicore-x-backend-new`
- **Image:** `arbicore-x-backend:g5.79-green-20260927`
- **Machine evidence:** `reports/shadow_validation/accel_status_snapshot_20261002T080658Z.json` (+ `…_latest.json`)
- **API raw:** `reports/shadow_validation/accel_checkpoint_api_raw_20261002T080658Z.json`
- **STOP:** No source/config/gate/mode changes. No PAPER/AUTOEXEC/RUNTIME/Recommendation activation. No rebuild/deploy/live tx. Campaign **not** reset/restarted.

---

## FINAL OUTPUT (binding)

| Field | Value |
|---|---|
| Campaign start (runner) | `2026-10-02T06:19:43.018995+00:00` |
| Container start | `2026-10-02T06:19:33.513948555Z` |
| Elapsed (at collection) | **≈ 1.86 h** (`span_hours` ≈ 1.79; cycles 1282; exceptions 0) |
| Next checkpoint | **8h accelerated confidence** ≈ `2026-10-02T14:19:43Z` (~6.14 h remaining) |
| Official Gate 9 | **24h continuous** — unchanged — earliest ≈ `2026-10-03T06:19:43Z` |
| Official Gate 10 | **72h continuous** — unchanged — earliest ≈ `2026-10-05T06:19:43Z` |
| Current health | **HEALTHY WITH OBSERVATIONS** |
| Blockers (safety / stop) | **None** |
| Gate 9/10 criteria relabeled? | **NO** — shorter runs must not be called Gate 9/10 PASS |

---

## 1. Campaign continuity

| Check | Result |
|---|---|
| Container | `running` / `healthy` / restart_count=**0** |
| Paper validation runner `is_running` | **true** |
| `last_cycle_at` | `2026-10-02T08:06:54.362882+00:00` (fresh) |
| Interruptions | **None observed** since runner `started_at` |
| Paper evidence total | **0** (`/validation/report.total=0`; Mongo continuity empty for paper evidence) |
| Opportunities seen/processed | **0 / 0** |
| Prior Gate 9–10 stamp | CONDITIONAL at ≈1.04h (`20261002T072116Z`) — same continuous runner |

Campaign was **not** reset for this checkpoint.

---

## 2. Safety posture (confirmed)

| Control | Value |
|---|---|
| `ARBICORE_EXECUTION_MODE` | **SHADOW** |
| `ARBICORE_SHADOW_CERT_ENABLED` | **true** |
| `ARBICORE_SCANNER_AUTOSTART` | **true** |
| `ARBICORE_AUTOEXEC_AUTOSTART` | **false** |
| `ARBICORE_RUNTIME_AUTOSTART` | **false** |
| `ARBICORE_PAPER_VALIDATION_ENABLED` | **true** (ops continuity; not mode promotion) |
| `live_execution_enabled` | **false** |
| Kill engaged | **true** (`boot_default`) |
| Signing / broadcast / funds | **not reached / 0 / 0** |
| Gate 7 | **$25.00** (M6 post-alchemy: rejects $24.99 / accepts $25.00) — **unchanged** |
| Gate 8 / H05 | Gate 8 $100k fail-closed; H05 price-feed/borrow-sizer **UNSET=OFF** — **unchanged** |
| Mode promotion | **NONE** |

No safety regression → continue; no stop.

---

## 3. Six-chain RPC + Alchemy 429 + Balancer notes (read-only)

| Chain | Host | eth_chainId + eth_blockNumber | Alchemy 429 |
|---|---|---|---|
| ethereum | `eth-mainnet.g.alchemy.com` | **PASS** | **none** |
| arbitrum | `arb-mainnet.g.alchemy.com` | **PASS** | **none** |
| optimism | `opt-mainnet.g.alchemy.com` | **PASS** | **none** |
| polygon | `polygon-mainnet.g.alchemy.com` | **PASS** | **none** |
| bnb | `bnb-mainnet.g.alchemy.com` | **PASS** | **none** |
| base | `mainnet.base.org` | **PASS** | n/a |

Alchemy path fp (five Alchemy chains): **`5e5d5bb1`** (old capacity-exhausted key cleared).

**Balancer (from M6 post-alchemy PASS; not re-run harness):**

- Ethereum **P0** known 80BAL-20WETH: **ok**
- P1 subgraph: **unset** → fail-closed `discovery_unavailable` (expected)
- P1b long-window: still limited by Alchemy Free **`eth_getLogs` block-range** (not monthly 429)
- Base P1b: **ok** on `mainnet.base.org` (prior M6)

---

## 4. A / B / C / E + EXECUTABLE + rejects (no fabrication)

### M6 SHADOW economic evidence (latest post-alchemy)

Source: `reports/shadow_validation/m6_post_alchemy_reset_latest.json` (`m6_status=PASS`)

| Bucket | Count |
|---|---|
| **A** real profitable (Gate 7) | **0** |
| **B** real economically rejected | **10** |
| **C** quote failures | **8** |
| **D** liquidity failures | **0** |
| **E** gas failures | **14** |

### Paper validation window (this campaign)

| Metric | Value |
|---|---|
| EXECUTABLE count | **0** |
| Paper histogram rejects | all **0** (no bundles) |
| `paper_pnl_usd` | **0.00** (A=0 / EXECUTABLE=0 ⇒ honest) |
| `max_drawdown_usd` | **0.00** |

---

## 5. Checkpoint policy application

| Threshold | Met? | Action taken |
|---|---|---|
| elapsed ≥ 8h | **NO** (≈1.86h) | **STATUS snapshot only** — do **not** write 8h confidence PASS |
| elapsed ≥ 24h | **NO** | Official Gate 9 **not** produced |
| elapsed ≥ 72h | **NO** | Official Gate 10 **not** produced |

**Official Gate 9 = 24h and Gate 10 = 72h remain binding. Do not relabel this run.**

---

## 6. Observations (not blockers)

1. Paper evidence total still **0** — runner healthy, opportunity pipeline empty.
2. Elapsed **&lt; 8h** — accelerated confidence report deferred.
3. Balancer P1 subgraph unset; P1b Free-tier getLogs range limit remains (capacity 429 cleared).

---

## 7. Next actions (ops only; no activation)

1. Leave continuous SHADOW + paper runner alone until **≥8h** for accelerated confidence report.
2. At ≥24h / ≥72h, produce official Gate 9 / Gate 10 per existing criteria only.
3. Parallel prep doc only: `docs/certification/RECOMMENDATION_LIMITED_LIVE_PREP_AUDIT_20261002.md` — **no activation**.
