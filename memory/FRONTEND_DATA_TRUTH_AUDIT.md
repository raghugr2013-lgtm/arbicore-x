# ArbiCore X — Frontend Data-Truth / Operator-Trust Audit

Date: 2026-06 · Author: E1 (read-only audit)
Scope: Complete operator console (React v2 UI mounted at `/dashboard`) + backing FastAPI
source-of-truth. **READ-ONLY. No code changed. No execution/live/signing enabled.**

> This is Phase 1 (audit) of the task. Phase 2 (P0/P1 fixes in controlled batches with tests)
> is deferred until you review this report. Nothing here weakens M3 fail-closed semantics.

---

## 0. How to read this report

**Active UI**: `frontend/src/App.js` mounts `AppShell` (the `src/v2/*` app) at `/dashboard`.
The older `src/pages/*` and `src/components/execution|panels|portfolio` trees are **legacy /
not routed** in the primary flow (kept only behind `?ui_v2` overrides / deep links). Every
operator-facing screen the user named is a `v2/pages/*` file. Data reaches the UI via two
clients:
- `v2/lib/api.js` (`v2Api.*`) — used by Opportunities, Discovery, Portfolio, Settings, etc.
- direct `axios.get(${REACT_APP_BACKEND_URL}/api/...)` — used by Control Center, Live Ops,
  Capital/Wallet.

All `/api/arbicore/*` handlers audited live in the monolith `backend/server.py` (8327 lines).
Legacy panels also call `arbicore/routes/*` — out of the primary path.

### Classification legend (as requested)
| Tag | Meaning |
|-----|---------|
| `REAL_LIVE` | Value read live from an external system (on-chain quote/RPC) at request time |
| `REAL_ONCHAIN` | On-chain balance/liquidity read (eth_call / balanceOf) |
| `REAL_DATABASE` | Persisted real record faithfully surfaced from Mongo |
| `CALCULATED` | Deterministically computed from real inputs (honest math) |
| `DERIVED` | Computed from a real input but via a **fabricated / non-authoritative** transform (e.g. ±10 % band, mislabelled unit) |
| `CACHED` | Snapshot refreshed periodically (RPC caps, startup self-tests) |
| `STALE` | Real but past its freshness window |
| `UNAVAILABLE` | Genuinely absent; **should** render "—" |
| `UNVERIFIED` | Present but not economically/live validated |
| `PLACEHOLDER` | Sentinel/init default standing in for a real value not yet wired |
| `DEMO` | Hardcoded sample payload |
| `HARDCODED` | Constant literal in code |

### Priority legend
- **P0** — operator/safety/financial-truth issue (a raw discovery can *look* executable/safe/profitable)
- **P1** — incorrect financial/market value shown as real
- **P2** — non-critical stale/empty handling
- **P3** — cosmetic

---

## 1. Executive summary (the headline)

The Control Center and Live Ops screens are genuinely **backend-authoritative and honest** —
they render server-decided GREEN/YELLOW/RED and use "—" for absent values. The **data-truth
failures are concentrated in ONE translation function and its frontend formatters**, and they
fully explain every symptom you reported (`confidence=0`, `spread=0.0 bps`, `depth=$0`, huge
`%` returns, fake 100 % safety):

- **Backend** `server.py::_canonical_opp_to_contract()` (lines **1013-1049**) coerces every
  missing economic field to `0` (`or 0`) instead of `null`, fabricates a return "range" from a
  **USD profit** figure, mislabels **capital-required as depth**, and derives **verdict from
  lifecycle status** (VALIDATED→GO) rather than economic validation.
- **Frontend** `v2/components/Primitives.jsx` `ConfidencePill`/`SafetyPill` coerce `null → 0`
  and render it as a real low score; `fmtPct()` multiplies the (USD) return field by 100 and
  appends `%` → the **implausible return percentages**; `fmtBps`/`fmtUsd` faithfully print the
  backend's coerced zeros.

