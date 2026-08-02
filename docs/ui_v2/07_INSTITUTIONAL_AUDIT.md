# ArbiCore X — Institutional Audit & Production Integration Plan

**Generated:** 2026-07-31 (post-Slice 5, feature-complete UI v2)
**Scope:** Full pre-production audit informed by the Backend ↔ UI Capability
Matrix (`docs/ui_v2/06_CAPABILITY_MATRIX.md`).
**Objective:** For every backend capability — determine purpose, exposure,
implementation stage, whether it should stay internal, whether it deserves a
UI surface, recommended improvements, and the production integration path.
**Non-goal:** No new UI features. No production integration in this phase.

---

## 0 · Executive summary

- **UI v2 status:** feature-complete across 7 top-level sections (Home,
  Discovery, Opportunities, Portfolio, Intelligence, Operations, Settings),
  22 sub-tabs, 48 endpoints wired, 62 backend contract tests passing.
- **Backend coverage:** 4 canonical composed endpoints (Slice 0 delta) are
  the only PROD wires today; 44 endpoints are PREVIEW stubs with documented
  future canonical targets.
- **Estimated canonical primitive coverage:** ≈ 85 / 245 (≈ 35%), up from
  38% raw baseline via composition.
- **Hidden-capability count:** ≈ 30 distinct capabilities across 7 backend
  layers still have no UI surface and no plan to expose (see §2).
- **Top three institutional risks (ranked):**
  1. **Contract drift risk** — 44 PREVIEW endpoints define the UI contract;
     production endpoints must match this shape *exactly* or the entire UI
     silently breaks. Mitigation: freeze `endpoints_ui_v2.tsv` before any
     production lift (§7.1).
  2. **Evidence & attestation gap** — `download_endpoint` in the drawer is
     wired to a route that has no backend handler; audit trail is not yet
     UI-inspectable end-to-end (§5.4).
  3. **Kill-switch UX gap** — Interlock ARM/DISARM works, but there is no
     one-key global kill-switch surfaced in the header; regulated operators
     expect this as a hardware-adjacent primitive (§6.4).
- **Top three institutional wins:**
  1. Every UI screen is a composition of documented endpoints — zero UI
     data is hard-coded outside `server.py`. This is the property most
     regulators actually care about.
  2. Design tokens + subnav pattern + `v2Api` mean any future backend
     endpoint can be added to the UI in ~ 20 lines and one file.
  3. `test_v2_slice{0..5}.py` is a machine-verifiable contract. A green
     suite against production is the go-live gate.

---

## 1 · Backend capability audit

Audit is organised by the 6-layer canonical architecture cited in
`docs/ui_v2/01_BACKEND_CAPABILITY_AUDIT.md`. Each capability uses a
7-attribute table:

| # | Purpose | UI exposure | Impl | Stay internal? | Deserves UI? | Improvements | Prod-integration path |

`Impl` values: **PROD** = wired to canonical; **PROD (composed)** = Slice-0
composed; **PREVIEW** = pod stub; **N/A** = no endpoint yet.

### 1.1 Layer 1 — Data ingestion & normalisation

| # | Purpose | UI exposure | Impl | Stay internal? | Deserves UI? | Improvements | Prod path |
|---|---|---|---|---|---|---|---|
| 1.1.1 | Portal-userscript quote ingestion (CEX) | Operations → Integrations (health only) | PREVIEW | Yes (feed) | Partially (health + freshness surface already exists) | Expose per-tab freshness + last-payload timestamp | Wire canonical `/api/execution/portal/diagnostic` behind an expandable diagnostic in Operations → Integrations |
| 1.1.2 | On-chain RPC quote ingestion (DEX) | Operations → Integrations (Alchemy row) | PREVIEW | Yes (feed) | Partially (health + latency) | Add per-chain latency histogram | Wire canonical RPC health endpoint (`RpcRegistry.status()`) |
| 1.1.3 | Funding-rate stream (perp venues) | None | N/A | No | **Yes — new** | Surface a cross-venue funding matrix | Add composed endpoint over `FundingRateRepo` → new Intelligence sub-tab |
| 1.1.4 | Order-book depth stream | None | N/A | No | **Yes — new** | Per venue-pair depth heatmap | Add composed endpoint → Discovery sub-tab |
| 1.1.5 | New-listing calendar ingestion | None (consumed inside LAUNCH scanner) | N/A | No | **Yes — new** | Standalone calendar with countdown | Compose over `ListingCalendarRepo` → Discovery sub-tab |
| 1.1.6 | News / narrative ingestion | None (consumed inside Discovery scoring) | N/A | No | Optional | Show top-narrative badges per opportunity | Add narrative field to opportunity detail response |
| 1.1.7 | Portal WS control channel | Operations → Integrations (health only) | PREVIEW | Yes (internal) | No | Add tab-count + last-heartbeat metric | Extend existing integrations endpoint payload |
| 1.1.8 | CoinGecko / market-cap enrichment | Operations → Integrations (health only) | PREVIEW | Yes | No | Rate-limit budget metric | Extend integrations endpoint |
| 1.1.9 | Chainlink price feeds | Operations → Integrations (health only) | PREVIEW | Yes | No | Show which pairs are used | Extend integrations endpoint |

