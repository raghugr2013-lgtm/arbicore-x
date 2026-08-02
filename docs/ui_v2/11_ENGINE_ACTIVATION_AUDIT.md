# ArbiCore X — Phase 0 · Engine Activation Audit

**Generated:** 2026-07-31
**Purpose:** Before Phase A (Contract Freeze) begins, enumerate every backend
engine — active or otherwise — and classify its participation in the
production execution pipeline. Identify dormant engines that already exist
and should be reactivated rather than rebuilt.
**Non-goal:** No implementation, no refactor, no integration. Audit only.

**Reference sources**
- `memory/PRD.md`
- `docs/ui_v2/01_BACKEND_CAPABILITY_AUDIT.md` (canonical, 245 endpoints)
- `docs/ui_v2/06_CAPABILITY_MATRIX.md`
- `docs/ui_v2/07_INSTITUTIONAL_AUDIT.md`
- `docs/ui_v2/08_PREVIEW_TO_PROD_INTEGRATION_AUDIT.md`
- `docs/ui_v2/09_TREASURY_SECURITY_ARCHITECTURE.md`
- `backend/server.py` — preview stubs + inline future-endpoint hints
- Slice-0 pulse pointers → real canonical endpoints
  (`/api/arbicore/scanners`, `/api/venues/status`,
  `/api/execution/portal/diagnostic`, `/api/execution/interlock`,
  `/api/portfolio/deployable`)

**Confidence note.** The canonical Python source **is** in this pod
(extracted from `arbicore-x-v1.0.2.bundle`). Every row below has now
been re-verified against `/tmp/canonical_extract/`. Rows that were
previously marked with `*` are corrected inline; the correction log
lives in §7 of `docs/ui_v2/13_WAVE1_VERIFICATION_REPORT.md`.

---

## 0 · Method

Every engine gets an 11-attribute row:

| Attr | Meaning |
|---|---|
| Purpose | One-line role in the pipeline. |
| Inputs | Upstream data streams / repos it consumes. |
| Outputs | Downstream artefacts it produces. |
| Dependencies | Sibling engines it calls. |
| Status | **Active** · **Partially Active** · **Dormant** · **Preview Only** · **Not Implemented** |
| UI exposure | Which UI v2 sub-tab surfaces its output (or "none"). |
| Prod usage | Whether real trading depends on it today. |
| AI provider | Local ML / external LLM / heuristic / none. |
| Learning loop | Reads outcomes? Writes back to a model store? |
| Action | **Reuse** · **Refine** · **Activate** · **Merge** · **Retire** |

Status definitions (used consistently):
- **Active** — runs continuously in production; verified by pulse pointers,
  scanner counters, or explicit documentation.
- **Partially Active** — code exists and runs, but not in every family /
  chain / mode expected of it.
- **Dormant** — code exists (per canonical audit) but is not scheduled or
  called by any live path.
- **Preview Only** — only the pod-local stub exists; no canonical
  implementation confirmed.
- **Not Implemented** — no code anywhere; referenced only by design docs.

---

## 1 · Engine Inventory (grouped by canonical layer)

The following ~45 engines were identified. Table density is dense on
purpose — one row per engine.

### 1.1 Layer 1 — Data Ingestion

| # | Engine | Purpose |
|---|---|---|
| L1-01 | Portal Userscript v2 | Bridges CEX venue tabs into internal quote stream |
| L1-02 | Portal WS Broker | Distributes portal messages to scanners |
| L1-03 | Alchemy RPC Client | On-chain read/subscribe for ETH-family chains |
| L1-04 | Multi-chain RPC Client | Same, for Solana / Base / Arbitrum / Polygon |
| L1-05 | CoinGecko Feed | Market-cap / trending enrichment |
| L1-06 | Chainlink Price Feed | On-chain price oracle |
| L1-07 | Telegram Ingress | Curated tweet / channel scraper (per Discovery signals) |
| L1-08 | GitHub Activity Watcher | Chain-launch / release activity |
| L1-09 | On-chain Pool Scanner | New DEX pool discovery |
| L1-10 | Listings Feed | New CEX listing calendar |
| L1-11 | Funding-Rate Feed | Perp funding rate cross-venue |
| L1-12 | Order-Book Depth Feed | Live depth per venue-pair |
| L1-13 | Whale Tracker | Large-transfer / large-order alerts |
| L1-14 | News / Narrative Feed | Narrative burst detection |

### 1.2 Layer 2 — Scanners (Opportunity generation)

| # | Engine | Purpose |
|---|---|---|
| L2-01 | CEX_ARBITRAGE Scanner | Cross-CEX price arbitrage |
| L2-02 | DEX_ARBITRAGE Scanner | Cross-DEX / pool arbitrage |
| L2-03 | FUNDING_ARBITRAGE Scanner | Perp funding vs spot arbitrage |
| L2-04 | CROSS_CHAIN_ARBITRAGE Scanner | Same asset, different chain |
| L2-05 | FLASH_LOAN_ARBITRAGE Scanner | Multi-hop flash-loan arb |
| L2-06 | LAUNCH_ARBITRAGE Scanner | New listing / launch arb |
| L2-07 | SPATIAL_ARBITRAGE Scanner | Triangular / venue-triangle arb |
| L2-08 | STATISTICAL_ARBITRAGE Scanner | Statistical pairs / z-score |

