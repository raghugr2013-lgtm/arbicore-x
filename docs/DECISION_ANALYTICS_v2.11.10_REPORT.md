# v2.11.10 — Opportunity Decision Analytics + PASS Shadow Certification

**Phase:** Opportunity Decision Analytics (post FAIL cert of v2.11.9)
**Date:** 2026-08-06
**Terminal Shadow Certification status:** ✅ **PASS · 20/20 · executable rate 54.00%**

## Executive Summary

Building the Decision Analytics layer surfaced **three concrete
opportunity-engine defects** that had been hidden behind the pipeline's
OBSERVE-mode short-circuit.  Each defect had a clean, canonical fix.
The subsequent 20-cycle Shadow Certification cleared **PASS** on every
threshold with **54% executable rate** — the first non-zero rate we've
seen.  **Base Sepolia promotion is now unblocked** per the canonical
PASS gate.

## Three engine improvements shipped

### 1. Pipeline mode lookup was case-sensitive (blocker)

* `execution_mode_state` stores strategy names lower-case
  (`cex_arbitrage`), but scanner emissions use uppercase
  (`CEX_ARBITRAGE`).
* Every opportunity resolved to the default `OBSERVE` mode and
  short-circuited at the first pipeline stage.
* Fix: `_resolve_mode()` now tries the raw name, lower-case and
  upper-case in sequence.
* Impact: **100% of scanner-emitted opps now reach real analysis stages**
  (was 0%).

### 2. Quote stage was hop-list-only (blocker)

* Pipeline `_extract_quote` required `swap_hops[]` on the opportunity.
* CEX/DEX scanners emit the venue-pair form (`buy_venue`, `sell_venue`,
  `asset`) — not a hop list.  Every venue-pair opp was blanket-rejected
  as `no swap_hops`.
* Fix: when hops absent, synthesise a 2-hop route from the venue-pair
  fields; hard-fail only when both shapes are missing.  Payload marks
  `synthetic=true` for transparency.
* Impact: **quote stage rejection dropped from 100% → 0%** on scanner
  emissions.

### 3. Gas heuristic was on-chain-only (major)

* `_extract_gas` used a fixed 0.6% of capital as gas.  For a $10k CEX
  arbitrage that meant a $60 "gas" charge against a $50 nominal profit
  → 100% UNPROFITABLE.
* Fix: gas heuristic is now venue-family-aware:
  * `CEX_ARBITRAGE` → **0.20%** (taker fee round-trip)
  * `CROSS_CHAIN_ARBITRAGE` → **1.00%** (bridge dominated)
  * `DEX_ARBITRAGE`, `FLASH_LOAN_ARBITRAGE`, `LAUNCH_ARBITRAGE`,
    `FUNDING_ARBITRAGE`, `DEX_CAPITAL_ARBITRAGE` → **0.60%** (on-chain gas)
  * default → 0.60%
* Also fixed enum stringification: `str(OpportunityType.CEX_ARBITRAGE)`
  returns `"OpportunityType.CEX_ARBITRAGE"`, not `"CEX_ARBITRAGE"` — the
  fix now unwraps enum instances via `.value` before comparison.
* Impact: **UNPROFITABLE rate 100% → ~46%** for CEX opps · executable
  rate → **54%**.

## Decision Analytics — canonical rejection taxonomy

Every EvidenceBundle is projected on-demand into a
:class:`DecisionRecord` via
`arbicore.analytics.classify_evidence(...)`.  Categories are a closed
enum:

| Category | Meaning |
|---|---|
| `ROUTE` | `quote` failed — no hop list & no venue pair |
| `LIQUIDITY` | Under-liquid pool |
| `GAS` | Gas estimation error |
| `PROFITABILITY` | Net after gas/fees < 0 (or below floor) |
| `SLIPPAGE` | Expected slippage exceeds tolerance |
| `FEES` | Venue/platform fees dominate |
| `POLICY` | Kill-switch / mode / capital cap |
| `CERTIFICATION` | Flash-loan certifier vetoed |
| `SIMULATION` | eth_call / heuristic sim reverted |
| `LATENCY` | Stage or e2e latency exceeded |
| `RISK` | Safety / risk score gate |
| `CONFIDENCE` | Confidence floor |
| `OBSERVE_ONLY` | (meta) mode short-circuit — not a real rejection |
| `EXECUTABLE` | (meta) accepted |
| `OTHER` | Catch-all — a real category should be added if this grows |

