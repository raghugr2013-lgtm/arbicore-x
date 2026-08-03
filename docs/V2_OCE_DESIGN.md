# ArbiCore X — Operational Certification Engine (OCE) — Design (v2.0.3)

**Status:** DESIGN ONLY · not implemented
**Prerequisite for build:** MID has accumulated sufficient production data (≥14 SHADOW days minimum)
**Owner:** operator (promotion actions) + platform (evidence gathering)

---

## 1. Purpose

The **Operational Certification Engine (OCE)** determines when the platform has objectively earned the next level of operational authority. It removes subjective "gut-feel" promotion from operator to platform-verified evidence. Every promotion is backed by machine-collected KPIs, replay validation, calibration convergence, and policy-compliance history — all reading exclusively from the Market Intelligence Database (MID).

The four operational tiers form a directed graph with promotion (upward) and demotion (downward) transitions:

```
    OBSERVE  ─promote→  PAPER  ─promote→  SHADOW  ─promote→  AUTONOMOUS
       ▲                   │                │                    │
       └──demote─── (auto or operator; any stage may fall back)──┘
```

- **OBSERVE** — platform is booted; no writes to Mongo except health; MID is populated but strategy is inert. Not yet meaningful for arbitrage. Used during initial VPS provisioning.
- **PAPER** — strategy proposes but never signs. Every candidate opportunity is journalled with a synthetic outcome computed from live quotes + market state. Zero real capital. Zero real orders.
- **SHADOW** — strategy proposes AND simulates against realistic gas + slippage estimates. Signed evidence bundles are emitted for every terminal event. Still zero real capital. Distinguished from PAPER by evidence-signing invariance + gas realism.
- **AUTONOMOUS** — strategy proposes AND executes. Real capital moves. Real signatures are broadcast. Only reachable after formal OCE certification.

---

## 2. Universal evidence requirements (all promotions)

Before any promotion the OCE checks these invariants:

| # | Invariant | Source |
|---|---|---|
| U1 | MID is healthy — 11 domains available, no domain last-write older than 5 min | `MidReader.status()` |
| U2 | No kill-switch trip in the last 24 h | `mid_decisions` (gate=`kill_switch`) |
| U3 | Backend health probe green for last 24 h continuously | `mid_gas` presence (proxy for background workers alive) |
| U4 | No calibration-worker crash in last 24 h | `arbicore_signal_metrics` last-write freshness |
| U5 | Adaptive weights worker last-tick within 3 h | `arbicore_signal_metrics` last-write freshness |
| U6 | No unexplained `mid_enum_warnings` (unknown enum values indicate a mis-registered strategy) | `mid_enum_warnings` count |

Failing any universal invariant → promotion refused with the specific U-code cited.

---

## 3. Per-stage promotion criteria

### 3.1 OBSERVE → PAPER

**Required evidence:**
- E1. Platform booted continuously for ≥ 4 h (uptime probe)
- E2. MID has ≥ 1000 `mid_market_state` rows across ≥ 2 pairs on the primary chain
- E3. MID has ≥ 100 `mid_gas` rows on the primary chain
- E4. Auth users seeded (`auth_users.count ≥ 2`)

**Required KPIs:** none — this promotion establishes the strategy loop.

**Certification score:** N/A (baseline promotion; approved if E1–E4 pass).

**Required MID statistics:** market_state and gas domains non-empty with reasonable diversity.

**Required replay metrics:** none (replay engine not yet meaningful).

**Required confidence calibration:** none.

**Required policy compliance:** kill-switch disengaged; mode ladder at `paper` for target strategy.

**Promotion conditions:**
- E1 ∧ E2 ∧ E3 ∧ E4 ∧ U1..U4 (U5, U6 not required at this tier)

**Automatic demotion conditions:**
- MID health falls off for ≥ 10 minutes → auto-demote to OBSERVE

**Audit trail:**
- `oce_promotion` event written to `mid_decisions` with `gate="oce_promotion"`, `verdict="allow"`, reason JSON containing the evidence codes.

---

### 3.2 PAPER → SHADOW

**Required evidence:**
- E5. ≥ 500 opportunities journalled with terminal state `shadow_recorded` (from `mid_opportunities`)
- E6. Signed evidence pipeline is healthy — every terminal event has an evidence bundle counterpart in `arbicore_evidence_bundles`
- E7. Journal coverage — every discovery emit produced a corresponding `mid_opportunities` row (integrity check)