### 1.3 Layer 3 — Scoring, Verdict, Learning

| # | Engine | Purpose |
|---|---|---|
| L3-01 | RegimeDetector | Market regime classifier (CALM / …) |
| L3-02 | ConfidenceScorer | Multi-factor per-opp confidence |
| L3-03 | SafetyScorer | Per-opp safety score (venue drift, liquidity risk) |
| L3-04 | FreshnessScorer | Quote-age gate |
| L3-05 | VerdictEngine | GO / SOFT_NO / HARD_NO |
| L3-06 | MongoRouteSuccessTracker | Per-route outcome history |
| L3-07 | DecisionAuditLog | Verdict log with top factors |
| L3-08 | CalibrationRepo * | Reliability diagrams / Brier |
| L3-09 | ModelRegistry * | Active model IDs + promotion history |
| L3-10 | GateDropAudit * | Per-family gate-drop counters |

### 1.4 Layer 4 — Execution

| # | Engine | Purpose |
|---|---|---|
| L4-01 | Order Router / Venue Fanout | Selects venue + places / bridges orders |
| L4-02 | Cycle Lifecycle Manager | Owns planned → running → settled state |
| L4-03 | SafetyInterlock | 5-gate execution gate |
| L4-04 | Approval Workflow | N-of-M sign for mutations |
| L4-05 | Kill-Switch Controller | Global emergency stop |
| L4-06 | Slippage Attribution | Per-leg slippage vs quoted mid |
| L4-07 | Gas Strategy | Per-chain gas policy + reserves |
| L4-08 | Portal Quote Diagnostic | Raw portal payload dump |
| L4-09 | Execution Position Repo | Open positions across venues |

### 1.5 Layer 5 — Portfolio, Treasury, Ledger

| # | Engine | Purpose |
|---|---|---|
| L5-01 | TreasuryLedger | Ledger entries + vault snapshots + PnL |
| L5-02 | VenueBalanceService | Per-venue balance aggregation |
| L5-03 | CapitalRouter | Deployable capital + per-venue utilisation |
| L5-04 | ExposureAnalyzer | Exposure by asset / by chain |
| L5-05 | AllocationPolicy | Target vs actual by bucket |
| L5-06 | Transfer Service | Executes cex↔cex / cex↔vault / bridge |
| L5-07 | Vault Reconcile Service | Vault vs on-chain diff |
| L5-08 | Evidence Bundle Exporter | Signed per-cycle evidence.zip |

### 1.6 Layer 6 — Governance, Compliance, Knowledge

| # | Engine | Purpose |
|---|---|---|
| L6-01 | UserService | Operator profile / MFA |
| L6-02 | OperatorFlags | Modes + feature flags |
| L6-03 | NotificationConfig | Channels + severities + events |
| L6-04 | ExecutionPolicy | Max size / gates / slippage / auto-exec |
| L6-05 | VenueRegistry | Exchange metadata + connectivity |
| L6-06 | WalletRegistry * | Wallet address book across chains |
| L6-07 | SecretManagement * | KMS handle store |
| L6-08 | ComplianceRegistry | Sanctions / restricted flags |
| L6-09 | RouteCertifier * | Candidate → canonical route promotion |
| L6-10 | Entity Graph * | Venue / token / team / chain relations |
| L6-11 | Similarity Search * | Find-similar (routes / opps) |
| L6-12 | Playbook Store | Arbitrage runbooks |
| L6-13 | Backup / Restore | Persistence layer backup |
| L6-14 | Deploy Verification Harness | 8-cat verify script (v1.0.2) |
| L6-15 | Health Probe | Readiness / liveness |
| L6-16 | AlertRepo / AlertService | Ops alert store + ack |
| L6-17 | WorkerRegistry | Background queue stats |

### 1.7 Discovery

| # | Engine | Purpose |
|---|---|---|
| DSC-01 | DiscoveryRepo | Candidate store |
| DSC-02 | DiscoveryScorer | Score by signal set |
| DSC-03 | DiscoveryTransition Service | Watch / promote / dismiss / reset |

**Total engines audited:** 51.

---

## 2 · Engine Activation Matrix (full row-per-engine)

Compact 11-column table below. Rows in `Status = Not Implemented` are the
gaps genuinely requiring net-new code (see §7). Rows marked `Preview Only`
have a canonical replacement pending Phase B–D lift.

### 2.1 Layer 1

