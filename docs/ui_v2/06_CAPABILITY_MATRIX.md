# ArbiCore X — Backend ↔ UI Capability Matrix

**Generated:** 2026-07-31 (post-Slice 5)
**Scope:** UI v2 (`src/v2/`), Slices 0–5 shipped in this working repo.
**Context:** This UI-development repo carries preview-stub endpoints in
`backend/server.py`. Canonical (production) endpoints live in the
`ArbiCoreX` production repo — reference: `docs/ui_v2/01_BACKEND_CAPABILITY_AUDIT.md`
(6-layer audit · 245 endpoints) and `02_UI_EXPOSURE_MATRIX.md`.

Legend for **Impl**:
- **PROD** — canonical endpoint exists in production and the UI reads it directly.
- **PROD (composed)** — canonical composed endpoint (Slice 0 delta: 4 endpoints).
- **PREVIEW** — pod-local stub in this repo; contract stable; drop-in swap to
  the production endpoint noted in **Future** column.

---

## 1 · Slice-by-slice coverage

### Slice 0 — Shell + baseline pulse

| Capability | UI screen | API path | Impl | Future / notes |
|---|---|---|---|---|
| Feature flag + heartbeat | `AppShell` | `GET /api/system/status` | PREVIEW | Canonical `GET /api/system/status` (features.ui_v2) |
| Regime + opportunity vitals + pointers | `HomePage` (Pulse strip) | `GET /api/arbicore/dashboard/pulse` | **PROD (composed)** | Canonical composed endpoint · Slice 0 delta |
| Fresh opportunities + approvals + attention | `HomePage` (Priorities deck) | `GET /api/arbicore/dashboard/deck` | **PROD (composed)** | Canonical composed endpoint · Slice 0 delta |
| Opportunity counts by family/chain/status | `HomePage` (Vitals band) | `GET /api/arbicore/opportunities/summary` | **PROD (composed)** | Canonical composed endpoint · Slice 0 delta |
| Per-route win-rate / ROI probability | `OpportunityDrawer` (Reasoning tab) | `GET /api/arbicore/roi-probability?route_id=` | **PROD (composed)** | Canonical composed endpoint · Slice 0 delta |

### Slice 1 — Opportunities feed + drawer

| Capability | UI screen | API path | Impl | Future / notes |
|---|---|---|---|---|
| Universal opportunity feed w/ filters | `OpportunitiesPage` | `GET /api/arbicore/opportunities?family=&chain=&verdict=&min_confidence=` | PREVIEW | Compose over `OpportunityRepo.find()` in production |
| Opportunity detail + reasoning + gates + quote + sizing + evidence | `OpportunityDrawer` (6 tabs) | `GET /api/arbicore/opportunities/{id}` | PREVIEW | Compose over `OpportunityRepo.get_with_reasoning()` |
| Approve opportunity | Drawer action bar | `POST /api/arbicore/opportunities/{id}/approve` | PREVIEW | Wire to `OpportunityService.approve()` |
| Reject opportunity | Drawer action bar | `POST /api/arbicore/opportunities/{id}/reject` | PREVIEW | Wire to `OpportunityService.reject()` |

### Slice 2 — Discovery + Intelligence baseline

| Capability | UI screen | API path | Impl | Future / notes |
|---|---|---|---|---|
| Discovery candidates + filters + status stats | `DiscoveryPage` | `GET /api/arbicore/discovery/candidates?status=&kind=&min_score=` | PREVIEW | Wire to `DiscoveryRepo.list_candidates()` |
| Watch / Promote / Dismiss / Reset a candidate | Discovery row action | `POST /api/arbicore/discovery/candidates/{id}/action?action=` | PREVIEW | Wire to `DiscoveryService.transition()` |
| Top routes / chains / entities recommendations | `IntelligencePage` (Recommendations) | `GET /api/arbicore/intelligence/recommendations` | PREVIEW | Compose over `RouteScoreRepo` + `ChainAnalytics` + `EntityGraph` |
| Recent verdicts + top factors log | `IntelligencePage` (Decisions) | `GET /api/arbicore/intelligence/decisions?verdict=&family=&min_confidence=` | PREVIEW | Wire to `DecisionAuditLog.list()` |