**Layer 1 conclusion:** three high-value hidden capabilities (1.1.3 funding
matrix, 1.1.4 depth heatmap, 1.1.5 listing calendar) deserve dedicated UI
surfaces. Each is a composed-endpoint + one Discovery/Intelligence sub-tab.

### 1.2 Layer 2 — Opportunity scanners

| # | Purpose | UI exposure | Impl | Stay internal? | Deserves UI? | Improvements | Prod path |
|---|---|---|---|---|---|---|---|
| 1.2.1 | CEX_ARBITRAGE scanner | Operations → Scanners row | PREVIEW | No | Yes (already there) | Show per-family opps/min sparkline | Lift to `ScannerRegistry.snapshot()` |
| 1.2.2 | DEX_ARBITRAGE scanner | " | PREVIEW | No | Yes | Same as above | " |
| 1.2.3 | FUNDING_ARBITRAGE scanner | " | PREVIEW | No | Yes | Link to funding matrix (1.1.3 when added) | " |
| 1.2.4 | CROSS_CHAIN_ARBITRAGE scanner | " | PREVIEW | No | Yes | Show bridge-latency badge | " |
| 1.2.5 | FLASH_LOAN_ARBITRAGE scanner | " | PREVIEW | No | Yes | Show flash-fee coverage margin | " |
| 1.2.6 | LAUNCH_ARBITRAGE scanner | " | PREVIEW | No | Yes | Link to listing calendar | " |
| 1.2.7 | SPATIAL_ARBITRAGE scanner | " | PREVIEW | No | Yes | Chart cross-venue price triangles | " |
| 1.2.8 | STATISTICAL_ARBITRAGE scanner | " | PREVIEW | No | Yes | Show model version + z-score threshold | " |
| 1.2.9 | Scanner start/pause/stop control | Row action | PREVIEW | No | Yes | Confirm-dialog on stop | Wire to `ScannerController.transition()` |
| 1.2.10 | Per-family gate-drop counters | Row counter | PREVIEW | No | Yes | Expandable "why dropped" breakdown | Compose over `GateDropAudit.by_family()` |

**Layer 2 conclusion:** UI shape is right; the improvements are additive
detail (sparklines, gate-drop breakdown). No new tabs needed.

### 1.3 Layer 3 — Scoring, confidence, verdict

| # | Purpose | UI exposure | Impl | Stay internal? | Deserves UI? | Improvements | Prod path |
|---|---|---|---|---|---|---|---|
| 1.3.1 | Confidence scoring (multi-factor) | Drawer → Reasoning tab | PREVIEW | No | Yes | Add per-factor unit info + evidence link | Wire to `ConfidenceScorer.explain()` |
| 1.3.2 | Verdict decision (GO/SOFT_NO/HARD_NO) | Card + Drawer badge | PREVIEW | No | Yes | Add hover-reason on badge | Same endpoint |
| 1.3.3 | Safety score | Drawer, opportunity card | PREVIEW | No | Yes | Break down safety inputs | Wire `SafetyScorer.explain()` |
| 1.3.4 | Freshness score / staleness gate | Drawer, interlock gate | PREVIEW | No | Yes | Show fresh-window countdown | Same endpoint |
| 1.3.5 | Regime detection (CALM/…) | Home Pulse | PROD (composed) | No | Yes (already) | Add regime history sparkline (§3.3) | Extend existing composed endpoint |
| 1.3.6 | Confidence calibration curves | None | N/A | Partially internal | **Yes — new (Intelligence)** | Reliability diagram + Brier score | Compose over `CalibrationRepo` |
| 1.3.7 | Model / policy version pinning | None | N/A | Partially internal | **Yes — new (Intelligence or Settings → Operational)** | Show active model IDs + promotion history | Compose over `ModelRegistry.active()` |
| 1.3.8 | Decision audit log | Intelligence → Decisions | PREVIEW | No | Yes | Sortable by delta-factors; export CSV | Wire to `DecisionAuditLog.list()` |

