# ArbiCore X ↔ Strategy Factory — GAP + OVERLAP Audit (AUDIT/PLANNING ONLY)

Branch `phase3/final-proof-completion` (HEAD `2d213a5`); `main` untouched (`621faea`).
No code ported/merged, no data changed, no safety gate touched, no signer/broadcast/
live enabled, no secrets requested/exposed. Fail-closed posture preserved.

> **SF access:** `strategy-factory-canonical` remains **inaccessible** from this
> workspace (re-probed this turn: `could not read Username for github.com` — no
> credential mechanism, private repo). All Strategy-Factory-side cells are
> **SF-UNVERIFIED**. The ArbiCore side below is inspected from **real code + tests**,
> not filenames.

---

## 1. EXECUTIVE SUMMARY

**You very likely do NOT need to take code from Strategy Factory for ArbiCore's
downstream roadmap.** ArbiCore already implements — and runtime-wires + tests — the
entire downstream stack (economics, EV, size optimizer, 11-check simulation gate,
discovery, evidence/provenance, ranking/confidence, and a **working advisory learning
loop** of ~3,500+ LOC). The only genuine gaps are **upstream research** capabilities
(generic Strategy IR/DSL, generation/mutation/evolution, backtest/walk-forward/
Monte-Carlo/robustness, external-knowledge connectors). Per the agreed boundary those
should **stay in Strategy Factory** (out-of-process) and reach ArbiCore only as a
**non-executable Strategy IR ingestion**. → **Recommended: OPTION D** (keep SF
separate; integrate via Strategy IR) + a **small native** IR-ingestion build in
ArbiCore. Porting SF engines into ArbiCore is **not** recommended.

## 2. ARBICORE CAPABILITY INVENTORY (real code + tests)

| # | Capability | Status | Location (real) | Exercised? | Reuse as-is |
|---|---|---|---|---|---|
| A | Strategy representation / IR | PARTIAL | `models/{opportunity_contract,canonical,discovery,enums}.py` (opportunity-level; **no generic strategy DSL**) | Yes (runtime) | Keep; extend for IR ingest |
| B | Strategy registry | MISSING | — | — | New (small) |
| C | Versioning / lifecycle | PARTIAL | `scanners/flash_loan_arbitrage/strategy_tagging.py`, `execution/mode.py` ladder | Yes | Extend |
| D | Strategy generation | MISSING | — | — | Keep in SF |
| E | Strategy mutation | MISSING | (grep hits are false positives) | — | Keep in SF |
| F | Evolution / genetic search | MISSING | — | — | Keep in SF |
| G | Parameter optimization | EXISTS (domain) | `economics/size_optimizer.py` (notional/liquidity/gas/flash/EV) | Yes (Phase-2/3 tests) | Yes |
| H | Backtesting | MISSING | — | — | SF role / defer |
| I | Walk-forward / OOS | MISSING/PARTIAL | `postvalidation/`, decision-history exists; no WF harness | Partial | Adapt later |
| J | Monte Carlo / robustness | MISSING | — | — | SF role / defer |
| K | Stress testing | MISSING | — | — | SF role / defer |
| L | Research / knowledge ingestion | MISSING | `knowledge`≈1 file | — | New (P2) |
| M | External knowledge connectors | MISSING | — | — | New (P2) |
| N | Provenance / source tracking | EXISTS | `evidence/audit_provenance.py`, provenance in ~100 files | Yes | Yes |
| O | Trust / confidence scoring | EXISTS | `intelligence/{confidence,confidence_v2,roi_probability,scoring}.py`, `learning/concrete/confidence_engine.py` | Yes | Yes |
| P | Strategy ranking | EXISTS | `intelligence/scoring.py`, EV in `economics/expected_value.py` | Yes | Yes |
| Q | Learning / feedback loop | EXISTS (advisory) | `learning/` + `learning/concrete/` (~3,500 LOC) | Yes (tests+runtime) | Yes (advisory-only) |
| R | Outcome collection | EXISTS | `learning/concrete/outcome_tracker.py` (245), `outcomes.py`, coll `arbicore_outcomes` | Yes | Yes |
| S | Replay infrastructure | PARTIAL | `mid_replay`, `test_iter10_settlement_replay.py`, historical replay | Yes | Extend |
| T | Calibration | EXISTS | `calibrator_isotonic.py` (340), `calibration_worker.py` (370), coll `calibration_log` | Yes (`test_wave3_calibrator_unit`) | Yes |
| U | Evidence bundles | EXISTS | `evidence/{bundle,signer,audit_provenance}.py` (Ed25519 audit signer) | Yes | Yes |
| V | Discovery | EXISTS | `discovery/{base_pool_registry,base_venues,multichain_venues}.py` | Yes | Yes |
| W | Route/economic validation | EXISTS | `economics/{opportunity_engine,opportunity_decision,net_profit,quote_provider}.py` | Yes (Phase-2/3) | Yes |
| X | Simulation / fork validation | PARTIAL | gate proven (`opportunity_decision`); on-chain fork **BLOCKED-BY-ENV** (no RPC) | Gate yes; fork no | Gate yes |
| Y | Safety / evidence gates | EXISTS | `execution/*`, kill switch, allowlists, capital policy, sim gate | Yes | Yes (authority) |