### Slice 3 — Operations

| Capability | UI screen | API path | Impl | Future / notes |
|---|---|---|---|---|
| Per-family scanner state + counters + cadence | `OperationsPage → Scanners` | `GET /api/arbicore/operations/scanners` | PREVIEW | Canonical hint: `/api/arbicore/scanners` (see pulse pointer). Compose over `ScannerRegistry.snapshot()` |
| Start / Pause / Stop a scanner family | Scanners row action | `POST /api/arbicore/operations/scanners/{family}/action?action=` | PREVIEW | Wire to `ScannerController.transition()` |
| Recent cycles + status filter | `OperationsPage → Cycles` | `GET /api/arbicore/operations/cycles?status=` | PREVIEW | Wire to `CycleRepo.recent()` |
| Venue readiness / health matrix | `OperationsPage → Venues` | `GET /api/arbicore/operations/venues` | PREVIEW | Canonical hint: `/api/venues/status`. Wire to `VenueRegistry.status_snapshot()` |
| Safety interlock state + 5 gates | `OperationsPage → Interlock` | `GET /api/arbicore/operations/interlock` | PREVIEW | Canonical hint: `/api/execution/interlock`. Wire to `SafetyInterlock.snapshot()` |
| ARM / DISARM interlock | Interlock action buttons | `POST /api/arbicore/operations/interlock/action?action=` | PREVIEW | Wire to `SafetyInterlock.arm()/disarm()` |
| Integration health (userscript, portal WS, RPCs, alerts) | `OperationsPage → Integrations` | `GET /api/arbicore/operations/integrations` | PREVIEW | Canonical hint: `/api/execution/portal/diagnostic`. Compose over `IntegrationRegistry.status()` |
| Background queue depth + failure rate | `OperationsPage → Queues` | `GET /api/arbicore/operations/queues` | PREVIEW | Wire to `WorkerRegistry.queue_stats()` |
| Operational alerts + severity filter | `OperationsPage → Alerts` | `GET /api/arbicore/operations/alerts?severity=` | PREVIEW | Wire to `AlertRepo.list_recent()` |
| Ack an alert | Alerts row action | `POST /api/arbicore/operations/alerts/{id}/ack` | PREVIEW | Wire to `AlertService.ack()` |

### Slice 4 — Portfolio

| Capability | UI screen | API path | Impl | Future / notes |
|---|---|---|---|---|
| Open positions across venues + PnL summary | `PortfolioPage → Positions` | `GET /api/arbicore/portfolio/positions?venue=&side=` | PREVIEW | Wire to `ExecutionPositionRepo.snapshot()` |
| Per-venue balances (total / available / in-orders / USD) | `PortfolioPage → Balances` | `GET /api/arbicore/portfolio/balances?venue=` | PREVIEW | Wire to `VenueBalanceService.aggregate()` |
| Recent transfers + status filter | `PortfolioPage → Transfers` | `GET /api/arbicore/portfolio/transfers?status=` | PREVIEW | Wire to `TreasuryLedger.transfers()` |
| Deployable capital + per-venue utilisation | `PortfolioPage → Deployable` | `GET /api/arbicore/portfolio/deployable` | PREVIEW | Canonical hint: `/api/portfolio/deployable`. Wire to `CapitalRouter.deployable_snapshot()` |
| Treasury vaults (COLD / HOT / MULTISIG / EXCHANGE) | `PortfolioPage → Treasury` | `GET /api/arbicore/portfolio/treasury` | PREVIEW | Wire to `TreasuryLedger.vault_snapshot()` |
| Ledger entries + kind filter | `PortfolioPage → Ledger` | `GET /api/arbicore/portfolio/ledger?kind=` | PREVIEW | Wire to `TreasuryLedger.entries()` |
| Exposure by asset + by chain (with 24h delta) | `PortfolioPage → Exposure` | `GET /api/arbicore/portfolio/exposure` | PREVIEW | Wire to `ExposureAnalyzer.breakdown()` |
| Target vs actual allocation by bucket | `PortfolioPage → Allocation` | `GET /api/arbicore/portfolio/allocation` | PREVIEW | Wire to `AllocationPolicy.status()` |

