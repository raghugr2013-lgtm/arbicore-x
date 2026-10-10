# Paper Gate 9–10 Validation (SHADOW ops evidence)

- **Status:** **CONDITIONAL**
- **Date:** 2026-10-02 (run stamp `20261002T072116Z`)
- **Workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Runtime:** `arbicore-x-backend-new`
- **Image:** `arbicore-x-backend:g5.79-green-20260927`
- **Plan:** `docs/certification/PAPER_VALIDATION_MINIMAL_DELTA_PLAN_20261002.md`
- **Audit:** `docs/certification/PAPER_BROKER_READINESS_AUDIT_20261002.md` (READY — reuse `arbicore/paper/*` under SHADOW)
- **Machine evidence:** `reports/paper_validation/gate9_10_final_20261002T072116Z.json`
- **STOP:** No Recommendation / Live promotion

---

## FINAL VERDICT

**CONDITIONAL**

| Gate | Result | Why |
|---|---|---|
| Gate 9 (24h + non-negative paper P&L) | **CONDITIONAL** | Runner span ≈ **1.04h** < 24h; `arbicore_paper_evidence` total = **0**. Paper P&L derivation = **$0.00** (EXECUTABLE=0 → non-negative). |
| Gate 10 (72h + drawdown within limits) | **CONDITIONAL** | Same continuity window < 72h. Max drawdown = **$0.00** (EXECUTABLE=0). |

Not **BLOCKED**: SHADOW held; AUTOEXEC/RUNTIME off; kill engaged; live execution false; signing/broadcast/funds not reached; Gate 7/8/H05 unchanged; six-chain RPC healthy.

---

## 1. Pre-run confirmations

| Check | Result |
|---|---|
| `git rev-parse HEAD` | `9b196cde0c975d0efe94e94f49de05b4244bdbc6` |
| Source / app code changes | **0** (docs/reports only in working tree) |
| Image on `arbicore-x-backend-new` | `arbicore-x-backend:g5.79-green-20260927` |
| `ARBICORE_EXECUTION_MODE` | **SHADOW** |
| `ARBICORE_AUTOEXEC_AUTOSTART` | **false** |
| `ARBICORE_RUNTIME_AUTOSTART` | **false** |
| `ARBICORE_PAPER_VALIDATION_ENABLED` | **true** |
| Gate 7 floor | **$25.00** (rejects $24.99 / accepts $25.00) |
| Gate 8 TVL | floor **$100,000**; fail-closed on unverifiable TVL — **unchanged** |
| H05 exact-size | env flags **OFF** / not enabled — **unchanged** |
| Six-chain RPC `eth_chainId`/`eth_blockNumber` | **PASS** (all six) |

### Six-chain RPC health

| Chain | Host | Result |
|---|---|---|
| ethereum | `eth-mainnet.g.alchemy.com` | PASS |
| arbitrum | `arb-mainnet.g.alchemy.com` | PASS |
| optimism | `opt-mainnet.g.alchemy.com` | PASS |
| polygon | `polygon-mainnet.g.alchemy.com` | PASS |
| bnb | `bnb-mainnet.g.alchemy.com` | PASS |
| base | `mainnet.base.org` | PASS |

---

## 2. Continuity / runner metrics

| Field | Value |
|---|---|
| `is_running` | true |
| `started_at` | `2026-10-02T06:19:43.018995+00:00` |
| `last_cycle_at` (refresh) | `2026-10-02T07:24:46.762081+00:00` |
| Span / uptime hours | ≈ **1.04** |
| `cycles_completed` (refresh) | 778 |
| `exceptions` | 0 |
| `opportunities_seen` / `processed` | 0 / 0 |
| `/validation/report.total` | **0** |
| Mongo `arbicore_paper_evidence.count` | **0** |

Continuity note: container/runner clock starts **2026-10-02T06:19:43Z** (post-restart). No prior unbroken ≥24h/≥72h paper-validation metrics window is claimable from this host process.

---