| # | Inputs | Outputs | Deps | Status | UI | Prod usage | AI | Learning | Action |
|---|---|---|---|---|---|---|---|---|---|
| L1-01 Portal Userscript v2 | CEX tab DOMs | Normalised quote stream | none | **Active** | Ops → Integrations (health) | Yes — primary CEX feed | none | writes freshness metric | Reuse |
| L1-02 Portal WS Broker | L1-01 | Distributed quotes | L1-01 | **Active** | Ops → Integrations | Yes | none | none | Reuse |
| L1-03 Alchemy RPC Client | ETH mainnet | On-chain reads/subs | none | **Partially Active** (DEGRADED per Ops → Integrations) | Ops → Integrations | Yes | none | none | Refine (multi-provider fallback) |
| L1-04 Multi-chain RPC Client | Sol/Base/Arb/Polygon | Reads/subs per chain | none | Partially Active * | Ops → Integrations | Yes for DEX/cross-chain | none | none | Refine |
| L1-05 CoinGecko Feed | HTTP | Trending / cap metadata | none | **Active** | Ops → Integrations + Discovery (implicit) | Yes | none | none | Reuse |
| L1-06 Chainlink Price Feed | On-chain | Price oracle | L1-03/04 | **Active** | Ops → Integrations | Yes | none | none | Reuse |
| L1-07 Telegram Ingress | External | Curated tweets/messages | none | **Active** (Discovery source `twitter:@…`) | Discovery rows | Yes (Discovery only) | none | none | Reuse |
| L1-08 GitHub Activity Watcher | External | Repo / release events | none | **Active** (Discovery source `github:activity`) | Discovery rows | Yes (Discovery only) | none | none | Reuse |
| L1-09 On-chain Pool Scanner | L1-03/04 | New pool events | L1-03/04 | **Active** (Discovery source `onchain:pool_scan`) | Discovery rows | Yes | none | none | Reuse |
| L1-10 Listings Feed | External | New listing events | none | **Active** for LAUNCH scanner + Discovery | Discovery rows only | Yes | none | none | Refine (surface calendar UI) |
| L1-11 Funding-Rate Feed | Perp APIs | Cross-venue funding | L1-02 | **Partially Active** (used inside FUNDING_ARBITRAGE only) | none | Yes indirectly | none | none | Activate (new Intelligence tab, per audit AI-3) |
| L1-12 Order-Book Depth Feed | Venue APIs | Depth arrays | L1-02 | **Partially Active** * (used inside gates) | none | Yes indirectly | none | none | Activate (new Discovery tab) |
| L1-13 Whale Tracker | External | Large-txn alerts | none | **Dormant** * | none | No | none | none | Activate |
| L1-14 News / Narrative Feed | External | Narrative tags | none | **Dormant** * (Discovery uses source tags but no dedicated feed) | none | No | Optional (LLM classifier) | none | Activate |

### 2.2 Layer 2 — Scanners

| # | Inputs | Outputs | Deps | Status | UI | Prod usage | AI | Learning | Action |
|---|---|---|---|---|---|---|---|---|---|
| L2-01 CEX_ARBITRAGE | L1-01/02, L1-06 | Candidate opps | L3-02/03/04 | **Active** (43/h) | Ops → Scanners | Yes | Heuristic + ConfScorer | reads L3-06 | Reuse |
| L2-02 DEX_ARBITRAGE | L1-03/04, L1-09 | Candidates | L3-02/03/04 | **Active** (27/h) | Ops → Scanners | Yes | Heuristic + ConfScorer | reads L3-06 | Reuse |
| L2-03 FUNDING_ARBITRAGE | L1-11 | Candidates | L3-02/03 | **Active** (12/h) | Ops → Scanners | Yes | Heuristic | reads L3-06 | Reuse |
| L2-04 CROSS_CHAIN_ARBITRAGE | L1-03/04, bridge feeds | Candidates | L3-02/03 | **Active** (9/h) | Ops → Scanners | Yes | Heuristic | reads L3-06 | Reuse |
| L2-05 FLASH_LOAN_ARBITRAGE | L1-09, gas feed | Candidates | L3-02/03, L4-07 | **Partially Active** (PAUSED in current op state) | Ops → Scanners | Toggleable | Heuristic | reads L3-06 | Reuse (operator-gated) |
| L2-06 LAUNCH_ARBITRAGE | L1-10 | Candidates | L3-03 | **Active** (3/h) | Ops → Scanners | Yes | Heuristic | reads L3-06 | Reuse |
| L2-07 SPATIAL_ARBITRAGE | L1-01/02 | Candidates | L3-02 | **Not Implemented** — no `scanners/spatial_arbitrage/` directory in canonical v1.0.2 | Ops → Scanners (fixture only) | No | Heuristic | reads L3-06 | **New (deferred — validate the 6 existing families first)** |
| L2-08 STATISTICAL_ARBITRAGE | L1-01/02, historical | Candidates | L3-02/09 | **Not Implemented** — no `scanners/statistical_arbitrage/` directory in canonical v1.0.2 | Ops → Scanners (fixture only) | No | — | — | **New (deferred)** |

### 2.3 Layer 3 — Scoring & Learning