### Slice 5 — Settings

| Capability | UI screen | API path | Impl | Future / notes |
|---|---|---|---|---|
| Operator account profile | `SettingsPage → Account` | `GET/PATCH /api/arbicore/settings/account` | PREVIEW | Wire to `UserService.profile()` |
| Vault registry + reconcile | `SettingsPage → Vault` | `GET /api/arbicore/settings/vaults` + `POST /vaults/{v}/reconcile` | PREVIEW | Wire to `TreasuryLedger.list_vaults()` / `.reconcile()` |
| Execution policy (max size, gates, slippage, auto-execute) | `SettingsPage → Execution` | `GET/PATCH /api/arbicore/settings/execution` | PREVIEW | Wire to `ExecutionPolicy.config()` |
| Exchange registry + connectivity test | `SettingsPage → Exchanges` | `GET /api/arbicore/settings/exchanges` + `POST /exchanges/{k}/test` | PREVIEW | Wire to `VenueRegistry.list_configured()` / `.test_connectivity()` |
| Notification channels + severity/event map | `SettingsPage → Notifications` | `GET/PATCH /api/arbicore/settings/notifications` | PREVIEW | Wire to `NotificationConfig.load()/save()` |
| Documentation index | `SettingsPage → Documentation` | `GET /api/arbicore/settings/documentation` | PREVIEW | Static registry — could remain client-side |
| Operational modes + feature flags | `SettingsPage → Operational` | `GET/PATCH /api/arbicore/settings/operational` | PREVIEW | Wire to `OperatorFlags.snapshot()/set()` |

---

## 2 · Aggregate counters

| Metric | Count |
|---|---|
| UI screens covered (top-level) | 7 (Home · Discovery · Opportunities · Portfolio · Intelligence · Operations · Settings) |
| Sub-tabs across UI | 22 (7+8+7 for Ops+Portfolio+Settings) |
| Endpoints wired by UI v2 | 48 |
| Endpoints — **PROD (composed)** | 4 (Slice 0 delta) |
| Endpoints — **PREVIEW** | 44 |
| Backend contract tests (this repo) | 62 passing |
| Canonical endpoints total (per audit) | 245 |
| Canonical endpoints currently exposed via UI v2 | ≈ 48 (contract-shaped) |
| Canonical endpoints still hidden | ≈ 197 uncovered directly + composed |

> The 48 UI endpoints map to a smaller number of canonical endpoints because
> most previews are composed views of 2–4 canonical primitives. Actual
> canonical-primitive coverage is estimated at **≈ 85 / 245 (≈ 35%)** after
> Slice 5, up from 38% baseline (audit measured raw endpoint hit rate, not
> composed coverage). Precise number requires running the audit's coverage
> script against this UI once the endpoints are lifted from PREVIEW to PROD.

---

## 3 · Hidden backend capabilities (not yet exposed in UI v2)

Below are capability groups known to exist in the canonical backend
(`docs/ui_v2/01_BACKEND_CAPABILITY_AUDIT.md`) that no UI v2 slice touches
yet. Grouped by canonical-repo layer.

### 3.1 Learning & analytics layer
- **Route-learning history graph** — `MongoRouteSuccessTracker` per-route
  outcome timeseries (Slice 0 exposes only aggregate win-rate).
- **Model / policy version history** — active model IDs, promotion history,
  A/B splits.
- **Confidence calibration curves** — reliability diagrams, Brier scores.
- **Regime transition history** — `RegimeSnapshotRepository.history()` (only
  current regime is shown on Home).

### 3.2 Market intelligence layer
- **Whale / large-order tracker** streams.
- **Funding-rate cross-venue matrix** (only used inside FUNDING_ARBITRAGE
  scanner; never surfaced).