**Required KPIs (rolling 7-day window):**
- K1. `journal_writes_per_hour ≥ 20` (proves the discovery pipeline is alive)
- K2. `preflight_success_rate ≥ 60%` (the strategy is not producing structurally invalid plans)
- K3. `gate_pass_rate.kill_switch = 100%` and `gate_pass_rate.mode ≥ 95%` (policy plumbing is coherent)

**Certification score:** `S = 0.3·K2_norm + 0.3·K3_norm + 0.4·(evidence_signing_success_rate)`, threshold **S ≥ 0.75**.

**Required MID statistics:**
- ≥ 5 unique `route_id` observed
- `mid_confidence` domain populated (SignalConfidence engine emitting)
- `mid_outcomes.terminal` distribution includes both `rejected` and `shadow_recorded`

**Required replay metrics:** partial 2-question replay (why-success / why-fail) resolves for ≥ 90% of terminal rows in the last 24 h.

**Required confidence calibration:** Brier score computed on `mid_confidence` vs eventual outcome for the last 500 samples ≤ 0.30 (i.e. platform's confidence is at least weakly aligned with observed outcome).

**Required policy compliance:** operator has reviewed and signed off on the strategy's `capital_policy` shape for SHADOW mode (`mode="shadow"` in `arbicore_capital_policy`).

**Promotion conditions:**
- E5 ∧ E6 ∧ E7 ∧ K1 ∧ K2 ∧ K3 ∧ (S ≥ 0.75) ∧ U1..U6

**Automatic demotion conditions:**
- K2 drops below 40 % over any rolling 6 h window → auto-demote to PAPER
- Any kill-switch trip → immediate auto-demote to PAPER (regardless of tier)
- Brier drift: 7-day rolling Brier score deteriorates by > 0.15 → auto-demote

**Audit trail:**
- OCE writes `oce_evaluation` snapshot to a new `mid_replay` counterpart collection every promotion attempt (`oce_evaluations`).
- Every promotion + every automatic demotion emits a signed evidence bundle via the existing evidence pipeline.

---

### 3.3 SHADOW → AUTONOMOUS

**Required evidence:**
- E8. ≥ 14 continuous days at SHADOW tier with no automatic demotion
- E9. ≥ 5000 terminal opportunities in `mid_outcomes` at SHADOW tier
- E10. ≥ 200 counter-factual replays completed (full 5-question form, `mid_replay` populated)
- E11. Operator has completed the AUTONOMOUS-readiness walkthrough (existing `operator_wizard` flow) and signed the promotion evidence bundle with a live signer key
- E12. Wallet registry has a fully-funded execution wallet on the target chain (real gas balance ≥ operator-configured threshold)
- E13. Broadcast pipeline preflight-succeeded in dry-run for ≥ 100 recent SHADOW opportunities (proves calldata + gas + revert-decode chain is not fantasy)

**Required KPIs (rolling 14-day window):**
- K4. `platform_would_have_pnl_usd > 0` — sum of SHADOW-mode counter-factual PnL is positive (the platform's decisions would have made money)
- K5. `platform_beats_alternatives_rate ≥ 60%` — in ≥ 60 % of replayed opportunities, the platform's chosen route + provider outperformed the best plausible alternative
- K6. `confidence_calibration_brier ≤ 0.20` — the platform's confidence scores are well-calibrated
- K7. `worker_uptime_ratio ≥ 99.0%` on every background worker for the window
- K8. `gate_pass_rate.preflight ≥ 80%` — reasonable plans are being produced

**Certification score:** `S = 0.25·K4_sign + 0.25·K5 + 0.25·(1 − K6) + 0.15·K7 + 0.10·K8`, threshold **S ≥ 0.85**.

**Required MID statistics:**
- Coverage across ≥ 3 unique flash-loan providers
- Coverage across ≥ 2 unique DEXes on the primary chain
- ≥ 20 unique `route_id` observed across the window

**Required replay metrics:** full 5-question replay (why success, why fail, better route, better provider, better size) resolves for ≥ 95 % of terminal rows in the window.

**Required confidence calibration:** Brier ≤ 0.20 sustained over the entire window (not just the last day).

**Required policy compliance:**
- Capital policy for AUTONOMOUS mode has been drafted and signed by the operator with a live signer key.
- Kill-switch operator contact is verified reachable (last successful Telegram test message ≤ 24 h ago).

**Promotion conditions:**
- E8 ∧ E9 ∧ E10 ∧ E11 ∧ E12 ∧ E13 ∧ K4 ∧ K5 ∧ K6 ∧ K7 ∧ K8 ∧ (S ≥ 0.85) ∧ U1..U6 ∧ operator co-signature

**Automatic demotion conditions:**
- Any kill-switch trip → immediate demote to SHADOW
- 3 consecutive AUTONOMOUS broadcasts revert on-chain within a 4 h window → auto-demote to SHADOW
- K6 (Brier) rises above 0.30 for any 24 h rolling window → auto-demote to SHADOW
- K7 falls below 95 % for any 24 h rolling window → auto-demote to SHADOW
- Manual operator kill → immediate demote to SHADOW

**Audit trail:**
- Two-party signature on the promotion evidence bundle (platform key + operator live signer key). Bundle stored permanently in `arbicore_evidence_bundles` with `bundle_type="oce_autonomous_promotion"`.
- Every AUTONOMOUS broadcast is bidirectionally linked (`mid_decisions.replay_context.decision_snapshot_id` ↔ `mid_outcomes.replay_context.decision_snapshot_id`).

---

## 4. OCE data model (future — not built now)

New Mongo collections when OCE is implemented:

| Collection | Purpose | Retention |
|---|---|---|
| `oce_evaluations` | Every promotion evaluation attempt (allowed or refused) with full evidence + KPI + score payload | permanent |
| `oce_transitions` | Every state transition (promotion or demotion) with signed evidence pointer | permanent |
| `oce_kpis_hourly` | Materialised hourly KPI aggregates over MID (rolling windows) | 365 d |

Each collection carries the same strategy-agnostic metadata block as the MID (per §P1-α invariant 6) so the OCE covers CEX-DEX, funding, treasury, liquidation, cross-chain, and institutional-credit strategies without redesign.

## 5. OCE REST surface (future)

```
GET  /api/arbicore/oce/status                       — current tier per strategy + last evaluation summary
GET  /api/arbicore/oce/evidence/{strategy_type}     — full evidence + KPI + score for the current tier
POST /api/arbicore/oce/evaluate/{strategy_type}     — trigger a fresh evaluation (idempotent read-mostly)
POST /api/arbicore/oce/promote/{strategy_type}      — request promotion (requires operator signature for AUTONOMOUS)
POST /api/arbicore/oce/demote/{strategy_type}       — operator-initiated demotion
GET  /api/arbicore/oce/transitions?strategy_type=…  — audit log of transitions
```

## 6. Operator UX (future)

- Dashboard card: current tier per active strategy · time-in-tier · time-to-next-promotion (if pending)
- Promotion review panel: side-by-side evidence + KPI + score with each requirement marked pass/fail/pending
- Demotion audit view: red-flagged rows with root-cause link into MID
- Kill-switch remains the ultimate override — engaging it always demotes to SHADOW regardless of OCE state

## 7. Build plan (deferred)

Recommended sequencing (post v2.1.0):

1. Wait for 30 days of SHADOW-tier MID accumulation on the deployed VPS.
2. Implement the `oce_kpis_hourly` aggregator (~2 d).
3. Implement the OBSERVE→PAPER and PAPER→SHADOW promotion paths (~3 d).
4. Ship OCE dashboard card + evaluation endpoint (~2 d).
5. Implement SHADOW→AUTONOMOUS promotion path with two-party signature (~3 d).
6. Implement automatic demotion paths (~2 d).

Total estimated build effort: ~12 dev-days, spanning ~3 weeks including validation.

## 8. Non-implementation commitment

This document is design-only for v2.0.3.

- No OCE code has been added to the repository.
- No OCE collections exist in Mongo.
- No OCE endpoints have been wired.
- No OCE tests have been introduced.

The OCE is a future capability. It becomes buildable only once the MID has accumulated the corpus of data described in §3. Until then, mode ladder promotion remains an operator decision executed via the existing `/execution/mode` endpoint.
