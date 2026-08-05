# Execution-Pipeline Activation Roadmap
## From preview-stub → live flash-loan runtime, one pipeline stage at a time

**Baseline:** post-v2.9.3 (auth hotfix on VPS)
**Framing:** every slice below is a **pipeline stage**, not a dashboard.
The dashboard tiles are downstream effects — the goal is to make each
pipeline stage produce real, verifiable runtime data.

```
Market Data
      ↓
Discovery
      ↓
Opportunity Detection
      ↓
Route Generation
      ↓
Profitability
      ↓
Execution Planning
      ↓
Flash Loan Execution
      ↓
Learning
```

Primary objective: **prove this pipeline works reliably end-to-end so we
can start limited-live flash-loan paper validation.** Everything else
(portfolio views, admin dashboards, ancillary settings) is secondary and
scheduled after the critical path is proven.

Pre-work already done:
- Empty-state widget sweep — PASS (see `EMPTY_STATE_WIDGET_SWEEP.md`).
  All 15 mounted pages render safely with empty/null data. One tiny
  HomePage Interlock fix folded into Pipeline Stage 3.
- Discovery: OpsCenter (the default landing) is already 100% real. It
  reads from `_MEMORY`, `_LIVE_SCANNER`, `_KILL_SWITCH_REPO`,
  `_VALIDATION_SUMMARY`, `_PROVIDER_REGISTRY`. **No activation needed for
  the operator's daily briefing view.**

---

## Pipeline stage table (revised priority per your Aug-5 directive)

| # | Pipeline stage | Product surface | Was old slice | New priority | Effort | End-to-end gate? |
| - | :------------- | :--------------- | :------------ | :----------- | :----- | :--------------: |
| 1 | **Opportunity Detection** | OpportunitiesPage · OpportunityDrawer · Home fresh-opps | v2.10 Slice 1 | **P0 · SHIP FIRST** | ~2.25 d | — |
| 2 | **Discovery** | DiscoveryPage · scanners status · discovery queue | v2.11 Slice 2 | **P0** | ~3.25 d | ✅ **MANDATORY PAUSE** — verify Market Data → Discovery → Opportunity Detection end-to-end before stage 3 |
| 3 | **Market Intelligence** | fees, gas, liquidity, exchange health, provider state · plus HomePage Interlock micro-fix | (new — not in v1 of roadmap) | **P0** | ~3.5 d | — |
| 4 | **Execution Planning / Readiness** | ExecutorVerify · FlashLoan pre-flight · plans/build · certification | (new — not in v1) | **P0** | ~3 d | ✅ end-to-end gate before stage 5: prove Opportunity → Route → Profitability → Certified plan |
| 5 | **Dashboard / Executive Summary** | HomePage · vitals · ROI | v2.12 | **P1** | ~2.25 d | — |
| 6 | **Portfolio** | positions · balances · deployable · transfers · ledger · exposure · allocation | v2.13 | **P1** | ~4 d for 6a (mount-only) + ~3.5 d for 6b (new repos) | — |
| 7 | **Operations / Monitoring** | scanner control · cycles · venues · interlock · integrations · queues · alerts | v2.14 | **P2** | ~5 d | — |
| 8 | **Remaining informational** | Intelligence Wave-1 completion · Settings verification · ancillary de-stub | v2.15/16/17 | **P3** | ~7 d combined | — |

**Total: ~34 developer-days.** Two engineers in parallel can compress to
~4 weeks of clock time. **The critical path (stages 1–4) is 12 dev-days
= ~2.5 weeks single-engineer, ~10 days two-engineer.**

---

## Stage 1 — Opportunity Detection (P0 · ship first)

### What runtime signal does this stage produce?
The list of currently-detected arbitrage opportunities, each with:
subject, chain, opportunity_type, verdict (GO/SOFT_NO/HARD_NO), confidence,
safety, spread_bps, depth_usd, return_low/high, route, age, provenance.

### Placeholder → canonical mapping