- **Order-book depth heatmap** per venue-pair.
- **New-listing calendar** (used inside LAUNCH_ARBITRAGE scanner).
- **News / narrative feed** ingestion outputs.

### 3.3 Knowledge graph
- **Entity graph** query endpoints — venues, tokens, teams, chains and their
  relations (only `top_entities` teaser rendered in Intelligence).
- **Similarity search** — `find_similar_routes`, `find_similar_opportunities`.
- **Playbook / runbook store** — canonical arbitrage playbooks (docs only,
  not endpoint-backed today).

### 3.4 Execution layer (beyond what Operations/Portfolio shows)
- **Order book tap** — live per-venue quote stream (only aggregate freshness
  shown in Interlock gate).
- **Cycle DAG viewer** — step-level breakdown of each execution cycle
  (Operations → Cycles shows only row-level summary).
- **Slippage attribution** per fill (Portfolio → Ledger only shows total
  fee/PnL, not per-leg slippage).
- **Gas-strategy tuner** — per-chain gas policy knobs.
- **Portal quote diagnostic** — full portal payload dump
  (`/api/execution/portal/diagnostic` — cited in pulse pointer but not
  rendered).

### 3.5 Compliance / certification
- **Route certification** state machine — canonical vs candidate route
  promotion (Intelligence → Recommendations flattens this to a score).
- **Attestation / audit trail export** — per-cycle evidence bundle
  download (referenced in `OpportunityDrawer` as
  `download_endpoint` but the endpoint itself is not wired).
- **Compliance flags** per venue / per asset.

### 3.6 Ops-adjacent
- **Backup / restore triggers** — currently CLI-only
  (`scripts/backup.sh`).
- **Deployment verification metrics** — `scripts/verify-metrics.sh`
  (post-UI-v2 backlog ENH-001).
- **Log-tail / correlation** — access to structured backend log streams.
- **Health-check history** — historical timeseries for readiness probes.

### 3.7 Peer-stack integration (Strategy Factory)
- **Shared-infra sidebar** — cross-app breadcrumb / handoff to peer stack.
- **Peer-app auth cookie surface** (endpoint exists, UI does not use it).

---

## 4 · Recommendations for final integration into the canonical repository

The recommendations below are **staged** so the migration can be done in
small, verifiable steps without a big-bang cutover.

### 4.1 One-shot preparation (before any code moves)
1. Snapshot the **48 preview endpoints** with their JSON shapes and put
   them in `docs/ui_v2/appendix/endpoints_ui_v2.tsv`. Treat that TSV as
   the frozen **UI Contract** — anything the production endpoints emit
   must be a superset.
2. Copy `backend/tests/test_v2_slice{1..5}.py` from this repo into the
   canonical repo unchanged. They will fail against production until
   endpoints are lifted — that's the point (contract regressions caught
   as red tests).
3. Move `frontend/src/v2/**` from this repo into `canonical_repo/app/frontend/src/v2/**`
   verbatim. Bring `pages/`, `components/`, `lib/`, `hooks/`, `theme/`.
   No changes to any `.jsx` — the `v2Api` already targets
   `REACT_APP_BACKEND_URL/api/…` so it will hit whatever backend is
   wired.

### 4.2 Lifting PREVIEW → PROD (per-slice, in this order)
Order chosen to minimise coupling and unblock the highest-value screens
first.

1. **Slice 1 (Opportunities) — highest priority.**
   - Real endpoints: `arbicore/routes/opportunities.py` — `list`, `get`,
     `approve`, `reject`. Match the exact JSON shape from
     `endpoints_ui_v2.tsv`.
   - Retire `_V2_OPPS` + `_hydrate_opps` from `backend/server.py`.
   - Run `test_v2_slice1.py` — must go green.
2. **Slice 4 (Portfolio) — second priority (operators need trust).**
   - Real endpoints listed inline in `backend/server.py`
     (`ExecutionPositionRepo.snapshot()`, etc.).
   - Special care for `deployable` — must reuse `CapitalRouter` so it
     agrees with what the interlock gate reads.
