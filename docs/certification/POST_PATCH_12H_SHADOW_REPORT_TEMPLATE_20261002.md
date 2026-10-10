# POST-PATCH 12h SHADOW Validation Report — TEMPLATE

> **POST-PATCH VALIDATION — NOT OFFICIAL GATE 9 — NOT GATE 10**
>
> Fill only after: (1) accelerated 8h baseline captured, (2) Workstream A deploy completed in a **separate** window, (3) ≥12.0 h continuous SHADOW on the post-patch image.
>
> Package runbook: `docs/certification/POST_8H_12H_SHADOW_VALIDATION_PACKAGE_20261002.md`

- **Kind:** Post-patch SHADOW validation (Workstream A quoter 429 / `befb14e`)
- **NOT** Gate 9 PASS (official Gate 9 = **≥24h** continuous on its own campaign rules)
- **NOT** Gate 10 PASS (official Gate 10 = **≥72h**)
- **Allowed verdicts:** `PASS` | `CONDITIONAL` | `FAIL` | `BLOCKED`
- **Machine evidence:** `reports/shadow_validation/post_patch_12h_<TS>Z.json`
- **Baseline (8h pre-patch):** `reports/shadow_validation/post_patch_baseline_8h_<TS>Z.json`

---

## Template body (copy into stamped final MD)

```markdown
# POST-PATCH 12h SHADOW Validation Report

> **POST-PATCH VALIDATION — NOT OFFICIAL GATE 9 — NOT GATE 10**

- **Status:** <PASS | CONDITIONAL | FAIL | BLOCKED>
- **Collected at:** <ISO-UTC>
- **Workspace:** /home/raghu/projects/arbicore-x-cert
- **Container:** arbicore-x-backend-new
- **Post-patch image / tip:** <tag> / befb14e6aa77515daa038e142ff978822a4fab91 (or certified successor)
- **Pre-patch baseline image:** arbicore-x-backend:g5.79-green-20260927
- **Workstream A cert gate:** <READY WITH CONDITIONS | READY (tip+fixture) | NO-GO> — cite cert doc §13
- **Machine evidence:** reports/shadow_validation/post_patch_12h_<TS>Z.json
- **Baseline evidence:** reports/shadow_validation/post_patch_baseline_8h_<TS>Z.json
- **STOP:** No LIMITED_LIVE / AUTOEXEC / RUNTIME / signing / broadcast; secrets redacted

## FINAL OUTPUT

| Field | Value |
|---|---|
| Label | POST-PATCH VALIDATION — NOT OFFICIAL GATE 9 — NOT GATE 10 |
| 8h baseline captured at | |
| Deploy cutover at (new StartedAt) | |
| Post-patch window end | |
| Post-patch elapsed hours (≥12.0?) | |
| restart_count (post-patch window) | |
| Post-patch verdict | |
| Official Gate 9 status (separate) | <PASS/CONDITIONAL/not-yet/waived> |
| Rollback available | g5.79-green-20260927 YES/NO |

## 1. Continuity (post-patch window)

- container status / health:
- StartedAt (post-deploy T0):
- RestartCount:
- runner.is_running / cycles / exceptions / last_cycle_at:
- interruptions:

## 2. Safety (must hold)

| Control | Required | Observed |
|---|---|---|
| ARBICORE_EXECUTION_MODE | SHADOW | |
| ARBICORE_SHADOW_CERT_ENABLED | true | |
| ARBICORE_AUTOEXEC_AUTOSTART | false | |
| ARBICORE_RUNTIME_AUTOSTART | false | |
| live_execution_enabled | false | |
| kill engaged | true | |
| signing | 0 / not reached | |
| broadcast | 0 | |
| funds movement | 0 | |
| Gate7 / Gate8 / H05 | $25 / $100k fail-closed / H05 OFF | |

## 3. Before / after RPC metrics

| Metric | Pre-patch 8h | Post-patch 12h | Δ / formula | PASS? |
|---|---:|---:|---|:---:|
| Window hours | | | — | — |
| Base→Alchemy failovers (M1) | | | | — |
| Failovers / hour | | | | — |
| Alchemy Base POSTs | | | | — |
| Alchemy POSTs / failover (M2) | | | target post ≤2.0; pre≈5 | |
| Alchemy 429 / hour (M3) | | | ≥70% drop or ≤0.3×pre | |
| Alchemy 200 / hour | | | | — |
| Cooldown activations (M7) | ~0 | | | |
| Timeouts / transport errors | | | | — |
| Successful RPC HTTP 200 (by host summary) | | | | — |

## 4. Quote metrics

| Metric | Pre | Post | Notes |
|---|---:|---:|---|
| status=ok count (/h) | | | source: |
| non-ok / failed (/h) | | | |
| fallback:break_even (/h) | | | fail-closed honesty |
| other fallback:* (/h) | | | |
| latency p50/p95 (if any) | | | or evidence_gap |
| provider usage mix | | | hosts only; fp8 optional |

## 5. Opportunity / economic

| Metric | Pre | Post |
|---|---:|---:|
| opportunities_seen / processed | | |
| paper report.total | | |
| EXECUTABLE | | |
| REJECTED (+ bucket breakdown) | | |
| A / B / C / E (label source) | | |
| paper_pnl_usd | | |
| max_drawdown_usd | | |

PnL method: A=0 / EXECUTABLE=0 ⇒ $0 / DD=$0 honest.

## 6. Six-chain coverage

| Chain | Host | chainId+blockNumber | 429 notes |
|---|---|---|---|
| ethereum | | | |
| arbitrum | | | |
| optimism | | | |
| polygon | | | |
| bnb | | | |
| base | | | |

Coverage verdict: 6/6 ? YES/NO (honest failures listed)

## 7. Infrastructure

- restart_count continuity:
- health timeline:
- image digest/tag:
- compose override used:
- rollback drill referenced: docs/... PACKAGE §10

## 8. Deploy gate record

- Self-contained bundle SHA256:
- Tip SHA:
- Cert / deploy recommendation at deploy: READY WITH CONDITIONS (product tip) / READY (tip+fixture 57f5365) / NO-GO — cite §13.6
- Fixture follow-up landed for CI co-run gate? YES/NO (`57f5365` or equivalent):
- Scoped-throttle residual status: fixture-only (resolved per §13) /

## 9. Evidence gaps (exact; no invented fills)

-

## 10. Verdict rationale (post-patch only)

-
```