| Placeholder in `server.py` | Canonical source of truth | Fix recipe |
| :------------------------- | :------------------------ | :--------- |
| `GET /arbicore/opportunities` (lines 537–596) — **hybrid** (canonical repo merged with hardcoded `_V2_OPPS`) | `_CANONICAL_OPP_REPO` (already injected) | Delete `_V2_OPPS`, `_hydrate_opps`, and the merge branch. Keep the `_canonical_opp_to_contract` translator. Return `{items, total, source: "canonical", generated_at}`. |
| `GET /arbicore/opportunities/{id}` (638) — hybrid | same | Delete preview fallback; 404 when not in canonical repo. |
| `POST /arbicore/opportunities/{id}/approve` (711) | `_OPPORTUNITY_JOURNAL.approve(id, actor)` | Persist to canonical repo + journal; drop in-memory `_V2_OPPS` mutation. |
| `POST /arbicore/opportunities/{id}/reject` (738) | `_OPPORTUNITY_JOURNAL.reject(id, actor, reason)` | Same. |
| `GET /arbicore/opportunities/{id}/timeline` (768) | `_OPPORTUNITY_JOURNAL.timeline(id)` | Real implementation exists; replace stub fallback. |
| `GET /arbicore/opportunities/summary` (447) — pure hardcoded | Aggregate `_CANONICAL_OPP_REPO.find({})` grouped by type/chain/status | Rewrite handler to run the aggregation. |

### Files touched
- `app/backend/server.py` — delete blocks at 447–455, 485–526, 529–534, 638–855 approve/reject/timeline stub bodies; keep translator and endpoint decorators.
- No frontend changes.

### Verification checklist (must all pass)
1. **Empty Mongo** curl smoke: every endpoint returns `{items: [], total: 0, source: "canonical"}` (200 OK).
2. **Seeded Mongo** curl smoke: seed 3 real `CanonicalOpportunity` docs; endpoints return exactly those 3.
3. Frontend Playwright: `/dashboard/opportunities` renders 3 rows; empty-state renders when Mongo cleared.
4. Approve one opportunity from UI → new document in `opportunity_journal` with `action=APPROVE`; row disappears from CANDIDATE filter.
5. Regression: `OpsCenter` remains fully functional (real live data was not touched).

### Release: **v2.10 · Opportunity Detection canonical activation** · effort 2.25 dev-days.

---

## Stage 2 — Discovery (P0)

### What runtime signal does this stage produce?
The list of **candidates** (discovered assets / venue pairs / chains that
may become opportunities) and the health of each discovery scanner.

### Placeholder → canonical mapping

| Placeholder | Canonical | Fix recipe |
| :---------- | :-------- | :--------- |
| `GET /arbicore/operations/scanners` (1275) — hardcoded 8-row `_V2_SCANNERS` | Mount `arbicore/routes/scanners.py`; aggregate `/scanners/{family}/status` for cex_arb + funding_arb + dex_arb + launch_arb into a single response, plus expose CROSS_CHAIN + FLASH_LOAN + SPATIAL + STATISTICAL as their real states from `_LIVE_SCANNER`. | Add a thin aggregator handler; delete `_V2_SCANNERS`. |
| `POST /arbicore/operations/scanners/{family}/action` (1284) | Existing per-family `POST /scanners/{family}/kill`, `/resume`, `PUT /config` in `scanners.py` | Dispatch by family. |
| `GET /arbicore/discovery/candidates` (903) — hardcoded 7-row `_V2_DISCOVERY` + fabricated calibration | **Path collision** with `scanners.py:370 /discovery/candidates` | Delete the stub. Adapt shape if needed (canonical returns `{count, items, generated_at}`; frontend expects `{items, total, stats, calibration, generated_at}`). Add a real calibration block from `DiscoveryScorer.calibration()` if exposed, otherwise omit. |
| `POST /arbicore/discovery/candidates/{id}/action` (939) | `scanners.py` candidate action or new persistence into `discovery_candidates` collection | Persist state via `DiscoveryRepo.transition(id, action)`. |
| `GET /arbicore/discovery/queue/status`, `/sources/status`, `/sources/hit-rates`, `/weekly-digest` | Already canonical in `scanners.py` | Just mount the router. |