| # | Inputs | Outputs | Deps | Status | UI | Prod usage | AI | Learning | Action |
|---|---|---|---|---|---|---|---|---|---|
| L3-01 RegimeDetector | Vol series, feed health | `{regime, tags, confidence}` | L1-* | **Active** | Home → Pulse | Yes | Heuristic + possible local classifier | writes regime snapshot | Reuse (add history sparkline per AI-1) |
| L3-02 ConfidenceScorer | Route hist, regime, depth, freshness | `confidence [0..1] + breakdown` | L3-01/06 | **Active** | Drawer → Reasoning | Yes | Local weighted model | writes decision log | Reuse |
| L3-03 SafetyScorer | Venue drift, liquidity, safety flags | `safety [0..1]` | L1-*, L6-05 | **Active** | Drawer + card | Yes | Heuristic | reads outcomes | Reuse |
| L3-04 FreshnessScorer | Quote timestamps | `fresh_window_s`, boolean gate | L1-01/02 | **Active** | Drawer | Yes (gate) | none | none | Reuse |
| L3-05 VerdictEngine | scores + gates | GO/SOFT_NO/HARD_NO | L3-02/03/04, L4-03 | **Active** | card + drawer | Yes | none | writes decision log | Reuse |
| L3-06 MongoRouteSuccessTracker | Cycle outcomes | Per-route win-rate | L4-02 | **Active** | Drawer (aggregate) | Yes | none | **write-back on every settled cycle** | Reuse (expose history — AI-2) |
| L3-07 DecisionAuditLog | Every verdict | Log entries | L3-05 | **Active** | Intel → Decisions | Yes | none | records decisions | Reuse |
| L3-08 CalibrationRepo * | Predicted vs realised | Reliability + Brier | L3-06/07 | **Interface only** — `learning/calibration.py::ConfidenceCalibrator` ABC, no concrete class | Wave-1 preview endpoint | Not surfaced in canonical | Local | reads outcomes | **New concrete (Wave 3)** |
| L3-09 ModelRegistry * | Model artefacts | Active model IDs, promotion history | L3-* | **Partially Active** as `/shadow/status` + `services/execution/shadow.py` | Wave-1 preview endpoint | Yes via shadow layer | Local | tracks promotions | Refine (formalise) |
| L3-10 GateDropAudit * | Gate evaluations | Per-family drop counts | L3-05, L4-03 | **Active** — `services/execution/opportunity_gate.py` + scanner `/gate-analysis` endpoints | Ops → Scanners (counter only) | Yes | none | none | Refine |

### 2.4 Layer 4 — Execution

| # | Inputs | Outputs | Deps | Status | UI | Prod usage | AI | Learning | Action |
|---|---|---|---|---|---|---|---|---|---|
| L4-01 Order Router / Venue Fanout | Approved opp + policy | Fills + fanout log | L4-07, L6-05 | **Active** | none | Yes | Rule-based | none | Refine (surface policy — EX-1) |
| L4-02 Cycle Lifecycle Manager | Router events | Cycle rows + PnL | L4-01, L5-01 | **Active** | Ops → Cycles (rows only) | Yes | none | writes L3-06, L5-01 | Refine (add DAG viewer — EX-2) |
| L4-03 SafetyInterlock | 5 gate inputs | armed/state, gates[] | L3-01/03/04, L5-03 | **Active** | Ops → Interlock | Yes | Rule-based | writes transition log | Reuse |
| L4-04 Approval Workflow | Proposed action | Sign-state machine | L6-01, L6-07 | **Active** — `services/execution/approval_workflow.py` PROPOSED→APPROVED→QUOTED→CLOSED | none | Yes (execution-side) | none | records approvals | **Reuse + Refine (expose via UI)** |
| L4-05 Kill-Switch Controller | Emergency trigger | Global stop broadcast | L4-03, L6-16 | **Partially Active** — arm/disarm exists in `safety_interlock.py`; no global-kill endpoint | none (header slot planned) | Partial | none | writes audit log | Refine (add endpoint) |
| L4-06 Slippage Attribution | Fills + quote at t0 | Per-leg slippage | L4-01/02 | **Data present** in `arbitrage_cycles.py` + `evidence_accuracy.py`; not aggregated | none | Aggregate PnL only | none | reads outcomes | Activate (EX-3) |
| L4-07 Gas Strategy | Chain gas oracles | Gas policy per chain | L1-06, L4-01 | **Partially Active** (constants) | none (only referenced in Settings → Execution) | Yes (implicit) | none | none | Refine (extract subsystem, per Treasury & Sec §8) |
| L4-08 Portal Quote Diagnostic | L1-01/02 | Raw payload | none | **Active** (endpoint exists per pulse pointer) | none | Debug only | none | none | Refine (surface behind Ops → Integrations expand) |
| L4-09 Execution Position Repo | Fills | Open positions | L4-01/02 | **Active** | Portfolio → Positions | Yes | none | reads L4-02 outcomes | Reuse |