Net effect: a `CANDIDATE` row that was never live-priced (all economics `None`, provenance
`SIMULATED`, `risk_score=0.0`) is shown to the operator as **CONF 0 · SAFE 100 % · spread
0.0 bps · depth $0 · est. return tens-of-thousands %**, with a **GO** badge once it reaches
VALIDATED. That is precisely the operator-trust hazard to eliminate.

**No screen enables or exposes execution/signing/broadcast**; these are display-truth defects,
not safety-gate breaches. The M3 fail-closed pipeline itself is intact.

---

## 2. Backend source-of-truth map (answers Question A + the prod-Mongo question)

Every repo's **actual** Mongo collection name (verified in code). This resolves the confusion
in the handoff about "missing" `arbicore_*`-prefixed collections — several of those names were
never the real names.

| Domain (UI concept) | Repo / engine | **Actual collection(s)** | Default when empty |
|---|---|---|---|
| Opportunities · confidence · spread · depth · est.return · verdict | `MongoOpportunityRepository` | **`arbicore_opportunities`** | empty list (honest) |
| Discovery candidates · score | same repo, projected | **`arbicore_opportunities`** | empty list (honest) |
| Opportunity audit trail | `OpportunityJournal` | **`arbicore_opportunity_journal`** | empty |
| Operator console mode (SHADOW/PAPER/…) | `ControlStateRepo` | **`control_state`** (+ `control_state_audit`) | **default `SHADOW`** in-code |
| Per-strategy execution mode | `ExecutionModeRepo` | **`execution_mode_state`** (+ `_audit`) | default map (OBSERVE/SHADOW) |
| Capital policy | `CapitalPolicyRepo` | **`capital_policy`** (+ `_audit`) | `DEFAULT_POLICY` constant |
| Wallet registry | `WalletRegistryRepo` | **`wallet_registry`** (+ `_audit`) | empty |
| Wallet metrics | canonical | **`arbicore_wallet_metrics`** | empty |
| Scanner / network / account / execution / operational / notifications config | `ConfigRepo` (+ typed wrappers) | **`arbicore_config`** (one doc per `_id: kind`), drafts in `arbicore_config_drafts`, audit `arbicore_config_audit` | typed defaults |
| Execution plans | `ExecutionPlansRepo` | **`execution_plans`** | empty |
| Evidence bundles | `EvidenceBundlesRepo` | **`evidence_bundles`** | empty |
| Calibration models | `CalibrationModelsRepo` | **`calibration_models`** | empty |
| Kill switch | `KillSwitchRepo` | **`kill_switch` / `kill_switch_audit`** | disengaged |

### Why the handoff's "missing" collections are expected (not a defect)
- `arbicore_scanner_config`, `arbicore_execution_settings`, `arbicore_operational_flags`,
  `arbicore_capital_policy`, `arbicore_wallet_registry` **were never collection names**. In
  code:
  - scanner/execution/operational/notifications/network/account config are all stored as
    **`_id: <kind>` documents inside the single `arbicore_config` collection** (which prod
    *does* have). So "scanner state / execution settings / operational flags" live inside
    `arbicore_config`, not in dedicated `arbicore_*` collections.
  - capital policy → `capital_policy` (prod has this), wallet registry → `wallet_registry`.
  - `arbicore_control_state` is really **`control_state`**; if prod lacks it, operator mode has
    simply never been persisted and `ControlStateRepo.get_mode()` returns the safe default
    **`SHADOW`**. This is a legitimate fail-safe default, **not** fabricated data.

### Source of truth per requested field (Question A, precise)
- **scanner state** → in-memory `ContinuousScanner.status()` (`/arbicore/engine/scanner/status`)
  + per-family config doc in `arbicore_config` (`kind=scanner`). Not a standalone collection.
- **flash-loan discovery** → `ContinuousDiscovery` writes `CanonicalOpportunity` rows into
  `arbicore_opportunities` (wired at `server.py:286`); cadence mirror in `opportunities`
  (Wave-7A). The live engine scan is `_CONTINUOUS_SCANNER` (decision history in
  `decision_history` / `route_recurrence` / `profit_alerts`).
