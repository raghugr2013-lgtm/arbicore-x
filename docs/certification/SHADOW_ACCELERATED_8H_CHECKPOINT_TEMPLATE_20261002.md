# SHADOW Accelerated 8h Checkpoint — TEMPLATE

- **Kind:** Accelerated **confidence** report package (fill at/after ≥8h elapsed)
- **NOT** Gate 9 PASS — Official Gate 9 remains **24h**
- **NOT** Gate 10 PASS — Official Gate 10 remains **72h**
- **Allowed verdicts only:** `HEALTHY` | `HEALTHY WITH OBSERVATIONS` | `BLOCKED`
- **Campaign:** do **not** restart / reset / shorten / promote
- **Package paths (produce at stamp):**
  - Human: `docs/certification/SHADOW_ACCELERATED_8H_CHECKPOINT_20261002.md`
  - Machine: `reports/shadow_validation/accel_8h_checkpoint_<TS>Z.json`
  - Optional API raw: `reports/shadow_validation/accel_8h_checkpoint_api_raw_<TS>Z.json`
  - Optional latest pointer: `reports/shadow_validation/accel_8h_checkpoint_latest.json`

---

## Fill instructions (ops, read-only)

1. Confirm `elapsed_hours >= 8` from paper runner `started_at` (`2026-10-02T06:19:43.018995+00:00` → earliest stamp `2026-10-02T14:19:43Z`).
2. Collect APIs listed in `GATE9_EVIDENCE_CHECKLIST_20261002.md` §A–E (no secrets).
3. Reuse M6 A/B/C/E if image unchanged; label source.
4. Apply A=0 / EXECUTABLE=0 ⇒ PnL=$0, DD=$0.
5. Issue one of the three confidence verdicts — **never** “Gate 9 PASS”.
6. Leave campaign untouched until official ≥24h Gate 9.

---

## Template body (copy into final MD)

```markdown
# SHADOW Accelerated 8h Confidence Checkpoint

- **Status:** <HEALTHY | HEALTHY WITH OBSERVATIONS | BLOCKED>
- **Kind:** Accelerated 8h confidence — **NOT** Gate 9 PASS — **NOT** Gate 10 PASS
- **Collected at:** <ISO-UTC>
- **Machine evidence:** reports/shadow_validation/accel_8h_checkpoint_<TS>Z.json
- **Image:** arbicore-x-backend:g5.79-green-20260927
- **Container:** arbicore-x-backend-new
- **STOP:** Campaign untouched; no mode/gate/source changes

## FINAL OUTPUT

| Field | Value |
|---|---|
| Campaign start (runner) | |
| Container start | |
| restart_count | |
| Elapsed at report | |
| Cycles / exceptions | |
| 8h verdict | |
| Official Gate 9 ETA (24h) | 2026-10-03T06:19:43Z |
| Hours remaining to Gate 9 | |
| Freeze held | YES/NO |

## 1. Continuity
- is_running:
- last_cycle_at:
- interruptions:

## 2. Runner health
- opportunities_seen / processed:
- last_error:
- paper report.total / histogram:

## 3. Six-chain coverage
| Chain | Host | chainId+blockNumber | 429 |
|---|---|---|---|
| ethereum | | | |
| arbitrum | | | |
| optimism | | | |
| polygon | | | |
| bnb | | | |
| base | | | |

## 4. Opportunity counts by state
- Paper histogram:
- Mongo paper_evidence:
- Verifier evidence_bundles since campaign (outcomes):

## 5. Economic evidence
- A/B/C/E (source:):
- EXECUTABLE:
- paper_pnl_usd / max_drawdown_usd (A=0 rule):

## 6. Rejection / fail-closed reasons
- Paper rejects:
- Gate8 / H05 posture:

## 7. Infrastructure errors
- RPC failures:
- Alchemy 429:
- Balancer notes (reuse M6 if not re-probed):

## 8. Safety state
- MODE / AUTOEXEC / RUNTIME / kill / live_execution / signing / broadcast / funds:

## 9. Evidence gaps (exact; no invented fills)
-

## 10. Verdict rationale
-
```

---

## Machine JSON schema (minimal)

```json
{
  "cert": "SHADOW_ACCELERATED_8H_CHECKPOINT",
  "not_gate9_pass": true,
  "not_gate10_pass": true,
  "official_gate9_hours": 24,
  "official_gate10_hours": 72,
  "ts": "<YYYYMMDDTHHMMSSZ>",
  "collected_at": "<ISO>",
  "git_head": "<sha>",
  "image": "arbicore-x-backend:g5.79-green-20260927",
  "container": {},
  "campaign": {},
  "safety": {},
  "rpc": {},
  "paper_evidence": {},
  "ABC_E": {},
  "pnl": {"method": "A=0 / EXECUTABLE=0 => PnL=$0 drawdown=$0", "paper_pnl_usd": 0.0, "max_drawdown_usd": 0.0},
  "health_status": "HEALTHY | HEALTHY WITH OBSERVATIONS | BLOCKED",
  "blockers": [],
  "observations": [],
  "evidence_gaps": [],
  "hours_to_gate9_24h": null,
  "STOP": "No Recommendation/PAPER/AUTOEXEC/RUNTIME activation; no rebuild/deploy/live tx; no Gate9 PASS claim"
}
```

---

## Phase-1 package readiness

| Item | Status |
|---|---|
| Template path exists | **This file** |
| Final MD path reserved | `docs/certification/SHADOW_ACCELERATED_8H_CHECKPOINT_20261002.md` (write at ≥8h) |
| Reports dir | `reports/shadow_validation/` |
| Auth/cookie method | session login via admin env (do not persist secrets in reports) |
| Campaign start locked | `2026-10-02T06:19:43.018995+00:00` |
| Earliest fill time | `2026-10-02T14:19:43Z` |

---

## After 8h checkpoint (prepare-only pointer — do not deploy yet)

Once this 8h confidence report is filled and the campaign remains untouched, operators may freeze a **pre-patch baseline** and later run the **post-patch 12h** package (separate change window):

- Package: `docs/certification/POST_8H_12H_SHADOW_VALIDATION_PACKAGE_20261002.md`
- 12h report template: `docs/certification/POST_PATCH_12H_SHADOW_REPORT_TEMPLATE_20261002.md`

That package is **not** official Gate 9 and **must not** be executed (no deploy/restart) until the 8h checkpoint is captured and Workstream A §13 deploy recommendation (**READY WITH CONDITIONS** / tip+fixture **READY**) plus campaign-owner GO.