### Files touched
- `app/backend/server.py`: delete blocks 863–946, 1263–1290; mount `arbicore/routes/scanners.py` with prefix `/api/arbicore`.
- Verify no collision beyond `/discovery/candidates` (I already verified — only 2 collisions repo-wide; the other is `/opportunities` handled in Stage 1).
- No frontend changes.

### Verification checklist
1. Every canonical scanner endpoint returns 401 without cookie (auth guard); 200 with cookie.
2. Empty Mongo → `discovery_candidates: {items: [], stats: {new:0, watching:0, promoted:0, dismissed:0}}`.
3. Trigger `_CONTINUOUS_DISCOVERY` scan once → new `CandidateRow` in Mongo → frontend `/discovery` renders the row.
4. Kill a scanner via frontend action → `POST /scanners/{family}/kill` → status becomes PAUSED → next tick shows opps_1h freezing.

### Release: **v2.11 · Discovery canonical activation** · effort 3.25 dev-days.

---

## ⛔ MANDATORY PAUSE — End-to-end pipeline verification (before Stage 3)

Per your directive: after Stage 2 ships, halt and prove the full
Market-Data → Discovery → Opportunity-Detection chain works with real
runtime data before touching Market Intelligence.

### Gate criteria (all must pass before Stage 3 begins)

1. **Market Data** — provider fetch loop runs continuously (`_PROVIDER_REGISTRY` polling ok), evidenced by non-empty `/api/arbicore/live/prices` returning fresh timestamps within poll interval.
2. **Discovery** — `_CONTINUOUS_DISCOVERY` produces at least one CandidateRow persisted to Mongo per hour under normal load.
3. **Opportunity Detection** — for each promoted candidate that turns into a canonical opportunity, verify:
   - Persisted in `arbicore_opportunities` with a valid `subject_id`, `chain`, `opportunity_type`, `confidence_score`, `spread_pct`, `capital_required_usd`, `route`, `expected_profit_usd`.
   - Visible in the frontend `/dashboard/opportunities` list.
   - Journal entry in `opportunity_journal` collection.
4. **No preview data anywhere in the chain**: `GET /api/arbicore/opportunities` response includes `source: "canonical"` (never `"preview"` or `"canonical+preview"`).
5. **Frontend Playwright walk-through** (screenshot each step):
   - Login → OpsCenter tiles show non-null live prices for at least 3 assets.
   - Navigate to `/discovery` → at least 1 candidate row with a real signal.
   - Navigate to `/opportunities` → at least 1 canonical opportunity row.
   - Click the row → drawer shows real route + timeline entries.
6. **Load / stability**: leave the platform running for 12 hours; Discovery + Opportunity ticks continue without exception; `/api/arbicore/observability` reports no persistent errors.
7. Produce `docs/verification_v2.11/discovery_pipeline_e2e.md` with evidence.

If any of the 7 checks fail, we do not proceed to Stage 3 — instead we
diagnose the discovery pipeline failure and ship a follow-up patch on
`hotfix/discovery-*` first. This is the exact verification-first cadence
you requested.

---

## Stage 3 — Market Intelligence (P0)

Feeds the profitability layer with the truth about the venues we would
actually trade against.

### Runtime signals produced
- Live venue prices + depth (already partially wired via `_LIVE_SCANNER`).
- Live gas per chain (`/api/arbicore/execution/gas` — already real via `_GAS_ORACLE`).
- Fee provenance per venue (`services/execution/bdag_transfers.py`, `evidence_accuracy.py` already exist; wire through).
- Exchange health / capability / breaker state (`arbicore/routes/scanners.py:/venues/*` — 5 endpoints available to mount).
- Provider state / freshness (`/api/arbicore/providers/status` — already real).
- Liquidity / order book snapshots (`_LIVE_SCANNER.prices()` — real).