- **opportunities / confidence / spread / depth / est.return / verdict** → `arbicore_opportunities`
  via `_canonical_opp_to_contract` (**the defect epicentre — §3**).
- **depth/TVL** → **NOT a real field on the opportunity.** UI "Depth" is `capital_required_usd`
  (see P1-2). Real pool TVL only exists in the flash-loan searcher path (M2.2 `tvl_provider` /
  `min_pool_tvl_usd_in_route`), which is **not** surfaced to the Opportunities table.
- **readiness** → `ExecutionReadinessEngine.evaluate()` (`control/readiness.py`) —
  backend-authoritative, honest.
- **mode** → `control_state` (default SHADOW).
- **capital policy** → `capital_policy` (default `DEFAULT_POLICY`).
- **wallet state** → live `WalletIntelligenceEngine` on-chain reads for the configured gas
  wallet (`arbicore_wallet_metrics` for history).

---

## 3. Opportunities screen — full field trace (answers Questions B, D)

**UI**: `v2/pages/OpportunitiesPage.jsx` table + `v2/components/OpportunityDrawer.jsx`.
**API**: `GET /api/arbicore/opportunities` → `server.py:963` (list) / `:1052` (detail).
**Translator**: `_canonical_opp_to_contract()` `server.py:1013-1049`.
**Model**: `arbicore/models/canonical.py::CanonicalOpportunity`.
**Formatters**: `v2/components/Primitives.jsx` (`ConfidencePill`, `SafetyPill`, `VerdictBadge`,
`FreshnessBadge`, `fmtUsd`, `fmtPct`, `fmtBps`).

Model note (canonical.py:78-95): `spread_pct`, `expected_profit_usd`, `capital_required_usd`,
`buy_price`, `sell_price` are correctly `Optional[float] = None`. BUT `confidence_score: 0.0`,
`risk_score: 0.0`, `liquidity_score: 0.0` default to **0.0 (not None)**, and
`source_data_quality` defaults to **`SIMULATED`**.

| UI field | Backend expr (line) | Source field | Class | Finding |
|---|---|---|---|---|
| Asset | `subject_id or asset` (1030) | real | `REAL_DATABASE` | OK |
| Family | `opportunity_type` (1031) | real | `REAL_DATABASE` | OK |
| Chain | `chain or "-"` (1034) | real | `REAL_DATABASE` | OK |
| **Verdict** (GO/SOFT_NO/HARD_NO) | `GO if status in {APPROVED,VALIDATED}` (1025-1027) | lifecycle `status` | **`DERIVED`** | **P0-3**: verdict = FSM stage, **not** economic validation. A candidate auto/operator-moved to VALIDATED shows **GO** with zero economic backing. |
| **Confidence** | `float(confidence_score or 0)` (1022) | `confidence_score` (default 0.0) | **`PLACEHOLDER`→shown real** | **P1-3**: unscored candidate → `0` rendered as a real 0 % low-confidence pill, not "—". |
| **Safety** | `1 - min(1, risk_score/100)` (1037) | `risk_score` (default 0.0) | **`DERIVED`** | **P0-1 (worst)**: `risk_score=0.0` → **safety = 1.0 → SAFE 100 %** for a never-risk-assessed row. Fake green. |
| **Spread** | `int(round((spread_pct or 0)*100))` (1038) | `spread_pct` | **`DERIVED` + coercion** | **P1-1**: `None → 0` shown as `0.0 bps` (real-looking). Also unit assumes `spread_pct` is in **percent**; if a scanner ever stores a fraction the bps is 100× wrong. |
| **Depth** | `int(round(capital_required_usd or 0))` (1039) | `capital_required_usd` | **mislabel + coercion** | **P1-2**: column labelled "Depth" (implies pool liquidity/TVL) but is **capital required**. `None → $0`. |
| **Est. return low/high** | `(expected_profit_usd or 0)*0.9 / *1.1` (1040-1041) | `expected_profit_usd` (USD) | **`DERIVED` (unit + fabricated band)** | **P0-2**: (a) USD value rendered by `fmtPct` = `×100 %` → **e.g. $1 000 → "90 000 %"** = the implausible returns you saw. (b) ±10 % band is fabricated, not a real interval. (c) `None → $0` → "0.00 %". |
| Age | `age_s` (1019, `except → 0`) | `created_at` | `CALCULATED` (P3) | On parse failure → `0` → FreshnessBadge shows fresh green "0s ago". |
| Provenance | `source_data_quality` (1045) present in payload | real | `REAL_DATABASE` **but unused** | **P1-5**: `SIMULATED/REAL/VERIFIED_REAL` is in the response yet **never rendered** in table or drawer. Operator cannot distinguish simulated from real. |

