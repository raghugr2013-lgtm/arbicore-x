# Paper Validation Minimal Delta Plan — Gates 9–10

- **Date:** 2026-10-02
- **Workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Audit input:** `docs/certification/PAPER_BROKER_READINESS_AUDIT_20261002.md` (`READY-WITH-MINOR-DELTA`)
- **Scope:** Plan only. **No** source modification. **No** SHADOW→PAPER promotion. **No** AUTOEXEC/RUNTIME. **No** live execution / signing / broadcast / deploy. **No** Gate 7 $25 change. **No** Gate 8 liquidity / H05 weaken. **No** PaperBroker rebuild.
- **Authority for gate labels:** `deploy/ARBICORE_X_HANDOFF_AUDIT.md` §8 autonomous execution gates (not flash-loan filter Gate 8 TVL / Gate 9 MEV).

---

## FINAL STATUS

**READY — no code change required**

Existing `arbicore/paper/*` evidence path + operator APIs can satisfy Gate 9 and Gate 10 **as written in the handoff**, under an evidence-derived paper P&L / drawdown interpretation. Do **not** implement wallet, fill ledger, P&L API, or six-chain simulator wiring for the next validation campaign.

---

## Gate definitions (exact handoff)

| Gate | Evidence required (handoff) | Depends on |
|---|---|---|
| **8 Paper execution** | “paper fills logged in `arbicore_paper_evidence`” | Gates 6–7 (market: ≥1 profitable route + atomic sim) — scarcity may keep A=0; evidence campaign still runnable |
| **9 24h validation** | continuous run, uptime, **non-negative paper P&L** | Gate 8 evidence path healthy |
| **10 72h validation** | sustained 72h, **drawdown within limits** | Gate 9 window extended |

**Immediate next autonomous gate after M6 SHADOW PASS:** Gate **8** (evidence campaign). Gates **9–10** are duration + accounting overlays on that same path — not a new broker architecture.

**Naming collision (do not confuse):**

| Label | Meaning in this plan |
|---|---|
| Handoff Gate 8 / 9 / 10 | Paper evidence → 24h P&L → 72h drawdown |
| Filter Gate 7 / 8 / 9 | $25 floor / TVL fail-closed / MEV — **frozen**; out of scope |

---

## Exact-source inspect summary

### Reused surfaces (`app/backend/arbicore/paper/*`)

| Module | Capability reused for Gate 9–10 |
|---|---|
| `runner.py` | Continuous cycles; `RunnerMetrics` (uptime, cycles, processed, exceptions) |
| `evidence.py` / `repo.py` | Immutable insert-only `arbicore_paper_evidence` (handoff “fills”) |
| `outcomes.py` / `classifier.py` | Closed 8-outcome vocabulary; EXECUTABLE = successful shadow path |
| `simulator.py` | `EthCallSimulator` + `HeuristicSimulator` + `SimulationRouter` (Base env map today) |
| `liquidity.py` / `stage_recorder.py` | Stage rigor already in pipeline |
| `paper_engine.py` | Legacy analysis only — **not** required for Gate 9–10 |

### Pipeline / accounting already on the path

| Location | What exists |
|---|---|
| `execution/pipeline.py` `_compute_profit` | Stage payload: `gross_profit_usd`, `gas_cost_usd`, `net_profit_usd`, `profitable` |
| `execution/pipeline.py` shadow decision | Journal `expected_result.expected_net_profit_usd` on `SHADOW_RECORDED` |
| `execution/pipeline.py` `_persist_evidence` | Stages (incl. profit) + inputs (chain/borrow/provider) on every bundle |
| PAPER ≡ SHADOW (non-broadcast) | Both terminate at shadow record — **do not demote to PAPER** |

### Evidence APIs (ops collection — sufficient)

| Endpoint | Gate use |
|---|---|
| `GET /api/arbicore/validation/metrics` | Gate 9–10 continuous run / uptime |
| `GET /api/arbicore/validation/report` | Histogram + `executable_rate` |
| `GET /api/arbicore/validation/evidence` (+ `/{id}`) | Spot-check “fills”; extract profit-stage `net_profit_usd` |
| Pulse `paper_validation` | Dashboard snapshot |
| `GET /api/arbicore/validation/daily_status` / `last_daily` | Optional ops cadence (MID validation reporter — complementary, not wallet) |

### Config / flags (ops-only; do not flip LIVE)

