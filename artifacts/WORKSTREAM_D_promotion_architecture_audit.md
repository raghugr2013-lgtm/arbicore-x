# Workstream D — Promotion / Mode Architecture Audit (read-only, design-only)

Branch: `engineering/gate9-parallel-93a20c9`  ·  Base: `93a20c9`  ·  Code changes: **NONE**
Rule honoured: do NOT create a new "Recommendation Mode"; do NOT activate live execution. Audit the
existing mode/promotion architecture, document what exists and what is missing for a future
human-approved execution stage. Gate 9 untouched.

---

## Modes that actually exist (`execution/mode.py`)

Canonical ladder (approved, enforced):

```
OBSERVE → PAPER → SHADOW → LIMITED_LIVE → FULL_LIVE
```

- `MODES = ("OBSERVE","PAPER","SHADOW","LIMITED_LIVE","FULL_LIVE")` — **per-strategy**, there is NO
  single global execution switch.
- **"Recommendation Mode" is NOT a ladder mode.** Confirmed: it does not appear in `MODES`,
  `TRADING_STRATEGIES`, or `default_mode_map()`. Do not introduce it.

### How each stage is represented
| Stage | Representation | Broadcast? |
|---|---|---|
| OBSERVE | ladder index 0 | no |
| **PAPER** | real ladder stage; backed by full `arbicore/paper/*` engine (paper_engine, simulator, runner, outcomes, classifier, evidence, stage_recorder, repo) | no |
| **SHADOW** | ladder index 2; flash-loan **default** (`default_mode_map()["flash_loan_arbitrage"]="SHADOW"`) — builds txs, estimates gas, validates profit, full sim, emits evidence, learns; **never broadcasts** | no |
| LIMITED_LIVE | ladder index 3 | **yes** (gated) |
| FULL_LIVE | ladder index 4 | **yes** (gated) |

### Execution authorization representation
- `is_broadcast_allowed(mode)` → **True only for `LIMITED_LIVE` / `FULL_LIVE`**. This is the single
  code predicate that authorizes on-chain broadcast / real order submission.
- Readiness matrix (`limited_live_readiness_matrix.py`) `operator_mode_allows` item: SHADOW
  **correctly denies**; Limited-Live attempt permitted only in LIMITED_LIVE/FULL_AUTOMATION.

### Approval gates that already exist
1. **Ladder-step gate** — `validate_transition(current, proposed)`: forward promotion must advance
   **exactly one step** (no SHADOW→FULL_LIVE skip); rollback (any number of steps back) always allowed
   and immediate.
2. **Strategy whitelist** — `transition()` rejects unknown strategies / unknown modes.
3. **Audit trail** — every transition appends an append-only `execution_mode_audit` row
   (`from_mode, to_mode, reason, at, actor`); state is one-doc-per-strategy, idempotent seeding.
4. **Signed evidence stamp** — on transition, when signing is configured, a Wave-5 signed evidence
   bundle stamps the change (per module docstring).
5. **Readiness prerequisites** (`build_readiness_matrix` / `gather_and_build`) — rpc, mongo, executor
   deployed + on-chain identity, **signer authorization**, operator mode, **kill switch**, and
   market-dependent per-candidate gates (Gate7 $25 / Gate8 / Gate9 / freshness / balancer liquidity /
   atomic simulation). Overall is fail-closed: software blockers → `SOFTWARE_INCOMPLETE`; else
   `AWAITING_OPERATOR_AND_ONCHAIN_ACTIONS`; matrix always reports `signed:false, broadcast:false,
   limited_live_enabled:false`.

---

## What is MISSING for a future human-approved execution stage

These are **design observations**, not authorised work. No code now.

1. **Explicit human-authorization record on `SHADOW → LIMITED_LIVE`.**
   Today the forward gate enforces *ladder-step validity* and records an `actor` string + reason, but
   there is no distinct, verifiable **human approval object** (e.g. a signed operator authorization /
   two-person rule / time-boxed approval token) specifically required to cross into a broadcast-capable
   mode. The transition is as strong as whoever can call `transition()`.
   - *Future minimal delta (when authorised):* require, for any transition where
     `is_broadcast_allowed(to_mode)` is True, a pre-recorded operator-authorization artefact
     (who/when/scope/expiry) validated before `_state.update_one`. Reuses the existing audit + signer
     infrastructure; adds a gate, not a new mode. **Do not build during Gate 9.**

2. **Readiness-matrix ↔ transition coupling is advisory, not enforcing.**
   `validate_transition` does not currently consult `build_readiness_matrix` — an operator could
   promote to LIMITED_LIVE while the matrix still shows BLOCKED/UNKNOWN items (broadcast would still be
   separately prevented by per-candidate gates + signer, so this is defence-in-depth, not an open
   hole).
   - *Future minimal delta (when authorised):* make a broadcast-capable forward transition require
     `matrix.overall == SOFTWARE_READY_...` (no software blockers) and signer READY. Additive gate.

3. **No "Recommendation Mode" — and none needed.**
   SHADOW already produces the recommendation surface (evidence bundles + CONFIRMED canonicals) without
   broadcast. A separate recommendation mode would duplicate SHADOW. **Do not create it.**

---

## Cross-chain execution (explicitly out of scope)
LIMITED_LIVE/FULL_LIVE broadcast authorization is same-chain flash-loan only. Cross-chain execution
requires a separate settlement/inventory/solver architecture that does not exist. Same-chain
broadcast capability does **not** imply cross-chain execution. Do not build.

---

## Summary
- The mode/promotion architecture is **real, per-strategy, one-step-forward, rollback-always,
  broadcast-gated to LIMITED_LIVE+**, with audit trail + signed stamp + fail-closed readiness matrix.
- PAPER and SHADOW are real stages (PAPER has a full engine); execution authorization = `mode ∈
  {LIMITED_LIVE, FULL_LIVE}` via `is_broadcast_allowed`.
- The only genuine *future* gaps are **(1)** an explicit human-authorization artefact on crossing into
  a broadcast-capable mode and **(2)** optionally coupling the readiness matrix to the forward gate —
  both additive gates, both frozen until explicitly authorised. **No code during Gate 9. No live
  execution. No new mode.**