**Layer 3 conclusion:** calibration + model-version are the two hidden
capabilities institutional operators most often ask for. Add them as a
new Intelligence sub-tab pair.

### 1.4 Layer 4 — Execution

| # | Purpose | UI exposure | Impl | Stay internal? | Deserves UI? | Improvements | Prod path |
|---|---|---|---|---|---|---|---|
| 1.4.1 | Order-router / venue-fanout | None | N/A | Yes (engine) | Partial (health) | Show fanout policy + fallback | Add read-only `OrderRouter.policy()` endpoint → Settings → Execution |
| 1.4.2 | Cycle lifecycle (planned → running → settled/reverted) | Operations → Cycles rows | PREVIEW | No | Yes | Cycle DAG viewer with per-leg fills | Wire to `CycleRepo` + new `CycleService.dag(id)` composed endpoint |
| 1.4.3 | Slippage attribution | None | N/A | No | **Yes — new column** | Per-fill slippage vs quoted mid | Add slippage field to cycle detail |
| 1.4.4 | Gas-strategy tuner | None (only stubbed under Execution config) | N/A | Partially internal | **Yes — new** | Per-chain gas policy knobs w/ read-out | Compose over `GasStrategyRegistry` → Settings → Execution add-on |
| 1.4.5 | Interlock gate evaluation | Operations → Interlock | PREVIEW | No | Yes | Per-gate history sparkline (last 24h) | Wire `SafetyInterlock.snapshot()` + `.history()` |
| 1.4.6 | Kill-switch trigger | Interlock DISARM | PREVIEW | No | **Yes — global** | Add header-level ⌘. shortcut + confirm | Wire to `SafetyInterlock.emergency_stop()` |
| 1.4.7 | Approve / Reject workflow | Drawer action bar | PREVIEW | No | Yes | Show downstream (auto-execute vs queued) | Wire to `OpportunityService.approve()/.reject()` |
| 1.4.8 | Portal quote diagnostic (raw payload) | Referenced in pulse pointer only | N/A | No | **Yes — expandable** | Raw payload viewer for last N ticks | Wire `/api/execution/portal/diagnostic` behind Ops → Integrations row |

**Layer 4 conclusion:** cycle DAG (1.4.2), slippage attribution (1.4.3),
gas tuner (1.4.4), and global kill-switch (1.4.6) are the four
execution-layer capabilities missing a first-class UI surface. All are
tickets already noted in the matrix §4.4.

### 1.5 Layer 5 — Portfolio, treasury, ledger

| # | Purpose | UI exposure | Impl | Stay internal? | Deserves UI? | Improvements | Prod path |
|---|---|---|---|---|---|---|---|
| 1.5.1 | Position snapshot | Portfolio → Positions | PREVIEW | No | Yes | Position drilldown drawer w/ linked cycles | Wire `ExecutionPositionRepo.snapshot()`; add `.detail(id)` |
| 1.5.2 | Venue balance aggregation | Portfolio → Balances | PREVIEW | No | Yes | Balance stale-alert flag | Wire `VenueBalanceService.aggregate()` |
| 1.5.3 | Transfer log | Portfolio → Transfers | PREVIEW | No | Yes | Retry-failed action | Wire `TreasuryLedger.transfers()` + `.retry(id)` |
| 1.5.4 | Deployable capital snapshot | Portfolio → Deployable | PREVIEW | No | Yes | Show per-strategy reservations | Wire `CapitalRouter.deployable_snapshot()` |
| 1.5.5 | Vault registry & reconcile | Portfolio → Treasury + Settings → Vault | PREVIEW | No | Yes | Show cosigner status per multisig | Wire `TreasuryLedger.vault_snapshot()/.reconcile()` |
| 1.5.6 | Ledger entries | Portfolio → Ledger | PREVIEW | No | Yes | Export CSV; range filter | Wire `TreasuryLedger.entries()` |
| 1.5.7 | Exposure analyser | Portfolio → Exposure | PREVIEW | No | Yes | Risk-band overlays (safe/hot) | Wire `ExposureAnalyzer.breakdown()` |
| 1.5.8 | Allocation policy | Portfolio → Allocation | PREVIEW | No | Yes | One-click rebalance suggestions | Wire `AllocationPolicy.status()`; add `.propose_rebalance()` |
| 1.5.9 | PnL settlement | Portfolio → Ledger (PNL kind) | PREVIEW | No | Yes | Daily / weekly PnL summary card on Home | Compose `TreasuryLedger.pnl_summary(window)` → Home widget (later) |