### Frontend formatter defects (`Primitives.jsx`)
- `ConfidencePill` (42): `Math.max(0, Math.min(1, Number(value) || 0))` → `null/undefined → 0`
  and paints a low-band pill. No "—"/UNAVAILABLE state. (**P1-3/P1-4**)
- `SafetyPill` (80): same pill → amplifies **P0-1**.
- `fmtPct` (129): `(Number(n)*100).toFixed(2)+"%"` → root of the **P0-2** implausible %.
- `fmtBps`/`fmtUsd` (122-137): correctly return "—" for `null`, but backend already coerced
  `null→0`, so "—" never triggers.
- `FreshnessBadge` (84): `Number(ageSeconds) || 0` → unknown age renders "0s ago" fresh green.

### Drawer extras (`OpportunityDrawer.jsx` / detail `server.py:1061-1080`)
- Reasoning `confidence_breakdown` (1063-1069): **`DEMO`** — a single synthetic row
  `delta = confidence*10`, `gates_passed=["provenance","lifecycle"]` **hardcoded**. Not real
  gate telemetry. (**P1-6**)
- Verification block (1071-1076): `quote_source="canonical_opp_repo"` (**HARDCODED**),
  `fresh_window_s=60` hardcoded, `stale = age>60`. Presented as a "quote source" though no
  quote was taken. (**P1-6**)
- Quote/Sizing tabs read `data.quote.*` / `data.sizing.*` which the detail endpoint **does not
  return** → every row shows "—" (honest, because `Row` uses `?? "—"`). (P3)
- Evidence tab: static empty-state text. (P3, honest)

### Why an "unvalidated" candidate looks executable (Question D — root cause chain)
1. `ContinuousDiscovery`/seed writes a `CanonicalOpportunity` with economics `None`,
   `confidence_score=0.0`, `risk_score=0.0`, `source_data_quality=SIMULATED`,
   `status=CANDIDATE`.
2. `_canonical_opp_to_contract` turns `None→0`, `risk 0→safety 1.0`, `expected_profit_usd→` a
   USD "return", `status→verdict`.
3. Frontend pills/`fmtPct` render those coerced zeros/USD as **real** CONF/SAFE/spread/depth/%.
4. Any promotion to VALIDATED flips verdict to **GO**.
None of this involves a live quote, TVL read, or economics gate — yet the row reads as a
safe, profitable, executable opportunity. **This is the core operator-trust breach.**

---

## 4. Discovery screen (answers B for Discovery)

**UI** `v2/pages/DiscoveryPage.jsx` · **API** `GET /api/arbicore/discovery/candidates`
(`server.py:1428`) · translator `_canonical_opp_to_discovery` (`server.py:1344-1390`).
Source: same `arbicore_opportunities`.

- `score = confidence_score or 0 → ConfidencePill` — same **P1-3** coercion (unscored → 0).
- `why`/`signals` — `CALCULATED` from real row (includes `provenance:simulated`). Honest.
- `source = "canonical:<provenance>"` — good: provenance **is** surfaced here (unlike
  Opportunities).