## 3. LEARNING INVENTORY (loop trace)

Chain status (real modules):
- observation ✓ `state_observers.py` (154), `adaptive_weights_observer.py` (246)
- prediction ✓ `confidence_engine.py` (239) + `calibrator_isotonic.py` (340)
- decision ✓ `economics/opportunity_decision.py`; coll `decision_history`/`mid_decisions`
- outcome ✓ `outcome_tracker.py` (245); coll `arbicore_outcomes`
- error ✓ `calibration_worker.py` (370) (isotonic calibration error)
- learning/update ✓ `adaptive_weights_worker.py` (244) → `adaptive_weight_recommendations`
- validation → **PARTIAL** (recommendations advisory; no formal promotion-gate)
- versioning → **PARTIAL** (recommendations stored; no explicit rollback/version governance)
- future influence ✓ advisory weights feed confidence/ranking (NEVER hard gates — proven `test_confidence_never_flips_execution`)

Supporting: `regime_classifier.py`/`regime_worker.py`, `sequence_miner.py` (temporal
sequences), `survival.py`, `route_success_tracker.py`, `metrics_aggregator.py`,
`ledger.py` (317), `evaluator_worker.py`. Tests: `test_adaptive_weights`,
`test_outcome_tracker_concrete`, `test_regime_classifier`, `test_wave3_calibrator_unit`,
`test_p0b_learning_ledger`, `test_learning_interfaces`, `test_outcome_repo_contract`.

**Classification: already functional (advisory).** Only the governance links
(validation→versioned-promotion→rollback) are PARTIAL. **Not a blocker.**

## 4. STRATEGY FACTORY CAPABILITY INVENTORY
**SF-UNVERIFIED — repository not accessible.** Cannot inspect SF source, imports,
deps, DB deps, external services, FX vs EVM coupling, or tests. Requires a read-only
checkout/archive (see §11) to complete.

## 5. OVERLAP MATRIX

| Capability | ArbiCore status | SF status | Recommendation | Effort |
|---|---|---|---|---|
| Strategy IR (generic) | PARTIAL | SF-UNVERIFIED | NEW_BUILD (ingest schema) | Medium |
| Strategy registry | MISSING | SF-UNVERIFIED | NEW_BUILD | Small |
| Lifecycle/versioning | PARTIAL | SF-UNVERIFIED | KEEP_ARBICORE + extend | Small |
| Generation/mutation/evolution | MISSING | SF-UNVERIFIED | DO_NOT_PORT (keep in SF) | — |
| Optimization (sizing) | EXISTS | SF-UNVERIFIED | KEEP_ARBICORE | — |
| GA/portfolio search (candidate proposer) | MISSING | SF-UNVERIFIED | ADAPT_FROM_SF (proposer only) / DEFER | Large |
| Backtest/WF/MC/robustness | MISSING | SF-UNVERIFIED | ADAPT_FROM_SF (EVM) / DEFER | Large |
| Regime analysis | EXISTS | SF-UNVERIFIED | KEEP_ARBICORE | — |
| Knowledge/external connectors | MISSING | SF-UNVERIFIED | NEW_BUILD (public sources) | Large |
| Trust/provenance | EXISTS | SF-UNVERIFIED | KEEP_ARBICORE | — |
| Ranking/EV/confidence | EXISTS | SF-UNVERIFIED | KEEP_ARBICORE | — |
| Learning loop | EXISTS (advisory) | SF-UNVERIFIED | KEEP_ARBICORE (+governance) | Small–Medium |
| Evidence bundles | EXISTS | SF-UNVERIFIED | KEEP_ARBICORE | — |
| Discovery/route/econ validation | EXISTS | SF-UNVERIFIED | KEEP_ARBICORE | — |
| Simulation gate / fork | PARTIAL | SF-UNVERIFIED | KEEP_ARBICORE (fork needs RPC) | — |
| Signer/broadcast/execution | EXISTS (authority) | must not exist in SF | DO_NOT_PORT | — |