**Layer 5 conclusion:** the Portfolio pages already cover the primitives;
recommendations here are quality-of-life (drilldown, retry, CSV export)
rather than new surfaces.

### 1.6 Layer 6 — Governance, compliance, knowledge

| # | Purpose | UI exposure | Impl | Stay internal? | Deserves UI? | Improvements | Prod path |
|---|---|---|---|---|---|---|---|
| 1.6.1 | Operator account / auth / MFA | Settings → Account | PREVIEW | No | Yes | Add API-key rotation UI | Wire `UserService.profile()`; add `.rotate_key()` |
| 1.6.2 | Feature flags & operator modes | Settings → Operational | PREVIEW | No | Yes | Add "who last changed" audit line | Wire `OperatorFlags.snapshot()`; extend with `changed_by` |
| 1.6.3 | Notification config | Settings → Notifications | PREVIEW | No | Yes | Add per-severity mute-window | Wire `NotificationConfig.load()/save()` |
| 1.6.4 | Documentation index | Settings → Documentation | PREVIEW | No | Yes (static ok) | Embed changelog head + last-updated | Stay client-side static |
| 1.6.5 | Route certification (candidate → canonical) | Intelligence → Recommendations (flattened) | N/A | No | **Yes — new** | State-machine promotion UI | Compose over `RouteCertifier.status()` |
| 1.6.6 | Evidence bundle export | Drawer references it, endpoint missing | N/A | No | **Yes — critical** | Signed evidence.zip download | Implement `EvidenceBundle.export(cycle_id)` first |
| 1.6.7 | Compliance flags per venue / asset | None | N/A | Partially internal | **Yes — new** | Show sanctions / restricted flags | Compose `ComplianceRegistry.flags()` |
| 1.6.8 | Backup / restore triggers | CLI only | N/A | Partially internal | Optional | Read-only backup timestamp display | Add `Backup.last_ts()` endpoint → Settings → Operational |
| 1.6.9 | Deploy verification metrics | CLI only (v1.0.2 harness) | N/A | Yes (ops) | Optional | Prom text metrics → Grafana | Roadmap ENH-001 |
| 1.6.10 | Log-tail / correlation | None | N/A | Yes (SRE) | No | — | Keep on the SRE side |
| 1.6.11 | Health-check history | None | N/A | Partially internal | Optional | 24h uptime strip on Home | Compose `HealthProbe.history()` |
| 1.6.12 | Peer-stack (Strategy Factory) breadcrumb | None | N/A | Yes | **Yes — new** | Cross-app menu link | Add small link block to header |

**Layer 6 conclusion:** route certification (1.6.5), evidence bundle
export (1.6.6), and compliance flags (1.6.7) are the three institutional
gaps that most affect regulated deployments. Evidence bundle is the
highest priority — it's already promised in the UI but has no backend.

---

## 2 · Hidden capability audit (deeper)

The following capabilities exist in the canonical backend audit but were
NOT surfaced anywhere in UI v2 Slices 0–5. Ranked by expected operator
value.