- `stats` counts — `REAL_DATABASE`. MetricStat defaults `?? 0` — acceptable (a real count of 0).
- `calibration` block `_canonical_discovery_calibration` (1393-1425): honest — rates default
  `0.0` only when `n<10`, `ece=0.0`/`drift_alert=False` are **HARDCODED** placeholders (P2).

---

## 5. Control Center (HONEST — reference implementation)

**UI** `v2/pages/ControlCenterPage.jsx` · **API** `GET /arbicore/control/readiness`
(`server.py:4514`→`ExecutionReadinessEngine.evaluate()`), `GET /arbicore/execution/kill-switch`,
`POST /arbicore/control/mode` (`:4532`).

- Readiness/components/modes/blockers/warnings — **`REAL_DATABASE`/`CALCULATED`**,
  backend-authoritative. Frontend `Pill` falls back to **INFO (blue)**, never fake GREEN, when
  status is missing (`TONE[status] || TONE.INFO`). ✅
- Mode change: backend decides (`can_transition`); LIMITED_LIVE/FULL_AUTOMATION **always
  refused** (`:4538-4540`). ✅
- Emergency Stop wired to authoritative kill switch. ✅
- **Only nit (P3)**: overall/current-mode fall back to `"INFO"`/`"—"` on load error — fine.

This screen is the **model** the Opportunities screen should follow (explicit states, no
coercion, honest fallbacks).

---

## 6. Live Ops (mostly honest)

**UI** `v2/pages/LiveOpsPage.jsx` · **APIs** `/arbicore/engine/scanner/status`, `/engine/checkpoint`,
`/engine/alerts`, `/engine/onboarding`.

- Funnel, top-opportunities, readiness matrix, blockers, onboarding — **backend-authoritative**;
  UI uses `?? "—"` and `!= null ? … : "—"` throughout. ✅ Provenance-respecting.
- Profit Alerts: only fire after the full real chain (quote→net→conf→EV→size→sim). ✅
- **P2/P3**: `Scanner Status` pill = `scanner.running ? "GREEN" : "YELLOW"` and Profit-Alerts
  pill = `total>0 ? "GREEN" : "INFO"`. "GREEN" here means *running / has-alerts*, not
  *ready-to-execute*; a hurried operator could over-read it. Recommend relabelling tone or pill
  text. Non-financial.
- Top-opportunities `confidence`/`size` show `?? "—"` (honest). ✅

---

## 7. Capital / Wallet (real on-chain, RPC-dependent)

**UI** `v2/pages/CapitalIntelligencePage.jsx` · **APIs** `/arbicore/capital/{balances,statement,
reconciliation,venue-stats,wallets,money-trail}` → `WalletIntelligenceEngine` live eth_call.

- Balances/statement/money-trail — **`REAL_ONCHAIN`** for the configured
  `ARBICORE_GAS_WALLET_ADDRESS` (or supplied address). ✅
- **P1-7 (verify in fix phase)**: when no RPC is configured (preview) or the address is unset,
  `_capital_default_address` raises 422 — need to confirm the engine surfaces
  UNAVAILABLE rather than `$0`/empty balances that could read as "wallet is empty". Trace
  `WalletIntelligenceEngine.live_balances` behaviour on RPC failure in the fix phase.

---

## 8. Portfolio, Intelligence, Operations, Settings, Flash-Loan, Journey (endpoint-level)

Audited at API/endpoint level (deep field trace deferred to fix phase; none are the reported
symptom source). Classifications:

- **Portfolio** (`v2Api.positions/balances/transfers/deployable/treasury/ledger/exposure/
  allocation` → `/arbicore/portfolio/*`, `routes/portfolio.py`): `REAL_DATABASE` where rows
  exist. **Check in fix phase** for `or 0` USD coercions mirroring §3 (deployable/treasury).
- **Intelligence** (`recommendations/decisions/calibration/models/certification/entities`):
  learning engines; `calibration_models` real. Some Wave-1/2 endpoints have **no UI consumer**
  (deliberate). `roi-probability` — see P1-8 below.
