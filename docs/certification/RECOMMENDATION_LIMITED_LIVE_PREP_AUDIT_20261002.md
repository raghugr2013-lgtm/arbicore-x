# Recommendation Mode → Limited Live Canary — Preparation Audit (docs only)

- **Status:** **PREP / NOT READY TO ACTIVATE**
- **Date:** 2026-10-02
- **Scope:** Parallel preparation **only** — inventory controls, gaps, blockers
- **Hard stop:** **NO** Recommendation Mode enablement, **NO** LIMITED_LIVE / canary activation, **NO** AUTOEXEC/RUNTIME, **NO** signing/broadcast, **NO** source/config/gate changes, **NO** rebuild/deploy/live tx
- **Runtime context:** SHADOW campaign continuous on `arbicore-x-backend-new` (`g5.79-green-20260927`); official Gate 9=24h / Gate 10=72h **unchanged** and **not** yet met (~1.86h elapsed at companion status snapshot)

---

## Executive verdict

Code already contains a fail-closed path from **analysis modes → Limited-Live eligibility → 6-gate broadcast ladder**, plus paper-validation and approval gates. What is **missing for a safe Recommendation → Limited Live canary** is primarily **ops proof and authority**, not a greenfield rewrite:

1. Sustained Gate 9 (24h) / Gate 10 (72h) SHADOW paper evidence (currently CONDITIONAL; evidence_total=0).
2. Genuine A≥1 / EXECUTABLE economics (A=0 honest today).
3. Explicit operator mode promotion + kill disengage + live_execution enable — all currently correctly **OFF**.
4. Deployed executor + funded burner + canary caps on a single chain (historical audits: contract built, deploy/proof incomplete on this cert path).
5. Clarification that there is **no separate enum named `RECOMMENDATION`** — “Recommendation Mode” maps to advisory surfaces + non-broadcast analysis modes (OBSERVE/PAPER/SHADOW) plus intelligence recommendations UI/API.

**Do not activate.** Remain SHADOW until Gate 9/10 continuity and canary prerequisites are separately authorized.

---

## 1. What “Recommendation Mode” means in this codebase

| Concept | Reality |
|---|---|
| Mode ladder | `OBSERVE → PAPER → SHADOW → LIMITED_LIVE → FULL_LIVE` (`arbicore/execution/mode.py`) |
| Named `RECOMMENDATION` execution mode | **Does not exist** as a mode enum value |
| Closest behavioral meaning | Non-broadcast analysis (PAPER/SHADOW/OBSERVE) + operator-facing **recommendations** (intelligence API/UI) + `ApprovalGate` (advisory) + `evaluate_limited_live_eligibility` (eligibility only) |
| Flash-loan default | `flash_loan_arbitrage=SHADOW` |
| Broadcast modes | `{LIMITED_LIVE, FULL_LIVE}` only |

**Implication for prep:** “Enable Recommendation Mode” must be defined as an **ops playbook** (advisory/recommend-only posture with explicit human approval), not a single env flip named `RECOMMENDATION`.

---

## 2. Inventory — controls that already exist (do not rebuild)

### 2.1 Mode & broadcast authority

| Control | Location | Current production posture (this host) |
|---|---|---|
| Mode ladder + one-step promotion | `execution/mode.py` | Global `ARBICORE_EXECUTION_MODE=SHADOW`; flash strategy SHADOW |
| Broadcast allow-list | `is_broadcast_allowed` → LIMITED_LIVE/FULL_LIVE only | Not in broadcast modes |
| AUTOEXEC / RUNTIME autostart | env | **false / false** |
| Kill switch | safety API | **engaged** (`boot_default`) |
| `live_execution_enabled` | safety status | **false** |
| Capital policy | safety status | max_per_trade $500 / per_chain $5k / daily $25k (informational; live unused) |

### 2.2 Economic / risk gates

| Control | Status |
|---|---|
| Gate 7 atomic profit floor **$25** | Confirmed M6 post-alchemy PASS; unchanged |
| Gate 8 route TVL **$100k**, fail-closed unverifiable | Confirmed; unchanged |
| H05 exact-size (price feed / borrow sizer) | **OFF / UNSET** |
| Gate 9 MEV / congestion (pipeline naming; **≠** official 24h paper Gate 9) | Implemented in eligibility + verifier path |
| Paper validation required | `require_paper_validation=true` on safety status |
| Approval gate | `safety/approval.py` — kill / live_execution / paper_validation / caps (advisory Phase 8 note) |

### 2.3 Limited-Live eligibility (CONFIRMED ≠ EXECUTABLE)

`arbicore/execution/limited_live_eligibility.py` — mandatory controls (all must PASS or DENY):

`quote_complete`, `economics_ok`, `gate_7`, `liquidity_verified`, `gate_8`, `executor_capability`, `gate_9` (MEV), `borrow_size_feasible`, `balancer_liquidity`, `atomic_simulation`, `freshness_ok`, `provenance_complete`, `verification_confirmed`, `mode_allows`, `kill_switch_ok`

Invariants always false in module: `signed`, `broadcast`, `limited_live_enabled`.

### 2.4 Limited-Live broadcast ladder

`execution/broadcast.py` — 6-gate LimitedLiveBroadcaster: kill → mode → capital → secret → preflight `eth_call` → operator_confirm. Sole intended `eth_sendRawTransaction` path for this design.

### 2.5 Operator / readiness surfaces