| Rank | Capability | Layer | Current state | Why hidden today | Recommended surface |
|---|---|---|---|---|---|
| 1 | Evidence bundle download per cycle | 1.6.6 | Referenced in Drawer, no backend | Ships in future canonical build | Wire into `OpportunityDrawer` Evidence tab |
| 2 | Cycle DAG viewer | 1.4.2 | Cycle rows only show summary | UI has no drilldown yet | Row-expand in Operations → Cycles |
| 3 | Route learning history graph | 1.3.5 / 1.5.9 | Slice 0 exposes aggregate only | Time-series not composed | New chart in Drawer Reasoning tab |
| 4 | Confidence calibration curves | 1.3.6 | Internal only | Requires reliability computation to be productised | New Intelligence sub-tab |
| 5 | Model version pinning + promotion log | 1.3.7 | Internal only | No promotion state machine surfaced | New Intelligence sub-tab (or Settings → Operational) |
| 6 | Funding-rate cross-venue matrix | 1.1.3 | Internal to scanner | No composed endpoint | New Intelligence sub-tab |
| 7 | Order-book depth heatmap | 1.1.4 | Internal | Streaming payload | New Discovery sub-tab |
| 8 | New-listing calendar | 1.1.5 | Internal | Consumed by LAUNCH scanner only | New Discovery sub-tab |
| 9 | Slippage attribution | 1.4.3 | Internal | Not summarised in ledger | New column in Portfolio → Ledger + Cycle DAG |
| 10 | Portal quote diagnostic (raw payload) | 1.4.8 | Endpoint exists, unwired | Deemed noisy | Expandable row on Ops → Integrations |
| 11 | Route certification state machine | 1.6.5 | Internal | Reduced to a score | New Intelligence sub-tab |
| 12 | Compliance flags per venue/asset | 1.6.7 | Internal | Reg risk not surfaced | Row badge on Ops → Venues + Portfolio → Balances |
| 13 | Gas-strategy tuner | 1.4.4 | Internal | Per-chain knobs unbounded | Extension of Settings → Execution |
| 14 | Regime transition history | 1.3.5 | Internal | Only current shown | Sparkline in Home Pulse |
| 15 | Whale / large-order tracker | Layer 1 add-on | Internal | Noisy without filter | New Discovery sub-tab |
| 16 | Entity graph browser | Layer 6 add-on | Internal | Large graph payload | New Intelligence sub-tab (long-term) |
| 17 | Similarity search (routes / opps) | Layer 6 add-on | Internal | No UI trigger | Right-click "find similar" on any opp/route |
| 18 | Playbook / runbook store | Layer 6 | Docs only | No endpoint | Later — extend Documentation |
| 19 | Peer-stack breadcrumb | 1.6.12 | Internal | Deployment concern | Header link block |
| 20 | Health-check history | 1.6.11 | Internal | SRE-facing | Small uptime strip on Home footer |

Items 1–5 are the **institutional MUST**. Items 6–13 are the
**high-value SHOULD**. Items 14–20 are the **nice-to-have COULD**.

---

## 3 · AI & learning audit

### 3.1 What exists (per canonical audit)
- **RegimeDetector** — categorical output (CALM/…) with confidence and
  tags. Slice 0 wires the current snapshot.
- **ConfidenceScorer** — multi-factor, per-opportunity, with per-factor
  contributions (breakdown surfaced in Drawer).
- **SafetyScorer** — separate gate; independent scale.
- **MongoRouteSuccessTracker** — per-route sample size, win-rate,
  outcome mean/sum, last outcome time. Slice 0 wires the aggregate.
- **DecisionAuditLog** — every verdict recorded with top factors and
  timestamp. Slice 2 wires the log listing.
- **CalibrationRepo** *(inferred, not verified in-pod)* — reliability
  diagrams + Brier scores.
- **ModelRegistry** *(inferred)* — active model IDs, promotion history.

### 3.2 What the UI shows today
- Regime: current only (Home Pulse).
- Confidence: per-opportunity breakdown (Drawer).
- Route ROI: aggregate win-rate + mean outcome (Drawer via
  `/roi-probability`).
- Decision log: last N verdicts, sortable by verdict/family (Intelligence).

### 3.3 Gaps
- **No temporal view** — regime history, route history, calibration
  history are all point-in-time. Institutional operators need "why is
  this different from yesterday?".
- **No calibration surface** — is a 0.72 confidence *actually* 72%
  historically? Unanswered in UI.
- **No model provenance** — which model produced this verdict? Not
  visible.
- **No A/B or shadow-model view** — if two policies run in shadow, we
  can't see the divergence.

### 3.4 Recommendations
- **AI-1** Extend `pulse` composed endpoint with a `regime_history_24h`
  array (~ 48 hourly points). Render as a sparkline under the regime
  chip. Cheap.
- **AI-2** Extend `/roi-probability` with `history_30d` (per-day
  win-rate). Render a mini-line-chart in Drawer.
- **AI-3** Add a new **Intelligence → Calibration** sub-tab reading a
  composed endpoint over `CalibrationRepo`. Reliability diagram +
  per-bucket Brier + drift banner. This is the single most-requested
  chart in institutional audits.
- **AI-4** Add a new **Intelligence → Models** sub-tab: active model
  IDs, promotion history, shadow deployments, kill-shadow action.
- **AI-5** Add `model_version` and `policy_version` to every decision
  in the decision-log payload; render as a mono-font suffix on each
  row. Zero UI redesign.
- **AI-6** Add an explainability annotation to the Drawer's Reasoning
  tab: which model, which feature values, which threshold crossed.

### 3.5 What should stay internal
- Raw feature vectors + intermediate scoring layers. UI should show
  final contributions and unit info, not the full tensor.