| Flag | Posture for Gate 9–10 |
|---|---|
| `ARBICORE_EXECUTION_MODE` / strategy modes | **Stay SHADOW** |
| `ARBICORE_PAPER_VALIDATION_ENABLED` | **true** on validation host |
| `ARBICORE_AUTOEXEC_AUTOSTART` | **false** |
| `ARBICORE_RUNTIME_AUTOSTART` | **false** |
| `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` | **off** if global runner on (avoid dup) |
| Gate 7 $25 / Gate 8 TVL / H05 | **unchanged** |

### Six-chain `eth_call`

- `SimulationRouter.from_env` maps only `base` / `base_sepolia` (`BASE_RPC_URL`, `BASE_SEPOLIA_RPC_URL`).
- Canonical RPC resolution elsewhere: `resolve_rpc_url_from_env` / `env_sync` (`ARBICORE_RPC_URL_<CHAIN>`, `{CHAIN}_RPC_URL`).
- Non-Base paper sim → documented **heuristic** fallback. M6 already certified six-chain SHADOW infra separately.

### Missing (confirmed)

- No `PaperBroker` type / paper wallet / balance ledger / paper-fill objects.
- No first-class cumulative paper P&L or drawdown API.
- No PAPER≠SHADOW behavioral split (irrelevant for this campaign).

---

## Gap disposition (Gate 9 vs Gate 10 vs neither)

| Gap (from audit) | Required for Gate 9? | Required for Gate 10? | Verdict |
|---|---|---|---|
| **Paper virtual wallet / balances** | No | No | **NO-GO implement.** Flash-loan paper path does not debit capital; handoff Gate 8 equates fills to evidence rows. |
| **Distinct paper fill objects / ledger** | No | No | **NO-GO implement.** Gate 8 wording: fills = `arbicore_paper_evidence`. |
| **First-class aggregated paper P&L API** | Metric yes; **new API no** | Same | **NO-GO implement.** Derive from EXECUTABLE evidence profit stages / journal `expected_net_profit_usd`. |
| **Drawdown tracker / limits API** | No | Metric yes; **new API no** | **NO-GO implement.** Chronological equity curve from same expected_net series; A=0 ⇒ PnL=0, drawdown=0 (honest). |
| **Six-chain `SimulationRouter.from_env` eth_call** | No | No | **NO-GO implement for Gates 9–10.** Quality-only; heuristic is already recorded on `simulation_backend`. |
| **PAPER≠SHADOW semantic split** | No | No | **NO-GO.** Stay SHADOW. |
| **Gas realism / live eth_gasPrice** | No | No | **NO-GO** for these gates. |
| **Liquidity silent-skip when TVL absent** | No (Gate 8 TVL filter separate) | No | **NO-GO** weaken/change. |

**If evidence-path validation can satisfy without these changes:** **Yes.** Recommend **no implement**.

---

## How Gate 9 / Gate 10 are satisfied without source (ops protocol)

### Shared preflight (non-negotiable)

1. Remain SHADOW; AUTOEXEC/RUNTIME off; no signing/broadcast/deploy.
2. Confirm `ARBICORE_PAPER_VALIDATION_ENABLED=true`; runner `is_running` via `/validation/metrics`.
3. Prefer single feeder: PaperValidationRunner only.
4. Gate 7 = $25; filter Gate 8 fail-closed; H05 off — unchanged.
5. Honest A=0 (zero EXECUTABLE) is a **valid** window outcome under market scarcity (same honesty rule as M6).

### Gate 8 (prerequisite evidence bar — ops)

- Collect `arbicore_paper_evidence` rows via runner + pipeline.
- Document sample validation_ids; treat each bundle as a paper fill (handoff convention).
- Pass criteria: evidence count > 0; no broadcasts; runner healthy. EXECUTABLE may be 0.

### Gate 9 — 24h (ops-only evidence recipe)

| Criterion | How to evidence (existing) |
|---|---|
| Continuous run | `/validation/metrics`: `is_running`, `cycles_completed`, `last_cycle_at` spanning ≥24h |
| Uptime | Same + process/host health; exception rate from `RunnerMetrics.exceptions` |
| Non-negative paper P&L | **Definition (canonical for this campaign):**  
  `paper_pnl_usd = Σ net_profit_usd` over bundles with `outcome=EXECUTABLE`, where `net_profit_usd` is taken from the **profit** stage payload (fallback: journal `expected_result.expected_net_profit_usd`).  
  If EXECUTABLE=0 → `paper_pnl_usd = 0` → **non-negative**.  
  Produce the sum in the certification report (Mongo query or scripted read of evidence APIs). **No new module.** |