---

## Machine JSON schema (minimal)

```json
{
  "cert": "POST_PATCH_12H_SHADOW_VALIDATION",
  "not_official_gate9": true,
  "not_official_gate10": true,
  "label": "POST-PATCH VALIDATION — NOT OFFICIAL GATE 9 — NOT GATE 10",
  "ts": "<YYYYMMDDTHHMMSSZ>",
  "collected_at": "<ISO>",
  "verdict": "PASS | CONDITIONAL | FAIL | BLOCKED",
  "workstream_a_tip": "befb14e6aa77515daa038e142ff978822a4fab91",
  "workstream_a_cert_gate": "READY WITH CONDITIONS | READY_TIP_PLUS_FIXTURE | NO-GO",
  "baseline_ref": "reports/shadow_validation/post_patch_baseline_8h_<TS>Z.json",
  "image_post": null,
  "image_pre": "arbicore-x-backend:g5.79-green-20260927",
  "container": {},
  "window_hours": null,
  "safety": {},
  "rpc": {},
  "quotes": {},
  "opportunities": {},
  "six_chain": {},
  "infra": {},
  "compare": {
    "M2_pre": null,
    "M2_post": null,
    "M3_reduction": null,
    "M7_post": null
  },
  "pnl": {
    "method": "A=0 / EXECUTABLE=0 => PnL=$0 drawdown=$0",
    "paper_pnl_usd": null,
    "max_drawdown_usd": null
  },
  "blockers": [],
  "observations": [],
  "evidence_gaps": [],
  "STOP": "Not Gate9/Gate10; no secrets; no invented EXECUTABLE"
}
```

---

## Pass criteria cheat-sheet (post-patch package)

| # | Criterion | PASS |
|---|---|---|
| C1 | Duration | ≥ **12.0** h continuous post-deploy |
| C2 | M2 Alchemy POSTs/failover | **≤ 2.0** |
| C3 | M3 429/hour | meaningful drop vs 8h baseline (≥70% or ≤0.3×) |
| C4 | Fail-closed honesty | no ok inflation under RL/cooldown |
| C5 | Safety | SHADOW; AUTOEXEC/RUNTIME off; signing/broadcast/funds **0** |
| C6 | Continuity | RestartCount **0** in post-patch window (or documented break → not PASS) |
| C7 | Six-chain | 6/6 probes or honest documented failures with operator accept |
| C8 | Deploy gate | Workstream A §13 **READY WITH CONDITIONS** (deploy product tip; land fixture hygiene for CI) or tip+fixture **READY**; Gate9 cutover separately authorized |

**CONDITIONAL:** C1+C2+C4+C5+C6 hold but C3 weak because Alchemy mostly 200s (cooldown under-stressed) — document explicitly.

---

## Naming conventions

| Artifact | Path |
|---|---|
| Final human report | `docs/certification/POST_PATCH_12H_SHADOW_<TS>Z.md` (or `…_20261002.md` if single-day stamp) |
| Machine JSON | `reports/shadow_validation/post_patch_12h_<TS>Z.json` |
| Latest pointer | `reports/shadow_validation/post_patch_12h_latest.json` |
| 8h baseline | `reports/shadow_validation/post_patch_baseline_8h_<TS>Z.json` |