- Training pipelines, backfills, feature-store operations.
- Live model retraining triggers.

---

## 4 · Execution workflow audit

### 4.1 Canonical workflow (as-audited)
```
scanner  ─▶  candidate opp  ─▶  scoring  ─▶  gates (safety, freshness,
                                            depth, regime, capital)
                                       ─▶  verdict (GO/SOFT_NO/HARD_NO)
                                       ─▶  approval (auto or human)
                                       ─▶  order router  ─▶  fills
                                       ─▶  cycle lifecycle (running →
                                            settled/reverted/failed)
                                       ─▶  PnL + ledger + evidence
```

### 4.2 UI coverage
- Scanner ↔ candidate: **Operations → Scanners** (counts only, no
  sample stream).
- Scoring & gates: **Drawer → Reasoning + Gates** (present).
- Verdict: **card + drawer badge** (present).
- Approval: **drawer action bar** (present).
- Order router: **not exposed**.
- Cycles: **Operations → Cycles** (row-level only, no DAG).
- Fills / slippage: **not exposed**.
- PnL: **Portfolio → Ledger** (present).
- Evidence: **drawer reference only, no download**.

### 4.3 Gaps
- **Router policy hidden** — operators can't see which venue-fanout
  policy was used, or why a fallback triggered.
- **Cycle drilldown absent** — every settled cycle should expand to
  show plan → attempts → fills → PnL split by leg.
- **Slippage silent** — attribution per fill is essential for A/B
  analysis of gas strategy and order type.
- **Evidence broken promise** — Drawer advertises download_endpoint
  but nothing serves it (§5.4).
- **No queue-back-pressure narrative** — Operations → Queues shows
  numbers but doesn't tell an operator whether it should worry.

### 4.4 Recommendations
- **EX-1** Add `router_policy` and `fallback_reason` to cycle detail;
  render as a chip in the Cycle DAG row.
- **EX-2** Add Cycle DAG row-expand: `plan → attempts → fills → pnl`
  with per-leg slippage. Single composed endpoint.
- **EX-3** Add slippage_bps and gas_paid_usd fields to every ledger
  entry of kind PNL or FEE; sortable column.
- **EX-4** Implement `EvidenceBundle.export(cycle_id)` (backend) →
  bind the Drawer's existing download link to it.
- **EX-5** Add a small "health band" component to Operations → Queues
  header: `NOMINAL / DEGRADED / BLOCKED` with the worst-queue reason.
- **EX-6** Wire a per-cycle **replay** action (dry-run only) so
  operators can inspect "what would the router do now?" without
  affecting live state.

---

## 5 · Treasury & Security architecture audit

### 5.1 Treasury inventory (from Slice 4/5 stubs + canonical audit)
- Vault types: **COLD**, **HOT**, **MULTISIG**, **EXCHANGE**.
- Custody model: mixed — self-custody for cold/hot/multisig; venue
  custody for exchange pool.
- Transfer kinds: `cex_to_cex`, `cex_to_vault`, `vault_to_cex`, `bridge`.
- Reconciliation: manual trigger per vault (Settings → Vault → RECONCILE).
- Ledger kinds: `PNL`, `FEE`, `TRANSFER`, `DEPOSIT`, `WITHDRAW`.

### 5.2 Security surfaces
- **Auth**: username/email, MFA toggle, session TTL (Settings → Account).
- **Read-only mode** and **maintenance mode** (Settings → Operational).
- **Kill-switch** (Operations → Interlock DISARM).
- **API-key masking** on the Exchanges surface (`AKb••••••••u3q`).
- **Read-only exchange** flag per venue (Settings → Exchanges).

### 5.3 Gaps
- **No multisig cosigner status** — the UI shows `signers_required /
  signers_total` but not per-signer state or last-signed timestamp.
- **No transfer approval workflow** — every transfer today is
  effectively hard-wired; institutions expect 2-of-N approval on
  outgoing transfers above threshold.
- **No API-key rotation UI** — masking is fine, but there is no
  "rotate now" action.
- **No sanctions / restricted-asset flags** — Exchanges + Balances
  surfaces show what we hold, not whether we should be holding it in
  each jurisdiction.
- **Kill-switch is buried** — reachable only via Operations →
  Interlock → DISARM (3 clicks). Institutional norm is `Ctrl+.` or
  a red header button.
- **Evidence chain-of-custody** — no export attestation on the
  evidence bundle (see §4.3).
- **Vault reconcile is fire-and-forget** — no diff report between
  expected and observed.