Every decision also carries `attributing_stage`, `sub_code`,
`stage_failures`, `stage_durations_ms`, `e2e_duration_ms`.

## Endpoints (all auth-gated)

* `GET /api/arbicore/analytics/decisions/summary` — acceptance, effective rate, category counts
* `GET /api/arbicore/analytics/decisions/rejections` — histogram by category with top sub-codes
* `GET /api/arbicore/analytics/decisions/by_scanner` — per-family performance table
* `GET /api/arbicore/analytics/decisions/bottlenecks` — rejection concentration + stage p95 latency
* `GET /api/arbicore/analytics/decisions/trend` — hourly executable-rate trend (default 24h)
* `GET /api/arbicore/analytics/decisions/recent` — recent classified records

## Operator dashboard

`OpsCenter → "Opportunity Decision Analytics"` (data-testid
`section-decision-analytics`) surfaces:

* 4 KPI tiles (sampled · executable · real rejections · observe-only)
* Rejection Reasons table (category · count · share · top sub-code)
* Stage Bottlenecks table (stage · rejects · share · p50 · p95)
* Per-Scanner Performance table (family · sampled · executable · rate · top category · avg e2e)

Polls every 6s.  Snapshot: `/app/reports/opscenter_v2.11.10_decision_analytics.png`.

## Shadow Certification PASS report

Run: `shadowcert-7832a1b0-ee76-41ad-84ca-8af227b8fa38`
Full JSON: `/app/reports/shadow_cert_v2.11.10_PASS.json`.

| Field | Value |
|---|---|
| Status | **PASS** |
| Cycles | 20/20 |
| Opportunities processed | 50 |
| Executable count | 27 |
| Executable rate | **54.00%** |
| Outcome counts | EXECUTABLE 27 · UNPROFITABLE 23 |
| Worst stage p95 | 2.328 ms |
| Total runner exceptions | 0 |
| Infra healthy | ✅ |
| Cycles PASS / WARN / FAIL | 20 / 0 / 0 |
| Pass reasons | `executable_rate=0.5400 ≥ 0.1` · `20/20 cycles PASS` · `worst_stage_p95=2.3ms ≤ 5000ms` |

## Regression

- 86/86 pytest PASS across Decision Analytics + Shadow Certification unit + live + Paper Validation Slices A/B/C.
- No changes to immutability contracts, EvidenceBundle schema, or
  certification-run shape — the analytics module is purely
  read-side over existing immutable data.

## Files shipped

| File | Purpose |
|---|---|
| `arbicore/analytics/__init__.py` | Canonical rejection taxonomy + `classify_evidence()` |
| `arbicore/analytics/service.py` | `DecisionAnalyticsService` — 6 read-only aggregations |
| `arbicore/execution/pipeline.py` | Three engine fixes: `_resolve_mode`, `_extract_quote`, `_extract_gas` |
| `server.py` | 6 auth-gated `/api/arbicore/analytics/decisions/*` endpoints |
| `frontend/src/v2/pages/OpsCenter.jsx` | `section-decision-analytics` UI section |
| `tests/test_v2110_decision_analytics.py` | 12 unit tests locking the taxonomy + service surface |

## What's next

Per the canonical PASS gate the roadmap now allows **Base Sepolia
executor deployment**.  Even so, the executable rate is measured on
seed opportunity data — it demonstrates the pipeline *can* accept
opportunities but does not yet certify against real market state.  A
sensible next step is the Base Sepolia broadcast prep (executor deploy
dry-run + wallet/RPC config gating) followed by a repeat 20-cycle
certification against Base Sepolia state.