## 3. Paper P&L and drawdown (offline derivation)

**Method (plan-canonical):**  
`paper_pnl_usd = Σ net_profit_usd` over `outcome=EXECUTABLE` bundles (profit stage payload; fallback journal `expected_net_profit_usd`).  
Equity curve / drawdown from chronological EXECUTABLE expected_net series.  
**If EXECUTABLE=0 → PnL=0 and drawdown=0** (honest; no fabricated fills).

| Metric | Value |
|---|---|
| EXECUTABLE count | **0** |
| `paper_pnl_usd` | **0.00** (≥ 0) |
| `max_drawdown_usd` | **0.00** |
| Drawdown limit (documented) | A=0 window: measured DD=0 satisfies any non-negative operator limit; **no live capital cap invented** |

Spot-check evidence IDs: **none available** (evidence total 0) — Gate 8 handoff “fills logged” bar not met on this window.

---

## 4. A / B / C / E (from recent M6 SHADOW evidence)

Reused M6 post-alchemy-reset harness `economic_evidence` (not paper-evidence fills):

| Bucket | Count |
|---|---|
| **A** real profitable (Gate 7 $25) | **0** |
| **B** real economically rejected | **10** |
| **C** quote failures | **8** |
| **D** liquidity failures | **0** |
| **E** gas failures | **14** |

Source: `reports/shadow_validation/m6_post_alchemy_reset_latest.json` (`m6_status=PASS`, A=0 honest). Six-chain coverage in that pass: ethereum, arbitrum, base, optimism, polygon, bnb.

---

## 5. Rejects / fail-closed / safety

| Item | Value |
|---|---|
| Paper histogram rejects | all **0** (no bundles) |
| Gate 8 fail-closed (unverifiable TVL) | **confirmed** in-image |
| Kill switch engaged | **true** (`boot_default`) |
| `live_execution_enabled` | **false** |
| Signing reached | **false** |
| Broadcasts | **0** |
| Funds moved | **0** |
| Mode promotion SHADOW→PAPER | **NONE** |

Strategy mode registry still shows seeded non-flash strategies as `PAPER` analysis modes and `flash_loan_arbitrage=SHADOW`; global `ARBICORE_EXECUTION_MODE=SHADOW`. No promotion performed in this run.

---

## 6. Artifacts (fresh; prior certs not overwritten)

| Artifact | Path |
|---|---|
| Cert (stable name) | `docs/certification/PAPER_GATE9_10_VALIDATION_20261002.md` |
| Cert (timestamped) | `docs/certification/PAPER_GATE9_10_VALIDATION_20261002T072116Z.md` |
| Preflight JSON | `reports/paper_validation/gate9_10_preflight_20261002T072116Z.json` |
| API session JSON | `reports/paper_validation/gate9_10_api_session_20261002T072116Z.json` |
| Derived PnL/duration | `reports/paper_validation/gate9_10_derived_20261002T072116Z.json` |
| Metrics refresh | `reports/paper_validation/gate9_10_metrics_refresh_20261002T072116Z.json` |
| Final report JSON | `reports/paper_validation/gate9_10_final_20261002T072116Z.json` |

---

## 7. Acceptance checklist (plan)

### Gate 9
- [x] Window timestamps + metrics snapshots (start/end relative to this process) — **span <24h**
- [x] `/validation/report` histogram at collection time
- [x] Paper P&L method + numeric result (≥ 0) — **0.00**
- [ ] Spot-check ≥3 evidence IDs — **blocked by evidence_total=0**
- [x] Affirm broadcasts=0; AUTOEXEC/RUNTIME false; SHADOW; Gate 7/8/H05 unchanged

### Gate 10
- [ ] 72h continuity — **not met** (≈1.04h)
- [x] Drawdown derivation + max DD vs stated A=0 limit interpretation — **0.00**
- [x] Same safety affirmations

---

## STOP

**No Recommendation. No Live / LIMITED_LIVE / FULL_LIVE promotion. Remain SHADOW.**