| Surface | Role |
|---|---|
| `execution/operator_wizard.py` | LIMITED_LIVE readiness aggregator |
| `execution/limited_live_eligibility.py` + readiness matrix | Candidate-level deny reasons |
| `docs/LIMITED_LIVE_READINESS.md` | Code vs VPS config SoT |
| `reports/handoff/ARBICORE_X_LIMITED_LIVE_GATES.md` | 13-gate checklist; **LIMITED_LIVE_PROVEN=FALSE** |
| Intelligence Recommendations UI/API | Advisory rankings — not execution authority |
| Paper Validation Framework | Evidence path under SHADOW (`arbicore/paper/*`) |

### 2.6 Recent cert anchors (reuse, do not overwrite)

| Anchor | Result |
|---|---|
| M6 POST-ALCHEMY SHADOW | **PASS** — A=0 B=10 C=8 E=14; six-chain; 429 cleared |
| Capability matrix audit | **READY** for continued SHADOW Gate 9/10 campaign |
| Paper Gate 9–10 | **CONDITIONAL** (~1.04h then; now ~1.86h) — duration + evidence_total=0 |
| Accelerated status snapshot | **HEALTHY WITH OBSERVATIONS** — elapsed &lt;8h |

---

## 3. Gaps (prep checklist — implementation deferred)

| # | Gap | Why it matters for Recommendation → Canary | Severity |
|---|---|---|---|
| G1 | No first-class `RECOMMENDATION` mode / documented ops contract | Ambiguity risk of accidental LIMITED_LIVE flip | Medium (process) |
| G2 | Official Gate 9 (24h) / Gate 10 (72h) unmet | No sustained paper continuity proof | **Hard** (ops time) |
| G3 | `arbicore_paper_evidence` total = 0; opportunities_seen = 0 | No recommendable EXECUTABLE trail on this campaign | **Hard** (market/inventory) |
| G4 | A=0 / EXECUTABLE=0 | No positive net economics to canary | **Hard** (market) |
| G5 | Kill engaged + live_execution false (correct today) | Canary requires explicit later operator arming | Expected gate |
| G6 | Executor deploy / verify per target chain | Broadcast without verified receiver is unsafe | **Hard** (deploy — out of this session) |
| G7 | Balancer P1 subgraph unset; P1b Free getLogs range | Limits Balancer discovery depth (P0 ok) | Medium |
| G8 | PaperBroker wallet/PnL ledger absent | Gate 9 PnL currently derived from EXECUTABLE stages only | Medium (accounting) |
| G9 | UniV3-centric executor capability vs multi-venue routes | Many candidates deny at `executor_capability` | Medium–Hard |
| G10 | Explicit human approval record for canary | Required by Limited Live gates checklist | Process |

---

## 4. Blockers before any activation (ordered)

1. **Do not leave SHADOW** until official **Gate 9 (24h)** evidence is collected under existing criteria (not 8h accelerated).
2. Prefer **Gate 10 (72h)** drawdown continuity before LIMITED_LIVE canary.
3. Require **≥1** honest EXECUTABLE / A-path candidate with Gate 7/8 pass (no threshold lowering).
4. Produce a written **Recommendation ops contract** (advisory-only vs mode promotion steps) — docs/process, still no activation here.
5. Single-chain **canary envelope**: chain choice, capital caps ≤ policy, max-one execution, kill re-arm, signer isolation, executor verify PASS.
6. Disengage kill / enable live_execution / promote mode **only** under separate explicit operator order (not this audit).

**Current host blockers that correctly prevent accidental live:** SHADOW + AUTOEXEC off + RUNTIME off + kill on + live_execution false + no signing.

---

## 5. Suggested canary shape (design only — NOT authorized)

When (and only when) Gates 9/10 and economics allow, a **Limited Live canary** should be:

- **One chain** (likely Base or prior operator choice) with verified executor address
- **One** approved candidate after fresh revalidation
- Caps: ≤ `max_per_trade_usd` and a tighter canary sub-cap if operator sets one
- Kill switch armed before and re-armed after
- Full receipt / repayment / residual verification per `ARBICORE_X_LIMITED_LIVE_GATES.md` gates 8–11
- Immediate abort on any safety regression

This section is **not** an activation order.

---

## 6. Dependency on accelerated SHADOW campaign

| Milestone | Role relative to Recommendation → Canary |
|---|---|
| Now (~1.86h) | STATUS only; stay SHADOW |
| 8h accelerated confidence | Ops confidence **≠** Gate 9 PASS |
| 24h Gate 9 | Required continuity for paper P&amp;L non-negativity claim |
| 72h Gate 10 | Required drawdown continuity |
| Recommendation prep (this doc) | Parallel paperwork only |
| Limited Live canary | **After** Gate 9/10 + economics + executor + explicit approval |

---

## 7. Explicit non-actions (this session)

- No Recommendation / LIMITED_LIVE / FULL_LIVE enablement
- No AUTOEXEC / RUNTIME enablement
- No kill disengage
- No signer provisioning, funding, deploy, or live tx
- No Gate 7/8/H05 changes
- No campaign restart

---

## 8. References

- `docs/LIMITED_LIVE_READINESS.md`
- `docs/LIMITED_LIVE_FLASH_LOAN_READINESS_AUDIT.md`
- `reports/handoff/ARBICORE_X_LIMITED_LIVE_GATES.md`
- `docs/certification/M6_POST_ALCHEMY_RESET_SHADOW_20261002.md`
- `docs/certification/PAPER_GATE9_10_VALIDATION_20261002T072116Z.md`
- `docs/certification/ARBITRAGE_CAPABILITY_MATRIX_AUDIT_20261002.md`
- `docs/certification/SHADOW_ACCELERATED_STATUS_SNAPSHOT_20261002T080658Z.md`
- `app/backend/arbicore/execution/limited_live_eligibility.py`
- `app/backend/arbicore/execution/mode.py`
- `app/backend/arbicore/execution/broadcast.py`
- `app/backend/arbicore/safety/approval.py`
