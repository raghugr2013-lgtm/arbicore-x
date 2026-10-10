# SHADOW Accelerated 8h Confidence Checkpoint

- **Status:** **HEALTHY WITH OBSERVATIONS**
- **Kind:** Accelerated 8h confidence — **NOT** Gate 9 PASS — **NOT** Gate 10 PASS
- **Collected at:** `2026-10-02T14:20:17.381024+00:00`
- **Workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Runtime:** `arbicore-x-backend-new`
- **Image:** `arbicore-x-backend:g5.79-green-20260927`
- **Machine evidence:** `reports/shadow_validation/accel_8h_checkpoint_20261002T142017Z.json` (+ `accel_8h_checkpoint_latest.json`)
- **API raw:** `reports/shadow_validation/accel_8h_checkpoint_api_raw_20261002T142017Z.json`
- **STOP:** No source/config/gate/mode changes. No PAPER/AUTOEXEC/RUNTIME/Recommendation activation. No rebuild/deploy/live tx. Campaign **not** reset/restarted.

---

## FINAL OUTPUT (binding)

| Field | Value |
|---|---|
| Campaign start (runner) | `2026-10-02T06:19:43.018995+00:00` |
| Container start | `2026-10-02T06:19:33.513948555Z` |
| restart_count | **0** |
| Elapsed (at collection) | **≈ 8.01 h** (span ≈ 8.01 h; cycles 5740; exceptions 0) |
| 8h verdict | **HEALTHY WITH OBSERVATIONS** |
| Official Gate 9 | **24h continuous** — unchanged — earliest ≈ `2026-10-03T06:19:43Z` (~15.99 h remaining) |
| Official Gate 10 | **72h continuous** — unchanged — earliest ≈ `2026-10-05T06:19:43Z` |
| Gate 9/10 criteria relabeled? | **NO** |
| Freeze held | **YES** (docs/reports only this task) |

---

## 1. Continuity duration

| Check | Result |
|---|---|
| Container | `running` / `healthy` / restart_count=**0** |
| Paper runner `is_running` | **True** |
| `last_cycle_at` | `2026-10-02T14:20:16.963647+00:00` |
| Interruptions | none observed (restart_count=0; runner continuous since started_at) |
| Daily run | `run_20261002_0619` running=True |

---

## 2. Runner health

| Metric | Value |
|---|---|
| cycles_completed | 5740 |
| exceptions | 0 |
| opportunities_seen / processed | 0 / 0 |
| last_error | None |
| `/validation/report.total` | **0** |
| paper_stats.analyses | 0 |

---

## 3. Six-chain coverage

| Chain | Host | ok | Alchemy 429 |
|---|---|---|---|
| ethereum | `eth-mainnet.g.alchemy.com` | **True** | False |
| arbitrum | `arb-mainnet.g.alchemy.com` | **True** | False |
| optimism | `opt-mainnet.g.alchemy.com` | **True** | False |
| polygon | `polygon-mainnet.g.alchemy.com` | **True** | False |
| bnb | `bnb-mainnet.g.alchemy.com` | **True** | False |
| base | `mainnet.base.org` | **True** | False |

RPC overall ok: **True**; alchemy_429_present: **False**

---

## 4. Opportunity counts by state

### Paper histogram

```json
{
  "EXECUTABLE": 0,
  "REJECTED": 0,
  "UNPROFITABLE": 0,
  "LIQUIDITY_FAILURE": 0,
  "GAS_FAILURE": 0,
  "ROUTE_FAILURE": 0,
  "RISK_FAILURE": 0,
  "SIMULATION_FAILURE": 0
}
```

### Mongo

| Collection | Count |
|---|---|
| arbicore_paper_evidence | 0 |
| arbicore_opportunity_journal | 0 |
| evidence_bundles (all) | 541251 |
| evidence_bundles since campaign | 1076 |

Outcomes since campaign (evidence_bundles): `{"None": 1076}`

---

## 5. Economic evidence (A/B/C/E, EXECUTABLE, PnL/DD)

### M6 SHADOW economic evidence (reused; image unchanged)

| Bucket | Count |
|---|---|
| **A** real profitable | **0** |
| **B** economically rejected | **10** |
| **C** quote failures | **8** |
| **D** liquidity failures | **0** |
| **E** gas failures | **14** |

Source: `reports/shadow_validation/m6_post_alchemy_reset_latest.json`

### Paper window

| Metric | Value |
|---|---|
| EXECUTABLE | **0** |
| paper_pnl_usd | **0.0** |
| max_drawdown_usd | **0.0** |

---

## 6. Rejection / fail-closed reasons

- Paper histogram rejects: all buckets as above (zeros if no bundles).
- Gate 8 / H05: unchanged from M6/Gate9 preflight (Gate8 $100k fail-closed; H05 UNSET=OFF).
- Mode API snapshot: `{"items": [{"strategy": "cex_arbitrage", "mode": "PAPER", "seeded": true, "created_at": "2026-09-07T05:24:07.936469+00:00", "updated_at": "2026-09-07T05:24:07.936469+00:00"}, {"strategy": "cross_chain_arbitrage", "mode": "PAPER", "seeded": true, "created_at": "2026-09-07T05:24:07.960548+00:00", "updated_at": "2026-09-07T05:24:07.960548+00:00"}, {"strategy": "dex_capital_arbitrage", "mode": "PAPER", "seeded": true, "created_at": "2026-09-07T05:24:07.949645+00:00", "updated_at": "2026-09-07T05:24:`

---

## 7. Infrastructure errors (RPC / 429 / Balancer)

- Alchemy monthly 429: **False**
- Balancer: reuse M6 post-alchemy: P1 subgraph unset; P1b Free getLogs range limits; capacity 429 cleared
- Per-chain failures: see RPC table / machine JSON.

---

## 8. Safety state

| Control | Value |
|---|---|
| ARBICORE_EXECUTION_MODE | **SHADOW** |
| AUTOEXEC_AUTOSTART | **false** |
| RUNTIME_AUTOSTART | **false** |
| PAPER_VALIDATION_ENABLED | **true** |
| live_execution_enabled | **False** |
| kill engaged | **True** (`boot_default`) |
| H05 price/borrow | UNSET / UNSET |

---

## 9. Exact evidence gaps

- arbicore_paper_evidence / validation report total=0
- no opportunities fed into paper runner this campaign

## 10. Observations / blockers

**Blockers:** []

**Observations:**
- paper_evidence_total=0 (runner OK; opportunity pipeline empty)
- opportunities_seen=0 / opportunities_processed=0
- verifier evidence_bundles appending since campaign (~1076); outcomes null/not paper EXECUTABLE

## 11. Verdict

**HEALTHY WITH OBSERVATIONS** — accelerated 8h confidence only. **Not** Gate 9 PASS. Leave campaign untouched until official ≥24h (`2026-10-03T06:19:43Z`).