## 6. EXACT REUSABLE / ADAPTABLE MODULES
Cannot be finalized (SF-UNVERIFIED). *Candidate* adaptation targets (architecture,
not wholesale copy): SF Strategy-IR schema/interpreter; SF backtest/WF/MC/robustness
harness (→ EVM fork/decision-history); SF GA/search (→ candidate proposer only); SF
public-source connector framework + trust/provenance. Confirm against real code first.

## 7. MODULES NOT TO PORT (regardless of SF verification)
- Anything that could set execution mode, engage/disengage kill switch, sign, or
  broadcast, or any reverse control path SF→ArbiCore execution/safety. **Hard F.**
- FX-market-specific logic (sessions/pip/lot/FX regimes) unless generalized. **E.**
- SF's own execution/order-management (if any) — ArbiCore is the sole execution authority.

## 8. P0 / P1 / P2 / DEFERRED ROADMAP
- **P0 (current roadmap):** nothing from SF required. Continue ArbiCore Phase-3
  offline hardening; clear fork/on-chain BLOCKED items when RPC is provisioned.
- **P1:** small native **Strategy IR ingest contract + registry + one-way admin API**
  (enables SF integration without porting engines); complete learning **governance**
  (validation→versioned-promotion→rollback) on the existing advisory loop.
- **P2:** external-knowledge connector framework (public sources); EVM backtest/WF/MC.
- **DEFERRED:** SF generation/mutation/evolution/GA (stay out-of-process in SF).
- **DO_NOT_PORT:** execution/signer/broadcast; FX-specific logic; reverse control.

## 9. BUILD-SIZE ESTIMATES (native ArbiCore work)
| Build | Size | Modules | Collections | API | Frontend | Tests | Ext deps | Migration |
|---|---|---|---|---|---|---|---|---|
| Strategy IR ingest schema + fingerprint | Medium (500–2k) | 2–3 | 0 | 0 | 0 | schema/fuzz | none | none |
| strategy_registry + candidate store | Small (<500) | 1–2 | 2–3 (additive) | 0 | 0 | CRUD/index | none | additive |
| One-way admin ingestion API + adapter | Medium | 2 | 0 | +3 (admin) | optional | boundary tests | none | none |
| Learning governance (promote/version/rollback) | Small–Medium (500–1.5k) | 2 | 1 (versions) | +1 | optional | leakage+rollback | none | additive |
| External knowledge connectors (public) | Large (2k–5k) | 4–6 | 2 | +2 | optional | connector/robots | httpx/feed libs | additive |
| EVM backtest/WF/MC harness | Large–V.Large | 5+ | 1–2 | +1 | optional | many | archive RPC | additive |

## 10. RECOMMENDED ARCHITECTURE
`SF (separate): research→generate→mutate→evolve→optimize→validate → emits StrategyIR +
fingerprint + version + provenance (NON-executable)` → **one-way admin ingestion** →
`ArbiCore: registry → candidate→opportunity adapter → economics/EV/optimizer →
simulation gate → fork/OOS/stress → evidence → ranking → PAPER/SHADOW → [operator]
future LIVE`. No reverse control path. SF/learning influence ranking/selection/
hypotheses/optimization only — never kill switch, signer, broadcast, allowlists,
quote freshness, repayment, calldata, risk limits, readiness, live mode.

## 11. RECOMMENDED NEXT IMPLEMENTATION STEP
**Decision first (no code):** adopt **OPTION D** (SF separate + Strategy IR ingestion).
If accepted, the first *implementation* step is the **P1 Strategy IR ingest schema +
`strategy_registry` + one-way admin API** (Small–Medium, additive, non-executable) —
this unblocks SF integration without porting any SF engine. To finalize §4/§6, provide
a **read-only** SF checkout or a source archive (no secrets); I will then complete the
A–F verdicts, dependency/test/legacy analysis, and adaptation sizes, and update this
doc — still audit-only, no porting.

## 12. SAFETY CONFIRMATION
No live execution, no signer/broadcast, kill switch untouched, execution authorization
unchanged, no secrets requested/exposed, no DB reset/recreate, no architectural change
made. `main` untouched (`621faea`). Posture: **SHADOW=READY; PAPER/LIMITED_LIVE/
FULL_AUTOMATION=BLOCKED.**