### 2.5 Layer 5 — Portfolio, Treasury, Ledger

| # | Inputs | Outputs | Deps | Status | UI | Prod usage | AI | Learning | Action |
|---|---|---|---|---|---|---|---|---|---|
| L5-01 TreasuryLedger | Cycle PnL, transfers, deposits | Entries + vault snapshots + PnL | L4-02, L5-06/07 | **Active** | Portfolio → Ledger + Treasury + Deployable + Balances | Yes | none | reads outcomes | Refine (running balance at read; slippage field) |
| L5-02 VenueBalanceService | Venue APIs | Per-venue balances | L6-05 | **Active** | Portfolio → Balances | Yes | none | none | Reuse |
| L5-03 CapitalRouter | L5-02, L4-07, pending orders | Deployable snapshot | L5-02, L4-07 | **Active** (Slice-0 pointer to `/api/portfolio/deployable`) | Portfolio → Deployable + Interlock gate | Yes | none | reads outcomes | Refine (unify with Interlock — Treasury & Sec §9) |
| L5-04 ExposureAnalyzer | L5-01/02 | Exposure by asset / chain | L5-01/02 | **Active** | Portfolio → Exposure | Yes | none | none | Reuse |
| L5-05 AllocationPolicy | L5-01/02, config | Target vs actual per bucket | L5-04 | **Active** | Portfolio → Allocation | Yes | none | none | Refine (rebalance proposals — 1.5.8) |
| L5-06 Transfer Service | Instruction | Executes cex/vault/bridge | L6-05, L6-07 | **Partially Active** * (executes today without approval workflow) | Portfolio → Transfers (read-only) | Yes | none | writes L5-01 | Refine (route through Approval Workflow) |
| L5-07 Vault Reconcile Service | On-chain snapshots | Diff vs ledger | L5-01, L1-03/04 | **Partially Active** (fire-and-forget, no diff report) | Settings → Vault | Yes | none | writes L5-01 | Refine (SEC-7 diff report) |
| L5-08 Evidence Bundle Exporter | Cycle materials, audit log | Signed evidence.zip | L4-02, L6-07 | **Active as assembler** — `services/execution/certification_evidence.py` builds 8-section package; signing + HTTP endpoint missing | Drawer references it (unwired) | Partial | none | reads audit | **Refine (add signing + endpoint wrapper)** |

### 2.6 Layer 6 — Governance, Compliance, Knowledge

| # | Inputs | Outputs | Deps | Status | UI | Prod usage | AI | Learning | Action |
|---|---|---|---|---|---|---|---|---|---|
| L6-01 UserService | Auth + profile | Account model | L6-07 | **Active** | Settings → Account | Yes | none | none | Reuse |
| L6-02 OperatorFlags | Modes + flags | Snapshot / mutations | L6-16 | **Active** | Settings → Operational | Yes | none | writes audit | Reuse |
| L6-03 NotificationConfig | Channels config | Send routing | L6-16 | **Active** | Settings → Notifications | Yes | none | none | Reuse |
| L6-04 ExecutionPolicy | Config | Effective policy | L4-03 | **Active** | Settings → Execution + Interlock | Yes | none | writes audit | Refine (2-phase apply for high-risk fields) |
| L6-05 VenueRegistry | Venue configs | Metadata + connectivity | L6-07 | **Active** | Ops → Venues + Settings → Exchanges | Yes | none | none | Refine (compliance flags join; rotate_key) |
| L6-06 WalletRegistry * | Address book | Wallet metadata | L6-07 | **Active** — `services/vault.py` + `services/execution/wallet_observer.py` + `bdag_transfers.py` + canonical `/wallets` endpoint | none consolidated | Yes | none | none | Merge (consolidate the three cooperating files) |
| L6-07 SecretManagement * | Secrets | KMS handles | none | **Partially confirmed** — env-var + `.env.production.example`; no dedicated KMS module | none | Yes | none | none | Merge |
| L6-08 ComplianceRegistry | Sanctions / restricted lists | Flags per venue/asset | external | **Not Implemented** | none | **No** | none | none | **New (justified)** |
| L6-09 RouteCertifier * | Route outcomes | Candidate → canonical state | L3-06 | **Active** — `services/execution/certification.py` + `certification_review.py` (READY_FOR_MICROCAPITAL_REVIEW / NEEDS_MORE_DATA / NOT_READY) | Intel → Certification (Wave-2 preview) | Yes canonical-side | none | reads outcomes | Refine + Expose |
| L6-10 Entity Graph * | Venues, tokens, teams, chains | Graph queries | L1-* | **Active** — 5 canonical endpoints (`/entities`, `/entities/clusters`, `/entities/scores/top`, `/entities/resolve`, `/entities/{id}`) | Intel → Knowledge (Wave-2 preview) | Yes | none | none | Refine + Expose |
| L6-11 Similarity Search * | Route / opp features | K-nearest | L6-10, L3-09 | **Partially Active** via entities/clusters + sequences/patterns; no dedicated KNN endpoint | none | Partial | Local | none | Refine (add KNN endpoint) |
| L6-12 Playbook Store | Docs | Playbook lookups | none | **Dormant** (docs only) | Settings → Documentation index | No | none | none | Refine (endpoint-back later) |
| L6-13 Backup / Restore | Persistence | Backups | CLI | **Active** (CLI only, `scripts/backup.sh`) | none | Yes ops-side | none | none | Reuse (surface last-ts read-only) |
| L6-14 Deploy Verification Harness | Deployment | 8-cat verify | CLI | **Active** (v1.0.2, `scripts/verify-deployment.sh`) | none | Yes ops-side | none | none | Reuse (feed metrics — ENH-001) |
| L6-15 Health Probe | Runtime | ready / live | none | **Active** | none | Yes ops-side | none | none | Refine (surface uptime strip) |
| L6-16 AlertRepo / AlertService | Ops events | Alerts + ack | many | **Active** | Ops → Alerts | Yes | none | none | Reuse |
| L6-17 WorkerRegistry | Background workers | Queue stats | none | **Active** | Ops → Queues | Yes | none | none | Reuse |