### Placeholder → canonical mapping

| Placeholder | Canonical | Fix recipe |
| :---------- | :-------- | :--------- |
| `GET /arbicore/operations/venues` (1319) — 9-row hardcoded | Mount `routes/venues.py:/venues/status` + `/venues/health` (real) | Delete stub; mount router with prefix `/api`. |
| Frontend `HomePage.jsx:65 Interlock ARMED` hardcoded literal | `_KILL.snapshot()` | Rewrite tile to consume `/api/arbicore/safety/status`. |
| Fee provenance UI in OperationsPage / IntelligencePage (currently uses stub) | `services/execution/bdag_transfers.py`, `evidence_accuracy.py`, `fee_provenance.py` (all exist) | Expose new lightweight endpoint `/arbicore/execution/fees/summary` that returns a rolled-up view. |
| `/arbicore/execution/venues` (existing stub) | `services/execution/venue_registry.py` (real) | Replace stub with `venue_registry.snapshot()`. |
| Exchange capability history | `scanners.py:/venues/{id}/capability-history` (real) | Mount + shape-adapt if IntelligencePage consumes. |

### Files touched
- `app/backend/server.py`: delete `operations/venues` stub (lines 1319–1334) and any other venue/fee stubs; mount `routes/venues.py`.
- `app/frontend/src/v2/pages/HomePage.jsx`: replace the hardcoded ARMED literal with data-driven state (0.25 d micro-fix).
- Optional: new tiny handler `/arbicore/execution/fees/summary` composing existing services.

### Verification checklist
1. `/venues/status` returns real capability list per venue.
2. HomePage Interlock tile shows correct state (toggle kill switch and observe tile flip).
3. Fees summary endpoint returns venue+chain-level fee breakdown that matches `execution_config.fees.*` in Mongo.

### Release: **v2.12 · Market Intelligence canonical activation** · effort ~3.5 dev-days.

---

## Stage 4 — Execution Planning / Readiness (P0)

Everything the operator needs to convert a certified opportunity into a
signed, ready-to-broadcast flash-loan plan — without any placeholder data.

### Placeholder → canonical mapping

Most of this pipeline is already wired (per §1 of the widget sweep):
`FlashLoanOperatorPage` and `ExecutorVerifyPage` call real endpoints
(`_KILL_SWITCH_REPO`, `_WALLET_REGISTRY`, `_SECRETS_REPO`,
`_EXECUTION_MODE_REPO`, `_EXECUTION_PLANS_REPO`, `_EXECUTION_CERTIFIER`,
`_LIMITED_LIVE_BROADCASTER`).

The remaining placeholders in this pipeline stage:

| Placeholder | Canonical | Fix recipe |
| :---------- | :-------- | :--------- |
| `GET /arbicore/execution/adapters` (2350) — likely hardcoded | `_EXECUTION_ADAPTERS_REGISTRY.snapshot()` if exists, else new tiny registry from `arbicore/execution/*.py` | Replace stub. |
| `GET /arbicore/execution/simulation/status` (2455) — hardcoded | `_SIMULATION_SERVICE.status()` (or return "unavailable" truthfully) | Real read. |
| Any residual planning-side stubs (audit by grep during this slice) | — | Case-by-case. |
| `GET /arbicore/roi-probability` (458) — hardcoded regardless of route_id | `arbicore/routes/arbicore.py:/outcomes?route_id=` (real, at line 171). Mount `arbicore/routes/arbicore.py` here. | Delegate. |

### Files touched
- `app/backend/server.py`: replace remaining execution-planning stubs; mount `arbicore/routes/arbicore.py` (adds ~20 real endpoints, no shadowing).
- No frontend changes.

### Verification checklist (end-to-end gate before Stage 5)
1. Take one opportunity from Stage 1's canonical list.
2. Frontend `/dashboard/flash-loan-operator`: build a plan against it (`POST /execution/plans/build`) — plan_id persisted in `execution_plans` collection.
3. Certify the plan (`POST /execution/plans/{id}/certify`) — certification passes/fails with **real** reasons.
4. Confirm the ROI probability shown alongside the plan matches `/arbicore/outcomes?route_id=` (real).
5. Broadcast is BLOCKED unless `execution_mode` is `LIMITED_LIVE` (real repo, real gate).