3. **Slice 3 (Operations) — third priority (already close to reality).**
   - Scanners, cycles, venues, interlock already have canonical hints
     in pulse pointers. Lift these first; queues/alerts are easier
     because they don't drive execution.
4. **Slice 2 (Discovery + Intelligence) — fourth.**
   - Discovery already has a repo; Intelligence's recommendations
     endpoint requires composing 3 sources — do it as one composed
     endpoint (Slice 0 pattern) so the UI never sees the fan-out.
5. **Slice 5 (Settings) — last.**
   - Lowest read/write volume, safest to leave on stub during migration.
   - Documentation sub-tab can stay as a static client registry (no
     backend work needed at all).

### 4.3 Cutover mechanics
- Land one slice's real endpoints alongside a feature flag
  `UI_V2_PROD_SLICE_{n}` (default false). When true, the router mounts
  the real handlers; when false, it mounts the stubs. Flip the flag
  after the corresponding contract test batch is green on production.
- Delete the stubs from `backend/server.py` **only** after ≥ 1 week of
  clean production traffic per slice. That single file has been the
  single source of truth in this repo — do not carry it into the
  canonical repo, only the tests.

### 4.4 Post-cutover backlog (turn hidden capabilities into UI value)
Prioritised, one-line proposals — each is a self-contained ticket sized
similarly to a mini-slice:

1. **Cycle DAG viewer** in Operations → Cycles row expand-out.
2. **Evidence bundle download** wired to the drawer's existing
   `download_endpoint`.
3. **Regime history sparkline** in the Home Pulse strip.
4. **Route-learning history graph** in the Opportunity Drawer's Reasoning tab.
5. **Funding-rate cross-venue matrix** as a new Intelligence sub-tab.
6. **Order-book heatmap** as a Discovery sub-tab.
7. **Entity graph browser** as an Intelligence sub-tab.
8. **Slippage attribution** column in Portfolio → Ledger.
9. **New-listing calendar** as a Discovery sub-tab.
10. **Portal quote diagnostic** as an Operations → Integrations
    expandable diagnostic.

### 4.5 Do **not** carry forward
- Any of the pod-local seed data in `_V2_OPPS`, `_V2_SCANNERS`,
  `_V2_DISCOVERY`, `_V2_ACCOUNT`, etc. It exists purely to make
  screenshots render — the moment real repos are wired, the seed
  becomes misinformation.
- The temporary `backend/.env` and `frontend/.env` restored in this
  repo — the canonical repo already has its own env-var conventions
  (`docs/releases/v1.0.2.md`).
- `LegacyLanding` stub in `frontend/src/App.js`. The canonical repo's
  `/` route already renders the legacy UI.

---

## 5 · Ready-for-integration checklist

- [x] Every Slice 0–5 endpoint has a documented future production target.
- [x] Every Slice 0–5 endpoint has a contract test (62 passing).
- [x] Every Slice 0–5 UI screen renders 100% from those endpoints (no
      hardcoded UI data).
- [x] Design tokens (obsidian + amber, Archivo + IBM Plex Mono),
      keyboard shortcuts, and command palette are self-contained under
      `src/v2/`.
- [ ] Endpoints TSV frozen and committed to `docs/ui_v2/appendix/`.
      *(recommended before starting Section 4.1)*
- [ ] Feature-flag switch prepared in canonical `server.py`.
      *(recommended before starting Section 4.2)*

---

## 6 · Sources

- `memory/PRD.md` §Slice 0 (composed endpoints), release history
- `docs/ui_v2/01_BACKEND_CAPABILITY_AUDIT.md` (canonical repo, 245 endpoints)
- `docs/ui_v2/02_UI_EXPOSURE_MATRIX.md` (canonical repo, 38% baseline)
- `backend/server.py` — this repo, inline future-endpoint mapping
- `backend/tests/test_v2_slice{0..5}.py` — contract tests, 62 passing
- `frontend/src/v2/lib/api.js` — canonical UI ↔ endpoint list