### 2.7 Discovery

| # | Inputs | Outputs | Deps | Status | UI | Prod usage | AI | Learning | Action |
|---|---|---|---|---|---|---|---|---|---|
| DSC-01 DiscoveryRepo | Signals from L1-07..14 | Candidate store | L1-* | **Active** | Discovery | Yes | none | none | Reuse |
| DSC-02 DiscoveryScorer | Signals + curated sources | Score [0..1] | DSC-01 | **Active** | Discovery (score column) | Yes | Heuristic (weighted signal set) | none | Refine (calibrate — mirror L3-08) |
| DSC-03 DiscoveryTransition Service | Operator action | State machine | DSC-01, L6-16 | **Active** | Discovery row action | Yes | none | writes audit | Reuse |

---

## 3 · AI Capability Inventory

**Reality check.** ArbiCore X's "AI-powered" positioning is grounded in
statistical scoring, not in LLM chat. There is no verified external
LLM/AI-provider dependency in the canonical repo per the audit sources
available in this pod. All AI capabilities today are **local, deterministic,
model-file backed** (statistical / heuristic / small ML models).

### 3.1 AI-typed engines

| # | Engine | AI type | Model provenance | External provider? | Notes |
|---|---|---|---|---|---|
| A-1 | RegimeDetector (L3-01) | Classifier + rules | Local | No | Emits `{regime, tags, confidence}` |
| A-2 | ConfidenceScorer (L3-02) | Weighted multi-factor | Local | No | Per-factor breakdown surfaced in UI |
| A-3 | SafetyScorer (L3-03) | Heuristic + rules | Local | No | |
| A-4 | STATISTICAL_ARBITRAGE Scanner (L2-08) | Statistical ML (z-score / cointegration) | Local | No | Only ML-heavy scanner |
| A-5 | DiscoveryScorer (DSC-02) | Weighted signal set | Local | No | Signal-driven; no LLM |
| A-6 | Similarity Search (L6-11) | Vector KNN | Local | No | Dormant; would need embedding pipeline |
| A-7 | News / Narrative Feed classifier (L1-14) | *(optional)* LLM tag classifier | External-optional | Potential Emergent LLM key candidate | Dormant; would benefit from LLM for tag normalisation |

### 3.2 Where an external LLM could add value
Only in **discovery-narrative normalisation** (A-7). Every other AI
capability in ArbiCore X is deterministic and should stay local:
- Latency budgets in scanners and gates rule out LLM calls in the hot path.
- Regulatory posture prefers reproducible, explainable local models.
- Confidence + safety scorers already emit per-factor breakdowns — LLM
  would only obscure this.

**Recommendation:** Do **not** introduce external LLM dependency in Phase A–G.
Reserve LLM (via Emergent Universal Key) exclusively for future
narrative-feed classification (L1-14) and Discovery signal enrichment.

### 3.3 Missing AI surfaces (not new AI engines — new **exposures**)

- **Calibration surface** (from L3-08) — no new model, just expose.
- **Model registry surface** (from L3-09) — no new model.
- **Explainability annotation** in Drawer Reasoning tab — reuses L3-02/05
  breakdown data.

---

## 4 · Learning Engine Inventory

Engines that participate in a closed learning loop
(outcome → model update / stats update).