- **Operations** (`scanners/cycles/venues/interlock/integrations/queues/alerts`,
  `server.py:2017+`): scanner status real (in-memory + `arbicore_config`); interlock real.
- **Settings** (`account/vaults/execution/exchanges/notifications/network/telegram/scanner/
  secrets`): persisted in `arbicore_config` + `wallet_registry` + `arbicore_secrets`. Secrets
  status only (never plaintext). ✅
- **Flash-Loan Operator / Journey / Initialization / Executor-Verify / Post-Trade**: readiness &
  wizard state from `operator_wizard`/`operator_journey`; gated RED; honest blockers. No live
  enable path.

### P1-8 — `roi-probability` is fully hardcoded DEMO
`GET /arbicore/roi-probability` (`server.py:920-931`) returns **hardcoded**
`sample_size=42, win_rate=0.643, realized_outcome_mean=0.012, …` for **any** `route_id`, and is
the **only `/arbicore/*` endpoint with NO auth dependency**. `v2Api.roiProbability` exists; if
any surviving panel renders it, those stats are pure fiction. Class: **`DEMO`/`HARDCODED`**.
(Also a minor auth-consistency gap.)

---

## 9. Suspicious zero/default/placeholder financial paths (answers Question C)

Each flagged path classified as (1) legit init default, (2) fail-closed fallback,
(3) sim/test-only, or (4) **accidental financial value reaching the UI**.

| Path (file:line) | What it is | Verdict |
|---|---|---|
| `discovery/base_venues.py:172` `tvl_usd=0.0` | Synthetic pool-graph nodes carry a **TVL sentinel**; comment: "real TVL is future engineering; depth handled by slippage + size optimizer". | **(1)/(3) sentinel.** Not shown as a real value directly — but note the legacy route-search TVL gate is a **no-op** (`min_pool_tvl_usd=0.0`), i.e. that engine does **not** enforce real depth. Flash-loan searcher path (M2.2) uses a separate real `tvl_provider`. **Depth is genuinely unmeasured in the legacy engine** → don't surface "depth" from it. |
| `economics/net_profit.py:80` `gas_cost_usd=0.0` | Gas computed only if full native-fee triple supplied, else 0. | **(2) fail-safe.** Downstream `opportunity_decision.py:63` `gas_ok = 0.0 < gas_cost_usd` **requires gas>0** → a 0-gas opportunity fails the gate. Fail-closed. But a 0 here **overstates net_profit** in any view that reads it pre-gate. |
| `live/scanner.py:248`, `opportunity_engine.py:270` `flash_loan_fee_bps=0.0` | Balancer V2 flash loans on Base are **genuinely 0 bps**. | **(1) legitimate real default.** |
| `economics/size_optimizer.py:113` `gas_cost_usd=0.0, flash_loan_fee_bps=0.0` | Function **parameter defaults**; real callers pass real values. | **(1)/(3).** Risk only if a caller forgets to pass — audit callers in fix phase. |
| `economics/quote_provider.py:150-151` `... or 0.0` | Normalises economics dict. | **(2) fallback**, but same `None→0` hazard if surfaced raw. |
| DEX fee defaults `_NOMINAL_FEE_BPS[dex]`, `fee_bps or 5` (`base_venues.py:169-172`) | Nominal fee when a venue has none. | **(1) init default** (documented nominal). Fine for routing; should not be shown as a *measured* fee. |
| postvalidation denominator `→0.0` | Divide-by-zero guard (rate = 0 when n=0). | **(2) guard.** Honest, but a "0.0 success rate" must render as "n/a (no samples)" not "0 %". |
| `roi-probability` 42/0.643 (`server.py:925-926`) | Hardcoded stats. | **(4) accidental DEMO reaching any consumer.** See P1-8. |
| `_canonical_opp_to_contract` `... or 0` (1022,1037-1041) | Missing economics → 0 / fabricated. | **(4) — the primary accidental-financial-placeholder path (P0/P1).** |

---