### Gate 10 — 72h (ops-only evidence recipe)

| Criterion | How to evidence (existing) |
|---|---|
| Sustained 72h | Extend Gate 9 window; continuous metrics unbroken (or documented restart with continuity note) |
| Drawdown within limits | **Definition:** equity curve `E_t = Σ_{i≤t} expected_net_i` over chronological EXECUTABLE evidence;  
  `drawdown = max(0, peak(E) − E_t)` / document max drawdown USD.  
  With EXECUTABLE=0: drawdown=0.  
  **Limit for A=0 window:** any configured non-negative limit is met. When EXECUTABLE>0 appear, use the same derived curve — still **no wallet**. Document the numeric limit used in the Gate 10 cert note (operator-chosen; do not invent live capital caps). |

### Explicit non-goals

- No LIMITED_LIVE / FULL_LIVE / signer unlock.
- No PaperBroker / wallet / fill ledger / P&L microservice.
- No SHADOW demotion to PAPER.
- No six-chain simulator patch in this phase.
- No Gate 7/8/H05 policy changes.

---

## Proposed code changes

**None.**

(Optional later — **not** Gate 9/10 blockers — retained from audit Tier 1 for traceability only:)

| If ever required | File | Reuse | Missing | Smallest delta | Tests | Why *not* now |
|---|---|---|---|---|---|---|
| Six-chain eth_call quality | `app/backend/arbicore/paper/simulator.py` `SimulationRouter.from_env` | `EthCallSimulator`, `resolve_rpc_url_from_env` / env_sync exports | Non-Base RPC map | Map eth/arb/op/poly/bnb/base via existing env keys | `tests/test_v2118_paper_validation_slice_b.py` | Gate criteria do not require eth_call over heuristic; M6 covered six-chain SHADOW |

**Do not implement** wallet / PnL API / fill ledger unless a future written gate rewrite **explicitly** mandates first-class broker accounting *and* rejects evidence-derived P&L. That would be a **new** scope (larger than minimal delta), not this plan.

---

## Acceptance checklist (Gate 9 then Gate 10)

### Gate 9 PASS package (certification doc only)

- [ ] 24h window timestamps + runner metrics snapshots (start / mid / end)
- [ ] `/validation/report` histogram at window end
- [ ] Paper P&L derivation method + numeric result (≥ 0)
- [ ] Spot-check ≥3 evidence IDs (stages present; `simulation_backend` recorded)
- [ ] Affirm: broadcasts=0; AUTOEXEC/RUNTIME false; mode SHADOW; Gate 7/8/H05 unchanged

### Gate 10 PASS package

- [ ] 72h continuity (or documented continuity after restart)
- [ ] Drawdown derivation + max drawdown vs stated limit
- [ ] Same safety affirmations as Gate 9

---

## Risk / honesty notes

1. **Gates 6–7 scarcity** can keep EXECUTABLE=0 for the entire 24h/72h window. That does **not** require inventing P&L or weakening gates; it yields PnL=0 / drawdown=0.
2. Handoff Gate 8 still “pending 6–7” for a *profitable* paper fill story — run Gate 8/9/10 evidence anyway; do not fake EXECUTABLE.
3. Profit-stage gas may be nominal % — acceptable for paper validation gates; do not expand scope into live gas oracle work.
4. Double-running PaperValidationRunner + flash-loan shadow route risks duplicate evidence — keep one feeder.

---

## Inspected artifacts (this plan)

- `docs/certification/PAPER_BROKER_READINESS_AUDIT_20261002.md`
- `deploy/ARBICORE_X_HANDOFF_AUDIT.md` §8
- `app/backend/arbicore/paper/*` (all modules)
- `app/backend/arbicore/execution/pipeline.py` (profit, simulate, evidence persist, shadow terminal)
- `app/backend/server.py` validation + paper endpoints
- `app/backend/arbicore/config/persistent.py` `resolve_rpc_url_from_env`
- `docs/PAPER_VALIDATION_v2.11.8_DELIVERABLES.md`
- M6 cert posture: remain SHADOW; no paper execution in that pass

---

## FINAL STATUS (repeat)

**READY — no code change required**

Gap go / no-go:

| Gap | Go implement? |
|---|---|
| Paper wallet | **NO-GO** |
| Paper fills ledger | **NO-GO** |
| Aggregated P&L / drawdown APIs | **NO-GO** (derive offline) |
| Six-chain eth_call wiring | **NO-GO** for Gate 9–10 |
| Ops evidence campaign (Gate 8→9→10) | **GO** (config/ops only) |