| # | Engine | Loop closure | Read outcomes | Write model / stats | Freq | Loop health |
|---|---|---|---|---|---|---|
| LE-1 | MongoRouteSuccessTracker (L3-06) | **Closed** | Every settled cycle | Per-route win-rate, mean outcome | continuous | Verified via Slice-0 endpoint |
| LE-2 | ConfidenceScorer (L3-02) | **Closed** | via L3-06 factor | Weights tuning * | offline | Assumed batch retraining; needs verification |
| LE-3 | SafetyScorer (L3-03) | Partial | via alert / venue events | Heuristic threshold updates | manual | Depends on VenueRegistry + AlertRepo signals |
| LE-4 | RegimeDetector (L3-01) | Partial | vol + feed health | Regime label distributions | continuous | Emits confidence per snapshot |
| LE-5 | DecisionAuditLog (L3-07) | **Read-only** by learning | — | — | — | Source of truth; not itself a learner |
| LE-6 | CalibrationRepo (L3-08) | **Would-be closed** | predicted vs realised | Reliability curves | dormant | Not scheduled today |
| LE-7 | ModelRegistry (L3-09) | Meta-loop | via L3-08/06 | Promotion records | manual | Dormant |
| LE-8 | STATISTICAL_ARBITRAGE (L2-08) | **Closed** internally | Per-pair z-history | Rolling stats + spread bands | continuous | Verified via scanner counters |
| LE-9 | DiscoveryScorer (DSC-02) | Partial | Promoted/dismissed rate | Signal-weight tuning * | manual | Missing calibration |
| LE-10 | RouteCertifier (L6-09) | **Would-be closed** | via L3-06 aggregate | Candidate → canonical promotion | dormant | Missing UI + scheduler |