## 10. Runtime / image metadata (answers Questions E, F, G)

**Endpoint** `GET /arbicore/version` → `_resolve_build_identity()` (`server.py:5160-5196`).
Values come from env → git → literal fallback:
```
app_version   = ARBICORE_VERSION or git_tag
git_sha       = ARBICORE_GIT_SHA or `git rev-parse HEAD` or "unknown"
git_tag       = ARBICORE_GIT_TAG or `git describe` or "unknown"
image_digest  = ARBICORE_IMAGE_DIGEST or "unset"
image_ref     = ARBICORE_IMAGE_REF   or "unset"
build_time    = ARBICORE_BUILD_TIME  or "unset"
runtime_env   = ARBICORE_ENV         or "unset"
```
**Why production reports unknown/unset**: the deployed Docker image has **no `.git` dir** (so
`git rev-parse`/`describe` fail) **and the build pipeline does not inject** `ARBICORE_GIT_SHA/
GIT_TAG/VERSION/BUILD_TIME/IMAGE_DIGEST/IMAGE_REF/ENV`. Result: every identity field falls back
to `"unknown"/"unset"`. Class: **(2) fail-safe default**, but **P1-9 operability**: you cannot
currently prove *Git == Docker == running code* in prod. Fix = inject these as build-args/env at
image build (no code change needed to the endpoint).

**Question E — API bind/port**: backend binds **`0.0.0.0:8001`** (supervisor-managed);
Kubernetes ingress routes `/api/*` → 8001, everything else → frontend `:3000`. Frontend calls
`REACT_APP_BACKEND_URL` (preview: `https://p0-3-certification.preview.emergentagent.com`). No
hardcoded prod host in the audited v2 client. ✅

**Question G — production (2.9.2-78b2a8c) vs latest validator (ce041c8) gap** (from code +
PRD/CHANGELOG; cannot introspect the running prod image from here):
Production predates this session's fixes, so it is missing (validator-only) work:
1. **MEV congestion source** (`runtime.py::make_base_congestion_source_from_env`,
   `eth_feeHistory.gasUsedRatio`) — prod fresh_fn can crash / DENY on `source_chain_congestion=None`.
2. **Aerodrome/Slipstream on-chain address+TVL propagation** (`aero_resolver.resolve_and_propagate`,
   `v3_state` registry fallback) — prod may mis-resolve Aerodrome pools / miss TVL.
3. **Case-insensitive Base token lookup** (`base_venues.canonical_symbol/token_address`) — prod can
   `KeyError`/DENY on cbETH/USDbC/cbBTC/rETH/wstETH/weETH routes.
4. **True all-in L1/L2 cost gate** (`searcher/base_all_in_cost.py`) — prod economics omit Base L1
   data fee → **net-profit overstated** in prod.
5. **Spread-widener watch + near-threshold signal** (`scripts/m3_0_spread_widener_watch.py`) — read-only
   tooling absent in prod.
