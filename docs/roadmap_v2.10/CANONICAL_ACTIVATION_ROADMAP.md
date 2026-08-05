# Canonical Runtime Activation Roadmap
## From preview-stub to real runtime data — slice-by-slice plan

**Baseline:** post-v2.9.3 (auth hotfix deployed)
**Prepared:** 2026-08-05
**Scope:** replace every placeholder value on every dashboard with real
runtime data sourced from live providers, Mongo, or runtime state.
**Non-goals:** UI redesign; changes to trading, arbitrage, scanner,
validation, flash-loan, or execution logic; deleting dormant modules.

---

## Executive summary

- **187** placeholder endpoints in `app/backend/server.py` return hardcoded
  arrays (`_V2_OPPS`, `_V2_DISCOVERY`, `_V2_SCANNERS`, `_V2_ACCOUNT`, etc.).
- **213** canonical, real-data endpoints already exist in the repo across:
  - `app/backend/arbicore/routes/arbicore.py`   (regime, entities, learning, opportunities, provenance, shadow) — 480 LOC
  - `app/backend/arbicore/routes/opportunity_center.py` (wallets, analytics, funnels, audit) — 298 LOC
  - `app/backend/arbicore/routes/scanners.py`   (cex_arb, funding_arb, dex_arb, launch_arb, discovery, venues) — 1273 LOC
  - `app/backend/routes/execution.py`           (cycles, config, exchanges, integration) — 1079 LOC
  - `app/backend/routes/portfolio.py`           (balances, deployable, allocation, health) — 195 LOC
  - `app/backend/routes/venues.py`              (status, health, prices, depth, readiness, alerts, intelligence) — 149 LOC
  - `app/backend/routes/alerts.py`, `portal.py`, `vault.py`, `observation.py` — 51 – 40 LOC each
- **Only 2** direct path collisions between stubs and canonical:
  - `/api/arbicore/opportunities` (list) — needs a shape adapter
  - `/api/arbicore/discovery/candidates` (list) — needs a shape adapter
- All other canonical endpoints are additive; mounting them does not shadow
  a stub. Removing stubs happens surgically per slice.

**Consequence:** the activation work is *much* less risky than "rewrite
everything". It is a sequence of small, verifiable slices — each one:
1. Mounts a canonical sub-router.
2. Deletes the matching stub block(s) from `server.py`.
3. Reconciles path collisions with a thin translator.
4. Verifies frontend rendering with empty-and-populated Mongo.
5. Ships as its own tagged release with rollback.

---

## Rankings

### Operational importance (impact on paper-trading validation)

| Rank | Slice | Rationale |
| :--- | :---- | :-------- |
| **P0** | **Opportunity Center**            | The single most critical dashboard. Operators approve / reject opportunities from here. Fake opportunities cause fake decisions. |
| **P0** | **Scanner / Discovery**           | Feeds the Opportunity Center. If scanners report fake `opps_1h` / `errors_1h`, the operator cannot judge which discovery families are healthy. |
| **P1** | **Dashboard / Executive Summary** | Home + OpsCenter tiles: regime, vitals, deck, ROI probability, system status banner. Sets the operator's mental model at every login. |
| **P1** | **Portfolio**                     | Positions, balances, deployable capital, transfers. If wrong, the operator sizes trades against phantom capital. |
| **P2** | **Operations / Monitoring**       | Scanner control, cycles, venues, interlock, integrations, queues, alerts. Critical for platform health but not for individual trade decisions. |
| **P2** | **Intelligence**                  | Calibration, adaptive weights, evidence, certification. Adjacent to trade decisions but consumed indirectly. |
| **P3** | **Settings / Configuration**      | Account, notifications, vault, execution config. Config surfaces; already partly wired to real repos. |
| **P3** | **Ancillary informational**       | Documentation, release manifest, docs bundle. Static/read-only. |

### Technical risk