### 5.4 Recommendations
- **SEC-1** Add per-cosigner status to `vaults` payload; render as a
  small chip cluster in Settings → Vault.
- **SEC-2** Introduce a transfer-approval state (`PROPOSED →
  APPROVED_BY_A → APPROVED_BY_B → EXECUTED`) with a threshold
  parameter in Settings → Execution; expose the approval action bar
  in Portfolio → Transfers rows.
- **SEC-3** Add a `POST /settings/exchanges/{k}/rotate_key` endpoint
  and a **ROTATE** button next to **TEST**.
- **SEC-4** Wire `ComplianceRegistry.flags()` → new column on Ops →
  Venues, Settings → Exchanges, and Portfolio → Balances (asset chip).
- **SEC-5** Add a header-level **KILL** button (destructive style,
  amber → red on hover) that maps to `⌘.` and calls
  `SafetyInterlock.emergency_stop()`; require typed confirmation.
- **SEC-6** Sign evidence-bundle exports (Ed25519); publish public
  key in Documentation.
- **SEC-7** Return a reconciliation diff report from `POST
  /vaults/{v}/reconcile`; render inline (expandable JSON) in the
  Vault row after ACK.

### 5.5 What should stay internal
- Private keys, seed phrases, HSM PINs — obviously.
- Bridge internals + relayer failover — surface only status.
- Backup / restore mechanics — CLI-only remains fine.

---

## 6 · Preview-to-production integration audit

### 6.1 Contract inventory
- 48 UI-facing endpoints (see `06_CAPABILITY_MATRIX.md` §1).
- 4 are canonical composed (Slice 0); the rest are PREVIEW.
- 62 backend contract tests define the wire shape.

### 6.2 Cutover risk map

| Risk | Slice most affected | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Contract shape drift | Any | Med | High (silent UI break) | Freeze `endpoints_ui_v2.tsv`; keep contract tests green on prod |
| Latency regression when moving from stubs → real repos | Slice 3, 4 | High | Med | Add p95 SLO to `pulse` (< 300 ms) and cycle-DAG (< 500 ms) |
| Auth boundary mismatch (stub returns 200 always) | Slice 5 | Med | High | Add auth-required tests before lift |
| Read/write consistency (PATCH → GET) | Slice 5 (already round-trips in stub) | Low | Med | Contract tests already assert |
| Cross-slice state (e.g. drawer approve → home deck refresh) | Slices 0+1 | Med | Low | Add refresh key + toast on Home when approve happens |
| Data-privacy leak in payload | Slice 5 (exchanges) | Med | High | Contract test already asserts masked API key |
| Time-zone / ISO parsing | All | Low | Low | Frontend already uses `.slice(11,19)` — safe |

### 6.3 Sequenced lift plan (concrete)

Order is the same as `06_CAPABILITY_MATRIX.md` §4.2 but each step now
has explicit gates.

1. **Prep**
   - Freeze `docs/ui_v2/appendix/endpoints_ui_v2.tsv`.
   - Copy `test_v2_slice{1..5}.py` into canonical repo.
   - Add `UI_V2_PROD_SLICE_{1..5}` env flags in canonical `server.py`.
2. **Slice 1 lift (Opportunities)** — highest value, isolated write
   surface.
   - Real `opportunities.py` router → repo composition.
   - Contract test suite must pass; add 2 auth-required tests.
   - Flip `UI_V2_PROD_SLICE_1=true`; monitor 7 days.
3. **Slice 4 lift (Portfolio)** — read-heavy, no writes.
   - Wire 8 endpoints. Add latency SLO to `deployable`.
   - Add slippage + gas fields (EX-3) as an additive extension.
4. **Slice 3 lift (Operations)** — includes writes on scanner action
   + interlock + alert ack.
   - Add confirm dialog on scanner stop (see 1.2.9).
   - Verify interlock disarm is auth-gated + audit-logged.
5. **Slice 2 lift (Discovery + Intelligence)** — includes
   discovery-action writes.
6. **Slice 5 lift (Settings)** — smallest surface, safest last.
   - Special care: exchange test must never leak keys.
   - Verify PATCH endpoints are RBAC-checked.
7. **Stub retirement** — remove seed data from `backend/server.py`
   after ≥ 1 week clean of each slice.

### 6.4 Gates before go-live
- [ ] Contract tests green on production for the target slice.
- [ ] p95 latency budget met per endpoint (see §6.2).
- [ ] Auth-required test asserts 401 without token.
- [ ] Rate-limit test asserts 429 above threshold.
- [ ] No data-privacy leak (masked keys, no seed phrases, no PII in
      error responses).