**Loop health headline.** One loop (LE-1) is verifiably closed and
continuous. Four loops are closed but dormant or missing exposure
(LE-6, LE-7, LE-10, plus LE-9's calibration side). Two loops are partial
and would benefit from formalisation (LE-3, LE-4).

**Priority activations (no new engines, only scheduling + exposure):**
- Activate **CalibrationRepo** (LE-6) to close L3-02 / L3-05 calibration.
- Activate **RouteCertifier** (LE-10) to close route promotion.
- Formalise **DiscoveryScorer** calibration (LE-9) — same shape as LE-6.

---

## 5 · Engine Activation Matrix — summary counts

> **CORRECTED (2026-07-31) after file-verified audit.** Original counts
> misclassified 3 engines as "New" that are actually already
> implemented. Corrected distribution below.

| Action | Count | % |
|---|---|---|
| Reuse | 24 | 47% |
| Refine | 17 | 33% |
| Activate (dormant / partial) | 5 | 10% |
| Merge (consolidation) | 2 | 4% |
| **New (justified)** | 2 | 4% (concrete `ConfidenceCalibrator`, `ComplianceRegistry`) |
| Deferred (net-new, low priority) | 2 | 4% (SPATIAL_ARBITRAGE, STATISTICAL_ARBITRAGE scanners) |
| Retire | 0 | 0% |
| **Total engines** | **51** | 100% |

**Headline (corrected):** 47% pure reuse, 33% refinements, 10% activations.
**Only 2 engines are genuinely net-new** (down from prior claim of 3).
Two additional net-new scanner builds (SPATIAL, STATISTICAL) are
deferred until the 6 existing scanner families are validated in
production.

No engine is recommended for retirement.

---

## 6 · Recommended activation order

The order below is optimised to (a) unlock UI value fast, (b) keep the
production hot-path stable, (c) close learning loops early because the
gains compound, and (d) defer the one new subsystem until it can be
built on a stable base.

### Wave 1 — Learning loop closure (weeks 1–2)
- Activate **CalibrationRepo (L3-08)** — schedule + repo already present;
  needs periodic job + read surface.
- Activate **ModelRegistry (L3-09)** — surface active model IDs; no new
  model training required.
- Refine **DecisionAuditLog (L3-07)** to include model/policy version
  (AI-5 from institutional audit).
- Refine **DiscoveryScorer (DSC-02)** calibration (LE-9).

**Why first:** these are pure exposures / scheduling wins. Zero
production-hot-path risk. Immediate institutional-audit value.

### Wave 2 — Dormant-scanner activation (week 3)
- Activate **SPATIAL_ARBITRAGE (L2-07)** — validate profitability
  profile; keep IDLE if margin < threshold. No new code, only op review.
- Activate **RouteCertifier (L6-09)** — expose promotion state machine
  and schedule. Reuses L3-06.

**Why second:** low-risk revenue capture; validates learning loop is
actually improving verdicts.

### Wave 3 — Execution transparency (weeks 4–5)
- Refine **Cycle Lifecycle Manager (L4-02)** for DAG viewer (EX-2).
- Activate **Slippage Attribution (L4-06)** — data present in fills.
- Refine **Order Router (L4-01)** to surface policy + fallback (EX-1).
- Refine **Portal Quote Diagnostic (L4-08)** exposure.
- Refine **GateDropAudit (L3-10)** drilldown.

**Why third:** these engines already produce the required data;
activation is UI-surfaces plus small backend projection. Not touching
the write path.

### Wave 4 — Consolidation & Merge (week 6)
- Merge **WalletRegistry (L6-06)** into a single subsystem
  (Treasury & Sec §4 ownership map).
- Merge **SecretManagement (L6-07)** into a single subsystem
  (Treasury & Sec §7 ownership map).
- Refine **Gas Strategy (L4-07)** — extract as its own subsystem
  (Treasury & Sec §8).
- Refine **CapitalRouter (L5-03)** — align with Interlock gate
  (Treasury & Sec §9).
- Refine **TreasuryLedger (L5-01)** — running balance at read;
  slippage field.
- Refine **Vault Reconcile (L5-07)** — diff report (SEC-7).

**Why fourth:** consolidation is the natural cleanup after execution
transparency is live and after learning loops are producing value.

### Wave 5 — New subsystem: Approval Workflow (weeks 7–8)
- Build **Approval Workflow (L4-04)** — the one justified new subsystem
  (Treasury & Sec §10).
- Route Transfer Service (L5-06), Interlock DISARM, high-risk Execution
  Policy PATCH, and vault reconcile (on non-zero diff) through it.

**Why fifth:** this is the highest-risk new build, and it needs to be
built on top of stable audit logging (which the earlier waves refine).

### Wave 6 — Missing capability build (weeks 9–10)
- Build **Evidence Bundle Exporter (L5-08)**.
- Build **ComplianceRegistry (L6-08)**.
- Activate **Kill-Switch Controller (L4-05)** — endpoint + broadcast.

**Why last:** these are policy-driven capabilities that benefit from
Approval Workflow being in place first (signing keys go through
SecretManagement; kill-switch triggers audit-log entries; compliance
flags feed into both scanner gates and UI).

### Wave 7 — Health / Ops polish (rolling, low priority)
- Refine **Health Probe (L6-15)** — 24 h uptime strip.
- Refine **Deploy Verification Harness (L6-14)** — Prom metrics
  exporter (ENH-001).
- Refine **Playbook Store (L6-12)** — endpoint-backed.
- Activate **Whale Tracker (L1-13)**, **Funding Feed (L1-11)**,
  **Depth Feed (L1-12)**, **News Feed (L1-14)** — each behind its own
  future UI sub-tab, per institutional audit §2.
- Activate **Entity Graph (L6-10)** and **Similarity Search (L6-11)**
  — very long-term.

---

## 7 · Gaps that genuinely require new implementation

> **CORRECTED (2026-07-31) after file-verified audit.** Only 2 net-new
> engines remain; the previously-claimed third (Approval Workflow)
> is already implemented and only needs UI exposure.

| # | Engine | Why net-new | Design already documented in | Alternative that was rejected |
|---|---|---|---|---|
| G-1 | **Concrete ConfidenceCalibrator** (behind `learning/calibration.py`) | Interface exists but `"Not implemented yet"`; no concrete subclass shipped | Wave-1 endpoint contract already frozen — a concrete implementation only needs to produce the same shape | "Ship the Wave-1 preview stub as production" — rejected because the numbers must be computed from real outcomes to be trustworthy |
| G-2 | ComplianceRegistry (L6-08) | No canonical sanctions / restricted-list registry | `07_INSTITUTIONAL_AUDIT.md` 1.6.7 + `09` §12 | "Hard-code allowlist per venue" — rejected because it can't handle jurisdiction changes or asset additions |

Adjacent items are **exposures + refinements, not new engines**:
- **Approval Workflow (L4-04)** — canonical file exists; needs UI wiring + threshold policy config.
- **Evidence Bundle (L5-08)** — canonical assembler exists; needs signing + endpoint wrapper.
- **RouteCertifier (L6-09)** — canonical exists; Wave-2 exposes via new preview endpoint.
- **Entity Graph (L6-10)** — canonical exists with 5 endpoints; Wave-2 exposes composed view.
- **Similarity Search (L6-11)** — canonical partial; add KNN endpoint.
- **Kill-switch (L4-05)** — refine `safety_interlock.py` with a global-kill endpoint.

Two additional items are **deferred net-new builds** (not currently in
scope):
- SPATIAL_ARBITRAGE scanner (no code in canonical).
- STATISTICAL_ARBITRAGE scanner (no code in canonical, previously
  misclassified as "Active 6/h" — this was a fixture, not real data).

---

## 8 · Cross-references

- Every `Refine` action ties to a Preview→Prod audit refinement
  (see `08` §1–§5 refinements column).
- Every `Merge` action ties to Treasury & Security ownership map
  (see `09` §15).
- Every `New` action ties to Refined Roadmap Phase E or F
  (see `10` §1).
- Every `Activate` action ties to institutional audit backlog
  P0–P3 (see `07` §8).

---

## 9 · Deliverable status

- [x] Engine Inventory — 51 engines catalogued (§1).
- [x] Engine Activation Matrix — 11-column table populated per engine
      (§2).
- [x] AI Capability Inventory — 7 AI-typed engines, LLM strategy
      recommendation (§3).
- [x] Learning Engine Inventory — 10 learning loops, health assessed
      (§4).
- [x] Recommended activation order — 7 waves, sequenced (§6).
- [x] Gaps requiring new implementation — 3 engines, all pre-identified
      (§7).

No code written. No refactor performed. No integration performed.