| Risk factor | Level |
| :---------- | :---- |
| Path collisions                    | **Low** (2 of 213 canonical endpoints) |
| Response shape drift               | **Medium** (canonical returns different shapes than stubs) |
| Auth requirement change (`require_auth` on every canonical endpoint) | **Medium** (frontend will need cookie session for every canonical call; this is already true post-v2.9.3) |
| Empty-state frontend rendering     | **Medium** (some widgets don't handle `items: []`) |
| Live provider dependency            | **Low** (canonical repos read from Mongo, not from live provider calls at request time) |

---

## Master activation table

Format: `Slice · Placeholder endpoint → Canonical endpoint · Files to touch · Frontend consumers · Effort · Priority`

### SLICE 1 — Opportunity Center (P0)

| Placeholder endpoint | Canonical replacement | Files to mount/edit | Frontend consumers | Effort |
| :--- | :--- | :--- | :--- | :--- |
| `GET /api/arbicore/opportunities` (server.py:537) — reads canonical + merges hardcoded `_V2_OPPS` | Already partially live via `_CANONICAL_OPP_REPO`. **DELETE `_V2_OPPS` merge branch.** Optionally also mount `arbicore/routes/arbicore.py:/opportunities` (different shape) as a v2 alias. | `server.py:481–635` (delete `_V2_OPPS`, `_hydrate_opps`, merge branch; keep translator `_canonical_opp_to_contract`) | `v2/pages/OpportunitiesPage.jsx`, `v2/pages/OpsCenter.jsx`, `v2/api/*.js`, `opportunity_center/*` | **0.5 day** |
| `GET /api/arbicore/opportunities/{id}` (server.py:638) — hybrid | Delete preview fallback, return 404 when not in canonical repo | `server.py:638–710` | `OpportunityDrawer.jsx`, `OpportunitiesPage.jsx` | **0.25 day** |
| `POST /api/arbicore/opportunities/{id}/approve` (server.py:711) — hybrid, mutates in-memory list | Restrict to canonical repo write; drop in-memory branch | `server.py:711–737` | `OpportunitiesPage.jsx`, keyboard shortcut `[A]` | **0.25 day** |
| `POST /api/arbicore/opportunities/{id}/reject` (server.py:738) — same | Same | `server.py:738–767` | Keyboard shortcut `[R]` | **0.25 day** |
| `GET /api/arbicore/opportunities/{id}/timeline` (server.py:768) — likely hybrid | Replace with `OpportunityJournal.timeline(opp_id)` (real; already exists) | `server.py:768–~855` | `OpportunityDrawer.jsx` timeline panel | **0.5 day** |
| `GET /api/arbicore/opportunities/summary` (server.py:447) — hardcoded `{total:14, by_family:{…}, by_chain:{…}, by_status:{…}}` | Aggregate over `_CANONICAL_OPP_REPO.find({})` grouped by `.opportunity_type`, `.chain`, `.status` | `server.py:447–455` | Header badge in `AppShell.jsx`, `OpsCenter` summary card | **0.5 day** |

**Slice 1 total effort:** ~2.25 dev-days · **P0**
**Slice 1 empty-state:** with no discovery running, list is empty → frontend must render an empty state (already does via `no_data_or_error` branch in `OpportunitiesPage.jsx:139`).
**Slice 1 deployable name:** `v2.10 — Opportunity Center canonical activation`

---

### SLICE 2 — Scanner / Discovery (P0)

| Placeholder endpoint | Canonical replacement | Files to mount/edit | Frontend consumers | Effort |
| :--- | :--- | :--- | :--- | :--- |
| `GET /api/arbicore/operations/scanners` (server.py:1275) — 8 hardcoded scanner rows | **Mount** `app/backend/arbicore/routes/scanners.py`. Aggregate `/scanners/{family}/status` responses OR add a new `/operations/scanners` aggregator that fans out to `cex_arb`, `funding_arb`, `dex_arb`, `launch_arb`. | `server.py:1263–1290` (delete `_V2_SCANNERS`); `scanners.py` mount block near line 3517 | `v2/pages/OperationsPage.jsx`, `v2/pages/OpsCenter.jsx` scanner panel | **1 day** |
| `POST /api/arbicore/operations/scanners/{family}/action` (server.py:1284) — mutates in-memory list | Route to canonical `/scanners/{family}/kill` and `/scanners/{family}/resume` (already exist for cex_arb, funding_arb, dex_arb, launch_arb) | `server.py:1284–1290`; add per-family action dispatcher | Same as above | **0.5 day** |
| `GET /api/arbicore/discovery/candidates` (server.py:903) — hardcoded 7 candidates + fabricated calibration | **Path collision.** Canonical `/discovery/candidates` exists in `scanners.py:370`. Delete stub; add shape translator if response shape differs. | `server.py:858–946`; `scanners.py:370` | `v2/pages/DiscoveryPage.jsx`, `DiscoveryPage` calibration panel | **1 day** (shape work) |
| `POST /api/arbicore/discovery/candidates/{id}/action` (server.py:939) — in-memory mutation | Use `scanners.py` `discovery/candidates/{id}` endpoint or persist to `discovery_candidates` collection with a real state machine | `server.py:939–946` | `DiscoveryPage` action buttons | **0.5 day** |
| `GET /api/arbicore/discovery/queue/status` (frontend does NOT call yet) | Already canonical (`scanners.py:340`). Additive — mount and expose. | `scanners.py` (mount only) | Future OpsCenter monitoring | **0.25 day** |

**Slice 2 total effort:** ~3.25 dev-days · **P0**
**Slice 2 empty-state:** with no scanners running, per-family status returns `{state:"IDLE", opps_1h:0}` — must NOT be shown as "fake data" but as truthful zero counts.
**Slice 2 deployable name:** `v2.11 — Scanner / Discovery canonical activation`

---

### SLICE 3 — Dashboard / Executive Summary (P1)

| Placeholder endpoint | Canonical replacement | Files to mount/edit | Frontend consumers | Effort |
| :--- | :--- | :--- | :--- | :--- |
| `GET /api/arbicore/dashboard/pulse` (server.py:396) — hardcoded regime CALM, vitals, tracked_routes: 47 | Compose from `arbicore/routes/arbicore.py:/regime/latest` + `/route-stats` + opportunities aggregate. | `server.py:396–419` | `HomePage.jsx`, `OpsCenter.jsx` pulse tiles | **1 day** |
| `GET /api/arbicore/dashboard/deck` (server.py:422) — 5 hardcoded opportunities | Read fresh CANDIDATE/APPROVED opps from `_CANONICAL_OPP_REPO`, plus `_OPPORTUNITY_JOURNAL.pending_approvals()` and `_OPPORTUNITY_JOURNAL.requires_attention()` (both exist). | `server.py:422–444` | `OpsCenter.jsx` deck | **0.5 day** |
| `GET /api/arbicore/roi-probability?route_id=…` (server.py:458) — hardcoded regardless of route_id | Delegate to `arbicore/routes/arbicore.py:/outcomes?route_id=…` (real, already exists at line 171) | `server.py:458–468` | `OpsCenter.jsx` ROI panel | **0.5 day** |
| `GET /api/system/status` (server.py:471) — `{"features":{"ui_v2":true},"preview":true}` | Return `{preview: false, features: OperationalFlagsRepo.snapshot()}` — but keep the `preview` field to allow future degraded modes. | `server.py:471–476` | Global preview banner logic (once we add it — but per your instruction, no banner is being built) | **0.25 day** |

**Slice 3 total effort:** ~2.25 dev-days · **P1**
**Slice 3 deployable name:** `v2.12 — Dashboard canonical activation`

---

### SLICE 4 — Portfolio (P1)

Currently the most dangerous slice: hardcoded balances, positions, transfers make the operator believe there is 20+ ETH and 2.5 BTC in a cold wallet.

| Placeholder endpoint | Canonical replacement | Files to mount/edit | Frontend consumers | Effort |
| :--- | :--- | :--- | :--- | :--- |
| `GET /api/arbicore/portfolio/positions` (server.py:1424) — 6 hardcoded positions | No canonical `positions` endpoint yet. Requires: (a) new repo pulling open positions from exchange integrations, OR (b) return empty until execution layer records positions. | `server.py:1424–1452`; new `PositionsRepo` OR return `{items: []}` | `PortfolioPage.jsx` positions tab | **2 days** (real repo) OR **0.5 day** (return empty and let frontend handle) |
| `GET /api/arbicore/portfolio/balances` (server.py:1455) — hardcoded balances | **Mount** `routes/portfolio.py:/portfolio/balances` (real; queries `WalletRegistry` + venue APIs) | `server.py:1455–1472`; mount `portfolio.py` | `PortfolioPage.jsx` balances tab | **1 day** (mount + shape adapt) |
| `GET /api/arbicore/portfolio/transfers` (server.py:1475) — 6 hardcoded transfers | Read from `transfer_ledger` collection (populated by execution layer). Return empty if not populated. | `server.py:1475–1498` | `PortfolioPage.jsx` transfers tab | **1 day** |
| `GET /api/arbicore/portfolio/deployable` (server.py:1501) — 6 hardcoded per-venue | **Mount** `routes/portfolio.py:/portfolio/deployable` (real; existing 30-line implementation) | `server.py:1501–1523` | `OpsCenter` capital tile, `PortfolioPage` | **0.5 day** |
| `GET /api/arbicore/portfolio/treasury` (server.py:1524) — hardcoded | Return sum of `cold_wallet` balances from `WalletRegistry` | `server.py:1524–1535` | `PortfolioPage.jsx` treasury card | **0.5 day** |
| `GET /api/arbicore/portfolio/ledger` (server.py:1536) — hardcoded | Aggregate `LedgerRepo` (execution layer already writes to it) | `server.py:1536–1551` | `PortfolioPage.jsx` ledger tab | **1 day** |
| `GET /api/arbicore/portfolio/exposure` (server.py:1552) — hardcoded | Derive from positions × marks | `server.py:1552–1572` | Exposure widget | **0.5 day** |
| `GET /api/arbicore/portfolio/allocation` (server.py:1573) — hardcoded | **Mount** `routes/portfolio.py:/portfolio/allocation` (real) | `server.py:1573–1585` | Allocation pie chart | **0.5 day** |

**Slice 4 total effort:** ~7.5 dev-days · **P1** (positions/ledger/transfers are the largest sub-slices; consider splitting into 4a and 4b)
**Slice 4 deployable name:** `v2.13 — Portfolio canonical activation`

---

### SLICE 5 — Operations / Monitoring (P2)

| Placeholder endpoint | Canonical replacement | Files to mount/edit | Frontend consumers | Effort |
| :--- | :--- | :--- | :--- | :--- |
| `GET /api/arbicore/operations/cycles` (server.py:1293) — 6 hardcoded cycles | **Mount** `routes/execution.py:/cycles` (real; queries `execution_cycles` collection); shape-adapt if needed | `server.py:1293–1316`; mount `execution.py` at prefix `/api/execution` (already prefixed; check for collisions with `/execution/*` stubs) | `OperationsPage.jsx` cycles tab | **1 day** |
| `GET /api/arbicore/operations/venues` (server.py:1319) — 9+ hardcoded venue rows | **Mount** `routes/venues.py:/venues/status` + `/venues/health` (real) | `server.py:1319–1330+`; mount `venues.py` | `OperationsPage.jsx` venues tab, `OpsCenter` venue readiness tile | **1 day** |
| `GET /api/arbicore/operations/interlock` (server.py:1335) — hardcoded | Compose from `KillSwitchRepo.snapshot()` + `_SAFETY_AVAILABLE` + `runtime_config`. `KillSwitchRepo` already exists. | `server.py:1335–1352` | `OperationsPage.jsx` interlock, `FlashLoanOperatorPage.jsx` kill switch | **0.5 day** |
| `POST /api/arbicore/operations/interlock/action` (server.py:1353) — hardcoded response | Delegate to `_KILL.engage/disengage` (real; already used by `/safety/kill/{engage,disengage}`) | `server.py:1353–1357` | Interlock buttons | **0.25 day** |
| `GET /api/arbicore/operations/integrations` (server.py:1358) — hardcoded | Snapshot from provider registry + telegram + evidence-signer + secrets manager | `server.py:1358–1372` | `OperationsPage.jsx` integrations tab | **1 day** |
| `GET /api/arbicore/operations/queues` (server.py:1373) — hardcoded | Query internal queues (calibration_queue, learning_queue, discovery_queue, broadcast_queue) sizes | `server.py:1373–1386` | `OperationsPage.jsx` queues tab | **0.5 day** |
| `GET /api/arbicore/operations/alerts` (server.py:1387) — hardcoded | **Mount** `routes/alerts.py:/alerts/log` (real; queries `alerts_log` collection). Frontend already calls `/alerts/log`. | `server.py:1387–1399` | `OperationsPage.jsx` alerts tab | **0.5 day** |
| `POST /api/arbicore/operations/alerts/{id}/ack` (server.py:1400) — hardcoded response | Set `acked_at` on `alerts_log` doc | `server.py:1400–1405` | Ack button | **0.25 day** |

**Slice 5 total effort:** ~5 dev-days · **P2**
**Slice 5 deployable name:** `v2.14 — Operations / Monitoring canonical activation`

---

### SLICE 6 — Intelligence (Wave-1 completion) (P2)

Currently a mixed state — some endpoints call real workers, others fabricate summaries.

| Placeholder endpoint | Canonical replacement | Effort |
| :--- | :--- | :--- |
| `GET /api/arbicore/intelligence/recommendations` (server.py:949) | `arbicore/routes/arbicore.py:/route-stats` + top-N slicer | **0.5 day** |
| `GET /api/arbicore/intelligence/decisions` (server.py:975) | `_OPPORTUNITY_JOURNAL.decisions(limit)` (exists) | **0.5 day** |
| `GET /api/arbicore/intelligence/calibration` (server.py:1037) | Delegate to `CalibrationWorker.snapshot()` (partly wired) | **0.5 day** |
| `GET /api/arbicore/intelligence/models` (server.py:1094) | Delegate to `ModelRegistry.list()` | **0.5 day** |
| `GET /api/arbicore/intelligence/certification` (server.py:1134) | Delegate to `EvidenceCertifier.summary()` | **0.5 day** |
| `GET /api/arbicore/intelligence/entities` (server.py:1204) | Redirect to canonical `arbicore/routes/arbicore.py:/entities` (mount that router) | **0.25 day** |
| `GET /api/arbicore/intelligence/{calibration,weights,evidence}/history` (server.py:1810–1954) | Delegate to worker history queries (some already exist) | **1 day** |

**Slice 6 total effort:** ~4 dev-days · **P2**
**Slice 6 deployable name:** `v2.15 — Intelligence Wave-1 completion`

---

### SLICE 7 — Settings / Configuration (P3)

Already partly wired. This slice is small — mostly verifying and de-stubbing the `_V2_ACCOUNT`, `_V2_EXECUTION`, `_V2_NOTIFICATIONS`, `_V2_OPERATIONAL` fallback dicts.

| Placeholder | Status | Effort |
| :--- | :--- | :--- |
| `/settings/account`, `/settings/execution`, `/settings/notifications`, `/settings/operational` | Reads/writes real `OperatorAccountRepo`, `ExecutionSettingsRepo`, etc. (partially). Verify each handler; delete dead fallback dicts. | **1 day** |
| `/settings/exchanges`, `/settings/vaults`, `/settings/documentation` | Mixed — some real, some documentation-static | **1 day** |

**Slice 7 total effort:** ~2 dev-days · **P3**
**Slice 7 deployable name:** `v2.16 — Settings verification & de-stub`

---

### SLICE 8 — Ancillary / informational (P3)

- `docs-package/*` endpoints
- Release manifest endpoints (`arbicore/routes/opportunity_center.py:/release/*`)
- Any leftover read-only informational endpoints

**Slice 8 total effort:** ~1 dev-day · **P3**
**Slice 8 deployable name:** `v2.17 — Ancillary de-stub`

---

## Total budget

| Slice | Effort | Priority | Cumulative |
| :---- | :----- | :------- | :--------- |
| v2.10  Opportunity Center               | 2.25 d | P0 |  2.25 d |
| v2.11  Scanner / Discovery              | 3.25 d | P0 |  5.50 d |
| v2.12  Dashboard / Executive Summary    | 2.25 d | P1 |  7.75 d |
| v2.13  Portfolio                        | 7.50 d | P1 | 15.25 d |
| v2.14  Operations / Monitoring          | 5.00 d | P2 | 20.25 d |
| v2.15  Intelligence Wave-1 completion   | 4.00 d | P2 | 24.25 d |
| v2.16  Settings verification            | 2.00 d | P3 | 26.25 d |
| v2.17  Ancillary de-stub                | 1.00 d | P3 | 27.25 d |

**Total: ~27 developer-days of focused work**, delivered as 8 tagged releases each shipping independently. Assuming a single engineer working full-time with QA on each release, roughly **6–8 calendar weeks** end to end. Two engineers in parallel (one on P0, one on P1) can compress to ~4 weeks.

---

## Per-slice deployment template

Each slice ships as its own tagged release using the identical procedure you approved for v2.9.3:

1. Branch `hotfix/canonical-slice-N` off `main` (which is at previous v2.10.k).
2. Apply the mount + delete-stub + shape-adapt patch.
3. Run backend curl smoke against a fresh `arbicore_x` (empty repos) + a
   seeded `arbicore_x` (real discovery having run for at least an hour).
4. Frontend Playwright smoke: for each affected page, load → assert
   empty-state renders when Mongo is empty; assert real rows render when
   Mongo has data.
5. Write per-slice `docs/RELEASE_NOTES_v2.N.md` with the same 9-section
   template we used for v2.9.3 (canonical, duplicates, breaking, verify,
   deploy, rollback).
6. Tag `v2.N-rc.1` on the branch; deploy to staging; 24h burn-in.
7. If green, ff-merge into `main`, tag `v2.N`, deploy to production.

---

## Empty-state contract (applies to every slice)

**Rule:** if a canonical repository has no data, the endpoint MUST return
an empty structure, NOT fake data:

```json
{ "items": [], "total": 0, "generated_at": "…" }
```

**Frontend rule:** every widget must handle `items: []` with a truthful
"No data yet — <reason>" empty state, not with an infinite spinner or a
fake row. Widgets that currently assume data is always present:
- `OpsCenter.jsx` regime tile (needs "Regime not yet computed" state)
- `PortfolioPage.jsx` positions tab (needs "No open positions" state)
- `OpsCenter.jsx` deck (needs "No fresh opportunities" state)

These frontend empty-state fixes are folded into their respective slices.

---

## What is intentionally EXCLUDED from this roadmap

- Any change to scanners, arbitrage logic, validation engines, flash-loan
  logic, or execution logic. Wiring existing endpoints to existing repos
  is not a logic change.
- Deletion of the dormant `arbicore/auth/__init__.py` (superseded by
  canonical auth but left on-disk per the surgical-hotfix policy).
- Any UI redesign. All frontend changes are limited to empty-state handling
  where the widget currently blanks on empty data.
- Any provider changes. Live providers already run inside the backend;
  the roadmap only exposes their outputs via canonical endpoints.
- Deletion of test fixtures under `app/backend/tests/_pending_scanner_activation/`
  (unrelated to placeholder replacement).

---

## Go / No-Go on Slice 1 (v2.10)

Once you approve, I will:
1. Open branch `hotfix/canonical-slice-1` off the *deployed* `main` (i.e.
   after v2.9.3 is on the VPS — never before).
2. Apply the Slice-1 patch (delete `_V2_OPPS` merge branch, delete
   `_hydrate_opps`, keep `_canonical_opp_to_contract`, verify /approve
   and /reject persist to `_CANONICAL_OPP_REPO`).
3. Run the backend curl smoke against a Mongo populated with 3 real
   `CanonicalOpportunity` rows + against an empty Mongo.
4. Run the frontend Playwright smoke on `/dashboard/opportunities` to
   verify empty-state renders correctly.
5. Produce `docs/RELEASE_NOTES_v2.10.md` with the same 9-section template.
6. Tag `v2.10-rc.1` and hand the branch back for review — no push to
   `main`, no VPS deployment without your explicit go.