> These are **validator/searcher backend** deltas. They do **not** change the frontend
> data-truth defects in §3 (those exist in both prod and this branch's `server.py`).

---

## 11. Ranked findings (fix backlog for Phase 2)

### P0 — operator/safety/financial truth
- **P0-1** Fake **100 % safety** for un-risk-assessed rows: `safety = 1 - risk_score/100` with
  `risk_score` defaulting `0.0` (canonical.py:86 + server.py:1037) → `SafetyPill 100 %`.
  → *Fix*: emit `safety=null` (and pill "—") unless a real risk assessment exists; treat
  `risk_score` as unknown vs a real 0.
- **P0-2** **Implausible return %**: USD `expected_profit_usd` put in `return_low/high`
  (server.py:1040-1041) then rendered `×100 %` by `fmtPct` (Primitives.jsx:129). Also a
  fabricated ±10 % band. → *Fix*: separate "expected profit (USD)" from "% return"; render USD
  with `fmtUsd`; only show a % when a real return fraction exists; `null → "—"`.
- **P0-3** **Verdict = lifecycle, not economics**: `GO` when status∈{VALIDATED,APPROVED}
  (server.py:1025-1027). → *Fix*: verdict must reflect economic validation
  (live-quoted + gates passed + provenance REAL), or relabel to a neutral "stage" chip and add a
  distinct economic-verdict field. Show `UNVERIFIED` for un-priced candidates.

### P1 — incorrect financial/market values
- **P1-1** Spread `None → 0.0 bps` coercion + percent/bps unit assumption (server.py:1038).
- **P1-2** "Depth" column actually shows `capital_required_usd`; `None → $0` (server.py:1039).
  Either surface **real pool TVL** or relabel the column and show "—" when absent.
- **P1-3 / P1-4** Confidence & Discovery score `None → 0` shown as real (server.py:1022,1346;
  Primitives.jsx:42-43). Add an UNAVAILABLE pill state.
- **P1-5** Provenance (`source_data_quality`) present in payload but **never rendered** on
  Opportunities table/drawer — operator can't tell SIMULATED from REAL/VERIFIED_REAL.
- **P1-6** Drawer Reasoning/Verification blocks are **DEMO/HARDCODED** (server.py:1063-1076):
  synthetic confidence breakdown, `gates_passed` literal, `quote_source="canonical_opp_repo"`,
  `fresh_window_s=60`. Present as real telemetry.
- **P1-7** Capital balances: confirm UNAVAILABLE (not `$0`) when RPC/address missing.
- **P1-8** `roi-probability` hardcoded DEMO + unauthenticated (server.py:920-931).
- **P1-9** `/arbicore/version` reports unknown/unset in prod — inject build metadata env at image build.

### P2 — non-critical stale/empty
- **P2-1** Age parse failure → `age_s=0` → FreshnessBadge "0s ago" fresh (server.py:1019-1021).
- **P2-2** Discovery `calibration.ece=0.0 / drift_alert=False` hardcoded (server.py:1423-1424).
- **P2-3** Postvalidation "0.0 rate" on zero samples should render "n/a".
- **P2-4** Legacy route-search TVL gate is a no-op (`min_pool_tvl_usd=0.0`) — depth unenforced in
  that engine; don't derive operator "depth" from it.

### P3 — cosmetic
- **P3-1** Live Ops "GREEN" pill means *running/has-alerts*, not *ready* — relabel tone/text.
- **P3-2** Legacy `src/pages/*` & `src/components/{execution,panels,portfolio}` trees are not in
  the primary route but still ship in the bundle; several use `lib/fmt.js` with its own coercions
  — dead-weight risk if a deep link exposes them.

---

## 12. Recommended fix strategy (for your approval — Phase 2, not yet done)

Two coordinated layers, mirroring the honest Control-Center pattern:
1. **Backend truth (server.py `_canonical_opp_to_contract` + detail):** stop `or 0` coercion —
   pass through `null` for absent economics; split USD-profit vs %-return into distinct,
   correctly-named fields; add an explicit `economic_state` (DISCOVERED / LIVE_QUOTED / VERIFIED
   / ECONOMICALLY_VALID) and a real economic `verdict`; surface `source_data_quality`; drop the
   DEMO reasoning/verification blocks or replace with real gate telemetry when present. Guard
   `roi-probability` behind auth or remove it.
2. **Frontend truth (`Primitives.jsx` + Opportunities/Discovery/Drawer):** add UNAVAILABLE
   states to `ConfidencePill`/`SafetyPill`/`FreshnessBadge` (render "—" for `null`, distinct
   from a real 0); render USD with `fmtUsd`, % only for genuine fractions; add a provenance chip;
   never paint GREEN/SAFE/GO unless the backend says the economic state warrants it.

All changes are **display-truth only** — no gate, mode, signing, or broadcast behaviour is
touched; M3 stays fail-closed. Each batch ships with tests + a screenshot proving zeros/greens
are replaced by "—"/UNAVAILABLE/UNVERIFIED.

*End of audit — awaiting your review before any code change.*