- [ ] Audit-log entry present for every write endpoint.
- [ ] Rollback script tested (flip `UI_V2_PROD_SLICE_{n}=false` +
      no data corruption).

### 6.5 Do NOT carry forward
- Any of the pod-local `_V2_*` seed data.
- `LegacyLanding` component in `frontend/src/App.js`.
- The temporary `.env` files recreated in this pod.
- The `backend/server.py` in its current monolithic form — production
  routers live under `arbicore/routes/*`.

---

## 7 · Cross-cutting recommendations (simplify / modernise)

Beyond exposure, these are things worth improving in the canonical
codebase during the same window.

- **CX-1 Endpoint naming** — production endpoints are inconsistent
  (`/api/venues/status` vs `/api/execution/interlock` vs
  `/api/portfolio/deployable`). New composed endpoints already follow
  `/api/arbicore/{domain}/…`. Recommend adopting that as the canonical
  prefix during the lift.
- **CX-2 Response envelope** — some legacy endpoints return arrays,
  some `{items, total}`. Slice-0..5 stubs always use
  `{items, total, generated_at}`. Standardise on this shape.
- **CX-3 Timestamps** — always ISO-8601 with tz. Contract tests
  enforce this already; ensure production adopts it.
- **CX-4 Error shape** — adopt `{error: "<code>", detail: "<msg>",
  correlation_id: "<uuid>"}` uniformly; UI can then surface the
  correlation ID in toast + Ops → Alerts.
- **CX-5 Feature-flag gating in payloads** — endpoints should
  advertise `preview: true` or `preview: false` in a top-level field
  so the UI can badge preview data (removes a class of "why doesn't
  this look real?" tickets).
- **CX-6 One monolithic `server.py` → split** — before production
  push, extract each slice's endpoints into
  `arbicore/routes/{opportunities,operations,portfolio,settings}.py`
  in the canonical repo. UI does not care.
- **CX-7 SSE / WS upgrade path** — 5 endpoints today are
  poll-friendly (`scanners`, `alerts`, `positions`, `deployable`,
  `pulse`). Model a server-sent-events layer for these five in the
  next cycle; UI already isolates fetch via `useAsync`.
- **CX-8 Design tokens as a package** — `src/v2/theme/tokens.css` is
  reusable; publish it (or the CSS + JS mirror) as an internal
  package so the peer stack (Strategy Factory) can align.
- **CX-9 Retire `LegacyLanding`** — after Slice 6 cutover, replace
  `/` with the `/v2` shell.

---

## 8 · Consolidated recommendation backlog

Priority order (P0 highest). Each entry maps to sections above.

- **P0 · Evidence bundle export** — 1.6.6 + EX-4. Backend implementation
  is the blocker; UI already gestures at it.
- **P0 · Global kill-switch UX** — SEC-5. Header button + `⌘.` +
  confirm-typed.
- **P0 · Cycle DAG viewer** — EX-2. Highest operator ROI in
  execution transparency.
- **P0 · Confidence calibration surface** — AI-3. Regulator-facing
  primitive.
- **P1 · Slippage attribution** — EX-3.
- **P1 · Route-learning history graph** — AI-2.
- **P1 · Compliance flags** — SEC-4.
- **P1 · Model version pinning** — AI-4/5.
- **P1 · Transfer approval workflow** — SEC-2.
- **P2 · Funding matrix / depth heatmap / listing calendar** — 1.1.3
  – 1.1.5. Three new sub-tabs (Intelligence + Discovery).
- **P2 · Regime history sparkline** — AI-1.
- **P2 · Gas-strategy tuner** — 1.4.4.
- **P2 · API-key rotation** — SEC-3.
- **P2 · Reconciliation diff report** — SEC-7.
- **P3 · Peer-stack breadcrumb** — 1.6.12.
- **P3 · Health-check history strip** — 1.6.11.
- **P3 · SSE/WS upgrade for 5 poll endpoints** — CX-7.

---

## 9 · Deliverables produced in this audit

- This document — `docs/ui_v2/07_INSTITUTIONAL_AUDIT.md`.
- Precedes and now supersedes `06_CAPABILITY_MATRIX.md` for planning
  purposes (the matrix remains the raw inventory; this audit adds the
  should/why/how columns).

No code was modified in this phase. No production integration was
performed. Awaiting user direction on which P0/P1 backlog items to
implement first.