### Release: **v2.13 · Execution Planning canonical activation** · effort ~3 dev-days.

---

## Stage 5 — Dashboard / Executive Summary (P1)

Once stages 1–4 land, this becomes a small deliverable: HomePage tiles
(regime, deck, vitals) already have empty-state safety and read from
`/dashboard/pulse` + `/dashboard/deck` + `/opportunities/summary`. Only
the stub handlers need rewriting.

Details unchanged from v1 of the roadmap (see `CANONICAL_ACTIVATION_ROADMAP.md`
Slice 3). Effort ~2.25 dev-days.

### Release: **v2.14 · Home dashboard canonical activation.**

---

## Stage 6 — Portfolio (P1)

Split into two sub-releases:

### 6a — mount-only (safe, fast)
Balances + Deployable + Allocation — canonical `routes/portfolio.py` (195 LOC) already implements these. Mount + shape-adapt. Effort **~1.5 dev-days**.

### 6b — new repos (positions, transfers, ledger, exposure)
No canonical implementation yet. Options:
- Return empty until execution layer records positions (safe, truthful).
- Build lightweight `PositionsRepo` from open-execution-cycle scan.

Effort **~4 dev-days** if we build the repo, or **~1 dev-day** to return empty and update the UI to explain "no positions until execution cycles run".

### Release: **v2.15 · Portfolio (6a mount)** then **v2.16 · Portfolio (6b positions)**.

---

## Stage 7 — Operations / Monitoring (P2)

Cycles, venue detail, interlock, integrations, queues, alerts — details
unchanged from v1 of the roadmap. Effort ~5 dev-days.

Notable: alerts endpoint already exists at `routes/alerts.py:/alerts/log`
and the frontend already calls it. Mounting the router fixes 3 endpoints
in a single move.

### Release: **v2.17 · Operations canonical activation.**

---

## Stage 8 — Remaining informational (P3)

Intelligence Wave-1 completion + Settings verification + ancillary
de-stub. Combined effort ~7 dev-days across 3 releases (v2.18, v2.19,
v2.20).

---

## Cumulative timeline

| After | State |
| :---- | :---- |
| Pipeline stage 2 (v2.11) | Discovery → Opportunity Detection pipeline runs end-to-end on real data. **Mandatory pause + 7-check verification.** |
| Pipeline stage 4 (v2.13) | Full critical path is live: Market Data → Discovery → Opportunity → Route → Profitability → Execution Planning. **This is the state we can begin flash-loan paper validation from.** |
| Pipeline stage 6b (v2.16) | Portfolio surfaces truthful for the operator sizing next trades. |
| Pipeline stage 8 (v2.20) | Every placeholder removed. |

**Critical-path completion (paper validation ready): ~12 dev-days = ~2.5
weeks single-engineer.**

---

## What is NOT in this roadmap

- Changes to trading, arbitrage, scanner, validation, flash-loan, or
  execution business logic. Wiring existing endpoints to existing repos
  is not a logic change.
- Deletion of the dormant `arbicore/auth/__init__.py` (retained per
  surgical-hotfix policy).
- UI redesign. All frontend touches are pinpoint (HomePage Interlock only).
- New provider integrations. All live providers already run in the backend.

---

## Kickoff prerequisites (before Stage 1)

1. **v2.9.3 deployed to VPS** and admin created via `POST /api/auth/setup`.
2. `main` on VPS matches tag `v2.9.3`.
3. This roadmap + `EMPTY_STATE_WIDGET_SWEEP.md` reviewed & approved.
4. When ready, I'll open `hotfix/canonical-slice-1` off deployed `main`
   and begin Stage 1 (Opportunity Detection). No code writing until
   you say "start Stage 1".
